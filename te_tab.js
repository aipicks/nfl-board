/* ---------- TE Touchdowns: best tight-end scoring spots on the next game day ---------- */
function teCard(r, i) {
  const d = r.d;
  return `<div class="game"><div class="gh"><h3>#${i + 1} ${r.player} <span class="xs mut">${r.team} ${r.home ? "vs" : "@"} ${r.opp}</span> ${r.status === "questionable" ? '<span class="chip y">QUESTIONABLE</span>' : ""}</h3><span class="chip g">TE score ${r.score}</span></div>
    <div style="margin:3px 0"><b style="font-size:16px">Anytime TD</b> <span class="mut">${BK[r.book]} ${price(r.price)}</span> · our chance <b>${(r.p_model * 100).toFixed(0)}%</b> · market ${(r.p_market * 100).toFixed(0)}%</div>
    <div class="mgrid"><div class="m r"><b>#${d.r_te_td}</b><span>TE TDs allowed (${d.te_td}/G)</span></div><div class="m r"><b>#${d.r_te_rz}</b><span>TE red-zone targets allowed (${d.te_rz}/G)</span></div><div class="m r"><b>#${d.r_epa}</b><span>worst pass defence</span></div><div class="m ${d.r_rz && d.r_rz <= 10 ? "r" : "y"}"><b>${d.r_rz ? "#" + d.r_rz : "-"}</b><span>worst red-zone defence${d.rz_td != null ? " (" + d.rz_td + "% TD)" : ""}</span></div></div>
    <ul class="notes">${r.why.map(x => `<li>+ ${x}</li>`).join("")}${r.risk.map(x => `<li style="color:var(--y)">! ${x}</li>`).join("")}</ul></div>`;
}
function initTe() {
  const T = D.te;
  if (!T || !T.day) { $("#teroot").innerHTML = `<div class="card"><h2>TE touchdowns</h2><p class="mut">No upcoming games.</p></div>`; return; }
  const dayTxt = new Date(T.day + "T12:00:00").toLocaleDateString("en-US", {weekday: "long", month: "short", day: "numeric"});
  const rows = T.rows.map((r, i) => `<tr><td>${i + 1}</td><td class="lab"><b>${r.player}</b> <span class="xs mut">${r.team}</span>${r.status === "questionable" ? ' <span class="chip y">Q</span>' : ""}</td><td class="xs">${T.games[r.game_id]}</td><td>${BK[r.book]} ${price(r.price)}</td>
    <td><b>${(r.p_model * 100).toFixed(0)}%</b> <span class="xs mut">mkt ${(r.p_market * 100).toFixed(0)}%</span></td><td>#${r.d.r_te_td}</td><td>#${r.d.r_te_rz}</td><td>#${r.d.r_epa}</td><td>${r.d.r_rz ? "#" + r.d.r_rz : "-"}</td><td><span class="chip ${r.score >= 85 ? "g" : "y"}">${r.score}</span></td></tr>`).join("");
  const defs = T.defences.map((x, i) => `<tr><td>${i + 1}</td><td class="lab"><b>${x.team}</b></td><td>${x.te_td.toFixed(2)} <span class="xs mut">#${x.r_te_td}</span></td><td>${x.te_rz_tgt.toFixed(2)} <span class="xs mut">#${x.r_te_rz_tgt}</span></td><td>${x.te_yds.toFixed(0)} <span class="xs mut">#${x.r_te_yds}</span></td><td>${x.epa_pass.toFixed(3)} <span class="xs mut">#${x.r_epa_pass}</span></td></tr>`).join("");
  $("#teroot").innerHTML = `<div class="card"><h2>TE touchdowns: ${dayTxt}</h2><p class="small">The three tight ends most likely to score on the next game day, picked against the defences that are worst for tight ends. <b>TE score (0-100)</b> = 60% how likely our touchdown model thinks he scores (usage, red-zone and goal-line touches, scoring environment) + 40% how bad the opposing defence is for tight ends: tight-end touchdowns allowed, tight-end red-zone targets allowed, tight-end yards allowed, pass defence and red-zone defence, all from 2026 games. Rank #1 = the worst defence. Only one tight end per team in the top three.</p>
    <p class="xs mut">Anytime TDs are long shots: even the best spot is about 3 in 10 to 4 in 10. Our touchdown model beat a flat rate in backtests but has not yet proven itself against the market. Check inactives before kickoff.</p></div>
    ${T.top.map(teCard).join("")}
    <h3 class="dh3">Every tight end on the slate</h3><div class="tw"><table class="tbl"><thead><tr><th>#</th><th>Tight end</th><th>Game</th><th>Anytime TD</th><th>Our chance</th><th>TE TDs allowed</th><th>TE red-zone targets</th><th>Pass D</th><th>Red-zone D</th><th>Score</th></tr></thead><tbody>${rows}</tbody></table></div>
    <h3 class="dh3">Defences, worst against tight ends first</h3><div class="tw"><table class="tbl"><thead><tr><th>#</th><th>Defence</th><th>TE TDs per game</th><th>TE red-zone targets per game</th><th>TE yards per game</th><th>EPA per dropback allowed</th></tr></thead><tbody>${defs}</tbody></table></div>`;
}
