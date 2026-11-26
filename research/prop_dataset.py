"""Point-in-time test set for the NFL prop model rebuild (2026-11-25).

One row per (game, player, market, line) from pred_log's last pre-kickoff snapshot: the market's de-vigged P(over) averaged across
books, the old model's P(over), the result, and features from this season's weekly box scores in weeks BEFORE the game only.
Writes research/prop_dataset.parquet.  Usage: python research/prop_dataset.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

import config
import db
from adapters import nflverse as nv

PROP_MKTS = ["pass_yds", "rush_yds", "rec_yds", "receptions", "rush_att", "pass_td", "pass_comp", "pass_att", "pass_int", "pass_rush_yds", "rush_rec_yds"]
SER = {"pass_yds": "passing_yards", "rush_yds": "rushing_yards", "rec_yds": "receiving_yards", "receptions": "receptions", "rush_att": "carries", "pass_td": "passing_tds",
       "pass_comp": "completions", "pass_att": "attempts", "pass_int": "passing_interceptions"}


def stat_series(st, market):
    if market in SER:
        return st[SER[market]].fillna(0)
    if market == "pass_rush_yds":
        return st.passing_yards.fillna(0) + st.rushing_yards.fillna(0)
    return st.rushing_yards.fillna(0) + st.receiving_yards.fillna(0)


def main():
    con = db.connect()
    d = pd.read_sql("SELECT * FROM pred_log WHERE result IN ('win','loss','push') AND is_parlay_leg=0", con)
    d = d[d.market.isin(PROP_MKTS) & (d.logged_ts < d.kickoff_utc.str.replace("Z", ":00Z"))].sort_values("logged_ts")
    d = d.drop_duplicates(["game_id", "market", "player_id", "side", "line", "book"], keep="last")
    d["p_over_mkt"] = np.where(d.side == "over", d.p_market, 1 - d.p_market)
    d["p_over_model"] = np.where(d.side == "over", d.p_model, 1 - d.p_model)
    g = d.groupby(["game_id", "market", "player_id", "line"]).agg(p_mkt=("p_over_mkt", "mean"), p_old=("p_over_model", "mean"), actual=("actual", "first"),
                                                                 n_books=("book", "nunique"), kickoff=("kickoff_utc", "first"), desc=("desc", "first")).reset_index()
    g["week"] = g.game_id.str.split("_").str[1].astype(int)
    g = g[g.game_id.str.startswith(str(config.SEASON))]
    stats = nv.get("stats", config.SEASON)
    stats = stats[stats.season_type == "REG"]
    team_col = "recent_team" if "recent_team" in stats.columns else "team"
    feats = []
    for r in g.itertuples():
        st = stats[(stats.player_id == r.player_id) & (stats.week < r.week)].sort_values("week")
        v = stat_series(st, r.market).values.astype(float)
        f = {"n": len(v)}
        if len(v):
            l5 = v[-5:]
            f.update(mean=v.mean(), med=np.median(v), last=v[-1], mean5=l5.mean(), med5=np.median(l5), sd=v.std() if len(v) > 1 else np.nan,
                     hit=np.mean(v > r.line), hit5=np.mean(l5 > r.line), mx=v.max(), mn=v.min())
            # volume context for receivers / backs / passers
            f["tgt5"] = st.targets.fillna(0).values[-5:].mean() if "targets" in st else np.nan
            f["car5"] = st.carries.fillna(0).values[-5:].mean() if "carries" in st else np.nan
            f["att5"] = st.attempts.fillna(0).values[-5:].mean() if "attempts" in st else np.nan
            f["tgt_trend"] = (st.targets.fillna(0).values[-3:].mean() - st.targets.fillna(0).values.mean()) if "targets" in st else np.nan
        feats.append(f)
    out = pd.concat([g.reset_index(drop=True), pd.DataFrame(feats)], axis=1)
    out = out[out.actual.notna() & (out.actual != out.line)]
    out["over"] = (out.actual > out.line).astype(int)
    out.to_parquet(pathlib.Path(__file__).parent / "prop_dataset.parquet")
    print(len(out), "rows; weeks", sorted(out.week.unique()), "; over rate", round(out.over.mean(), 3), "; mean p_mkt", round(out.p_mkt.mean(), 3))
    print(out.market.value_counts().to_string())


if __name__ == "__main__":
    main()
