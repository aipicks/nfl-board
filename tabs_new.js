/* ---------- TD scorers, Player props, Results, How it works ---------- */
const GNAME = Object.fromEntries(D.games.map(g => [g.id, `${g.away} @ ${g.home}`]));
const PROP_LABEL = {pass_yds: "Pass yds", rush_yds: "Rush yds", rec_yds: "Rec yds", receptions: "Receptions", rush_att: "Rush att", pass_td: "Pass TD", pass_comp: "Completions", pass_att: "Pass att", pass_int: "Interceptions", pass_rush_yds: "Pass+rush yds", rush_rec_yds: "Rush+rec yds", td_any: "Anytime TD"};
const CORE = ["pass_yds", "rush_yds", "rec_yds", "receptions", "rush_att"];
const evChip = e => `<span class="badge ${evc(e)}">${e >= D.cfg.bet ? "BET" : e >= D.cfg.lean ? "LEAN" : "PASS"} ${sgn(e * 100)}%</span>`;
const rkChip = (r, n) => r == null ? "" : `<span class="chip ${r <= 10 ? "g" : r <= 22 ? "y" : "r"}">#${r}</span>`;
const stTag = s => s && s !== "healthy" ? `<span class="chip ${s === "questionable" ? "y" : "r"}">${s.toUpperCase()}</span>` : `<span class="chip g">HEALTHY</span>`;
const kick = iso => new Date(iso).toLocaleString("en-US", {...ET, month: "short", day: "numeric"});
const sel = (id, opts, label) => `<select id="${id}"><option value="">${label}</option>${opts.map(o => `<option value="${o[0]}">${o[1]}</option>`).join("")}</select>`;
const pbar = (p, col) => `<div class="bar" style="width:64px"><i style="width:${Math.max(2, Math.min(100, p * 100))}%;background:var(--${col})"></i></div>`;

/* ---- anytime TD ---- */
function tdRowHtml(t, n) {
  const prices = Object.entries(t.prices).sort((a, b) => b[1] - a[1]).map(([b, v]) => `<span class="bk ${b === t.best_book ? "best" : ""}">${BK[b]} ${price(v)}</span>`).join(" ");
  return `<tr><td>${n}</td><td class="lab"><b>${t.player}</b> <span class="xs mut">${t.pos} · ${t.team} ${t.home ? "vs" : "@"} ${t.opp}</span><br>${stTag(t.status)} ${t.limited ? '<span class="chip y">limited data</span>' : ""}${t.usage_boost > 0.08 ? `<span class="chip g">usage +${Math.round(t.usage_boost * 100)}%</span>` : ""}<br><span class="xs mut">${kick(t.kickoff)} ET</span></td>
    <td>${price(t.best_price)}<br><span class="xs mut">${BK[t.best_book]}</span></td><td class="xs">${prices}</td>
    <td><b>${pct(t.p_model)}</b>${pbar(t.p_model, "acc")}</td><td>${pct(t.p_market)}${pbar(t.p_market, "y")}</td><td><b>${pct(t.p_final)}</b>${pbar(t.p_final, evc(t.ev))}</td><td>${evChip(t.ev)}</td>
    <td class="xs">${t.snap_pct != null ? t.snap_pct + "% snaps<br>" : ""}${t.tgt_pg} tgt, ${t.car_pg} car /g<br>RZ ${t.rz_pg}/g · GL ${t.gl_pg}/g<br>TD in ${t.td_games} of ${t.games} games</td>
    <td class="xs">${t.opp_td_pg != null ? `${t.opp} allows ${t.opp_td_pg} TD/g to ${t.pos}s ${rkChip(t.opp_td_rank)}<br><span class="mut">league ${t.opp_td_lg}</span>` : "-"}<br>team ${t.env_pts} pts</td></tr>`;
}
/* Role gate (2026-11-25, user: too many long shots who barely see the field were inflating EV). Keep only players who are on the field,
   get the ball, and have a scoring-area role, at a sane price. "Show all" still lists everyone. */
const TD_GATE = {snap: 50, rbTouch: 8, recTgt: 4, qbCar: 4, rz: 0.8, gl: 0.3, maxPrice: 450};
function tdRole(t) {
  if (t.best_price > TD_GATE.maxPrice) return false;
  if (t.snap_pct == null || t.snap_pct < TD_GATE.snap) return false;
  const vol = t.pos === "RB" ? t.car_pg + t.tgt_pg >= TD_GATE.rbTouch : t.pos === "QB" ? t.car_pg >= TD_GATE.qbCar : t.tgt_pg >= TD_GATE.recTgt;
  return vol && (t.rz_pg >= TD_GATE.rz || t.gl_pg >= TD_GATE.gl);
}
const TS = {team: "", game: "", pos: "", sort: "ev", only: false, all: false};
function renderTd() {
  const base = D.td.filter(t => t.p_model >= D.cfg.td_min && !t.limited && tdRole(t)).slice(0, D.cfg.td_top);
  let rows = (TS.all ? D.td : base).filter(t => (!TS.team || t.team === TS.team) && (!TS.game || t.game_id === TS.game) && (!TS.pos || t.pos === TS.pos) && (!TS.only || t.ev >= D.cfg.lean));
  const key = {ev: t => -t.ev, model: t => -t.p_model, final: t => -t.p_final, game: t => t.kickoff}[TS.sort];
  rows = rows.slice().sort((a, b) => key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0);
  $("#tdbody").innerHTML = rows.map((t, i) => tdRowHtml(t, i + 1)).join("") || `<tr><td colspan="10" class="mut">No players match.</td></tr>`;
  $("#tdcount").textContent = `${rows.length} shown · ${D.td.length} players priced · ${D.td.filter(t => t.p_model >= D.cfg.td_min).length} have a model chance of ${D.cfg.td_min * 100}% or more`;
}
function initTd() {
  const teams = [...new Set(D.td.map(t => t.team))].sort();
  $("#tdroot").innerHTML = `<div class="card"><h2>+EV TD scorers</h2><p class="small">Every player with anytime-TD odds this week. Only players our model gives <b>${D.cfg.td_min * 100}% or more</b>, top ${D.cfg.td_top} by EV (renumbered after filters). <b>Role filter:</b> only players with ${TD_GATE.snap}%+ of snaps, real volume (RB ${TD_GATE.rbTouch}+ touches a game, WR/TE ${TD_GATE.recTgt}+ targets, QB ${TD_GATE.qbCar}+ carries), a scoring-area role (${TD_GATE.rz}+ red-zone touches or ${TD_GATE.gl}+ goal-line touches a game), priced +${TD_GATE.maxPrice} or shorter. Deep long shots who rarely see the field are hidden; "show all" brings them back. Model = expected touches in five zones of the field (targets and carries outside the 20, in the red zone, at the goal line) x the league TD rate of each zone, scaled by the team's scoring environment, opponent TDs allowed to the position, and who is missing; usage moves to teammates when a player is out. Final % blends ${Math.round(D.cfg.w.td * 100)}% model / ${Math.round((1 - D.cfg.w.td) * 100)}% market. Backtest on 2025: log-loss 0.487 vs 0.527 for a flat rate.</p>
    <p class="xs mut">Market % divides each price's implied chance by an assumed ${Math.round(D.cfg.td_hold * 100)}% overround (these prices have no "No" side). Players with fewer than 3 games are labelled limited data, lean on the market, and stay out of the top-50 list (tick "show all priced players" to see them). A model-vs-market gap above 1.5x is believed less, because big gaps usually mean the model missed a role. Statuses can change before kickoff; Sunday inactives post about 90 minutes before.</p></div>
    <div class="ctl">${sel("tdteam", teams.map(t => [t, t]), "All teams")}${sel("tdgame", D.games.map(g => [g.id, GNAME[g.id]]), "All games")}${sel("tdpos", ["RB", "WR", "TE", "QB"].map(p => [p, p]), "All positions")}
    <select id="tdsort"><option value="ev">Sort: best EV</option><option value="model">Sort: model %</option><option value="final">Sort: final %</option><option value="game">Sort: kickoff</option></select>
    <label class="tg"><input type="checkbox" id="tdonly"> BET/LEAN only</label><label class="tg"><input type="checkbox" id="tdall"> show all priced players</label></div>
    <div class="xs mut" id="tdcount" style="margin:2px 0 6px"></div>
    <div class="tw"><table class="tbl"><thead><tr><th>#</th><th>Player</th><th>Best price</th><th>All books</th><th>Model</th><th>Market</th><th>Final</th><th>EV</th><th>Usage (per game)</th><th>Opponent vs position</th></tr></thead><tbody id="tdbody"></tbody></table></div>`;
  const u = () => { TS.team = $("#tdteam").value; TS.game = $("#tdgame").value; TS.pos = $("#tdpos").value; TS.sort = $("#tdsort").value; TS.only = $("#tdonly").checked; TS.all = $("#tdall").checked; renderTd(); };
  ["#tdteam", "#tdgame", "#tdpos", "#tdsort", "#tdonly", "#tdall"].forEach(s => $(s).onchange = u);
  renderTd();
}

/* ---- player props ---- */
function propRowHtml(p, showGame) {
  const b = p.best, c = evc(b.ev);
  const books = p.books.slice().sort((x, y) => (x.l ?? 0) - (y.l ?? 0)).map(x => `<span class="bk">${BK[x.b]} ${x.l ?? ""} <span class="mut">o</span>${price(x.o)} <span class="mut">u</span>${price(x.u)}</span>`).join(" ");
  const mx = Math.max(...p.series, 1);
  const spark = `<svg width="68" height="20" viewBox="0 0 68 20">${p.series.map((v, i) => { const h = Math.max(1, v / mx * 18); const hit = p.ref_line != null && v > p.ref_line; return `<rect x="${i * 8.5}" y="${20 - h}" width="7" height="${h}" fill="${hit ? "#2fcf6b" : "#ff5a5f"}" opacity=".85"/>`; }).join("")}${p.ref_line != null ? `<line x1="0" x2="68" y1="${20 - Math.min(19, p.ref_line / mx * 18)}" y2="${20 - Math.min(19, p.ref_line / mx * 18)}" stroke="currentColor" stroke-dasharray="3 2" opacity=".6"/>` : ""}</svg>`;
  const opp = `${p.opp} allows <b>${p.opp_pa26 ?? "-"}</b> ${rkChip(p.opp_rk26)} <span class="mut">(lg ${p.opp_lg26})</span><br><span class="xs mut">2025: ${p.opp_pa25 ?? "-"} ${p.opp_rk25 != null ? "#" + p.opp_rk25 : ""}</span><br><span class="xs mut">${p.opp_stat.replace("_", " ")} per game</span>`;
  return `<tr><td class="lab"><b>${p.player}</b> <span class="xs mut">${p.pos} · ${p.team} ${p.home ? "vs" : "@"} ${p.opp}</span><br>${stTag(p.status)} ${p.limited ? '<span class="chip y">limited data</span>' : ""}${showGame ? `<br><span class="xs mut">${kick(p.kickoff)} ET</span>` : ""}</td>
    <td>${PROP_LABEL[p.market]}<br><span class="xs mut">line ${p.ref_line ?? "-"} · ${p.n_books} book${p.n_books > 1 ? "s" : ""}</span></td><td class="xs">${books}</td>
    <td><b>${p.mu}</b><span class="xs mut"> ±${p.sd}</span><br><span class="xs mut">avg ${p.avg26 ?? "-"} (${p.n26} g) · 2025 ${p.avg25 ?? "-"}</span></td><td>${spark}<br><span class="xs mut">${p.hit_over != null ? Math.round(p.hit_over * 100) + "% over, last " + p.hit_n : ""}</span></td>
    <td><span class="badge ${c}">${b.label} ${sgn(b.ev * 100)}%</span><br><b>${b.side} ${b.line}</b> ${BK[b.book]} ${price(b.price)}<br><span class="xs mut">model ${pct(b.p_model)} · mkt ${pct(b.p_market)} · final ${pct(b.p_final)}</span></td><td class="xs">${opp}</td></tr>`;
}
const PST = {};
function propsUI(pre, rows, showGame) {
  PST[pre] = {rows, st: {team: "", game: "", pos: "", market: "", sort: "ev", only: false, core: !showGame ? false : true}, showGame};
  const teams = [...new Set(rows.map(p => p.team))].sort(), mk = [...new Set(rows.map(p => p.market))];
  return `<div class="ctl">${showGame ? sel(pre + "game", D.games.map(g => [g.id, GNAME[g.id]]), "All games") : ""}${sel(pre + "team", teams.map(t => [t, t]), "All teams")}${sel(pre + "pos", ["QB", "RB", "WR", "TE"].map(p => [p, p]), "All positions")}
    ${sel(pre + "mk", mk.map(m => [m, PROP_LABEL[m]]), "All markets")}<select id="${pre}sort"><option value="ev">Sort: best EV</option><option value="p">Sort: final %</option><option value="name">Sort: player</option><option value="game">Sort: kickoff</option></select>
    <label class="tg"><input type="checkbox" id="${pre}only"> BET/LEAN only</label>${showGame ? `<label class="tg"><input type="checkbox" id="${pre}core" checked> core props only</label>` : ""}</div>
    <div class="xs mut" id="${pre}count" style="margin:2px 0 6px"></div>
    <div class="tw"><table class="tbl props"><thead><tr><th>Player</th><th>Market</th><th>Lines by book (o = over, u = under)</th><th>Projection (±sd)</th><th>Last 8 (dashed = line)</th><th>Best pick</th><th>Opposing defence vs position</th></tr></thead><tbody id="${pre}body"></tbody></table></div>`;
}
function renderPropsUI(pre) {
  const S = PST[pre], s = S.st;
  const get = id => (document.getElementById(pre + id) || {}).value || "";
  s.game = get("game"); s.team = get("team"); s.pos = get("pos"); s.market = get("mk"); s.sort = get("sort") || "ev"; s.only = !!(document.getElementById(pre + "only") || {}).checked;
  const core = document.getElementById(pre + "core"); s.core = core ? core.checked : false;
  let rows = S.rows.filter(p => (!s.game || p.game_id === s.game) && (!s.team || p.team === s.team) && (!s.pos || p.pos === s.pos) && (!s.market || p.market === s.market) && (!s.only || p.best.ev >= D.cfg.lean) && (!s.core || s.market || CORE.includes(p.market)));
  const k = {ev: p => -p.best.ev, p: p => -p.best.p_final, name: p => p.player, game: p => p.kickoff}[s.sort];
  rows = rows.slice().sort((a, b) => k(a) < k(b) ? -1 : k(a) > k(b) ? 1 : 0);
  const lim = 250;
  document.getElementById(pre + "body").innerHTML = rows.slice(0, lim).map(p => propRowHtml(p, S.showGame)).join("") || `<tr><td colspan="7" class="mut">No props match.</td></tr>`;
  document.getElementById(pre + "count").textContent = `${Math.min(rows.length, lim)} of ${rows.length} shown`;
}
function bindPropsUI(pre) { ["game", "team", "pos", "mk", "sort", "only", "core"].forEach(i => { const e = document.getElementById(pre + i); if (e) e.onchange = () => renderPropsUI(pre); }); renderPropsUI(pre); }
function initProps() {
  const nCore = D.props.filter(p => CORE.includes(p.market)).length;
  $("#propsroot").innerHTML = `<div class="card"><h2>Player props</h2><p class="small">Every prop the five books post, projected as expected volume x efficiency: team pass and rush volume from the game script (spread and total), the player's recency-weighted share (teammates' absences move touches to the players behind them), catch rate and yards per catch, carry or attempt, shrunk toward the position average, then opponent defence vs position (half strength, scaled by games played) and wind. Yards use a gamma distribution, counts a negative binomial, with variance fitted on 2025 walk-forward errors. ${D.props.length} props across ${D.games.length} games (${nCore} core: pass yds, rush yds, rec yds, receptions, rush att).</p>
    <p class="xs mut">Not modelled (the books post them, our model does not): longest pass, longest rush, longest reception. Only ${Math.round(D.cfg.prop_trust * 100)}% of the gap between model and market is believed (less when the gap to the line is huge, because that usually means a role or injury we do not know about), then the final blends ${Math.round(D.cfg.w.prop * 100)}% model / ${Math.round((1 - D.cfg.w.prop) * 100)}% market. The Results tab judges whether it earns more trust. Sunday-morning inactives can change everything.</p></div>` + propsUI("pp", D.props, true);
  bindPropsUI("pp");
}

/* ---- results ---- */
function rTable(title, o) {
  const rows = Object.entries(o).filter(([k, v]) => v.n).map(([k, v]) => `<tr><td class="lab">${k}</td><td>${v.n}</td><td>${v.w}-${v.l}${v.p ? "-" + v.p : ""}</td><td>${v.hit != null ? pct(v.hit) : "-"}</td><td>${v.pred != null ? pct(v.pred) : "-"}</td>
    <td>${v.brier_model ?? "-"}</td><td>${v.brier_market ?? "-"}</td><td>${v.brier_final ?? "-"}</td><td><span class="chip ${v.units > 0.05 ? "g" : v.units < -0.05 ? "r" : "y"}">${v.units > 0 ? "+" : ""}${v.units}</span></td><td>${v.roi != null ? pct(v.roi) : "-"}</td></tr>`).join("");
  return `<h3 class="dh3">${title}</h3><div class="tw"><table class="tbl"><thead><tr><th></th><th>Picks</th><th>W-L-P</th><th>Hit rate</th><th>Predicted</th><th>Brier model</th><th>Brier market</th><th>Brier final</th><th>Units ($1 flat)</th><th>ROI</th></tr></thead><tbody>${rows || '<tr><td colspan="10" class="mut">Nothing settled yet.</td></tr>'}</tbody></table></div>`;
}
function calChart(cal) {
  if (!cal.length) return `<p class="mut">The calibration chart appears after the first picks settle.</p>`;
  const w = 560, h = 220, p = 34, X = v => p + v * (w - 2 * p), Y = v => h - p - v * (h - 2 * p);
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" role="img" aria-label="Calibration: predicted chance vs actual hit rate"><line x1="${X(0)}" y1="${Y(0)}" x2="${X(1)}" y2="${Y(1)}" stroke="currentColor" opacity=".35" stroke-dasharray="5 4"/>
    ${[0, .25, .5, .75, 1].map(v => `<text x="${X(v)}" y="${h - 10}" font-size="10" text-anchor="middle" fill="currentColor" opacity=".7">${v * 100}%</text><text x="6" y="${Y(v) + 3}" font-size="10" fill="currentColor" opacity=".7">${v * 100}%</text>`).join("")}
    ${cal.map(c => `<circle cx="${X(c.pred)}" cy="${Y(c.actual)}" r="${Math.min(14, 4 + Math.sqrt(c.n))}" fill="#378ADD" opacity=".75"><title>${c.bin}: ${c.n} picks, predicted ${pct(c.pred)}, actual ${pct(c.actual)}, market ${pct(c.market)}</title></circle>`).join("")}</svg>
    <div class="xs mut">Each dot is a probability bucket (size = number of picks). On the dashed line our probabilities are honest; above it we were too cautious, below it too confident.</div>`;
}
function cardHistHtml() {
  const H = D.card_hist; if (!H) return "";
  const u = v => (v > 0 ? "+" : "") + v.toFixed(2), r = v => v == null ? "-" : (v * 100).toFixed(1) + "%";
  const row = (k, x) => `<tr><td class="lab">${k}</td><td>${x.n}</td><td>${x.w}-${x.l}${x.p ? "-" + x.p : ""}</td><td><span class="chip ${x.units > 0 ? "g" : x.units < 0 ? "r" : "y"}">${u(x.units)}</span></td><td>${r(x.roi)}</td></tr>`;
  const KN = {prop: "Player props", spread: "Spreads", total: "Totals"};
  return `<div class="card"><h2>Best Picks record</h2><p class="small">Only the short Best Picks list counts here: past weeks were re-graded as if today's Best Picks rules had been used, choosing only from what was known before kickoff and grading at the logged price (1 unit each). Anytime-TD picks are not included yet. ${H.total.n} picks: <b>${H.total.w}-${H.total.l}${H.total.p ? "-" + H.total.p : ""}, ${u(H.total.units)} units (${r(H.total.roi)} per pick)</b>.</p>
    <div class="tw"><table class="tbl"><thead><tr><th></th><th>Picks</th><th>W-L-P</th><th>Units</th><th>ROI</th></tr></thead><tbody>
    ${Object.entries(H.by_kind).filter(([k, x]) => x.n).map(([k, x]) => row(KN[k] || k, x)).join("")}${Object.entries(H.by_label).filter(([k, x]) => x.n).map(([k, x]) => row(k, x)).join("")}
    ${H.by_week.map(x => row("Week " + x.week, x)).join("")}</tbody></table></div>
    <p class="xs mut">Prop picks use prop model v2 (rebuilt 2026-11-25), replayed week by week using only earlier weeks to train it; the first weeks have no prop picks because the model needs history to learn from. Spreads and totals use the game model. A few weeks of results are a small sample.</p></div>`;
}
function initResults() {
  const R = D.results, g = R.groups || {};
  const cards = `<div class="mgrid"><div class="m"><b>${R.logged}</b><span>predictions logged</span></div><div class="m ${R.settled ? "g" : "y"}"><b>${R.settled}</b><span>settled</span></div><div class="m"><b>${R.pending}</b><span>waiting for games</span></div><div class="m"><b>${(g["All picks"] || {}).n || 0}</b><span>graded (excl. voids)</span></div></div>`;
  const early = R.settled < 100 ? `<div class="note">Only ${R.settled} picks are graded so far. A few days of results say almost nothing; judge the model after hundreds of picks per market. Tracking started ${R.first_logged ? new Date(R.first_logged).toLocaleDateString() : "when you first run the board"}; every prediction is saved before kickoff and the last pre-kickoff snapshot is the one graded.</div>` : "";
  $("#resultsroot").innerHTML = cardHistHtml() + `<details class="card"><summary><b>Every prediction ever logged</b> <span class="xs mut">(the long list, not what we would play)</span></summary><div class="card"><h2>Results</h2><p class="small">Hit rate vs predicted, Brier score (lower is better) for our model, the de-vigged market and the final blend, calibration, and flat $1 profit. Brier compares the probabilities we gave to what happened: if "model" beats "market", the model adds information.</p></div>${cards}${early}
    ${rTable("By bet type", R.groups || {})}${rTable("By market", R.by_market || {})}${rTable("By label (BET / LEAN / PASS)", R.by_label || {})}
    <h3 class="dh3">Calibration (final probability vs what happened)</h3>${calChart(R.calibration || [])}
    <h3 class="dh3">Before any results exist: what the backtests said</h3><ul class="notes"><li>Game margin: model error 12.98 vs 12.38 for the closing line over 273 games; our edge over the market was not proven, so projections are shrunk toward it.</li>
    <li>Anytime TD: walk-forward log-loss 0.487 vs 0.527 for a flat rate (2025, weeks 5-18); better than a constant, not tested against market prices.</li><li>Props: yardage and count variance fitted on 2025 walk-forward errors; no historical prop prices, so edge vs the market is untested.</li>
    <li>Public money and line movement carry a small capped weight; once enough spreads settle this tab will show whether those picks beat the ones without it.</li></ul>
    <h3 class="dh3">What the board has learned</h3>${learnHtml()}
    <div class="note">${R.backup_reminder}</div></details>`;
}

function how2() {
  const c = D.cfg, pc = v => Math.round(v * 100) + "%";
  const R = D.results || {}, all = (R.groups || {})["All picks"] || {};
  const sec = (t, body) => `<div class="card"><h2>${t}</h2>${body}</div>`;
  $("#how").innerHTML = sec("How this board works", `<p>This board turns public NFL data and live sportsbook prices into a short list of picks each week. Every number on it comes from a fixed set of rules that run the same way every time: nothing is hand-picked after the fact, and every pick is saved before kickoff and graded afterwards.</p>
    <p class="small"><b>Please read this first:</b> these are research picks tracked with paper money (1 unit each), not betting advice. Sportsbook lines are very sharp, and our own backtests have not shown that the model beats them yet. Treat every pick as an informed opinion, not a sure thing.</p>`)
  + sec("1. Best Picks: the short list", `<p>The Best Picks tab is the list we would actually play. It follows the same rules every week:</p>
    <ul class="dyn"><li><b>Sunday main slate</b> (Sunday games before 7 PM ET): 8 to 12 player props, at most 2 from one game, plus 3 spreads and 2 totals.</li>
    <li><b>Standalone games</b> (Thursday, Friday, holiday games, Sunday night, Monday night): 2 player props and 1 spread or total each, plus an anytime-touchdown pick only when our chance beats the price by 3 percentage points or more.</li>
    <li>If fewer picks pass the rules, fewer are shown. Nothing is added just to fill a number.</li></ul>
    <p>A player prop has to pass every one of these checks: a healthy starter with at least 5 games this season; a real line (no receptions under 2.5, receiving yards under 25.5, rushing yards under 30.5, attempts under 10.5); our model at 56% to 72%; the market not strongly against it (45%+); the same side hitting in 4 of his last 5 games or 70% of the season; and a fair price (-115 or better on yardage props, -125 on others). <b>FIRM</b> means the model is at 62%+ and the side hit in 4 of the last 5; everything else is a <b>LEAN</b>.</p>`)
  + sec("2. Spreads and totals", `<p><b>Team strength.</b> Each team gets an offence and defence rating built from every play this season and last: how many points each play adds or costs on average (called EPA), split into passing and running, adjusted for the strength of the opponents faced. Recent games count more (a ${c.half_life}-week half-life) and small samples are pulled toward league average.</p>
    <p><b>Game adjustments.</b> On top of the ratings: home field (${c.hfa} points, none at neutral sites), the expected starting quarterback, injuries to key players and offensive linemen, rest and travel, and weather for outdoor totals (wind of 15+ mph, rain, snow, cold). Public betting money and line movement get a small capped nudge only.</p>
    <p><b>From score to chance.</b> The projected margin and total are turned into a chance to cover using the real spread of NFL results since 2006, so key numbers like 3 and 7 get their true weight. Because closing lines have been more accurate than our projections in testing, the projection is first pulled toward the market line, and the final chance is ${pc(c.w.spread)} our model and ${pc(1 - c.w.spread)} the market (with the bookmaker's margin removed).</p>
    <p><b>Value.</b> Expected value (EV) compares that chance with the best price across ${D.cfg.books ? D.cfg.books.length : 5} sportsbooks. A spread or total needs <b>+${c.lean * 100}% EV</b> to be a LEAN and <b>+${c.bet * 100}%</b> to be FIRM. If our raw projection points the other way from the value side, it can only be a LEAN.</p>`)
  + sec("3. Player props", `<p><b>What we learned.</b> Our first prop model projected each player's volume and efficiency. When we checked it against 12,320 graded props, it had no skill: props it rated 85% hit about as often as props it rated 50%. Recent averages and hit rates turned out to be almost fully priced into the lines already. What the lines did <i>not</i> price correctly was a lean: overs hit only 47% of the time while the books priced them near 50%, and rushing overs only about 43%.</p>
    <p><b>The current model</b> starts from the sportsbooks' own probability (with their margin removed) and corrects it using every graded prop this season: how often each type of prop has actually gone over or under at a given price, plus a small adjustment for the player's median over his last 8 games versus the line. It is refit every time the board is built, so it keeps learning as results come in.</p>
    <p>A prop makes Best Picks only when our chance beats the price's implied chance by at least 4 points (FIRM at 6+). When we replayed this on past weeks, training each week only on the weeks before it, those picks went ${D.card_hist && D.card_hist.by_kind.prop.n ? `${D.card_hist.by_kind.prop.w}-${D.card_hist.by_kind.prop.l} (${D.card_hist.by_kind.prop.units > 0 ? "+" : ""}${D.card_hist.by_kind.prop.units} units)` : "positive"}. That is a handful of weeks, and the edge comes from a market-wide lean that books can fix at any time, so expect it to shrink.</p>`)
  + sec("4. Anytime touchdowns", `<p>A player's touchdown chance comes from where he gets the ball: targets and carries outside the 20, in the red zone and at the goal line, each multiplied by how often the league scores from that spot, then scaled by his team's expected points, the opponent's touchdowns allowed to his position, and whether teammates are out (their usage moves to the players still active).</p>
    <p>The tab only lists players who are really on the field: ${50}%+ of snaps, real volume (running backs 8+ touches a game, receivers and tight ends 4+ targets, quarterbacks 4+ carries), a scoring-area role (0.8+ red-zone or 0.3+ goal-line touches a game), and a price of +450 or shorter. Long shots who rarely touch the ball are hidden, because their prices made the model look far better than it is.</p>`)
  + sec("5. Data and timing", `<ul class="dyn"><li><b>Plays, players and schedules:</b> nflverse public play-by-play data (this season and last).</li>
    <li><b>Prices:</b> FanDuel, DraftKings, BetMGM, ESPN BET and Bovada via SportsGameOdds; each pick uses the best price available at that moment.</li>
    <li><b>Injuries, weather, public betting:</b> team injury reports, game-day forecasts for outdoor stadiums, and SportsBettingDime betting percentages.</li>
    <li><b>Updates:</b> the board refreshes Thursday and Saturday, with an optional quick Sunday-morning run. Inactives post about 90 minutes before kickoff, so always check a player's status before acting on a pick.</li></ul>`)
  + sec("6. Tracking and honesty", `<p>Every pick is saved before kickoff and graded from the final box score at the logged price. The Results tab shows wins and losses, units, and whether our probabilities were honest (calibration and Brier score against the market). In backtests on last season, the closing line predicted game margins better than our ratings did (average miss 12.4 points vs 13.0), which is exactly why projections are pulled toward the market. Small samples say very little; judge the board after hundreds of picks, not a few weekends.</p>`);
}

function learnHtml() {
  const L = D.learning || {}, ch = Object.entries(L.learned || {});
  const rules = Object.entries(L.rules || {}).map(([k, v]) => `<li><code>${k}</code>: changes only after ${v.min_n} graded picks, inside ${v.bounds[0]} to ${v.bounds[1]}, moving halfway to the evidence each time.</li>`).join("");
  const les = (L.lessons || []).slice().reverse().map(x => `<li><b>${x.title}</b><br><span class="xs mut">${x.body}</span></li>`).join("");
  return `<div class="small">Every run reviews the picks that have settled, checks the biggest misses against what was known beforehand (reviews/week_N.md), and nudges a few priors only when there is enough evidence. Your corrections are recorded as lessons and fixed at the root, with a test so the same mistake cannot return.</div>
    <h3 class="dh3">Automatic changes so far</h3>${ch.length ? `<ul class="notes">${ch.map(([k, v]) => `<li>${v.updated}: <code>${k}</code> ${v.was} to <b>${v.value}</b> (${v.n} picks; ${v.reason})</li>`).join("")}</ul>` : `<p class="mut small">None yet: not enough graded picks. Rules:</p><ul class="notes">${rules}</ul>`}
    <h3 class="dh3">Lessons from your corrections (newest first)</h3><ul class="notes">${les}</ul>`;
}
