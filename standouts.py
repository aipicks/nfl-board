"""Plain-English write-up of what stands out in a game: matchup edges, run game, passing game, injuries that change things, likely game script.

Built only from numbers already on the page (2026 ranks, injuries with usage, our projection). Ranks: #1 is the best in the league at that unit
(offence: best attack; defence: best at stopping it)."""
import numpy as np

import config

PASS_KEYS = ["epa_pass", "sr_pass", "ypa"]
RUSH_KEYS = ["epa_rush", "sr_rush", "rush_ypc"]


def _row(d, side, key):
    return next((r for r in d["metrics"][side] if r["key"] == key), None)


def _rk(d, side, key, team):
    r = _row(d, side, key)
    return None if r is None else r[team]["r26"]


def _val(d, side, key, team):
    r = _row(d, side, key)
    return None if r is None else r[team]["v26"]


def _comp(d, side, keys, team):
    v = [x for x in (_rk(d, side, k, team) for k in keys) if x is not None]
    return float(np.mean(v)) if v else None


def _fmt(d, side, key, team):
    r = _row(d, side, key)
    v = r[team]["v26"]
    f = r["fmt"]
    dec = int(f.split(".")[1][0]) if "." in f else 1
    return f"{v * 100:.{dec}f}%" if "%" in f else f"{v:+.{dec}f}" if "+" in f else f"{v:.{dec}f}"


def _ord(n):
    n = int(round(n))
    return f"#{n}"


def _injuries(d, team):
    return [i for i in d["injuries"] if i["team"] == team]


def _importance(i):
    return (i.get("snap_pct") or 0) + 2 * (i.get("car") or 0) + 3 * (i.get("tgt") or 0)


def standouts(d: dict) -> list[dict]:
    a, h = d["away"], d["home"]
    teams = ((a, h), (h, a))
    sec = []

    # ---------------------------------------------------------------- run game
    items = []
    for t, o in teams:
        off, dfn = _comp(d, "off", RUSH_KEYS, t), _comp(d, "def", RUSH_KEYS, o)
        if off is None or dfn is None:
            continue
        ypc_o, ypc_d = _fmt(d, "off", "rush_ypc", t), _fmt(d, "def", "rush_ypc", o)
        sr_d = _fmt(d, "def", "sr_rush", o)
        rbs = [i for i in _injuries(d, t) if i["pos"] in ("RB", "FB") and i["status"] in ("out", "doubtful") and (i.get("car") or 0) >= 15]
        extra = ""
        if rbs:
            r = max(rbs, key=lambda i: i["car"])
            nxt = (r.get("next_up") or [{}])[0].get("name")
            extra = f" {r['name']} is {r['status']} (he has {r['car']} of the team's carries so far){' and ' + nxt + ' is next up' if nxt else ''}, which makes it harder."
        if off <= 10 and dfn >= 20:
            items.append(("g", f"{t} should be able to run the ball: their run game ranks {_ord(off)} ({ypc_o} yards per carry) against a {o} run defence ranked {_ord(dfn)} ({ypc_d} allowed, {sr_d} of runs successful).{extra}"))
        elif off >= 22 and dfn <= 10:
            items.append(("r", f"{t} will struggle running the ball against {o}: their run game ranks {_ord(off)} ({ypc_o} per carry) and {o}'s run defence ranks {_ord(dfn)} ({ypc_d} allowed, only {sr_d} of runs successful).{extra}"))
        elif off <= 12 and dfn <= 12:
            items.append(("y", f"{t}'s good run game ({_ord(off)}, {ypc_o} per carry) meets a strong {o} run defence ({_ord(dfn)}, {ypc_d} allowed): something has to give.{extra}"))
        elif off >= 20 and dfn >= 20:
            items.append(("y", f"{t}'s run game is poor ({_ord(off)}, {ypc_o} per carry) but {o}'s run defence is also poor ({_ord(dfn)}, {ypc_d} allowed), so this is a chance to improve.{extra}"))
        else:
            items.append(("y", f"{t} run game {_ord(off)} ({ypc_o} per carry) vs {o} run defence {_ord(dfn)} ({ypc_d} allowed): no big gap either way.{extra}"))
    sec.append({"title": "Running game", "items": items})

    # ---------------------------------------------------------------- passing game
    items = []
    for t, o in teams:
        off, dfn = _comp(d, "off", PASS_KEYS, t), _comp(d, "def", PASS_KEYS, o)
        if off is None or dfn is None:
            continue
        ypa_o, ypa_d = _fmt(d, "off", "ypa", t), _fmt(d, "def", "ypa", o)
        qb = [i for i in _injuries(d, t) if i["pos"] == "QB" and i["status"] != "healthy"]
        recv = [i for i in _injuries(d, t) if i["pos"] in ("WR", "TE") and i["status"] in ("out", "doubtful") and (i.get("tgt") or 0) >= 12]
        secondary = [i for i in _injuries(d, o) if i["pos"] in ("CB", "S", "DB") and i["status"] in ("out", "doubtful") and (i.get("snap_pct") or 0) >= 50]
        notes = ""
        if qb:
            notes += f" {qb[0]['name']} is {qb[0]['status']} at quarterback."
        if recv:
            notes += " Without " + ", ".join(f"{r['name']} ({r['tgt']} targets so far)" for r in recv[:2]) + " their receiving group is thinner."
        if secondary:
            notes += f" {o} is missing {', '.join(i['name'] + ' (' + i['pos'] + ')' for i in secondary[:3])} in the secondary."
        if off <= 10 and dfn >= 20:
            items.append(("g", f"{t}'s passing game is an advantage: it ranks {_ord(off)} ({ypa_o} yards per attempt) against a {o} pass defence ranked {_ord(dfn)} ({ypa_d} allowed).{notes}"))
        elif off >= 22 and dfn <= 10:
            items.append(("r", f"{t}'s passing game is in trouble: it ranks {_ord(off)} ({ypa_o} per attempt) against a {o} pass defence ranked {_ord(dfn)} ({ypa_d} allowed).{notes}"))
        else:
            items.append(("y", f"{t} pass offence {_ord(off)} ({ypa_o} per attempt) vs {o} pass defence {_ord(dfn)} ({ypa_d} allowed): fairly even.{notes}"))
        # protection vs rush, explosives
        sk_o, sk_d = _rk(d, "off", "sack_rate", t), _rk(d, "def", "sack_rate", o)
        if sk_o is not None and sk_d is not None:
            if sk_o >= 22 and sk_d <= 8:
                items.append(("r", f"{t}'s quarterback is under pressure risk: they take sacks at a {_ord(sk_o)}-ranked rate ({_fmt(d, 'off', 'sack_rate', t)}) and {o}'s pass rush ranks {_ord(sk_d)} ({_fmt(d, 'def', 'sack_rate', o)} sack rate)."))
            elif sk_o <= 8 and sk_d >= 24:
                items.append(("g", f"{t} protects the quarterback well ({_ord(sk_o)}) and {o}'s pass rush is weak ({_ord(sk_d)}): clean pockets are likely."))
        ex_o, ex_d = _rk(d, "off", "expl_pass", t), _rk(d, "def", "expl_pass", o)
        if ex_o is not None and ex_d is not None and ex_o <= 10 and ex_d >= 22:
            items.append(("g", f"Big plays: {t} throws explosive (20+ yard) passes at a {_ord(ex_o)} rate and {o} allows them at a {_ord(ex_d)} rate."))
    sec.append({"title": "Passing game", "items": items})

    # ---------------------------------------------------------------- glaring gaps
    pairs = [("epa_pass", "epa_pass", "passing efficiency"), ("ypa", "ypa", "yards per pass attempt"), ("epa_rush", "epa_rush", "run efficiency"), ("rush_ypc", "rush_ypc", "yards per carry"),
             ("stuff_rate", "stuff_rate", "avoiding (or forcing) stuffed runs"), ("third", "third", "3rd-down conversion"), ("rz_td", "rz_td", "red-zone touchdowns"), ("ppd", "ppd", "points per drive"),
             ("expl_rush", "expl_rush", "big runs (10+ yards)"), ("expl_pass", "expl_pass", "big passes (20+ yards)")]
    gaps = []
    for t, o in teams:
        for ko, kd, lab in pairs:
            ro, rd = _rk(d, "off", ko, t), _rk(d, "def", kd, o)
            if ro is None or rd is None:
                continue
            gaps.append((rd - ro, t, o, lab, ro, rd, ko, kd))
    gaps.sort(key=lambda g: -abs(g[0]))
    items = []
    for gap, t, o, lab, ro, rd, ko, kd in gaps[:5]:
        if abs(gap) < 14:
            continue
        who = f"{t} has the edge in {lab}" if gap > 0 else f"{o} has the edge over {t} in {lab}"
        items.append(("g" if gap > 0 else "r", f"{who}: {t} offence ranks {_ord(ro)} ({_fmt(d, 'off', ko, t)}) while {o}'s defence ranks {_ord(rd)} ({_fmt(d, 'def', kd, o)}), a gap of {abs(gap):.0f} places."))
    if items:
        sec.append({"title": "Biggest gaps in the matchup", "items": items})

    # ---------------------------------------------------------------- injuries
    items = []
    for t, o in teams:
        inj = sorted([i for i in _injuries(d, t) if i["status"] in ("out", "doubtful", "questionable") and _importance(i) >= 40], key=lambda i: -_importance(i))[:5]
        for i in inj:
            nxt = ", ".join(n["name"] for n in (i.get("next_up") or [])[:2] if isinstance(n.get("name"), str))
            use = []
            if i.get("car"):
                use.append(f"{i['car']} carries")
            if i.get("tgt"):
                use.append(f"{i['tgt']} targets")
            if i.get("snap_pct"):
                use.append(f"{i['snap_pct']}% of snaps")
            effect = ""
            if i["pos"] in ("T", "G", "C", "OT", "OG"):
                sk = _rk(d, "off", "sack_rate", t)
                effect = f" Weaker pass protection and run blocking{' (they already rank ' + _ord(sk) + ' in sack rate)' if sk else ''}."
            elif i["pos"] in ("CB", "S", "DB"):
                effect = f" That thins the secondary against {o}'s passing game."
            elif i["pos"] in ("DE", "DT", "LB", "OLB", "ILB", "NT"):
                effect = f" That weakens the front seven against {o}'s run game and pass rush."
            elif i["pos"] == "QB":
                effect = " Quarterback availability swings both the spread and the total."
            elif i["pos"] in ("RB", "WR", "TE"):
                effect = f" His work should go to {nxt}." if nxt else ""
            hist = (i.get("hist") or {}).get("text")
            items.append(("r" if i["status"] != "questionable" else "y", f"{t}: {i['name']} ({i['pos']}, {i['status']}{', ' + i['injury'] if i.get('injury') else ''}; {', '.join(use)}).{effect}" + (f" {hist}" if hist else "")))
    if items:
        sec.append({"title": "Injuries that change this game", "items": items})

    # ---------------------------------------------------------------- game script
    P = d["projection"]
    ref = P["ref"]
    items = []
    fav_home = P["margin"] >= 0
    fav, dog = (h, a) if fav_home else (a, h)
    m = abs(P["margin"])
    line_txt = f"market has {h} {ref['spread']:+g}" if ref.get("spread") is not None else ""
    items.append(("y", f"Our projection: {fav} by {m:.1f} ({a} {P['pts_away']:.1f}, {h} {P['pts_home']:.1f}; total {P['total']:.1f}). {line_txt[0].upper() + line_txt[1:] if line_txt else ''}{', total ' + str(ref['total']) if ref.get('total') is not None else ''}."))
    npa = {t: _val(d, "off", "neutral_pass", t) for t in (a, h)}
    if all(v is not None for v in npa.values()):
        lg = _row(d, "off", "neutral_pass")["lg26"]
        pace = d["plays_proj"]
        lean = {t: ("pass-heavy" if npa[t] > lg + 0.03 else "run-leaning" if npa[t] < lg - 0.03 else "balanced") for t in (a, h)}
        items.append(("y", f"Tendencies: {a} is {lean[a]} in neutral situations ({npa[a] * 100:.0f}% pass, league {lg * 100:.0f}%), {h} is {lean[h]} ({npa[h] * 100:.0f}%). We project about {pace[a]['plays']:.0f} plays for {a} and {pace[h]['plays']:.0f} for {h}."))
    run_a, run_h = _comp(d, "off", RUSH_KEYS, a), _comp(d, "off", RUSH_KEYS, h)
    rd_a, rd_h = _comp(d, "def", RUSH_KEYS, a), _comp(d, "def", RUSH_KEYS, h)
    if None not in (run_a, run_h, rd_a, rd_h):
        if run_a >= 18 and run_h >= 18 and rd_a <= 14 and rd_h <= 14:
            items.append(("y", "Both teams run poorly and both defend the run well, so expect short drives, punts, and scoring that depends on a few pass plays: a slow, low-possession game."))
        elif run_a <= 12 and run_h <= 12:
            items.append(("y", "Both teams run the ball well, which shortens the game (clock keeps moving) but gives each side steady drives."))
    if m >= 6:
        items.append(("y", f"With a {m:.0f}-point gap, if {fav} leads they can lean on the run and the clock while {dog} is forced to throw more in the second half; if {dog} keeps it close, the margin shrinks quickly."))
    elif m <= 3:
        items.append(("y", "This is projected as a one-score game: expect balanced play-calling until late, and the last possession or a turnover to decide it."))
    if ref.get("total") is not None:
        diff = P["total"] - ref["total"]
        if diff <= -2:
            items.append(("y", f"Scoring: our total is {abs(diff):.1f} below the market, which fits the defensive strengths and absences above (Under lean, but our model has not yet beaten the market's totals)."))
        elif diff >= 2:
            items.append(("y", f"Scoring: our total is {diff:.1f} above the market (Over lean, but our model has not yet beaten the market's totals)."))
    w = d["weather"]["hours"][d["weather"]["kickoff_hour_index"]]
    if d.get("indoor"):
        items.append(("g", "Indoors: weather is not a factor."))
    elif w["windspeed_10m"] >= 15 or w["windgusts_10m"] >= 25:
        items.append(("r", f"Wind {w['windspeed_10m']:.0f} mph with gusts to {w['windgusts_10m']:.0f}: favours the run and short passes, hurts deep throws and long field goals."))
    elif w["precipitation_probability"] >= 40:
        items.append(("r", f"{w['precipitation_probability']:.0f}% chance of precipitation: grip and ball security matter, passing efficiency usually dips."))
    sec.append({"title": "How we expect the game to go", "items": items})
    return sec
