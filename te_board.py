"""Tight-end touchdown targets: which tight ends are most likely to score on the next game day, against the worst defences for tight ends.

Two ingredients (2026 games only):
  * the anytime-TD model's win probability for the tight end (usage, red-zone and goal-line touches, scoring environment, availability);
  * how bad the opposing defence is for tight ends: TE touchdowns allowed per game, TE red-zone targets allowed per game, TE yards allowed,
    overall pass defence (EPA per dropback allowed) and red-zone touchdown rate allowed. Each is ranked 1 (worst defence) to 32.
TE score (0-100) = 60% percentile of the TD probability among that day's tight ends + 40% the defence's average rank.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

import config
import deep_dive as DD
from adapters import nflverse as nv

W_PROB, W_DEF = 0.6, 0.4


def _et(iso):
    t = datetime.strptime(iso[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    return t.astimezone(ZoneInfo("America/New_York"))


def defences_vs_te(con) -> pd.DataFrame:
    """One row per defence: TE touchdowns / red-zone targets / targets / yards allowed per game, plus pass-D and red-zone-D ranks. Rank 1 = worst for the defence."""
    p = DD._pbp(config.SEASON)
    st = nv.get("stats", config.SEASON)
    pos = st.drop_duplicates("player_id").set_index("player_id").position
    p = p[(p.pass_attempt == 1) & p.receiver_player_id.notna() & (p.sack != 1)].copy()
    p["pos"] = p.receiver_player_id.map(pos)
    p["de"] = nv.norm_team(p.defteam)
    games = DD._pbp(config.SEASON).assign(de=lambda x: nv.norm_team(x.defteam)).groupby("de").game_id.nunique()
    te = p[p.pos == "TE"]
    g = pd.DataFrame({"games": games})
    g["te_td"] = te.groupby("de").pass_touchdown.sum().reindex(g.index).fillna(0) / g.games
    g["te_rz_tgt"] = te[te.yardline_100 <= 20].groupby("de").size().reindex(g.index).fillna(0) / g.games
    g["te_tgt"] = te.groupby("de").size().reindex(g.index).fillna(0) / g.games
    g["te_yds"] = te.groupby("de").yards_gained.sum().reindex(g.index).fillna(0) / g.games
    dv = DD.ranked(config.SEASON, "def", con)["vals"]
    g["epa_pass"] = dv.epa_pass.reindex(g.index)
    g["rz_td"] = dv.rz_td.reindex(g.index) if "rz_td" in dv else float("nan")
    for c in ("te_td", "te_rz_tgt", "te_tgt", "te_yds", "epa_pass", "rz_td"):
        g["r_" + c] = g[c].rank(ascending=False, method="min")          # 1 = allows the most
    g["def_rank"] = g[["r_te_td", "r_te_rz_tgt", "r_te_yds", "r_epa_pass", "r_rz_td"]].mean(axis=1)      # average rank, lower = worse defence for TEs
    g["def_pct"] = 1 - (g.def_rank.rank(method="average") - 1) / max(len(g) - 1, 1)                         # 1.0 = the worst defence vs TEs
    return g


def _tone(r, n=32):
    return "one of the most generous" if r <= 6 else "generous" if r <= 11 else "about average" if r <= 21 else "stingy" if r <= 27 else "one of the stingiest"


def build(tds, deeps, games, con, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    upcoming = [g for g in games if datetime.strptime(g["kickoff"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc) > now]
    if not upcoming:
        return {"day": None, "top": [], "rows": [], "defences": []}
    day = min(_et(g["kickoff"]) for g in upcoming).date()
    gids = {g["id"] for g in upcoming if _et(g["kickoff"]).date() == day}
    dfn = defences_vs_te(con)
    wk = nv.get("stats", config.SEASON)
    wk = wk[(wk.season_type == "REG") & (wk.position == "TE")]
    me = wk.groupby("player_id").agg(g=("week", "nunique"), tgt=("targets", "sum"), rec=("receptions", "sum"), tdg=("receiving_tds", lambda x: int((x > 0).sum())), tds=("receiving_tds", "sum"))
    rows = []
    for t in tds:
        if t["pos"] != "TE" or t["game_id"] not in gids or t["status"] in ("out", "doubtful") or t["limited"]:
            continue
        o = dfn.loc[t["opp"]] if t["opp"] in dfn.index else None
        if o is None:
            continue
        rows.append({"game_id": t["game_id"], "player": t["player"], "team": t["team"], "opp": t["opp"], "home": t["home"], "status": t["status"], "book": t["best_book"],
                     "price": t["best_price"], "p_model": t["p_model"], "p_market": t["p_market"], "p_final": t["p_final"], "tgt_pg": t["tgt_pg"], "rz_pg": t["rz_pg"], "gl_pg": t["gl_pg"],
                     "tgt_share": t["tgt_share"], "td_games": int(me.tdg.get(t["player_id"], 0)), "games": int(me.g.get(t["player_id"], 0)),
                     "tgt26": round(float(me.tgt.get(t["player_id"], 0)) / max(int(me.g.get(t["player_id"], 0)), 1), 1), "tds26": int(me.tds.get(t["player_id"], 0)), "snap_pct": t["snap_pct"], "env_pts": t["env_pts"],
                     "d": {"te_td": round(o.te_td, 2), "r_te_td": int(o.r_te_td), "te_rz": round(o.te_rz_tgt, 2), "r_te_rz": int(o.r_te_rz_tgt), "te_yds": round(o.te_yds, 1),
                           "r_te_yds": int(o.r_te_yds), "epa": round(o.epa_pass, 3), "r_epa": int(o.r_epa_pass), "rz_td": None if pd.isna(o.rz_td) else round(float(o.rz_td) * 100, 1),
                           "r_rz": None if pd.isna(o.r_rz_td) else int(o.r_rz_td), "gp": int(o.games), "def_rank": round(float(o.def_rank), 1), "def_pct": round(float(o.def_pct), 3)}})
    if rows:
        pp = pd.Series([r["p_final"] for r in rows])
        pct = pp.rank(pct=True)
        for r, q in zip(rows, pct):
            r["score"] = round(100 * (W_PROB * q + W_DEF * r["d"]["def_pct"]), 1)
    rows.sort(key=lambda r: -r["score"])
    top, teams = [], set()
    for r in rows:                      # best three, one tight end per team
        if r["team"] not in teams and len(top) < 3:
            top.append(r)
            teams.add(r["team"])
    for r in top:
        d, why, risk = r["d"], [], []
        why.append(f"{r['opp']} has allowed {d['te_td']:g} touchdowns per game to tight ends (#{d['r_te_td']} of 32, {_tone(d['r_te_td'])}) over {d['gp']} games.")
        why.append(f"They give up {d['te_rz']:g} red-zone targets per game to tight ends (#{d['r_te_rz']}) and {d['te_yds']:g} tight-end yards per game (#{d['r_te_yds']}).")
        why.append(f"Pass defence is #{d['r_epa']} worst by EPA allowed per dropback" + (f", and #{d['r_rz']} worst in the red zone ({d['rz_td']}% of trips end in a touchdown)." if d["r_rz"] else "."))
        why.append(f"This season {r['player']} has {r['tgt26']:g} targets a game and has scored in {r['td_games']} of {r['games']} games ({r['tds26']} TD{'s' if r['tds26'] != 1 else ''}); his recent-weighted usage is {r['rz_pg']:g} red-zone and {r['gl_pg']:g} goal-line touches per game.")
        why.append(f"Our model gives him {r['p_model'] * 100:.0f}% to score (market {r['p_market'] * 100:.0f}%); his team is projected for about {r['env_pts']:.0f} points.")
        if r["status"] == "questionable":
            risk.append("Listed questionable (we treat that as 75% to play); check Sunday's inactives.")
        if r["p_market"] < r["p_model"] - 0.07:
            risk.append(f"The market is much lower on him ({r['p_market'] * 100:.0f}%), so he may have a role the model overrates.")
        if r["games"] < 4:
            risk.append(f"Only {r['games']} games of 2026 data.")
        risk.append("An anytime TD is a long shot even for the best matchup: about 3 in 10 to 4 in 10 even at the top.")
        r["why"], r["risk"] = why, risk
    gname = {g["id"]: f"{g['away']} @ {g['home']}" for g in games}
    dnames = [{"team": t, **{k: (None if pd.isna(v) else float(v)) for k, v in dfn.loc[t].items() if k in ("te_td", "te_rz_tgt", "te_yds", "epa_pass", "r_te_td", "r_te_rz_tgt", "r_te_yds", "r_epa_pass", "def_rank")}}
              for t in dfn.sort_values("def_rank").index if t in {r["opp"] for r in rows}]
    return {"day": day.isoformat(), "top": top, "rows": rows, "defences": dnames, "games": {g: gname[g] for g in gids}}
