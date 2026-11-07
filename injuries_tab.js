/* ---------- Injuries tab (all games) ---------- */
const IGRP = {QB: "QB", RB: "RB", FB: "RB", WR: "WR", TE: "TE", T: "OL", G: "OL", C: "OL", OT: "OL", OG: "OL", OL: "OL", DE: "DL", DT: "DL", NT: "DL", DL: "DL", LB: "LB", OLB: "LB", ILB: "LB", MLB: "LB",
  CB: "DB", S: "DB", FS: "DB", SS: "DB", DB: "DB", K: "ST", PK: "ST", P: "ST", LS: "ST"};
const IGRP_ORDER = ["QB", "RB", "WR", "TE", "OL", "DL", "LB", "DB", "ST"];
const IGRP_NAME = {QB: "Quarterback", RB: "Running backs", WR: "Receivers", TE: "Tight ends", OL: "Offensive line", DL: "Defensive line", LB: "Linebackers", DB: "Secondary", ST: "Kickers / punters"};
const igrp = p => IGRP[String(p || "").trim()] || "ST";
const iimp = i => (i.snap_pct || 0) + 2 * (i.car || 0) + 3 * (i.tgt || 0);
const isc = s => s === "out" || s === "doubtful" ? "r" : "y";
const IS = {sort: "impact", team: "", grp: "", status: "", q: ""};

function injTeamImpact(g, side) {
  const c = g.comp, k = side === "home" ? "home" : "away";
  const skill = c["inj_" + k] || 0, line = c["inj_net_" + k] || 0;
  return {skill, line, total: skill + line};
}
function injRow(i) {
  const nxt = (i.next_up || []).slice(0, 2).map(n => `${n.name}${n.snap_pct != null ? " (" + n.snap_pct + "%)" : ""}`).join(", ");
  const use = [i.snap_pct != null ? i.snap_pct + "% snaps" + (i.long_term && i.snap_year ? " in " + i.snap_year : "") : "", i.car ? i.car + " carries" : "", i.tgt ? i.tgt + " targets" : ""].filter(Boolean).join(" · ");
  return `<tr><td class="lab"><b>${i.name}</b> <span class="xs mut">${i.pos}</span></td><td><span class="chip ${isc(i.status)}">${(i.raw_status || i.status).toUpperCase()}</span></td><td>${i.injury || "-"}<br><span class="xs mut">${(i.practice || "").replace(" in Practice", "") || "no practice info"}</span></td>
    <td class="xs">${use || "-"}</td><td class="xs">${nxt || "-"}</td><td class="xs">${i.long_term ? "<b>season-long</b>" : relT(i.date)}${i.hist ? "<br>" + i.hist.text : ""}${i.note ? "<br><span class='mut'>" + i.note + "</span>" : ""}</td></tr>`;
}
function injTeamBlock(g, d, team, side) {
  const items = d.injuries.filter(i => i.team === team && (!IS.grp || igrp(i.pos) === IS.grp) && (!IS.status || (IS.status === "out" ? (i.status === "out" || i.status === "doubtful") : i.status === "questionable")) && (!IS.q || i.name.toLowerCase().includes(IS.q)));
  const imp = injTeamImpact(g, side), mx = 6;
  const bar = (v, lab) => `<div class="xs" style="display:flex;align-items:center;gap:6px"><span style="min-width:104px">${lab}</span><div class="bar" style="width:110px"><i style="width:${Math.min(100, Math.abs(v) / mx * 100)}%;background:var(--${v <= -2 ? "r" : v <= -0.8 ? "y" : "g"})"></i></div><span>${v > 0 ? "+" : ""}${v.toFixed(1)} pts</span></div>`;
  const groups = IGRP_ORDER.map(gk => ({gk, rows: items.filter(i => igrp(i.pos) === gk).sort((a, b) => (a.status === "out" ? 0 : 1) - (b.status === "out" ? 0 : 1) || iimp(b) - iimp(a))})).filter(x => x.rows.length);
  const body = groups.map(x => `<tr class="grp"><td colspan="6">${IGRP_NAME[x.gk].toUpperCase()}</td></tr>${x.rows.map(injRow).join("")}`).join("");
  return `<div><div class="small"><b>${team}</b> · ${items.filter(i => i.status === "out").length} out, ${items.filter(i => i.status === "doubtful").length} doubtful, ${items.filter(i => i.status === "questionable").length} questionable</div>
    ${bar(imp.skill, "Skill players")}${bar(imp.line, "Line / defence")}<div class="xs mut" style="margin:2px 0 6px">Points our projection takes off ${team}'s scoring because of these absences (total ${imp.total > 0 ? "+" : ""}${imp.total.toFixed(1)}).</div>
    <div class="tw"><table class="tbl"><thead><tr><th>Player</th><th>Status</th><th>Injury / practice</th><th>Usual role</th><th>Next man up</th><th>Updated</th></tr></thead><tbody>${body || `<tr><td colspan="6" class="mut">${items.length === 0 && (IS.grp || IS.status || IS.q) ? "Nothing matches the filters." : "No flagged players."}</td></tr>`}</tbody></table></div></div>`;
}
function injGameCard(g) {
  const d = D.deeps[g.id]; if (!d) return "";
  const qbs = d.injuries.filter(i => i.pos === "QB" && i.status !== "healthy");
  const qbPen = t => qbs.filter(q => q.team === t && !q.long_term).reduce((s, q) => s - (q.status === "questionable" ? 1 : 4), 0);   // a missing starting QB is the biggest injury there is
  const ia = injTeamImpact(g, "away").total + qbPen(g.away), ih = injTeamImpact(g, "home").total + qbPen(g.home);
  const worse = ia < ih ? g.away : g.home, gap = Math.abs(ia - ih);
  const news = (d.injury_news || []).filter(n => /designation|participant|practiced/i.test(n.note)).slice(0, 3);
  return `<div class="game"><div class="gh"><h3>${g.away} @ ${g.home}</h3><span class="mut small">${new Date(g.kickoff).toLocaleString("en-US", {...ET, month: "short", day: "numeric"})} ET · <a href="#" style="color:var(--acc)" onclick="openDeep('${g.id}');return false">Deep dive →</a></span></div>
    <div class="small">${qbs.map(q => `<span class="chip ${isc(q.status)}">QB ${q.team}: ${q.name} ${q.status}</span>`).join(" ")} ${gap >= 0.8 ? `<span class="chip ${gap >= 2.5 ? "r" : "y"}">${worse} hurt more by injuries (${gap.toFixed(1)} pts)</span>` : `<span class="chip g">Injuries about even</span>`} ${news.length ? `<span class="xs mut">Cleared: ${news.map(n => n.name).join(", ")}</span>` : ""}</div>
    <div class="grid2" style="margin-top:6px">${injTeamBlock(g, d, g.away, "away")}${injTeamBlock(g, d, g.home, "home")}</div></div>`;
}
function renderInjuries() {
  let gs = D.games.filter(g => D.deeps[g.id] && (!IS.team || g.home === IS.team || g.away === IS.team));
  const score = g => injTeamImpact(g, "away").total + injTeamImpact(g, "home").total;
  gs.sort((a, b) => IS.sort === "impact" ? score(a) - score(b) : IS.sort === "time" ? a.kickoff.localeCompare(b.kickoff) : (a.away + a.home).localeCompare(b.away + b.home));
  $("#injlist").innerHTML = gs.map(injGameCard).join("") || `<p class="mut">No games match.</p>`;
}
function initInjuries() {
  const all = D.games.filter(g => D.deeps[g.id]).flatMap(g => D.deeps[g.id].injuries.map(i => ({...i, gid: g.id})));
  const cnt = s => all.filter(i => i.status === s).length;
  const top = all.filter(i => i.status === "out" || i.status === "doubtful").sort((a, b) => iimp(b) - iimp(a)).slice(0, 12);
  const teams = [...new Set(D.games.flatMap(g => [g.home, g.away]))].sort();
  $("#injroot").innerHTML = `<div class="card"><h2>Injuries: every game</h2><p class="small">Every flagged player on both teams of every game, from ESPN and the team reports with the official practice status, plus players on injured reserve or the PUP list who were hurt in earlier weeks and so are not on this week's report (marked season-long; their absence is already in the projection), ${D.ages.injuries ? `last refreshed ${agoTxt(ago(D.ages.injuries))}` : ""}. Bars show how many points our projection takes off each team's scoring (skill players, offensive line, defence). Questionable players are treated as 75% to play. Statuses can change until inactives post about 90 minutes before kickoff.</p></div>
    <div class="mgrid"><div class="m r"><b>${cnt("out")}</b><span>out or on IR</span></div><div class="m r"><b>${cnt("doubtful")}</b><span>doubtful</span></div><div class="m y"><b>${cnt("questionable")}</b><span>questionable</span></div><div class="m r"><b>${all.filter(i => i.long_term).length}</b><span>of the "out" are season-long (IR / PUP)</span></div></div>
    <h3 class="dh3">Biggest absences on the slate (by role: snaps, carries and targets)</h3>
    <div class="tw"><table class="tbl"><thead><tr><th>Player</th><th>Team</th><th>Game</th><th>Status</th><th>Injury</th><th>Usual role</th></tr></thead><tbody>${top.map(i => `<tr><td class="lab"><b>${i.name}</b> <span class="xs mut">${i.pos}</span></td><td>${i.team}</td><td class="xs">${GNAME[i.gid]}</td><td><span class="chip ${isc(i.status)}">${(i.raw_status || i.status).toUpperCase()}</span></td><td>${i.injury || "-"}</td><td class="xs">${i.snap_pct != null ? i.snap_pct + "% snaps" : ""}${i.car ? " · " + i.car + " carries" : ""}${i.tgt ? " · " + i.tgt + " targets" : ""}</td></tr>`).join("")}</tbody></table></div>
    <div class="ctl"><select id="injsort"><option value="impact">Sort: most hurt games first</option><option value="time">Sort: kickoff</option><option value="game">Sort: game</option></select>
    <select id="injteam"><option value="">All teams</option>${teams.map(t => `<option>${t}</option>`).join("")}</select>
    <select id="injgrp"><option value="">All positions</option>${IGRP_ORDER.map(x => `<option value="${x}">${IGRP_NAME[x]}</option>`).join("")}</select>
    <select id="injstatus"><option value="">All statuses</option><option value="out">Out / doubtful</option><option value="q">Questionable</option></select>
    <input id="injq" type="search" placeholder="Search a player" style="background:var(--card);color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:6px 8px;font-size:13px"></div><div id="injlist"></div>`;
  const u = () => { IS.sort = $("#injsort").value; IS.team = $("#injteam").value; IS.grp = $("#injgrp").value; IS.status = $("#injstatus").value; IS.q = $("#injq").value.trim().toLowerCase(); renderInjuries(); };
  ["#injsort", "#injteam", "#injgrp", "#injstatus"].forEach(s => $(s).onchange = u);
  $("#injq").oninput = u;
  renderInjuries();
}
