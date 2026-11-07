"""Player-props math: distributions (gamma for yards, negative binomial for counts) and the volume x efficiency projection.

projection = expected volume (team volume from the game script x the player's recency-weighted share, redistributed for missing teammates)
             x efficiency (catch rate, yards per catch / carry / attempt, shrunk toward the position average)
             x opponent-vs-position factor (half strength, scaled by games played) x wind.
Variance = a * mean per market (a fitted on last season's walk-forward residuals, config.PROP_DISP).
"""
import math

import numpy as np
from scipy.stats import gamma, nbinom, poisson

import config

YARD_MARKETS = {"pass_yds", "rush_yds", "rec_yds", "pass_rush_yds", "rush_rec_yds"}


def variance(market: str, mu: float, parts: tuple = ()) -> float:
    if market == "pass_rush_yds":
        return config.PROP_DISP["pass_yds"] * parts[0] + config.PROP_DISP["rush_yds"] * parts[1]
    if market == "rush_rec_yds":
        return config.PROP_DISP["rush_yds"] * parts[0] + config.PROP_DISP["rec_yds"] * parts[1]
    return config.PROP_DISP[market] * mu


def p_over(market: str, mu: float, line: float, parts: tuple = ()) -> tuple[float, float]:
    """(P(over), P(push)) for a posted line. Whole-number lines can push; half-point lines cannot."""
    if mu <= 0:
        return 0.0, 0.0
    var = max(variance(market, mu, parts), mu * 1.001 if market not in YARD_MARKETS else mu * 2)
    if market in YARD_MARKETS:
        k, th = mu * mu / var, var / mu
        p_gt = 1 - gamma.cdf(line, k, scale=th)
        if line == int(line):          # yards are integers: P(Y = line) ~ density, split a unit around the line
            pp = gamma.cdf(line + 0.5, k, scale=th) - gamma.cdf(line - 0.5, k, scale=th)
            return float(1 - gamma.cdf(line + 0.5, k, scale=th)), float(pp)
        return float(p_gt), 0.0
    if var <= mu * 1.02:
        dist = poisson(mu)
    else:
        r = mu * mu / (var - mu)
        dist = nbinom(r, r / (r + mu))
    fl = math.floor(line)
    if line == fl:                     # integer line: over = more than the line, push = equal
        return float(1 - dist.cdf(fl)), float(dist.pmf(fl))
    return float(1 - dist.cdf(fl)), 0.0


def shrink(num: float, den: float, prior: float, k: float) -> float:
    return (num + k * prior) / (den + k)


def opp_factor(ratio: float | None, games: int) -> float:
    if ratio is None or not np.isfinite(ratio):
        return 1.0
    return 1 + config.PROP_OPP_STRENGTH * (ratio - 1) * games / (games + 8.0)
