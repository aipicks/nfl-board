"""Deep-dive extras: quarterback lines, skill usage, plays/pace projection, data-driven game-dynamics bullets."""
import numpy as np
import pandas as pd

import config
from adapters import nflverse as nv
from model import ratings as R


def qb_block(teams, pbp_fn):
    rows = []
    for s in (config.SEASON, config.LAST_SEASON):
        p = pbp_fn(s)
        p["team"] = nv.norm_team(p.posteam)
        q = p[(p.qb_dropback == 1) & p.epa.notna() & p.team.isin(teams)]
        g = q.groupby(["team", "passer_player_name"])
        att = p[(p.pass_attempt == 1) & p.team.isin(teams)].groupby(["team", "passer_player_name"])
        d = pd.DataFrame({"dropbacks": g.size(), "epa_db": g.epa.mean(), "sack_rate": g.sack.mean(), "scrambles": g.qb_scramble.sum(),
                          "ints": att.interception.sum(), "td": att.pass_touchdown.sum(), "att": att.size(), "comp": att.complete_pass.sum(),
                          "ypa": att.yards_gained.mean(), "cpoe": att.cpoe.mean(), "adot": att.air_yards.mean(), "qb_hits": g.qb_hit.sum(),
                          "games": g.game_id.nunique()}).reset_index()
        d["season"] = s
        rows.append(d[d.dropbacks >= 10])
    d = pd.concat(rows).sort_values(["team", "season", "dropbacks"], ascending=[True, False, False])
    return d.rename(columns={"passer_player_name": "name"}).to_dict("records")


def usage_block(teams, con):
    """Per skill player this season: targets, receptions, yards, TDs, carries, rush yds, red-zone and goal-line touches, snap%."""
    st = nv.get("stats", config.SEASON)
    st = st[st.season_type == "REG"].copy()
    st["team"] = nv.norm_team(st.team)
    pw = pd.read_sql("select player_id, stats_json from player_week where season=?", con, params=(config.SEASON,))
    import json
    js = pw.stats_json.map(json.loads)
    pw["rz_t"] = js.map(lambda d: d.get("rz_targets") or 0); pw["rz_c"] = js.map(lambda d: d.get("rz_carries") or 0)
    pw["gl_t"] = js.map(lambda d: d.get("gl_targets") or 0); pw["gl_c"] = js.map(lambda d: d.get("gl_carries") or 0)
    z = pw.groupby("player_id")[["rz_t", "rz_c", "gl_t", "gl_c"]].sum()
    sn = nv.get("snaps", config.SEASON)
    sn = sn[sn.game_type == "REG"]
    snap = sn.groupby("player").offense_pct.mean() * 100
    out = []
    for t in teams:
        x = st[(st.team == t) & st.position.isin(["QB", "RB", "WR", "TE"])]
        tt = x.targets.sum()
        tc = x.carries.sum()
        a = x.groupby(["player_id", "player_display_name", "position"]).agg(g=("week", "nunique"), tgt=("targets", "sum"), rec=("receptions", "sum"), ryd=("receiving_yards", "sum"),
                                                                           rtd=("receiving_tds", "sum"), car=("carries", "sum"), rsh=("rushing_yards", "sum"), rutd=("rushing_tds", "sum"),
                                                                           air=("receiving_air_yards", "sum"), yac=("receiving_yards_after_catch", "sum")).reset_index()
        a["opp"] = a.tgt + a.car
        for r in a[a.position != "QB"].sort_values("opp", ascending=False).head(10).itertuples():
            zz = z.loc[r.player_id] if r.player_id in z.index else None
            out.append({"team": t, "name": r.player_display_name, "pos": r.position, "g": int(r.g), "tgt": int(r.tgt), "tgt_share": round(r.tgt / tt, 3) if tt else None,
                        "rec": int(r.rec), "rec_yds": int(r.ryd), "rec_td": int(r.rtd), "ypt": round(r.ryd / r.tgt, 2) if r.tgt else None,
                        "adot": round(r.air / r.tgt, 1) if r.tgt else None, "car": int(r.car), "car_share": round(r.car / tc, 3) if tc else None, "rush_yds": int(r.rsh),
                        "ypc": round(r.rsh / r.car, 2) if r.car else None, "rush_td": int(r.rutd), "rz": None if zz is None else int(zz.rz_t + zz.rz_c),
                        "gl": None if zz is None else int(zz.gl_t + zz.gl_c), "snap": None if r.player_display_name not in snap.index else round(float(snap[r.player_display_name]))})
    return out


def dynamics(d: dict) -> list[dict]:
    """Rule-based, data-driven bullets. tag: g (favours over / helps), r (hurts), y (neutral/mixed)."""
    out = []
    a, h = d["away"], d["home"]
    w = d["weather"]
    ko = w["hours"][w["kickoff_hour_index"]]
    pr = d["projection"]
    day = d["history"]["day"]
    ra, rh = d["rest"]["away"], d["rest"]["home"]
    rest_txt = (f"{a} {ra:.0f} days' rest, {h} {rh:.0f}" if ra == ra and rh == rh else "rest days unavailable")
    flag = "short week for both" if (ra <= 5 and rh <= 5) else ("rest edge to " + (h if rh > ra else a) if abs(ra - rh) >= 3 else "normal rest")
    out.append({"tag": "y", "text": f"{day['label']} game ({rest_txt}; {flag}). {day['label']} games since 2015 average {day['avg_total']} points vs a {day['avg_line']} line "
                                    f"(over {day['over_pct']:.0%}); home teams win {day['home_win_pct']:.0%}."})
    if d.get("altitude_ft", {}).get(h, 0) > 4000:
        out.append({"tag": "y", "text": f"Altitude {d['altitude_ft'][h]:,} ft: air density is {abs(w['density_vs_sea_level_pct']):.0f}% below sea level tonight, so kicks and punts carry farther and the ball cuts through the air with less drag. "
                                        f"{a} travels {d['travel_miles']:,} miles into it on a short week."})
    if d.get("indoor"):
        out.append({"tag": "g", "text": "Indoors (dome or closed roof): wind, rain and temperature do not affect this game."})
    elif ko["windgusts_10m"] >= 25 or ko["windspeed_10m"] >= 15:
        out.append({"tag": "r", "text": f"Wind {ko['windspeed_10m']:.0f} mph, gusts {ko['windgusts_10m']:.0f} mph ({ko['wind_dir']}) at kickoff: hurts deep passing and long field goals."})
    elif True:
        out.append({"tag": "g", "text": f"Calm: wind {ko['windspeed_10m']:.0f} mph, gusts {ko['windgusts_10m']:.0f} mph ({ko['wind_dir']}). No wind penalty on passing or kicking."})
    if d.get("indoor"):
        pass
    elif ko["precipitation_probability"] >= 40 or ko["precipitation"] > 0.02:
        out.append({"tag": "r", "text": f"Precipitation risk {ko['precipitation_probability']:.0f}% ({ko['cond']}): lowers passing efficiency and totals historically."})
    else:
        out.append({"tag": "g", "text": f"Dry: {ko['precipitation_probability']:.0f}% precipitation chance, {ko['cond'].lower()}."})
    if not d.get("indoor") and ko["temperature_2m"] < 40:
        out.append({"tag": "y", "text": f"Cold: {ko['temperature_2m']:.0f}F ({ko['apparent_temperature']:.0f}F feels-like). Small drag on scoring; grip and kicking get harder below 32F."})
    # matchup edges from ranks (rank 1 = best for that unit)
    off = {r["key"]: r for r in d["metrics"]["off"]}
    de = {r["key"]: r for r in d["metrics"]["def"]}
    pairs = [("epa_pass", "pass offence vs pass defence"), ("epa_rush", "run offence vs run defence"), ("sack_rate", "pass protection vs pass rush"), ("rz_td", "red-zone offence vs red-zone defence"),
             ("third", "3rd-down offence vs 3rd-down defence"), ("expl_pass", "explosive passing vs explosive passes allowed")]
    for off_t, def_t in ((a, h), (h, a)):
        for k, lab in pairs:
            ro, rd = off[k][off_t]["r26"], de[k][def_t]["r26"]
            if ro is None or rd is None:
                continue
            ro_c, rd_c = ro, rd                               # 2026 ranks only
            if ro_c <= 11 and rd_c >= 22:
                out.append({"tag": "g", "text": f"Edge for the {off_t} offence: {lab}. {off_t} offence about #{ro_c:.0f} vs {def_t} defence about #{rd_c:.0f} (2026 ranks)."})
            elif ro_c >= 22 and rd_c <= 11:
                out.append({"tag": "r", "text": f"Edge for the {def_t} defence: {lab}. {def_t} defence about #{rd_c:.0f} vs {off_t} offence about #{ro_c:.0f} (2026 ranks)."})
    outs = [i for i in d["injuries"] if i["status"] == "out"]
    for t in (a, h):
        k = [f"{i['name']} ({i['pos']})" for i in outs if i["team"] == t]
        if k:
            out.append({"tag": "r" if t == h else "y", "text": f"{t} out: " + ", ".join(k) + "."})
    out.append({"tag": "y", "text": f"Our projection: {a} {pr['pts_away']:.1f} - {h} {pr['pts_home']:.1f} (margin {h} {pr['margin']:+.1f}, total {pr['total']:.1f}) vs market {h} {-pr['ref']['spread']:+.1f}, total {pr['ref']['total']}."})
    return out


def plays_block(ctx, game):
    r = ctx["ratings"]
    out = {}
    for t, o in ((game.home, game.away), (game.away, game.home)):
        e = R.project_epa(r, t, o)
        out[t] = {"plays": e["plays"], "epa_pass": e["epa_pass"], "epa_rush": e["epa_rush"], "sr": e["sr"]}
    return out
