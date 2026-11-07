/* ---------- Deep Dive tab ---------- */
let DP = null;
const fm = (f, v) => {
  if (v == null || isNaN(v)) return "-";
  const dec = (f.match(/\.(\d)/) || [0, 1])[1] | 0;
  if (f.includes("%")) return (v * 100).toFixed(dec) + "%";
  return (f.includes("+") && v > 0 ? "+" : "") + v.toFixed(dec);
};
const rk = (r, good) => { if (r == null) return ""; const n = 32; const c = good ? (r <= 10 ? "g" : r <= 22 ? "y" : "r") : (r >= 23 ? "g" : r >= 11 ? "y" : "r"); return `<span class="chip ${c}">#${r}</span>`; };
function dsec(id, title, sub) { return `<h2 class="dh" id="${id}">${title}${sub ? ` <span class="xs mut">${sub}</span>` : ""}</h2>`; }

/* rank chips already encode "1 = best for that unit" (offence: best attack; defence: best defence), so every chip uses good=true colouring */
function dMetricTable2(side, title) {
  const a = DP.away, h = DP.home;
  let last = "";
  const rows = DP.metrics[side].map(r => {
    const ok = r.better !== null && r.better !== undefined;
    const c = o => o ? `<span class="v">${fm(r.fmt, o.v26)}</span> ${ok ? rk(o.r26, true) : ""}<span class="xs mut y25 blk">2025: ${fm(r.fmt, o.v25)} ${ok && o.r25 != null ? "#" + o.r25 : ""}</span>` : "";
    const head = r.group !== last ? `<tr class="grp"><td colspan="4">${r.group.toUpperCase()}</td></tr>` : "";
    last = r.group;
    return `${head}<tr><td class="lab">${r.label}</td><td>${c(r[a])}</td><td>${c(r[h])}</td><td class="mut">${fm(r.fmt, r.lg26)}<span class="xs y25 blk">${fm(r.fmt, r.lg25)}</span></td></tr>`;
  }).join("");
  return `<div class="tw"><table class="tbl"><thead><tr><th>${title}</th><th>${a}</th><th>${h}</th><th>League</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function dStandouts() {
  const col = {g: "g", r: "r", y: "y"};
  return dsec("d-stand", "What stands out", "written from the numbers below, the injury report and our projection") +
    DP.standouts.map(s => `<h3 class="dh3">${s.title}</h3><ul class="dyn">${s.items.map(([tag, text]) => `<li><span class="chip ${col[tag]}">${tag === "g" ? "edge" : tag === "r" ? "problem" : "note"}</span> ${text}</li>`).join("")}</ul>`).join("") +
    `<div class="xs mut">Ranks are out of 32 with #1 best: for an offence that means best at attacking, for a defence best at stopping it. "Edge" = good for the team named, "problem" = bad for the team named.</div>`;
}
function dWeather() {
  const W = DP.weather, hrs = W.hours, k = W.kickoff_hour_index, K = hrs[k];
  const cl = (v, g, y, inv) => inv ? (v >= g ? "g" : v >= y ? "y" : "r") : (v < g ? "g" : v < y ? "y" : "r");
  const tcls = t => (t >= 40 && t <= 80) ? "g" : ((t >= 32 && t < 40) || (t > 80 && t <= 90)) ? "y" : "r";
  const card = (b, l, c) => `<div class="m ${c || ""}"><b>${b}</b><span>${l}</span></div>`;
  const mi = K.visibility / 1609.34, inhg = K.surface_pressure * 0.02953;
  const cards = [card(Math.round(K.temperature_2m) + "°F", "temperature", tcls(K.temperature_2m)), card(Math.round(K.apparent_temperature) + "°F", "feels like", tcls(K.apparent_temperature)),
    card(K.windspeed_10m.toFixed(0) + " mph", `wind from ${K.wind_dir} (${K.winddirection_10m.toFixed(0)}°)`, cl(K.windspeed_10m, 10, 15)), card(K.windgusts_10m.toFixed(0) + " mph", "gusts", cl(K.windgusts_10m, 20, 30)),
    card(K.precipitation_probability.toFixed(0) + "%", "precipitation chance", cl(K.precipitation_probability, 20, 50)), card(K.precipitation.toFixed(2) + " in", "rain this hour", cl(K.precipitation, 0.02, 0.1)),
    card(K.snowfall.toFixed(1) + " in", "snow this hour", K.snowfall > 0 ? "r" : "g"), card(K.relative_humidity_2m.toFixed(0) + "%", "humidity", ""), card(Math.round(K.dew_point_2m) + "°F", "dew point", ""),
    card(K.cloudcover.toFixed(0) + "%", "cloud cover", ""), card(mi.toFixed(1) + " mi", "visibility", mi >= 6 ? "g" : mi >= 3 ? "y" : "r"), card(inhg.toFixed(2) + " inHg", `station pressure (${K.surface_pressure.toFixed(0)} hPa)`, ""),
    card(K.air_density.toFixed(3), `air density kg/m³ (${W.density_vs_sea_level_pct}% vs sea level)`, W.density_vs_sea_level_pct < -8 ? "y" : ""), card(K.cape.toFixed(0), "CAPE (storm energy)", K.cape > 500 ? "r" : "g"),
    card(K.cond, "sky / conditions", "")].join("");
  const rows = hrs.map((x, i) => `<tr class="${i === k ? "ko" : ""}"><td>${x.et}${i === k ? " <b>KO</b>" : ""}</td><td><span class="chip ${tcls(x.temperature_2m)}">${Math.round(x.temperature_2m)}°</span></td><td>${Math.round(x.apparent_temperature)}°</td>
    <td>${x.relative_humidity_2m.toFixed(0)}%</td><td><span class="chip ${cl(x.windspeed_10m, 10, 15)}">${x.windspeed_10m.toFixed(0)}</span></td><td><span class="chip ${cl(x.windgusts_10m, 20, 30)}">${x.windgusts_10m.toFixed(0)}</span></td>
    <td>${x.wind_dir}</td><td><span class="chip ${cl(x.precipitation_probability, 20, 50)}">${x.precipitation_probability.toFixed(0)}%</span></td><td>${x.precipitation.toFixed(2)}</td><td>${x.cloudcover.toFixed(0)}%</td><td>${(x.visibility / 1609.34).toFixed(1)}</td><td>${x.air_density.toFixed(3)}</td><td class="xs">${x.cond}</td></tr>`).join("");
  // chart
  const w = 640, ht = 170, pad = 28, n = hrs.length, X = i => pad + i * (w - 2 * pad) / (n - 1), mx = Math.max(45, ...hrs.map(x => x.windgusts_10m)) + 3;
  const Y = v => ht - 22 - (v / mx) * (ht - 40);
  const line = (key, col, dash) => `<polyline fill="none" stroke="${col}" stroke-width="2" ${dash ? 'stroke-dasharray="6 4"' : ""} points="${hrs.map((x, i) => X(i) + "," + Y(x[key])).join(" ")}"/>` + hrs.map((x, i) => `<circle cx="${X(i)}" cy="${Y(x[key])}" r="3" fill="${col}"/>`).join("");
  const rain = hrs.map((x, i) => `<rect x="${X(i) - 8}" y="${Y(x.precipitation * 100)}" width="16" height="${Math.max(0, ht - 22 - Y(x.precipitation * 100))}" fill="#85B7EB" opacity=".7"/>`).join("");
  const svg = `<svg viewBox="0 0 ${w} ${ht}" width="100%" role="img" aria-label="Wind, gusts and rain by hour"><rect x="${X(k) - 14}" y="6" width="${X(Math.min(n - 1, k + 3.5)) - X(k) + 14}" height="${ht - 28}" fill="rgba(127,127,127,.15)"/>
    ${[0, 10, 20, 30, 40].filter(v => v <= mx).map(v => `<line x1="${pad}" x2="${w - pad}" y1="${Y(v)}" y2="${Y(v)}" stroke="rgba(127,127,127,.25)"/><text x="4" y="${Y(v) + 4}" font-size="10" fill="currentColor" opacity=".6">${v}</text>`).join("")}
    ${rain}${line("windgusts_10m", "#E24B4A", true)}${line("windspeed_10m", "#378ADD")}
    ${hrs.map((x, i) => `<text x="${X(i)}" y="${ht - 6}" font-size="10" text-anchor="middle" fill="currentColor" opacity=".7">${x.et.replace(":00 ", "")}</text>`).join("")}</svg>`;
  const nw = DP.nflweather;
  const hist = (rows, ttl) => `<div class="tw"><table class="tbl"><thead><tr><th>${ttl}</th><th>Games</th><th>Avg total vs line</th><th>Over %</th><th>Avg total</th></tr></thead><tbody>${rows.map(r => `<tr><td class="lab">${r.bucket}</td><td>${r.n}</td><td><span class="chip ${r.avg_diff < -0.7 ? "r" : r.avg_diff > 0.7 ? "g" : "y"}">${sgn(r.avg_diff)}</span></td><td>${(r.over_pct * 100).toFixed(0)}%</td><td>${r.avg_total}</td></tr>`).join("")}</tbody></table></div>`;
  const kk = DP.kicking, fg = b => kk.fg.filter(x => x.band === b);
  const fgrow = b => { const a = fg(b).find(x => x.at_home_stadium), e = fg(b).find(x => !x.at_home_stadium); return `<tr><td class="lab">FG ${b} yds</td><td>${a ? (a.pct * 100).toFixed(0) + "% (" + a.n + ")" : "-"}</td><td>${e ? (e.pct * 100).toFixed(0) + "% (" + e.n + ")" : "-"}</td></tr>`; };
  return dsec("d-weather", "Weather and environment", "Open-Meteo hourly forecast; game window shaded; KO = kickoff") + (DP.indoor ? `<div class="note" style="background:var(--gbg);border-color:var(--g)">Indoors (dome or closed roof): weather does not affect this game. The outside forecast below is for reference only.</div>` : "") +
    `<div class="mgrid">${cards}</div>
    <div class="xs mut" style="margin:6px 0">Legend: <span class="chip g">calm / mild</span> <span class="chip y">watch</span> <span class="chip r">impactful</span>. Blue line wind, red dashed gusts (mph), blue bars rain (hundredths of an inch).</div>${svg}
    <div class="tw"><table class="tbl"><thead><tr><th>Time ET</th><th>Temp</th><th>Feels</th><th>Humid</th><th>Wind</th><th>Gust</th><th>From</th><th>Precip %</th><th>Rain in</th><th>Cloud</th><th>Vis mi</th><th>Air dens.</th><th>Sky</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${nw ? `<div class="small" style="margin:6px 0">nflweather.com says: ${Math.round(nw.temp_f)}°F, wind ${Math.round(nw.wind_mph)} mph, ${Math.round(nw.precip_pct)}% precipitation, ${nw.conditions}, ${nw.indoor ? "indoors" : "outdoors"}.</div>` : ""}
    <div class="small" style="margin:6px 0">Model weather adjustment applied to the total: <b>${sgn(DP.projection.comp.weather)}</b> points (wind above 15 mph, rain/snow, cold below 25F; domes ignore it).</div>
    <div class="grid2">${hist(DP.weather_history.wind, "Wind (outdoor games since 2012)")}${hist(DP.weather_history.temp, "Temperature")}</div>
    <h3 class="dh3">Altitude and kicking at ${DP.home}'s stadium (2025-26 sample for kicking)</h3>
    <div class="tw"><table class="tbl"><thead><tr><th></th><th>At ${DP.home}</th><th>Elsewhere</th></tr></thead><tbody>${fgrow("under 40")}${fgrow("40-49")}${fgrow("50+")}
    <tr><td class="lab">Average punt (gross yds)</td><td>${kk.punt_gross.at}</td><td>${kk.punt_gross.elsewhere}</td></tr><tr><td class="lab">Kickoff touchback rate</td><td>${(kk.touchback_rate.at * 100).toFixed(0)}%</td><td>${(kk.touchback_rate.elsewhere * 100).toFixed(0)}%</td></tr>
    <tr><td class="lab">Average game total</td><td>${kk.avg_total_at} (${kk.games_at} games)</td><td>${kk.avg_total_elsewhere}</td></tr></tbody></table></div>`;
}

function dBars(arr, line, mu, lab, lo, hi) {
  const w = 640, ht = 150, pad = 24, data = arr.filter(a => a[0] >= lo && a[0] <= hi), mx = Math.max(...data.map(a => a[1])), n = hi - lo + 1, bw = (w - 2 * pad) / n;
  const X = v => pad + (v - lo + 0.5) * bw;
  return `<svg viewBox="0 0 ${w} ${ht}" width="100%" role="img" aria-label="${lab} probability distribution">${data.map(a => `<rect x="${pad + (a[0] - lo) * bw + 1}" y="${ht - 20 - a[1] / mx * (ht - 40)}" width="${Math.max(1, bw - 2)}" height="${a[1] / mx * (ht - 40)}" fill="${a[0] > line ? "#2fcf6b" : "#ff5a5f"}" opacity=".75"/>`).join("")}
    <line x1="${X(line)}" x2="${X(line)}" y1="6" y2="${ht - 20}" stroke="currentColor" stroke-width="2" stroke-dasharray="4 3"/><text x="${X(line) + 4}" y="14" font-size="11" fill="currentColor">market ${line}</text>
    <line x1="${X(mu)}" x2="${X(mu)}" y1="22" y2="${ht - 20}" stroke="#378ADD" stroke-width="2"/><text x="${X(mu) + 4}" y="28" font-size="11" fill="#378ADD">our used mean ${mu.toFixed(1)}</text>
    ${data.filter((a, i) => (a[0]) % 5 === 0).map(a => `<text x="${X(a[0])}" y="${ht - 5}" font-size="10" text-anchor="middle" fill="currentColor" opacity=".7">${a[0]}</text>`).join("")}</svg>`;
}

function dMatchups() {
  const a = DP.away, h = DP.home, off = Object.fromEntries(DP.metrics.off.map(r => [r.key, r])), de = Object.fromEntries(DP.metrics.def.map(r => [r.key, r]));
  const rowsDef = [["#", "PASSING"], ["epa_pass", "Passing efficiency (EPA per dropback)"], ["sr_pass", "Pass success rate"], ["ypa", "Yards per pass attempt"], ["comp_pct", "Completion %"], ["cpoe", "Accuracy: completion % above expected"], ["expl_pass", "Explosive passes (20+ yards)"], ["int_rate", "Interception rate"],
    ["#", "RUSHING"], ["epa_rush", "Run efficiency (EPA per play)"], ["sr_rush", "Run success rate"], ["rush_ypc", "Yards per carry"], ["expl_rush", "Explosive runs (10+ yards)"], ["stuff_rate", "Runs stuffed (0 or less)"],
    ["#", "OTHER"], ["sack_rate", "Pass protection vs pass rush (sack rate)"], ["qbhit_rate", "Pass protection vs pass rush (QB hit rate)"], ["third", "3rd down"], ["rz_td", "Red zone TD %"], ["ppd", "Points per drive"], ["pts_pg", "Points per game"]];
  const t = (offT, defT) => `<div class="tw"><table class="tbl"><thead><tr><th>${offT} offence vs ${defT} defence</th><th>${offT} offence</th><th>${defT} defence</th></tr></thead><tbody>` + rowsDef.map(([k, l]) => {
    if (k === "#") return `<tr class="grp"><td colspan="3">${l}</td></tr>`;
    const o = off[k], d = de[k]; if (!o || !d) return "";
    const ro = o[offT], rd = d[defT];
    return `<tr><td class="lab">${l}</td><td><span class="v">${fm(o.fmt, ro.v26)}</span> ${rk(ro.r26, true)} <span class="xs mut y25">25: ${fm(o.fmt, ro.v25)}</span></td><td><span class="v">${fm(d.fmt, rd.v26)}</span> ${rk(rd.r26, true)} <span class="xs mut y25">25: ${fm(d.fmt, rd.v25)}</span></td></tr>`;
  }).join("") + `</tbody></table></div>`;
  return dsec("d-match", "Head-to-head matchups", "rank chips: #1 = best in the league at that unit") + `<div class="grid2">${t(a, h)}${t(h, a)}</div>`;
}

function dPos() {
  const a = DP.away, h = DP.home;
  const rows = DP.pos_allowed.map(r => { const c = o => o ? `<span class="v">${o.v26 == null ? "-" : o.v26.toFixed(1)}</span> ${o.r26 == null ? "" : `<span class="chip ${o.r26 <= 10 ? "g" : o.r26 <= 22 ? "y" : "r"}">#${o.r26}</span>`}<span class="xs mut y25 blk">2025: ${o.v25 == null ? "-" : o.v25.toFixed(1)} #${o.r25}</span>` : "";
    return `<tr><td class="lab">${r.label}</td><td>${c(r[a])}</td><td>${c(r[h])}</td><td class="mut">${r.lg26.toFixed(1)}<span class="xs y25 blk">${r.lg25.toFixed(1)}</span></td></tr>`; }).join("");
  const def = DP.defenders.map(d => `<tr><td>${d.team}</td><td class="lab">${d.name} <span class="xs mut">${d.pos}</span></td><td>${d.g}</td><td>${d.pd}</td><td>${d.ints}</td><td>${d.sacks}</td><td>${d.hits}</td><td>${d.tfl}</td><td>${d.solo}</td><td>${d.ff}</td></tr>`).join("");
  return dsec("d-pos", "Coverage and pass-rush profile; what each defence allows by position", "per game; #1 = allows the MOST (soft spot for the attacker, green)") +
    `<div class="tw"><table class="tbl"><thead><tr><th>Allowed per game to...</th><th>${a} defence</th><th>${h} defence</th><th>League</th></tr></thead><tbody>${rows}</tbody></table></div>
    <h3 class="dh3">Top defenders by pass-defence and pass-rush production (2026)</h3>
    <div class="tw"><table class="tbl"><thead><tr><th>Tm</th><th>Player</th><th>G</th><th>PD</th><th>INT</th><th>Sacks</th><th>QB hits</th><th>TFL</th><th>Solo</th><th>FF</th></tr></thead><tbody>${def}</tbody></table></div>
    <div class="xs mut">Man vs zone coverage rates, pressure rate and blown-block data are not in the free sources; completion %, accuracy vs expected, air yards, YAC, sack, QB-hit and interception rates above are the coverage and rush proxies.</div>`;
}

function dPlayers() {
  const a = DP.away, h = DP.home;
  const qb = DP.qbs.filter(q => q.season === 2026 || q.dropbacks > 100).map(q => `<tr><td>${q.team}</td><td class="lab">${q.name} <span class="xs mut">${q.season}</span></td><td>${q.games}</td><td>${q.att}</td><td>${(q.comp / q.att * 100).toFixed(1)}%</td><td>${q.ypa.toFixed(2)}</td><td>${q.td}/${q.ints}</td>
    <td><span class="chip ${q.epa_db > 0.05 ? "g" : q.epa_db > -0.05 ? "y" : "r"}">${sgn(q.epa_db * 100) }</span></td><td>${q.cpoe == null ? "-" : sgn(q.cpoe)}</td><td>${q.adot.toFixed(1)}</td><td><span class="chip ${q.sack_rate < 0.05 ? "g" : q.sack_rate < 0.07 ? "y" : "r"}">${(q.sack_rate * 100).toFixed(1)}%</span></td><td>${q.qb_hits}</td></tr>`).join("");
  const us = DP.usage.map(u => `<tr><td>${u.team}</td><td class="lab">${u.name} <span class="xs mut">${u.pos}</span></td><td>${u.snap ?? "-"}${u.snap != null ? "%" : ""}</td><td>${u.tgt}</td><td><span class="chip ${u.tgt_share >= 0.2 ? "g" : u.tgt_share >= 0.1 ? "y" : "r"}">${u.tgt_share == null ? "-" : (u.tgt_share * 100).toFixed(0) + "%"}</span></td>
    <td>${u.rec}</td><td>${u.rec_yds}</td><td>${u.ypt ?? "-"}</td><td>${u.adot ?? "-"}</td><td>${u.rec_td}</td><td>${u.car}</td><td>${u.car_share == null ? "-" : (u.car_share * 100).toFixed(0) + "%"}</td><td>${u.rush_yds}</td><td>${u.ypc ?? "-"}</td><td>${u.rush_td}</td><td>${u.rz ?? "-"}</td><td>${u.gl ?? "-"}</td></tr>`).join("");
  return dsec("d-players", "Quarterbacks and skill-player usage", "2026 season; QB EPA shown x100 per dropback") +
    `<div class="tw"><table class="tbl"><thead><tr><th>Tm</th><th>QB</th><th>G</th><th>Att</th><th>Cmp%</th><th>Y/A</th><th>TD/INT</th><th>EPA/db</th><th>Accuracy vs exp.</th><th>aDOT</th><th>Sack%</th><th>QB hits</th></tr></thead><tbody>${qb}</tbody></table></div>
    <div class="tw"><table class="tbl"><thead><tr><th>Tm</th><th>Player</th><th>Snap%</th><th>Tgt</th><th>Tgt sh</th><th>Rec</th><th>Yds</th><th>Y/T</th><th>aDOT</th><th>TD</th><th>Car</th><th>Car sh</th><th>Rush</th><th>YPC</th><th>TD</th><th>RZ</th><th>GL</th></tr></thead><tbody>${us}</tbody></table></div>
    <div class="xs mut">RZ = red-zone touches (targets + carries inside the 20), GL = goal-line touches (inside the 5).</div>`;
}

const relT = iso => { if (!iso) return "-"; const h = (Date.now() - Date.parse(iso)) / 36e5; return h < 1 ? Math.max(1, Math.round(h * 60)) + " min ago" : h < 48 ? h.toFixed(0) + " h ago" : Math.round(h / 24) + " d ago"; };
function dInjuries() {
  const sc = r => r.status === "out" ? "r" : r.status === "doubtful" ? "r" : "y";
  const last = DP.injuries.concat(DP.injury_news).map(r => r.date).filter(Boolean).sort().pop();
  const grp = t => { const x = DP.injuries.filter(r => r.team === t); return `${t}: ${x.filter(r => r.status === "out").length} out, ${x.filter(r => r.status === "doubtful").length} doubtful, ${x.filter(r => r.status === "questionable").length} questionable`; };
  const rows = DP.injuries.slice().sort((a, b) => a.team.localeCompare(b.team) || (b.date || "").localeCompare(a.date || "")).map(r =>
    `<tr><td>${r.team}</td><td class="lab"><b>${r.name}</b> <span class="xs mut">${r.pos}</span></td><td><span class="chip ${sc(r)}">${r.raw_status ? r.raw_status.toUpperCase() : r.status.toUpperCase()}</span></td><td>${r.injury || "-"}</td>
    <td class="xs">${r.practice ? r.practice.replace(" in Practice", "") : "-"}</td><td class="xs">${relT(r.date)}</td>
    <td>${r.snap_pct == null ? "-" : `<div class="bar" style="width:64px"><i style="width:${r.snap_pct}%;background:var(--${sc(r)})"></i></div><span class="xs mut">${r.snap_pct}% snaps</span>`}</td>
    <td class="xs">${r.tgt ? r.tgt + " tgt" : ""}${r.car ? (r.tgt ? ", " : "") + r.car + " car" : ""}</td>
    <td class="xs">${(r.next_up || []).map(n => `${n.name}${n.snap_pct != null ? " (" + n.snap_pct + "%)" : ""}`).join("<br>") || "-"}</td><td class="xs">${r.hist ? r.hist.text + "<br>" : ""}<span class="mut">${r.note || ""}</span></td></tr>`).join("");
  const news = DP.injury_news.map(r => `<tr><td>${r.team}</td><td class="lab"><b>${r.name}</b> <span class="xs mut">${r.pos}</span></td><td><span class="chip g">NO DESIGNATION</span></td><td class="xs">${relT(r.date)}</td><td class="xs">${r.note}</td></tr>`).join("");
  return dsec("d-inj", "Injury report and latest updates", `latest ESPN/team report ${relT(last)}; statuses can change until inactives post about 90 minutes before kickoff`) +
    `<div class="mgrid"><div class="m r"><b>${DP.injuries.filter(r => r.team === DP.away && r.status === "out").length + DP.injuries.filter(r => r.team === DP.home && r.status === "out").length}</b><span>players ruled out</span></div>
     <div class="m y"><b>${DP.injuries.filter(r => r.status === "questionable" || r.status === "doubtful").length}</b><span>questionable / doubtful</span></div><div class="m g"><b>${DP.injury_news.filter(r => /designation|participant/i.test(r.note)).length}</b><span>cleared (no designation / full practice)</span></div></div>
     <div class="small">${grp(DP.away)} · ${grp(DP.home)}. Red = out or doubtful, yellow = questionable. Next man up comes from the depth chart (snap share in brackets).</div>
     ${rows ? `<div class="tw"><table class="tbl"><thead><tr><th>Tm</th><th>Player</th><th>Status</th><th>Injury</th><th>Practice</th><th>Updated</th><th>Usual snaps</th><th>Usage</th><th>Next man up</th><th>How long out and history</th></tr></thead><tbody>${rows}</tbody></table></div>` : `<p class="mut">No flagged players on either team.</p>`}
     <h3 class="dh3">Other availability news (no game-status designation)</h3>
     <div class="tw"><table class="tbl"><thead><tr><th>Tm</th><th>Player</th><th>Status</th><th>Updated</th><th>Report</th></tr></thead><tbody>${news}</tbody></table></div>
     <div class="xs mut">Defensive and offensive-line absences are shown here but not priced into our projection (only QB and skill-player availability is).</div>`;
}

function dHistory() {
  const H = DP.history, a = DP.away, h = DP.home;
  const log = t => `<div class="tw"><table class="tbl"><thead><tr><th>${t} 2026</th><th>Opp</th><th>Score</th><th>ATS</th><th>O/U</th><th>Line</th><th>Temp</th><th>Wind</th></tr></thead><tbody>${H.logs[t].map(r => `<tr><td>Wk ${r.week}</td><td>${r.home ? "vs" : "@"} ${r.opp}</td><td>${r.pf}-${r.pa}</td><td><span class="chip ${r.ats === "W" ? "g" : r.ats === "L" ? "r" : "y"}">${r.ats}</span></td><td><span class="chip ${r.ou === "O" ? "g" : r.ou === "U" ? "r" : "y"}">${r.ou}</span></td><td>${r.line}</td><td>${r.temp ?? "-"}</td><td>${r.wind ?? "-"}</td></tr>`).join("")}</tbody></table></div>`;
  const tr = t => { const x = DP.trend[t]; const mx = 0.5; return `<div class="small"><b>${t}</b> weekly EPA: ` + x.map(r => `<span class="chip ${r.off_epa_pass > 0.1 ? "g" : r.off_epa_pass > -0.05 ? "y" : "r"}" title="wk${r.week} off pass EPA ${r.off_epa_pass.toFixed(2)}, def pass EPA ${r.def_epa_pass.toFixed(2)}">W${r.week} ${sgn(r.off_epa_pass * 100)}/${sgn(r.def_epa_pass * 100)}</span>`).join(" ") + `</div>`; };
  return dsec("d-hist", "Game logs, trends and history", "ATS from the team's side; O/U vs closing total") + `<div class="grid2">${log(a)}${log(h)}</div>
    <div class="xs mut" style="margin:4px 0">Weekly chips: offence pass EPA/dropback / defence pass EPA allowed (x100). Green = strong offence week.</div>${tr(a)}${tr(h)}
    <div class="grid2" style="margin-top:8px"><div class="tw"><table class="tbl"><thead><tr><th>Context</th><th>Value</th></tr></thead><tbody>
    <tr><td class="lab">Last meetings</td><td>${H.meetings.map(m => `${m.season} wk${m.week}: ${m.away} @ ${m.home} ${m.score} (total ${m.total}, line ${m.line ?? "-"})`).join("<br>") || "none since 2015"}</td></tr>
    <tr><td class="lab">${h} home games since 2018</td><td>${H.home_team.n} games, avg total ${H.home_team.avg_total} vs line ${H.home_team.avg_line}, over ${(H.home_team.over_pct * 100).toFixed(0)}%, avg margin ${sgn(H.home_team.avg_margin)}, cover ${(H.home_team.cover_pct * 100).toFixed(0)}%</td></tr>
    <tr><td class="lab">${H.day.label} games since 2015</td><td>${H.day.n} games, avg total ${H.day.avg_total} vs ${H.day.avg_line}, over ${(H.day.over_pct * 100).toFixed(0)}%, home win ${(H.day.home_win_pct * 100).toFixed(0)}%</td></tr>
    <tr><td class="lab">Previous games</td><td>${a}: wk${DP.previous_game[a].week} ${DP.previous_game[a].home ? "vs" : "@"} ${DP.previous_game[a].opp} ${DP.previous_game[a].score}<br>${h}: wk${DP.previous_game[h].week} ${DP.previous_game[h].home ? "vs" : "@"} ${DP.previous_game[h].opp} ${DP.previous_game[h].score}</td></tr>
    <tr><td class="lab">Rest / travel</td><td>${a} ${DP.rest.away} days, ${h} ${DP.rest.home} days; ${a} travels ${DP.travel_miles?.toLocaleString()} mi; altitude ${Object.entries(DP.altitude_ft).map(([k, v]) => k + " " + v.toLocaleString() + " ft").join(", ")}</td></tr></tbody></table></div></div>`;
}

function dProps() {
  const rows = DP.players.props_idx.map(i => D.props[i]), tds = DP.players.td_idx.map(i => D.td[i]).sort((x, y) => y.p_final - x.p_final);
  return dsec("d-props", "Player props and anytime TDs", "same model as the Player props and TD tabs") +
    (rows.length < 20 ? `<div class="note">Only ${rows.length} prop lines are posted for this game so far (books post most props 1-3 days before kickoff). Refresh later in the week.</div>` : "") +
    `<div class="note">Volume x efficiency model with opponent-vs-position and wind adjustments; ${Math.round(D.cfg.prop_trust * 100)}% of the gap to the market is believed, then blended ${Math.round(D.cfg.w.prop * 100)}% model / ${Math.round((1 - D.cfg.w.prop) * 100)}% market. Wind used: ${DP.players.wind_used} mph.</div>` +
    propsUI("dp", rows, false) +
    `<h3 class="dh3">Anytime touchdown scorer (sorted by our final probability)</h3><div class="tw"><table class="tbl"><thead><tr><th>#</th><th>Player</th><th>Best price</th><th>All books</th><th>Model</th><th>Market</th><th>Final</th><th>EV</th><th>Usage (per game)</th><th>Opponent vs position</th></tr></thead><tbody>${tds.map((t, i) => tdRowHtml(t, i + 1)).join("")}</tbody></table></div>`;
}

function renderDeep(gid) {
  gid = gid || D.deep_default;
  DP = D.deeps ? D.deeps[gid] : null;
  if (!DP) { $("#deep").innerHTML = `<p class="mut">No deep dive built.</p>`; return; }
  const g = D.games.find(x => x.id === DP.game_id), P = DP.projection, a = DP.away, h = DP.home;
  window.openDeep = id => { document.querySelector('#tabs button[data-t=deep]').click(); renderDeep(id); window.scrollTo(0, 0); };
  const nav = [["d-mkt", "Market"], ["d-dyn", "Game dynamics"], ["d-weather", "Weather"], ["d-stand", "What stands out"], ["d-team", "Team stats"], ["d-match", "Matchups"], ["d-pos", "Coverage"], ["d-players", "Players"], ["d-inj", "Injuries"], ["d-hist", "History"], ["d-props", "Props"]].map(([i, l]) => `<a class="chip" href="#${i}" onclick="document.getElementById('${i}').scrollIntoView({behavior:'smooth'});return false">${l}</a>`).join(" ");
  const dyn = DP.dynamics.map(x => `<li><span class="chip ${x.tag}">${x.tag === "g" ? "helps scoring" : x.tag === "r" ? "hurts scoring" : "context"}</span> ${x.text}</li>`).join("");
  const pp = DP.plays_proj;
  $("#deep").innerHTML = `<div class="card"><h2>${a} @ ${h} deep dive</h2><div class="small">${new Date(DP.kickoff).toLocaleString("en-US", {...ET, timeZone: "America/New_York", month: "short", day: "numeric"})} ET · ${DP.roof} · ${a} ${DP.rest.away}d rest, ${h} ${DP.rest.home}d rest</div>
    <div class="ctl" style="margin:8px 0"><select id="dsel">${D.games.map(x => `<option value="${x.id}" ${x.id === DP.game_id ? "selected" : ""}>${x.away} @ ${x.home} · ${new Date(x.kickoff).toLocaleString("en-US", {...ET, month: "short", day: "numeric"})}</option>`).join("")}</select></div><div class="ages" style="margin-top:8px">${nav}</div><label class="tg" style="display:inline-block;margin-top:8px"><input type="checkbox" id="show25"> Show 2025 numbers for reference (hidden by default: all team stats below are 2026)</label></div>
    ${dsec("d-mkt", "Market, our projection and EV")}${g ? gameHtml(g) : ""}
    <div class="grid2"><div><div class="small"><b>Margin distribution</b> (${h} margin; green = ${h} covers the market line)</div>${dBars(DP.dist.margin, -P.ref.spread, DP.dist.mu_margin_used, "margin", -24, 24)}</div>
    <div><div class="small"><b>Total distribution</b> (green = over ${P.ref.total})</div>${dBars(DP.dist.total, P.ref.total, DP.dist.mu_total_used, "total", 20, 70)}</div></div>
    <div class="small">Projected plays: ${a} ${pp[a].plays.toFixed(1)}, ${h} ${pp[h].plays.toFixed(1)} · pass EPA ${a} ${sgn(pp[a].epa_pass * 100)}, ${h} ${sgn(pp[h].epa_pass * 100)} (x100) · run EPA ${a} ${sgn(pp[a].epa_rush * 100)}, ${h} ${sgn(pp[h].epa_rush * 100)} · components: ${Object.entries(P.comp).filter(([k, v]) => Math.abs(v) >= 0.05 && k !== "ratings_total").map(([k, v]) => k + " " + sgn(v)).join(", ")}</div>
    ${dsec("d-dyn", "Game dynamics", "data-driven; green helps scoring, red hurts it")}<ul class="dyn">${dyn}</ul>
    ${dWeather()}
    ${dStandouts()}
    ${dsec("d-team", "Team statistics with league ranks", "all 2026 games so far, with league rank; chips green top 10, yellow middle, red bottom 10")}
    <div class="xs mut" style="margin:2px 0 6px">What the terms mean: <b>EPA</b> = expected points added per play (above 0 is good). <b>Success rate</b> = share of plays that gain enough yardage to keep the offence on schedule. <b>Explosive</b> = passes of 20+ yards, runs of 10+. <b>Accuracy: completion % above expected</b> (CPOE) = how often a quarterback completes passes compared with what the difficulty of those throws would predict; for a defence it is how much better than expected opponents complete passes against them (higher = worse). <b>Yards after catch</b> = yards gained after the reception.</div><div class="grid2">${dMetricTable2("off", "Offence")}${dMetricTable2("def", "Defence (what they allow)")}</div>
    ${dMatchups()}${dPos()}${dPlayers()}${dInjuries()}${dHistory()}${dProps()}`;
  $("#dsel").onchange = e => renderDeep(e.target.value);
  $("#show25").onchange = e => $("#deep").classList.toggle("show25", e.target.checked);
  bindPropsUI("dp");
}
