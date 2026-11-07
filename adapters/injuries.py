"""Injuries. Primary: ESPN public injuries JSON (full league). Official: nflverse injuries (the NFL's own practice/game-status
reports). RotoWire's table endpoint returns only 5 rows to non-subscribers, so it is NOT used (no paywall workarounds).

Status vocabulary: healthy | questionable | doubtful | out   (IR/PUP/suspension -> out)
"""
import json

import pandas as pd

import config
from adapters import nflverse as nv
from adapters.http import fetch
from adapters.names import ESPN_TEAM_FIX, attach_player_ids

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
STATUS_MAP = {"out": "out", "injured reserve": "out", "ir": "out", "doubtful": "doubtful", "questionable": "questionable",
              "active": "healthy", "probable": "healthy"}
ORDER = {"healthy": 0, "questionable": 1, "doubtful": 2, "out": 3}


def map_status(s) -> str | None:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    k = str(s).strip().lower()
    if k in STATUS_MAP:
        return STATUS_MAP[k]
    if any(x in k for x in ("pup", "physically unable", "suspen", "nfi", "non-football", "reserve", "exempt")):
        return "out"
    return "questionable"          # unknown wording: be cautious


def espn(max_age_s=1800) -> pd.DataFrame:
    path, st = fetch(ESPN_URL, config.CACHE / "espn" / "injuries.json", max_age_s=max_age_s)
    j = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for t in j["injuries"]:
        for i in t["injuries"]:
            a = i["athlete"]
            team = (a.get("team") or {}).get("abbreviation") or ""
            rows.append({"name": a["displayName"], "team": ESPN_TEAM_FIX.get(team, team), "pos": (a.get("position") or {}).get("abbreviation"),
                         "injury": ((i.get("details") or {}).get("type") or i.get("type", {}).get("description") or ""),
                         "raw_status": i["status"], "status": map_status(i["status"]), "note": i.get("shortComment", ""),
                         "date": i.get("date")})
    df = pd.DataFrame(rows)
    df.attrs["fetch"] = st
    return df


def official(season: int, week: int) -> pd.DataFrame:
    """NFL official report via nflverse: report_status (final game status) and practice_status (participation)."""
    d = nv.get("injuries", season, max_age_s=3600)
    d = d[d.week == week].copy()
    d["team"] = nv.norm_team(d.team)
    d["status"] = d.report_status.map(map_status)
    d["practice"] = d.practice_status.fillna("")
    return d.rename(columns={"full_name": "name", "position": "pos", "gsis_id": "player_id",
                             "report_primary_injury": "injury"})[["player_id", "name", "team", "pos", "injury", "status", "practice"]]


def current(players: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    """One row per player on either report: merged status, both sources, and a conflict flag.
    Rule: an official game-status designation overrides ESPN, unless ESPN is harsher (same-day downgrade); otherwise ESPN. Practice 'DNP all week' is shown as a flag."""
    e = attach_player_ids(espn(), players)
    o = official(season, week)
    m = e.merge(o[["player_id", "status", "practice"]].rename(columns={"status": "off_status"}), on="player_id", how="outer")
    # official-only rows (no ESPN entry)
    only_o = m[m.name.isna()].drop(columns=["name", "team", "pos", "injury"]).merge(
        o[["player_id", "name", "team", "pos", "injury"]], on="player_id", how="left")
    m = pd.concat([m[m.name.notna()], only_o], ignore_index=True)
    m = m.rename(columns={"status": "espn_status"})
    # ESPN carries same-day downgrades (questionable -> out) before nflverse's report updates, so a harsher ESPN status beats the official one
    harsher = m.espn_status.map(ORDER).fillna(-1) > m.off_status.map(ORDER).fillna(-1)
    m["status"] = m.off_status.where(m.off_status.notna() & ~harsher, m.espn_status).fillna("healthy")
    m["conflict"] = (m.off_status.notna() & m.espn_status.notna() & (m.off_status != m.espn_status))
    m["dnp"] = m.practice.fillna("").str.startswith("Did Not")
    for c in ("date", "raw_status"):
        if c not in m:
            m[c] = None
    return m[["player_id", "name", "team", "pos", "injury", "status", "espn_status", "off_status", "practice", "conflict", "dnp", "note", "date", "raw_status"]]


def store(con, snap_ts: str, df: pd.DataFrame):
    rows = df.dropna(subset=["player_id"]).assign(snap_ts=snap_ts, source="espn+official")
    rows[["snap_ts", "player_id", "name", "team", "pos", "injury", "status", "source"]].to_sql(
        "injuries", con, if_exists="append", index=False)


# roster reserve codes (nflverse status RES): R01 injured reserve, R48 IR designated to return, R04 PUP, R05 non-football injury; anything else is shown as "reserve list"
RES_LABEL = {"R01": "Injured Reserve", "R48": "Injured Reserve", "R04": "PUP list", "R05": "Non-football injury list"}


def long_term(season: int, last_season: int, exclude_ids=()) -> pd.DataFrame:
    """Players on the roster's reserve list (IR / PUP / NFI) who are NOT on the weekly injury report because they were hurt in an earlier week.
    Display only: the team ratings are built from games actually played, so their absence is already in the projection.
    Kept when the player has a real role: played this season before going on IR, or had 20%+ of snaps / 15+ targets or carries last season."""
    r = nv.get("roster", season)
    r = r[(r.status == "RES") & r.gsis_id.notna() & ~r.gsis_id.isin(set(exclude_ids))].copy()
    r["team"] = nv.norm_team(r.team)

    def snaps(s):
        x = nv.get("snaps", s)
        x = x[x.game_type == "REG"]
        a = x.groupby("pfr_player_id").agg(off=("offense_pct", "mean"), de=("defense_pct", "mean"), g=("week", "nunique"))
        return (a[["off", "de"]].fillna(0).max(axis=1)).round(2), a.g

    def usage(s):
        x = nv.get("stats", s)
        x = x[x.season_type == "REG"]
        return x.groupby("player_id").agg(tgt=("targets", "sum"), car=("carries", "sum"), g=("week", "nunique"))

    s26, g26s = snaps(season)
    s25, _ = snaps(last_season)
    u26, u25 = usage(season), usage(last_season)
    last = nv.get("injuries", season)
    last = last.sort_values("week").drop_duplicates("gsis_id", keep="last").set_index("gsis_id")
    rows = []
    for x in r.itertuples():
        g26 = int(g26s.get(x.pfr_id, 0)) if isinstance(x.pfr_id, str) else 0
        sn25 = float(s25.get(x.pfr_id, 0)) if isinstance(x.pfr_id, str) else 0.0
        sn26 = float(s26.get(x.pfr_id, 0)) if isinstance(x.pfr_id, str) else 0.0
        t25 = int(u25.tgt.get(x.gsis_id, 0)) if x.gsis_id in u25.index else 0
        c25 = int(u25.car.get(x.gsis_id, 0)) if x.gsis_id in u25.index else 0
        if not (g26 > 0 or sn25 >= 0.2 or t25 >= 15 or c25 >= 15):
            continue
        t26 = int(u26.tgt.get(x.gsis_id, 0)) if x.gsis_id in u26.index else 0
        c26 = int(u26.car.get(x.gsis_id, 0)) if x.gsis_id in u26.index else 0
        li = last.loc[x.gsis_id] if x.gsis_id in last.index else None
        inj = (li.report_primary_injury if li is not None and isinstance(li.report_primary_injury, str) else "")
        note = (f"Played {g26} game{'s' if g26 != 1 else ''} this season, then went on the reserve list" if g26 else "Has not played this season")
        if li is not None:
            note += f"; last on the weekly report in week {int(li.week)}"
        rows.append({"player_id": x.gsis_id, "name": x.full_name, "team": x.team, "pos": x.position, "injury": inj, "status": "out",
                     "raw_status": RES_LABEL.get(x.status_description_abbr, "Reserve list"), "note": note, "long_term": True, "g26": g26,
                     "snap_pct": round((sn26 if g26 else sn25) * 100), "snap_year": season if g26 else last_season,
                     "tgt": t26 if g26 else t25, "car": c26 if g26 else c25})
    return pd.DataFrame(rows)
