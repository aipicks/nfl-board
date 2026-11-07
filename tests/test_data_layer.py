import pandas as pd
import validate
import db
from data_layer import team_week, usage_from_pbp
from adapters import nflverse as nv


def _pbp():
    return pd.DataFrame({
        "season": [2026] * 4, "week": [1] * 4, "season_type": ["REG"] * 4, "posteam": ["LAR", "LAR", "LAR", "LAR"],
        "defteam": ["SEA"] * 4, "epa": [1.0, -1.0, 0.5, 0.5], "success": [1, 0, 1, 1], "pass": [1, 1, 0, 0],
        "rush": [0, 0, 1, 1], "qb_kneel": [0] * 4, "qb_spike": [0] * 4,
        "yardline_100": [3, 30, 15, 2], "play_type": ["pass", "pass", "run", "run"], "play_id": [1, 2, 3, 4],
        "receiver_player_id": ["A", "A", None, None], "rusher_player_id": [None, None, "B", "B"]})


def test_team_week_epa_split_and_code_normalised():
    t = team_week(_pbp())
    assert set(t.team) == {"LA", "SEA"}
    r = t[t.team == "LA"].iloc[0]
    assert r.plays == 4 and r.off_epa_pass == 0.0 and r.off_epa_rush == 0.5 and r.off_sr == 0.75


def test_usage_red_zone_and_goal_line():
    u = usage_from_pbp(_pbp()).set_index("player_id")
    assert u.loc["A", "rz_targets"] == 1 and u.loc["A", "gl_targets"] == 1
    assert u.loc["B", "rz_carries"] == 2 and u.loc["B", "gl_carries"] == 1


def test_team_codes_normalise():
    assert list(nv.norm_team(pd.Series(["LAR", "WSH", "KC"]))) == ["LA", "WAS", "KC"]


def test_validation_all_pass_on_built_db():
    """Guards the weekly-update step: if data_layer output is wrong, this fails (network checks skipped)."""
    out = validate.run_all(db.connect(), espn_check=False)
    assert [n for n, ok, _ in out if not ok] == []
