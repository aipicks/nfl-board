"""Walk-forward backtest of the QB-aware ratings. For each game 2025 + 2026-to-date, ratings use only earlier games; the QB term
uses the QB who actually started (upper bound on what knowing the starter is worth). Also reports the trust factor: how much of
(model - market) was real."""
import numpy as np, pandas as pd, config, db
from model import ratings as R
import backtest

con = db.connect(); tg = R.team_games(con)
g = pd.read_csv(config.CACHE / "nflverse" / "games.csv"); g = g[(g.game_type == "REG") & g.home_score.notna() & g.season.isin([2025, 2026]) & (g.week >= 3)].copy()
g["home"] = g.home_team.replace({"LAR": "LA"}); g["away"] = g.away_team.replace({"LAR": "LA"})
g["t"] = (g.season - (config.LAST_SEASON - 1)) * config.OFFSEASON_WEEKS + g.week
qbe = tg.set_index(["season", "week", "team"]).qb_epa
cache = {t: R.fit(tg, t) for t in sorted(g.t.unique())}
rows = []
for _, x in g.iterrows():
    r = cache[x.t]
    hfa = config.HFA_NEUTRAL if x.location == "Neutral" else config.HFA
    qh, qa = qbe.get((x.season, x.week, x.home)), qbe.get((x.season, x.week, x.away))
    m0, t0 = backtest.base_projection(r, x.home, x.away, config.POINTS_PER_EPA, hfa)
    m1, t1 = backtest.base_projection(r, x.home, x.away, config.POINTS_PER_EPA, hfa, qh, qa)
    rows.append((x.result, x.spread_line, m0, m1, x.total, x.total_line, t0, t1))
d = pd.DataFrame(rows, columns=["res", "mkt", "m0", "m1", "tot", "tline", "t0", "t1"])
b = cache[max(cache)]["pass"]
print(f"games={len(d)}  QB coefficient on pass EPA/play: {b['qb_beta']:.2f} per 1.0 EPA/db  (qb mean {b['qb_mean']:+.3f})")
for name, c in (("avg QB   ", "m0"), ("actual QB", "m1")):
    e = d.res - d[c]; print(f"{name}: margin rmse {np.sqrt((e**2).mean()):.3f}")
print("market   : margin rmse", np.sqrt(((d.res - d.mkt) ** 2).mean()).round(3), "| total rmse model", np.sqrt(((d.tot - d.t1) ** 2).mean()).round(3), "market", np.sqrt(((d.tot - d.tline) ** 2).mean()).round(3))
for lab, c, tc in (("margin", "m1", None), ("total", None, "t1")):
    x = (d[c] - d.mkt).values if c else (d[tc] - d.tline).values
    y = (d.res - d.mkt).values if c else (d.tot - d.tline).values
    k = (x * y).sum() / (x * x).sum(); se = np.sqrt(((y - k * x) ** 2).sum() / (len(x) - 1) / (x * x).sum())
    print(f"trust {lab}: {k:+.3f} +/- {se:.3f}  (sd of model-market {x.std():.2f})")
