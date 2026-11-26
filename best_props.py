"""Best Props: for every game, the props we are MOST CONFIDENT will win (not the most +EV).

Per game: 1 quarterback prop, 2 wide-receiver props, 2 running-back props, 1 tight-end prop, each priced between +120 and -140 at one of the
five books. A candidate must be one our model supports (about 55%+ on its own) that the market does not strongly oppose; the ranking is the
final win probability (70% model / 30% market after the usual shrink). Anytime TDs can fill a receiver / back / tight-end slot when the price
is in range. Each pick comes with the reasons (projection vs line, recent games, opposing defence, injuries, game script) and the risks.
"""
import numpy as np

import config

PRICE_LO, PRICE_HI = -140, 120
SLOTS = {"QB": ({"pass_yds", "pass_comp", "pass_att", "pass_td", "pass_int"}, 1), "WR": ({"rec_yds", "receptions"}, 2),
         "RB": ({"rush_yds", "rush_att", "receptions", "rec_yds", "rush_rec_yds"}, 2), "TE": ({"rec_yds", "receptions"}, 1)}
LABEL = {"pass_yds": "passing yards", "rush_yds": "rushing yards", "rec_yds": "receiving yards", "receptions": "receptions", "rush_att": "rushing attempts", "pass_td": "passing TDs",
         "pass_comp": "completions", "pass_att": "pass attempts", "pass_int": "interceptions", "rush_rec_yds": "rush + receiving yards", "pass_rush_yds": "pass + rush yards", "td_any": "anytime TD"}
PASS_MKTS = {"pass_yds", "pass_comp", "pass_att", "pass_td", "rec_yds", "receptions", "pass_rush_yds"}
GRP = {"WR": ("WR",), "TE": ("TE",), "RB": ("RB", "FB"), "QB": ("QB",)}


def _in_range(p):
    return PRICE_LO <= p <= PRICE_HI


def _conf(p):
    return ("High confidence", "g") if p >= 0.62 else ("Good confidence", "y") if p >= 0.57 else ("Lean", "y")


def _pick_from_prop(row, o):
    return {"kind": "prop", "slot": None, "player": row["player"], "player_id": row["player_id"], "pos": row["pos"], "team": row["team"], "opp": row["opp"], "market": row["market"],
            "label": LABEL.get(row["market"], row["market"]), "side": o["side"], "line": o["line"], "book": o["book"], "price": o["price"], "p_final": o["p_final"],
            "p_model": o["p_model"], "p_market": o["p_market"], "mu": row["mu"], "sd": row["sd"], "status": row["status"], "series": row["series"], "n26": row["n26"],
            "avg26": row["avg26"], "avg25": row["avg25"], "opp_pa26": row["opp_pa26"], "opp_rk26": row["opp_rk26"], "opp_lg26": row["opp_lg26"], "opp_stat": row["opp_stat"],
            "wind_f": row.get("wind_f", 1.0), "limited": row["limited"], "game_id": row["game_id"], "home": row["home"],
            "opp_run_rk": row.get("opp_run_rk"), "opp_pass_rk": row.get("opp_pass_rk"), "att_mm": row.get("att_mm", 1.0), "car_mm": row.get("car_mm", 1.0)}


def _pick_from_td(t):
    prices = {b: p for b, p in t["prices"].items() if _in_range(p)}
    if not prices:
        return None
    b = max(prices, key=prices.get)
    return {"kind": "td", "slot": None, "player": t["player"], "player_id": t["player_id"], "pos": t["pos"], "team": t["team"], "opp": t["opp"], "market": "td_any", "label": "anytime TD",
            "side": "yes", "line": None, "book": b, "price": prices[b], "p_final": t["p_final"], "p_model": t["p_model"], "p_market": t["p_market"], "mu": None, "sd": None, "status": t["status"],
            "series": [], "n26": t["games"], "avg26": None, "avg25": None, "opp_pa26": t.get("opp_td_pg"), "opp_rk26": t.get("opp_td_rank"), "opp_lg26": t.get("opp_td_lg"), "opp_stat": f"{t['pos']} TDs",
            "wind_f": 1.0, "limited": t["limited"], "game_id": t["game_id"], "home": t["home"], "td": t}


def _why(p, d, g):
    """Reasons and risks for one pick. d = deep dive of the game, g = game row (projection, weather)."""
    why, risk = [], []
    over = p["side"] in ("over", "yes")
    if p["kind"] == "prop":
        diff = p["mu"] - p["line"]
        win_edge = diff if p["side"] == "over" else -diff
        why.append(f"We project {p['mu']:.1f} {p['label']} against a line of {p['line']:g}: {abs(diff):.1f} {'above' if diff >= 0 else 'below'} it ({'supports' if win_edge > 0 else 'does not support'} the {p['side']}).")
        s = p["series"]
        if s:
            hit = sum(1 for v in s if (v > p["line"] if p["side"] == "over" else v < p["line"]))
            why.append(f"The {p['side']} hit in {hit} of his {len(s)} games this season (by game: {', '.join(f'{v:g}' for v in s)}).")
        if p["avg26"] is not None and p["n26"]:
            why.append(f"2026 average {p['avg26']:g} over {p['n26']} game{'s' if p['n26'] != 1 else ''}.")
        rr, pr = p.get("opp_run_rk"), p.get("opp_pass_rk")
        if rr and pr:
            ru = "elite" if rr <= 5 else "good" if rr <= 12 else "average" if rr <= 20 else "weak" if rr <= 27 else "one of the worst"
            pa = "elite" if pr <= 5 else "good" if pr <= 12 else "average" if pr <= 20 else "weak" if pr <= 27 else "one of the worst"
            sh = (p["att_mm"] - 1) * 100
            if p["market"] in ("pass_att", "pass_comp", "pass_yds", "pass_td", "rec_yds", "receptions", "pass_rush_yds") and abs(sh) >= 0.8:
                why.append(f"Matchup: {p['opp']}'s run defence is {ru} (#{rr} of 32) and its pass defence is {pa} (#{pr}), which {'pushes' if sh > 0 else 'pulls'} {p['team']} {'toward' if sh > 0 else 'away from'} throwing ({sh:+.1f}% pass attempts).")
            elif p["market"] in ("rush_att", "rush_yds", "rush_rec_yds") and abs((p["car_mm"] - 1) * 100) >= 0.8:
                why.append(f"Matchup: {p['opp']}'s run defence is {ru} (#{rr} of 32) and its pass defence is {pa} (#{pr}), so {p['team']} carries move {(p['car_mm'] - 1) * 100:+.1f}%.")
    else:
        t = p["td"]
        why.append(f"Our model gives {p['team']} {p['pos']} {p['player']} a {t['p_model'] * 100:.0f}% chance to score (market {t['p_market'] * 100:.0f}%): about {t['rz_pg']} red-zone and {t['gl_pg']} goal-line touches per game, {t['games_with_td'] if 'games_with_td' in t else t['td_games']} TD games in {t['games']}.")
    if p["opp_rk26"] is not None and p["opp_pa26"] is not None:
        rk = p["opp_rk26"]
        tone = "one of the most generous" if rk <= 8 else "above average" if rk <= 14 else "about average" if rk <= 20 else "stingy" if rk <= 26 else "one of the stingiest"
        why.append(f"{p['opp']} allows {p['opp_pa26']:g} {p['opp_stat'].replace('_', ' ')} per game (rank #{rk} of 32, {tone}; league {p['opp_lg26']:g}).")
        if over and rk >= 24 and p["kind"] == "prop":
            risk.append(f"{p['opp']} has been tough against this position.")
        if not over and rk <= 8 and p["kind"] == "prop":
            risk.append(f"{p['opp']} has been generous to this position, which works against an under.")
    inj = d["injuries"]
    mates = [i for i in inj if i["team"] == p["team"] and i["pos"] in GRP.get(p["pos"], (p["pos"],)) and i["name"] != p["player"] and i["status"] in ("out", "doubtful")
             and ((i.get("tgt") or 0) >= 10 or (i.get("car") or 0) >= 12)]
    if mates:
        names = ", ".join(f"{m['name']} ({m['tgt'] or 0} tgt, {m['car'] or 0} car so far)" for m in mates[:2])
        why.append(f"{names} {'is' if len(mates) == 1 else 'are'} out, so his role should {'grow' if over else 'be watched'}.")
    oppd = [i for i in inj if i["team"] == p["opp"] and i["status"] in ("out", "doubtful") and (i.get("snap_pct") or 0) >= 50]
    if p["market"] in PASS_MKTS:
        sec = [i for i in oppd if i["pos"] in ("CB", "S", "DB")]
        if sec and over:
            why.append(f"{p['opp']} is missing {', '.join(i['name'] for i in sec[:3])} in the secondary.")
    else:
        fr = [i for i in oppd if i["pos"] in ("DT", "DE", "NT", "LB", "OLB", "ILB")]
        if fr and over:
            why.append(f"{p['opp']} is missing {', '.join(i['name'] for i in fr[:3])} up front.")
    # game script
    pts = g["pts_home"] if p["home"] else g["pts_away"]
    margin_team = (g["margin"] if p["home"] else -g["margin"])
    if p["market"] in ("rush_yds", "rush_att", "rush_rec_yds") and over and margin_team >= 3:
        why.append(f"{p['team']} is projected to win by {margin_team:.1f}, which usually means more carries late.")
    if p["market"] in ("rush_yds", "rush_att") and over and margin_team <= -6:
        risk.append(f"{p['team']} is projected to trail by {-margin_team:.1f}; if they fall behind early carries drop.")
    if p["market"] in PASS_MKTS and over and margin_team <= -3:
        why.append(f"{p['team']} is projected to trail by {-margin_team:.1f}, which raises passing volume.")
    if p["market"] in PASS_MKTS and over and margin_team >= 7:
        risk.append(f"{p['team']} is projected to lead by {margin_team:.1f}; a big lead can mean fewer throws late.")
    w = d["weather"]["hours"][d["weather"]["kickoff_hour_index"]]
    if not d.get("indoor") and p["market"] in PASS_MKTS and (w["windspeed_10m"] >= 14 or w["windgusts_10m"] >= 25):
        (why if not over else risk).append(f"Wind {w['windspeed_10m']:.0f} mph (gusts {w['windgusts_10m']:.0f}) {'hurts the passing game, which supports the under' if not over else 'could hurt the passing game'}.")
    if p["status"] == "questionable":
        risk.append("Listed questionable (we treat that as 75% to play); check Sunday's inactives.")
    if p["n26"] is not None and p["n26"] < 4 and p["kind"] == "prop":
        risk.append(f"Only {p['n26']} games of 2026 data.")
    if p["p_market"] < 0.5:
        risk.append(f"The market leans the other way ({p['p_market'] * 100:.0f}% for this side).")
    return why, risk


TIERS = ((0.55, 0.48, 0.30), (0.50, 0.42, 0.20), (0.0, 0.0, 0.0))     # (min model prob, min market prob, min anytime-TD prob): relaxed only to fill an empty slot


def _cands(props, tds, gid, slot, mk, tier, allow_limited):
    pm_min, pk_min, td_min = tier
    cs = []
    for r in props:
        if r["game_id"] != gid or r["pos"] != slot or r["market"] not in mk or r["status"] in ("out", "doubtful") or (r["limited"] and not allow_limited):
            continue
        opts = [o for o in r["opts"] if _in_range(o["price"]) and o["p_model"] >= pm_min and o["p_market"] >= pk_min]
        if opts:
            cs.append(_pick_from_prop(r, max(opts, key=lambda o: o["p_final"])))
    if slot != "QB":
        for t in tds:
            if t["game_id"] == gid and t["pos"] == slot and t["status"] not in ("out", "doubtful") and (not t["limited"] or allow_limited) and t["p_model"] >= td_min:
                p = _pick_from_td(t)
                if p and p["p_market"] >= td_min:
                    cs.append(p)
    return cs


def select(props, tds, deeps, games) -> dict:
    """Every game gets its full slate of picks (1 QB, 2 WR, 2 RB, 1 TE): best-supported first, relaxing the filters only to fill an empty slot."""
    out = {}
    gmap = {g["id"]: g for g in games}
    for gid, d in deeps.items():
        g = gmap[gid]
        cands = {}
        for slot, (mk, n) in SLOTS.items():
            chosen, used = [], set()
            for ti, tier in enumerate(TIERS):
                for allow_limited in ((False,) if ti == 0 else (False, True)):
                    if len(chosen) >= n:
                        break
                    cs = sorted(_cands(props, tds, gid, slot, mk, tier, allow_limited), key=lambda p: -p["p_final"])
                    for p in cs:
                        if p["player_id"] in used:
                            continue
                        p["relaxed"] = ti > 0 or allow_limited
                        chosen.append(p)
                        used.add(p["player_id"])
                        if len(chosen) == n:
                            break
            chosen.sort(key=lambda p: -p["p_final"])
            for p in chosen:
                p["slot"] = slot
                p["why"], p["risk"] = _why(p, d, g)
                if p.get("relaxed"):
                    p["risk"].append("Weaker pick: nothing stronger was available in the +120 to -140 range for this slot.")
                p["conf"], p["conf_cls"] = _conf(p["p_final"])
            cands[slot] = chosen
        out[gid] = cands
    return out


def _game_bets(g):
    """The best spread and total at the five books as pick-shaped dicts, with reasons from our projection."""
    out = []
    for mk in ("spread", "total"):
        b = (g["markets"].get(mk) or {}).get("best")
        if not b:
            continue
        if mk == "spread":
            tm = g["home"] if b["side"] == "home" else g["away"]
            line = b["line"] if b["side"] == "home" else -b["line"]          # stored lines are from the home team's view
            pick = f"{tm} {line:+g}"
            proj = g["margin"] if b["side"] == "home" else -g["margin"]
            why = [f"We project {g['home']} {g['pts_home']:.0f}, {g['away']} {g['pts_away']:.0f}: {tm} {'wins by' if proj > 0 else 'loses by'} {abs(proj):.1f} on average against a line of {line:+g}.",
                   f"Model {b['p_model'] * 100:.0f}% vs market {b['p_market'] * 100:.0f}% to cover (win chance after blending {b['p_final'] * 100:.0f}%)."]
        else:
            pick = f"{b['side'].upper()} {b['line']:g}"
            why = [f"We project {g['total']:.1f} total points ({g['pts_home']:.0f} + {g['pts_away']:.0f}) against a line of {b['line']:g}.",
                   f"Model {b['p_model'] * 100:.0f}% vs market {b['p_market'] * 100:.0f}% on the {b['side']} (win chance after blending {b['p_final'] * 100:.0f}%)."]
            w = g.get("weather") or {}
            if w and not w.get("indoor") and (w.get("wind_mph") or 0) >= 12:
                why.append(f"Wind of {w['wind_mph']:g} mph can hold down the passing game.")
        risk = [f"Expected value is {b['ev'] * 100:+.1f}% at this price: " + ("a real edge." if b["ev"] > 0.03 else "the edge is thin, treat it as a lean.")]
        out.append({"kind": "game", "slot": "GAME", "player": "Spread" if mk == "spread" else "Game total", "player_id": f"game_{mk}", "pos": "GAME", "team": g["away"], "opp": g["home"],
                    "market": mk, "label": mk, "side": b["side"], "line": b["line"], "book": b["book"], "price": b["price"], "pick": pick, "p_final": b["p_final"], "p_model": b["p_model"],
                    "p_market": b["p_market"], "mu": None, "sd": None, "status": "healthy", "series": [], "game_id": g["id"], "home": False, "why": why, "risk": risk})
    return out


def mnf(bp, games, now=None) -> dict | None:
    """The five best bets for the Monday night game: the strongest of the game's best props, anytime TDs, spread and total, ranked by win chance (one per player)."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    now = now or datetime.now(timezone.utc)
    cand = []
    for g in games:
        ko = datetime.strptime(g["kickoff"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        if ko > now and ko.astimezone(ZoneInfo("America/New_York")).weekday() == 0:
            cand.append((ko, g))
    if not cand:
        return None
    _, g = min(cand, key=lambda x: x[0])
    pool = [p for ps in bp.get(g["id"], {}).values() for p in ps] + _game_bets(g)
    pool.sort(key=lambda p: -p["p_final"])
    picks, seen = [], set()
    for p in pool:
        if p["player_id"] in seen:
            continue
        seen.add(p["player_id"])
        q = dict(p)
        q["conf"], q["conf_cls"] = _conf(q["p_final"])
        picks.append(q)
        if len(picks) == 5:
            break
    return {"game_id": g["id"], "away": g["away"], "home": g["home"], "kickoff": g["kickoff"], "picks": picks}


WATCH = [("DK Metcalf", "DK Metcalf"), ("Wan'Dale Robinson", "Wan'Dale Robinson"), ("Garrett Wilson", "Garrett Wilson"), ("Dalton Kincaid", "Dalton Kincaid")]


def watchlist(props, tds, deeps, games) -> list[dict]:
    """A deeper look at players the user flagged: every market we price for them, the side we lean, and why."""
    gmap = {g["id"]: g for g in games}
    out = []
    for key, name in WATCH:
        rows = [r for r in props if r["player"].lower().replace("’", "'") == name.lower() or key.lower() in r["player"].lower()]
        if not rows:
            out.append({"name": name, "found": False})
            continue
        r0 = rows[0]
        g = gmap[r0["game_id"]]
        d = deeps[r0["game_id"]]
        markets = []
        for r in sorted(rows, key=lambda x: x["market"]):
            o = max(r["opts"], key=lambda x: x["p_final"])                                   # the side and price we like most, wherever it sits
            ir = [x for x in r["opts"] if _in_range(x["price"])]
            oi = max(ir, key=lambda x: x["p_final"]) if ir else None
            pk = _pick_from_prop(r, o)
            why, risk = _why(pk, d, g)
            alt = None if (oi is None or oi is o) else {"side": oi["side"], "line": oi["line"], "book": oi["book"], "price": oi["price"], "p_final": oi["p_final"]}
            markets.append({"market": r["market"], "label": LABEL.get(r["market"], r["market"]), "ref_line": r["ref_line"], "mu": r["mu"], "sd": r["sd"], "side": pk["side"], "line": pk["line"], "book": pk["book"],
                            "price": pk["price"], "in_range": _in_range(o["price"]), "alt": alt, "p_final": pk["p_final"], "p_model": pk["p_model"], "p_market": pk["p_market"], "series": r["series"],
                            "hit_over": r["hit_over"], "why": why, "risk": risk, "conf": _conf(pk["p_final"])[0], "conf_cls": _conf(pk["p_final"])[1]})
        tdr = [t for t in tds if t["player_id"] == r0["player_id"]]
        usage = next((u for u in d["usage"] if u["name"] == r0["player"]), None)
        out.append({"name": r0["player"], "found": True, "pos": r0["pos"], "team": r0["team"], "opp": r0["opp"], "status": r0["status"], "game_id": r0["game_id"], "kickoff": r0["kickoff"],
                    "usage": usage, "markets": sorted(markets, key=lambda m: -m["p_final"]),
                    "td": None if not tdr else {"p_model": tdr[0]["p_model"], "p_market": tdr[0]["p_market"], "best_price": tdr[0]["best_price"], "best_book": tdr[0]["best_book"], "p_final": tdr[0]["p_final"]}})
    return out


# ---------------------------------------------------------------------------------------------------------------------------------
# Best Picks card (2026-11-25, user's rules): a short final card instead of every candidate.
#   Sunday main slate (Sunday games before 7 PM ET): 8-12 player props (max 2 per game), 3 spreads, 2 totals.
#   Standalone / primetime games (any non-Sunday game, Sunday night, Monday night): per game 2 player props + 1 game pick
#   (spread or total, whichever has the better edge) + optionally 1 anytime TD when there is real value.
#   Never padded: if fewer picks pass, fewer are shown.
YARD_MKTS = {"pass_yds", "rush_yds", "rec_yds", "rush_rec_yds", "pass_rush_yds"}
MIN_OVER_LINE = {"receptions": 2.5, "rec_yds": 25.5, "rush_yds": 30.5, "rush_att": 10.5}   # no depth-player tiny lines
CARD_P_MIN, CARD_P_MAX, CARD_FIRM = 0.55, 0.72, 0.60
TD_GATE = {"snap": 50, "rb_touch": 8, "rec_tgt": 4, "qb_car": 4, "rz": 0.8, "gl": 0.3, "max_price": 450, "edge": 0.03}


def _implied(price):
    return 100 / (price + 100) if price > 0 else -price / (-price + 100)


def _hits(p):
    s, ln = p.get("series") or [], p.get("line")
    if ln is None:
        return []
    return [(v > ln) if p["side"] == "over" else (v < ln) for v in s]


def _prop_ok(p):
    if p["kind"] != "prop" or p.get("relaxed") or p.get("limited") or p["status"] != "healthy" or (p.get("n26") or 0) < 5:
        return False
    if not CARD_P_MIN <= p["p_final"] <= CARD_P_MAX:
        return False
    if p["price"] < (-115 if p["market"] in YARD_MKTS else -125):
        return False
    if p["side"] == "over" and p["line"] is not None and p["line"] < MIN_OVER_LINE.get(p["market"], 0):
        return False
    h = _hits(p)
    return len(h) >= 5 and (sum(h[-5:]) >= 4 or sum(h) / len(h) >= 0.70)


def _label_prop(p):
    h = _hits(p)
    return "FIRM" if p["p_final"] >= CARD_FIRM and sum(h[-5:]) >= 4 else "LEAN"


def td_role(t):
    g = TD_GATE
    if t["best_price"] > g["max_price"] or t.get("snap_pct") is None or t["snap_pct"] < g["snap"] or t["status"] != "healthy" or t["limited"]:
        return False
    if t["pos"] == "RB":
        vol = t["car_pg"] + t["tgt_pg"] >= g["rb_touch"]
    elif t["pos"] == "QB":
        vol = t["car_pg"] >= g["qb_car"]
    else:
        vol = t["tgt_pg"] >= g["rec_tgt"]
    return vol and (t["rz_pg"] >= g["rz"] or t["gl_pg"] >= g["gl"])


def _slot(g):
    """'sunday' for the Sunday day slate, else 'standalone' (Thu/Fri/Sat/Mon/holiday games and Sunday night)."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    ko = datetime.strptime(g["kickoff"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/New_York"))
    return "sunday" if ko.weekday() == 6 and ko.hour < 19 else "standalone"


def _game_pick(g, mk):
    for p in _game_bets(g):
        if p["market"] != mk:
            continue
        b = g["markets"][mk]["best"]
        if b["ev"] < config.LEAN_EV:
            return None
        q = dict(p)
        q["label_card"] = "FIRM" if b["ev"] >= config.BET_EV else "LEAN"
        q["ev"] = b["ev"]
        if mk == "spread":
            agree = (g["margin"] + b["line"] > 0) == (b["side"] == "home")    # stored line is the home team's
        else:
            agree = (g["total"] > b["line"]) == (b["side"] == "over")
        if not agree:
            q["label_card"] = "LEAN"
            q["risk"] = q["risk"] + ["Our raw projection points the other way; the edge comes from the price, so it is a lean at best."]
        return q
    return None


CARD_PM_MIN, CARD_PM_MAX, CARD_MKT_MIN = 0.56, 0.72, 0.45   # model's own chance band; market must not strongly oppose


def _score(p):
    h = _hits(p)
    return 0.6 * p["p_model"] + 0.4 * (sum(h) / len(h) if h else 0)


def _card_props(props, deeps, gmap, model):
    """Prop model v2 (model/prop_calib.py): best side per player where our chance beats the price by EDGE_MIN+, ranked by edge."""
    from model import prop_calib as PC
    import statistics
    best = {}
    for r in props:
        if r["status"] != "healthy" or r["limited"] or (r.get("n26") or 0) < 5 or r["game_id"] not in gmap or model is None:
            continue
        opts = r.get("opts") or []
        mk = {}
        for o in opts:                                    # de-vigged market P(over) at each line, averaged over books
            mk.setdefault(o["line"], []).append(o["p_market"] if o["side"] == "over" else 1 - o["p_market"])
        med8 = statistics.median(r["series"][-8:]) if r.get("series") else None
        if med8 is None:
            continue
        for o in opts:
            yard = r["market"] in YARD_MKTS
            if not (-115 if yard else -125) <= o["price"] <= 140 or o["line"] < MIN_OVER_LINE.get(r["market"], 0):
                continue
            po = PC.p_over(model, r["market"], sum(mk[o["line"]]) / len(mk[o["line"]]), med8, o["line"])
            pside = po if o["side"] == "over" else 1 - po
            edge = pside - PC.implied(o["price"])
            if edge < PC.EDGE_MIN:
                continue
            p = _pick_from_prop(r, o)
            p["p_new"], p["edge"] = round(pside, 4), round(edge, 4)
            k = r["player_id"]
            if k not in best or edge > best[k]["edge"]:
                best[k] = p
    out = {}
    for p in best.values():
        g = gmap[p["game_id"]]
        p["why"], p["risk"] = _why(p, deeps.get(p["game_id"], {}), g)
        h = _hits(p)
        p["hit_txt"] = f"{sum(h)} of {len(h)} this season" if h else "no history"
        p["label_card"] = "FIRM" if p["edge"] >= PC.EDGE_FIRM else "LEAN"
        p["conf"], p["conf_cls"] = _conf(p["p_new"])
        out.setdefault(p["game_id"], []).append(p)
    for v in out.values():
        v.sort(key=lambda p: -p["edge"])
    return out


def card(bp, games, tds, props=None, deeps=None, model=None) -> dict:
    gmap = {g["id"]: g for g in games}
    props_by_game = _card_props(props or [], deeps or {}, gmap, model)
    sun_ids = [g["id"] for g in games if _slot(g) == "sunday"]
    out = {"sunday": None, "standalone": []}
    if sun_ids:
        pool, per = [], {}
        for p in sorted([p for gid in sun_ids for p in props_by_game.get(gid, [])], key=lambda p: -p["edge"]):
            if per.get(p["game_id"], 0) >= 2 or any(q["player_id"] == p["player_id"] for q in pool):
                continue
            pool.append(p)
            per[p["game_id"]] = per.get(p["game_id"], 0) + 1
            if len(pool) == 12:
                break
        spreads = sorted(filter(None, (_game_pick(gmap[i], "spread") for i in sun_ids)), key=lambda p: -p["ev"])[:3]
        totals = sorted(filter(None, (_game_pick(gmap[i], "total") for i in sun_ids)), key=lambda p: -p["ev"])[:2]
        for p in pool + spreads + totals:
            p["game"] = f"{gmap[p['game_id']]['away']} @ {gmap[p['game_id']]['home']}"
        out["sunday"] = {"n_games": len(sun_ids), "props": pool, "spreads": spreads, "totals": totals}
    for g in sorted((g for g in games if _slot(g) == "standalone"), key=lambda g: g["kickoff"]):
        ps = props_by_game.get(g["id"], [])[:2]
        gp = [p for p in (_game_pick(g, "spread"), _game_pick(g, "total")) if p]
        gp = max(gp, key=lambda p: p["ev"]) if gp else None
        td = None
        best = sorted((t for t in tds if t["game_id"] == g["id"] and td_role(t)), key=lambda t: -(t["p_final"] - _implied(t["best_price"])))
        if best and best[0]["p_final"] - _implied(best[0]["best_price"]) >= TD_GATE["edge"]:
            t = best[0]
            td = {"player": t["player"], "pos": t["pos"], "team": t["team"], "opp": t["opp"], "book": t["best_book"], "price": t["best_price"], "p_final": t["p_final"],
                  "p_market": t["p_market"], "implied": round(_implied(t["best_price"]), 4), "snap_pct": t["snap_pct"], "rz_pg": t["rz_pg"], "gl_pg": t["gl_pg"],
                  "td_games": t["td_games"], "games": t["games"], "label_card": "LEAN"}
        out["standalone"].append({"game_id": g["id"], "away": g["away"], "home": g["home"], "kickoff": g["kickoff"], "props": ps, "game_pick": gp, "td": td})
    return out
