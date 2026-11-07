"""Turns raw odds_snap rows into per-outcome views: reference line, best price, de-vigged consensus, line movement."""
import pandas as pd
import config
from model.devig import devig_pair, devig_single, key_numbers_crossed, to_prob

# which two sides pair up for each market
PAIRS = {"moneyline": ("home", "away"), "spread": ("home", "away"), "total": ("over", "under")}
NO_LINE = -9999.0
TOTAL_KEYS = (37, 41, 43, 44, 47, 51)     # common NFL total key numbers (informational only)


def latest(con) -> pd.DataFrame:
    """Rows from the most recent snapshot of each event."""
    return pd.read_sql(
        "select o.* from odds_snap o join (select event_id, max(snap_ts) t from odds_snap group by event_id) m "
        "on o.event_id=m.event_id and o.snap_ts=m.t", con)


def wide(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (event, market, player, book): line + both sides' prices.
    Spread/total lines are stored from the side's own perspective; we normalise to the first side (home / over)."""
    d = df.copy()
    d["player_id"] = d.player_id.fillna("")
    first = d.side.isin(["home", "over", "yes"])
    d["line_n"] = d.line.where(~(~first & (d.market == "spread")), -d.line).fillna(NO_LINE)
    d["slot"] = d.side.map({"home": "a", "over": "a", "yes": "a", "away": "b", "under": "b"})
    w = d.pivot_table(index=["event_id", "market", "player_id", "book", "line_n"], columns="slot", values="price",
                      aggfunc="first").reset_index()
    for c in ("a", "b"):
        if c not in w:
            w[c] = None
    w = w.rename(columns={"a": "price_a", "b": "price_b", "line_n": "line"})
    w.loc[w.line == NO_LINE, "line"] = float("nan")
    return w


def consensus(w: pd.DataFrame, ref_book: str = config.REFERENCE_BOOK, td_hold: float = 0.0, line=None):
    """For ONE outcome (event, market, player): fair prob of side A (home/over/yes), reference line and best prices.
    Returns None if nothing usable. Uses only books quoting the reference line so the pair is comparable."""
    if w.empty:
        return None
    ref = w[w.book == ref_book]
    ref_line = line if line is not None else (ref.line.iloc[0] if not ref.empty else w.line.mode().iloc[0])
    same = w[(w.line == ref_line) | w.line.isna()]
    fair = []
    for _, r in same.iterrows():
        if pd.notna(r.price_a) and pd.notna(r.price_b):
            fair.append(devig_pair(r.price_a, r.price_b)[0])
        elif pd.notna(r.price_a) and td_hold:
            fair.append(devig_single(r.price_a, td_hold))
    if not fair:
        return None
    pick = lambda col: (lambda x: None if x.empty else x.idxmax())(same[col].dropna())
    ia, ib = pick("price_a"), pick("price_b")
    ln = lambda i: float(same.loc[i, "line"]) if pd.notna(same.loc[i, "line"]) else None
    return {"line": None if pd.isna(ref_line) else float(ref_line), "p_a": sum(fair) / len(fair), "n_books": len(fair),
            "ref_price_a": None if ref.empty else ref.price_a.iloc[0], "ref_price_b": None if ref.empty else ref.price_b.iloc[0],
            "best_a": None if ia is None else (same.loc[ia, "book"], ln(ia), int(same.loc[ia, "price_a"])),
            "best_b": None if ib is None else (same.loc[ib, "book"], ln(ib), int(same.loc[ib, "price_b"]))}


def all_lines(w: pd.DataFrame, td_hold: float = 0.0) -> list[dict]:
    """Consensus at EVERY line quoted (books differ: FD 1.5, others 2.5). Each book's price is evaluated at its own line,
    with the market probability taken from the books quoting that same line."""
    lines = w.line.dropna().unique() if w.line.notna().any() else [None]
    out = []
    for ln in sorted(lines):
        c = consensus(w, td_hold=td_hold, line=ln)
        if c:
            out.append(c)
    return out


def movement(df: pd.DataFrame, event_id: str, market: str):
    """Opening vs current (reference book) line and key numbers crossed. Spread is from the HOME team's view."""
    d = df[(df.event_id == event_id) & (df.market == market) & (df.side.isin(["home", "over"]))]
    if d.empty:
        return None
    ref = d[d.book == config.REFERENCE_BOOK]
    cur = (ref if not ref.empty else d).line.iloc[0]
    op = d.open_line.dropna()
    op = op.iloc[0] if len(op) else None
    keys = key_numbers_crossed(op, cur) if market == "spread" else (
        [k for k in TOTAL_KEYS if op is not None and min(op, cur) <= k <= max(op, cur)] if op is not None and op != cur else [])
    moved = None if op is None else round(float(cur) - float(op), 2)
    lim = 5 if market == "spread" else 6
    # SBD reports the same open lines as SGO, so big moves are real market moves; flagged only so the page can highlight them
    return {"open": op, "current": float(cur), "moved": moved, "keys": keys, "big_move": moved is not None and abs(moved) > lim}
