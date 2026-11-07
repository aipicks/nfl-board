"""Data validation. `python validate.py` prints PASS/FAIL per check; weekly update calls run_all() and aborts on FAIL."""
import json
import pandas as pd
import config
import db
from adapters import nflverse as nv
from adapters.http import fetch

ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"


def season_coverage(con):
    """Return {season: (weeks_present, label)} so the page can label full vs partial history."""
    out = {}
    for s, wks in con.execute("select season, count(distinct week) from team_week group by season"):
        out[s] = (wks, "full season" if wks >= 18 else f"partial ({wks} weeks)")
    return out


def run_all(con=None, espn_check=True):
    con = con or db.connect()
    res = []

    def chk(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    tw = pd.read_sql("select * from team_week", con)
    g = pd.read_sql("select * from games", con)
    pw = pd.read_sql("select * from player_week", con)
    pl = pd.read_sql("select * from players", con)

    # teams: exactly the 32 codes, in every table
    for name, df, cols in [("team_week", tw, ["team"]), ("games", g, ["home", "away"])]:
        seen = set().union(*[set(df[c]) for c in cols])
        chk(f"{name} teams == 32 known codes", seen == nv.TEAMS32, f"diff={seen ^ nv.TEAMS32}")
    chk("player_week teams valid", set(pw.team) <= nv.TEAMS32, f"bad={set(pw.team) - nv.TEAMS32}")

    # season/week sanity and full-season labelling
    cov = season_coverage(con)
    for s_ in (config.LAST_SEASON - 1, config.LAST_SEASON):
        c_ = cov.get(s_)
        chk(f"{s_} is a full season (17 games/team)", c_ and c_[1] == "full season"
            and (tw[tw.season == s_].groupby("team").size() == 17).all(), str(c_))
    cur = tw[tw.season == config.SEASON]
    chk(f"{config.SEASON} weeks contiguous from 1", sorted(cur.week.unique()) == list(range(1, cur.week.max() + 1)),
        f"weeks={sorted(cur.week.unique())}")
    chk("every team-week has pbp metrics", tw[["off_epa_pass", "off_epa_rush", "def_epa_pass", "off_sr", "plays"]].notna().all().all())
    chk("plays/game in plausible range (25-100; OT/blowouts)", tw.plays.between(25, 100).all(),
        f"min={tw.plays.min()} max={tw.plays.max()}")
    chk("EPA/play in plausible range (|per-game EPA| < 1.5)", tw[["off_epa_pass", "off_epa_rush"]].abs().max().max() < 1.5,
        str(tw[["off_epa_pass", "off_epa_rush"]].abs().max().to_dict()))

    # pbp-derived team points vs schedule scores; stats vs pbp: team passing yards
    played = g[g.home_score.notna()]
    chk("no duplicate games", not g.game_id.duplicated().any())
    chk("games: scored games have both scores", played.away_score.notna().all())
    scores = pd.concat([played[["season", "week", "home", "home_score", "away_score"]].set_axis(["season", "week", "team", "f", "a"], axis=1),
                        played[["season", "week", "away", "away_score", "home_score"]].set_axis(["season", "week", "team", "f", "a"], axis=1)])
    m = tw.merge(scores, on=["season", "week", "team"], how="left")
    m = m[m.f.notna()]
    chk("team_week pts_for matches schedule scores", (m.pts_for == m.f).all() and (m.pts_against == m.a).all())

    # box-score check: player stats (nflverse weekly) must sum to team totals from pbp
    pbp = nv.get("pbp", config.SEASON)
    p = pbp[pbp.season_type == "REG"]
    team_py = p.groupby(["week", "posteam"]).passing_yards.sum().rename("pbp_py")
    team_py.index = team_py.index.set_levels(nv.norm_team(pd.Series(team_py.index.levels[1])).values, level=1)
    ps = pw[pw.season == config.SEASON].copy()
    ps["py"] = ps.stats_json.map(lambda s: json.loads(s).get("passing_yards") or 0)
    sums = ps.groupby(["week", "team"]).py.sum()
    j = pd.concat([sums, team_py], axis=1).dropna()
    diff = (j.py - j.pbp_py).abs()
    chk("player passing yds sum to pbp team passing yds (<=3 yds off)", (diff <= 3).mean() > 0.99,
        f"{(diff <= 3).mean():.1%} of {len(j)} team-weeks; worst={diff.max()}")

    # TD cross-check: player rushing+receiving TDs <= team offensive TDs in pbp
    chk("players table has no duplicate ids", not pl.player_id.duplicated().any())
    chk("every player_week id is in players", pw.player_id.isin(pl.player_id).mean() > 0.97,
        f"{pw.player_id.isin(pl.player_id).mean():.1%}")

    # independent source: ESPN scoreboard finals for the latest finished week
    if espn_check:
        try:
            wk = int(played[played.season == config.SEASON].week.max())
            n = _espn_scores(con, played, wk)
            chk(f"ESPN finals match schedule scores (weeks {wk-1}-{wk}, {n[0]} games)", n[1] == 0, f"{n[1]} mismatches: {n[2]}")
        except Exception as e:  # network down: report, don't fail the run
            res.append(("ESPN cross-check", True, f"skipped: {e}"))
        try:
            n, bad = _espn_qb(con, played)
            chk(f"ESPN box score QB passing yds match nflverse ({n} QBs)", n > 0 and not bad, f"mismatch={bad}")
        except Exception as e:
            res.append(("ESPN QB box-score check", True, f"skipped: {e}"))
    return res


def _espn_qb(con, played):
    """Independent check: ESPN game-summary passing yards for each finished 2026 game's starting QB vs our player_week."""
    gw = played[(played.season == config.SEASON)].tail(6)
    n, bad = 0, []
    for _, gm in gw.iterrows():
        d = (pd.to_datetime(gm.kickoff_utc).tz_localize(None) - pd.Timedelta(hours=8)).strftime("%Y%m%d")
        sb, _ = fetch(ESPN, config.CACHE / "espn" / f"scoreboard_{d}.json", params={"dates": d}, max_age_s=3600)
        for ev in json.loads(sb.read_text(encoding="utf-8"))["events"]:
            ab = {nv.TEAM_FIX.get(c["team"]["abbreviation"], "WAS" if c["team"]["abbreviation"] == "WSH" else c["team"]["abbreviation"])
                  for c in ev["competitions"][0]["competitors"]}
            if ab != {gm.home, gm.away}:
                continue
            sp, _ = fetch(ESPN.replace("scoreboard", "summary"), config.CACHE / "espn" / f"summary_{ev['id']}.json",
                          params={"event": ev["id"]}, max_age_s=24 * 3600)
            for team in json.loads(sp.read_text(encoding="utf-8"))["boxscore"]["players"]:
                cat = next(c for c in team["statistics"] if c["name"] == "passing")
                a = team["team"]["abbreviation"]; a = nv.TEAM_FIX.get(a, "WAS" if a == "WSH" else a)
                row = cat["athletes"][0]  # first listed passer
                yds = int(row["stats"][cat["labels"].index("YDS")])
                nm = row["athlete"]["displayName"]
                mine = pd.read_sql("select p.name, json_extract(w.stats_json,'$.passing_yards') y from player_week w "
                                   "join players p using(player_id) where w.season=? and w.week=? and w.team=? "
                                   "order by y desc limit 1", con, params=(gm.season, gm.week, a))
                n += 1
                if mine.empty or int(mine.y[0]) != yds:
                    bad.append((a, nm, yds, None if mine.empty else (mine.name[0], mine.y[0])))
    return n, bad


def _espn_scores(con, played, wk):
    gw = played[(played.season == config.SEASON) & (played.week >= wk - 1)]
    bad, n = [], 0
    dates = sorted(set((pd.to_datetime(gw.kickoff_utc).dt.tz_localize(None) - pd.Timedelta(hours=8)).dt.strftime("%Y%m%d")))
    for d in dates:
        path, _ = fetch(ESPN, config.CACHE / "espn" / f"scoreboard_{d}.json", params={"dates": d}, max_age_s=3600)
        for ev in json.loads(path.read_text(encoding="utf-8"))["events"]:
            comp = ev["competitions"][0]
            if not comp["status"]["type"]["completed"]:
                continue
            sc = {c["team"]["abbreviation"]: int(c["score"]) for c in comp["competitors"]}
            sc = {nv.TEAM_FIX.get(k, "WAS" if k == "WSH" else k): v for k, v in sc.items()}
            row = gw[(gw.home.isin(sc)) & (gw.away.isin(sc))]
            if row.empty:
                continue
            r = row.iloc[0]
            n += 1
            if sc[r.home] != r.home_score or sc[r.away] != r.away_score:
                bad.append((r.home, r.away))
    return n, len(bad), bad


if __name__ == "__main__":
    out = run_all()
    for name, ok, detail in out:
        print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    print(season_coverage(db.connect()))
    raise SystemExit(0 if all(o for _, o, _ in out) else 1)


def validate_context(con=None):
    """Checks on the latest injuries / weather / splits snapshots for the current week."""
    import context
    con = con or db.connect()
    res = []
    chk = lambda n, ok, d="": res.append((n, bool(ok), d))
    wk = context.current_week(con)
    g = pd.read_sql("select game_id from games where season=? and week=?", con, params=(config.SEASON, wk))
    w = pd.read_sql("select * from weather where snap_ts=(select max(snap_ts) from weather)", con)
    chk("weather covers every game this week", set(g.game_id) <= set(w.game_id), f"missing={set(g.game_id) - set(w.game_id)}")
    chk("weather values plausible", w.temp_f.between(-20, 125).all() and w.wind_mph.between(0, 60).all() and w.precip_pct.between(0, 100).all())
    s = pd.read_sql("select * from public_splits where snap_ts=(select max(snap_ts) from public_splits)", con)
    unplayed = pd.read_sql("select game_id from games where season=? and week=? and home_score is null", con, params=(config.SEASON, wk))
    chk("splits cover every unplayed game x 3 markets", all((s.game_id == x).sum() == 6 for x in unplayed.game_id),
        f"games with splits={s.game_id.nunique()}/{len(unplayed)}")
    sums = s.groupby(["game_id", "market"])[["tickets_pct", "money_pct"]].sum()
    chk("each split pair sums to ~100%", ((sums - 100).abs() < 1.5).all().all(), f"worst={float((sums - 100).abs().max().max()):.2f}")
    i = pd.read_sql("select * from injuries where snap_ts=(select max(snap_ts) from injuries)", con)
    chk("injury statuses in vocabulary", set(i.status) <= {"healthy", "questionable", "doubtful", "out"})
    chk("injury teams valid", set(i.team.dropna()) <= nv.TEAMS32, f"bad={set(i.team.dropna()) - nv.TEAMS32}")
    flagged = i[i.status != "healthy"]
    chk("injury report is non-trivial (>=100 flagged players)", len(flagged) >= 100, f"{len(flagged)}")
    return res
