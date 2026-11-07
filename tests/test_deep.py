import json
import db
import deep_dive as D


def test_deep_dive_builds_and_is_json_serialisable():
    """Guards the deep-dive step of the weekly update: every section present, ranks within 1..32, props internally consistent."""
    con = db.connect()
    gid = con.execute("select game_id from games where season=2026 and home_score is null and sgo_event_id is not null order by kickoff_utc limit 1").fetchone()[0]
    d = D._clean(D.build(gid, con))
    json.dumps(d)
    for k in ("metrics", "pos_allowed", "weather", "weather_history", "kicking", "history", "injuries", "projection", "dist", "players", "dynamics", "qbs", "usage"):
        assert d[k], k
    for side in ("off", "def"):
        for r in d["metrics"][side]:
            for t in (d["away"], d["home"]):
                for rk in (r[t]["r26"], r[t]["r25"]):
                    assert rk is None or 1 <= rk <= 32
    assert abs(sum(v for _, v in d["dist"]["margin"]) - 1) < 0.1
    for p in d["players"]["props"]:
        for o in p["options"]:
            assert 0 < o["p_final"] < 1
            lo, hi = sorted((o["p_model"], o["p_market"]))
            assert lo - 1e-3 <= o["p_final"] <= hi + 1e-3
    h = d["weather"]["hours"][d["weather"]["kickoff_hour_index"]]
    assert -30 < h["temperature_2m"] < 125 and 0 <= h["windspeed_10m"] < 80
