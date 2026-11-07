"""Walk-forward backtest of the base game model (ratings only) on last season + this season to date.
Each game is projected using ONLY earlier games. Compares model vs the closing market. `python backtest.py`"""
import itertools

import numpy as np
import pandas as pd

import config
import db
from model import ratings as R


def base_projection(r, home, away, B, hfa, qb_h=None, qb_a=None):
    h, a = R.project_epa(r, home, away, qb_epa=qb_h), R.project_epa(r, away, home, qb_epa=qb_a)
    mu, lg_plays = R.league_mu_epa(r), r["plays"]["mu"]
    pts = lambda p: config.LEAGUE_PTS_PER_TEAM + B * (p["plays"] * p["epa_pp"] - lg_plays * mu)
    ph, pa = pts(h), pts(a)
    return ph - pa + hfa, ph + pa


def run(con=None, seasons=None, min_week=3, half_lives=(14,), ridges=(6.0,), Bs=(1.0,), hfas=(config.HFA,), verbose=True):
    con = con or db.connect()
    tg = R.team_games(con)
    g = pd.read_csv(config.CACHE / "nflverse" / "games.csv")
    g = g[(g.game_type == "REG") & g.home_score.notna()]
    g = g.assign(home=g.home_team.replace({"LAR": "LA"}), away=g.away_team.replace({"LAR": "LA"}))
    base = int(tg.season.min())
    seasons = seasons or [config.LAST_SEASON, config.SEASON]
    g = g[g.season.isin(seasons) & (g.week >= min_week)].copy()
    g["t"] = (g.season - base) * config.OFFSEASON_WEEKS + g.week
    res = []
    for hl, rg in itertools.product(half_lives, ridges):
        cache = {t: R.fit(tg, t, half_life=hl, ridge=rg) for t in sorted(g.t.unique())}
        for B, hfa in itertools.product(Bs, hfas):
            pm, pt = [], []
            for _, x in g.iterrows():
                m, t_ = base_projection(cache[x.t], x.home, x.away, B, hfa)
                pm.append(m); pt.append(t_)
            e_m = g.result.values - np.array(pm)
            e_t = g.total.values - np.array(pt)
            res.append({"half_life": hl, "ridge": rg, "B": B, "hfa": hfa, "rmse_margin": np.sqrt((e_m ** 2).mean()),
                        "bias_margin": e_m.mean(), "rmse_total": np.sqrt((e_t ** 2).mean()), "bias_total": e_t.mean(), "n": len(g)})
    out = pd.DataFrame(res)
    mk_m = np.sqrt(((g.result - g.spread_line) ** 2).mean())
    mk_t = np.sqrt(((g.total - g.total_line) ** 2).mean())
    if verbose:
        print(f"games={len(g)}  MARKET rmse margin={mk_m:.2f} total={mk_t:.2f}")
        print(out.sort_values("rmse_margin").round(3).head(12).to_string(index=False))
    return out, mk_m, mk_t, g


if __name__ == "__main__":
    run(half_lives=(8, 14, 24), ridges=(3.0, 6.0, 12.0), Bs=(0.8, 1.0, 1.3), hfas=(1.5,))
