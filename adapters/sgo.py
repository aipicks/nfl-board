"""SportsGameOdds adapter. ONE slate-level request per run (never per player); raw JSON cached; five books only.

Flow: usage guard -> GET /events (this week's window) -> cache raw -> parse into odds_snap rows.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

import config
from adapters.http import fetch

# SGO teamID (minus _NFL) -> nflverse abbreviation
TEAM_ABBR = {
    "ARIZONA_CARDINALS": "ARI", "ATLANTA_FALCONS": "ATL", "BALTIMORE_RAVENS": "BAL", "BUFFALO_BILLS": "BUF",
    "CAROLINA_PANTHERS": "CAR", "CHICAGO_BEARS": "CHI", "CINCINNATI_BENGALS": "CIN", "CLEVELAND_BROWNS": "CLE",
    "DALLAS_COWBOYS": "DAL", "DENVER_BRONCOS": "DEN", "DETROIT_LIONS": "DET", "GREEN_BAY_PACKERS": "GB",
    "HOUSTON_TEXANS": "HOU", "INDIANAPOLIS_COLTS": "IND", "JACKSONVILLE_JAGUARS": "JAX", "KANSAS_CITY_CHIEFS": "KC",
    "LAS_VEGAS_RAIDERS": "LV", "LOS_ANGELES_CHARGERS": "LAC", "LOS_ANGELES_RAMS": "LA", "MIAMI_DOLPHINS": "MIA",
    "MINNESOTA_VIKINGS": "MIN", "NEW_ENGLAND_PATRIOTS": "NE", "NEW_ORLEANS_SAINTS": "NO", "NEW_YORK_GIANTS": "NYG",
    "NEW_YORK_JETS": "NYJ", "PHILADELPHIA_EAGLES": "PHI", "PITTSBURGH_STEELERS": "PIT", "SAN_FRANCISCO_49ERS": "SF",
    "SEATTLE_SEAHAWKS": "SEA", "TAMPA_BAY_BUCCANEERS": "TB", "TENNESSEE_TITANS": "TEN", "WASHINGTON_COMMANDERS": "WAS",
}
# SGO statID -> our market name. Core props first; optional ones are kept only if a book posts them.
PROP_STATS = {
    "passing_yards": "pass_yds", "rushing_yards": "rush_yds", "receiving_yards": "rec_yds",
    "receiving_receptions": "receptions", "rushing_attempts": "rush_att",
    # optional (not on every book, lower priority)
    "passing_touchdowns": "pass_td", "passing_completions": "pass_comp", "passing_attempts": "pass_att",
    "passing_interceptions": "pass_int", "passing_longestCompletion": "long_pass", "rushing_longestRush": "long_rush",
    "receiving_longestReception": "long_rec", "passing+rushing_yards": "pass_rush_yds",
    "rushing+receiving_yards": "rush_rec_yds",
}
CORE_PROPS = {"pass_yds", "rush_yds", "rec_yds", "receptions", "rush_att"}
CACHE = config.CACHE / "sgo"


def _key() -> str:
    k = os.environ.get("SGO_API_KEY")
    if not k:
        env = config.ROOT / ".env"
        if env.exists():
            m = re.search(r"^SGO_API_KEY=(\S+)", env.read_text(), re.M)
            k = m.group(1) if m else None
    if not k:
        raise RuntimeError("SGO_API_KEY missing (put it in .env)")
    return k


def usage() -> dict:
    r = requests.get(f"{config.SGO_BASE}/account/usage", headers={"x-api-key": _key()}, timeout=30)
    r.raise_for_status()
    return r.json()["data"]["rateLimits"]["per-month"]


def remaining_entities() -> int:
    u = usage()
    return int(u["max-entities"]) - int(u["current-entities"])


def fetch_slate(start: datetime, end: datetime, expected_events: int, *, force=False, max_age_s=1800):
    """One request for all events in [start, end]. Returns (raw_json_path, status). Falls back to the last cached slate."""
    CACHE.mkdir(parents=True, exist_ok=True)
    latest = CACHE / "slate_latest.json"
    if not force and latest.exists() and time.time() - latest.stat().st_mtime < max_age_s:
        return latest, "cached"
    left = remaining_entities()
    if left < expected_events + 100:
        raise RuntimeError(f"SGO monthly budget low: {left} entities left, need ~{expected_events} (+100 reserve)")
    iso = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    params = {"leagueID": "NFL", "type": "match", "finalized": "false", "limit": 50,
              "startsAfter": iso(start), "startsBefore": iso(end), "bookmakerID": ",".join(config.ALLOWED_BOOKS)}
    path, st = fetch(f"{config.SGO_BASE}/events", latest, headers={"x-api-key": _key()}, params=params, timeout=90)
    if st == "fresh":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (CACHE / f"slate_{stamp}.json").write_bytes(path.read_bytes())   # keep history of raw pulls
    return path, st


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


from adapters.names import norm_name as _norm_name


def match_players(sgo_players: dict, players: pd.DataFrame) -> dict:
    """SGO playerID -> nflverse player_id by normalised name (+team when ambiguous). Unmatched -> 'sgo:<id>'."""
    players = players.assign(key=players.name.fillna("").map(_norm_name))
    out = {}
    for pid, p in sgo_players.items():
        nm = p.get("name") or f"{p.get('firstName', '')} {p.get('lastName', '')}".strip() or pid.rsplit("_", 2)[0].replace("_", " ").title()
        p = {**p, "name": nm}
        team = TEAM_ABBR.get(str(p.get("teamID", "")).removesuffix("_NFL"))
        c = players[players.key == _norm_name(p["name"])]
        if len(c) > 1:
            c = c[c.team == team] if (c.team == team).any() else c
        out[pid] = c.player_id.iloc[0] if len(c) >= 1 and (len(c) == 1 or (c.team == team).sum() == 1) else f"sgo:{pid}"
    return out


def parse(raw_path, snap_ts: str, players: pd.DataFrame, games: pd.DataFrame):
    """Raw SGO JSON -> (odds_snap rows DataFrame, event->game_id map, unmatched player names)."""
    j = json.loads(raw_path.read_text(encoding="utf-8"))
    rows, ev_map, unmatched = [], {}, set()
    for e in j["data"]:
        home = TEAM_ABBR[e["teams"]["home"]["teamID"].removesuffix("_NFL")]
        away = TEAM_ABBR[e["teams"]["away"]["teamID"].removesuffix("_NFL")]
        ko = e["status"]["startsAt"][:10]
        g = games[(games.home == home) & (games.away == away) & (games.kickoff_utc.str[:10].between(
            (pd.Timestamp(ko) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), ko))]
        if g.empty:
            continue
        ev_map[e["eventID"]] = g.game_id.iloc[0]
        pmap = match_players(e.get("players", {}), players)
        for oid, o in e["odds"].items():
            if o["periodID"] != "game" or o.get("cancelled"):
                continue
            bt, stat, ent, side = o["betTypeID"], o["statID"], o["statEntityID"], o["sideID"]
            if ent in ("home", "away", "all"):
                # ml/sp are quoted per team (entity home/away); the game total only on entity "all".
                # Team totals (ou on home/away) are deliberately skipped.
                if stat != "points" or not ((bt in ("ml", "sp") and ent != "all") or (bt == "ou" and ent == "all")):
                    continue
                market, player = {"ml": "moneyline", "sp": "spread", "ou": "total"}[bt], None
            else:
                player = pmap.get(ent)
                if stat == "touchdowns" and bt == "yn" and side == "yes":
                    market = "td_any"
                elif stat in PROP_STATS and bt == "ou":
                    market = PROP_STATS[stat]
                else:
                    continue
                if player and player.startswith("sgo:"):
                    unmatched.add(e["players"].get(ent, {}).get("name") or ent)
            open_price = _num(o.get("openBookOdds"))
            open_line = _num(o.get("openBookSpread") if bt == "sp" else o.get("openBookOverUnder"))
            for book, b in (o.get("byBookmaker") or {}).items():
                if book not in config.ALLOWED_BOOKS or not b.get("available", True):
                    continue
                price = _num(b.get("odds"))
                if price is None:
                    continue
                line = _num(b.get("spread") if bt == "sp" else b.get("overUnder"))
                rows.append((snap_ts, e["eventID"], oid, market, player, side, line, book, int(price),
                             open_price, open_line, 0))
    cols = ["snap_ts", "event_id", "odd_id", "market", "player_id", "side", "line", "book", "price",
            "open_price", "open_line", "is_alt"]
    return pd.DataFrame(rows, columns=cols), ev_map, sorted(unmatched)
