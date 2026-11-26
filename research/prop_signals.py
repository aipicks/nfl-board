"""Which signals predict over/under beyond the market? Walk-forward by week on research/prop_dataset.parquet."""
import pathlib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

d = pd.read_parquet(pathlib.Path(__file__).parent / "prop_dataset.parquet")
d = d.sort_values("n_books").drop_duplicates(["game_id", "market", "player_id"], keep="last")   # main line only
d = d[d.n >= 3].copy()
lg = lambda p: np.log(p / (1 - p))
d["z_mkt"] = lg(d.p_mkt.clip(.02, .98))
d["z_old"] = lg(d.p_old.clip(.02, .98))
s = np.maximum(d.line.abs(), 1)
for k in ["mean", "med", "mean5", "med5", "last"]:
    d["g_" + k] = (d[k] - d.line) / s
d["hit_c"] = d.hit - 0.5; d["hit5_c"] = d.hit5 - 0.5
d["is_under_mkt"] = (d.p_mkt < 0.5).astype(int)
ll = lambda p, y: -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
print("rows", len(d), "over rate", round(d.over.mean(), 3))
print("log-loss  market", round(ll(d.p_mkt.clip(.02, .98), d.over), 4), " old model", round(ll(d.p_old.clip(.02, .98), d.over), 4), " coin", round(ll(np.full(len(d), .5), d.over), 4),
      " constant", round(ll(np.full(len(d), d.over.mean()), d.over), 4))
print("\nsingle-signal correlation with (actual - line)/line:")
d["res"] = (d.actual - d.line) / s
for c in ["g_mean", "g_med", "g_mean5", "g_med5", "g_last", "hit_c", "hit5_c", "z_old", "z_mkt"]:
    print(f"  {c:8s} corr {d[c].corr(d.res):+.3f}   over-rate when >0: {d[d[c] > 0].over.mean():.3f} (n={int((d[c] > 0).sum())})  when <0: {d[d[c] < 0].over.mean():.3f}")
print("\nby market: over rate vs market")
print(d.groupby("market").agg(n=("over", "size"), over=("over", "mean"), mkt=("p_mkt", "mean")).round(3).to_string())

sets = {"mkt only": ["z_mkt"], "mkt+median gaps": ["z_mkt", "g_med", "g_med5"], "mkt+mean gaps": ["z_mkt", "g_mean", "g_mean5"],
        "mkt+hit rates": ["z_mkt", "hit_c", "hit5_c"], "mkt+all": ["z_mkt", "g_med", "g_med5", "g_mean", "g_mean5", "g_last", "hit_c", "hit5_c"],
        "mkt+old": ["z_mkt", "z_old"], "intercept only": []}
print("\nwalk-forward (train weeks < w, test week w, w = 8..11):")
for name, cols in sets.items():
    ps, ys = [], []
    for w in range(8, 12):
        tr, te = d[d.week < w], d[d.week == w]
        if not cols:
            p = np.full(len(te), tr.over.mean())
        else:
            m = LogisticRegression(C=1.0).fit(tr[cols].fillna(0), tr.over)
            p = m.predict_proba(te[cols].fillna(0))[:, 1]
        ps.append(p); ys.append(te.over.values)
    p, y = np.concatenate(ps), np.concatenate(ys)
    print(f"  {name:18s} log-loss {ll(np.clip(p, .02, .98), y):.4f}  acc {np.mean((p > .5) == y):.3f}")
