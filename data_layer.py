"""Builds games/team_week/players/player_week from nflverse. `python data_layer.py` refreshes the DB."""
import json
import pandas as pd
import config
import db
from adapters import nflverse as nv

SEASONS = [config.LAST_SEASON - 1, config.LAST_SEASON, config.SEASON]   # 2024 only seeds team ratings
STAT_COLS = ["completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "carries",
             "rushing_yards", "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds",
             "target_share", "air_yards_share", "passing_epa", "rushing_epa", "receiving_epa", "sacks_suffered"]
USAGE = ["rz_targets", "gl_targets", "rz_carries", "gl_carries"]


def _play_mask(p):
    return ((p.season_type == "REG") & p.epa.notna() & ((p["pass"] == 1) | (p.rush == 1))
            & (p.qb_kneel != 1) & (p.qb_spike != 1))


def team_week(pbp: pd.DataFrame) -> pd.DataFrame:
    """Per team-week offence and defence: EPA/play (pass, rush), success rate, play count."""
    p = pbp[_play_mask(pbp)].copy()
    p["posteam"], p["defteam"] = nv.norm_team(p.posteam), nv.norm_team(p.defteam)
    p["epa_pass"] = p.epa.where(p["pass"] == 1)
    p["epa_rush"] = p.epa.where(p.rush == 1)
    off = p.groupby(["season", "week", "posteam"]).agg(
        plays=("epa", "size"), off_epa_pass=("epa_pass", "mean"), off_epa_rush=("epa_rush", "mean"),
        off_sr=("success", "mean")).reset_index().rename(columns={"posteam": "team"})
    dfn = p.groupby(["season", "week", "defteam"]).agg(
        def_epa_pass=("epa_pass", "mean"), def_epa_rush=("epa_rush", "mean"),
        def_sr=("success", "mean")).reset_index().rename(columns={"defteam": "team"})
    return off.merge(dfn, on=["season", "week", "team"], how="outer")


def usage_from_pbp(pbp: pd.DataFrame) -> pd.DataFrame:
    """Red-zone (inside 20) and goal-line (inside 5) usage per player-week."""
    p = pbp[(pbp.season_type == "REG") & (pbp.yardline_100 <= 20) & (pbp.play_type.isin(["pass", "run"]))].copy()
    p["gl"] = (p.yardline_100 <= 5).astype(int)
    rec = (p[p["pass"] == 1].groupby(["season", "week", "receiver_player_id"])
           .agg(rz_targets=("gl", "size"), gl_targets=("gl", "sum")).reset_index()
           .rename(columns={"receiver_player_id": "player_id"}))
    rus = (p[p.rush == 1].groupby(["season", "week", "rusher_player_id"])
           .agg(rz_carries=("gl", "size"), gl_carries=("gl", "sum")).reset_index()
           .rename(columns={"rusher_player_id": "player_id"}))
    return rec.merge(rus, on=["season", "week", "player_id"], how="outer").fillna(0)


def _games(sched):
    ko = pd.to_datetime(sched.gameday + " " + sched.gametime.fillna("13:00"))
    ko = ko.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    return pd.DataFrame({
        "game_id": sched.game_id, "season": sched.season, "week": sched.week,
        "kickoff_utc": ko.dt.strftime("%Y-%m-%dT%H:%MZ"), "home": sched.home_team, "away": sched.away_team,
        "roof": sched.roof, "home_score": sched.home_score, "away_score": sched.away_score,
        "sgo_event_id": None, "rest_home": sched.home_rest, "rest_away": sched.away_rest, "location": sched.location})


def _replace(con, table, df):
    con.execute(f"DELETE FROM {table}")
    df.to_sql(table, con, if_exists="append", index=False)


def build(verbose=True):
    con = db.connect()
    sched = nv.schedule()
    sched = sched[sched.season.isin(SEASONS)]
    old = dict(con.execute("select game_id, sgo_event_id from games where sgo_event_id is not null").fetchall())
    gm = _games(sched)
    gm["sgo_event_id"] = gm.game_id.map(old)          # a rebuild must not lose the SGO event links
    _replace(con, "games", gm)

    tw, uw, pw, rosters = [], [], [], []
    for s in SEASONS:
        pbp = nv.get("pbp", s)
        tw.append(team_week(pbp))
        uw.append(usage_from_pbp(pbp))
        st = nv.get("stats", s)
        st = st[st.season_type == "REG"].copy()
        st["team"], st["opponent_team"] = nv.norm_team(st.team), nv.norm_team(st.opponent_team)
        pw.append(st)
        ro = nv.get("roster", s)
        ro["team"] = nv.norm_team(ro.team)
        rosters.append(ro.assign(season=s))
    tw = pd.concat(tw)
    pts = pd.concat([
        sched[["season", "week", "home_team", "home_score", "away_score"]].set_axis(
            ["season", "week", "team", "pts_for", "pts_against"], axis=1),
        sched[["season", "week", "away_team", "away_score", "home_score"]].set_axis(
            ["season", "week", "team", "pts_for", "pts_against"], axis=1)])
    _replace(con, "team_week", tw.merge(pts, on=["season", "week", "team"], how="left"))

    ro = pd.concat(rosters).sort_values("season").drop_duplicates("gsis_id", keep="last").dropna(subset=["gsis_id"])
    _replace(con, "players", pd.DataFrame({
        "player_id": ro.gsis_id, "name": ro.full_name, "pos": ro.position, "team": ro.team, "sgo_id": None,
        "draft_pick": pd.to_numeric(ro.draft_number, errors="coerce"), "nfl_seasons": ro.years_exp}))

    pwk, usage = pd.concat(pw), pd.concat(uw)
    snaps = pd.concat([nv.get("snaps", s).assign(season=s) for s in SEASONS])
    snaps = snaps[snaps.game_type == "REG"]
    idmap = (pd.concat(rosters).dropna(subset=["pfr_id", "gsis_id"]).drop_duplicates("pfr_id")
             .set_index("pfr_id").gsis_id)
    snaps["player_id"] = snaps.pfr_player_id.map(idmap)
    snaps = snaps.dropna(subset=["player_id"])[["season", "week", "player_id", "offense_pct"]]
    pwk = (pwk.merge(usage, on=["season", "week", "player_id"], how="left")
           .merge(snaps, on=["season", "week", "player_id"], how="left"))
    pwk[USAGE] = pwk[USAGE].fillna(0)
    keep = (pwk[["attempts", "carries", "targets"]].fillna(0).sum(axis=1) > 0)
    pwk = pwk[keep]
    cols = [c for c in STAT_COLS if c in pwk] + USAGE
    js = pwk[cols].astype(float).apply(lambda r: json.dumps({k: (None if pd.isna(v) else v) for k, v in r.items()}), axis=1)
    _replace(con, "player_week", pd.DataFrame({
        "season": pwk.season, "week": pwk.week, "player_id": pwk.player_id, "team": pwk.team,
        "opp": pwk.opponent_team, "stats_json": js, "snap_pct": pwk.offense_pct}))
    con.commit()
    if verbose:
        for t in ["games", "team_week", "players", "player_week"]:
            print(t, con.execute(f"select count(*) from {t}").fetchone()[0])
        print("file status:", nv.status)
    return con


if __name__ == "__main__":
    build()
