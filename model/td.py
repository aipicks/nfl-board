"""Anytime-TD model.

lambda (expected TDs in the game) = sum over usage bands of (player's expected touches in that band x league conversion rate of that band)
                                    x team scoring environment x opponent-vs-position factor x P(plays)
P(at least one TD) = 1 - exp(-lambda)           (a Poisson count; other TD types are folded into the band rates)

Usage bands (from play-by-play): targets outside the 20, red-zone targets (6-20), goal-line targets (inside 5), and the same three for
carries. Expected touches are recency-weighted over this season and last, shrunk toward a role prior when a player has few games, and
a missing teammate's usage is redistributed to the players behind him. Every weight is a config prior unless td_backtest.py fitted it.
"""
import json
import math

import numpy as np
import pandas as pd

import config
from adapters import nflverse as nv

BANDS = ["tgt_out", "tgt_rz", "tgt_gl", "car_out", "car_rz", "car_gl"]
POS_RECV = ("WR", "TE", "RB")


def league_conversion(seasons=None) -> dict:
    """TD probability per target / carry in each band, from play-by-play (default: last two seasons)."""
    seasons = seasons or [config.LAST_SEASON, config.SEASON]
    rows = []
    for s in seasons:
        p = nv.get("pbp", s)
        p = p[(p.season_type == "REG") & p.play_type.isin(["pass", "run"])]
        rows.append(p[["play_type", "yardline_100", "touchdown", "pass_touchdown", "rush_touchdown", "two_point_attempt", "sack", "qb_scramble", "receiver_player_id", "rusher_player_id"]])
    p = pd.concat(rows)
    p = p[p.two_point_attempt != 1]
    band = lambda y: np.where(y <= 5, "gl", np.where(y <= 20, "rz", "out"))
    t = p[(p.play_type == "pass") & p.receiver_player_id.notna()]
    c = p[(p.play_type == "run") & p.rusher_player_id.notna() & (p.qb_scramble != 1)]
    out = {}
    for name, d, col in (("tgt", t, "pass_touchdown"), ("car", c, "rush_touchdown")):
        b = band(d.yardline_100.values)
        for k in ("out", "rz", "gl"):
            m = b == k
            out[f"{name}_{k}"] = float(d.loc[m, col].mean())
    return out


def parse_pw(con, seasons) -> pd.DataFrame:
    """Per player-game usage components and TD counts from the player_week table."""
    q = f"select season, week, player_id, team, opp, stats_json, snap_pct from player_week where season in ({','.join(map(str, seasons))})"
    pw = pd.read_sql(q, con)
    js = pw.stats_json.map(json.loads)
    g = lambda k: js.map(lambda d: d.get(k) or 0.0)
    pw["tgt"], pw["car"] = g("targets"), g("carries")
    pw["rz_t"], pw["gl_t"], pw["rz_c"], pw["gl_c"] = g("rz_targets"), g("gl_targets"), g("rz_carries"), g("gl_carries")
    pw["tgt_gl"], pw["tgt_rz"] = pw.gl_t, (pw.rz_t - pw.gl_t).clip(lower=0)
    pw["tgt_out"] = (pw.tgt - pw.rz_t).clip(lower=0)
    pw["car_gl"], pw["car_rz"] = pw.gl_c, (pw.rz_c - pw.gl_c).clip(lower=0)
    pw["car_out"] = (pw.car - pw.rz_c).clip(lower=0)
    pw["td"] = g("rushing_tds") + g("receiving_tds")
    pw["tgt_share"] = js.map(lambda d: d.get("target_share") or 0.0)
    return pw


def usage_profile(pw: pd.DataFrame, as_of: tuple, half_life_games: float = None, prior_weight: float = None) -> pd.DataFrame:
    """Per-player expected usage per game using games strictly before as_of=(season, week). Recency-weighted; a player with few games
    is shrunk toward zero usage (the role prior is applied in lambda via `n_eff`)."""
    hl = half_life_games or config.TD_HALF_LIFE_GAMES
    d = pw[(pw.season < as_of[0]) | ((pw.season == as_of[0]) & (pw.week < as_of[1]))].copy()
    d["order"] = d.season * 100 + d.week
    out = []
    for pid, x in d.groupby("player_id"):
        x = x.sort_values("order")
        age = np.arange(len(x))[::-1]
        w = 0.5 ** (age / hl)
        row = {"player_id": pid, "n_games": len(x), "n_eff": float(w.sum()), "team": x.team.iloc[-1], "td_games": int((x.td > 0).sum()),
               "td_rate_w": float((w * (x.td > 0)).sum() / w.sum()), "tds_per_game_w": float((w * x.td).sum() / w.sum()),
               "snap_pct": float(x.snap_pct.dropna().tail(5).mean()) if x.snap_pct.notna().any() else np.nan,
               "tgt_share": float((w * x.tgt_share).sum() / w.sum()), "last_week": int(x.order.iloc[-1])}
        for b in BANDS:
            row[b] = float((w * x[b]).sum() / w.sum())
        out.append(row)
    return pd.DataFrame(out).set_index("player_id")


def redistribute(prof: pd.DataFrame, pos: pd.Series, missing: dict[str, float], floor_car: float = 1.0) -> pd.DataFrame:
    """missing: player_id -> probability he does NOT play.
    Targets: a missing player's expected targets move to teammates in proportion to their own targets (WR/TE/RB).
    Carries: running-back carries are CONSOLIDATED: the RB group's total carries (red-zone and goal-line too) stay with the group and are
    re-split among the backs who are available, by their usual workload plus a small floor, so the lone healthy back becomes the lead back."""
    p = prof.copy()
    for pid, m in missing.items():
        if pid not in p.index or m <= 0:
            continue
        team = p.at[pid, "team"]
        mates = p[(p.team == team) & (p.index != pid)]
        rec = mates[mates.index.map(lambda i: pos.get(i) in POS_RECV)]
        backs = rec[rec.index.map(lambda i: pos.get(i) == "RB" and missing.get(i, 0) < 1)]
        keep = config.RB_TARGET_KEEP if (pos.get(pid) == "RB" and len(backs)) else 0.0      # pass-catching back's work mostly stays with the remaining backs
        for b in [x for x in BANDS if x.startswith("tgt")]:
            tot = rec[b].sum()
            if tot > 0:
                p.loc[rec.index, b] += m * p.at[pid, b] * (1 - keep) * rec[b] / tot
            if keep and len(backs):
                wb = (backs[b] + 0.1) * (1 - backs.index.map(lambda i: missing.get(i, 0)))
                p.loc[backs.index, b] += m * p.at[pid, b] * keep * wb / wb.sum()
    cb = [x for x in BANDS if x.startswith("car")]
    for team, grp in prof.groupby("team"):
        rbs = [i for i in grp.index if pos.get(i) == "RB"]
        if len(rbs) < 2 or not any(missing.get(i, 0) > 0 for i in rbs):
            continue
        usual = prof.loc[rbs, cb].sum(axis=1)
        w = pd.Series({i: (1 - missing.get(i, 0)) * (usual[i] + floor_car) for i in rbs})
        if w.sum() <= 0:
            continue
        for b in cb:
            total = prof.loc[rbs, b].sum()
            p.loc[rbs, b] = total * w / w.sum()
    return p


def lam(row: pd.Series, conv: dict, env_mult: float = 1.0, opp_mult: float = 1.0, p_play: float = 1.0) -> float:
    base = sum(row[b] * conv[b] for b in BANDS)
    return base * env_mult * opp_mult * p_play


def p_td(l: float) -> float:
    return 1 - math.exp(-l)


def prob_from_row(row, conv, hist_weight, env_mult=1.0, opp_mult=1.0, p_play=1.0, role_prior=0.0) -> tuple[float, float]:
    """Blend usage-based lambda with the player's own TD history (observed TDs per game), shrunk by games played."""
    lu = lam(row, conv, env_mult, opp_mult, p_play)
    n = row["n_eff"]
    lh = (row["tds_per_game_w"] * n + role_prior * config.TD_PRIOR_GAMES) / (n + config.TD_PRIOR_GAMES) * env_mult * opp_mult * p_play
    l = (1 - hist_weight) * lu + hist_weight * lh
    return p_td(l), l


def calibrate(p: float) -> float:
    """Backtest-based compression of high probabilities (reliability table in td_backtest.py)."""
    k = config.TD_CAL_KNEE
    return p if p <= k else k + (p - k) * config.TD_CAL_SLOPE
