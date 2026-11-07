"""Walk-forward fit of prop dispersion: predict each player-game with a recency-weighted mean of his earlier games (2024+2025), then fit
Var(actual | mean) = a*mean + c*mean^2 per market on 2025 weeks 6-18. Also reports calibration of P(over) at the player's own median line.
`python props_backtest.py`"""
import numpy as np, pandas as pd
from scipy.stats import gamma, nbinom
from adapters import nflverse as nv

st = pd.concat([nv.get("stats", s).assign(season=s) for s in (2024, 2025)])
st = st[st.season_type == "REG"].copy()
st["order"] = st.season * 100 + st.week
M = {"pass_yds": ("passing_yards", "QB", "attempts", 15), "pass_att": ("attempts", "QB", "attempts", 15), "pass_comp": ("completions", "QB", "attempts", 15),
     "pass_td": ("passing_tds", "QB", "attempts", 15), "pass_int": ("passing_interceptions", "QB", "attempts", 15), "rush_yds": ("rushing_yards", "RB", "carries", 4),
     "rush_att": ("carries", "RB", "carries", 4), "rec_yds": ("receiving_yards", None, "targets", 3), "receptions": ("receptions", None, "targets", 3)}
out = {}
for mk, (col, pos, gate, gmin) in M.items():
    d = st[st.position.isin([pos] if pos else ["WR", "TE", "RB"])].copy()
    rows = []
    for pid, x in d.groupby("player_id"):
        x = x.sort_values("order").reset_index(drop=True)
        v = x[col].fillna(0).values
        for i in range(len(x)):
            if x.season[i] != 2025 or x.week[i] < 6 or i < 4:
                continue
            w = 0.5 ** (np.arange(i)[::-1] / 6.0)
            mu = (w * v[:i]).sum() / w.sum()
            if x[gate].fillna(0)[:i].tail(5).mean() < gmin:
                continue
            rows.append((mu, v[i]))
    a = pd.DataFrame(rows, columns=["mu", "y"]); a = a[a.mu > 0]
    res2 = (a.y - a.mu) ** 2
    cv2 = float((res2 / a.mu ** 2).mean())            # constant-CV model: var = cv2 * mu^2
    lin = float((res2 / a.mu).mean())                 # Poisson-like model: var = lin * mu
    # pick the form with the flatter residual-vs-mean relationship
    q = pd.qcut(a.mu, 4, duplicates="drop"); g = res2.groupby(q, observed=True).mean(); mm = a.mu.groupby(q, observed=True).mean()
    slope = np.polyfit(np.log(mm), np.log(g), 1)[0]          # var ~ mu^slope
    coef = np.array([lin, 0.0]) if slope < 1.5 else np.array([0.0, cv2])
    print(f"   {mk}: resid sd {np.sqrt(res2.mean()):.2f}, cv {np.sqrt(cv2):.2f}, var~mu^{slope:.2f}")
    bias = (a.y - a.mu).mean()
    # calibration of P(over median-ish line): line = round(mu)+0.5 ; compare predicted vs actual
    var = coef[0] * a.mu + coef[1] * a.mu ** 2
    line = np.floor(a.mu) + 0.5
    if "yds" in mk:
        k = a.mu ** 2 / var; th = var / a.mu; p = 1 - gamma.cdf(line, k, scale=th)
    else:
        r = (a.mu ** 2 / (var - a.mu)).clip(lower=0.5, upper=500); p = 1 - nbinom.cdf(np.floor(line), r, r / (r + a.mu))
    act = (a.y > line).astype(float)
    out[mk] = (round(coef[0], 3), round(coef[1], 4))
    print(f"{mk:10} n={len(a):5d} mean={a.mu.mean():7.2f} bias={bias:+.2f}  var = {coef[0]:.3f}*mu + {coef[1]:.4f}*mu^2   P(over) pred {p.mean():.3f} actual {act.mean():.3f}")
print(out)
