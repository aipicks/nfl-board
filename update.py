"""Weekly update: refresh data, validate, refresh context + odds, rebuild the board with a deep dive for EVERY game.

    python update.py             full run (Thursday / Saturday)
    python update.py --quick     skip the nflverse rebuild (Sunday-morning re-run: injuries, weather, odds, board)

Aborts before building if validation fails. Backs up the database first. Nothing is published."""
import shutil
import sys
import time
from datetime import datetime, timezone

import config
import db


def step(name, fn):
    t = time.time()
    print(f"[{name}] ...", flush=True)
    out = fn()
    print(f"[{name}] done in {time.time() - t:.0f}s", flush=True)
    return out


def main(quick=False):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bk = config.ROOT / "data" / "backups"
    bk.mkdir(parents=True, exist_ok=True)
    if config.DB_PATH.exists():
        shutil.copy(config.DB_PATH, bk / f"nfl_{ts}.db")
        old = sorted(bk.glob("nfl_*.db"))[:-10]
        for f in old:
            f.unlink()
        print(f"database backed up to data/backups/nfl_{ts}.db (keeping the last 10)")
    import data_layer, validate, context, odds, build_board, tracking, learning
    if not quick:
        step("nflverse data", lambda: data_layer.build(verbose=False))
        bad = [(n, d) for n, ok, d in step("validate data", validate.run_all) if not ok]
        if bad:
            print("DATA VALIDATION FAILED, not building:", bad)
            return 1
    r = step("settle finished games", lambda: tracking.settle(db.connect()))
    print("   ", r)
    print("    learning:", step("learn from settled picks", lambda: learning.run(db.connect())))
    step("injuries, weather, public splits", lambda: context.refresh(verbose=True))
    con, wk, st, unmatched = step("odds (1 SportsGameOdds request)", lambda: odds.ingest(force=True))
    bad = [(n, d) for n, ok, d in step("validate context", validate.validate_context) if not ok]
    if bad:
        print("CONTEXT VALIDATION FAILED, not building:", bad)
        return 1
    data = step("build board (TD, props, deep dives, log picks, results)", lambda: build_board.build())
    c = db.connect()
    c.execute("insert into run_log values (?,?,?,?)", (ts, "update", 1, f"week {wk}, {len(data['games'])} games, quick={quick}"))
    c.commit()
    print(f"\nDONE: week {wk}, {len(data['games'])} games with deep dives. Open board.html (also written to docs/index.html).")
    print("Reminder: back up data/nfl.db somewhere outside this folder now and then; it holds all logged predictions.")
    return 0


if __name__ == "__main__":
    sys.exit(main(quick="--quick" in sys.argv))
