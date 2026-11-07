import json
import math
from datetime import datetime, timezone

import pandas as pd
import pytest

import config
import db
import tracking as TR
from model import props as P, td as T


# ---------------- anytime TD ----------------
def test_td_probability_from_lambda_and_calibration_compresses_only_high_end():
    assert T.p_td(0.0) == 0 and T.p_td(math.log(2)) == pytest.approx(0.5)
    assert T.calibrate(0.2) == 0.2 and T.calibrate(0.5) < 0.5
    assert T.calibrate(0.5) == pytest.approx(0.35 + 0.15 * config.TD_CAL_SLOPE)


def test_td_lambda_is_sum_of_zone_touches_times_zone_rates():
    conv = {b: 0.1 for b in T.BANDS}
    row = pd.Series({b: 1.0 for b in T.BANDS})
    assert T.lam(row, conv) == pytest.approx(0.6)
    assert T.lam(row, conv, env_mult=2, opp_mult=0.5, p_play=0.5) == pytest.approx(0.3)


def test_missing_teammate_usage_is_redistributed():
    prof = pd.DataFrame({"team": ["X", "X", "X", "Y"], **{b: [4.0, 2.0, 2.0, 5.0] for b in T.BANDS}}, index=["a", "b", "c", "d"])
    pos = pd.Series({"a": "WR", "b": "WR", "c": "TE", "d": "WR"})
    out = T.redistribute(prof, pos, {"a": 1.0})
    assert out.loc["b", "tgt_rz"] == pytest.approx(4.0) and out.loc["c", "tgt_rz"] == pytest.approx(4.0)   # a's 4 split evenly
    assert out.loc["d", "tgt_rz"] == 5.0                                                                    # other team untouched
    assert T.redistribute(prof, pos, {"a": 0.5}).loc["b", "tgt_rz"] == pytest.approx(3.0)


def test_td_usage_profile_uses_only_earlier_games():
    pw = pd.DataFrame({"season": [2026] * 3, "week": [1, 2, 3], "player_id": ["p"] * 3, "team": ["X"] * 3, "td": [1, 0, 1], "snap_pct": [50, 60, 70],
                       "tgt_share": [.2, .2, .2], **{b: [1.0, 2.0, 9.0] for b in T.BANDS}})
    prof = T.usage_profile(pw, (2026, 3))
    assert prof.loc["p", "n_games"] == 2 and prof.loc["p", "tgt_rz"] < 2.0     # week 3 (9.0) excluded


# ---------------- props distributions ----------------
def test_prop_probabilities_monotone_and_integer_lines_push():
    for m, mu, lo_line, hi_line in (("rec_yds", 50.0, 30.5, 70.5), ("receptions", 4.0, 2.5, 6.5), ("pass_td", 1.5, 0.5, 2.5)):
        assert P.p_over(m, mu, lo_line)[0] > P.p_over(m, mu, hi_line)[0]
    po, pp = P.p_over("receptions", 4.0, 4.0)
    assert pp > 0.1 and po + pp < 1
    po2, pp2 = P.p_over("receptions", 4.0, 3.5)
    assert pp2 == 0 and po2 == pytest.approx(po + pp, abs=1e-9)
    assert P.p_over("rec_yds", 0.0, 10.5) == (0.0, 0.0)


def test_prop_mean_at_the_line_is_close_to_even():
    assert 0.35 < P.p_over("rec_yds", 60.0, 60.5)[0] < 0.55
    assert 0.35 < P.p_over("receptions", 4.5, 4.5)[0] < 0.55


# ---------------- tracking: logging and settlement ----------------
@pytest.fixture()
def tmpdb(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    return db.connect()


def _res(ko, side="home"):
    opt = {"side": side, "line": -3.5, "book": "fanduel", "price": -110, "p_model": 0.55, "p_market": 0.5, "p_final": 0.54, "ev": 0.03, "label": "BET"}
    return [{"game_id": "G1", "home": "AAA", "away": "BBB", "kickoff_utc": ko, "margin": 4.0, "total": 44.0, "comp": {},
             "markets": {"spread": {"best": opt, "fanduel": [opt], "options": [opt]}, "total": {"best": None, "fanduel": [], "options": []}}}]


def test_logging_updates_before_kickoff_and_never_after(tmpdb):
    now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    assert TR.log_predictions(tmpdb, _res("2026-10-18T17:00Z"), [], [], now=now)["new"] == 1
    r2 = TR.log_predictions(tmpdb, _res("2026-10-18T17:00Z"), [], [], now=now)
    assert r2["new"] == 0 and r2["updated"] == 1 and tmpdb.execute("select count(*) from pred_log").fetchone()[0] == 1
    late = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
    assert TR.log_predictions(tmpdb, _res("2026-10-18T17:00Z"), [], [], now=late) == {"new": 0, "updated": 0}


def test_settlement_and_results_metrics(tmpdb, monkeypatch):
    tmpdb.execute("insert into games(game_id, season, week, home, away, home_score, away_score) values ('G1', 2026, 6, 'AAA', 'BBB', 27, 20)")
    tmpdb.commit()
    TR.log_predictions(tmpdb, _res("2026-10-18T17:00Z"), [], [], now=datetime(2026, 10, 18, 12, tzinfo=timezone.utc))
    monkeypatch.setattr(TR, "_stats_by_week", lambda s: {})
    assert TR.settle(tmpdb)["settled"] == 1                                    # home -3.5 wins by 7
    assert tmpdb.execute("select result, actual from pred_log").fetchone() == ("win", 7.0)
    g = TR.results(tmpdb)["groups"]["Spreads"]
    assert g["n"] == 1 and g["w"] == 1 and g["units"] == pytest.approx(100 / 110, abs=0.01)
    assert g["brier_final"] == pytest.approx((0.54 - 1) ** 2, abs=1e-3) and g["brier_market"] == pytest.approx(0.25, abs=1e-3)


# ---------------- the weekly update's steps ----------------
def test_weekly_update_pipeline_runs_on_live_db():
    """Guards every offline step update.py calls: game model, TD, props, parlays, deep dive, results."""
    import build_board
    import update
    assert callable(update.main)
    d = build_board.payload(log=False)
    assert d["games"] and d["td"] and d["props"] and d["deeps"]
    assert set(d["games"][0]["markets"]) == set(config.GAME_MARKETS)                    # spreads and totals only
    for p in d["props"][:50]:
        assert 0 < p["best"]["p_final"] < 1 and p["sd"] > 0
    assert set(d["results"]) >= {"logged", "groups", "calibration"}
    json.dumps(build_board._clean(d))


def test_long_term_injured_reserve_players_are_listed():
    import config
    from adapters import injuries as I
    lt = I.long_term(config.SEASON, config.LAST_SEASON)
    assert len(lt) > 50 and (lt.status == "out").all() and lt.long_term.all()
    assert lt.player_id.is_unique
    ex = I.long_term(config.SEASON, config.LAST_SEASON, exclude_ids={lt.player_id.iloc[0]})
    assert lt.player_id.iloc[0] not in set(ex.player_id)          # players already on the weekly report are not repeated


def test_te_board_top_three_distinct_teams_and_sorted():
    import build_board, db, te_board
    d = build_board.payload(log=False)
    r = te_board.build(d["td"], d["deeps"], d["games"], db.connect())
    assert r["day"] and 1 <= len(r["top"]) <= 3
    assert len({x["team"] for x in r["top"]}) == len(r["top"])
    sc = [x["score"] for x in r["rows"]]
    assert sc == sorted(sc, reverse=True) and all(0 <= s <= 100 for s in sc)
    assert all(x["status"] not in ("out", "doubtful") for x in r["rows"])


def test_injury_history_counts_missed_games_and_snaps():
    import sqlite3
    import inj_history as IH
    from adapters import nflverse as nv
    con = sqlite3.connect(config.DB if hasattr(config, "DB") else "data/nfl.db")
    r = nv.get("roster", config.SEASON)
    r = r[r.status == "ACT"].dropna(subset=["gsis_id", "pfr_id"]).iloc[0]
    h = IH.history(con, r.gsis_id, r.team, 8, name=r.full_name)
    assert h["tg"] >= 5 and h["gp"] <= h["tg"] and h["streak"] <= h["missed"] <= h["tg"] and h["text"]
    assert IH.history(con, None, "NE", 8) is None
