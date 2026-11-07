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
function initBest() {
  const all = Object.entries(D.bestprops.games).flatMap(([gid, c]) => Object.values(c).flat());
  const top = all.slice().sort((a, b) => b.p_final - a.p_final).slice(0, 8);
  const nHigh = all.filter(p => p.p_final >= 0.62).length, nGood = all.filter(p => p.p_final >= 0.57 && p.p_final < 0.62).length;
  const mn = D.bestprops.mnf;
  const mnHtml = mn ? `<div class="card"><h2>Monday Night Football: 5 best bets</h2><p class="small">${mn.away} @ ${mn.home}, ${new Date(mn.kickoff).toLocaleString("en-US", {...ET, weekday: "short", hour: "numeric", minute: "2-digit"})} ET. Chosen from this game's best props, anytime TDs, spread and total, ranked by win chance after the ${Math.round(D.cfg.w.prop * 100)}/${Math.round((1 - D.cfg.w.prop) * 100)} model/market blend, one bet per player. None of this is proven yet; check the inactives before kickoff.</p>
    ${mn.picks.map((p, i) => `<div class="xs mut" style="margin-top:8px">BET ${i + 1}</div>` + bpPickCard(p)).join("")}</div>` : "";
  $("#bestroot").innerHTML = mnHtml + `<div class="card"><h2>Best props</h2><p class="small">For every game: our favourite <b>1 quarterback</b>, <b>2 wide receiver</b>, <b>2 running back</b> and <b>1 tight end</b> prop, using the real lines the books post, built from this season's games only plus the opposing defences (run defence, pass defence, and what they allow to that position), priced between <b>+120 and -140</b>. This is about which props we are <b>most confident will win</b>, not which have the most expected value. Each slot gets the best-supported prop (our model backs the side and the market does not strongly disagree); only if nothing qualifies do the filters relax, and those picks are flagged as weaker. Picks are ranked by win chance after blending ${Math.round(D.cfg.w.prop * 100)}% model / ${Math.round((1 - D.cfg.w.prop) * 100)}% market. Anytime TDs can fill a receiver, back or tight-end slot when the price is in range.</p>
    <p class="xs mut">${all.length} picks across ${D.games.length} games: ${nHigh} high confidence (62%+), ${nGood} good (57-62%), the rest lean. The prop model has not yet been tested against real results, so even the best picks are around 55-63%, not locks. Every pick here is saved before kickoff and graded in Results under "Best props picks". Check Sunday's inactives before betting.</p></div>
    <h3 class="dh3">Your watchlist, taken apart</h3>${D.bestprops.watch.map(bpWatch).join("")}
    <h3 class="dh3">Most confident picks on the slate</h3><div class="tw"><table class="tbl"><thead><tr><th>Pick</th><th>Game</th><th>Price</th><th>Win chance</th></tr></thead><tbody>${top.map(p => `<tr><td class="lab"><b>${p.player}</b> <span class="xs mut">${p.pos}</span><br>${p.kind === "td" ? "anytime TD" : p.side.toUpperCase() + " " + p.line + " " + p.label}</td><td class="xs">${GNAME[p.game_id]}</td><td>${BK[p.book]} ${price(p.price)}</td><td><span class="chip ${p.conf_cls}">${(p.p_final * 100).toFixed(0)}%</span></td></tr>`).join("")}</tbody></table></div>
    <div class="ctl"><select id="bpsort"><option value="time">Sort games: kickoff</option><option value="conf">Sort games: most confident first</option></select>
    <span class="seg" id="bpslot"><button data-s="" class="on">All</button><button data-s="QB">QB</button><button data-s="WR">WR</button><button data-s="RB">RB</button><button data-s="TE">TE</button></span>
    <label class="tg"><input type="checkbox" id="bponly"> Good or high confidence only</label></div><div id="bplist"></div>`;
  $("#bpsort").onchange = e => { BPS.sort = e.target.value; renderBest(); };
  $("#bponly").onchange = e => { BPS.only = e.target.checked; renderBest(); };
  document.querySelectorAll("#bpslot button").forEach(b => b.onclick = () => { document.querySelectorAll("#bpslot button").forEach(x => x.classList.remove("on")); b.classList.add("on"); BPS.slot = b.dataset.s; renderBest(); });
  renderBest();
}
