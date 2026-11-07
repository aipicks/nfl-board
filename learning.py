"""The learning loop. Run by update.py after games settle (and by hand: `python learning.py`).

1. REVIEW   every settled pick vs what happened: projection bias and error vs the market, calibration, biggest misses with the context
            that was known at the time (injuries, weather, QB), written to reviews/week_N.md for a human (and the analyst) to read.
2. ADJUST   a few priors are nudged by the evidence, but only with enough graded picks, with damping, inside hard bounds, and every
            change is logged in lessons_auto.md and learned.json (config.py loads learned.json at import). Nothing else is touched silently.
3. LESSONS  lessons.md holds the corrections the user gives; the Results tab shows them next to the automatic changes.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import config
import db

ROOT = config.ROOT
LEARNED = ROOT / "learned.json"
# parameter -> (min graded picks, bounds, damping toward the new estimate)
RULES = {"MODEL_TRUST.margin": (80, (0.0, 0.6), 0.5), "MODEL_TRUST.total": (80, (0.0, 0.6), 0.5), "TD_LAMBDA_SCALE": (300, (0.8, 1.2), 0.5), "PROP_TRUST": (300, (0.05, 0.8), 0.5)}


def _load() -> dict:
    return json.loads(LEARNED.read_text(encoding="utf-8")) if LEARNED.exists() else {}


def current_value(name: str):
    if name.startswith("MODEL_TRUST."):
        return config.MODEL_TRUST[name.split(".")[1]]
    return getattr(config, name)


def _estimates(con) -> dict:
    """Evidence-based targets from settled picks. Returns {param: (estimate, n, note)}."""
    d = pd.read_sql("select * from pred_log where result in ('win','loss') and is_parlay_leg=0", con)
    out = {}
    if d.empty:
        return out
    d["y"] = (d.result == "win").astype(float)
    d["x"] = d.extra.map(lambda s: json.loads(s) if s else {})
    for mk, key, pname in (("spread", "proj_margin", "MODEL_TRUST.margin"), ("total", "proj_total", "MODEL_TRUST.total")):
        s = d[(d.market == mk) & d.x.map(lambda x: key in x)]
        if len(s) >= 20:
            # does the model's disagreement with the market predict the outcome? regress (won - market p) on (model p - market p)
            gap = (s.p_model - s.p_market).values
            res = (s.y - s.p_market).values
            beta = float((gap * res).sum() / max((gap * gap).sum(), 1e-9))
            out[pname] = (beta, len(s), f"{mk}: outcome-vs-market on model-vs-market slope {beta:+.2f}")
    t = d[d.market == "td_any"]
    if len(t) >= 50:
        out["TD_LAMBDA_SCALE"] = (config.TD_LAMBDA_SCALE * float(t.y.mean() / max(t.p_model.mean(), 1e-6)), len(t), f"anytime TD: predicted {t.p_model.mean():.3f} vs actual {t.y.mean():.3f}")
    p = d[~d.market.isin(["spread", "total", "td_any"])]
    if len(p) >= 50:
        gap = (p.p_model - p.p_market).values
        res = (p.y - p.p_market).values
        out["PROP_TRUST"] = (float((gap * res).sum() / max((gap * gap).sum(), 1e-9)), len(p), f"props: outcome-vs-market on model-vs-market slope")
    return out


def adjust(con, write=True) -> list[dict]:
    learned = _load()
    changes = []
    for name, (est, n, note) in _estimates(con).items():
        need, (lo, hi), damp = RULES[name]
        if n < need:
            continue
        cur = current_value(name)
        new = float(np.clip(cur + damp * (est - cur), lo, hi))
        if abs(new - cur) < 0.01 * max(abs(cur), 0.1):
            continue
        learned[name] = {"value": round(new, 4), "n": n, "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "reason": note, "was": round(float(cur), 4)}
        changes.append({"param": name, **learned[name]})
    if changes and write:
        LEARNED.write_text(json.dumps(learned, indent=2), encoding="utf-8")
        with open(ROOT / "lessons_auto.md", "a", encoding="utf-8") as f:
            for c in changes:
                f.write(f"- {c['updated']}: {c['param']} {c['was']} -> {c['value']} ({c['n']} graded picks; {c['reason']})\n")
    return changes


def weekly_review(con) -> dict:
    """Biggest misses and bias per settled week, with the context known when the pick was logged. Writes reviews/week_N.md."""
    d = pd.read_sql("select p.*, g.season, g.week, g.home, g.away, g.home_score, g.away_score from pred_log p join games g using(game_id) where p.result is not null and p.market in ('spread','total')", con)
    out = {}
    if d.empty:
        return out
    d["x"] = d.extra.map(lambda s: json.loads(s) if s else {})
    (ROOT / "reviews").mkdir(exist_ok=True)
    for (season, week), w in d.groupby(["season", "week"]):
        lines = [f"# Week {week}, {season}: review of {len(w)} graded spread/total picks", ""]
        g = w[w.result.isin(["win", "loss"])]
        if len(g):
            lines.append(f"Hit rate {g.result.eq('win').mean():.1%} vs predicted {g.p_final.mean():.1%}; BET/LEAN picks {g[g.label.isin(['BET','LEAN'])].result.eq('win').sum()}-{g[g.label.isin(['BET','LEAN'])].result.eq('loss').sum()}.")
        err = []
        for r in w.itertuples():
            if r.market == "spread" and "proj_margin" in r.x:
                err.append((abs((r.home_score - r.away_score) - r.x["proj_margin"]), f"{r.away}@{r.home} spread: projected {r.home} by {r.x['proj_margin']:+.1f}, actual {r.home_score - r.away_score:+d}", r.x.get("notes", [])))
            if r.market == "total" and "proj_total" in r.x:
                err.append((abs((r.home_score + r.away_score) - r.x["proj_total"]), f"{r.away}@{r.home} total: projected {r.x['proj_total']:.1f}, actual {r.home_score + r.away_score}", r.x.get("notes", [])))
        err.sort(key=lambda e: -e[0])
        lines += ["", "## Largest projection errors (check whether the notes explain them)", ""]
        for e, txt, notes in err[:8]:
            lines.append(f"- off by {e:.1f}: {txt}" + (f" | known then: {'; '.join(notes)[:300]}" if notes else ""))
        (ROOT / "reviews" / f"week_{int(season)}_{int(week):02d}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        out[f"{int(season)}-{int(week)}"] = len(err)
    return out


def lessons_text() -> list[dict]:
    """Parse lessons.md: '## date: title' followed by the paragraph beneath it."""
    f = ROOT / "lessons.md"
    if not f.exists():
        return []
    out, cur = [], None
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            cur = {"title": line[3:].strip(), "body": ""}
            out.append(cur)
        elif cur is not None and line.strip():
            cur["body"] += (" " if cur["body"] else "") + line.strip()
    return out


def summary() -> dict:
    auto = []
    f = ROOT / "lessons_auto.md"
    if f.exists():
        auto = [l[2:] for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("- ")][-12:]
    return {"learned": _load(), "auto_changes": auto, "lessons": lessons_text(), "rules": {k: {"min_n": v[0], "bounds": v[1]} for k, v in RULES.items()}}


def run(con=None) -> dict:
    con = con or db.connect()
    return {"adjusted": adjust(con), "reviewed": weekly_review(con)}


if __name__ == "__main__":
    print(run())
