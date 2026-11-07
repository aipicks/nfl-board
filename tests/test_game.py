import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

import config
import db
from model import dist, game as G, qb as QB, ratings as R


def test_margin_distribution_is_lumpy_at_key_numbers():
    # a normal curve (sd 13.2) puts ~3% on exactly 3; the real distribution puts far more
    _, push3, _ = dist.home_spread_probs(3.0, -3.0)
    assert push3 > 0.06
    _, push7, _ = dist.home_spread_probs(7.0, -7.0)
    assert push7 > 0.05
    w, p, l = dist.home_spread_probs(3.2, -3.5)
    w2, p2, l2 = dist.home_spread_probs(3.2, -2.5)
    assert w2 - w > 0.055 and p == 0 and p2 == 0          # crossing the 3 is worth many points of probability


def test_distribution_probabilities_sum_to_one_and_are_monotone():
    for mu in (-10, -3, 0, 4.5, 13):
        assert sum(dist.home_spread_probs(mu, -2.5)) == pytest.approx(1)
    assert dist.home_moneyline_probs(7)[0] > dist.home_moneyline_probs(0)[0] > dist.home_moneyline_probs(-7)[0]
    assert dist.over_probs(50, 44.5)[0] > dist.over_probs(44, 44.5)[0] > dist.over_probs(38, 44.5)[0]


def test_distribution_mean_matches_projection():
    for mu in (-6.3, 0.0, 2.2, 9.9):
        pmf = dist._load()[0].pmf(mu)
        assert float((pmf.index.values * pmf.values).sum()) == pytest.approx(mu, abs=0.35)


def test_weather_adjustments():
    assert G._weather_adj(None) == (0.0, "")
    assert G._weather_adj({"indoor": 1, "wind_mph": 30}) == (0.0, "")                   # domes ignore weather
    a, _ = G._weather_adj({"indoor": 0, "wind_mph": 25, "precip_pct": 0, "conditions": "Clear", "temp_f": 60})
    assert a == pytest.approx(config.WIND_TOTAL_PER_MPH * 10)
    a, _ = G._weather_adj({"indoor": 0, "wind_mph": 5, "precip_pct": 10, "conditions": "Definite Rain Showers", "temp_f": 60})
    assert a == config.RAIN_TOTAL_ADJ
    a, _ = G._weather_adj({"indoor": 0, "wind_mph": 5, "precip_pct": 0, "conditions": "Clear", "temp_f": 15})
    assert a == config.COLD_TOTAL_ADJ
    a, _ = G._weather_adj({"indoor": 0, "wind_mph": 60, "precip_pct": 0, "conditions": "Clear", "temp_f": 60})
    assert a == -3.0                                                                      # capped


def test_rest():
    assert G._rest(14) == config.REST_BYE_BONUS and G._rest(4) == config.REST_SHORT_PENALTY and G._rest(7) == 0
    assert G._rest(None) == 0


def test_ratings_recover_known_strengths():
    teams = ["A", "B", "C", "D"]
    rows = []
    for w in range(1, 13):
        for h, a in (("A", "B"), ("C", "D")) if w % 2 else (("A", "C"), ("B", "D")):
            for team, opp in ((h, a), (a, h)):
                rows.append({"team": team, "opp": opp, "t": w, "off_epa_pass": 0.2 if team == "A" else 0.0, "off_epa_rush": 0.0,
                             "off_sr": 0.45, "plays": 60.0})
    tg = pd.DataFrame(rows)
    r = R.fit(tg, 13, half_life=100, ridge=0.5)
    assert r["pass"]["off"]["A"] > 0.1 and abs(r["pass"]["off"]["B"]) < 0.08
    assert R.project_epa(r, "A", "B")["epa_pass"] > R.project_epa(r, "B", "A")["epa_pass"]


def test_qb_adjustment_direction():
    qg = pd.DataFrame({"player_id": ["s", "b"] * 6, "team": ["X"] * 12, "t": list(range(1, 7)) * 2,
                       "db": [35, 5] * 6, "epa": [7.0, -1.0] * 6, "name": ["S", "B"] * 6})
    shr = QB.shrunk_epa(qg)
    depth = pd.DataFrame({"team": ["X", "X"], "pos_abb": ["QB", "QB"], "gsis_id": ["s", "b"], "pos_rank": [1, 2], "player_name": ["S", "B"]})
    healthy, _ = QB.qb_adjustment(qg, shr, depth, {}, "X", 7, 38)
    out, _ = QB.qb_adjustment(qg, shr, depth, {"s": "out"}, "X", 7, 38)
    q, _ = QB.qb_adjustment(qg, shr, depth, {"s": "questionable"}, "X", 7, 38)
    assert out < q < healthy + 1e-9 and out < -1.0


def test_board_pipeline_smoke_and_ev_consistency():
    """Guards the weekly step: gather -> project -> evaluate runs on the live DB and every option is internally consistent."""
    import board_data
    ctx, res = board_data.run(db.connect())
    assert res, "no games evaluated"
    from model.devig import ev as ev_fn, to_decimal
    for r in res:
        assert 20 < r["total"] < 75 and abs(r["margin"]) < 30
        for m, v in r["markets"].items():
            for o in v["options"]:
                assert 0 < o["p_final"] < 1 and o["p_push"] >= 0
                exp = o["p_final"] * (1 - o["p_push"]) * (to_decimal(o["price"]) - 1) - (1 - o["p_final"]) * (1 - o["p_push"])
                assert o["ev"] == pytest.approx(exp, abs=1e-9)
            if v["best"]:
                assert v["best"]["ev"] == max(o["ev"] for o in v["options"])


def test_blend_weight_bounds_final_probability_between_model_and_market():
    for r in __import__("board_data").run(db.connect())[1][:4]:
        for v in r["markets"].values():
            for o in v["options"]:
                lo, hi = sorted((o["p_model"], o["p_market"]))
                assert lo - 1e-9 <= o["p_final"] <= hi + 1e-9


def _synthetic(qb_effect=0.0, flag_rows=()):
    rows = []
    rng = np.random.default_rng(0)
    for w in range(1, 17):
        for h, a in (("A", "B"), ("C", "D")) if w % 2 else (("A", "C"), ("B", "D")):
            for team, opp in ((h, a), (a, h)):
                qb = 0.15 if (team == "A" and w % 2) else -0.05
                rows.append({"team": team, "opp": opp, "t": w, "off_epa_pass": 0.05 + qb_effect * qb + rng.normal(0, 0.02),
                             "off_epa_rush": 0.0, "off_sr": 0.45, "plays": 60.0, "qb_epa": qb,
                             "flag_w": 0.2 if (team, w) in flag_rows else 1.0})
    return pd.DataFrame(rows)


def test_qb_covariate_is_learned_and_moves_the_projection():
    r = R.fit(_synthetic(qb_effect=1.0), 17, half_life=100, ridge=1.0)
    assert r["pass"]["qb_beta"] > 0.5
    base = R.project_epa(r, "A", "B")["epa_pass"]
    assert R.project_epa(r, "A", "B", qb_epa=0.15)["epa_pass"] > base > R.project_epa(r, "A", "B", qb_epa=-0.2)["epa_pass"]


def test_game_flag_downweights_an_outlier_game():
    tg = _synthetic(0.0)
    tg.loc[(tg.team == "A") & (tg.t == 15), "off_epa_pass"] = -2.0          # one disastrous (e.g. heavy-rain) game
    flagged = tg.assign(flag_w=np.where((tg.team == "A") & (tg.t == 15), 0.1, 1.0))
    a_plain = R.fit(tg, 17, half_life=100, ridge=1.0)["pass"]["off"]["A"]
    a_flag = R.fit(flagged, 17, half_life=100, ridge=1.0)["pass"]["off"]["A"]
    assert a_flag > a_plain + 0.005          # the blame is shared with the opponent defence, so the shift is modest


def test_backup_qb_prior_is_below_experienced_starter():
    qg = pd.DataFrame({"player_id": ["vet"] * 8 + ["backup"], "db": [60] * 8 + [10], "epa": [0.0] * 8 + [0.0], "team": "X", "t": list(range(1, 10)), "name": "n"})
    s = QB.shrunk_epa(qg)
    assert s["backup"] < s["vet"] and s["backup"] < 0.0 <= s["vet"] + 1e-9


def test_neutral_site_has_no_home_field(monkeypatch):
    assert config.HFA_NEUTRAL == 0.0 and config.HFA > 0
