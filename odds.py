"""Odds ingest. `python odds.py` pulls this week's slate from SGO (1 request), stores it, prints a summary."""
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

import config
import db
from adapters import sgo


def current_window(con):
    """(week, start, end, n_games) for the first week of this season that still has unplayed games."""
    g = pd.read_sql("select * from games where season=?", con, params=(config.SEASON,))
    wk = int(g[g.home_score.isna()].week.min())
    unplayed = g[(g.week == wk) & g.home_score.isna()]
    end = pd.to_datetime(unplayed.kickoff_utc).max().to_pydatetime().replace(tzinfo=timezone.utc) + timedelta(hours=6)
    return wk, datetime.now(timezone.utc), end, len(unplayed)


def ingest(force=False):
    con = db.connect()
    wk, start, end, n = current_window(con)
    path, st = sgo.fetch_slate(start, end, n, force=force)
    snap_ts = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if con.execute("select 1 from odds_snap where snap_ts=? limit 1", (snap_ts,)).fetchone():
        print(f"snapshot {snap_ts} already stored ({st})")
        return con, wk, st, []
    players = pd.read_sql("select player_id, name, team from players", con)
    games = pd.read_sql("select game_id, home, away, kickoff_utc from games where season=? and week=?", con,
                        params=(config.SEASON, wk))
    rows, ev_map, unmatched = sgo.parse(path, snap_ts, players, games)
    rows.to_sql("odds_snap", con, if_exists="append", index=False)
    for ev, gid in ev_map.items():
        con.execute("update games set sgo_event_id=? where game_id=?", (ev, gid))
    con.execute("insert into run_log values (?,?,?,?)", (snap_ts, "odds", 1, f"{len(rows)} rows, {len(ev_map)} events ({st})"))
    con.commit()
    return con, wk, st, unmatched


def game_lines(con):
    """One dict per game: reference line, de-vigged fair probs, best price per side, opening line and movement."""
    from model import odds_view as ov
    df = ov.latest(con)
    w = ov.wide(df)
    games = pd.read_sql("select game_id, home, away, kickoff_utc, sgo_event_id from games where sgo_event_id is not null", con)
    out = []
    for _, g in games.iterrows():
        row = {"game_id": g.game_id, "home": g.home, "away": g.away, "kickoff_utc": g.kickoff_utc}
        for m in ("spread", "moneyline", "total"):
            c = ov.consensus(w[(w.event_id == g.sgo_event_id) & (w.market == m)])
            row[m] = c
            row[m + "_move"] = ov.movement(df, g.sgo_event_id, m) if m != "moneyline" else None
        out.append(row)
    return out


if __name__ == "__main__":
    con, wk, st, unmatched = ingest(force="--force" in sys.argv)
    print(f"week {wk} slate ({st}); sgo budget left: {sgo.remaining_entities()}")
    print(pd.read_sql("select market, count(*) rows, count(distinct book) books from odds_snap group by market order by 2 desc", con).to_string(index=False))
    print("unmatched SGO players:", len(unmatched), unmatched[:15])
    print(f"{'game':9} {'FD spread(home)':>15} {'fair home':>9} {'open':>6} {'keys':>8} | {'total':>6} {'fair over':>9} {'open':>6} | {'fair ML home':>12}")
    for g in game_lines(con):
        sp, tt, ml = g["spread"], g["total"], g["moneyline"]
        if not (sp and tt and ml):
            print(g["away"], "@", g["home"], "missing market"); continue
        print(f"{g['away']+'@'+g['home']:9} {sp['line']:>15} {sp['p_a']:>9.3f} {str(g['spread_move']['open']):>6} {str(g['spread_move']['keys']):>8} | "
              f"{tt['line']:>6} {tt['p_a']:>9.3f} {str(g['total_move']['open']):>6} | {ml['p_a']:>12.3f}  books={sp['n_books']}/{tt['n_books']}/{ml['n_books']}")
