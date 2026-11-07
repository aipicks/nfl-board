"""Quarterback adjustment: expected starter's shrunk EPA/dropback vs the QB mix that produced the team's rating window."""
import pandas as pd

import config
from adapters import nflverse as nv


def load_qb_games() -> pd.DataFrame:
    """One row per QB-game: passer id/name/team, t (rating time axis), dropbacks, EPA sum."""
    rows = []
    for s in (config.LAST_SEASON - 1, config.LAST_SEASON, config.SEASON):
        p = nv.get("pbp", s)
        p = p[(p.season_type == "REG") & (p.qb_dropback == 1) & p.epa.notna() & p.passer_player_id.notna()]
        g = p.groupby(["passer_player_id", "week", "posteam"]).agg(name=("passer_player_name", "first"), db=("epa", "size"), epa=("epa", "sum")).reset_index()
        g["season"] = s
        rows.append(g)
    q = pd.concat(rows).rename(columns={"passer_player_id": "player_id", "posteam": "team"})
    q["team"] = nv.norm_team(q.team)
    q["t"] = (q.season - (config.LAST_SEASON - 1)) * config.OFFSEASON_WEEKS + q.week
    return q


def shrunk_epa(qg: pd.DataFrame) -> dict:
    """player_id -> EPA/dropback shrunk toward a prior. Experienced QBs shrink toward the league mean; QBs with little
    NFL data in our window shrink toward replacement level (a backup is usually worse than the average starter)."""
    lg = qg.epa.sum() / qg.db.sum()
    a = qg.groupby("player_id").agg(db=("db", "sum"), epa=("epa", "sum"))
    k = config.QB_SHRINK_DROPBACKS
    exp = (a.db / config.QB_EXPERIENCE_DROPBACKS).clip(upper=1.0)
    prior = config.QB_REPLACEMENT_EPA + (lg - config.QB_REPLACEMENT_EPA) * exp
    return ((a.epa + k * prior) / (a.db + k)).to_dict()


def rated_mix(qg: pd.DataFrame, shr: dict, team: str, as_of_t: float) -> float:
    """Dropback- and recency-weighted EPA/dropback of the QBs behind this team's rating window."""
    d = qg[(qg.team == team) & (qg.t < as_of_t)]
    if d.empty:
        return config.QB_REPLACEMENT_EPA
    w = d.db * 0.5 ** ((as_of_t - d.t) / config.RATING_HALF_LIFE)
    return float((w * d.player_id.map(shr)).sum() / w.sum())


def qb_adjustment(qg, shr, depth, inj_status: dict, team: str, as_of_t: float, dropbacks: float):
    """Points for `team`'s offence from who is expected under centre. Returns (points, note)."""
    qbs = depth[(depth.team == team) & (depth.pos_abb == "QB")].sort_values("pos_rank")
    if qbs.empty:
        return 0.0, ""
    ids = list(qbs.gsis_id)[:3]
    p_play = [config.PLAY_PROB.get(inj_status.get(i, "healthy"), 1.0) for i in ids]
    # QB1 plays with p1; otherwise QB2 (if QB2 also flagged, fall through to QB3 / replacement)
    probs, left = [], 1.0
    for p in p_play:
        probs.append(left * p)
        left *= (1 - p)
    probs.append(left)                                     # nobody -> replacement-level
    epas = [shr.get(i, config.QB_REPLACEMENT_EPA) for i in ids] + [config.QB_REPLACEMENT_EPA]
    exp_epa = sum(p * e for p, e in zip(probs, epas))
    base = rated_mix(qg, shr, team, as_of_t)
    pts = (exp_epa - base) * dropbacks * config.POINTS_PER_EPA * config.QB_ADJ_SCALE
    note = f"QB {qbs.player_name.iloc[0]} ({inj_status.get(ids[0], 'healthy')}): exp EPA/db {exp_epa:+.2f} vs rated {base:+.2f}"
    return pts, note


def expected_qb_epa(shr: dict, depth, inj_status: dict, team: str):
    """Expected EPA/dropback of whoever is under centre, mixing QB1/QB2/QB3 by P(plays). Returns (epa, note)."""
    qbs = depth[(depth.team == team) & (depth.pos_abb == "QB")].sort_values("pos_rank")
    if qbs.empty:
        return None, ""
    ids = list(qbs.gsis_id)[:3]
    probs, left = [], 1.0
    for i in ids:
        p = config.PLAY_PROB.get(inj_status.get(i, "healthy"), 1.0)
        probs.append(left * p)
        left *= (1 - p)
    probs.append(left)
    epas = [shr.get(i, config.QB_REPLACEMENT_EPA) for i in ids] + [config.QB_REPLACEMENT_EPA]
    exp = sum(p * e for p, e in zip(probs, epas))
    return exp, f"QB {qbs.player_name.iloc[0]} ({inj_status.get(ids[0], 'healthy')}): expected EPA/db {exp:+.2f}"


def pregame_starter_epa(qg: pd.DataFrame) -> pd.DataFrame:
    """For each team-game: the QB with most dropbacks and his shrunk EPA/db using ONLY earlier games (no leakage)."""
    st = qg.sort_values("db").groupby(["season", "week", "team"]).tail(1)[["season", "week", "team", "player_id", "t"]]
    out = []
    for t, grp in st.groupby("t"):
        shr = shrunk_epa(qg[qg.t < t]) if (qg.t < t).any() else {}
        out.append(grp.assign(qb_epa=grp.player_id.map(shr).fillna(config.QB_REPLACEMENT_EPA)))   # unseen QB = replacement level
    return pd.concat(out)[["season", "week", "team", "player_id", "qb_epa"]]
