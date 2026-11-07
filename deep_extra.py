"""Deep-dive helpers: weather history, kicking/altitude, distances, preview prop + anytime-TD model."""
import json
import math

import numpy as np
import pandas as pd
from scipy.stats import norm, poisson

import config
from adapters import nflverse as nv
from model import odds_view as ov
from model.devig import blend, ev as ev_fn, label, to_prob

C = config.CACHE / "nflverse"
WIND_BUCKETS = [(0, 5, "0-4 mph"), (5, 10, "5-9 mph"), (10, 15, "10-14 mph"), (15, 20, "15-19 mph"), (20, 99, "20+ mph")]
TEMP_BUCKETS = [(-50, 32, "under 32F"), (32, 45, "32-44F"), (45, 60, "45-59F"), (60, 75, "60-74F"), (75, 130, "75F+")]
STAT_COL = {"pass_yds": "passing_yards", "rush_yds": "rushing_yards", "rec_yds": "receiving_yards", "receptions": "receptions", "rush_att": "carries",
            "pass_td": "passing_tds", "pass_comp": "completions", "pass_att": "attempts", "pass_int": "passing_interceptions"}
POS_ALLOWED = {"pass_yds": ("QB", "pass_yds"), "pass_td": ("QB", "pass_td"), "pass_int": ("QB", "ints"), "pass_att": ("QB", "att"), "pass_comp": ("QB", "att")}
PROP_LABEL = {"pass_yds": "Pass yds", "rush_yds": "Rush yds", "rec_yds": "Rec yds", "receptions": "Receptions", "rush_att": "Rush att", "pass_td": "Pass TD",
              "pass_comp": "Completions", "pass_att": "Pass att", "pass_int": "Interceptions", "long_pass": "Longest pass", "long_rush": "Longest rush",
              "long_rec": "Longest rec", "pass_rush_yds": "Pass+rush yds", "rush_rec_yds": "Rush+rec yds"}


def weather_history() -> dict:
    """Outdoor games since 2012: total vs closing line by wind and temperature bucket."""
    g = pd.read_csv(C / "games.csv")
    g = g[(g.game_type == "REG") & g.home_score.notna() & (g.season >= 2012) & (g.roof == "outdoors")].copy()
    g["tot"] = g.home_score + g.away_score
    g["d"] = g.tot - g.total_line
    out = {}
    for name, col, bk in (("wind", "wind", WIND_BUCKETS), ("temp", "temp", TEMP_BUCKETS)):
        d = g.dropna(subset=[col])
        rows = []
        for lo, hi, lab in bk:
            x = d[(d[col] >= lo) & (d[col] < hi)]
            if len(x):
                dec = x[x.tot != x.total_line]
                rows.append({"bucket": lab, "n": len(x), "avg_diff": round(float(x.d.mean()), 2), "over_pct": round(float((dec.tot > dec.total_line).mean()), 3),
                             "avg_total": round(float(x.tot.mean()), 1)})
        out[name] = rows
    return out


def kicking_block(home: str, pbp_fn) -> dict:
    """Field goals / punts / kickoffs at the home stadium vs elsewhere (2025 + 2026): the altitude question."""
    rows = []
    for s in (config.LAST_SEASON, config.SEASON):
        p = pbp_fn(s)
        p["home_team"] = nv.norm_team(p.home_team)
        rows.append(p)
    p = pd.concat(rows)
    fg = p[(p.play_type == "field_goal") & p.kick_distance.notna()].copy()
    fg["made"] = (fg.field_goal_result == "made").astype(int)
    fg["at"] = fg.home_team == home
    fg["band"] = pd.cut(fg.kick_distance, [0, 39, 49, 100], labels=["under 40", "40-49", "50+"])
    t = fg.groupby(["at", "band"], observed=True).agg(n=("made", "size"), pct=("made", "mean")).reset_index()
    pu = p[(p.play_type == "punt") & p.kick_distance.notna()].copy()
    pu["at"] = pu.home_team == home
    pg = pu.groupby("at").kick_distance.mean()
    kk = p[(p.play_type == "kickoff") & p.touchback.notna()].copy()
    kk["at"] = kk.home_team == home
    kb = kk.groupby("at").touchback.mean()
    sc = p.groupby(["game_id", "home_team"]).agg(h=("total_home_score", "max"), a=("total_away_score", "max")).reset_index()
    sc["tot"] = sc.h + sc.a
    sc["at"] = sc.home_team == home
    f = lambda v: None if pd.isna(v) else round(float(v), 3)
    return {"fg": [{"at_home_stadium": bool(r.at), "band": str(r.band), "n": int(r.n), "pct": round(float(r.pct), 3)} for r in t.itertuples()],
            "punt_gross": {"at": f(pg.get(True, np.nan)), "elsewhere": f(pg.get(False, np.nan))},
            "touchback_rate": {"at": f(kb.get(True, np.nan)), "elsewhere": f(kb.get(False, np.nan))},
            "avg_total_at": f(sc[sc["at"]].tot.mean()), "avg_total_elsewhere": f(sc[~sc["at"]].tot.mean()), "games_at": int(sc["at"].sum())}


def haversine(a, b) -> float:
    r = 3958.8
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _series(logs: pd.DataFrame, pid: str, market: str):
    x = logs[logs.player_id == pid].sort_values(["season", "week"])
    if market == "rush_rec_yds":
        v = x.rushing_yards.fillna(0) + x.receiving_yards.fillna(0)
    elif market == "pass_rush_yds":
        v = x.passing_yards.fillna(0) + x.rushing_yards.fillna(0)
    elif market in STAT_COL:
        v = x[STAT_COL[market]].fillna(0)
    else:
        return None
    return pd.DataFrame({"season": x.season.values, "week": x.week.values, "v": v.values, "opp": x.opponent_team.values})


def props_block(game, odds_w, con, pos_a26, pos_a25, wind_eff: float, team_pts: dict) -> dict:
    """PREVIEW prop and anytime-TD model for the two teams: recent form x opponent defence vs position x wind, blended with the
    market at the configured weight. Not the final step-7 model (no negative binomial, no teammate-injury redistribution yet)."""
    away, home = game.away, game.home
    players = pd.read_sql("select player_id, name, team, pos from players", con).set_index("player_id")
    logs = pd.concat([nv.get("stats", s).assign(season=s) for s in (config.LAST_SEASON, config.SEASON)])
    logs = logs[logs.season_type == "REG"].copy()
    logs["team"], logs["opponent_team"] = nv.norm_team(logs.team), nv.norm_team(logs.opponent_team)
    w = odds_w[(odds_w.event_id == game.sgo_event_id) & ~odds_w.market.isin(["spread", "moneyline", "total", "td_any"])]
    out = []
    for (pid, market), grp in w.groupby(["player_id", "market"]):
        if pid.startswith("sgo:") or pid not in players.index:
            continue
        pl = players.loc[pid]
        lg = logs[logs.player_id == pid]
        team = pl.team if pl.team in (away, home) else (lg.sort_values(["season", "week"]).team.iloc[-1] if len(lg) else None)
        if team not in (away, home):
            continue
        opp = home if team == away else away
        cons = ov.all_lines(grp)
        if not cons:
            continue
        ref = ov.consensus(grp)
        entry = {"player": pl["name"], "team": team, "pos": pl.pos, "market": market, "label": PROP_LABEL.get(market, market), "books": []}
        for r in grp.sort_values("book").itertuples():
            entry["books"].append({"book": r.book, "line": None if pd.isna(r.line) else float(r.line), "over": None if pd.isna(r.price_a) else int(r.price_a),
                                   "under": None if pd.isna(r.price_b) else int(r.price_b)})
        s = _series(logs, pid, market)
        proj = sd = None
        if s is not None and len(s):
            s26, s25 = s[s.season == config.SEASON], s[s.season == config.LAST_SEASON]
            avg26 = s26.v.mean() if len(s26) else np.nan
            avg25 = s25.v.mean() if len(s25) else np.nan
            last3 = s26.v.tail(3).mean() if len(s26) else np.nan
            prior = avg25 if not np.isnan(avg25) else avg26
            n26 = len(s26)
            base = (n26 * avg26 + 6 * prior) / (n26 + 6) if (n26 and not np.isnan(prior)) else prior
            if base is not None and not np.isnan(base):
                pg = pl.pos if pl.pos in ("QB", "RB", "WR", "TE") else "WR"
                if market in ("pass_yds", "pass_td", "pass_int", "pass_att", "pass_comp", "pass_rush_yds"):
                    p_, col = "QB", {"pass_yds": "pass_yds", "pass_td": "pass_td", "pass_int": "ints", "pass_att": "att", "pass_comp": "att", "pass_rush_yds": "pass_yds"}[market]
                elif market in ("rush_yds", "rush_att"):
                    p_, col = ("QB" if pg == "QB" else "RB"), {"rush_yds": "rush_yds", "rush_att": "car"}[market]
                elif market in ("rec_yds", "receptions", "rush_rec_yds"):
                    p_, col = (pg if pg in ("WR", "TE", "RB") else "WR"), {"rec_yds": "rec_yds", "receptions": "rec", "rush_rec_yds": "rec_yds"}[market]
                else:
                    p_, col = pg, None
                f = 1.0
                if col and (p_, col) in pos_a26.columns:
                    x26, x25 = pos_a26[(p_, col)], pos_a25[(p_, col)]
                    mine = x26.get(opp, np.nan)
                    lgv = x26.mean()
                    if lgv and not np.isnan(mine):
                        f = 1 + 0.5 * (mine / lgv - 1)
                wf = 1.0
                if market in ("pass_yds", "rec_yds", "pass_comp", "pass_att", "receptions", "pass_rush_yds", "rush_rec_yds") and wind_eff > 12:
                    wf = 1 - min(0.12, 0.01 * (wind_eff - 12))
                proj = float(base * f * wf)
                allv = s.v.tail(14)
                floor = 0.3 * proj if "yds" in market else 0.4 * math.sqrt(max(proj, 0.5)) + 0.6
                sd = float(max(allv.std(ddof=1) if len(allv) > 3 else 0.35 * proj, floor))
                entry.update({"avg26": None if np.isnan(avg26) else round(float(avg26), 1), "last3": None if np.isnan(last3) else round(float(last3), 1),
                              "avg25": None if np.isnan(avg25) else round(float(avg25), 1), "n26": int(n26), "opp_factor": round(f, 3), "wind_factor": round(wf, 3),
                              "proj": round(proj, 1), "sd": round(sd, 1), "series": [round(float(v), 1) for v in s.v.tail(8)]})
        opts = []
        if proj is not None:
            by_line = {None if pd.isna(c["line"]) else float(c["line"]): c for c in cons}
            for r in grp.itertuples():
                ln = None if pd.isna(r.line) else float(r.line)
                c = by_line.get(ln)
                if c is None or ln is None:
                    continue
                po_model = float(1 - poisson.cdf(math.floor(ln), proj)) if market in ("pass_td", "pass_int") else float(1 - norm.cdf((ln - proj) / sd))
                sv = s.v.tail(14)
                emp = (float((sv > ln).sum()) + 0.5) / (len(sv) + 1)              # Laplace-smoothed hit rate over his last 14 games
                po = (len(sv) * emp + 6 * po_model) / (len(sv) + 6)               # normal/Poisson model for thin samples, his own history as it grows
                po = c["p_a"] + config.PROP_TRUST * (po - c["p_a"])               # preview model is unvalidated: only a fraction is trusted
                for side, price, pm, pk in (("over", r.price_a, po, c["p_a"]), ("under", r.price_b, 1 - po, 1 - c["p_a"])):
                    if pd.isna(price):
                        continue
                    pf = blend(pm, pk, config.MODEL_WEIGHT["prop"])
                    e = ev_fn(pf, price)
                    opts.append({"side": side, "book": r.book, "line": ln, "price": int(price), "p_model": round(pm, 4), "p_market": round(pk, 4),
                                 "p_final": round(pf, 4), "ev": round(e, 4), "label": label(e)})
            opts.sort(key=lambda o: -o["ev"])
        entry["options"] = opts
        entry["best"] = opts[0] if opts else None
        if ref:
            entry["ref"] = {"line": ref["line"], "p_over_market": round(ref["p_a"], 4), "n_books": ref["n_books"]}
            if s is not None and len(s) and ref["line"] is not None:
                sv = s.v.tail(12)
                entry["hit_over_last12"] = round(float((sv > ref["line"]).mean()), 2)
                entry["hit_n"] = int(len(sv))
        out.append(entry)
    # anytime TD
    tds = []
    td = odds_w[(odds_w.event_id == game.sgo_event_id) & (odds_w.market == "td_any")]
    pw = pd.read_sql("select season, week, player_id, stats_json from player_week where season>=?", con, params=(config.LAST_SEASON,))
    js = pw.stats_json.map(json.loads)
    pw["td"] = js.map(lambda d: (d.get("rushing_tds") or 0) + (d.get("receiving_tds") or 0))
    pw["rz"] = js.map(lambda d: (d.get("rz_targets") or 0) + (d.get("rz_carries") or 0))
    pw["gl"] = js.map(lambda d: (d.get("gl_carries") or 0) + (d.get("gl_targets") or 0))
    prior_pos = {"RB": 0.30, "WR": 0.22, "TE": 0.20, "QB": 0.10}
    sn = nv.get("snaps", config.SEASON)
    sn = sn[(sn.game_type == "REG") & (sn.position != "QB")].sort_values("week")
    snaps = sn.groupby("player").offense_pct.apply(lambda v: float(v.tail(5).mean()) * 100).to_dict()
    for pid, grp in td.groupby("player_id"):
        if pid.startswith("sgo:") or pid not in players.index:
            continue
        pl = players.loc[pid]
        if pl.team not in (away, home):
            continue
        x = pw[pw.player_id == pid]
        n, gwt = len(x), int((x.td > 0).sum())
        recent = x.sort_values(["season", "week"]).tail(6)
        sp = snaps.get(pl["name"])
        role = 0.25 if sp is None else min(1.0, (sp / 60.0) ** 1.5)                  # depth players do not get a starter's prior
        p_hist = (gwt + 8 * prior_pos.get(pl.pos, 0.08) * role) / (n + 8)
        p_model = min(0.9, p_hist * (team_pts.get(pl.team, 22.5) / 22.5) ** 0.8)
        grp = grp.dropna(subset=["price_a"])
        if grp.empty:
            continue
        best = grp.loc[grp.price_a.idxmax()]
        cons_p = float(np.mean([to_prob(v) / (1 + config.TD_ASSUMED_HOLD) for v in grp.price_a]))
        p_model = cons_p + config.PROP_TRUST * (p_model - cons_p)
        pf = blend(p_model, cons_p, config.MODEL_WEIGHT["td"])
        e = ev_fn(pf, best.price_a)
        tds.append({"player": pl["name"], "team": pl.team, "pos": pl.pos, "best_book": best.book, "best_price": int(best.price_a),
                    "prices": {r.book: int(r.price_a) for r in grp.itertuples()}, "p_market": round(cons_p, 4), "p_model": round(p_model, 4),
                    "p_final": round(pf, 4), "ev": round(e, 4), "label": label(e), "games": int(n), "games_with_td": gwt,
                    "td_rate": round(gwt / n, 3) if n else None, "rz_pg_recent": round(float(recent.rz.mean()), 2) if len(recent) else None,
                    "gl_pg_recent": round(float(recent.gl.mean()), 2) if len(recent) else None, "team_pts": round(team_pts.get(pl.team, 22.5), 1)})
    tds.sort(key=lambda r: -r["ev"])
    out.sort(key=lambda r: -(r["best"]["ev"] if r["best"] else -9))
    return {"props": out, "td": tds, "wind_used": round(wind_eff, 1)}
