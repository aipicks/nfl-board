"""How many points is each injured position group worth? Walk-forward on 2025 + 2026-to-date.

y = actual margin - our injury-blind base projection (ratings + actual starting QB). Regress y on the difference in 'starter-equivalents
missing' (P(misses) x usual snap share, summed by position group) between the two teams, ridge-shrunk toward priors because 270 games is thin.
Same for totals. `python inj_backtest.py`  ->  coefficients to paste into config.INJ_PTS / INJ_TOTAL_PTS."""
import numpy as np
import pandas as pd

import config
import db
from adapters.names import norm_name
import backtest
from adapters import nflverse as nv
from model import ratings as R

GROUP = {"T": "OL", "G": "OL", "C": "OL", "OT": "OL", "OG": "OL", "OL": "OL", "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL", "LB": "LB", "ILB": "LB", "OLB": "LB", "MLB": "LB",
         "CB": "CB", "DB": "CB", "S": "S", "FS": "S", "SS": "S", "WR": "WR", "TE": "TE", "RB": "RB", "FB": "RB", "K": "ST", "P": "ST", "LS": "ST"}
GROUPS = ["OL", "DL", "LB", "CB", "S", "WR", "TE", "RB", "ST"]
MISS = {"out": 1.0, "doubtful": 0.9, "questionable": 0.25}
PRIOR = {"OL": 0.5, "DL": 0.6, "LB": 0.35, "CB": 0.75, "S": 0.4, "WR": 0.9, "TE": 0.5, "RB": 0.6, "ST": 0.15}   # points of margin per full-time starter missing


def snap_shares(seasons):
    """(gsis_id, order) -> average snap share over that player's previous 4 games."""
    ros = pd.concat([nv.get("roster", s) for s in seasons]).dropna(subset=["pfr_id", "gsis_id"]).drop_duplicates("pfr_id").set_index("pfr_id").gsis_id
    sn = pd.concat([nv.get("snaps", s).assign(season=s) for s in seasons])
    sn = sn[sn.game_type == "REG"].copy()
    sn["gsis"] = sn.pfr_player_id.map(ros)
    sn["share"] = sn[["offense_pct", "defense_pct"]].max(axis=1)
    sn["order"] = sn.season * 100 + sn.week
    sn = sn.sort_values("order")
    out = {}
    for g, x in sn.dropna(subset=["gsis"]).groupby("gsis"):
        out[g] = (x.order.values, x.share.values)
    sn["key"] = sn.player.map(norm_name)                 # fallback: some players (many linemen) are missing from the roster id map
    for g, x in sn.groupby("key"):
        out.setdefault("name:" + g, (x.order.values, x.share.values))
    return out


def prior_share(sh, gsis, order, name=None):
    key = gsis if gsis in sh else ("name:" + norm_name(name) if name is not None and "name:" + norm_name(name) in sh else None)
    if key is None:
        return np.nan
    o, s = sh[key]
    k = np.searchsorted(o, order)          # games strictly before this one
    return float(np.mean(s[max(0, k - 4):k])) if k > 0 else np.nan


def burdens(seasons, sh):
    rows = []
    for s in seasons:
        inj = nv.get("injuries", s).copy()
        inj["team"] = nv.norm_team(inj.team)
        inj["miss"] = inj.report_status.str.lower().map(MISS)
        inj = inj.dropna(subset=["miss", "gsis_id"])
        inj["grp"] = inj.position.str.strip().map(GROUP)
        inj = inj.dropna(subset=["grp"])
        inj["order"] = s * 100 + inj.week
        inj["share"] = [prior_share(sh, g, o, n) for g, o, n in zip(inj.gsis_id, inj.order, inj.full_name)]
        inj = inj[inj.share.notna() & (inj.share >= 0.15)]
        inj["x"] = inj.miss * inj.share
        rows.append(inj.groupby(["season", "week", "team", "grp"]).x.sum().reset_index())
    return pd.concat(rows)


def ridge(D, y, c0, lam):
    A = D.T @ D + lam * np.eye(D.shape[1])
    c = np.linalg.solve(A, D.T @ y + lam * c0)
    res = y - D @ c
    s2 = (res ** 2).sum() / max(1, len(y) - D.shape[1])
    cov = s2 * np.linalg.inv(A) @ (D.T @ D) @ np.linalg.inv(A)
    return c, np.sqrt(np.diag(cov))


if __name__ == "__main__":
    con = db.connect()
    tg = R.team_games(con)
    seasons = [config.LAST_SEASON - 1, config.LAST_SEASON, config.SEASON]
    sh = snap_shares(seasons)
    bd = burdens([config.LAST_SEASON, config.SEASON], sh)
    X = bd.pivot_table(index=["season", "week", "team"], columns="grp", values="x", fill_value=0).reindex(columns=GROUPS, fill_value=0)
    g = pd.read_csv(config.CACHE / "nflverse" / "games.csv")
    g = g[(g.game_type == "REG") & g.home_score.notna() & g.season.isin([config.LAST_SEASON, config.SEASON]) & (g.week >= 3)].copy()
    g["home"], g["away"] = g.home_team.replace({"LAR": "LA"}), g.away_team.replace({"LAR": "LA"})
    g["t"] = (g.season - (config.LAST_SEASON - 1)) * config.OFFSEASON_WEEKS + g.week
    qbe = tg.set_index(["season", "week", "team"]).qb_epa
    cache = {t: R.fit(tg, t) for t in sorted(g.t.unique())}
    rows = []
    for _, x in g.iterrows():
        hfa = config.HFA_NEUTRAL if x.location == "Neutral" else config.HFA
        m, t = backtest.base_projection(cache[x.t], x.home, x.away, config.POINTS_PER_EPA, hfa, qbe.get((x.season, x.week, x.home)), qbe.get((x.season, x.week, x.away)))
        xh = X.loc[(x.season, x.week, x.home)] if (x.season, x.week, x.home) in X.index else pd.Series(0.0, index=GROUPS)
        xa = X.loc[(x.season, x.week, x.away)] if (x.season, x.week, x.away) in X.index else pd.Series(0.0, index=GROUPS)
        rows.append({"y_m": x.result - m, "y_t": x.total - t, **{f"dm_{k}": xa[k] - xh[k] for k in GROUPS}, **{f"st_{k}": xa[k] + xh[k] for k in GROUPS}})
    d = pd.DataFrame(rows)
    print(f"games={len(d)}; mean burden per team-game (starter-equivalents out):", X.mean().round(2).to_dict())
    c0 = np.array([PRIOR[k] for k in GROUPS])
    Dm = d[[f"dm_{k}" for k in GROUPS]].values
    cm, sm = ridge(Dm, d.y_m.values, c0, lam=676.0)
    print("\nMARGIN: points per starter missing  (prior -> ridge posterior +/- se; raw OLS in brackets)")
    raw, _ = ridge(Dm, d.y_m.values, np.zeros(len(GROUPS)), lam=1e-6)
    for k, a, b, se, r_ in zip(GROUPS, c0, cm, sm, raw):
        print(f"  {k:3} {a:+.2f} -> {b:+.2f} +/- {se:.2f}   [{r_:+.2f}]")
    print("   RMSE margin before", round(float(np.sqrt((d.y_m ** 2).mean())), 3), "after", round(float(np.sqrt(((d.y_m - Dm @ cm) ** 2).mean())), 3), "(in-sample)")
    # totals: offence-side groups lower scoring, defence-side groups raise it
    S = d[[f"st_{k}" for k in GROUPS]].values
    sign = np.array([-1 if k in ("OL", "WR", "TE", "RB") else (1 if k in ("DL", "LB", "CB", "S") else 0) for k in GROUPS])
    ct, st_ = ridge(S, d.y_t.values, c0 * sign * 0.5, lam=676.0)
    print("\nTOTAL: points on the game total per starter missing (own side)")
    for k, a, b, se in zip(GROUPS, c0 * sign * 0.5, ct, st_):
        print(f"  {k:3} {a:+.2f} -> {b:+.2f} +/- {se:.2f}")
    print("\nPRIOR_USED = ", {k: round(float(v), 2) for k, v in zip(GROUPS, cm)})
