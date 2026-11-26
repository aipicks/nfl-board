"""Prop model v2 (2026-11-25): market-anchored calibration.

Why: the v1 volume x efficiency model had no skill (12,320 graded props: hit ~48-49% whatever its confidence; log-loss 0.737 vs the
market's 0.690). Testing showed the player's recent history adds almost nothing once the line is known, but the books shade overs:
overs hit 47.4% while the de-vigged market said 50%, rushing overs only ~43%.

Model: P(over) = logistic( a + b * logit(de-vigged market P(over)) + c * (median of his last 8 games - line) / line + market-type terms ),
fitted on every graded prop logged before kickoff (one row per player / market / game, main line). Refit on each build. A side is a
candidate when this probability beats the price's implied chance by EDGE_MIN or more.
Walk-forward check (train on earlier weeks only, bet weeks 8-11): unders at 4+ points of edge +14% on 314 bets, overs +16% on 33.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

import config

MARKETS = ["pass_yds", "rush_yds", "rec_yds", "receptions", "rush_att", "pass_td", "pass_comp", "pass_att", "pass_int", "pass_rush_yds", "rush_rec_yds"]
SER = {"pass_yds": "passing_yards", "rush_yds": "rushing_yards", "rec_yds": "receiving_yards", "receptions": "receptions", "rush_att": "carries", "pass_td": "passing_tds",
       "pass_comp": "completions", "pass_att": "attempts", "pass_int": "passing_interceptions"}
EDGE_MIN, EDGE_FIRM = 0.04, 0.06
C = 0.5


def _logit(p):
    p = np.clip(p, 0.02, 0.98)
    return np.log(p / (1 - p))


def stat_series(st, market):
    if market in SER:
        return st[SER[market]].fillna(0)
    if market == "pass_rush_yds":
        return st.passing_yards.fillna(0) + st.rushing_yards.fillna(0)
    return st.rushing_yards.fillna(0) + st.receiving_yards.fillna(0)


def features(df):
    """df needs market, p_mkt (de-vigged P(over)), med8 (median of last 8 games), line."""
    x = pd.DataFrame({"z_mkt": _logit(df.p_mkt.values), "g_med": ((df.med8 - df.line) / np.maximum(df.line.abs(), 1)).fillna(0).clip(-2, 2).values})
    for m in MARKETS:
        x["m_" + m] = (df.market.values == m).astype(float)
    return x


def training_set(con, stats, before_week=None):
    """One row per graded main line (last pre-kickoff snapshot), with point-in-time med8 from this season's earlier weeks."""
    d = pd.read_sql("SELECT game_id, market, player_id, side, line, book, p_market, actual, logged_ts, kickoff_utc FROM pred_log "
                    "WHERE result IN ('win','loss','push') AND is_parlay_leg=0", con)
    d = d[d.market.isin(MARKETS) & (d.logged_ts < d.kickoff_utc.str.replace("Z", ":00Z")) & d.game_id.str.startswith(str(config.SEASON))]
    d = d.sort_values("logged_ts").drop_duplicates(["game_id", "market", "player_id", "side", "line", "book"], keep="last")
    d["p_over_mkt"] = np.where(d.side == "over", d.p_market, 1 - d.p_market)
    g = d.groupby(["game_id", "market", "player_id", "line"]).agg(p_mkt=("p_over_mkt", "mean"), actual=("actual", "first"), n_books=("book", "nunique")).reset_index()
    g = g.sort_values("n_books").drop_duplicates(["game_id", "market", "player_id"], keep="last")
    g["week"] = g.game_id.str.split("_").str[1].astype(int)
    if before_week is not None:
        g = g[g.week < before_week]
    g = g[g.actual.notna() & (g.actual != g.line)]
    by_pid = {pid: x.sort_values("week") for pid, x in stats.groupby("player_id")}
    med, n = [], []
    for r in g.itertuples():
        x = by_pid.get(r.player_id)
        v = stat_series(x[x.week < r.week], r.market).values[-8:] if x is not None else np.array([])
        med.append(float(np.median(v)) if len(v) else np.nan); n.append(len(v))
    g["med8"], g["n"] = med, n
    g = g[g.n >= 3]
    g["over"] = (g.actual > g.line).astype(int)
    return g


def fit(train):
    m = LogisticRegression(C=C, max_iter=1000)
    m.fit(features(train), train.over)
    return m


def p_over(model, market, p_mkt, med8, line):
    df = pd.DataFrame({"market": [market], "p_mkt": [p_mkt], "med8": [med8], "line": [line]})
    return float(model.predict_proba(features(df))[0, 1])


def implied(price):
    return 100 / (price + 100) if price > 0 else -price / (-price + 100)
