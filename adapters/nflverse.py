"""nflverse release files (play-by-play w/ EPA, weekly player stats, snaps, rosters, depth charts, injuries, schedule)."""
import pandas as pd
import config
from adapters.http import fetch

BASE = "https://github.com/nflverse/nflverse-data/releases/download"
DIR = config.CACHE / "nflverse"

# nflverse is not fully consistent on franchise codes; normalise to the schedule file's codes.
TEAM_FIX = {"LAR": "LA", "STL": "LA", "SD": "LAC", "OAK": "LV", "LVR": "LV", "WSH": "WAS", "ARZ": "ARI",
            "BLT": "BAL", "CLV": "CLE", "HST": "HOU", "JAC": "JAX", "SL": "LA"}
TEAMS32 = {"ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX",
           "KC", "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"}

FILES = {
    "pbp": "pbp/play_by_play_{s}.parquet",
    "stats": "stats_player/stats_player_week_{s}.parquet",
    "snaps": "snap_counts/snap_counts_{s}.parquet",
    "depth": "depth_charts/depth_charts_{s}.parquet",
    "injuries": "injuries/injuries_{s}.parquet",
    "roster": "rosters/roster_{s}.parquet",
}
status: dict[str, str] = {}   # filename -> fresh|cached|stale (shown on the page as data age)


def norm_team(s: pd.Series) -> pd.Series:
    return s.replace(TEAM_FIX)


def get(kind: str, season: int, max_age_s=6 * 3600) -> pd.DataFrame:
    rel = FILES[kind].format(s=season)
    path, st = fetch(f"{BASE}/{rel}", DIR / rel.split("/")[-1], max_age_s=max_age_s)
    status[path.name] = st
    return pd.read_parquet(path)


def schedule(max_age_s=6 * 3600) -> pd.DataFrame:
    path, st = fetch(f"{BASE}/schedules/games.csv", DIR / "games.csv", max_age_s=max_age_s)
    status[path.name] = st
    g = pd.read_csv(path)
    g["home_team"], g["away_team"] = norm_team(g.home_team), norm_team(g.away_team)
    return g[g.game_type == "REG"].copy()
