"""Non-skill injury impact: offensive line, defensive line, linebackers, cornerbacks, safeties, kicker/punter.

loss (points) = INJ_PTS[group] x usual snap share x P(misses)   per player; offence groups lower the team's own scoring, defence groups raise
the opponent's. Group values are the ridge posterior from inj_backtest.py (priors shrunk by 2025-26 walk-forward data), not exact.
QB and skill positions (WR/TE/RB) are handled elsewhere (QB covariate, usage-based skill model).
"""
import numpy as np
import pandas as pd

import config
from adapters import nflverse as nv
from adapters.names import norm_name

GROUP = {"T": "OL", "G": "OL", "C": "OL", "OT": "OL", "OG": "OL", "OL": "OL", "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL", "LB": "LB", "ILB": "LB", "OLB": "LB", "MLB": "LB",
         "CB": "CB", "DB": "CB", "S": "S", "FS": "S", "SS": "S", "K": "ST", "PK": "ST", "P": "ST", "LS": "ST"}
OFFENCE_GROUPS = ("OL", "ST")
DEFENCE_GROUPS = ("DL", "LB", "CB", "S")


def recent_snap_share(season: int) -> dict:
    """normalised name -> average of the player's last 4 snap shares (this season, falling back to last season)."""
    out = {}
    for s in (season - 1, season):                      # later season overwrites
        sn = nv.get("snaps", s)
        sn = sn[sn.game_type == "REG"].copy()
        sn["share"] = sn[["offense_pct", "defense_pct"]].max(axis=1)
        sn = sn.sort_values("week")
        for name, x in sn.groupby("player"):
            out[norm_name(name)] = float(x.share.tail(4).mean())
    return out


def active_ids(season: int) -> set:
    """gsis ids on the 53-man active roster in the latest roster file (status ACT). IR (RES), practice squad (DEV) and cut players are not available."""
    r = nv.get("roster", season)
    r = r[r.week == r.week.max()]
    return set(r[r.status == "ACT"].gsis_id.dropna())


def group_losses(inj: pd.DataFrame, team: str, shares: dict) -> dict:
    """inj: flagged-player frame (name, team, pos, status). Returns {'off': pts, 'def': pts, 'notes': [...]} for one team."""
    off = dfn = 0.0
    notes = []
    f = inj[(inj.team == team) & (inj.status != "healthy")]
    for p in f.itertuples():
        grp = GROUP.get(str(p.pos).strip())
        if grp is None:
            continue
        share = shares.get(norm_name(p.name), 0.5)
        if share < 0.15:
            continue
        miss = 1 - config.PLAY_PROB.get(p.status, 1.0)
        loss = config.INJ_PTS[grp] * share * miss
        if loss < 0.05:
            continue
        if grp in OFFENCE_GROUPS:
            off += loss
        else:
            dfn += loss
        if loss >= 0.2:
            notes.append(f"{p.name} ({p.pos}, {p.status}) {'-' if grp in OFFENCE_GROUPS else '+'}{loss:.1f}")
    return {"off": min(off, config.INJ_CAP_GROUP), "def": min(dfn, config.INJ_CAP_GROUP), "notes": notes}
