"""Builds the +EV TD scorers rows for every game on the slate. Used by build_board; `python td_board.py` prints the top of the list."""
import numpy as np
import pandas as pd

import config
from model import odds_view as ov, td as T
from model.devig import blend, ev as ev_fn, label, to_prob

GROUP = {"RB": "RB", "WR": "WR", "TE": "TE", "QB": "QB"}


def _allowed(pw26: pd.DataFrame, pos: pd.Series) -> pd.DataFrame:
    """2026 TDs allowed per game to each position group by each defence, with rank (1 = allows the most)."""
    d = pw26.assign(grp=pw26.player_id.map(pos))
    d = d[d.grp.isin(["RB", "WR", "TE"])]
    games = pw26.groupby("opp").week.nunique()
    t = d.groupby(["opp", "grp"]).td.sum().unstack(fill_value=0)
    pg = t.div(games, axis=0)
    rk = pg.rank(ascending=False, method="min")
    return pg, rk, games


def td_rows(ctx: dict, res: list[dict], con) -> list[dict]:
    conv = T.league_conversion()
    pw = T.parse_pw(con, [config.LAST_SEASON, config.SEASON])
    wk = ctx["week"]
    players = pd.read_sql("select player_id, name, team, pos, nfl_seasons, draft_pick from players", con).set_index("player_id")
    pos = players.pos
    prof = T.usage_profile(pw, (config.SEASON, wk))
    # only players who can actually play: on the 53-man active list, or who played within the last 2 weeks (a player on IR or the practice squad
    # since long ago has no role to redistribute). This is what makes the lone healthy back the lead back when the others are out.
    cur = config.SEASON * 100 + wk
    prof = prof[prof.index.isin(ctx["active"]) | (prof.last_week >= cur - 2)]
    prof["team"] = prof.index.map(players.team).where(prof.index.isin(players.index), prof.team)
    prof["team"] = prof.team.fillna("")
    inj = ctx["injuries"].drop_duplicates("player_id").set_index("player_id")
    status = inj.status.to_dict()
    missing = {pid: 1 - config.PLAY_PROB.get(s, 1.0) for pid, s in status.items() if s != "healthy"}
    before_tot = prof[T.BANDS].sum(axis=1)
    prof2 = T.redistribute(prof, pos, missing)
    boost = (prof2[T.BANDS].sum(axis=1) / before_tot.replace(0, np.nan) - 1).fillna(0)
    pg, rk, gm = _allowed(pw[pw.season == config.SEASON], pos)
    lg_pg = pg.mean()
    depth = ctx["depth"]
    odds = ov.wide(ctx["odds_latest"])
    odds = odds[odds.market == "td_any"]
    rows = []
    for r in res:
        ev_id = ctx["event_ids"].get(r["game_id"])
        o = odds[odds.event_id == ev_id]
        if o.empty:
            continue
        ref = r["ref"]
        mm = (-ref["spread"] + config.MODEL_TRUST["margin"] * (r["margin"] + ref["spread"])) if ref.get("spread") is not None else r["margin"]
        tt = (ref["total"] + config.MODEL_TRUST["total"] * (r["total"] - ref["total"])) if ref.get("total") is not None else r["total"]
        pts = {r["home"]: (tt + mm) / 2, r["away"]: (tt - mm) / 2}
        for pid, grp in o.groupby("player_id"):
            if pid.startswith("sgo:") or pid not in players.index:
                continue
            pl = players.loc[pid]
            if pl.team not in (r["home"], r["away"]):
                continue
            st = status.get(pid, "healthy")
            pp = config.PLAY_PROB.get(st, 1.0)
            if pp == 0:
                continue
            opp = r["away"] if pl.team == r["home"] else r["home"]
            g = GROUP.get(pl.pos)
            if pid in prof2.index:
                row = prof2.loc[pid]
            else:
                row = pd.Series({**{b: 0.0 for b in T.BANDS}, "n_eff": 0.0, "n_games": 0, "td_games": 0, "td_rate_w": 0.0, "tds_per_game_w": 0.0, "snap_pct": np.nan, "tgt_share": 0.0})
            env = (pts[pl.team] / 22.5) ** config.TD_ENV_GAMMA
            ratio = 1.0
            if g in ("RB", "WR", "TE") and opp in pg.index and g in pg.columns and lg_pg[g] > 0:
                n = gm.get(opp, 0)
                ratio = 1 + (pg.at[opp, g] / lg_pg[g] - 1) * n / (n + 6)
            opp_mult = 1 + config.TD_OPP_STRENGTH * (ratio - 1)
            # role prior for players with little data: starter vs backup from the depth chart
            d = depth[(depth.gsis_id == pid)]
            rank = int(d.pos_rank.min()) if len(d) else 9
            lam_role = config.TD_ROLE_LAMBDA["starter"].get(pl.pos, 0.05) if rank <= 2 else config.TD_ROLE_LAMBDA["backup"]
            p0, l0 = T.prob_from_row(row, conv, config.TD_HIST_WEIGHT, env, opp_mult, pp, role_prior=lam_role * 0.0)
            wdata = row["n_eff"] / (row["n_eff"] + 3.0)
            l = wdata * l0 + (1 - wdata) * lam_role * env * opp_mult * pp
            l = (l + config.TD_LAMBDA_BASE) * config.TD_LAMBDA_SCALE
            p_model = T.calibrate(T.p_td(l))
            prices = {x.book: int(x.price_a) for x in grp.itertuples() if not pd.isna(x.price_a)}
            if not prices:
                continue
            p_mkt = float(np.mean([to_prob(v) / (1 + config.TD_ASSUMED_HOLD) for v in prices.values()]))
            bb = max(prices, key=prices.get)
            trust = config.TD_TRUST_BASE + config.TD_TRUST_DATA * row["n_eff"] / (row["n_eff"] + 6.0)
            ratio_gap = max(p_model / p_mkt, p_mkt / p_model)        # huge disagreements are usually the model missing a role (special teams, depth chart): believe them less
            trust = trust / (1 + config.TD_GAP_PENALTY * max(0.0, ratio_gap - 1.5))
            p_adj = p_mkt + trust * (p_model - p_mkt)          # how much of the model-vs-market gap is believed (less when we have little data)
            pf = blend(p_adj, p_mkt, config.MODEL_WEIGHT["td"])
            e = ev_fn(pf, prices[bb])
            rz = float(row.tgt_rz + row.tgt_gl + row.car_rz + row.car_gl)
            rows.append({
                "game_id": r["game_id"], "player_id": pid, "player": pl["name"], "pos": pl.pos, "team": pl.team, "opp": opp, "home": pl.team == r["home"], "kickoff": r["kickoff_utc"],
                "status": st, "best_book": bb, "best_price": prices[bb], "prices": prices, "p_model": round(p_model, 4), "p_market": round(p_mkt, 4), "p_final": round(pf, 4), "trust": round(trust, 2),
                "ev": round(e, 4), "label": label(e), "lambda": round(float(l), 3), "snap_pct": None if pd.isna(row.snap_pct) else round(float(row.snap_pct)),
                "tgt_pg": round(float(row.tgt_out + row.tgt_rz + row.tgt_gl), 1), "car_pg": round(float(row.car_out + row.car_rz + row.car_gl), 1), "rz_pg": round(rz, 2),
                "gl_pg": round(float(row.tgt_gl + row.car_gl), 2), "tgt_share": round(float(row.tgt_share), 3), "games": int(row.n_games), "td_games": int(row.td_games),
                "limited": bool(row.n_games < 3), "usage_boost": round(float(boost.get(pid, 0.0)), 2), "env_pts": round(pts[pl.team], 1),
                "opp_td_pg": None if not (g in pg.columns and opp in pg.index) else round(float(pg.at[opp, g]), 2),
                "opp_td_rank": None if not (g in rk.columns and opp in rk.index) else int(rk.at[opp, g]),
                "opp_td_lg": None if g not in lg_pg.index else round(float(lg_pg[g]), 2)})
    rows.sort(key=lambda x: -x["ev"])
    return rows


if __name__ == "__main__":
    import board_data, db
    con = db.connect()
    ctx, res = board_data.run(con)
    rows = td_rows(ctx, res, con)
    d = pd.DataFrame(rows)
    print(len(d), "players priced;", int((d.p_model >= config.TD_MIN_PROB).sum()), "with model >= 15%")
    top = d[d.p_model >= config.TD_MIN_PROB].head(15)
    print(top[["player", "pos", "team", "opp", "best_price", "p_model", "p_market", "p_final", "ev", "label", "games", "td_games", "limited"]].to_string(index=False))
    print(d.p_model.describe().round(3).to_dict())
