"""Name/team normalisation shared by the adapters."""
import re

import pandas as pd

ESPN_TEAM_FIX = {"WSH": "WAS", "LAR": "LA", "JAC": "JAX"}


def norm_name(n: str) -> str:
    n = re.sub(r"[.'’`-]", "", str(n).lower())
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def attach_player_ids(df: pd.DataFrame, players: pd.DataFrame, name_col="name", team_col="team") -> pd.DataFrame:
    """Add player_id by normalised name (team breaks ties). Unmatched rows get None."""
    p = players.assign(key=players.name.fillna("").map(norm_name))
    by_key = {k: g for k, g in p.groupby("key")}
    ids = []
    for _, r in df.iterrows():
        g = by_key.get(norm_name(r[name_col]))
        if g is None:
            ids.append(None)
        elif len(g) == 1:
            ids.append(g.player_id.iloc[0])
        else:
            t = g[g.team == r[team_col]]
            ids.append(t.player_id.iloc[0] if len(t) == 1 else None)
    return df.assign(player_id=ids)
