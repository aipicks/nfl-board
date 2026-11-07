"""Prediction tracking: log every prediction BEFORE kickoff, settle from final box scores, summarise for the Results tab.

pred_log row = one pick: (game, market, player, side, line, book) with our model / market / final probability that THIS pick wins.
A re-run before kickoff updates the row (the last pre-kickoff snapshot is the graded one); after kickoff nothing is written.
"""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import config
from adapters import nflverse as nv
from model.devig import to_decimal

NOW = lambda: datetime.now(timezone.utc)


def _key(r):
    return (r["game_id"], r["market"], r.get("player_id") or "", r["side"], -999.0 if r.get("line") is None else float(r["line"]), r["book"])


def _upsert(con, ts, rows):
    n_new = n_upd = 0
    for r in rows:
        k = _key(r)
        ex = con.execute("select pred_id, result from pred_log where game_id=? and market=? and coalesce(player_id,'')=? and side=? and coalesce(line,-999)=? and book=? and is_parlay_leg=0",
                         k).fetchone()
        vals = (ts, r["game_id"], r["market"], r.get("player_id"), r["side"], r.get("line"), r["book"], r["price"], r["p_model"], r["p_market"], r["p_final"], r["ev"], r["label"],
                r["kickoff_utc"], r.get("desc"), json.dumps(r.get("extra") or {}))
        if ex:
            if r.get("extra", {}).get("best_pick") and ex[1] is None:
                old = json.loads(con.execute("select extra from pred_log where pred_id=?", (ex[0],)).fetchone()[0] or "{}")
                r["extra"] = {**old, **r["extra"]}
            if ex[1] is None:
                con.execute("update pred_log set logged_ts=?, price=?, p_model=?, p_market=?, p_final=?, ev=?, label=?, kickoff_utc=?, desc=?, extra=? where pred_id=?",
                            (ts, r["price"], r["p_model"], r["p_market"], r["p_final"], r["ev"], r["label"], r["kickoff_utc"], r.get("desc"), json.dumps(r.get("extra") or {}), ex[0]))
                n_upd += 1
        else:
            con.execute("insert into pred_log(logged_ts, game_id, market, player_id, side, line, book, price, p_model, p_market, p_final, ev, label, is_parlay_leg, kickoff_utc, desc, extra) "
                        "values (?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?)", vals)
            n_new += 1
    return n_new, n_upd


def log_predictions(con, res, props, tds, now=None, best=None, kickoffs=None) -> dict:
    """Log everything the board shows, for games that have not kicked off. Returns counts."""
    now = now or NOW()
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    future = lambda ko: pd.Timestamp(ko, tz="UTC") > pd.Timestamp(now)
    rows = []
    for r in res:
        if not future(r["kickoff_utc"]):
            continue
        for m in config.GAME_MARKETS:
            v = r["markets"].get(m)
            if not v:
                continue
            picks = [v["best"]] + [o for o in v["fanduel"] if v["best"] is None or o is not v["best"]][:1]
            for o in picks:
                if not o:
                    continue
                desc = (f"{r['home'] if o['side'] == 'home' else r['away']} {(o['line'] if o['side'] == 'home' else -o['line']):+g}" if m == "spread" else f"{o['side']} {o['line']:g}")
                rows.append({"game_id": r["game_id"], "market": m, "side": o["side"], "line": o["line"], "book": o["book"], "price": o["price"], "p_model": o["p_model"], "p_market": o["p_market"],
                             "p_final": o["p_final"], "ev": o["ev"], "label": o["label"], "kickoff_utc": r["kickoff_utc"], "desc": f"{r['away']}@{r['home']} {desc}",
                             "extra": {"proj_margin": r["margin"], "proj_total": r["total"], "signal_spread": r["comp"].get("signal_spread"), "signal_total": r["comp"].get("signal_total"), "notes": [str(n)[:160] for n in r.get("notes", [])[:8]]}})
    for p in props:
        if not future(p["kickoff"]):
            continue
        for o in {id(x): x for x in (p["best"], p["fd"]) if x}.values():
            rows.append({"game_id": p["game_id"], "market": p["market"], "player_id": p["player_id"], "side": o["side"], "line": o["line"], "book": o["book"], "price": o["price"],
                         "p_model": o["p_model"], "p_market": o["p_market"], "p_final": o["p_final"], "ev": o["ev"], "label": o["label"], "kickoff_utc": p["kickoff"],
                         "desc": f"{p['player']} {o['side']} {o['line']:g} {p['market']}", "extra": {"mu": p["mu"], "trust": p.get("trust")}})
    for t in tds:
        if not future(t["kickoff"]) or t["p_model"] < config.TD_MIN_PROB:
            continue
        rows.append({"game_id": t["game_id"], "market": "td_any", "player_id": t["player_id"], "side": "yes", "line": None, "book": t["best_book"], "price": t["best_price"],
                     "p_model": t["p_model"], "p_market": t["p_market"], "p_final": t["p_final"], "ev": t["ev"], "label": t["label"], "kickoff_utc": t["kickoff"],
                     "desc": f"{t['player']} anytime TD", "extra": {"lambda": t["lambda"], "limited": t["limited"]}})
    from model.devig import ev as _ev, label as _label
    for gid, slots in (best or {}).items():            # the Best Props picks are graded as their own group
        ko = (kickoffs or {}).get(gid)
        if not ko or not future(ko):
            continue
        for slot, picks in slots.items():
            for p in picks:
                e = _ev(p["p_final"], p["price"])
                rows.append({"game_id": gid, "market": p["market"], "player_id": p["player_id"], "side": p["side"], "line": p["line"], "book": p["book"], "price": p["price"], "p_model": p["p_model"],
                             "p_market": p["p_market"], "p_final": p["p_final"], "ev": round(e, 4), "label": _label(e), "kickoff_utc": ko,
                             "desc": f"{p['player']} {p['side']} {p['line'] if p['line'] is not None else ''} {p['label']}".replace("  ", " "), "extra": {"best_pick": True, "slot": slot}})
    new, upd = _upsert(con, ts, rows)
    con.commit()
    return {"new": new, "updated": upd}


# ------------------------------------------------------------------ settlement
def _outcome(v: float) -> str:
    return "win" if v > 1e-9 else ("push" if abs(v) <= 1e-9 else "loss")


def eval_pick(kind: str, market: str, side: str, line, pid, game, stats) -> tuple[str, float | None]:
    """Return (result, actual) for one pick given the final game row and the week's player stats (dict player_id -> row)."""
    hs, as_ = game["home_score"], game["away_score"]
    if kind in ("spread", "total") or market in ("spread", "total"):
        m = market if market in ("spread", "total") else kind
        if m == "spread":
            margin = hs - as_
            v = (margin + line) if side == "home" else -(margin + line)
            return _outcome(v), float(margin)
        tot = hs + as_
        return _outcome((tot - line) if side == "over" else (line - tot)), float(tot)
    row = stats.get(pid)
    if row is None:
        return "void", None                               # did not play: books refund
    if market == "td_any":
        td = (row.get("rushing_tds") or 0) + (row.get("receiving_tds") or 0)
        return ("win" if td > 0 else "loss"), float(td)
    col = {"pass_yds": "passing_yards", "rush_yds": "rushing_yards", "rec_yds": "receiving_yards", "receptions": "receptions", "rush_att": "carries", "pass_td": "passing_tds",
           "pass_comp": "completions", "pass_att": "attempts", "pass_int": "passing_interceptions"}
    if market in col:
        a = float(row.get(col[market]) or 0)
    elif market == "pass_rush_yds":
        a = float(row.get("passing_yards") or 0) + float(row.get("rushing_yards") or 0)
    elif market == "rush_rec_yds":
        a = float(row.get("rushing_yards") or 0) + float(row.get("receiving_yards") or 0)
    else:
        return "void", None
    return _outcome((a - line) if side == "over" else (line - a)), a


def _stats_by_week(season: int) -> dict:
    st = nv.get("stats", season, max_age_s=3600)
    st = st[st.season_type == "REG"]
    return {w: {r["player_id"]: r for r in x.to_dict("records")} for w, x in st.groupby("week")}


def settle(con) -> dict:
    ts = NOW().strftime("%Y-%m-%dT%H:%M:%SZ")
    games = pd.read_sql("select game_id, season, week, home_score, away_score from games where home_score is not null", con).set_index("game_id")
    sw = {}
    n = 0
    pend = pd.read_sql("select * from pred_log where result is null and is_parlay_leg=0", con)
    for r in pend.itertuples():
        if r.game_id not in games.index:
            continue
        g = games.loc[r.game_id]
        if g.season not in sw:
            sw[g.season] = _stats_by_week(int(g.season))
        stats = sw[g.season].get(int(g.week), {})
        if r.market not in ("spread", "total") and not stats:
            continue                                           # player stats not published yet
        res, act = eval_pick(r.market, r.market, r.side, r.line, r.player_id, g, stats)
        con.execute("update pred_log set result=?, actual=?, settled_ts=? where pred_id=?", (res, act, ts, r.pred_id))
        n += 1
    con.commit()
    return {"settled": n}


# ------------------------------------------------------------------ Results tab data
def _profit(price, result):
    return (to_decimal(price) - 1) if result == "win" else (-1.0 if result == "loss" else 0.0)


def _summ(d: pd.DataFrame) -> dict:
    g = d[d.result.isin(["win", "loss", "push"])]
    dec = g[g.result.isin(["win", "loss"])]
    if g.empty:
        return {"n": 0}
    y = (dec.result == "win").astype(float)
    pr = g.apply(lambda r: _profit(r.price, r.result), axis=1)
    out = {"n": int(len(g)), "w": int((g.result == "win").sum()), "l": int((g.result == "loss").sum()), "p": int((g.result == "push").sum()), "units": round(float(pr.sum()), 2),
           "roi": round(float(pr.sum() / len(g)), 3)}
    if len(dec):
        out.update({"hit": round(float(y.mean()), 3), "pred": round(float(dec.p_final.mean()), 3), "brier_model": round(float(((dec.p_model - y) ** 2).mean()), 4),
                    "brier_market": round(float(((dec.p_market - y) ** 2).mean()), 4), "brier_final": round(float(((dec.p_final - y) ** 2).mean()), 4)})
    return out


def results(con) -> dict:
    d = pd.read_sql("select * from pred_log where is_parlay_leg=0", con)
    pend = d[d.result.isna()]
    out = {"logged": int(len(d)), "pending": int(len(pend)), "settled": int(d.result.notna().sum()), "first_logged": None if d.empty else d.logged_ts.min(),
           "backup_reminder": "Back up data/nfl.db outside this folder: it holds every logged prediction."}
    s = d[d.result.notna() & (d.result != "void")]
    best = s[s.extra.fillna("").str.contains("best_pick")]
    groups = {"Best props picks": best, "Spreads": s[s.market == "spread"], "Totals": s[s.market == "total"], "Anytime TDs": s[s.market == "td_any"], "Player props": s[~s.market.isin(["spread", "total", "td_any"])],
              "All picks": s}
    out["groups"] = {k: _summ(v) for k, v in groups.items()}
    out["by_market"] = {m: _summ(x) for m, x in s.groupby("market")}
    out["by_label"] = {lab: _summ(x) for lab, x in s.groupby("label")}
    out["by_label_market"] = {f"{m}|{lab}": _summ(x) for (m, lab), x in s.groupby(["market", "label"])}
    dec = s[s.result.isin(["win", "loss"])].copy()
    if len(dec):
        dec["y"] = (dec.result == "win").astype(float)
        dec["bin"] = pd.cut(dec.p_final, [0, .1, .2, .3, .4, .5, .6, .7, .8, 1.0])
        out["calibration"] = [{"bin": str(b), "n": int(len(x)), "pred": round(float(x.p_final.mean()), 3), "actual": round(float(x.y.mean()), 3),
                               "market": round(float(x.p_market.mean()), 3)} for b, x in dec.groupby("bin", observed=True)]
    else:
        out["calibration"] = []
    return out
