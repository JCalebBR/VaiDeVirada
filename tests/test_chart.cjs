const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { runInNewContext, createContext, runInContext } = require('node:vm');

const code = readFileSync(join(__dirname, '../app.js'), 'utf8');
const { trend, projectionAt, firstRoundAt, firstRoundDetailsAt } = runInNewContext(
  `${code.split('\nfunction draw()')[0]}\n({ trend, projectionAt, firstRoundAt, firstRoundDetailsAt });`,
);

test('recent trend reaches the 100% mark', () => {
  const history = [20, 40, 60].map((counted, index) => ({
    counted, validVotes: counted * 1000,
    candidates: { '22': { percentage: 48 + index }, '13': { percentage: 52 - index } },
  }));
  const projected = trend(history, '22');
  assert.equal(projected.start, 60);
  assert.equal(projected.end, 100);
  assert.equal(projected.projected, 52);
  assert.equal(trend(history, '13').projected, 48);
});

test('does not extrapolate from too few observations', () => {
  assert.equal(trend([{ counted: 30, candidates: { '22': { percentage: 50 } } }], '22'), null);
});

test('projection hover interpolates values along both trend lines', () => {
  const history = [20, 40, 60].map((counted, index) => ({
    counted, validVotes: counted * 1000,
    candidates: { '22': { percentage: 48 + index }, '13': { percentage: 52 - index } },
  }));
  assert.equal(projectionAt(history, 60), null);
  assert.equal(projectionAt(history, 101), null);
  assert.equal(projectionAt(history, 80).percentages['22'], 51);
  assert.equal(projectionAt(history, 80).percentages['13'], 49);
  assert.equal(projectionAt(history, 80).votes['22'], 40800);
  assert.equal(projectionAt(history, 80).votes['13'], 39200);
});

test('first-round hover interpolates the historical curve', () => {
  const history = [10, 30].map((counted, index) => ({
    counted,
    candidates: { '22': { percentage: 45 + index * 2, votes: 100 + index * 200 },
      '13': { percentage: 40 + index * 3, votes: 90 + index * 180 } },
  }));
  assert.equal(firstRoundAt(history, 0), null);
  assert.equal(firstRoundAt(history, 20)['22'], 46);
  assert.equal(firstRoundAt(history, 20)['13'], 41.5);
  assert.equal(firstRoundDetailsAt(history, 20)['22'].votes, 200);
  assert.equal(firstRoundDetailsAt(history, 20)['13'].votes, 180);
});

test('forecast, first-round mode and bulletin analysis controls', async () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      clientWidth: 800, clientHeight: 400, offsetWidth: 240, style: {},
      listeners: {}, classList: { toggle() {} },
      attrs: {}, children: [], firstChild: { textContent: '' },
      addEventListener(event, handler) { this.listeners[event] = handler; },
      setAttribute(name, value) { this.attrs[name] = value; },
      getAttribute(name) { return this.attrs[name] ?? null; },
      replaceChildren() { this.children = []; },
      append(child) { this.children.push(child); },
      getBoundingClientRect: () => ({ left: 0 }),
    });
    return elements.get(id);
  };
  const context = createContext({
    document: { getElementById: element, createElement: () => ({}) },
    window: { addEventListener() {} },
    setInterval() {},
    fetch: async () => { throw new Error('offline'); },
    URL, console: { error() {}, warn() {} },
  });
  runInContext(code, context);
  const history = [20, 40, 60].map((counted, index) => ({
    id: String(index), at: '2026-10-25T20:00:00-03:00', counted, validVotes: 1000,
    candidates: { '22': { percentage: 48 + index, votes: 500 + index * 100 },
      '13': { percentage: 52 - index, votes: 500 + index * 100 } },
  }));
  context.historyFixture = history;
  runInContext(`state.data = {
    history: historyFixture,
    firstRound: { candidates: { '22': { percentage: 47 }, '13': { percentage: 45 } } }
  }; state.firstHistory = [
    { counted: 10, candidates: { '22': { percentage: 48, votes: 100 }, '13': { percentage: 42, votes: 90 } } },
    { counted: 100, candidates: { '22': { percentage: 47, votes: 1000 }, '13': { percentage: 45, votes: 900 } } }
  ]; inspect(geometry().xp(80));`, context);
  assert.match(element('tooltip').innerHTML, /PROJEÇÃO · 80,00%/);
  assert.match(element('tooltip').innerHTML, /Flávio Bolsonaro: 51,00%/);
  assert.match(element('tooltip').innerHTML, /Lula: 49,00%/);
  assert.match(element('tooltip').innerHTML, /votos estimados/i);
  assert.match(element('tooltip').innerHTML, /1º TURNO/);
  assert.equal(element('tooltip').hidden, false);
  assert.equal(runInContext('state.hover', context), null);
  assert.equal(element('first-panel').hidden, false);
  assert.match(element('first-chart').innerHTML, /stroke="#1659a7"/);
  assert.doesNotMatch(element('chart').innerHTML, /stroke-dasharray="7 5"/);
  element('first-chart-wrap').listeners.pointermove({
    clientX: runInContext('geometry(document.getElementById("first-chart-wrap")).xp(80)', context),
  });
  assert.match(element('first-tooltip').innerHTML, /1º TURNO · 80,00%/);
  assert.match(element('first-tooltip').innerHTML, /800 votos/);
  runInContext('inspect(geometry().xp(40))', context);
  assert.match(element('tooltip').innerHTML, /Flávio Bolsonaro: 49,00% · 600 votos/);
  assert.match(element('tooltip').innerHTML, /Lula: 51,00% · 600 votos/);
  runInContext("setFirstMode('overlay')", context);
  assert.equal(element('first-panel').hidden, true);
  assert.match(element('chart').innerHTML, /stroke-dasharray="7 5"/);
  runInContext("setFirstMode('separate')", context);
  assert.equal(element('first-panel').hidden, false);
  element('extension-toggle').listeners.click();
  assert.equal(element('extension-panel').hidden, false);
  assert.equal(element('extension-toggle').getAttribute('aria-expanded'), 'true');
  element('extension-toggle').listeners.click();
  assert.equal(element('extension-panel').hidden, true);
  const analysis = JSON.parse(readFileSync(join(__dirname, '../data/extension-analysis.json'), 'utf8'));
  context.analysisFixture = analysis;
  runInContext('renderExtensionAnalysis(analysisFixture)', context);
  assert.equal(element('analysis-content').hidden, false);
  assert.match(element('analysis-coverage').textContent, /seções com arquivos próprios já reconciliadas/);
  assert.match(element('analysis-coverage').textContent, /agregadas a uma seção principal/);
  assert.match(element('analysis-verdict').textContent, /nas seções reconciliadas/);
  assert.match(element('analysis-comparison').innerHTML, /Cenário até 17h, mesmas seções/);
  assert.match(element('analysis-bounds').textContent, /não um intervalo de confiança/);
  assert.match(element('analysis-areas').innerHTML, /PB/);
  assert.match(element('analysis-histogram-note').textContent, /antes das 17h/);
  assert.doesNotMatch(element('analysis-histogram').innerHTML, /[–—]/);
  const fmt = new Intl.NumberFormat('pt-BR');
  assert.equal(element('analysis-window').textContent, fmt.format(analysis.national.post17to19));
  assert.equal(element('extension-late').textContent,
    `${fmt.format(analysis.national.post17to19 + analysis.national.after19)} de ${fmt.format(analysis.national.total)}`);
  assert.match(element('analysis-progress-text').textContent, /seções processadas/);
  assert.ok(Number(element('analysis-progress').getAttribute('aria-valuenow')) > 0);
  assert.match(element('analysis-progress-bar').style.width, /%$/);
  const answered = JSON.parse(JSON.stringify(analysis));
  answered.progress = { state: 'running', updatedAt: new Date().toISOString(), sectionsPerMinute: 1766,
    etaCompleteAt: new Date(Date.now() + 3_600_000).toISOString() };
  answered.confidence = { margin: 4_430_191, lateEstimate: 21_130, lateUpper: 348_442, sampleSections: 10_106,
    answered: true, marginFinal: true };
  answered.official.winner = '13';
  context.answeredFixture = answered;
  runInContext('renderExtensionAnalysis(answeredFixture)', context);
  assert.match(element('analysis-progress-text').textContent, /Término previsto/);
  assert.match(element('analysis-confidence-answer').textContent, /Lula venceria do mesmo jeito/);
  assert.equal(element('extension-verdict-label').textContent, 'RESPOSTA COM 99,9% DE CONFIANÇA');
  answered.confidence = { ...answered.confidence, answered: false, sectionsNeeded: 40_000,
    etaAnsweredAt: new Date(Date.now() + 1_800_000).toISOString() };
  answered.progress.state = 'blocked';
  runInContext('renderExtensionAnalysis(answeredFixture)', context);
  assert.match(element('analysis-confidence-answer').textContent, /Ainda não dá/);
  assert.match(element('analysis-confidence-detail').textContent, /Previsão para responder/);
  assert.match(element('analysis-progress-text').textContent, /bloqueio do TSE/);
  assert.equal(element('extension-verdict-label').textContent, 'RESPOSTA ATÉ AGORA');
  assert.throws(() => runInContext('renderExtensionAnalysis({schemaVersion: 1})', context),
    /inconsistentes/);
  const emptyAnalysis = JSON.parse(JSON.stringify(analysis));
  for (const field of ['total', 'pre17', 'post17to19', 'after19', 'sections', 'estimatedMargin']) {
    emptyAnalysis.national[field] = 0;
  }
  for (const field of ['votes', 'estimatedWindow', 'estimatedRemoved', 'estimatedUntil17']) {
    for (const candidate of Object.keys(emptyAnalysis.national[field])) emptyAnalysis.national[field][candidate] = 0;
  }
  Object.assign(emptyAnalysis.coverage, { ok: 0, failed: 0, excluded: 0, unreconciled: 0, aggregated: 0,
    pending: emptyAnalysis.coverage.enumeratedSections });
  context.emptyFixture = emptyAnalysis;
  runInContext('renderExtensionAnalysis(emptyFixture)', context);
  assert.match(element('analysis-status').textContent, /zeros não representam o Brasil/);
  await runInContext('loadExtensionAnalysis()', context);
  assert.equal(element('analysis-content').hidden, true);
  assert.match(element('analysis-status').textContent, /Não foi possível carregar/);
  context.fetch = async () => ({ ok: true, json: async () => analysis });
  await runInContext('loadExtensionAnalysis()', context);
  assert.equal(element('analysis-content').hidden, false);
  context.fetch = async () => ({
    ok: true,
    json: async () => ({
      areasPublished: 1, areasExpected: 28,
      datasetUrl: 'https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna',
      round2Bulletins: { AC: 'https://cdn.tse.jus.br/second.zip' },
    }),
  });
  await runInContext('loadExtensionCatalog()', context);
  assert.match(element('extension-bu-status').textContent, /1 de 28 áreas/);
  assert.equal(element('extension-files').children[0].textContent, 'AC ↗');
});
