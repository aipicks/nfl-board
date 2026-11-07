"""Game-day forecasts from nflweather.com (server-rendered HTML). Domes / closed roofs are flagged indoor and ignore weather."""
import re

import pandas as pd
from bs4 import BeautifulSoup

import config
from adapters.http import fetch
from adapters.sgo import TEAM_ABBR

URL = "https://www.nflweather.com/"
# visible team label on the page is the nickname ("Giants"); the site writes "Washington" for the Commanders
NICK_TO_ABBR = {k.split("_")[-1].lower(): v for k, v in TEAM_ABBR.items()}
NICK_TO_ABBR["washington"] = "WAS"


def raw(max_age_s=1800):
    path, st = fetch(URL, config.CACHE / "nflweather" / "index.html", max_age_s=max_age_s)
    return path.read_text(encoding="utf-8", errors="ignore"), st


def parse(html: str) -> pd.DataFrame:
    """-> one row per game box: home, away, kickoff_et, temp_f, wind_mph, precip_pct, conditions, indoor, final."""
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for box in soup.select("div.game-box"):
        nicks = [x.get_text(strip=True).lower() for x in box.select(".team-game-box span.fw-bold")]
        if len(nicks) != 2 or not all(n in NICK_TO_ABBR for n in nicks):
            continue
        away, home = (NICK_TO_ABBR[n] for n in nicks)
        text = re.sub(r"\s+", " ", box.get_text(" ", strip=True))
        ko = re.search(r"(\d{2}/\d{2}/\d{2} \d{2}:\d{2} [AP]M)", text)
        img = (box.select_one("img.game-box-weather-image") or {}).get("src", "")
        temp = re.search(r"(-?\d+)\s*\S?\s*F\b", text)
        wind = re.search(r"(\d+)\s*mph", text)
        pct = re.search(r"(\d+)%", text)
        spans = [s.get_text(strip=True) for s in box.select(".game-info span") if s.get_text(strip=True)]
        cond = next((s for s in spans if re.search(r"[A-Za-z]{4}", s) and "mph" not in s and "°" not in s
                     and not re.search(r"\d\s*\S?\s*F$", s) and s not in ("air",) and "_" not in s and s.lower() not in ("sw", "ne", "nw", "se", "n", "s", "e", "w")), "")
        rows.append({"home": home, "away": away,
                     "kickoff_et": pd.to_datetime(ko.group(1), format="%m/%d/%y %I:%M %p") if ko else pd.NaT,
                     "temp_f": float(temp.group(1)) if temp else None, "wind_mph": float(wind.group(1)) if wind else None,
                     "precip_pct": float(pct.group(1)) if pct else 0.0, "conditions": cond,
                     "indoor": int("dome" in img.lower()), "final": "Final" in text})
    return pd.DataFrame(rows)


def to_games(df: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Attach game_id; mark indoor from the schedule's roof (dome/closed) too."""
    m = df.merge(games[["game_id", "home", "away", "roof"]], on=["home", "away"], how="inner")
    m["indoor"] = ((m.indoor == 1) | m.roof.isin(["dome", "closed"])).astype(int)
    ind = m.indoor == 1                          # a dome page can come without numbers: use a neutral indoor reading
    m.loc[ind, "temp_f"] = m.loc[ind, "temp_f"].fillna(72.0)
    m.loc[ind, "wind_mph"] = m.loc[ind, "wind_mph"].fillna(0.0)
    gap = ~ind & (m.temp_f.isna() | m.wind_mph.isna())          # outdoor game with no forecast posted yet (e.g. a neutral-site game): mild, calm placeholder, labelled
    m.loc[gap, "temp_f"] = m.loc[gap, "temp_f"].fillna(55.0)
    m.loc[gap, "wind_mph"] = m.loc[gap, "wind_mph"].fillna(5.0)
    m.loc[gap, "conditions"] = "Forecast not posted yet (placeholder 55F, 5 mph)"
    return m


def store(con, snap_ts: str, df: pd.DataFrame):
    df.assign(snap_ts=snap_ts)[["snap_ts", "game_id", "temp_f", "wind_mph", "precip_pct", "conditions", "indoor"]].to_sql(
        "weather", con, if_exists="append", index=False)
