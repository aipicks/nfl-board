"""Full single-game deep dive (weather, team metrics with league ranks, coverage / pass-rush proxies, position matchups,
players, props, history, dynamics, injuries, our projection). `python deep_dive.py SEA DEN` prints a summary; build_board
embeds build(game_id) in the board's Deep Dive tab."""
import json
import math
import re
import sys

import numpy as np
import pandas as pd
import requests
from scipy.stats import norm

import config
import db
from adapters import injuries as inj_ad, nflverse as nv
from adapters.http import fetch
from model import dist, odds_view as ov
from model.devig import blend, ev as ev_fn, label
import inj_history as IH
import deep_extra as X
import deep_more as M
import standouts as SO

C = config.CACHE / "nflverse"
STADIUM = {  # lat, lon, altitude ft, default roof
    "ARI": (33.5276, -112.2626, 1070, "closed"), "ATL": (33.7554, -84.4009, 1050, "closed"), "BAL": (39.2780, -76.6227, 40, "open"),
    "BUF": (42.7738, -78.7870, 600, "open"), "CAR": (35.2258, -80.8528, 750, "open"), "CHI": (41.8623, -87.6167, 595, "open"),
    "CIN": (39.0955, -84.5161, 490, "open"), "CLE": (41.5061, -81.6995, 580, "open"), "DAL": (32.7473, -97.0945, 600, "closed"),
    "DEN": (39.7439, -105.0201, 5280, "open"), "DET": (42.3400, -83.0456, 600, "dome"), "GB": (44.5013, -88.0622, 640, "open"),
    "HOU": (29.6847, -95.4107, 40, "closed"), "IND": (39.7601, -86.1639, 715, "closed"), "JAX": (30.3239, -81.6373, 15, "open"),
    "KC": (39.0489, -94.4839, 800, "open"), "LV": (36.0909, -115.1833, 2000, "dome"), "LAC": (33.9535, -118.3392, 100, "dome"),
    "LA": (33.9535, -118.3392, 100, "dome"), "MIA": (25.9580, -80.2389, 10, "open"), "MIN": (44.9738, -93.2575, 830, "dome"),
    "NE": (42.0909, -71.2643, 250, "open"), "NO": (29.9511, -90.0812, 5, "dome"), "NYG": (40.8135, -74.0745, 10, "open"),
    "NYJ": (40.8135, -74.0745, 10, "open"), "PHI": (39.9008, -75.1675, 40, "open"), "PIT": (40.4468, -80.0158, 730, "open"),
    "SEA": (47.5952, -122.3316, 14, "open"), "SF": (37.4033, -121.9694, 20, "open"), "TB": (27.9759, -82.5033, 10, "open"),
    "TEN": (36.1665, -86.7713, 400, "open"), "WAS": (38.9076, -76.8645, 150, "open")}
# metric -> (label, higher_is_better_for_the_unit_that_has_the_ball, fmt)
OFF_M = {"epa_pass": ("Pass EPA/dropback", True, "{:+.3f}"), "epa_rush": ("Rush EPA/play", True, "{:+.3f}"), "sr": ("Success rate", True, "{:.1%}"),
         "sr_pass": ("Pass success rate", True, "{:.1%}"), "sr_rush": ("Rush success rate", True, "{:.1%}"),
         "plays_pg": ("Plays per game", True, "{:.1f}"), "neutral_pass": ("Neutral-situation pass rate", None, "{:.1%}"),
         "expl_pass": ("Explosive pass (20+) rate", True, "{:.1%}"), "expl_rush": ("Explosive run (10+) rate", True, "{:.1%}"),
         "ypa": ("Yards per attempt", True, "{:.2f}"), "comp_pct": ("Completion %", True, "{:.1%}"), "cpoe": ("Accuracy: completion % above expected", True, "{:+.1f}"),
         "air_pa": ("Air yards per attempt", None, "{:.1f}"), "yac_pc": ("YAC per completion", True, "{:.1f}"),
         "sack_rate": ("Sack rate taken", False, "{:.1%}"), "qbhit_rate": ("QB hit rate taken", False, "{:.1%}"),
         "int_rate": ("Interception rate", False, "{:.1%}"), "rush_ypc": ("Yards per carry", True, "{:.2f}"),
         "stuff_rate": ("Runs stuffed (0 or less)", False, "{:.1%}"), "third": ("3rd-down conversion", True, "{:.1%}"),
         "ppd": ("Points per drive", True, "{:.2f}"), "drives_pg": ("Drives per game", None, "{:.1f}"),
         "rz_td": ("Red-zone TD %", True, "{:.1%}"), "rz_trips": ("Red-zone trips per game", True, "{:.1f}"),
         "to_pg": ("Turnovers per game", False, "{:.2f}"), "pen_pg": ("Penalties per game", False, "{:.1f}"), "pts_pg": ("Points per game", True, "{:.1f}")}
# same keys read from the defensive side: "better" flips
DEF_BETTER = {k: (None if v[1] is None else (not v[1])) for k, v in OFF_M.items()}
DEF_BETTER.update({"sack_rate": True, "qbhit_rate": True, "int_rate": True, "to_pg": True, "pen_pg": False})
DEF_LABEL = {"sack_rate": "Sack rate (pass rush)", "qbhit_rate": "QB hit rate (pass rush)", "int_rate": "Interception rate (coverage)", "to_pg": "Takeaways per game",
             "epa_pass": "Pass EPA allowed/dropback", "epa_rush": "Rush EPA allowed/play", "sr": "Success rate allowed", "sr_pass": "Pass success rate allowed",
             "sr_rush": "Rush success rate allowed", "plays_pg": "Plays faced per game", "expl_pass": "Explosive passes allowed", "expl_rush": "Explosive runs allowed",
             "ypa": "Yards per attempt allowed", "comp_pct": "Completion % allowed", "cpoe": "Accuracy allowed: completion % above expected", "air_pa": "Air yards per attempt allowed",
             "yac_pc": "YAC per completion allowed", "rush_ypc": "Yards per carry allowed", "stuff_rate": "Runs stuffed (defence)", "third": "3rd-down conv. allowed",
             "ppd": "Points per drive allowed", "rz_td": "Red-zone TD % allowed", "rz_trips": "Red-zone trips allowed per game", "pts_pg": "Points allowed per game",
             "drives_pg": "Opponent drives per game", "neutral_pass": "Opponent neutral pass rate", "pen_pg": "Penalties per game"}


_PBP, _RK, _PA = {}, {}, {}


def _pbp(season):
    if season not in _PBP:
        p = nv.get("pbp", season)
        _PBP[season] = p[p.season_type == "REG"].copy()
    return _PBP[season].copy()


def team_metrics(season: int, side: str) -> pd.DataFrame:
    """One row per team for the given season. side='off' (team has the ball) or 'def' (team defends)."""
    p = _pbp(season)
    k = "posteam" if side == "off" else "defteam"
    p["team"] = nv.norm_team(p[k])
    ok = p.epa.notna() & ((p["pass"] == 1) | (p.rush == 1)) & (p.qb_kneel != 1) & (p.qb_spike != 1) & p.team.notna()
    x = p[ok]
    g = x.groupby("team")
    games = g.game_id.nunique()
    db_ = x[x["pass"] == 1]
    att = x[(x.pass_attempt == 1)]
    comp = att[att.complete_pass == 1]
    ru = x[(x.rush == 1) & (x.qb_scramble != 1)]
    nz = x[(x.score_differential.abs() <= 7) & x.qtr.isin([1, 2, 3])]
    d = pd.DataFrame({"games": games})
    d["plays_pg"] = g.size() / games
    d["epa_pass"] = db_.groupby("team").epa.mean(); d["epa_rush"] = x[x.rush == 1].groupby("team").epa.mean()
    d["sr"] = g.success.mean(); d["sr_pass"] = db_.groupby("team").success.mean(); d["sr_rush"] = x[x.rush == 1].groupby("team").success.mean()
    d["neutral_pass"] = nz.groupby("team")["pass"].mean()
    d["expl_pass"] = db_.assign(e=(db_.yards_gained >= 20)).groupby("team").e.mean()
    d["expl_rush"] = ru.assign(e=(ru.yards_gained >= 10)).groupby("team").e.mean()
    d["ypa"] = att.groupby("team").yards_gained.mean(); d["comp_pct"] = att.groupby("team").complete_pass.mean()
    d["cpoe"] = att.groupby("team").cpoe.mean(); d["air_pa"] = att.groupby("team").air_yards.mean()
    d["yac_pc"] = comp.groupby("team").yards_after_catch.mean()
    d["sack_rate"] = db_.groupby("team").sack.mean(); d["qbhit_rate"] = db_.groupby("team").qb_hit.mean()
    d["int_rate"] = att.groupby("team").interception.mean()
    d["rush_ypc"] = ru.groupby("team").yards_gained.mean(); d["stuff_rate"] = ru.assign(s=(ru.yards_gained <= 0)).groupby("team").s.mean()
    t3 = x[x.down == 3]; d["third"] = t3.groupby("team").third_down_converted.sum() / t3.groupby("team").size()
    # turnovers: offence loses them, defence takes them
    to = p[(p.interception == 1) | (p.fumble_lost == 1)].groupby("team").size()
    d["to_pg"] = to.reindex(d.index).fillna(0) / games
    pen = p[p.penalty == 1]
    pt = pen.groupby(nv.norm_team(pen.penalty_team)).size()
    d["pen_pg"] = (pt.reindex(d.index).fillna(0) / games) if side == "off" else np.nan
    # drives
    dr = p[p.drive.notna() & p.team.notna()].groupby(["team", "game_id", "drive"]).agg(res=("fixed_drive_result", "first"))
    dr["pts"] = dr.res.map({"Touchdown": 7, "Field goal": 3}).fillna(0)
    d["ppd"] = dr.groupby("team").pts.mean(); d["drives_pg"] = dr.groupby("team").size() / games
    rz = p[(p.yardline_100 <= 20) & p.drive.notna() & p.team.notna()].groupby(["team", "game_id", "drive"]).fixed_drive_result.first()
    d["rz_trips"] = rz.groupby("team").size() / games
    d["rz_td"] = rz.eq("Touchdown").groupby("team").mean()
    return d


def pts_pg(season, con) -> pd.DataFrame:
    g = pd.read_sql("select * from games where season=? and home_score is not null", con, params=(season,))
    a = pd.concat([g.rename(columns={"home": "team", "home_score": "pf", "away_score": "pa"})[["team", "pf", "pa"]],
                   g.rename(columns={"away": "team", "away_score": "pf", "home_score": "pa"})[["team", "pf", "pa"]]])
    return a.groupby("team").mean()


def ranked(season: int, side: str, con) -> dict:
    if (season, side) in _RK:
        return _RK[(season, side)]
    d = team_metrics(season, side)
    pp = pts_pg(season, con)
    d["pts_pg"] = pp.pf if side == "off" else pp.pa
    better = {k: (v[1] if side == "off" else DEF_BETTER[k]) for k, v in OFF_M.items()}
    rk = pd.DataFrame(index=d.index)
    for k, b in better.items():
        if k in d and b is not None:
            rk[k] = d[k].rank(ascending=not b, method="min")
    _RK[(season, side)] = {"vals": d, "rank": rk, "better": better}
    return _RK[(season, side)]


def position_allowed(season: int) -> pd.DataFrame:
    if season in _PA:
        return _PA[season]
    _PA[season] = _position_allowed(season)
    return _PA[season]


def _position_allowed(season: int) -> pd.DataFrame:
    """Per defence: per-game receptions/yards/TDs allowed to WR / TE / RB, rushing to RB, passing to QB (from weekly player stats)."""
    s = nv.get("stats", season)
    s = s[s.season_type == "REG"].copy()
    s["def"] = nv.norm_team(s.opponent_team)
    out = {}
    for pos in ("QB", "RB", "WR", "TE"):
        q = s[s.position == pos]
        gm = s.groupby("def").week.nunique()
        a = q.groupby("def").agg(pass_yds=("passing_yards", "sum"), pass_td=("passing_tds", "sum"), ints=("passing_interceptions", "sum"), att=("attempts", "sum"),
                                  car=("carries", "sum"), rush_yds=("rushing_yards", "sum"), rush_td=("rushing_tds", "sum"),
                                  tgt=("targets", "sum"), rec=("receptions", "sum"), rec_yds=("receiving_yards", "sum"), rec_td=("receiving_tds", "sum"),
                                  fpts=("fantasy_points_ppr", "sum"))
        for c in a.columns:
            out[(pos, c)] = a[c] / gm
    return pd.DataFrame(out)


def player_table(team: str, opp: str, con) -> pd.DataFrame:
    """Season + 2025 + recent per-game stats for skill players on `team`."""
    rows = []
    for s in (config.SEASON, config.LAST_SEASON):
        st = nv.get("stats", s)
        st = st[(st.season_type == "REG")].copy()
        st["team"], st["opponent_team"] = nv.norm_team(st.team), nv.norm_team(st.opponent_team)
        rows.append(st.assign(season=s))
    return pd.concat(rows)


def weather_block(game, home: str):
    la, lo, alt, _ = STADIUM[home]
    ko = pd.Timestamp(game.kickoff_utc)
    import time
    params = {
        "latitude": la, "longitude": lo, "timezone": "UTC", "temperature_unit": "fahrenheit", "windspeed_unit": "mph", "precipitation_unit": "inch",
        "start_date": ko.strftime("%Y-%m-%d"), "end_date": (ko + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m,dew_point_2m,precipitation_probability,precipitation,snowfall,weathercode,cloudcover,"
                  "surface_pressure,visibility,windspeed_10m,windgusts_10m,winddirection_10m,cape,uv_index"}
    cache = config.CACHE / "openmeteo" / f"{game.game_id}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    r = None
    for i in range(4):                               # Open-Meteo sometimes answers "service is overloaded": retry, then use the last good copy
        try:
            j = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=30).json()
            if "hourly" in j:
                r = j["hourly"]
                cache.write_text(json.dumps(r), encoding="utf-8")
                break
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    if r is None:
        if not cache.exists():
            raise RuntimeError(f"no Open-Meteo forecast for {game.game_id} and no cached copy")
        r = json.loads(cache.read_text(encoding="utf-8"))
    h = pd.DataFrame(r)
    h["t"] = pd.to_datetime(h.time, utc=True)
    w = h[(h.t >= ko - pd.Timedelta(hours=2)) & (h.t <= ko + pd.Timedelta(hours=5))].copy()
    # air density (kg/m3) from station pressure, temperature, humidity: where the altitude effect shows up
    def dens(row):
        tk = (row.temperature_2m - 32) / 1.8 + 273.15
        e = 6.1078 * 10 ** (7.5 * (row.dew_point_2m - 32) / 1.8 / (237.3 + (row.dew_point_2m - 32) / 1.8))      # vapour pressure, hPa
        pd_ = row.surface_pressure - e
        return (pd_ * 100) / (287.058 * tk) + (e * 100) / (461.495 * tk)
    w["air_density"] = w.apply(dens, axis=1)
    sea_level = 1.225
    comp = lambda d: ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"][int((d % 360) / 22.5 + .5) % 16]
    w["wind_dir"] = w.winddirection_10m.map(comp)
    w["et"] = w.t.dt.tz_convert("America/New_York").dt.strftime("%-I:%M %p") if False else w.t.dt.tz_convert("America/New_York").dt.strftime("%I:%M %p").str.lstrip("0")
    cols = ["et", "temperature_2m", "apparent_temperature", "relative_humidity_2m", "dew_point_2m", "precipitation_probability", "precipitation", "snowfall", "weathercode",
            "cloudcover", "surface_pressure", "visibility", "windspeed_10m", "windgusts_10m", "winddirection_10m", "wind_dir", "cape", "air_density"]
    out = {"hours": w[cols].round(3).to_dict("records"), "altitude_ft": alt, "air_density_sea_level": sea_level,
           "kickoff_hour_index": int(((w.t - ko).abs()).values.argmin())}
    out["density_vs_sea_level_pct"] = round(float(w.air_density.mean() / sea_level - 1) * 100, 1)
    return out


WCODE = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain",
         63: "Rain", 65: "Heavy rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Rain showers", 81: "Rain showers", 82: "Violent showers", 95: "Thunderstorm"}


def history_block(away: str, home: str, week: int) -> dict:
    g = pd.read_csv(C / "games.csv")
    g = g[(g.game_type == "REG") & g.home_score.notna()].copy()
    g["tot"] = g.home_score + g.away_score
    out = {}
    row = g[(g.season == config.SEASON) & (g.week == week) & (g.home_team == home) & (g.away_team == away)]
    full = pd.read_csv(C / "games.csv")
    r0 = full[(full.season == config.SEASON) & (full.week == week) & (full.home_team == home) & (full.away_team == away)]
    wd = str(r0.weekday.iloc[0]) if len(r0) else "Sunday"
    thu = g[(g.weekday == wd) & (g.season >= 2015)]
    out["day"] = {"label": wd, "n": len(thu), "avg_total": round(thu.tot.mean(), 1), "avg_line": round(thu.total_line.mean(), 1),
                  "over_pct": round(float((thu.tot > thu.total_line).sum() / ((thu.tot != thu.total_line).sum())), 3),
                  "fav_cover_pct": round(float(((thu.result > thu.spread_line)).mean()), 3), "home_win_pct": round(float((thu.result > 0).mean()), 3)}
    allg = g[g.season >= 2015]
    out["all"] = {"avg_total": round(allg.tot.mean(), 1), "over_pct": round(float((allg.tot > allg.total_line).sum() / (allg.tot != allg.total_line).sum()), 3)}
    h = g[(g.home_team == home) & (g.season >= 2018)]
    out["home_team"] = {"team": home, "n": len(h), "avg_total": round(h.tot.mean(), 1), "avg_line": round(h.total_line.mean(), 1),
                        "over_pct": round(float((h.tot > h.total_line).sum() / (h.tot != h.total_line).sum()), 3),
                        "avg_margin": round(float(h.result.mean()), 1), "cover_pct": round(float((h.result > h.spread_line).sum() / (h.result != h.spread_line).sum()), 3)}
    # last meetings
    m = g[((g.home_team == home) & (g.away_team == away)) | ((g.home_team == away) & (g.away_team == home))].sort_values(["season", "week"]).tail(4)
    out["meetings"] = [{"season": int(r.season), "week": int(r.week), "home": r.home_team, "away": r.away_team, "score": f"{int(r.away_score)}-{int(r.home_score)}",
                        "total": int(r.tot), "line": r.total_line} for r in m.itertuples()]
    # each team's recent games (this season) with ATS / OU
    logs = {}
    for t in (away, home):
        x = g[(g.season == config.SEASON) & ((g.home_team == t) | (g.away_team == t))].sort_values("week")
        rows = []
        for r in x.itertuples():
            ishome = r.home_team == t
            pf, pa = (r.home_score, r.away_score) if ishome else (r.away_score, r.home_score)
            sp = r.spread_line if ishome else -r.spread_line            # +ve = this team favoured
            rows.append({"week": int(r.week), "opp": r.away_team if ishome else r.home_team, "home": bool(ishome), "pf": int(pf), "pa": int(pa),
                         "ats": "W" if (pf - pa) > sp else ("L" if (pf - pa) < sp else "P"), "ou": "O" if r.tot > r.total_line else ("U" if r.tot < r.total_line else "P"),
                         "line": r.total_line, "spread": float(sp), "temp": None if pd.isna(r.temp) else float(r.temp), "wind": None if pd.isna(r.wind) else float(r.wind)})
        logs[t] = rows
    out["logs"] = logs
    return out


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if (math.isnan(o) or math.isinf(o)) else round(float(o), 4)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def build(game_id: str, con=None, ctx=None, res=None, props=None, tds=None) -> dict:
    con = con or db.connect()
    g = pd.read_sql("select * from games where game_id=?", con, params=(game_id,)).iloc[0]
    home, away = g.home, g.away
    out = {"game_id": game_id, "home": home, "away": away, "kickoff": g.kickoff_utc, "rest": {"home": g.rest_home, "away": g.rest_away}, "roof": g.roof}
    # ---- team metrics with ranks (2026 + 2025)
    teams_block = {}
    for side in ("off", "def"):
        r26, r25 = ranked(config.SEASON, side, con), ranked(config.LAST_SEASON, side, con)
        rows = []
        for k, (lab, better, fmt) in OFF_M.items():
            if side == "def" and k == "pen_pg":
                continue
            if k not in r26["vals"]:
                continue
            e = {"key": k, "label": lab if side == "off" else DEF_LABEL.get(k, lab), "fmt": fmt, "better": better if side == "off" else DEF_BETTER[k]}
            for t in (away, home):
                e[t] = {"v26": r26["vals"].at[t, k], "r26": r26["rank"].at[t, k] if k in r26["rank"] else None,
                        "v25": r25["vals"].at[t, k], "r25": r25["rank"].at[t, k] if k in r25["rank"] else None}
            e["lg26"] = float(r26["vals"][k].mean()); e["lg25"] = float(r25["vals"][k].mean())
            rows.append(e)
        ORDER = ["epa_pass", "sr_pass", "ypa", "comp_pct", "cpoe", "air_pa", "yac_pc", "expl_pass", "int_rate",
                 "epa_rush", "sr_rush", "rush_ypc", "expl_rush", "stuff_rate",
                 "sr", "sack_rate", "qbhit_rate", "third", "ppd", "rz_td", "rz_trips", "drives_pg", "plays_pg", "neutral_pass", "to_pg", "pen_pg", "pts_pg"]
        grp = lambda k: "Passing" if k in ORDER[:9] else ("Rushing" if k in ORDER[9:14] else "Other")
        for e in rows:
            e["group"] = grp(e["key"])
        rows.sort(key=lambda e: ORDER.index(e["key"]) if e["key"] in ORDER else 99)
        teams_block[side] = rows
    out["metrics"] = teams_block
    # ---- position matchups: what each defence allows per game to each position group, with ranks
    pa26, pa25 = position_allowed(config.SEASON), position_allowed(config.LAST_SEASON)
    pos = []
    for (p, c), lab in {("WR", "rec_yds"): "WR receiving yds", ("WR", "rec"): "WR receptions", ("WR", "rec_td"): "WR TDs", ("TE", "rec_yds"): "TE receiving yds",
                        ("TE", "rec"): "TE receptions", ("TE", "rec_td"): "TE TDs", ("RB", "rush_yds"): "RB rushing yds", ("RB", "car"): "RB carries",
                        ("RB", "rush_td"): "RB rush TDs", ("RB", "rec_yds"): "RB receiving yds", ("RB", "rec"): "RB receptions", ("QB", "pass_yds"): "QB passing yds",
                        ("QB", "pass_td"): "QB passing TDs", ("QB", "ints"): "QB interceptions", ("QB", "rush_yds"): "QB rushing yds", ("QB", "fpts"): "QB fantasy pts (PPR)",
                        ("RB", "fpts"): "RB fantasy pts (PPR)", ("WR", "fpts"): "WR fantasy pts (PPR)", ("TE", "fpts"): "TE fantasy pts (PPR)"}.items():
        e = {"label": lab}
        for t in (away, home):
            e[t] = {"v26": pa26[(p, c)].get(t), "r26": float(pa26[(p, c)].rank(ascending=False, method="min").get(t)), "v25": pa25[(p, c)].get(t),
                    "r25": float(pa25[(p, c)].rank(ascending=False, method="min").get(t))}   # rank 1 = allows the MOST
        e["lg26"] = float(pa26[(p, c)].mean()); e["lg25"] = float(pa25[(p, c)].mean())
        pos.append(e)
    out["pos_allowed"] = pos
    # ---- top defenders (coverage / rush production)
    st = nv.get("stats", config.SEASON)
    st = st[st.season_type == "REG"].copy(); st["team"] = nv.norm_team(st.team)
    dfn = []
    for t in (away, home):
        d = st[st.team == t].groupby("player_display_name").agg(pos=("position", "first"), g=("week", "nunique"), pd=("def_pass_defended", "sum"), ints=("def_interceptions", "sum"),
                                                                 sacks=("def_sacks", "sum"), hits=("def_qb_hits", "sum"), tfl=("def_tackles_for_loss", "sum"),
                                                                 solo=("def_tackles_solo", "sum"), ff=("def_fumbles_forced", "sum"), dtd=("def_tds", "sum")).reset_index()
        d["impact"] = d.pd + 3 * d.ints + 2 * d.sacks + d.hits * 0.5 + d.tfl
        for r in d[d.impact > 0].sort_values("impact", ascending=False).head(8).itertuples():
            dfn.append({"team": t, "name": r.player_display_name, "pos": r.pos, "g": int(r.g), "pd": int(r.pd), "ints": int(r.ints), "sacks": float(r.sacks), "hits": int(r.hits),
                        "tfl": float(r.tfl), "solo": int(r.solo), "ff": int(r.ff), "tds": int(r.dtd)})
    out["defenders"] = dfn
    # ---- weather (all metrics, hourly) + history + kicking
    wb = weather_block(g, home)
    for h in wb["hours"]:
        h["cond"] = WCODE.get(int(h["weathercode"]), f"code {int(h['weathercode'])}")
    out["weather"] = wb
    out["indoor"] = bool(g.roof in ("dome", "closed"))
    nw = pd.read_sql("select * from weather where game_id=? order by snap_ts desc limit 1", con, params=(game_id,))
    out["nflweather"] = nw.iloc[0].to_dict() if len(nw) else None
    out["weather_history"] = X.weather_history()
    out["kicking"] = X.kicking_block(home, _pbp)
    out["history"] = history_block(away, home, int(g.week))
    # ---- schedule / travel / dynamics
    out["travel_miles"] = round(X.haversine(STADIUM[away][:2], STADIUM[home][:2])) if away in STADIUM and home in STADIUM else None
    out["altitude_ft"] = {t: STADIUM[t][2] for t in (away, home) if t in STADIUM}
    prev = {}
    for t in (away, home):
        x = pd.read_sql("select * from games where season=? and week<? and (home=? or away=?) order by week desc limit 1", con, params=(config.SEASON, int(g.week), t, t))
        if len(x):
            r = x.iloc[0]; ih = r.home == t
            prev[t] = {"week": int(r.week), "opp": r.away if ih else r.home, "home": bool(ih), "score": f"{int(r.home_score if ih else r.away_score)}-{int(r.away_score if ih else r.home_score)}"}
    out["previous_game"] = prev
    # ---- weekly trend (offence / defence EPA by week)
    tw = pd.read_sql("select * from team_week where season=? and team in (?,?) order by week", con, params=(config.SEASON, away, home))
    out["trend"] = {t: tw[tw.team == t][["week", "off_epa_pass", "off_epa_rush", "def_epa_pass", "def_epa_rush", "plays", "pts_for", "pts_against"]].to_dict("records") for t in (away, home)}
    # ---- injuries (all flagged players on both teams) with usage
    pl = pd.read_sql("select player_id, name, team, pos from players", con)
    inj = inj_ad.current(pl, config.SEASON, int(g.week))
    sn = nv.get("snaps", config.SEASON); sn = sn[sn.game_type == "REG"]
    avg = sn.groupby("player").agg(off=("offense_pct", "mean"), de=("defense_pct", "mean"))
    stw = nv.get("stats", config.SEASON); stw = stw[stw.season_type == "REG"]
    use = stw.groupby("player_display_name").agg(tgt=("targets", "sum"), car=("carries", "sum"), g=("week", "nunique"))
    depth = nv.get("depth", config.SEASON)
    depth = depth[depth.dt == depth.dt.max()]
    GROUP = {"CB": ["LCB", "RCB", "NB"], "S": ["SS", "FS"], "LB": ["WLB", "MLB", "SLB", "LILB", "RILB"], "DE": ["LDE", "RDE"], "DT": ["LDT", "RDT", "NT"],
             "WR": ["WR"], "RB": ["RB"], "TE": ["TE"], "QB": ["QB"], "T": ["LT", "RT"], "G": ["LG", "RG"], "C": ["C"], "DL": ["LDE", "RDE", "LDT", "RDT", "NT"], "DB": ["LCB", "RCB", "NB", "SS", "FS"], "OL": ["LT", "LG", "C", "RG", "RT"], "OT": ["LT", "RT"], "OG": ["LG", "RG"], "FS": ["FS"], "SS": ["SS"]}
    out_ids = set(inj[inj.status.isin(["out", "doubtful"])].player_id)
    # players on injured reserve / PUP who were hurt in earlier weeks (so they are not on this week's report) still count as out
    lt = inj_ad.long_term(config.SEASON, config.LAST_SEASON, exclude_ids=set(inj[inj.status != "healthy"].player_id))
    lt = lt[lt.team.isin([away, home])]
    out_ids |= set(lt.player_id)
    def next_up(team, pos, pid):
        slots = GROUP.get(pos)
        if not slots:
            return []
        dd = depth[(depth.team == team) & depth.pos_abb.isin(slots) & (depth.gsis_id != pid) & ~depth.gsis_id.isin(out_ids)].sort_values("pos_rank").drop_duplicates("gsis_id")
        res = []
        for r_ in dd.head(3).itertuples():
            a_ = avg.loc[r_.player_name] if r_.player_name in avg.index else None
            res.append({"name": r_.player_name, "rank": int(r_.pos_rank), "snap_pct": None if a_ is None else round(float(max(np.nan_to_num(a_.off), np.nan_to_num(a_.de))) * 100)})
        return res
    word = re.compile(r"injur|hamstring|ankle|knee|calf|foot|ribs|groin|shoulder|forearm|concussion|designation|practice|participant|limited|questionable|doubtful|ruled out|placed|signed|activated", re.I)
    rows, news = [], []
    for r in inj[inj.team.isin([away, home])].sort_values("date", ascending=False).itertuples():
        a = avg.loc[r.name] if r.name in avg.index else None
        u = use.loc[r.name] if r.name in use.index else None
        item = {"team": r.team, "name": r.name, "pos": r.pos, "status": r.status, "raw_status": r.raw_status if isinstance(r.raw_status, str) else "", "injury": r.injury if isinstance(r.injury, str) else "",
                "practice": r.practice if isinstance(r.practice, str) else "", "note": r.note if isinstance(r.note, str) else "", "date": r.date if isinstance(r.date, str) else None,
                "snap_pct": None if a is None else round(float(max(np.nan_to_num(a.off), np.nan_to_num(a.de))) * 100),
                "tgt": None if u is None else int(u.tgt), "car": None if u is None else int(u.car), "g": None if u is None else int(u.g)}
        if r.status != "healthy":
            item["next_up"] = next_up(r.team, r.pos, r.player_id)
            item["hist"] = IH.history(con, r.player_id, r.team, int(g.week), name=r.name)
            rows.append(item)
        elif item["note"] and word.search(item["note"]):
            news.append(item)            # listed active, but the latest report mentions availability / practice / roster moves
    for r in lt.itertuples():
        rows.append({"team": r.team, "name": r.name, "pos": r.pos, "status": "out", "raw_status": r.raw_status, "injury": r.injury, "practice": "", "note": r.note, "date": None,
                     "snap_pct": r.snap_pct, "snap_year": int(r.snap_year), "tgt": int(r.tgt), "car": int(r.car), "g": int(r.g26), "long_term": True,
                     "next_up": next_up(r.team, r.pos, r.player_id), "hist": IH.history(con, r.player_id, r.team, int(g.week), name=r.name)})
    out["injury_news"] = news
    out["injuries"] = rows
    # ---- our projection, components and score distribution; props
    if ctx is None:
        import board_data
        ctx, res = board_data.run(con)
    pr = next(r for r in res if r["game_id"] == game_id)
    out["projection"] = {"margin": pr["margin"], "total": pr["total"], "pts_home": pr["pts_home"], "pts_away": pr["pts_away"], "comp": pr["comp"], "notes": pr["notes"], "ref": pr["ref"]}
    mu_m = pr["markets"]["spread"]["options"][0]["p_model"] if False else None
    mm = (-pr["ref"]["spread"] + config.MODEL_TRUST["margin"] * (pr["margin"] + pr["ref"]["spread"])) if pr["ref"].get("spread") is not None else pr["margin"]
    tt = (pr["ref"]["total"] + config.MODEL_TRUST["total"] * (pr["total"] - pr["ref"]["total"])) if pr["ref"].get("total") is not None else pr["total"]
    pm, pt = dist._load()[0].pmf(mm), dist._load()[1].pmf(tt)
    out["dist"] = {"mu_margin_used": mm, "mu_total_used": tt,
                   "margin": [[int(k), round(float(v), 4)] for k, v in pm.items() if -30 <= k <= 30], "total": [[int(k), round(float(v), 4)] for k, v in pt.items() if 20 <= k <= 75]}
    gm = pd.read_sql("select * from games where game_id=?", con, params=(game_id,)).iloc[0]
    wind_eff = float(np.nanmean([max(h["windspeed_10m"], 0.6 * h["windgusts_10m"]) for h in wb["hours"][2:6]]))
    out["qbs"] = M.qb_block([away, home], _pbp)
    out["usage"] = M.usage_block([away, home], con)
    out["plays_proj"] = M.plays_block(ctx, gm)
    if props is not None:
        out["players"] = {"props_idx": [i for i, p in enumerate(props) if p["game_id"] == game_id], "td_idx": [i for i, t in enumerate(tds or []) if t["game_id"] == game_id], "wind_used": round(wind_eff, 1)}
    else:
        w = ov.wide(ctx["odds_latest"])
        tdr = {home: pr["pts_home"], away: pr["pts_away"]}
        out["players"] = X.props_block(gm, w, con, position_allowed(config.SEASON), position_allowed(config.LAST_SEASON), wind_eff, tdr)
    out["dynamics"] = M.dynamics(out)
    out["standouts"] = SO.standouts(out)
    return out


def build_all(con=None, ctx=None, res=None, props=None, tds=None) -> dict:
    """Deep dive for every unplayed game this week that has odds. Returns {game_id: deep}."""
    con = con or db.connect()
    if ctx is None:
        import board_data
        ctx, res = board_data.run(con)
    out = {}
    for r in res:
        out[r["game_id"]] = _clean(build(r["game_id"], con, ctx, res, props, tds))
    return out


if __name__ == "__main__":
    a, h = sys.argv[1], sys.argv[2]
    con = db.connect()
    gid = pd.read_sql("select game_id from games where season=? and home=? and away=? and home_score is null", con, params=(config.SEASON, h, a)).iloc[0, 0]
    d = build(gid, con)
    print(json.dumps(_clean(d))[:3000])
