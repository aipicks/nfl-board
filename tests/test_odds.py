import json
from pathlib import Path
import pandas as pd
import pytest
from model import devig as d, odds_view as ov
from adapters import sgo

FIX = Path(__file__).parent / "sgo_fixture.json"


def test_conversions_roundtrip():
    assert d.to_prob(-110) == pytest.approx(0.5238, abs=1e-4)
    assert d.to_prob(+150) == pytest.approx(0.4)
    assert d.to_decimal(-200) == pytest.approx(1.5) and d.to_decimal(+250) == pytest.approx(3.5)
    for a in (-300, -110, 105, 250):
        assert d.to_american(d.to_prob(a)) == a


def test_devig_pair_sums_to_one_and_removes_margin():
    a, b = d.devig_pair(-110, -110)
    assert a == pytest.approx(0.5) and b == pytest.approx(0.5)
    a, b = d.devig_pair(-150, +130)
    assert a + b == pytest.approx(1) and a > 0.5 > b and a < d.to_prob(-150)


def test_devig_single_uses_assumed_hold():
    assert d.devig_single(+300, 0.0) == pytest.approx(0.25)
    assert d.devig_single(+300, 0.10) == pytest.approx(0.25 / 1.10)


def test_ev_formula_and_push():
    assert d.ev(0.5, +100) == pytest.approx(0.0)
    assert d.ev(0.55, -110) == pytest.approx(0.55 * (100 / 110) - 0.45)
    # push refunds stake: p_win .45, p_push .1, p_loss .45
    assert d.ev(0.45, +100, p_push=0.1) == pytest.approx(0.0)


def test_labels_thresholds():
    assert [d.label(x) for x in (0.05, 0.03, 0.02, 0.01, 0.009, -0.1)] == ["BET", "BET", "LEAN", "LEAN", "PASS", "PASS"]


def test_blend_5050_in_logit_space():
    assert d.blend(0.6, 0.6, 0.5) == pytest.approx(0.6)
    p = d.blend(0.7, 0.5, 0.5)
    assert 0.5 < p < 0.7 and p == pytest.approx(0.6, abs=0.012)   # logit midpoint of .7 and .5
    assert d.blend(0.8, 0.4, 1.0) == pytest.approx(0.8) and d.blend(0.8, 0.4, 0.0) == pytest.approx(0.4)


def test_key_numbers():
    assert d.key_numbers_crossed(-2.5, -3.5) == [-3]
    assert d.key_numbers_crossed(-6.5, -7.5) == [-7]
    assert d.key_numbers_crossed(2.5, -3.5) == [-3]
    assert d.key_numbers_crossed(4.0, -3.5) == [3, -3]
    assert d.key_numbers_crossed(-3.5, -3.5) == []
    assert d.key_numbers_crossed(-4.5, -5.5) == []


def _parsed():
    players = pd.DataFrame({"player_id": ["00-W", "00-L"], "name": ["Christian Watson", "Jordan Love"], "team": ["GB", "GB"]})
    games = pd.DataFrame({"game_id": ["G1"], "home": ["GB"], "away": ["CHI"], "kickoff_utc": ["2026-10-11T17:00Z"]})
    return sgo.parse(FIX, "2026-10-09T00:00:00Z", players, games)


def test_parse_five_books_only_and_markets():
    rows, ev_map, unmatched = _parsed()
    assert set(rows.book) <= {"fanduel", "draftkings", "betmgm", "espnbet", "bovada"}
    assert set(rows.market) == {"spread", "moneyline", "total", "td_any", "pass_yds"}   # no team totals, no 1q props
    assert unmatched == [] and ev_map
    assert set(rows[rows.market == "pass_yds"].player_id) == {"00-L"}
    tot = rows[(rows.market == "total") & (rows.book == "fanduel")]
    assert tot.line.between(30, 70).all()                     # game total, not a ~22 team total


def test_wide_normalises_spread_to_home_perspective():
    rows, _, _ = _parsed()
    w = ov.wide(rows)
    sp = w[(w.market == "spread") & (w.book == "fanduel")]
    assert len(sp) == 1 and sp.price_a.notna().all() and sp.price_b.notna().all()
    away = rows[(rows.market == "spread") & (rows.book == "fanduel") & (rows.side == "away")].line.iloc[0]
    assert sp.line.iloc[0] == -away


def test_consensus_fair_prob_between_0_and_1_and_per_line():
    rows, _, _ = _parsed()
    w = ov.wide(rows)
    c = ov.consensus(w[w.market == "total"])
    assert 0.4 < c["p_a"] < 0.6 and c["n_books"] >= 1
    assert len(ov.all_lines(w[w.market == "total"])) >= 1


def test_player_entry_without_name_does_not_crash():
    sp = {"JOHN_DOE_1_NFL": {"playerID": "JOHN_DOE_1_NFL", "teamID": "GREEN_BAY_PACKERS_NFL", "firstName": "John", "lastName": "Doe"},
          "X_1_NFL": {"playerID": "X_1_NFL"}}
    players = pd.DataFrame({"player_id": ["p1"], "name": ["John Doe"], "team": ["GB"]})
    m = sgo.match_players(sp, players)
    assert m["JOHN_DOE_1_NFL"] == "p1" and m["X_1_NFL"].startswith("sgo:")
