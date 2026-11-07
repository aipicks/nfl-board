import json
from pathlib import Path
import pandas as pd
import pytest
from adapters import injuries, splits, weather
from adapters.names import norm_name, attach_player_ids
from model import public

T = Path(__file__).parent


def test_weather_parse_domes_nicknames_and_numbers():
    d = weather.parse((T / "weather_fixture.html").read_text(encoding="utf-8"))
    assert set(zip(d.away, d.home)) == {("MIN", "NO"), ("NYG", "WAS"), ("DET", "ARI")}   # "Washington" quirk handled
    no = d[d.home == "NO"].iloc[0]
    assert no.indoor == 1                                  # dome icon
    az = d[d.home == "ARI"].iloc[0]
    assert az.wind_mph > 0 and 0 < az.temp_f < 130 and 0 <= az.precip_pct <= 100


def test_weather_roof_from_schedule_marks_indoor():
    d = pd.DataFrame({"home": ["X"], "away": ["Y"], "indoor": [0], "temp_f": [50], "wind_mph": [5], "precip_pct": [0], "conditions": [""]})
    g = pd.DataFrame({"game_id": ["g"], "home": ["X"], "away": ["Y"], "roof": ["closed"]})
    assert weather.to_games(d, g).indoor.iloc[0] == 1


def test_splits_parse_tickets_vs_money():
    j = json.loads((T / "sbd_fixture.json").read_text())
    g0 = j["data"][0]["competitors"]
    games = pd.DataFrame({"game_id": ["G"], "home": [g0["home"]["abbreviation"]], "away": [g0["away"]["abbreviation"]],
                          "kickoff_utc": [j["data"][0]["scheduled"][:16] + "Z"]})
    df = splits.parse(j, games)
    assert set(df.market) == {"moneyline", "spread", "total"} and len(df) == 6
    pair = df[df.market == "spread"]
    assert pair.tickets_pct.sum() == pytest.approx(100, abs=0.1) and pair.money_pct.sum() == pytest.approx(100, abs=0.1)


def test_split_signal_and_cap():
    assert public.split_signal(30, 45)[0] == "sharp"
    assert public.split_signal(75, 60)[0] == "public"
    assert public.split_signal(52, 55)[0] == "neutral"
    assert public.capped_adjustment(60, 0.75) == 0.75 and public.capped_adjustment(-60, 0.75) == -0.75
    assert public.capped_adjustment(15, 0.75) == pytest.approx(0.375)


def test_injury_status_mapping():
    m = injuries.map_status
    assert (m("Out"), m("Injured Reserve"), m("Doubtful"), m("Questionable"), m("Active")) == ("out", "out", "doubtful", "questionable", "healthy")
    assert m("Physically Unable to Perform") == "out" and m("Day-To-Day") == "questionable" and m(float("nan")) is None


def test_name_matching_suffix_punctuation_and_team_tiebreak():
    assert norm_name("D'Andre Swift") == norm_name("DAndre Swift") and norm_name("Robert Beal Jr.") == "robert beal"
    p = pd.DataFrame({"player_id": ["a", "b"], "name": ["Mike Williams", "Mike Williams"], "team": ["NYJ", "PIT"]})
    r = attach_player_ids(pd.DataFrame({"name": ["Mike Williams"], "team": ["PIT"]}), p)
    assert r.player_id.iloc[0] == "b"
    assert attach_player_ids(pd.DataFrame({"name": ["Nobody Here"], "team": ["PIT"]}), p).player_id.iloc[0] is None
