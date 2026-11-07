"""Builds the player-prop rows (all games on the slate). `python props_board.py` prints the top of the list."""
import math

import numpy as np
import pandas as pd

import config
import deep_dive as DD
from adapters import nflverse as nv
from model import odds_view as ov, props as P, td as T
from model.devig import blend, ev as ev_fn, label

POS_MARKETS = {"QB": {"pass_yds", "pass_td", "pass_comp", "pass_att", "pass_int", "pass_rush_yds", "rush_yds", "rush_att"}}
ALLOWED_COL = {"pass_yds": ("QB", "pass_yds"), "pass_td": ("QB", "pass_td"), "pass_int": ("QB", "ints"), "pass_att": ("QB", "att"), "pass_comp": ("QB", "att"),
               "pass_rush_yds": ("QB", "pass_yds"), "rush_yds": ("RB", "rush_yds"), "rush_att": ("RB", "car"), "rush_rec_yds": ("RB", "rush_yds")}
RECV_ALLOWED = {"rec_yds": "rec_yds", "receptions": "rec"}
LG_CR = {"WR": 0.63, "TE": 0.70, "RB": 0.78}
LG_YPR = {"WR": 12.5, "TE": 10.3, "RB": 7.6}


def _pos_ratio(pa, pos, num, den, opp):
    """What this defence allows to `pos` (num per den, e.g. yards per target) relative to the league; None if unknown."""
    try:
        a, b = pa[(pos, num)], pa[(pos, den)]
        lg = a.sum() / b.sum()
        return float(a[opp] / b[opp] / lg) if b[opp] > 0 and lg > 0 else None
    except KeyError:
        return None


def _weights(n):
    return 0.5 ** (np.arange(n)[::-1] / config.PROP_HALF_LIFE_GAMES)


def _wstats(stats: pd.DataFrame, pids: set) -> dict:
    out = {}
    d = stats[stats.player_id.isin(pids)].sort_values("order")
    for pid, x in d.groupby("player_id"):
        w = _weights(len(x))
        f = lambda c: float((w * x[c].fillna(0).values).sum())
        out[pid] = {"n": len(x), "w": float(w.sum()), "tgt": f("targets"), "rec": f("receptions"), "ryd": f("receiving_yards"), "car": f("carries"), "rsh": f("rushing_yards"),
                    "att": f("attempts"), "comp": f("completions"), "pyd": f("passing_yards"), "ptd": f("passing_tds"), "pint": f("passing_interceptions"),
                    "x": x}
    return out


def props_rows(ctx: dict, res: list[dict], con) -> list[dict]:
    stats = nv.get("stats", config.SEASON).assign(season=config.SEASON)          # this season only: enough games are in, last year is not used
    stats = stats[stats.season_type == "REG"].copy()
    stats["team"], stats["opponent_team"] = nv.norm_team(stats.team), nv.norm_team(stats.opponent_team)
    stats["order"] = stats.season * 100 + stats.week
    players = pd.read_sql("select player_id, name, team, pos from players", con).set_index("player_id")
    status = dict(zip(ctx["injuries"].player_id, ctx["injuries"].status))
    # team volume (recency weighted attempts and carries per game)
    tv = stats.groupby(["team", "order"]).agg(att=("attempts", "sum"), car=("carries", "sum")).reset_index().sort_values("order")
    team_vol = {}
    for t, x in tv.groupby("team"):
        w = _weights(len(x))
        team_vol[t] = (float((w * x.att).sum() / w.sum()), float((w * x.car).sum() / w.sum()))
    # usage after redistributing missing teammates' touches
    pw = T.parse_pw(con, [config.SEASON])
    prof = T.usage_profile(pw, (config.SEASON, ctx["week"]))
    # only players who can actually play: on the 53-man active list, or who played within the last 2 weeks (a player on IR or the practice squad
    # since long ago has no role to redistribute). This is what makes the lone healthy back the lead back when the others are out.
    cur = config.SEASON * 100 + ctx["week"]
    prof = prof[prof.index.isin(ctx["active"]) | (prof.last_week >= cur - 2)]
    pos = players.pos
    missing = {pid: 1 - config.PLAY_PROB.get(s, 1.0) for pid, s in status.items() if s != "healthy"}
    prof = T.redistribute(prof, pos, missing)
    prof["tgt_tot"] = prof.tgt_out + prof.tgt_rz + prof.tgt_gl
    prof["car_tot"] = prof.car_out + prof.car_rz + prof.car_gl
    # opponent defences (2026 only): per-attempt yards, completion %, yards per carry vs league
    dvals = DD.ranked(config.SEASON, "def", con)["vals"]
    lgm = dvals[["ypa", "comp_pct", "rush_ypc"]].mean()
    lg_er, sd_er, lg_ep, sd_ep = dvals.epa_rush.mean(), dvals.epa_rush.std(), dvals.epa_pass.mean(), dvals.epa_pass.std()
    rk_run = dvals.epa_rush.rank(method="min")           # 1 = best run defence (least EPA allowed per rush)
    rk_pass = dvals.epa_pass.rank(method="min")
    pa26, pa25 = DD.position_allowed(config.SEASON), DD.position_allowed(config.LAST_SEASON)
    odds = ov.wide(ctx["odds_latest"])
    odds = odds[odds.market.isin(config.PROP_MARKETS)]
    pids = set(odds.player_id) - {p for p in odds.player_id if p.startswith("sgo:")}
    ws = _wstats(stats, pids)
    rows = []
    for r in res:
        gid, home, away = r["game_id"], r["home"], r["away"]
        ev_id = ctx["event_ids"].get(gid)
        o = odds[odds.event_id == ev_id]
        if o.empty:
            continue
        ref = r["ref"]
        mm = (-ref["spread"] + config.MODEL_TRUST["margin"] * (r["margin"] + ref["spread"])) if ref.get("spread") is not None else r["margin"]
        tt = (ref["total"] + config.MODEL_TRUST["total"] * (r["total"] - ref["total"])) if ref.get("total") is not None else r["total"]
        pts = {home: (tt + mm) / 2, away: (tt - mm) / 2}
        wx = ctx["weather"].get(gid) or {}
        wind = 0.0 if wx.get("indoor") else float(wx.get("wind_mph") or 0.0)
        wind_f = 1 - min(0.12, 0.012 * max(0.0, wind - 12))
        for (pid, market), grp in o.groupby(["player_id", "market"]):
            if pid.startswith("sgo:") or pid not in players.index or pid not in ws:
                continue
            pl = players.loc[pid]
            if pl.team not in (home, away):
                continue
            st = status.get(pid, "healthy")
            if st == "out":
                continue
            p_pos = pl.pos
            if p_pos != "QB" and market.startswith("pass_") and market != "pass_rush_yds":
                continue
            if market == "pass_rush_yds" and p_pos != "QB":
                continue
            team, opp = pl.team, (away if pl.team == home else home)
            w = ws[pid]
            m_team = pts[team] - pts[opp]
            n_opp = int(dvals.at[opp, "games"]) if opp in dvals.index else 0
            # matchup: a stout run defence pushes the offence to throw, a leaky pass defence invites it (fitted on last season's neutral-situation pass rate)
            z_run = (dvals.at[opp, "epa_rush"] - lg_er) / sd_er if opp in dvals.index and sd_er else 0.0
            z_pass = (dvals.at[opp, "epa_pass"] - lg_ep) / sd_ep if opp in dvals.index and sd_ep else 0.0
            d_pr = (-config.PROP_PASS_RATE["run"] * z_run + config.PROP_PASS_RATE["pass"] * z_pass) * n_opp / (n_opp + 8.0)
            att_mm, car_mm = 1 + d_pr / 0.58, 1 - d_pr / 0.42
            att_t = team_vol.get(team, (33.0, 25.0))[0] * float(np.clip(1 - config.PROP_SCRIPT_PASS * m_team, 0.9, 1.1)) * att_mm
            car_t = team_vol.get(team, (33.0, 25.0))[1] * float(np.clip(1 + config.PROP_SCRIPT_RUSH * m_team, 0.9, 1.12)) * car_mm
            att_ratio, car_ratio = att_t / max(team_vol.get(team, (33.0, 25.0))[0], 1), car_t / max(team_vol.get(team, (33.0, 25.0))[1], 1)
            f_ypa = P.opp_factor(dvals.at[opp, "ypa"] / lgm.ypa if opp in dvals.index else None, n_opp)
            f_cmp = P.opp_factor(dvals.at[opp, "comp_pct"] / lgm.comp_pct if opp in dvals.index else None, n_opp)
            f_rsh = P.opp_factor(dvals.at[opp, "rush_ypc"] / lgm.rush_ypc if opp in dvals.index else None, n_opp)
            parts = ()
            rush_mu = rec_mu = None
            # ---- component means
            car_pg = float(prof.at[pid, "car_tot"]) if pid in prof.index else (w["car"] / w["w"])
            tgt_pg = float(prof.at[pid, "tgt_tot"]) if pid in prof.index else (w["tgt"] / w["w"])
            ypc = P.shrink(w["rsh"], w["car"], 4.3, 40)
            if market in ("rush_yds", "rush_att", "pass_rush_yds", "rush_rec_yds"):
                car = car_pg * car_ratio if p_pos != "QB" else w["car"] / w["w"] * car_ratio
                rush_mu = car * ypc * f_rsh
                rush_att_mu = car
            if market in ("rec_yds", "receptions", "rush_rec_yds"):
                g = p_pos if p_pos in LG_CR else "WR"
                cr = P.shrink(w["rec"], w["tgt"], LG_CR[g], 20)
                ypr = P.shrink(w["ryd"], w["rec"], LG_YPR[g], 15)
                tg = tgt_pg * att_ratio
                f_cr = math.sqrt(f_cmp * P.opp_factor(_pos_ratio(pa26, g, "rec", "tgt", opp), n_opp))      # this defence vs THIS position: catch rate ...
                f_yr = math.sqrt(f_ypa * P.opp_factor(_pos_ratio(pa26, g, "rec_yds", "rec", opp), n_opp))  # ... and yards per catch
                rec_n = tg * cr * f_cr
                rec_mu = rec_n * ypr * f_yr * wind_f
            if p_pos == "QB" and market.startswith("pass_"):
                att = att_t * 0.97                 # a QB with posted passing lines is the expected starter (about 3% of attempts go to a backup)
                ypa = P.shrink(w["pyd"], w["att"], 6.8, 150)
                cmp_ = P.shrink(w["comp"], w["att"], 0.64, 150)
                pass_yds = att * ypa * f_ypa * wind_f
            if market == "pass_yds":
                mu = pass_yds
            elif market == "pass_att":
                mu = att
            elif market == "pass_comp":
                mu = att * cmp_ * f_cmp
            elif market == "pass_td":
                mu = att * P.shrink(w["ptd"], w["att"], 0.045, 300) * (pts[team] / 22.5) ** 0.5
            elif market == "pass_int":
                mu = att * P.shrink(w["pint"], w["att"], 0.022, 400)
            elif market == "rush_yds":
                mu = rush_mu
            elif market == "rush_att":
                mu = rush_att_mu
            elif market == "rec_yds":
                mu = rec_mu
            elif market == "receptions":
                mu = rec_n
            elif market == "pass_rush_yds":
                rq = (w["rsh"] / w["w"]) * car_ratio
                mu, parts = pass_yds + rq, (pass_yds, rq)
            elif market == "rush_rec_yds":
                mu, parts = rush_mu + rec_mu, (rush_mu, rec_mu)
            else:
                continue
            if mu is None or not np.isfinite(mu) or mu <= 0:
                continue
            cons = {None if pd.isna(c["line"]) else float(c["line"]): c for c in ov.all_lines(grp)}
            refc = ov.consensus(grp)
            gap = abs(mu - refc["line"]) / max(refc["line"], 1.0) if refc and refc["line"] is not None else 0.0
            trust = config.PROP_TRUST / (1 + config.PROP_GAP_PENALTY * max(0.0, gap - 0.2))   # a huge gap to the line usually means the market knows a role/injury we do not
            opts = []
            for b in grp.itertuples():
                ln = None if pd.isna(b.line) else float(b.line)
                c = cons.get(ln)
                if c is None or ln is None:
                    continue
                po, pu = P.p_over(market, mu, ln, parts)
                for side, price, pm, pk in (("over", b.price_a, po, c["p_a"]), ("under", b.price_b, 1 - po - pu, 1 - c["p_a"])):
                    if pd.isna(price):
                        continue
                    decisive = pm + (po if side == "under" else (1 - po - pu)) if False else None
                    other = (1 - po - pu) if side == "over" else po
                    cond = pm / (pm + other) if (pm + other) > 0 else 0.5
                    p_adj = pk + trust * (cond - pk)
                    pf = blend(p_adj, pk, config.MODEL_WEIGHT["prop"])
                    e = ev_fn(pf * (1 - pu), price, p_push=pu) if pu else ev_fn(pf, price)
                    opts.append({"side": side, "book": b.book, "line": ln, "price": int(price), "p_model": round(cond, 4), "p_market": round(pk, 4), "p_final": round(pf, 4),
                                 "push": round(pu, 4), "ev": round(e, 4), "label": label(e)})
            if not opts:
                continue
            opts.sort(key=lambda x: -x["ev"])
            x = w["x"]
            ser = {"pass_yds": "passing_yards", "rush_yds": "rushing_yards", "rec_yds": "receiving_yards", "receptions": "receptions", "rush_att": "carries", "pass_td": "passing_tds",
                   "pass_comp": "completions", "pass_att": "attempts", "pass_int": "passing_interceptions"}
            if market in ser:
                v = x[ser[market]].fillna(0)
            elif market == "pass_rush_yds":
                v = x.passing_yards.fillna(0) + x.rushing_yards.fillna(0)
            else:
                v = x.rushing_yards.fillna(0) + x.receiving_yards.fillna(0)
            last = v.tail(12)
            pcol = ALLOWED_COL.get(market) or (((p_pos if p_pos in LG_CR else "WR"), RECV_ALLOWED.get(market, "rec_yds")) if market in RECV_ALLOWED else ("RB", "rush_yds"))
            if market == "rush_rec_yds" and p_pos in LG_CR:
                pcol = (p_pos, "rec_yds")
            a26, a25 = pa26[pcol], pa25[pcol]
            rows.append({
                "game_id": gid, "player_id": pid, "player": pl["name"], "pos": p_pos, "team": team, "opp": opp, "home": team == home, "kickoff": r["kickoff_utc"], "status": st,
                "market": market, "mu": round(float(mu), 2), "sd": round(math.sqrt(P.variance(market, mu, parts)), 2),
                "books": [{"b": b.book, "l": None if pd.isna(b.line) else float(b.line), "o": None if pd.isna(b.price_a) else int(b.price_a), "u": None if pd.isna(b.price_b) else int(b.price_b)} for b in grp.itertuples()],
                "ref_line": None if not refc else refc["line"], "ref_p_over": None if not refc else round(refc["p_a"], 4), "n_books": None if not refc else refc["n_books"],
                "opts": opts, "best": opts[0], "fd": next((o2 for o2 in opts if o2["book"] == config.REFERENCE_BOOK), None),
                "series": [round(float(z), 1) for z in v.tail(8)], "hit_n": int(len(last)),
                "hit_over": None if (not refc or refc["line"] is None or len(last) == 0) else round(float((last > refc["line"]).mean()), 2),
                "avg26": None if not (x.season == config.SEASON).any() else round(float(v[x.season.values == config.SEASON].mean()), 1), "n26": int((x.season == config.SEASON).sum()),
                "avg25": None if not (x.season == config.LAST_SEASON).any() else round(float(v[x.season.values == config.LAST_SEASON].mean()), 1),
                "opp_pa26": None if opp not in a26.index else round(float(a26[opp]), 1), "opp_rk26": None if opp not in a26.index else int(a26.rank(ascending=False, method="min")[opp]),
                "opp_pa25": None if opp not in a25.index else round(float(a25[opp]), 1), "opp_rk25": None if opp not in a25.index else int(a25.rank(ascending=False, method="min")[opp]),
                "opp_lg26": round(float(a26.mean()), 1), "opp_stat": f"{pcol[0]} {pcol[1]}",
                "opp_run_rk": int(rk_run[opp]) if opp in rk_run.index else None, "opp_pass_rk": int(rk_pass[opp]) if opp in rk_pass.index else None,
                "att_mm": round(att_mm, 3), "car_mm": round(car_mm, 3), "m_team": round(float(m_team), 1),
                "trust": round(trust, 2), "limited": bool(w["n"] < 4), "f_opp": round(float(f_ypa if "yds" in market else f_cmp), 3), "wind_f": round(wind_f, 3)})
    rows.sort(key=lambda z: -z["best"]["ev"])
    return rows


if __name__ == "__main__":
    import board_data, db
    con = db.connect()
    ctx, res = board_data.run(con)
    rows = props_rows(ctx, res, con)
    d = pd.DataFrame([{**{k: v for k, v in r.items() if k in ("player", "pos", "team", "opp", "market", "mu", "sd", "ref_line", "limited")}, **{"side": r["best"]["side"], "line": r["best"]["line"], "book": r["best"]["book"], "price": r["best"]["price"], "pm": r["best"]["p_model"], "pk": r["best"]["p_market"], "pf": r["best"]["p_final"], "ev": r["best"]["ev"], "lab": r["best"]["label"]}} for r in rows])
    print(len(d), "rows;", d.lab.value_counts().to_dict(), "; markets", d.market.value_counts().to_dict())
    print(d.head(14).to_string(index=False))
