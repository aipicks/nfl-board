/* ---------- Best Props: the props we are most confident will win, per game ---------- */
const BPNAME = {QB: "Quarterback", WR: "Wide receivers", RB: "Running backs", TE: "Tight end"};
function bpSpark(p) {
  const s = p.series || []; if (!s.length || p.line == null) return "";
  const mx = Math.max(...s, p.line * 1.15, 1), w = 8 * s.length + 4;
  const ly = 24 - p.line / mx * 22;
  return `<svg width="${w + 2}" height="26" viewBox="0 0 ${w + 2} 26" role="img" aria-label="last ${s.length} games vs line ${p.line}">${s.map((v, i) => { const h = Math.max(1, v / mx * 22); const win = p.side === "over" ? v > p.line : v < p.line; return `<rect x="${i * 8 + 1}" y="${24 - h}" width="6" height="${h}" fill="${win ? "#2fcf6b" : "#ff5a5f"}" opacity=".85"/>`; }).join("")}<line x1="0" x2="${w}" y1="${ly}" y2="${ly}" stroke="currentColor" stroke-dasharray="3 2" opacity=".7"/></svg>`;
}
function bpPickCard(p, showGame) {
  const pick = p.kind === "game" ? p.pick : p.kind === "td" ? `Yes: ${p.player} anytime TD` : `${p.side.toUpperCase()} ${p.line} ${p.label}`;
  const hit = (p.series || []).length && p.line != null ? (p.series.filter(v => p.side === "over" ? v > p.line : v < p.line).length + " of " + p.series.length) : "";
  return `<div class="pickcard" style="border:1px solid var(--line);border-left:4px solid var(--${p.conf_cls === "g" ? "g" : "y"});border-radius:10px;padding:8px 10px;margin:6px 0;background:var(--card2)">
    <div class="gh"><div><b style="font-size:15px">${p.player}</b> <span class="xs mut">${p.kind === "game" ? p.team + " @ " + p.opp : p.pos + " · " + p.team + (p.home ? " vs " : " @ ") + p.opp}</span> ${p.status === "questionable" ? '<span class="chip y">QUESTIONABLE</span>' : ""}</div>
      <span class="chip ${p.conf_cls}">${p.conf} · ${(p.p_final * 100).toFixed(0)}%</span></div>
    <div style="margin:3px 0"><b style="font-size:16px">${pick}</b> <span class="mut">${BK[p.book]} ${price(p.price)}</span>${hit ? ` <span class="xs mut">· ${hit} games this season went this way</span>` : ""}</div>
    <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap"><div>${bpSpark(p)}<div class="xs mut">2026 games so far, dashed = line</div></div>
      <div class="xs mut">${p.mu != null ? `our projection <b style="color:var(--tx)">${p.mu}</b> (±${p.sd})<br>` : ""}model ${(p.p_model * 100).toFixed(0)}% · market ${(p.p_market * 100).toFixed(0)}%</div></div>
    <ul class="notes">${p.why.map(x => `<li>+ ${x}</li>`).join("")}${p.risk.map(x => `<li style="color:var(--y)">! ${x}</li>`).join("")}</ul></div>`;
}
const BPS = {slot: "", sort: "time", only: false};
function bpGame(g) {
  const c = D.bestprops.games[g.id]; if (!c) return "";
  const slots = ["QB", "WR", "RB", "TE"].filter(s => !BPS.slot || BPS.slot === s);
  const body = slots.map(s => { const ps = (c[s] || []).filter(p => !BPS.only || p.p_final >= 0.57); return `<h3 class="dh3">${BPNAME[s]}</h3>${ps.map(p => bpPickCard(p)).join("") || `<div class="mut small">No ${BPNAME[s].toLowerCase()} prop clears the filters (price between +120 and -140 and a model that agrees).</div>`}`; }).join("");
  return `<div class="game"><div class="gh"><h3>${g.away} @ ${g.home}</h3><span class="mut small">${new Date(g.kickoff).toLocaleString("en-US", {...ET, month: "short", day: "numeric"})} ET · <a href="#" style="color:var(--acc)" onclick="openDeep('${g.id}');return false">Deep dive →</a></span></div>${body}</div>`;
}
function bpWatch(w) {
  if (!w.found) return `<div class="game"><b>${w.name}</b><div class="mut small">No props are posted for this player this week.</div></div>`;
  const rows = w.markets.map(m => `<tr><td class="lab">${m.label}</td><td>${m.ref_line ?? "-"}</td><td><b>${m.mu}</b><span class="xs mut"> ±${m.sd}</span></td>
    <td><b>${m.side.toUpperCase()} ${m.line}</b><br><span class="xs mut">${BK[m.book]} ${price(m.price)}${m.in_range ? "" : " (outside +120 to -140)"}</span>${m.alt ? `<br><span class="xs mut">in range: ${m.alt.side} ${m.alt.line} ${BK[m.alt.book]} ${price(m.alt.price)} (${(m.alt.p_final * 100).toFixed(0)}%)</span>` : ""}</td>
    <td><span class="chip ${m.conf_cls}">${(m.p_final * 100).toFixed(0)}%</span><br><span class="xs mut">model ${(m.p_model * 100).toFixed(0)}% · mkt ${(m.p_market * 100).toFixed(0)}%</span></td><td class="xs">${m.hit_over != null ? Math.round(m.hit_over * 100) + "% over this season" : ""}</td></tr>`).join("");
  const top = w.markets[0], u = w.usage;
  return `<div class="game"><div class="gh"><h3>${w.name} <span class="xs mut">${w.pos} · ${w.team} vs ${w.opp}</span></h3><span>${w.status !== "healthy" ? `<span class="chip y">${w.status.toUpperCase()}</span>` : '<span class="chip g">HEALTHY</span>'}</span></div>
    ${u ? `<div class="small mut">2026 role: ${u.tgt} targets${u.tgt_share != null ? " (" + (u.tgt_share * 100).toFixed(0) + "% of team)" : ""}, ${u.rec_yds} receiving yards, ${u.car} carries, ${u.snap != null ? u.snap + "% of snaps" : "snap share n/a"}${u.rz != null ? `, ${u.rz} red-zone touches` : ""}.</div>` : ""}
    <div class="tw"><table class="tbl"><thead><tr><th>Prop</th><th>Line</th><th>Our projection</th><th>Lean</th><th>Win chance</th><th>Recent</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${w.td ? `<div class="small">Anytime TD: ${price(w.td.best_price)} at ${BK[w.td.best_book]}, our chance ${(w.td.p_model * 100).toFixed(0)}% vs market ${(w.td.p_market * 100).toFixed(0)}%.</div>` : ""}
    <ul class="notes">${top.why.map(x => `<li>+ ${x}</li>`).join("")}${top.risk.map(x => `<li style="color:var(--y)">! ${x}</li>`).join("")}</ul></div>`;
}
function renderBest() {
  const gs = D.games.filter(g => D.bestprops.games[g.id]).sort((a, b) => BPS.sort === "conf" ? Math.max(0, ...Object.values(D.bestprops.games[b.id]).flat().map(p => p.p_final)) - Math.max(0, ...Object.values(D.bestprops.games[a.id]).flat().map(p => p.p_final)) : a.kickoff.localeCompare(b.kickoff));
  $("#bplist").innerHTML = gs.map(bpGame).join("");
}
function cpLab(l) { return `<span class="badge ${l === "FIRM" ? "g" : "y"}">${l}</span>`; }
function cpProp(p) {
  return `<div class="cp"><div class="cp1">${cpLab(p.label_card)} <b>${p.player}</b> <span class="xs mut">${p.pos} · ${p.team} ${p.home ? "vs" : "@"} ${p.opp}</span></div>
    <div class="cp2"><b>${p.side.toUpperCase()} ${p.line} ${p.label}</b> <span class="mut">${BK[p.book]} ${price(p.price)}</span></div>
    <div class="xs mut">Our chance ${(p.p_new * 100).toFixed(0)}% vs ${((p.p_new - p.edge) * 100).toFixed(0)}% priced in (edge +${(p.edge * 100).toFixed(1)} pts) · market ${(p.p_market * 100).toFixed(0)}% · ${p.side} hit ${p.hit_txt}</div>
    <ul class="notes">${p.why.slice(0, 3).map(x => `<li>+ ${x}</li>`).join("")}${p.risk.slice(0, 2).map(x => `<li style="color:var(--y)">! ${x}</li>`).join("")}</ul></div>`;
}
function cpGame(p, g) {
  return `<div class="cp"><div class="cp1">${cpLab(p.label_card)} <b>${p.pick}</b> <span class="xs mut">${p.market === "spread" ? "spread" : "total"} · ${g || p.game}</span></div>
    <div class="cp2"><span class="mut">${BK[p.book]} ${price(p.price)}</span> <span class="xs mut">· EV ${p.ev >= 0 ? "+" : ""}${(p.ev * 100).toFixed(1)}%</span></div>
    <ul class="notes">${p.why.map(x => `<li>+ ${x}</li>`).join("")}${p.risk.map(x => `<li style="color:var(--y)">! ${x}</li>`).join("")}</ul></div>`;
}
function cpTd(t) {
  return `<div class="cp"><div class="cp1">${cpLab("LEAN")} <b>${t.player}</b> anytime TD <span class="xs mut">${t.pos} · ${t.team} vs ${t.opp}</span></div>
    <div class="cp2"><span class="mut">${BK[t.book]} ${price(t.price)}</span> <span class="xs mut">· our chance ${(t.p_final * 100).toFixed(0)}% vs ${(t.implied * 100).toFixed(0)}% implied</span></div>
    <div class="xs mut">${t.snap_pct}% of snaps · ${t.rz_pg} red-zone and ${t.gl_pg} goal-line touches a game · scored in ${t.td_games} of ${t.games} games. Touchdowns are high-variance.</div></div>`;
}
function initBest() {
  const C = D.card || {sunday: null, standalone: []};
  const kickTxt = iso => new Date(iso).toLocaleString("en-US", {...ET, weekday: "short", hour: "numeric", minute: "2-digit"});
  const none = what => `<div class="mut small">No ${what} passed the rules this week.</div>`;
  const prime = C.standalone.map(s => `<div class="game"><div class="gh"><h3>${s.away} @ ${s.home}</h3><span class="mut small">${kickTxt(s.kickoff)} ET · standalone game</span></div>
    <h3 class="dh3">Player props</h3>${s.props.map(cpProp).join("") || none("prop")}
    <h3 class="dh3">Game pick</h3>${s.game_pick ? cpGame(s.game_pick, `${s.away} @ ${s.home}`) : none("spread or total")}
    ${s.td ? `<h3 class="dh3">Touchdown with value</h3>${cpTd(s.td)}` : ""}</div>`).join("");
  const S = C.sunday;
  const sun = S ? `<div class="game"><div class="gh"><h3>Sunday main slate</h3><span class="mut small">${S.n_games} games before 7 PM ET</span></div>
    <h3 class="dh3">Player props (${S.props.length})</h3>${S.props.map(cpProp).join("") || none("prop")}
    <h3 class="dh3">Spreads (${S.spreads.length})</h3>${S.spreads.map(p => cpGame(p)).join("") || none("spread")}
    <h3 class="dh3">Totals (${S.totals.length})</h3>${S.totals.map(p => cpGame(p)).join("") || none("total")}</div>` : "";
  $("#bestroot").innerHTML = `<div class="card"><h2>Best Picks</h2><p class="small">The short list we would actually play, chosen by fixed rules before kickoff. <b>Sunday main slate:</b> 8 to 12 player props (at most 2 per game), 3 spreads and 2 totals. <b>Standalone games</b> (Thursday, Friday, holidays, Sunday night, Monday night): 2 player props and 1 spread or total each, plus an anytime touchdown only when our chance beats the price by 3+ points. If fewer picks pass, fewer are shown; nothing is added to fill a quota.</p>
    <p class="xs mut">Props need: a healthy starter with 5+ games this season, a real line (no receptions under 2.5, receiving yards under 25.5, rushing yards under 30.5, attempts under 10.5), a price of -115 or better on yardage (-125 on other props), and our chance beating the price's implied chance by 4+ points. FIRM = 6+ points of edge; LEAN = 4 to 6. Spreads and totals need +1% EV or more (FIRM at +3%); if our raw projection disagrees with the side, it is a LEAN at best. Paper picks, 1 unit each. The prop model is still being tested, so treat these as informed opinions, not locks.</p></div>
    ${prime ? `<h3 class="dh3">Standalone and primetime games</h3>${prime}` : ""}${sun}
    <details class="card"><summary><b>Every candidate by game</b> <span class="xs mut">(the long list these picks came from)</span></summary>
      <div class="ctl"><select id="bpsort"><option value="time">Sort games: kickoff</option><option value="conf">Sort games: most confident first</option></select>
      <span class="seg" id="bpslot"><button data-s="" class="on">All</button><button data-s="QB">QB</button><button data-s="WR">WR</button><button data-s="RB">RB</button><button data-s="TE">TE</button></span>
      <label class="tg"><input type="checkbox" id="bponly"> Good or high confidence only</label></div><div id="bplist"></div>
      ${D.bestprops.watch.length ? `<h3 class="dh3">Your watchlist</h3>${D.bestprops.watch.map(bpWatch).join("")}` : ""}</details>`;
  $("#bpsort").onchange = e => { BPS.sort = e.target.value; renderBest(); };
  $("#bponly").onchange = e => { BPS.only = e.target.checked; renderBest(); };
  document.querySelectorAll("#bpslot button").forEach(b => b.onclick = () => { document.querySelectorAll("#bpslot button").forEach(x => x.classList.remove("on")); b.classList.add("on"); BPS.slot = b.dataset.s; renderBest(); });
  renderBest();
}
