"""Game model: projected margin / total per game, win-cover-total probabilities, blended with the de-vigged market, EV.

margin = ratings(EPA, pace) + HFA + QB + skill injuries + rest/travel + capped public/line-move signal
total  = ratings + QB + injuries + weather + capped public/line-move signal
Every adjustment is a config prior (config.py); the base ratings are tuned by backtest.py.
"""
import json
import re

import numpy as np
import pandas as pd

import config
from model import dist, injuries as INJ, ratings as R, qb as QB, odds_view as ov
from model.devig import blend, ev, label
from model.public import capped_adjustment

TZ = {**{t: 0 for t in "BUF MIA NE NYJ NYG PHI PIT BAL CLE CIN WAS ATL CAR JAX TB DET IND".split()},
      **{t: 1 for t in "CHI GB MIN KC NO HOU DAL TEN".split()},
      **{t: 2 for t in "DEN ARI".split()}, **{t: 3 for t in "LV LAC LA SEA SF".split()}}


def _skill_usage(con, season_now: int) -> pd.DataFrame:
    """Recent target share and rush share per player (last N appearances)."""
    pw = pd.read_sql("select season, week, player_id, team, stats_json from player_week where season>=?", con, params=(season_now - 1,))
    js = pw.stats_json.map(json.loads)
    pw["tgt"] = js.map(lambda d: d.get("target_share") or 0.0)
    pw["car"] = js.map(lambda d: d.get("carries") or 0.0)
    pw["tcar"] = pw.groupby(["season", "week", "team"]).car.transform("sum")
    pw["rsh"] = np.where(pw.tcar > 0, pw.car / pw.tcar, 0.0)
    pw = pw.sort_values(["season", "week"]).groupby("player_id").tail(config.USAGE_LOOKBACK_GAMES)
    return pw.groupby("player_id").agg(tgt=("tgt", "mean"), rsh=("rsh", "mean"))


def _weather_adj(w) -> tuple[float, str]:
    if w is None or w.get("indoor"):
        return 0.0, ""
    adj, why = 0.0, []
    wind = w.get("wind_mph") or 0
    if wind > config.WIND_MPH_THRESHOLD:
        a = max(-3.0, config.WIND_TOTAL_PER_MPH * (wind - config.WIND_MPH_THRESHOLD)); adj += a; why.append(f"wind {wind:.0f} mph {a:+.1f}")
    cond = (w.get("conditions") or "").lower()
    if (w.get("precip_pct") or 0) >= 60 or re.search(r"snow|sleet|(definite|likely|heavy).*(rain|storm)", cond):
        adj += config.RAIN_TOTAL_ADJ; why.append(f"precip {config.RAIN_TOTAL_ADJ:+.1f}")
    if (w.get("temp_f") is not None) and w["temp_f"] < 25:
        adj += config.COLD_TOTAL_ADJ; why.append(f"cold {w['temp_f']:.0f}F {config.COLD_TOTAL_ADJ:+.1f}")
    return adj, ", ".join(why)


def _rest(days) -> float:
    if days is None or pd.isna(days):
        return 0.0
    return config.REST_BYE_BONUS if days >= 10 else (config.REST_SHORT_PENALTY if days <= 5 else 0.0)


def project(ctx: dict) -> list[dict]:
    """ctx from gather(); returns one projection dict per game."""
    r, as_of = ctx["ratings"], ctx["as_of_t"]
    mu_epa, lg_plays = R.league_mu_epa(r), r["plays"]["mu"]
    pts_of = lambda p: config.LEAGUE_PTS_PER_TEAM + config.POINTS_PER_EPA * (p["plays"] * p["epa_pp"] - lg_plays * mu_epa)
    inj = ctx["injuries"]
    status = dict(zip(inj.player_id, inj.status))
    out = []
    for _, g in ctx["games"].iterrows():
        h, a = g.home, g.away
        exp_h, note_h = QB.expected_qb_epa(ctx["qb_shr"], ctx["depth"], status, h)
        exp_a, note_a = QB.expected_qb_epa(ctx["qb_shr"], ctx["depth"], status, a)
        ph, pa = R.project_epa(r, h, a, qb_epa=exp_h), R.project_epa(r, a, h, qb_epa=exp_a)
        ph0, pa0 = R.project_epa(r, h, a), R.project_epa(r, a, h)            # same matchup with an average QB
        pts = {h: pts_of(ph), a: pts_of(pa)}
        comp = {"ratings_margin": pts_of(ph0) - pts_of(pa0), "ratings_total": pts_of(ph0) + pts_of(pa0)}
        comp["qb_home"], comp["qb_away"] = pts[h] - pts_of(ph0), pts[a] - pts_of(pa0)
        notes = []
        for t, adj, note in ((h, comp["qb_home"], note_h), (a, comp["qb_away"], note_a)):
            if abs(adj) >= 0.3 and note:
                notes.append(f"{t}: {note} => {adj:+.1f} pts vs an average QB")
        # skill injuries (WR/TE/RB): expected loss = (1 - P(plays)) * usage value
        for t in (h, a):
            f = inj[(inj.team == t) & inj.pos.isin(["WR", "TE", "RB"]) & (inj.status != "healthy")]
            loss, names = 0.0, []
            for _, p in f.iterrows():
                u = ctx["usage"].loc[p.player_id] if p.player_id in ctx["usage"].index else None
                if u is None:
                    continue
                val = config.SKILL_PTS_PER_TARGET_SHARE * u.tgt + config.SKILL_PTS_PER_RUSH_SHARE * u.rsh
                l = (1 - config.PLAY_PROB[p.status]) * val
                if l >= 0.15:
                    names.append(f"{p['name']} ({p.status}) -{l:.1f}")
                loss += l
            loss = min(loss, config.INJURY_CAP_PER_TEAM)
            pts[t] -= loss; comp[f"inj_{'home' if t == h else 'away'}"] = -loss
            if names:
                notes.append(f"{t} skill injuries: " + "; ".join(names))
        # offensive line / defence / special teams absences (snap-share weighted, calibrated by inj_backtest.py)
        gl = {t: INJ.group_losses(inj, t, ctx["snap_shares"]) for t in (h, a)}
        for t, o in ((h, a), (a, h)):
            pts[t] -= gl[t]["off"]
            pts[o] += gl[t]["def"]
            comp[f"inj_ol_{'home' if t == h else 'away'}"] = -gl[t]["off"]
            comp[f"inj_def_{'home' if t == h else 'away'}"] = -gl[t]["def"]          # points the OPPONENT gains because this team's defence is thin
            if gl[t]["notes"]:
                notes.append(f"{t} line/defence/ST: " + "; ".join(gl[t]["notes"]))
        comp["inj_net_home"] = -gl[h]["off"] + gl[a]["def"]          # net effect of line / defence absences on the HOME team's own points
        comp["inj_net_away"] = -gl[a]["off"] + gl[h]["def"]
        margin = pts[h] - pts[a] + (config.HFA_NEUTRAL if g.location == "Neutral" else config.HFA)
        total = pts[h] + pts[a]
        # rest / travel
        rest = _rest(g.rest_home) - _rest(g.rest_away)
        trav = config.TRAVEL_TZ_PENALTY if abs(TZ[a] - TZ[h]) >= 2 else 0.0
        margin += rest - trav            # trav is a (negative) penalty on the AWAY team, so it helps the home margin
        comp["rest"], comp["travel"] = rest, -trav
        # weather (totals)
        wa, wnote = _weather_adj(ctx["weather"].get(g.game_id))
        total += wa; comp["weather"] = wa
        if wnote:
            notes.append("weather: " + wnote)
        # public money + line movement, jointly capped
        sp = ctx["splits"].get((g.game_id, "spread"), {}); to = ctx["splits"].get((g.game_id, "total"), {})
        s_pub = capped_adjustment(sp["home"]["money_pct"] - sp["home"]["tickets_pct"], config.PUBLIC_CAP_SPREAD) if "home" in sp else 0.0
        t_pub = capped_adjustment(to["over"]["money_pct"] - to["over"]["tickets_pct"], config.PUBLIC_CAP_TOTAL) if "over" in to else 0.0
        mv = ctx["moves"].get(g.game_id, {})
        s_mv = (-float(np.clip(mv["spread"]["moved"] / 3, -1, 1)) * config.LINE_MOVE_CAP_SPREAD) if mv.get("spread") and mv["spread"]["moved"] is not None else 0.0
        t_mv = (float(np.clip(mv["total"]["moved"] / 3, -1, 1)) * config.LINE_MOVE_CAP_TOTAL) if mv.get("total") and mv["total"]["moved"] is not None else 0.0
        s_sig = float(np.clip(s_pub + s_mv, -config.PUBLIC_CAP_SPREAD, config.PUBLIC_CAP_SPREAD))
        t_sig = float(np.clip(t_pub + t_mv, -config.PUBLIC_CAP_TOTAL, config.PUBLIC_CAP_TOTAL))
        comp["signal_spread"], comp["signal_total"] = s_sig, t_sig
        margin += s_sig; total += t_sig
        out.append({"game_id": g.game_id, "home": h, "away": a, "kickoff_utc": g.kickoff_utc, "margin": margin, "total": total,
                    "pts_home": (total + margin) / 2, "pts_away": (total - margin) / 2, "comp": comp, "notes": notes,
                    "eff_n": dist.effective_sample(margin)})
    return out


def _ref_line(w: pd.DataFrame):
    """Reference market line: FanDuel's, else the most common line."""
    f = w[w.book == config.REFERENCE_BOOK].line.dropna()
    d = f if len(f) else w.line.dropna()
    return None if d.empty else float(d.iloc[0] if len(f) else d.mode().iloc[0])


def _options(w: pd.DataFrame, market: str, proj: dict, wmodel: float):
    """All (book, line, side) options for one market with model prob, market prob, blended prob and EV."""
    opts = []
    if w.empty:
        return opts
    ref = proj["ref"]
    # OUR margin/total as used for probabilities: the projection shrunk toward the market by the backtested trust factor
    mu_m = (-ref["spread"] + config.MODEL_TRUST["margin"] * (proj["margin"] + ref["spread"])) if ref.get("spread") is not None else proj["margin"]
    mu_t = (ref["total"] + config.MODEL_TRUST["total"] * (proj["total"] - ref["total"])) if ref.get("total") is not None else proj["total"]
    proj = {**proj, "margin_eff": mu_m, "total_eff": mu_t}
    cons = {None if pd.isna(c["line"]) else float(c["line"]): c for c in ov.all_lines(w)}
    for _, r in w.iterrows():
        ln = None if pd.isna(r.line) else float(r.line)
        c = cons.get(ln)
        if c is None:
            continue
        if market == "spread":
            wa, pu, la = dist.home_spread_probs(proj["margin_eff"], ln); sides = ("home", "away")
        elif market == "moneyline":
            wa, pu, la = dist.home_moneyline_probs(proj["margin_eff"]); sides = ("home", "away")
        else:
            wa, pu, la = dist.over_probs(proj["total_eff"], ln); sides = ("over", "under")
        for side, price, pm_w, pm_l, pmk in ((sides[0], r.price_a, wa, la, c["p_a"]), (sides[1], r.price_b, la, wa, 1 - c["p_a"])):
            if pd.isna(price):
                continue
            decisive = pm_w + pm_l
            p_model_c = pm_w / decisive if decisive else 0.5
            p_c = blend(p_model_c, pmk, wmodel)
            p_win, p_loss = p_c * (1 - pu), (1 - p_c) * (1 - pu)
            e = ev(p_win, price, p_push=pu)
            opts.append({"market": market, "side": side, "book": r.book, "line": ln, "price": int(price), "p_model": p_model_c,
                         "p_market": pmk, "p_final": p_c, "p_push": pu, "ev": e, "label": label(e), "n_books": c["n_books"]})
    return opts


def evaluate(ctx: dict, projections: list[dict]) -> list[dict]:
    w_all = ov.wide(ctx["odds_latest"])
    res = []
    for p in projections:
        ev_id = ctx["event_ids"].get(p["game_id"])
        row = dict(p)
        evw = w_all[w_all.event_id == ev_id]
        row["ref"] = {"spread": _ref_line(evw[evw.market == "spread"]), "total": _ref_line(evw[evw.market == "total"])}
        p = {**p, "ref": row["ref"]}
        row["markets"] = {}
        for m in config.GAME_MARKETS:
            w = w_all[(w_all.event_id == ev_id) & (w_all.market == m)]
            o = _options(w, m, p, config.MODEL_WEIGHT[m])
            o.sort(key=lambda x: x["ev"], reverse=True)
            fd = [x for x in o if x["book"] == config.REFERENCE_BOOK]
            row["markets"][m] = {"best": o[0] if o else None, "options": o, "fanduel": fd}
        res.append(row)
    return res
