"""Empirical NFL margin / total distributions (real, lumpy at 3 and 7), conditioned on a projection.

For a projected home margin mu we take historical games whose CLOSING spread was near mu (Gaussian kernel), and use their
ACTUAL integer margins, shifted by the (fractional) gap between mu and those spreads via a two-point mixture so the mean is
right and the lumps survive. P(win/push/loss) for any line is then read straight off the pmf.
"""
import numpy as np
import pandas as pd

import config


class _Cond:
    def __init__(self, cond: np.ndarray, outcome: np.ndarray, bw: float):
        self.cond, self.out, self.bw = cond, outcome, bw

    def pmf(self, mu: float) -> pd.Series:
        w = np.exp(-0.5 * ((self.cond - mu) / self.bw) ** 2)
        w = w / w.sum()
        d = mu - float((w * self.out).sum())     # centre on the OUTCOME mean so E[margin] = mu exactly
        lo = np.floor(d)
        f = d - lo
        vals = np.concatenate([self.out + lo, self.out + lo + 1])
        wts = np.concatenate([w * (1 - f), w * f])
        s = pd.Series(wts).groupby(vals).sum()
        return s

    def eff_n(self, mu: float) -> float:
        w = np.exp(-0.5 * ((self.cond - mu) / self.bw) ** 2)
        return float(w.sum() ** 2 / (w ** 2).sum())


_cache = {}


def _load():
    if "m" in _cache:
        return _cache["m"], _cache["t"]
    g = pd.read_csv(config.CACHE / "nflverse" / "games.csv")
    g = g[(g.game_type == "REG") & g.home_score.notna() & (g.season >= config.HIST_FROM_SEASON)]
    g = g.dropna(subset=["spread_line", "total_line"])
    _cache["m"] = _Cond(g.spread_line.values.astype(float), g.result.values.astype(float), config.MARGIN_KERNEL_BW)
    _cache["t"] = _Cond(g.total_line.values.astype(float), g.total.values.astype(float), config.TOTAL_KERNEL_BW)
    return _cache["m"], _cache["t"]


def _wlp(pmf: pd.Series, test) -> tuple[float, float, float]:
    """(win, push, loss) where test(values) returns signed outcome (>0 win, ==0 push, <0 loss)."""
    s = test(pmf.index.values.astype(float))
    return float(pmf[s > 1e-9].sum()), float(pmf[np.abs(s) <= 1e-9].sum()), float(pmf[s < -1e-9].sum())


def home_spread_probs(mu_margin: float, home_line: float):
    """Home bet at `home_line` (e.g. -3.5 = home gives 3.5). Returns (win, push, loss) for the HOME side."""
    return _wlp(_load()[0].pmf(mu_margin), lambda m: m + home_line)


def home_moneyline_probs(mu_margin: float):
    return _wlp(_load()[0].pmf(mu_margin), lambda m: m)


def over_probs(mu_total: float, line: float):
    """(win, push, loss) for the OVER at `line`."""
    return _wlp(_load()[1].pmf(mu_total), lambda t: t - line)


def effective_sample(mu_margin: float) -> float:
    return _load()[0].eff_n(mu_margin)
