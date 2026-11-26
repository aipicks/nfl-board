"""Do unders pay at real prices? Best under price per main line, graded; by market and by week; plus a walk-forward model."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
import db

con = db.connect()
p = pd.read_sql("SELECT game_id, market, player_id, side, line, book, price, p_market, logged_ts, kickoff_utc, result FROM pred_log WHERE result IN ('win','loss','push') AND is_parlay_leg=0", con)
p = p[p.logged_ts < p.kickoff_utc.str.replace("Z", ":00Z")].sort_values("logged_ts").drop_duplicates(["game_id", "market", "player_id", "side", "line", "book"], keep="last")
d = pd.read_parquet(pathlib.Path(__file__).parent / "prop_dataset.parquet")
d = d.sort_values("n_books").drop_duplicates(["game_id", "market", "player_id"], keep="last")
d = d[d.n >= 3]
dec = lambda a: np.where(a > 0, a / 100, 100 / np.abs(a))


def best(side):
    q = p[p.side == side].sort_values("price").drop_duplicates(["game_id", "market", "player_id", "line"], keep="last")[["game_id", "market", "player_id", "line", "price", "book"]]
    return q.rename(columns={"price": f"px_{side}", "book": f"bk_{side}"})


d = d.merge(best("under"), on=["game_id", "market", "player_id", "line"], how="left").merge(best("over"), on=["game_id", "market", "player_id", "line"], how="left")
d["u_under"] = np.where(d.over == 0, dec(d.px_under), -1.0)
d["u_over"] = np.where(d.over == 1, dec(d.px_over), -1.0)
h = d[d.px_under.notna()]
print("all unders at best price: n", len(h), "hit", round(1 - h.over.mean(), 3), "roi", round(h.u_under.mean(), 3), "avg price", round(h.px_under.mean(), 1))
print(h.groupby("market").agg(n=("over", "size"), under_hit=("over", lambda x: 1 - x.mean()), roi=("u_under", "mean"), px=("px_under", "mean")).round(3).to_string())
print("\nby week (all unders):"); print(h.groupby("week").agg(n=("over", "size"), roi=("u_under", "mean")).round(3).T.to_string())
r = h[h.market.isin(["rush_yds", "rush_att"])]
print("\nrushing unders by week:"); print(r.groupby("week").agg(n=("over", "size"), roi=("u_under", "mean")).round(3).T.to_string())

# walk-forward model: market prob + market-type dummies + simple history gaps; bet the side whose model prob beats the price by 3+ pts
lg = lambda x: np.log(x / (1 - x))
d["z_mkt"] = lg(d.p_mkt.clip(.02, .98))
s = np.maximum(d.line.abs(), 1)
d["g_med"] = (d.med - d.line) / s
mk = pd.get_dummies(d.market, prefix="m").astype(float)
d = pd.concat([d, mk], axis=1)
cols = ["z_mkt", "g_med"] + list(mk.columns)
bets = []
for w in range(8, 12):
    tr, te = d[d.week < w], d[d.week == w].copy()
    m = LogisticRegression(C=0.5).fit(tr[cols].fillna(0), tr.over)
    te["p"] = m.predict_proba(te[cols].fillna(0))[:, 1]
    for side, pcol, px, ucol in (("under", lambda t: 1 - t.p, "px_under", "u_under"), ("over", lambda t: t.p, "px_over", "u_over")):
        t = te[te[px].notna()].copy()
        t["edge"] = pcol(t) - 1 / (1 + dec(t[px]))
        for th in (0.0, 0.02, 0.04):
            x = t[t.edge >= th]
            bets.append(dict(week=w, side=side, th=th, n=len(x), units=x[ucol].sum()))
b = pd.DataFrame(bets).groupby(["side", "th"]).agg(n=("n", "sum"), units=("units", "sum"))
b["roi"] = (b.units / b.n).round(3)
print("\nwalk-forward model bets (weeks 8-11):"); print(b.round(2).to_string())
