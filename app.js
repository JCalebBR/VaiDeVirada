const $ = (id) => document.getElementById(id);
const state = { data: null, firstHistory: [], firstMode: 'separate', firstHoverCounted: null,
  scale: 'linear', range: [0, 100], hover: null, forecastCounted: null, dragging: false, live: false };
const colors = { '22': '#1659a7', '13': '#e12f34' };
const formatPct = (n, digits = 2) => `${new Intl.NumberFormat('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n)}%`;
const formatInt = (n) => new Intl.NumberFormat('pt-BR').format(n);
const dateFmt = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'America/Sao_Paulo' });
const toX = (n) => state.scale === 'log' ? Math.log1p(n) : n;
const fromX = (n) => state.scale === 'log' ? Math.expm1(n) : n;
const clamp = (n, min, max) => Math.max(min, Math.min(max, n));

function geometry(el = $('chart-wrap')) {
  const w = el.clientWidth, h = el.clientHeight;
  const left = w < 500 ? 49 : 58, right = w - 14, top = 14, bottom = h - 36;
  const lo = toX(state.range[0]), hi = toX(state.range[1]);
  const xp = (x) => left + (toX(x) - lo) / (hi - lo) * (right - left);
  const unpx = (x) => fromX(lo + (x - left) / (right - left) * (hi - lo));
  return { w, h, left, right, top, bottom, xp, unpx };
}

function trend(history, number) {
  const points = history.slice(-8);
  if (points.length < 3 || points.at(-1).counted - points[0].counted < .25) return null;
  const xs = points.map(p => p.counted), ys = points.map(p => p.candidates[number].percentage);
  const xm = xs.reduce((a, b) => a + b, 0) / xs.length;
  const ym = ys.reduce((a, b) => a + b, 0) / ys.length;
  const den = xs.reduce((a, x) => a + (x - xm) ** 2, 0);
  if (den < .0001) return null;
  const slope = xs.reduce((a, x, i) => a + (x - xm) * (ys[i] - ym), 0) / den;
  const last = points.at(-1), end = 100;
  if (end <= last.counted) return null;
  return { start: last.counted, y: last.candidates[number].percentage, end,
    projected: clamp(last.candidates[number].percentage + slope * (end - last.counted), 0, 100) };
}

function projectionAt(history, counted) {
  if (!history.length || counted <= history.at(-1).counted || counted > 100) return null;
  const last = history.at(-1);
  const result = { counted, percentages: {}, votes: {},
    estimatedValidVotes: Math.round(last.validVotes * counted / last.counted) };
  for (const n of Object.keys(colors)) {
    const t = trend(history, n);
    if (!t) return null;
    result.percentages[n] = t.y + (t.projected - t.y) * (counted - t.start) / (t.end - t.start);
    result.votes[n] = Math.round(result.estimatedValidVotes * result.percentages[n] / 100);
  }
  return result;
}

function firstRoundDetailsAt(history, counted) {
  if (!history.length || counted < history[0].counted || counted > history.at(-1).counted) return null;
  const upper = history.findIndex(p => p.counted >= counted);
  const end = history[upper], start = history[Math.max(0, upper - 1)];
  const ratio = end.counted === start.counted ? 0 : (counted - start.counted) / (end.counted - start.counted);
  return Object.fromEntries(Object.keys(colors).map(n => [n, {
    percentage: start.candidates[n].percentage + (end.candidates[n].percentage - start.candidates[n].percentage) * ratio,
    votes: Math.round(start.candidates[n].votes + (end.candidates[n].votes - start.candidates[n].votes) * ratio),
  }]));
}

function firstRoundAt(history, counted) {
  const details = firstRoundDetailsAt(history, counted);
  return details && Object.fromEntries(Object.keys(colors).map(n => [n, details[n].percentage]));
}

function draw() {
  if (!state.data) return;
  const { firstRound, history } = state.data;
  const g = geometry();
  if (g.w <= 0) return;
  const visible = history.filter(p => p.counted >= state.range[0] && p.counted <= state.range[1]);
  const firstVisible = state.firstHistory.filter(p => p.counted >= state.range[0] && p.counted <= state.range[1]);
  const vals = visible.flatMap(p => Object.keys(colors).map(n => p.candidates[n].percentage));
  if (state.firstMode === 'overlay') {
    vals.push(...Object.keys(colors).map(n => firstRound.candidates[n].percentage));
    vals.push(...firstVisible.flatMap(p => Object.keys(colors).map(n => p.candidates[n].percentage)));
  }
  for (const n of Object.keys(colors)) {
    const t = trend(history, n);
    if (t && state.range[1] > t.start) {
      const edge = Math.min(state.range[1], t.end);
      vals.push(t.y + (t.projected - t.y) * (edge - t.start) / (t.end - t.start));
    }
  }
  if (!vals.length) vals.push(...Object.keys(colors).map(n => history.at(-1).candidates[n].percentage));
  const yMin = Math.max(0, Math.floor((Math.min(...vals) - 2) / 2) * 2);
  const yMax = Math.min(100, Math.ceil((Math.max(...vals) + 2) / 2) * 2);
  const yp = y => g.bottom - (y - yMin) / (yMax - yMin || 1) * (g.bottom - g.top);
  let svg = `<defs><clipPath id="plot-clip"><rect x="${g.left}" y="${g.top}" width="${g.right-g.left}" height="${g.bottom-g.top}"/></clipPath></defs>`;
  for (let i = 0; i <= 4; i++) {
    const value = yMin + (yMax - yMin) * i / 4, y = yp(value);
    svg += `<line x1="${g.left}" x2="${g.right}" y1="${y}" y2="${y}" stroke="#d8dcd8" stroke-dasharray="4 5"/><text x="${g.left-8}" y="${y+4}" text-anchor="end" fill="#586461" font-size="11" font-family="DM Sans,sans-serif">${formatPct(value, 0)}</text>`;
  }
  const ticks = state.scale === 'log' ? [0,.1,.5,1,2,5,10,25,50,100] : [0,10,20,30,40,50,60,70,80,90,100];
  for (const value of ticks.filter(t => t >= state.range[0] && t <= state.range[1])) {
    const x = g.xp(value);
    if (x < g.left || x > g.right) continue;
    if (state.scale === 'linear' && g.right - g.left < 450 && value % 20) continue;
    svg += `<line x1="${x}" x2="${x}" y1="${g.bottom}" y2="${g.bottom+5}" stroke="#586461"/><text x="${x}" y="${g.bottom+20}" text-anchor="middle" fill="#586461" font-size="11" font-family="DM Sans,sans-serif">${String(value).replace('.', ',')}%</text>`;
  }
  svg += `<line x1="${g.left}" x2="${g.right}" y1="${g.bottom}" y2="${g.bottom}" stroke="#1c2526"/>`;
  svg += '<g clip-path="url(#plot-clip)">';
  if (state.firstMode === 'overlay') {
    for (const n of Object.keys(colors)) {
      const points = state.firstHistory.map(p => `${g.xp(p.counted)},${yp(p.candidates[n].percentage)}`).join(' ');
      if (points) svg += `<polyline points="${points}" fill="none" stroke="${colors[n]}" stroke-width="2" stroke-dasharray="7 5" opacity=".8" stroke-linejoin="round"/>`;
    }
  }
  for (const n of Object.keys(colors)) {
    const color = colors[n];
    const points = history.map(p => `${g.xp(p.counted)},${yp(p.candidates[n].percentage)}`).join(' ');
    if (history.length > 1) svg += `<polyline points="${points}" fill="none" stroke="${color}" stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round"/>`;
    const t = trend(history, n);
    if (t) svg += `<line x1="${g.xp(t.start)}" y1="${yp(t.y)}" x2="${g.xp(t.end)}" y2="${yp(t.projected)}" stroke="${color}" stroke-width="2" stroke-dasharray="2 6" stroke-linecap="round"/>`;
    const last = history.at(-1);
    svg += `<circle cx="${g.xp(last.counted)}" cy="${yp(last.candidates[n].percentage)}" r="5" fill="${color}" stroke="white" stroke-width="2"/>`;
  }
  const forecast = state.forecastCounted === null ? null : projectionAt(history, state.forecastCounted);
  let inspectedCounted = null;
  if (forecast && forecast.counted >= state.range[0] && forecast.counted <= state.range[1]) {
    const x = g.xp(forecast.counted);
    inspectedCounted = forecast.counted;
    svg += `<line x1="${x}" x2="${x}" y1="${g.top}" y2="${g.bottom}" stroke="#1c2526" stroke-dasharray="3 4" opacity=".75"/>`;
    for (const n of Object.keys(colors)) svg += `<circle cx="${x}" cy="${yp(forecast.percentages[n])}" r="6" fill="${colors[n]}" stroke="white" stroke-width="2"/>`;
  } else if (state.hover !== null && history[state.hover]) {
    const p = history[state.hover], x = g.xp(p.counted);
    inspectedCounted = p.counted;
    svg += `<line x1="${x}" x2="${x}" y1="${g.top}" y2="${g.bottom}" stroke="#1c2526" stroke-dasharray="3 4" opacity=".75"/>`;
    for (const n of Object.keys(colors)) svg += `<circle cx="${x}" cy="${yp(p.candidates[n].percentage)}" r="6" fill="${colors[n]}" stroke="white" stroke-width="2"/>`;
  }
  const comparison = state.firstMode === 'overlay' && inspectedCounted !== null
    ? firstRoundAt(state.firstHistory, inspectedCounted) : null;
  if (comparison) for (const n of Object.keys(colors)) {
    svg += `<circle cx="${g.xp(inspectedCounted)}" cy="${yp(comparison[n])}" r="5" fill="white" stroke="${colors[n]}" stroke-width="2"/>`;
  }
  svg += '</g>';
  $('chart').setAttribute('viewBox', `0 0 ${g.w} ${g.h}`);
  $('chart').innerHTML = svg;
  renderTooltip(g);
  drawFirstRound();
}

function drawFirstRound() {
  const panel = $('first-panel');
  panel.hidden = state.firstMode !== 'separate';
  if (panel.hidden || !state.firstHistory.length) return;
  const g = geometry($('first-chart-wrap'));
  if (g.w <= 0) return;
  const visible = state.firstHistory.filter(p => p.counted >= state.range[0] && p.counted <= state.range[1]);
  const values = (visible.length ? visible : state.firstHistory).flatMap(p =>
    Object.keys(colors).map(n => p.candidates[n].percentage));
  const low = Math.max(0, Math.floor(Math.min(...values) - 1));
  const high = Math.min(100, Math.ceil(Math.max(...values) + 1));
  const yp = value => g.bottom - (value - low) / (high - low || 1) * (g.bottom - g.top);
  let svg = `<defs><clipPath id="first-clip"><rect x="${g.left}" y="${g.top}" width="${g.right - g.left}" height="${g.bottom - g.top}"/></clipPath></defs>`;
  for (let i = 0; i <= 2; i++) {
    const value = low + (high - low) * i / 2, y = yp(value);
    svg += `<line x1="${g.left}" x2="${g.right}" y1="${y}" y2="${y}" stroke="#d8dcd8" stroke-dasharray="3 6"/><text x="${g.left - 8}" y="${y + 4}" text-anchor="end" fill="#586461" font-size="10" font-family="DM Sans,sans-serif">${formatPct(value, 0)}</text>`;
  }
  svg += `<g clip-path="url(#first-clip)">`;
  for (const n of Object.keys(colors)) {
    const points = state.firstHistory.map(p => `${g.xp(p.counted)},${yp(p.candidates[n].percentage)}`).join(' ');
    svg += `<polyline points="${points}" fill="none" stroke="${colors[n]}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>`;
  }
  const counted = state.firstHoverCounted;
  const comparison = counted === null ? null : firstRoundAt(state.firstHistory, counted);
  if (comparison && counted >= state.range[0] && counted <= state.range[1]) {
    const x = g.xp(counted);
    svg += `<line x1="${x}" x2="${x}" y1="${g.top}" y2="${g.bottom}" stroke="#1c2526" stroke-dasharray="3 4" opacity=".7"/>`;
    for (const n of Object.keys(colors)) svg += `<circle cx="${x}" cy="${yp(comparison[n])}" r="5" fill="${colors[n]}" stroke="white" stroke-width="2"/>`;
  }
  svg += '</g>';
  $('first-chart').setAttribute('viewBox', `0 0 ${g.w} ${g.h}`);
  $('first-chart').innerHTML = svg;
  const tip = $('first-tooltip');
  if (!comparison || counted < state.range[0] || counted > state.range[1]) { tip.hidden = true; return; }
  const details = firstRoundDetailsAt(state.firstHistory, counted);
  tip.innerHTML = `<strong>1º TURNO · ${formatPct(counted)} das urnas</strong><span class="blue-text">Flávio Bolsonaro: ${formatPct(details['22'].percentage)} · ${formatInt(details['22'].votes)} votos</span><br><span class="red-text">Lula: ${formatPct(details['13'].percentage)} · ${formatInt(details['13'].votes)} votos</span><br>Entre capturas, valores interpolados`;
  tip.hidden = false;
  tip.style.left = `${clamp(g.xp(counted) + 13, 0, g.w - tip.offsetWidth)}px`;
  tip.style.top = '8px';
}

function renderTooltip(g) {
  const tip = $('tooltip');
  const firstComparison = counted => {
    const values = firstRoundDetailsAt(state.firstHistory, counted);
    return values ? `<br><span class="tooltip-divider">1º TURNO · MESMO % DE URNAS (APROX.)</span><br><span class="blue-text">Flávio: ${formatPct(values['22'].percentage)} · ${formatInt(values['22'].votes)} votos</span><br><span class="red-text">Lula: ${formatPct(values['13'].percentage)} · ${formatInt(values['13'].votes)} votos</span>` : '';
  };
  const forecast = state.forecastCounted === null ? null : projectionAt(state.data.history, state.forecastCounted);
  if (forecast && forecast.counted >= state.range[0] && forecast.counted <= state.range[1]) {
    const x = g.xp(forecast.counted);
    tip.innerHTML = `<strong>PROJEÇÃO · ${formatPct(forecast.counted)} das urnas</strong><span class="blue-text">Flávio Bolsonaro: ${formatPct(forecast.percentages['22'])} · ~${formatInt(forecast.votes['22'])} votos</span><br><span class="red-text">Lula: ${formatPct(forecast.percentages['13'])} · ~${formatInt(forecast.votes['13'])} votos</span><br>Votos estimados: ritmo de votos válidos por urna atual; não são resultado oficial${firstComparison(forecast.counted)}`;
    tip.hidden = false;
    tip.style.left = `${clamp(x + 13, 0, g.w - tip.offsetWidth)}px`;
    tip.style.top = '25px';
    return;
  }
  const p = state.data?.history[state.hover];
  if (!p) { tip.hidden = true; return; }
  const x = g.xp(p.counted);
  if (x < g.left || x > g.right) { tip.hidden = true; return; }
  tip.innerHTML = `<strong>${dateFmt.format(new Date(p.at))} · ${formatPct(p.counted)} das urnas</strong><span class="blue-text">Flávio Bolsonaro: ${formatPct(p.candidates['22'].percentage)} · ${formatInt(p.candidates['22'].votes)} votos</span><br><span class="red-text">Lula: ${formatPct(p.candidates['13'].percentage)} · ${formatInt(p.candidates['13'].votes)} votos</span><br>${formatInt(p.validVotes)} votos válidos<br>${p.origin ? 'Captura arquivada do TSE (horário da captura)' : 'Totalização oficial do TSE'}${firstComparison(p.counted)}`;
  tip.hidden = false;
  const w = $('chart-wrap').clientWidth;
  tip.style.left = `${clamp(x + 13, 0, w - tip.offsetWidth)}px`;
  tip.style.top = '25px';
}

function inspect(clientX) {
  const g = geometry(), x = clientX - $('chart-wrap').getBoundingClientRect().left;
  if (x < g.left || x > g.right) { state.hover = null; state.forecastCounted = null; draw(); return; }
  const forecast = projectionAt(state.data.history, clamp(g.unpx(x), 0, 100));
  if (forecast) {
    state.forecastCounted = forecast.counted;
    state.hover = null;
    draw();
    return;
  }
  state.forecastCounted = null;
  const visible = state.data.history.map((p, index) => ({ index, distance: Math.abs(g.xp(p.counted) - x) })).filter(p => g.xp(state.data.history[p.index].counted) >= g.left && g.xp(state.data.history[p.index].counted) <= g.right);
  state.hover = visible.length ? visible.reduce((a, b) => a.distance < b.distance ? a : b).index : null;
  draw();
}

function zoom(factor, anchor = .5) {
  const lo = toX(state.range[0]), hi = toX(state.range[1]);
  const middle = lo + (hi - lo) * anchor, width = clamp((hi - lo) * factor, .025, toX(100));
  let start = middle - width * anchor;
  start = clamp(start, 0, toX(100) - width);
  state.range = [fromX(start), fromX(start + width)];
  draw();
}

function setFirstMode(mode) {
  state.firstMode = mode;
  state.firstHoverCounted = null;
  for (const kind of ['separate', 'overlay']) {
    $(`first-${kind}`).classList.toggle('active', kind === mode);
    $(`first-${kind}`).setAttribute('aria-pressed', String(kind === mode));
  }
  $('first-mode-label').textContent = mode === 'separate'
    ? '1º TURNO / RESULTADO FINAL' : 'CURVAS PONTILHADAS / 1º TURNO (FINAL)';
  $('first-legend').hidden = mode !== 'overlay';
  $('first-tooltip').hidden = true;
  $('first-panel').hidden = mode !== 'separate';
  draw();
}

function updateUI(data) {
  const last = data.history.at(-1);
  if (!last) throw new Error('Nenhum registro de apuração disponível');
  for (const n of Object.keys(colors)) {
    $(`score-${n}`).textContent = formatPct(last.candidates[n].percentage);
    $(`votes-${n}`).textContent = `${formatInt(last.candidates[n].votes)} votos · 1º turno: ${formatPct(data.firstRound.candidates[n].percentage)}`;
    $(`reference-${n}`).textContent = `${n === '22' ? 'Flávio Bolsonaro' : 'Lula'} ${formatPct(data.firstRound.candidates[n].percentage)}`;
  }
  $('counted').textContent = formatPct(last.counted);
  const age = Date.now() - new Date(last.at).getTime();
  $('status-text').textContent = last.counted >= 99.99 ? 'APURAÇÃO CONCLUÍDA' : age > 20 * 60 * 1000 ? 'DADOS DESATUALIZADOS' : state.live ? 'AO VIVO · CONSULTA DIRETA AO TSE' : 'APURAÇÃO EM ANDAMENTO';
  $('updated').textContent = `TSE: ${dateFmt.format(new Date(last.at))} (Brasília) · ${data.history.length} registros`;
  $('source-link').href = data.round2Url;
  draw();
}

function appendObserved(data, snapshot) {
  const history = data.history;
  const last = history.at(-1);
  if (snapshot.counted < last.counted || snapshot.at < last.at) return;
  if (history.some(p => p.id === snapshot.id || (
    p.candidates['13'].votes === snapshot.candidates['13'].votes &&
    p.candidates['22'].votes === snapshot.candidates['22'].votes))) return;
  if (snapshot.counted === last.counted) history.pop();
  history.push(snapshot);
}

function parseOfficial(payload) {
  if (payload.ele !== '6258' || payload.t !== '2' || payload.cdabr !== 'br') throw new Error('Feed inesperado do TSE');
  const cargo = payload.carg.find(c => c.cd === '1');
  const rows = {};
  for (const group of cargo.agr) for (const party of group.par || []) for (const cand of party.cand || []) {
    if (cand.n === '13' || cand.n === '22') {
      rows[cand.n] = { name: cand.nmu, votes: Number(cand.vap), percentage: Number(cand.pvapn.replace(',', '.')) };
    }
  }
  if (!rows['13'] || !rows['22'] || !Number.isFinite(rows['13'].percentage) || !Number.isFinite(rows['22'].percentage)) throw new Error('Candidatos ausentes no feed');
  const [day, month, year] = payload.dt.split('/');
  const at = `${year}-${month}-${day}T${payload.ht}-03:00`;
  return { id: String(payload.idg), at, counted: Number(payload.s.pstn.replace(',', '.')),
    validVotes: Number(payload.v.vvc), candidates: rows };
}

async function loadLive() {
  if (!state.data) return;
  try {
    const response = await fetch(`${state.data.round2Url}?v=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const snapshot = parseOfficial(await response.json());
    appendObserved(state.data, snapshot);
    state.live = true;
    updateUI(state.data);
  } catch (error) {
    console.warn('Consulta direta indisponível; usando histórico publicado:', error);
    state.live = false;
    updateUI(state.data);
  }
}

async function load() {
  try {
    const response = await fetch(`./data/results.json?v=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!data.history?.length || !data.firstRound?.candidates) throw new Error('Dados incompletos');
    if (state.data) {
      for (const point of state.data.history) {
        if (!data.history.some(p => p.id === point.id)) appendObserved(data, point);
      }
    }
    state.data = data;
    updateUI(data);
    if (!state.firstHistory.length) await loadFirstRound();
    await loadLive();
  } catch (error) {
    $('status-text').textContent = state.data ? 'FALHA AO ATUALIZAR · EXIBINDO ÚLTIMO REGISTRO' : 'DADOS INDISPONÍVEIS';
    $('updated').textContent = 'Não foi possível obter os dados. Tente recarregar a página.';
    console.error('Falha ao carregar apuração:', error);
  }
}

async function loadFirstRound() {
  try {
    const response = await fetch('./data/first-round-history.json');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const archive = await response.json();
    if (!Array.isArray(archive.history) || archive.history.at(-1)?.counted !== 100) throw new Error('Série incompleta');
    state.firstHistory = archive.history;
    $('first-status').textContent = '';
    draw();
  } catch (error) {
    $('first-status').textContent = 'Série do 1º turno indisponível no momento; valores finais permanecem abaixo do gráfico.';
    console.warn('Falha ao carregar série do 1º turno:', error);
  }
}

$('linear').addEventListener('click', () => setScale('linear'));
$('log').addEventListener('click', () => setScale('log'));
$('first-separate').addEventListener('click', () => setFirstMode('separate'));
$('first-overlay').addEventListener('click', () => setFirstMode('overlay'));
function setScale(scale) {
  state.scale = scale;
  for (const kind of ['linear', 'log']) {
    $(kind).classList.toggle('active', kind === scale);
    $(kind).setAttribute('aria-pressed', String(kind === scale));
  }
  draw();
}
$('zoom-in').addEventListener('click', () => zoom(.6));
$('zoom-out').addEventListener('click', () => zoom(1 / .6));
$('reset').addEventListener('click', () => { state.range = [0, 100]; state.hover = null; state.forecastCounted = null; draw(); });
$('chart-wrap').addEventListener('wheel', e => { if (!state.data) return; e.preventDefault(); const g = geometry(); zoom(e.deltaY < 0 ? .8 : 1.25, clamp((e.clientX - $('chart-wrap').getBoundingClientRect().left - g.left) / (g.right - g.left), 0, 1)); }, { passive: false });
$('chart-wrap').addEventListener('pointermove', e => {
  if (!state.data) return;
  if (state.dragging) {
    const g = geometry(), dx = e.clientX - state.dragging.x;
    const width = toX(state.range[1]) - toX(state.range[0]);
    const start = clamp(state.dragging.start - dx / (g.right - g.left) * width, 0, toX(100) - width);
    state.range = [fromX(start), fromX(start + width)];
    state.hover = null; state.forecastCounted = null; draw();
  } else inspect(e.clientX);
});
$('chart-wrap').addEventListener('pointerdown', e => { if (!state.data) return; state.dragging = { x: e.clientX, start: toX(state.range[0]) }; $('chart-wrap').setPointerCapture(e.pointerId); inspect(e.clientX); });
$('chart-wrap').addEventListener('pointerup', () => { state.dragging = false; });
$('chart-wrap').addEventListener('pointercancel', () => { state.dragging = false; });
$('chart-wrap').addEventListener('pointerleave', e => {
  if (!state.dragging && e.pointerType !== 'touch') {
    state.hover = null;
    state.forecastCounted = null;
    draw();
  }
});
$('first-chart-wrap').addEventListener('pointermove', e => {
  if (!state.firstHistory.length) return;
  const g = geometry($('first-chart-wrap'));
  const x = e.clientX - $('first-chart-wrap').getBoundingClientRect().left;
  state.firstHoverCounted = x >= g.left && x <= g.right ? clamp(g.unpx(x), 0, 100) : null;
  drawFirstRound();
});
$('first-chart-wrap').addEventListener('pointerdown', e => {
  if (!state.firstHistory.length) return;
  const g = geometry($('first-chart-wrap'));
  const x = e.clientX - $('first-chart-wrap').getBoundingClientRect().left;
  state.firstHoverCounted = x >= g.left && x <= g.right ? clamp(g.unpx(x), 0, 100) : null;
  drawFirstRound();
});
$('first-chart-wrap').addEventListener('pointerleave', e => {
  if (e.pointerType !== 'touch') { state.firstHoverCounted = null; drawFirstRound(); }
});
$('first-chart-wrap').addEventListener('wheel', e => {
  if (!state.data) return;
  e.preventDefault();
  const g = geometry($('first-chart-wrap'));
  const anchor = clamp((e.clientX - $('first-chart-wrap').getBoundingClientRect().left - g.left) / (g.right - g.left), 0, 1);
  zoom(e.deltaY < 0 ? .8 : 1.25, anchor);
}, { passive: false });
window.addEventListener('resize', draw);
load();
setInterval(load, 90_000);
setInterval(loadLive, 30_000);
