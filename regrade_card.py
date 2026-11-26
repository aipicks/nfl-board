"""Re-grade past weeks as if the Best Picks card rules (best_props.card, 2026-11-25) had been used.

Uses only what was logged BEFORE kickoff (the last pre-kickoff snapshot of each line in pred_log) plus this season's weekly box
scores from weeks BEFORE the game, so nothing from the result leaks into the choice. Then grades the chosen picks at their logged
prices. Writes results/card_history.json (shown on the Results tab) and prints a summary.

Not replayed: anytime-TD picks (the snap / red-zone role data was not logged per week) and the "projection disagrees" downgrade
for spreads and totals (the raw projection was not logged). Injury status: a line that was logged means the player was not ruled out.
Usage: python regrade_card.py
"""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

import best_props as B
import numpy as np
from model import prop_calib as PC
import config
from adapters import nflverse as nv
import db

PROP_MKTS = {"pass_yds", "rush_yds", "rec_yds", "receptions", "rush_att", "pass_td", "pass_comp", "pass_att", "pass_int", "pass_rush_yds", "rush_rec_yds"}
SER = {"pass_yds": "passing_yards", "rush_yds": "rushing_yards", "rec_yds": "receiving_yards", "receptions": "receptions", "rush_att": "carries", "pass_td": "passing_tds",
       "pass_comp": "completions", "pass_att": "attempts", "pass_int": "passing_interceptions"}


def _series(stats, pid, market, week):
    x = stats[(stats.player_id == pid) & (stats.week < week)].sort_values("week")
    if market in SER:
        v = x[SER[market]].fillna(0)
    elif market == "pass_rush_yds":
        v = x.passing_yards.fillna(0) + x.rushing_yards.fillna(0)
    else:
        v = x.rushing_yards.fillna(0) + x.receiving_yards.fillna(0)
    return [float(z) for z in v.tail(8)], len(x)


def _units(result, price):
    if result == "win":
        return price / 100 if price > 0 else 100 / -price
    return -1.0 if result == "loss" else 0.0


def _slot(ko):
    k = datetime.strptime(ko[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/New_York"))
    return "sunday" if k.weekday() == 6 and k.hour < 19 else "standalone"


def main(quiet=False):
    con = db.connect()
    d = pd.read_sql("SELECT * FROM pred_log WHERE result IN ('win','loss','push') AND is_parlay_leg=0", con)
    d = d[d.logged_ts < d.kickoff_utc.str.replace("Z", ":00Z")].sort_values("logged_ts")
    d = d.drop_duplicates(["game_id", "market", "player_id", "side", "line", "book"], keep="last")
    d["week"] = d.game_id.str.split("_").str[1].astype(int)
    d["season"] = d.game_id.str.split("_").str[0].astype(int)
    d = d[d.season == config.SEASON]
    stats = nv.get("stats", config.SEASON)
    stats = stats[stats.season_type == "REG"]
    train_all = PC.training_set(con, stats)
    picks = []
    for wk, w in d.groupby("week"):
        games = w.drop_duplicates("game_id")[["game_id", "kickoff_utc"]]
        props = {}
        tr = train_all[train_all.week < wk]
        if len(tr) >= 300:                                      # prop model v2, fitted only on weeks before this one
            model = PC.fit(tr)
            pw_ = w[w.market.isin(PROP_MKTS)].copy()
            pw_["p_over_mkt"] = pw_.apply(lambda r: r.p_market if r.side == "over" else 1 - r.p_market, axis=1)
            mk = pw_.groupby(["game_id", "market", "player_id", "line"]).p_over_mkt.mean()
            for r in pw_.itertuples():
                yard = r.market in B.YARD_MKTS
                if not ((-115 if yard else -125) <= r.price <= 140) or r.line < B.MIN_OVER_LINE.get(r.market, 0):
                    continue
                s_, n26 = _series(stats, r.player_id, r.market, wk)
                if n26 < 5:
                    continue
                po = PC.p_over(model, r.market, mk[(r.game_id, r.market, r.player_id, r.line)], float(np.median(s_[-8:])), r.line)
                pside = po if r.side == "over" else 1 - po
                edge = pside - PC.implied(r.price)
                if edge < PC.EDGE_MIN:
                    continue
                k = (r.game_id, r.player_id)
                if k not in props or edge > props[k][0]:
                    props[k] = (edge, r, "FIRM" if edge >= PC.EDGE_FIRM else "LEAN")
        by_game = {}
        for (gid, _), v in props.items():
            by_game.setdefault(gid, []).append(v)
        for v in by_game.values():
            v.sort(key=lambda t: -t[0])
        gp = {}
        for r in w[w.market.isin(("spread", "total"))].itertuples():
            if r.ev >= config.LEAN_EV and ((r.game_id, r.market) not in gp or r.ev > gp[(r.game_id, r.market)].ev):
                gp[(r.game_id, r.market)] = r

        def add(r, kind, lab, slot):
            picks.append({"week": int(wk), "slot": slot, "kind": kind, "game_id": r.game_id, "desc": r.desc, "market": r.market, "side": r.side, "line": r.line,
                          "book": r.book, "price": int(r.price), "label": lab, "result": r.result, "actual": r.actual, "units": round(_units(r.result, r.price), 3)})

        sun = [g for g in games.itertuples() if _slot(g.kickoff_utc) == "sunday"]
        pool, per = [], {}
        for t in sorted([t for g in sun for t in by_game.get(g.game_id, [])], key=lambda t: -t[0]):
            if per.get(t[1].game_id, 0) >= 2:
                continue
            pool.append(t); per[t[1].game_id] = per.get(t[1].game_id, 0) + 1
            if len(pool) == 12:
                break
        for t in pool:
            add(t[1], "prop", t[2], "sunday")
        for mk, n in (("spread", 3), ("total", 2)):
            for r in sorted([gp[(g.game_id, mk)] for g in sun if (g.game_id, mk) in gp], key=lambda r: -r.ev)[:n]:
                add(r, mk, "FIRM" if r.ev >= config.BET_EV else "LEAN", "sunday")
        for g in games.itertuples():
            if _slot(g.kickoff_utc) != "standalone":
                continue
            for t in by_game.get(g.game_id, [])[:2]:
                add(t[1], "prop", t[2], "standalone")
            c = [gp[(g.game_id, mk)] for mk in ("spread", "total") if (g.game_id, mk) in gp]
            if c:
                r = max(c, key=lambda r: r.ev)
                add(r, r.market, "FIRM" if r.ev >= config.BET_EV else "LEAN", "standalone")

    def summ(ps):
        dec = [p for p in ps if p["result"] != "push"]
        w = sum(p["result"] == "win" for p in ps)
        l = sum(p["result"] == "loss" for p in ps)
        u = round(sum(p["units"] for p in ps), 2)
        return {"n": len(ps), "w": w, "l": l, "p": len(ps) - w - l, "units": u, "roi": round(u / len(dec), 3) if dec else None}

    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "rules": "best_props.card with prop model v2 (2026-11-25), replayed on pre-kickoff data; props from week 8 (model needs earlier weeks to train)",
           "total": summ(picks), "by_kind": {k: summ([p for p in picks if p["kind"] == k]) for k in ("prop", "spread", "total")},
           "by_label": {k: summ([p for p in picks if p["label"] == k]) for k in ("FIRM", "LEAN")},
           "by_week": [{"week": wk, **summ([p for p in picks if p["week"] == wk])} for wk in sorted({p["week"] for p in picks})], "picks": picks}
    (config.ROOT / "results").mkdir(exist_ok=True)
    (config.ROOT / "results" / "card_history.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    if not quiet:
        print("total", out["total"]); print("by kind", out["by_kind"]); print("by label", out["by_label"])
        for x in out["by_week"]:
            print(x)
    return out


if __name__ == "__main__":
    main()
