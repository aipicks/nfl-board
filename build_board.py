"""Builds board.html (and docs/index.html) from the DB: `python build_board.py`  (does not publish anything).

Pipeline: game model (spread + total) -> anytime-TD rows -> player-prop rows -> deep dive for every game ->
log every prediction (games not yet kicked off only) -> Results summary -> HTML.
"""
import json
import math
import sys
from datetime import datetime, timezone

import config
import board_data
import db
import deep_dive
import best_props
import te_board
import learning
import props_board
import td_board
import tracking

BOOK_ABBR = {"fanduel": "FD", "draftkings": "DK", "betmgm": "MGM", "espnbet": "ESPN", "bovada": "BOV"}


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else round(o, 4)
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return _clean(o.item())
    except ImportError:
        pass
    return o


def payload(log=True):
    con = db.connect()
    ctx, res = board_data.run(con)
    games = []
    for r in res:
        gid = r["game_id"]
        mk = {m: {"best": v["best"], "fd": v["fanduel"][:2], "options": v["options"]} for m, v in r["markets"].items()}
        games.append({
            "id": gid, "home": r["home"], "away": r["away"], "kickoff": r["kickoff_utc"],
            "margin": r["margin"], "total": r["total"],
            "margin_eff": (-r["ref"]["spread"] + config.MODEL_TRUST["margin"] * (r["margin"] + r["ref"]["spread"])) if r["ref"].get("spread") is not None else r["margin"],
            "total_eff": (r["ref"]["total"] + config.MODEL_TRUST["total"] * (r["total"] - r["ref"]["total"])) if r["ref"].get("total") is not None else r["total"],
            "pts_home": r["pts_home"], "pts_away": r["pts_away"],
            "comp": r["comp"], "notes": r["notes"], "ref": r["ref"], "markets": mk,
            "weather": {k: ctx["weather"].get(gid, {}).get(k) for k in ("temp_f", "wind_mph", "precip_pct", "conditions", "indoor")} if gid in ctx["weather"] else None,
            "splits": {m: ctx["splits"].get((gid, m)) for m in config.GAME_MARKETS},
            "moves": ctx["moves"].get(gid),
        })
    tds = td_board.td_rows(ctx, res, con)
    props = props_board.props_rows(ctx, res, con)
    deeps = deep_dive.build_all(con, ctx, res, props, tds)
    bp = best_props.select(props, tds, deeps, games)
    watch = best_props.watchlist(props, tds, deeps, games)
    mnf = best_props.mnf(bp, games)
    kos = {g["id"]: g["kickoff"] for g in games}
    te = te_board.build(tds, deeps, games, con)
    logged = tracking.log_predictions(con, res, props, tds, best=bp, kickoffs=kos) if log else None
    for p in props:                                   # the per-option lists were only needed for the Best Props selection
        p.pop("opts", None)
    allbest = [(g["id"], m, v["best"]) for g in games for m, v in g["markets"].items() if v["best"]]
    top = max(allbest, key=lambda x: x[2]["ev"]) if allbest else None
    first = min(games, key=lambda g: g["kickoff"])["id"] if games else None
    data = {"built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "week": ctx["week"], "season": config.SEASON,
            "ages": ctx["ages"], "games": games, "deeps": deeps, "deep_default": first, "top": {"game": top[0], "market": top[1]} if top else None,
            "td": tds, "props": props, "te": te, "bestprops": {"games": bp, "watch": watch, "mnf": mnf, "range": [best_props.PRICE_LO, best_props.PRICE_HI]},
            "results": tracking.results(con), "logged": logged, "learning": learning.summary(),
            "cfg": {"bet": config.BET_EV, "lean": config.LEAN_EV, "w": config.MODEL_WEIGHT, "trust": config.MODEL_TRUST, "hfa": config.HFA,
                    "half_life": config.RATING_HALF_LIFE, "ridge": config.RATING_RIDGE, "play": config.PLAY_PROB,
                    "cap_s": config.PUBLIC_CAP_SPREAD, "cap_t": config.PUBLIC_CAP_TOTAL, "prop_trust": config.PROP_TRUST, "td_hold": config.TD_ASSUMED_HOLD,
                    "td_min": config.TD_MIN_PROB, "td_top": config.TD_TOP_N, "markets": list(config.GAME_MARKETS)},
            "books": BOOK_ABBR}
    return data


def build(out_files=("board.html", "docs/index.html"), log=True):
    data = _clean(payload(log))
    tpl = (config.ROOT / "board_template.html").read_text(encoding="utf-8")
    js = "\n".join((config.ROOT / f).read_text(encoding="utf-8") for f in ("deep_tab.js", "tabs_new.js", "weather_tab.js", "injuries_tab.js", "bestprops_tab.js", "te_tab.js"))
    html = tpl.replace("/*DEEPJS*/", js).replace("__DATA__", json.dumps(data, separators=(",", ":")))
    for f in out_files:
        p = config.ROOT / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
    return data


if __name__ == "__main__":
    d = build(log="--nolog" not in sys.argv)
    print(f"built board.html + docs/index.html: week {d['week']}, {len(d['games'])} games, {len(d['td'])} TD rows, {len(d['props'])} prop rows, "
          f"logged {d['logged']}")
