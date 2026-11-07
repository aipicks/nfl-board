"""Odds math: American <-> probability, de-vig, EV, labels, key-number line movement. Pure functions, unit-tested."""
import config

KEY_NUMBERS = (3, 7)


def to_decimal(american: float) -> float:
    return 1 + american / 100 if american > 0 else 1 + 100 / -american


def to_prob(american: float) -> float:
    """Raw implied probability (includes the book's margin)."""
    return 100 / (american + 100) if american > 0 else -american / (-american + 100)


def to_american(p: float) -> int:
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def devig_pair(american_a: float, american_b: float) -> tuple[float, float]:
    """Proportional de-vig of a two-way market. Returns fair (p_a, p_b) summing to 1."""
    pa, pb = to_prob(american_a), to_prob(american_b)
    s = pa + pb
    return pa / s, pb / s


def devig_single(american: float, hold: float) -> float:
    """One-sided markets (anytime TD has no 'No' price). Divide by an ASSUMED overround (config prior)."""
    return min(to_prob(american) / (1 + hold), 0.999)


def ev(p_win: float, american: float, p_push: float = 0.0) -> float:
    """EV per 1 unit staked = p*payout - (1-p-push); a push refunds the stake."""
    payout = to_decimal(american) - 1
    return p_win * payout - (1 - p_win - p_push)


def label(ev_value: float) -> str:
    if ev_value >= config.BET_EV:
        return "BET"
    if ev_value >= config.LEAN_EV:
        return "LEAN"
    return "PASS"


def blend(p_model: float, p_market: float, w_model: float) -> float:
    """Logit-space blend; w_model=0.5 is 50/50."""
    import math
    eps = 1e-6
    lg = lambda p: math.log(max(min(p, 1 - eps), eps) / (1 - max(min(p, 1 - eps), eps)))
    z = w_model * lg(p_model) + (1 - w_model) * lg(p_market)
    return 1 / (1 + math.exp(-z))


def key_numbers_crossed(open_line: float, cur_line: float, keys=KEY_NUMBERS) -> list[int]:
    """Key numbers a spread/total moved across (or onto/off of) between open and current, on the signed number line.
    Spreads only; totals use their own key set at the call site."""
    if open_line is None or cur_line is None or open_line == cur_line:
        return []
    lo, hi = sorted((open_line, cur_line))
    out = []
    for k in keys:
        for kk in (k, -k):
            if lo <= kk <= hi and kk not in out:
                out.append(kk)
    return sorted(out, key=abs)
