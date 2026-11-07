"""Gathers everything the game model needs from the DB + caches. `python board_data.py` prints projections vs the market."""
import pandas as pd

import config
import db
from adapters import nflverse as nv
from model import game as G, injuries as INJ, odds_view as ov, qb as QB, ratings as R


def gather(con=None) -> dict:
    con = con or db.connect()
    tg = R.team_games(con)
    games_all = pd.read_sql("select * from games where season=?", con, params=(config.SEASON,))
    wk = int(games_all[games_all.home_score.isna()].week.min())
    games = games_all[(games_all.week == wk) & games_all.home_score.isna() & games_all.sgo_event_id.notna()].sort_values("kickoff_utc")
    as_of = float(tg[tg.season == config.SEASON].t.max() + 1)
    qg = QB.load_qb_games()
    depth = nv.get("depth", config.SEASON)
    depth = depth[depth.dt == depth.dt.max()]
    inj = pd.read_sql("select * from injuries where snap_ts=(select max(snap_ts) from injuries)", con)
    w = pd.read_sql("select * from weather where snap_ts=(select max(snap_ts) from weather)", con)
    sp = pd.read_sql("select * from public_splits where snap_ts=(select max(snap_ts) from public_splits)", con)
    splits = {}
    for r in sp.itertuples():
        splits.setdefault((r.game_id, r.market), {})[r.side] = {"tickets_pct": r.tickets_pct, "money_pct": r.money_pct}
    odds = ov.latest(con)
    moves = {}
    for g in games.itertuples():
        moves[g.game_id] = {m: ov.movement(odds, g.sgo_event_id, m) for m in ("spread", "total")}
    snap = lambda t: con.execute(f"select max(snap_ts) from {t}").fetchone()[0]
    return {"week": wk, "games": games, "as_of_t": as_of, "ratings": R.fit(tg, as_of), "qb_games": qg, "qb_shr": QB.shrunk_epa(qg),
            "depth": depth, "injuries": inj, "usage": G._skill_usage(con, config.SEASON), "snap_shares": INJ.recent_snap_share(config.SEASON), "active": INJ.active_ids(config.SEASON),
            "weather": {r["game_id"]: r for r in w.to_dict("records")}, "splits": splits, "odds_latest": odds, "moves": moves,
            "event_ids": dict(zip(games.game_id, games.sgo_event_id)),
            "ages": {"odds": snap("odds_snap"), "injuries": snap("injuries"), "weather": snap("weather"), "splits": snap("public_splits")}}


def run(con=None):
    ctx = gather(con)
    proj = G.project(ctx)
    return ctx, G.evaluate(ctx, proj)


if __name__ == "__main__":
    ctx, res = run()
    print(f"week {ctx['week']}  games {len(res)}")
    for r in res:
        sp = r["markets"]["spread"]["fanduel"]; to = r["markets"]["total"]["fanduel"]
        fd_line = sp[0]["line"] if sp else None
        print(f"{r['away']}@{r['home']:4} proj margin {r['margin']:+5.1f} total {r['total']:5.1f} | FD home line {fd_line} total {to[0]['line'] if to else None}"
              f" | comp " + " ".join(f"{k}={v:+.1f}" for k, v in r['comp'].items() if k not in ('ratings_total',) and abs(v) >= 0.05))
        for n in r["notes"]:
            print("      ", n)
