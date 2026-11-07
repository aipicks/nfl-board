"""Public-betting signal: tickets % vs money % per side. Small, capped; NOT a fade-the-public rule."""
import config


def split_signal(tickets_pct: float, money_pct: float) -> tuple[str, float]:
    """('sharp' | 'public' | 'neutral', money - tickets) for ONE side.
    Money well above tickets = sharp-looking; heavy tickets with light money = public."""
    diff = money_pct - tickets_pct
    if diff >= config.PUBLIC_DIFF_MIN:
        return "sharp", diff
    if diff <= -config.PUBLIC_DIFF_MIN:
        return "public", diff
    return "neutral", diff


def capped_adjustment(diff: float, cap: float) -> float:
    """Points to move a projection TOWARD the side with money > tickets. Linear in the gap, hard-capped at +/-cap."""
    scale = max(-1.0, min(1.0, diff / config.PUBLIC_FULL_DIFF))
    return cap * scale
