"""Regression tests: one per correction recorded in lessons.md, so the same mistake cannot come back."""
import json

import numpy as np
import pandas as pd
import pytest

import config
import db
import learning
from model import injuries as INJ, td as T


def _prof(rows):
    return pd.DataFrame(rows).set_index("id")[["team"] + T.BANDS].astype(float) if False else pd.DataFrame(
        [{"id": r["id"], "team": r["team"], **{b: r.get(b, 0.0) for b in T.BANDS}} for r in rows]).set_index("id")


def test_lone_healthy_running_back_becomes_the_lead_back():
    """Eagles case: Barkley out, Shipley out, Pierce is the only back with a role. His carries must rise sharply, not stay a backup's."""
    prof = _prof([{"id": "barkley", "team": "PHI", "car_out": 12.0, "car_rz": 1.5, "car_gl": 0.7}, {"id": "shipley", "team": "PHI", "car_out": 2.5, "car_rz": 0.2},
                  {"id": "pierce", "team": "PHI", "car_out": 6.0, "car_rz": 0.5, "car_gl": 0.1}, {"id": "steele", "team": "PHI", "car_out": 0.3}])
    pos = pd.Series({"barkley": "RB", "shipley": "RB", "pierce": "RB", "steele": "RB"})
    out = T.redistribute(prof, pos, {"barkley": 1.0, "shipley": 1.0})
    car = lambda d, i: d.loc[i, ["car_out", "car_rz", "car_gl"]].sum()
    assert car(out, "pierce") > 2.0 * car(prof, "pierce")
    assert car(out, "barkley") == 0 and car(out, "shipley") == 0
    group_before = sum(car(prof, i) for i in prof.index)
    group_after = sum(car(out, i) for i in prof.index)
    assert group_after == pytest.approx(group_before)                       # the group's carries are conserved, not lost


def test_no_consolidation_when_nobody_is_missing():
    prof = _prof([{"id": "a", "team": "X", "car_out": 10.0}, {"id": "b", "team": "X", "car_out": 5.0}])
    out = T.redistribute(prof, pd.Series({"a": "RB", "b": "RB"}), {})
    assert out.car_out.tolist() == [10.0, 5.0]


def test_missing_backs_targets_mostly_stay_with_remaining_backs():
    prof = _prof([{"id": "rb1", "team": "X", "tgt_out": 3.0}, {"id": "rb2", "team": "X", "tgt_out": 1.0}, {"id": "wr1", "team": "X", "tgt_out": 7.0}])
    pos = pd.Series({"rb1": "RB", "rb2": "RB", "wr1": "WR"})
    out = T.redistribute(prof, pos, {"rb1": 1.0})
    gain_rb, gain_wr = out.loc["rb2", "tgt_out"] - 1.0, out.loc["wr1", "tgt_out"] - 7.0
    assert gain_rb > gain_wr * 1.0 and gain_rb + gain_wr == pytest.approx(3.0)


def _inj(rows):
    return pd.DataFrame(rows, columns=["name", "team", "pos", "status"])


def test_line_and_defence_injuries_move_the_game():
    shares = {"alpha cb": 1.0, "beta ol": 0.95, "gamma s": 0.9, "bench guy": 0.05}
    inj = _inj([("Alpha CB", "X", "CB", "out"), ("Beta OL", "X", "T", "out"), ("Gamma S", "X", "S", "questionable"), ("Bench Guy", "X", "LB", "out"), ("Q", "Y", "CB", "out")])
    g = INJ.group_losses(inj, "X", shares)
    assert g["def"] == pytest.approx(config.INJ_PTS["CB"] * 1.0 + config.INJ_PTS["S"] * 0.9 * (1 - config.PLAY_PROB["questionable"]), abs=1e-6)     # a questionable safety misses 25%
    assert g["off"] == pytest.approx(config.INJ_PTS["OL"] * 0.95)
    assert INJ.group_losses(inj, "Y", shares)["off"] == 0                                                         # other team untouched
    many = _inj([(f"p{i}", "X", "CB", "out") for i in range(12)])
    assert INJ.group_losses(many, "X", {f"p{i}": 1.0 for i in range(12)})["def"] == config.INJ_CAP_GROUP         # capped


def test_active_roster_filter_excludes_ir_and_practice_squad(monkeypatch):
    ros = pd.DataFrame({"week": [6, 6, 6, 6], "status": ["ACT", "RES", "DEV", "CUT"], "gsis_id": ["a", "b", "c", "d"]})
    monkeypatch.setattr(INJ.nv, "get", lambda kind, season, **k: ros)
    assert INJ.active_ids(2026) == {"a"}


# ---------------- learning loop ----------------
@pytest.fixture()
def learn_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(learning, "LEARNED", tmp_path / "learned.json")
    monkeypatch.setattr(learning, "ROOT", tmp_path)
    return db.connect()


def _log(con, n, market, p_model, p_market, wins, **extra):
    for i in range(n):
        con.execute("insert into pred_log(game_id, market, side, book, price, p_model, p_market, p_final, ev, label, is_parlay_leg, result, extra) values (?,?,?,?,?,?,?,?,?,?,0,?,?)",
                    (f"g{i}", market, "home", "fanduel", -110, p_model, p_market, 0.5, 0.0, "PASS", "win" if i < wins else "loss", json.dumps(extra)))
    con.commit()


def test_learning_waits_for_enough_graded_picks(learn_db):
    _log(learn_db, 40, "spread", 0.6, 0.5, 30, proj_margin=3.0)
    assert learning.adjust(learn_db) == []


def test_learning_moves_only_within_bounds_and_logs_it(learn_db, monkeypatch):
    monkeypatch.setitem(config.MODEL_TRUST, "margin", 0.15)
    _log(learn_db, 120, "spread", 0.62, 0.50, 100, proj_margin=3.0)        # model said 62%, market 50%, and it won 83%: model deserves far more trust
    ch = learning.adjust(learn_db)
    c = next(x for x in ch if x["param"] == "MODEL_TRUST.margin")
    assert 0.15 < c["value"] <= 0.6                                          # moved up, inside the hard bound, damped
    assert json.loads(learning.LEARNED.read_text())["MODEL_TRUST.margin"]["value"] == c["value"]
    assert (learning.ROOT / "lessons_auto.md").read_text().count("MODEL_TRUST.margin") == 1


def test_learning_never_exceeds_hard_bounds(learn_db, monkeypatch):
    monkeypatch.setattr(config, "TD_LAMBDA_SCALE", 1.15)
    _log(learn_db, 400, "td_any", 0.10, 0.10, 380, lam=0.1)                  # absurdly good outcomes: scale wants to explode
    for _ in range(5):
        learning.adjust(learn_db)
        monkeypatch.setattr(config, "TD_LAMBDA_SCALE", json.loads(learning.LEARNED.read_text())["TD_LAMBDA_SCALE"]["value"])
    assert 0.8 <= config.TD_LAMBDA_SCALE <= 1.2


def test_lessons_file_parses_and_covers_the_corrections():
    L = learning.lessons_text()
    titles = " ".join(x["title"].lower() for x in L)
    for key in ("projection says covers", "injuries matter", "2026 team stats", "keep learning"):
        assert key in titles
