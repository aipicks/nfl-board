"""Refresh injuries, weather and public splits for the current week and store snapshots.  `python context.py`"""
from datetime import datetime, timezone

import pandas as pd

import config
import db
from adapters import injuries, splits, weather


def current_week(con) -> int:
    g = pd.read_sql("select week, home_score from games where season=?", con, params=(config.SEASON,))
    return int(g[g.home_score.isna()].week.min())


def refresh(con=None, verbose=True) -> dict:
    con = con or db.connect()
    wk = current_week(con)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    games = pd.read_sql("select game_id, home, away, kickoff_utc, roof from games where season=? and week=?", con, params=(config.SEASON, wk))
    players = pd.read_sql("select player_id, name, team, pos from players", con)
    out = {"week": wk, "snap_ts": ts}

    inj = injuries.current(players, config.SEASON, wk)
    injuries.store(con, ts, inj)
    out["injuries"] = inj

    html, wst = weather.raw()
    w = weather.to_games(weather.parse(html), games)
    weather.store(con, ts, w)
    out["weather"], out["weather_fetch"] = w, wst

    j, sst = splits.raw()
    sp = splits.parse(j, games)
    splits.store(con, ts, sp)
    out["splits"], out["splits_fetch"] = sp, sst
    for step, n in (("injuries", len(inj)), ("weather", len(w)), ("splits", len(sp))):
        con.execute("insert into run_log values (?,?,?,?)", (ts, step, 1, f"{n} rows"))
    con.commit()
    if verbose:
        print(f"week {wk}: injuries {len(inj)} (conflicts {int(inj.conflict.sum())}), weather {len(w)}/{len(games)} games, splits {len(sp)} rows")
    return out


if __name__ == "__main__":
    refresh()
