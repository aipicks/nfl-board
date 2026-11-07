"""Injury history for one player: how long he has been out, how much he played before, and how long he has been on the weekly report.
2026 regular season only. Weeks missed are team games (bye weeks do not count) in which the player had no offensive or defensive snaps."""
import functools

import pandas as pd

import config
from adapters import nflverse as nv


@functools.lru_cache(maxsize=None)
def _frames(season):
    sn = nv.get("snaps", season)
    sn = sn[sn.game_type == "REG"].copy()
    sn["snap"] = sn[["offense_pct", "defense_pct"]].fillna(0).max(axis=1)
    sn["played"] = (sn.offense_snaps.fillna(0) + sn.defense_snaps.fillna(0)) > 0
    inj = nv.get("injuries", season)
    inj = inj[inj.game_type == "REG"].sort_values("week")
    ro = nv.get("roster", season).dropna(subset=["gsis_id", "pfr_id"]).drop_duplicates("gsis_id")
    return sn, inj, dict(zip(ro.gsis_id, ro.pfr_id))


def role(snap):
    return None if snap is None else "key starter" if snap >= 70 else "regular starter" if snap >= 50 else "rotation player" if snap >= 25 else "depth / special teams"


def _plural(n, w):
    return f"{n} {w}{'' if n == 1 else 's'}"


def history(con, pid, team, week, name=None, season=None) -> dict | None:
    """Games missed in a row, last game played and snap share before, snap share this season, and the weekly-report timeline."""
    season = season or config.SEASON
    if not isinstance(pid, str):
        return None
    sn, inj, pfr = _frames(season)
    pf = pfr.get(pid)
    tw = [int(r[0]) for r in con.execute("select week from games where season=? and week<? and home_score is not null and (home=? or away=?) order by week", (season, int(week), team, team))]
    mine = sn[sn.pfr_player_id == pf] if pf else sn.iloc[0:0]
    if not len(mine) and name:              # roster file has no pfr id for some players: fall back to name within the team
        mine = sn[(sn.player == name) & (sn.team == team)]
    known = len(mine) > 0                   # no snap rows at all means we cannot tell, not that he never played
    played = mine[mine.played & mine.week.isin(tw)].sort_values("week")
    pw = set(int(w) for w in played.week)
    streak = 0
    for w in reversed(tw):
        if w in pw:
            break
        streak += 1
    missed = len([w for w in tw if w not in pw])
    last_played = int(played.week.max()) if len(played) else None
    snap_avg = round(float(played.snap.mean()) * 100) if len(played) else None
    snap_before = round(float(played.snap.tail(3).mean()) * 100) if len(played) else None
    rep = inj[inj.gsis_id == pid]
    timeline = [{"w": int(r.week), "s": r.report_status if isinstance(r.report_status, str) else "", "i": r.report_primary_injury if isinstance(r.report_primary_injury, str) else ""} for r in rep.itertuples()]
    first_week = timeline[0]["w"] if timeline else None
    parts = []
    if not tw:
        parts.append("Season has only just started.")
    elif not known:
        parts.append("No 2026 snap data found for this player, so games missed are unknown.")
    elif streak:
        span = f"weeks {tw[-streak]}-{tw[-1]}" if streak > 1 else f"week {tw[-1]}"
        parts.append(f"Has missed {_plural(streak, 'straight game')} ({span}).")
        if last_played is not None:
            parts.append(f"Last played in week {last_played}, when he was on the field for {snap_before}% of snaps (last 3 games he played).")
        else:
            parts.append("Has not played at all in 2026.")
        if missed > streak:
            parts.append(f"Also missed {_plural(missed - streak, 'earlier game')}.")
    else:
        parts.append(f"Has not missed a game yet in 2026, so this would be his first absence." if not missed else f"Played last week; missed {_plural(missed, 'earlier game')} this season.")
    if len(played):
        parts.append(f"Played {len(pw)} of {len(tw)} team games at {snap_avg}% of snaps on average ({role(snap_avg)}).")
    if first_week is not None:
        inj_names = [t["i"] for t in timeline if t["i"]]
        parts.append(f"On the weekly injury report {_plural(len(timeline), 'week')} this season, first in week {first_week}" + (f" ({inj_names[0].lower()})." if inj_names else "."))
    if not known:
        streak = missed = 0
    return {"streak": streak, "missed": missed, "gp": len(pw), "tg": len(tw), "last_played": last_played, "snap_avg": snap_avg, "snap_before": snap_before,
            "role": role(snap_avg), "first_week": first_week, "timeline": timeline, "text": " ".join(parts)}
