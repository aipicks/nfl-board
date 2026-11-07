import best_props as bp


def test_price_window():
    assert bp.PRICE_LO == -140 and bp.PRICE_HI == 120


def test_slot_counts():
    assert {k: v[1] for k, v in bp.SLOTS.items()} == {"QB": 1, "WR": 2, "RB": 2, "TE": 1}


def test_every_pick_in_price_window_and_unique_per_game():
    import build_board
    d = build_board.payload(log=False)
    for gid, c in d["bestprops"]["games"].items():
        names = [p["player"] for ps in c.values() for p in ps]
        assert len(names) == len(set(names))
        for s, ps in c.items():
            assert len(ps) == bp.SLOTS[s][1]           # every game gets its full slate
            for p in ps:
                assert bp.PRICE_LO <= p["price"] <= bp.PRICE_HI
                assert p.get("relaxed") or p["p_model"] >= (0.30 if p["kind"] == "td" else 0.55)


def test_props_use_this_season_only_and_have_matchup_fields():
    import build_board, config
    d = build_board.payload(log=False)
    for r in d["props"]:
        assert r["avg25"] is None                      # last season is not used for props
        assert len(r["series"]) == min(8, r["n26"])    # recent-games list only holds 2026 games
        assert r["opp_run_rk"] is None or 1 <= r["opp_run_rk"] <= 32


def test_mnf_picks_are_five_unique_players_ranked_by_win_chance():
    import best_props as bp
    from datetime import datetime, timezone
    g = {"id": "g1", "home": "SEA", "away": "CHI", "kickoff": "2026-11-03T01:15Z", "margin": 3.4, "total": 42.4, "pts_home": 22.9, "pts_away": 19.5, "weather": None,
         "markets": {"spread": {"best": {"side": "home", "line": -3.5, "book": "betmgm", "price": -102, "p_model": .49, "p_market": .48, "p_final": .488, "ev": -.03}},
                     "total": {"best": {"side": "under", "line": 46.5, "book": "betmgm", "price": -108, "p_model": .52, "p_market": .5, "p_final": .512, "ev": -.01}}}}
    picks = {s: [{"player_id": f"{s}{i}", "player": f"{s}{i}", "p_final": .5 + .01 * i, "kind": "prop"} for i in range(2)] for s in ("QB", "WR", "RB", "TE")}
    out = bp.mnf({"g1": picks}, [g], now=datetime(2026, 11, 2, 12, tzinfo=timezone.utc))
    ps = out["picks"]
    assert len(ps) == 5 and len({p["player_id"] for p in ps}) == 5
    assert [p["p_final"] for p in ps] == sorted((p["p_final"] for p in ps), reverse=True)
    assert bp.mnf({"g1": picks}, [g], now=datetime(2026, 11, 4, tzinfo=timezone.utc)) is None


def test_mnf_away_spread_pick_shows_the_away_teams_line():
    import best_props as bp
    g = {"id": "g1", "home": "SEA", "away": "CHI", "margin": -3.0, "total": 42.0, "pts_home": 20, "pts_away": 23, "weather": None,
         "markets": {"spread": {"best": {"side": "away", "line": -3.5, "book": "betmgm", "price": -110, "p_model": .55, "p_market": .5, "p_final": .53, "ev": .02}}}}
    p = bp._game_bets(g)[0]
    assert p["pick"] == "CHI +3.5"      # the home line of -3.5 means the away team gets +3.5
