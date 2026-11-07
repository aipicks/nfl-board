"""Walk-forward backtest of the anytime-TD model on last season (weeks 5-18): features use only earlier games.
Reports log-loss / Brier for variants and the reliability table, and fits the lambda scale. `python td_backtest.py`"""
import numpy as np, pandas as pd, config, db
from model import td as T

con = db.connect()
pw = T.parse_pw(con, [2024, 2025])
players = pd.read_sql("select player_id, pos from players", con).set_index("player_id").pos
conv = T.league_conversion([2024])
print({k: round(v, 3) for k, v in conv.items()})
g = pd.read_csv(config.CACHE / "nflverse" / "games.csv"); g = g[(g.season == 2025) & (g.game_type == "REG")]
imp = {}
for r in g.itertuples():
    imp[(r.week, r.home_team.replace("LAR", "LA"))] = r.total_line / 2 + r.spread_line / 2
    imp[(r.week, r.away_team.replace("LAR", "LA"))] = r.total_line / 2 - r.spread_line / 2
rows = []
for wk in range(5, 19):
    prof = T.usage_profile(pw, (2025, wk))
    act = pw[(pw.season == 2025) & (pw.week == wk)].set_index("player_id")
    # TDs allowed to receiving / rushing group by defence, before this week
    before = pw[(pw.season < 2025) | ((pw.season == 2025) & (pw.week < wk))]
    before = before.assign(grp=before.player_id.map(players).map(lambda p: "RB" if p == "RB" else ("QB" if p == "QB" else "REC")))
    allowed = before.groupby(["opp", "grp"]).agg(td=("td", "sum"), gm=("week", "size")).reset_index()
    for pid, a in act.iterrows():
        if pid not in prof.index or prof.at[pid, "n_games"] < 3 or players.get(pid) not in ("RB", "WR", "TE"):
            continue
        r = prof.loc[pid]
        if sum(r[b] for b in T.BANDS) < 0.5:
            continue
        env = (imp.get((wk, a.team), 22.5) / 22.5)
        grp = "RB" if players.get(pid) == "RB" else "REC"
        ao = allowed[(allowed.opp == a.opp) & (allowed.grp == grp)]
        la = allowed[allowed.grp == grp]
        oppr = (ao.td.sum() / max(1, ao.gm.sum())) / (la.td.sum() / la.gm.sum()) if len(ao) else 1.0
        n = ao.gm.sum() if len(ao) else 0
        oppr = 1 + (oppr - 1) * n / (n + 40)
        rows.append({"pid": pid, "wk": wk, "y": int(a.td > 0), "env": env, "opp": oppr, "lu": T.lam(r, conv), "lh": r.tds_per_game_w, "n": r.n_eff})
d = pd.DataFrame(rows); print(len(d), 'player-games, TD rate', round(d.y.mean(), 3))
def score(df, gam, hw, so, scale):
    l = ((1 - hw) * df.lu + hw * df.lh) * df.env ** gam * (1 + so * (df.opp - 1)) * scale
    p = 1 - np.exp(-l); p = p.clip(1e-4, 1 - 1e-4)
    return float(-(df.y * np.log(p) + (1 - df.y) * np.log(1 - p)).mean()), float(((p - df.y) ** 2).mean()), float(p.mean())
base = d.y.mean(); print('constant-rate logloss', round(-(base * np.log(base) + (1 - base) * np.log(1 - base)), 4))
res = []
for gam in (0, 0.5, 0.8, 1.2):
    for hw in (0, 0.3, 0.5, 0.7, 1.0):
        for so in (0, 0.5, 1.0):
            # calibrate scale on this variant so comparisons are fair
            sc = min(np.linspace(0.6, 1.6, 21), key=lambda s: score(d, gam, hw, so, s)[0])
            ll, br, pm = score(d, gam, hw, so, sc); res.append((ll, br, gam, hw, so, round(sc, 2), pm))
r = pd.DataFrame(res, columns=["logloss", "brier", "gamma", "hist_w", "opp_s", "scale", "mean_p"]).sort_values("logloss"); print(r.head(8).round(4).to_string(index=False))
b = r.iloc[0]; print("variants: usage only", r[(r.hist_w == 0) & (r.gamma == b.gamma) & (r.opp_s == b.opp_s)].logloss.round(4).tolist(), "hist only", r[(r.hist_w == 1.0) & (r.gamma == b.gamma) & (r.opp_s == b.opp_s)].logloss.round(4).tolist())
l = ((1 - b.hist_w) * d.lu + b.hist_w * d.lh) * d.env ** b.gamma * (1 + b.opp_s * (d.opp - 1)) * b.scale; d["p"] = 1 - np.exp(-l)
d["bin"] = pd.cut(d.p, [0, .08, .12, .16, .2, .25, .3, .4, 1]); print(d.groupby("bin", observed=True).agg(n=("y", "size"), pred=("p", "mean"), actual=("y", "mean")).round(3))
