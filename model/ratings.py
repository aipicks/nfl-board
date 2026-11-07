"""Opponent-adjusted team ratings: time-weighted ridge regression of per-play EPA (pass, rush) and pace on
offence-team and defence-team effects. Ratings are in EPA/play above a league-average team (defence: +ve = worse)."""
import numpy as np
import pandas as pd

import config

METRICS = {"pass": "off_epa_pass", "rush": "off_epa_rush", "sr": "off_sr", "plays": "plays"}


def game_flags() -> pd.DataFrame:
    """Per team-game weight multipliers from game_flags.csv (season,week,team,weight,reason). The weight applies to that team's
    OFFENCE row in that game (which also carries the opponent's defence). Edit the file to add your own judgement calls."""
    f = config.ROOT / config.GAME_FLAGS_FILE
    if not f.exists():
        return pd.DataFrame(columns=["season", "week", "team", "flag_w"])
    d = pd.read_csv(f, comment="#")
    return d.rename(columns={"weight": "flag_w"})[["season", "week", "team", "flag_w"]]


def team_games(con) -> pd.DataFrame:
    """One row per team-game with the team's offence metrics, opponent, and a running 'time' index (weeks)."""
    tw = pd.read_sql("select * from team_week", con)
    g = pd.read_sql("select season, week, home, away from games", con)
    a = g.rename(columns={"home": "team", "away": "opp"}).assign(home=1)
    b = g.rename(columns={"away": "team", "home": "opp"}).assign(home=0)
    m = tw.merge(pd.concat([a, b]), on=["season", "week", "team"], how="left")
    # time: seasons are 20 'weeks' apart (18 weeks + ~2 bye/offseason gap handled by decay), so decay is in games-ish units
    from model import qb as QB
    st = QB.pregame_starter_epa(QB.load_qb_games())
    m = m.merge(st, on=["season", "week", "team"], how="left")
    m["qb_epa"] = m.qb_epa.fillna(0.0)
    m = m.merge(game_flags(), on=["season", "week", "team"], how="left")
    m["flag_w"] = pd.to_numeric(m.flag_w, errors="coerce").fillna(1.0)
    base = int(m.season.min())
    m["t"] = (m.season - base) * config.OFFSEASON_WEEKS + m.week
    return m


def fit(tg: pd.DataFrame, as_of_t: float, *, half_life=None, ridge=None) -> dict:
    """Ratings using only rows with t < as_of_t."""
    half_life = half_life or config.RATING_HALF_LIFE
    ridge = ridge if ridge is not None else config.RATING_RIDGE
    d = tg[tg.t < as_of_t].copy()
    for col, default in (("flag_w", 1.0), ("qb_epa", 0.0)):     # optional columns
        if col not in d:
            d[col] = default
    teams = sorted(set(tg.team))
    ix = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    X = np.zeros((len(d), 2 * n))
    X[np.arange(len(d)), d.team.map(ix).values] = 1          # offence effect
    X[np.arange(len(d)), n + d.opp.map(ix).values] = 1       # opponent defence effect
    w = 0.5 ** ((as_of_t - d.t.values) / half_life) * d.flag_w.values
    out = {"teams": teams, "n_games": len(d)}
    for k, col in METRICS.items():
        y = d[col].values
        mu = np.average(y, weights=w)
        Xk, pen = X, ridge * np.ones(2 * n)
        if k == "pass":                       # quarterback quality enters as a covariate, so team ratings exclude the QB
            qm = np.average(d.qb_epa.values, weights=w)
            z = ((d.qb_epa.values - qm) * 10)[:, None]
            Xk = np.hstack([X, z]); pen = np.append(pen, config.QB_RIDGE)
        A = Xk.T @ (Xk * w[:, None]) + np.diag(pen)
        beta = np.linalg.solve(A, Xk.T @ (w * (y - mu)))
        out[k] = {"mu": mu, "off": dict(zip(teams, beta[:n])), "def": dict(zip(teams, beta[n:2 * n]))}
        if k == "pass":
            out[k]["qb_beta"], out[k]["qb_mean"] = float(beta[2 * n] * 10), float(qm)
    # league pass rate on EPA plays is approximated by 'plays' split; use a fixed league value from data
    return out


def project_epa(r: dict, team: str, opp: str, pass_rate: float | None = None, qb_epa: float | None = None):
    """Expected EPA/play, plays and per-component values for `team` on offence vs `opp` defence."""
    pr = pass_rate if pass_rate is not None else config.LEAGUE_PASS_RATE
    ep = r["pass"]["mu"] + r["pass"]["off"][team] + r["pass"]["def"][opp]
    if qb_epa is not None:
        ep += r["pass"]["qb_beta"] * (qb_epa - r["pass"]["qb_mean"])
    er = r["rush"]["mu"] + r["rush"]["off"][team] + r["rush"]["def"][opp]
    plays = r["plays"]["mu"] + r["plays"]["off"][team] + r["plays"]["def"][opp]
    return {"epa_pass": ep, "epa_rush": er, "epa_pp": pr * ep + (1 - pr) * er, "plays": plays,
            "sr": r["sr"]["mu"] + r["sr"]["off"][team] + r["sr"]["def"][opp]}


def league_mu_epa(r: dict, pass_rate: float | None = None) -> float:
    pr = pass_rate if pass_rate is not None else config.LEAGUE_PASS_RATE
    return pr * r["pass"]["mu"] + (1 - pr) * r["rush"]["mu"]
