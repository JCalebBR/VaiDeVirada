const $ = (id) => document.getElementById(id);
const state = { data: null, scale: 'linear', range: [0, 100], hover: null, dragging: false, live: false };
const colors = { '22': '#1659a7', '13': '#e12f34' };
const formatPct = (n, digits = 2) => `${new Intl.NumberFormat('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n)}%`;
const formatInt = (n) => new Intl.NumberFormat('pt-BR').format(n);
const dateFmt = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'America/Sao_Paulo' });
const toX = (n) => state.scale === 'log' ? Math.log1p(n) : n;
const fromX = (n) => state.scale === 'log' ? Math.expm1(n) : n;
const clamp = (n, min, max) => Math.max(min, Math.min(max, n));

function geometry() {
  const el = $('chart-wrap');
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
  const last = points.at(-1), end = Math.min(100, last.counted + Math.min(8, (last.counted - points[0].counted) / 2));
  if (end <= last.counted) return null;
  return { start: last.counted, y: last.candidates[number].percentage, end, projected: last.candidates[number].percentage + slope * (end - last.counted) };
}

function draw() {
  if (!state.data) return;
  const { firstRound, history } = state.data;
  const g = geometry();
  if (g.w <= 0) return;
  const visible = history.filter(p => p.counted >= state.range[0] && p.counted <= state.range[1]);
  const vals = [...Object.keys(colors).map(n => firstRound.candidates[n].percentage), ...visible.flatMap(p => Object.keys(colors).map(n => p.candidates[n].percentage))];
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
  for (const n of Object.keys(colors)) {
    const color = colors[n], reference = firstRound.candidates[n].percentage;
    svg += `<line x1="${g.left}" x2="${g.right}" y1="${yp(reference)}" y2="${yp(reference)}" stroke="${color}" stroke-width="2" stroke-dasharray="7 5" opacity=".8"/>`;
    const points = history.map(p => `${g.xp(p.counted)},${yp(p.candidates[n].percentage)}`).join(' ');
    if (history.length > 1) svg += `<polyline points="${points}" fill="none" stroke="${color}" stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round"/>`;
    const t = trend(history, n);
    if (t) svg += `<line x1="${g.xp(t.start)}" y1="${yp(t.y)}" x2="${g.xp(t.end)}" y2="${yp(t.projected)}" stroke="${color}" stroke-width="2" stroke-dasharray="2 6" stroke-linecap="round"/>`;
    const last = history.at(-1);
    svg += `<circle cx="${g.xp(last.counted)}" cy="${yp(last.candidates[n].percentage)}" r="5" fill="${color}" stroke="white" stroke-width="2"/>`;
  }
  if (state.hover !== null && history[state.hover]) {
    const p = history[state.hover], x = g.xp(p.counted);
    svg += `<line x1="${x}" x2="${x}" y1="${g.top}" y2="${g.bottom}" stroke="#1c2526" stroke-dasharray="3 4" opacity=".75"/>`;
    for (const n of Object.keys(colors)) svg += `<circle cx="${x}" cy="${yp(p.candidates[n].percentage)}" r="6" fill="${colors[n]}" stroke="white" stroke-width="2"/>`;
  }
  svg += '</g>';
  $('chart').setAttribute('viewBox', `0 0 ${g.w} ${g.h}`);
  $('chart').innerHTML = svg;
  renderTooltip(g);
}

function renderTooltip(g) {
  const tip = $('tooltip');
  const p = state.data?.history[state.hover];
  if (!p) { tip.hidden = true; return; }
  const x = g.xp(p.counted);
  if (x < g.left || x > g.right) { tip.hidden = true; return; }
  tip.innerHTML = `<strong>${dateFmt.format(new Date(p.at))} · ${formatPct(p.counted)} das urnas</strong><span class="blue-text">Flávio Bolsonaro: ${formatPct(p.candidates['22'].percentage)}</span><br><span class="red-text">Lula: ${formatPct(p.candidates['13'].percentage)}</span><br>${formatInt(p.validVotes)} votos válidos<br>${p.origin ? 'Captura arquivada do TSE (horário da captura)' : 'Totalização oficial do TSE'}`;
  tip.hidden = false;
  const w = $('chart-wrap').clientWidth;
  tip.style.left = `${clamp(x + 13, 0, w - tip.offsetWidth)}px`;
  tip.style.top = '25px';
}

function inspect(clientX) {
  const g = geometry(), x = clientX - $('chart-wrap').getBoundingClientRect().left;
  if (x < g.left || x > g.right) { state.hover = null; draw(); return; }
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
    await loadLive();
  } catch (error) {
    $('status-text').textContent = state.data ? 'FALHA AO ATUALIZAR · EXIBINDO ÚLTIMO REGISTRO' : 'DADOS INDISPONÍVEIS';
    $('updated').textContent = 'Não foi possível obter os dados. Tente recarregar a página.';
    console.error('Falha ao carregar apuração:', error);
  }
}

$('linear').addEventListener('click', () => setScale('linear'));
$('log').addEventListener('click', () => setScale('log'));
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
$('reset').addEventListener('click', () => { state.range = [0, 100]; state.hover = null; draw(); });
$('chart-wrap').addEventListener('wheel', e => { if (!state.data) return; e.preventDefault(); const g = geometry(); zoom(e.deltaY < 0 ? .8 : 1.25, clamp((e.clientX - $('chart-wrap').getBoundingClientRect().left - g.left) / (g.right - g.left), 0, 1)); }, { passive: false });
$('chart-wrap').addEventListener('pointermove', e => {
  if (!state.data) return;
  if (state.dragging) {
    const g = geometry(), dx = e.clientX - state.dragging.x;
    const width = toX(state.range[1]) - toX(state.range[0]);
    const start = clamp(state.dragging.start - dx / (g.right - g.left) * width, 0, toX(100) - width);
    state.range = [fromX(start), fromX(start + width)];
    state.hover = null; draw();
  } else inspect(e.clientX);
});
$('chart-wrap').addEventListener('pointerdown', e => { if (!state.data) return; state.dragging = { x: e.clientX, start: toX(state.range[0]) }; $('chart-wrap').setPointerCapture(e.pointerId); inspect(e.clientX); });
$('chart-wrap').addEventListener('pointerup', () => { state.dragging = false; });
$('chart-wrap').addEventListener('pointercancel', () => { state.dragging = false; });
$('chart-wrap').addEventListener('pointerleave', () => { if (!state.dragging) { state.hover = null; draw(); } });
window.addEventListener('resize', draw);
load();
setInterval(load, 90_000);
setInterval(loadLive, 30_000);
