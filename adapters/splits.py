"""Public betting splits from SportsBettingDime's own JSON feed (the one its public-betting-trends page loads).
betsPercentage = tickets %, stakePercentage = money %. Not behind a login; robots.txt does not exclude /wp-json."""
import json

import pandas as pd

import config
from adapters.http import fetch
from adapters.names import ESPN_TEAM_FIX

URL = "https://www.sportsbettingdime.com/wp-json/adpt/v1/nfl-odds"
PARAMS = {"books": "sr:book:17324", "format": "us"}      # book list only affects the odds fields we ignore


def raw(max_age_s=1800):
    path, st = fetch(URL, config.CACHE / "sbd" / "nfl-odds.json", params=PARAMS, max_age_s=max_age_s)
    return json.loads(path.read_text(encoding="utf-8")), st


def parse(j, games: pd.DataFrame) -> pd.DataFrame:
    """-> rows (game_id, market, side, tickets_pct, money_pct, updated). games: game_id, home, away, kickoff_utc."""
    rows = []
    for g in j["data"]:
        home = ESPN_TEAM_FIX.get(g["competitors"]["home"]["abbreviation"], g["competitors"]["home"]["abbreviation"])
        away = ESPN_TEAM_FIX.get(g["competitors"]["away"]["abbreviation"], g["competitors"]["away"]["abbreviation"])
        day = g["scheduled"][:10]
        m = games[(games.home == home) & (games.away == away) & (games.kickoff_utc.str[:10].between(
            (pd.Timestamp(day) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), day))]
        if m.empty or not g.get("bettingSplits"):
            continue
        for market, sp in g["bettingSplits"].items():
            for side in ("home", "away", "over", "under"):
                if side in sp and isinstance(sp[side], dict):
                    rows.append({"game_id": m.game_id.iloc[0], "market": {"moneyline": "moneyline", "spread": "spread", "total": "total"}[market],
                                 "side": side, "tickets_pct": sp[side]["betsPercentage"], "money_pct": sp[side]["stakePercentage"],
                                 "updated": sp.get("updated")})
    return pd.DataFrame(rows, columns=["game_id", "market", "side", "tickets_pct", "money_pct", "updated"])


def store(con, snap_ts: str, df: pd.DataFrame):
    df.drop(columns=["updated"]).assign(snap_ts=snap_ts)[["snap_ts", "game_id", "market", "side", "tickets_pct", "money_pct"]].to_sql(
        "public_splits", con, if_exists="append", index=False)
