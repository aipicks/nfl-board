/* ---------- Weather tab (all games) ---------- */
function wxSummary(d) {
  const W = d.weather, hrs = W.hours, k = W.kickoff_hour_index, win = hrs.slice(k, k + 4), K = hrs[k];
  const wind = Math.max(...win.map(x => x.windspeed_10m)), windAvg = win.reduce((s, x) => s + x.windspeed_10m, 0) / win.length, gust = Math.max(...win.map(x => x.windgusts_10m));
  const pp = Math.max(...win.map(x => x.precipitation_probability)), rain = win.reduce((s, x) => s + x.precipitation, 0), temp = K.temperature_2m, feels = K.apparent_temperature;
  const eff = Math.max(wind, gust * 0.6);
  const score = d.indoor ? 0 : Math.max(0, eff - 8) + pp / 100 * 8 + rain * 40 + Math.max(0, 35 - feels) * 0.4;
  const level = d.indoor ? ["Indoors", "g"] : score >= 10 ? ["High impact", "r"] : score >= 5 ? ["Some impact", "y"] : ["Little impact", "g"];
  return {K, win, wind, windAvg, gust, pp, rain, temp, feels, eff, score, level, k};
}
function wxChart(d, s) {
  const hrs = d.weather.hours, from = Math.max(0, s.k - 1), to = Math.min(hrs.length - 1, s.k + 5), H = hrs.slice(from, to + 1), n = H.length, w = 330, ht = 96, pad = 20;
  const mx = Math.max(30, ...H.map(x => x.windgusts_10m)) + 2, X = i => pad + i * (w - 2 * pad) / (n - 1), Y = v => ht - 16 - v / mx * (ht - 26);
  const line = (key, col, dash) => `<polyline fill="none" stroke="${col}" stroke-width="2" ${dash ? 'stroke-dasharray="5 3"' : ""} points="${H.map((x, i) => X(i) + "," + Y(x[key])).join(" ")}"/>`;
  const gs = X(s.k - from) - 8, ge = X(Math.min(n - 1, s.k - from + 3.3));
  return `<svg viewBox="0 0 ${w} ${ht}" width="100%" role="img" aria-label="Wind, gusts and rain by hour for ${d.away} at ${d.home}"><rect x="${gs}" y="2" width="${ge - gs}" height="${ht - 18}" fill="rgba(127,127,127,.18)"/>
    ${H.map((x, i) => `<rect x="${X(i) - 6}" y="${Y(Math.min(mx, x.precipitation * 90))}" width="12" height="${Math.max(0, ht - 16 - Y(Math.min(mx, x.precipitation * 90)))}" fill="#85B7EB" opacity=".75"/>`).join("")}
    ${line("windgusts_10m", "#E24B4A", true)}${line("windspeed_10m", "#378ADD")}
    ${H.map((x, i) => `<text x="${X(i)}" y="${ht - 3}" font-size="9" text-anchor="middle" fill="currentColor" opacity=".7">${x.et.replace(":00 ", "")}</text>`).join("")}</svg>`;
}
function wxBucket(rows, v) {
  return rows.find(r => { const m = r.bucket.match(/(\d+)(?:-(\d+))?/); const a = +m[1], b = m[2] ? +m[2] + 1 : 99; return v >= a && v < b; });
}
function wxCard(g) {
  const d = D.deeps[g.id]; if (!d) return "";
  const s = wxSummary(d), K = s.K, nw = d.nflweather, cmp = d.projection.comp.weather || 0;
  const chip = (txt, c) => `<span class="chip ${c}">${txt}</span>`;
  const c = (v, a, b) => v < a ? "g" : v < b ? "y" : "r";
  const tc = t => (t >= 40 && t <= 80) ? "g" : ((t >= 32 && t < 40) || (t > 80 && t <= 90)) ? "y" : "r";
  const mi = K.visibility / 1609.34;
  const bullets = [];
  if (d.indoor) bullets.push(["g", "Indoors (dome or closed roof): none of the weather below matters. The outside forecast is for reference only."]);
  else {
    if (s.wind >= 15 || s.gust >= 25) bullets.push(["r", `Wind ${s.windAvg.toFixed(0)} mph average, gusts to ${s.gust.toFixed(0)} from the ${K.wind_dir}: deep passes and long field goals get harder; the run game and short passes matter more.`]);
    else if (s.wind >= 10) bullets.push(["y", `Breezy: ${s.windAvg.toFixed(0)} mph, gusts to ${s.gust.toFixed(0)} from the ${K.wind_dir}. Small effect on deep throws and kicks.`]);
    else bullets.push(["g", `Calm: ${s.windAvg.toFixed(0)} mph wind, gusts to ${s.gust.toFixed(0)}. No wind effect on passing or kicking.`]);
    if (s.pp >= 50 || s.rain >= 0.1) bullets.push(["r", `Rain likely (${s.pp.toFixed(0)}% chance, about ${s.rain.toFixed(2)} in over the game): slippery ball, more drops and fumbles, passing efficiency usually dips.`]);
    else if (s.pp >= 25) bullets.push(["y", `${s.pp.toFixed(0)}% chance of rain: a shower could affect part of the game.`]);
    else bullets.push(["g", `Dry: ${s.pp.toFixed(0)}% chance of rain.`]);
    if (s.feels < 32) bullets.push(["r", `Freezing: feels like ${s.feels.toFixed(0)}F. Harder to grip, kick and throw; scoring usually dips a little.`]);
    else if (s.feels < 45) bullets.push(["y", `Cold: feels like ${s.feels.toFixed(0)}F. Minor effect.`]);
    else if (s.temp > 85) bullets.push(["y", `Hot: ${s.temp.toFixed(0)}F. Late-game fatigue and depth rotation matter more.`]);
    if (d.altitude_ft && d.altitude_ft[g.home] > 4000) bullets.push(["y", `Altitude ${d.altitude_ft[g.home].toLocaleString()} ft: thin air (${d.weather.density_vs_sea_level_pct}% vs sea level) means longer kicks and punts.`]);
    const wb = wxBucket(d.weather_history.wind, s.eff);
    if (wb) bullets.push(["y", `History: outdoor games with wind like this (${wb.bucket}) landed ${wb.avg_diff > 0 ? "+" : ""}${wb.avg_diff} points vs the closing total on average (${wb.n} games, over ${(wb.over_pct * 100).toFixed(0)}%).`]);
    bullets.push([cmp < -0.2 ? "r" : "y", `Our model's weather adjustment to this total: ${cmp > 0 ? "+" : ""}${cmp.toFixed(1)} points.`]);
    if (nw && (Math.abs((nw.wind_mph || 0) - s.windAvg) >= 5 || Math.abs((nw.precip_pct || 0) - s.pp) >= 30)) bullets.push(["y", `The two forecasts disagree: nflweather.com says ${Math.round(nw.wind_mph)} mph and ${Math.round(nw.precip_pct)}% rain, Open-Meteo says ${s.windAvg.toFixed(0)} mph and ${s.pp.toFixed(0)}%. Check again Sunday morning.`]);
  }
  return `<div class="game wxgame"><div class="gh"><h3>${g.away} @ ${g.home}</h3><span class="mut small">${new Date(g.kickoff).toLocaleString("en-US", {...ET, month: "short", day: "numeric"})} ET · ${chip(s.level[0], s.level[1])}</span></div>
    <div class="mgrid" style="grid-template-columns:repeat(auto-fit,minmax(96px,1fr))"><div class="m ${d.indoor ? "g" : tc(s.temp)}"><b>${Math.round(s.temp)}°F</b><span>feels ${Math.round(s.feels)}°F</span></div>
    <div class="m ${d.indoor ? "g" : c(s.eff, 10, 15)}"><b>${s.windAvg.toFixed(0)} mph</b><span>${K.wind_dir} · gusts ${s.gust.toFixed(0)}</span></div>
    <div class="m ${d.indoor ? "g" : c(s.pp, 25, 50)}"><b>${s.pp.toFixed(0)}%</b><span>rain chance · ${s.rain.toFixed(2)} in</span></div>
    <div class="m"><b>${K.relative_humidity_2m.toFixed(0)}%</b><span>humidity · ${K.cloudcover.toFixed(0)}% cloud</span></div>
    <div class="m ${mi >= 6 ? "g" : mi >= 3 ? "y" : "r"}"><b>${mi.toFixed(0)} mi</b><span>visibility · ${K.cond}</span></div></div>
    ${wxChart(d, s)}<div class="xs mut">Blue line wind, red dashed gusts (mph), blue bars rain; shaded = game window (kickoff to about 3 h 15 m).</div>
    <ul class="dyn">${bullets.map(([t, x]) => `<li><span class="chip ${t}">${t === "r" ? "matters" : t === "g" ? "no issue" : "watch"}</span> ${x}</li>`).join("")}</ul></div>`;
}
const WX = {sort: "impact", filter: ""};
function renderWeather() {
  let gs = D.games.filter(g => D.deeps[g.id]).map(g => ({g, s: wxSummary(D.deeps[g.id]), d: D.deeps[g.id]}));
  gs = gs.filter(x => !WX.filter || (WX.filter === "outdoor" && !x.d.indoor) || (WX.filter === "wind" && !x.d.indoor && x.s.eff >= 12) || (WX.filter === "rain" && !x.d.indoor && x.s.pp >= 30) || (WX.filter === "cold" && !x.d.indoor && x.s.feels < 40));
  gs.sort((a, b) => WX.sort === "impact" ? b.s.score - a.s.score : WX.sort === "time" ? a.g.kickoff.localeCompare(b.g.kickoff) : (a.g.away + a.g.home).localeCompare(b.g.away + b.g.home));
  $("#wxlist").innerHTML = gs.map(x => wxCard(x.g)).join("") || `<p class="mut">No games match.</p>`;
}
function initWeather() {
  const all = D.games.filter(g => D.deeps[g.id]).map(g => ({g, s: wxSummary(D.deeps[g.id]), d: D.deeps[g.id]}));
  const watch = all.filter(x => !x.d.indoor).sort((a, b) => b.s.score - a.s.score).slice(0, 4);
  $("#weatherroot").innerHTML = `<div class="card"><h2>Weather: every game</h2><p class="small">Hourly forecasts (Open-Meteo) at each stadium for the game window, with nflweather.com as a second opinion. Games are ordered by how much the weather could matter: wind and gusts first, then rain and cold. Domes and closed roofs are marked indoors. ${D.ages.weather ? `Weather last refreshed ${agoTxt(ago(D.ages.weather))}.` : ""}</p>
    <div class="small"><b>Games to watch:</b> ${watch.map(x => `${x.g.away} @ ${x.g.home} <span class="chip ${x.s.level[1]}">${x.s.level[0]}</span>`).join(" · ")}</div></div>
    <div class="ctl"><select id="wxsort"><option value="impact">Sort: most weather impact</option><option value="time">Sort: kickoff</option><option value="game">Sort: game</option></select>
    <span class="seg" id="wxfilter"><button data-f="" class="on">All</button><button data-f="outdoor">Outdoor</button><button data-f="wind">Windy</button><button data-f="rain">Rain</button><button data-f="cold">Cold</button></span></div><div id="wxlist"></div>`;
  $("#wxsort").onchange = e => { WX.sort = e.target.value; renderWeather(); };
  document.querySelectorAll("#wxfilter button").forEach(b => b.onclick = () => { document.querySelectorAll("#wxfilter button").forEach(x => x.classList.remove("on")); b.classList.add("on"); WX.filter = b.dataset.f; renderWeather(); });
  renderWeather();
}
