const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { runInNewContext, createContext, runInContext } = require('node:vm');

const code = readFileSync(join(__dirname, '../app.js'), 'utf8');
const { trend, projectionAt, firstRoundAt } = runInNewContext(
  `${code.split('\nfunction draw()')[0]}\n({ trend, projectionAt, firstRoundAt });`,
);

test('recent trend reaches the 100% mark', () => {
  const history = [20, 40, 60].map((counted, index) => ({
    counted,
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
    counted,
    candidates: { '22': { percentage: 48 + index }, '13': { percentage: 52 - index } },
  }));
  assert.equal(projectionAt(history, 60), null);
  assert.equal(projectionAt(history, 101), null);
  assert.equal(projectionAt(history, 80).percentages['22'], 51);
  assert.equal(projectionAt(history, 80).percentages['13'], 49);
});

test('first-round hover interpolates the historical curve', () => {
  const history = [10, 30].map((counted, index) => ({
    counted,
    candidates: { '22': { percentage: 45 + index * 2 }, '13': { percentage: 40 + index * 3 } },
  }));
  assert.equal(firstRoundAt(history, 0), null);
  assert.equal(firstRoundAt(history, 20)['22'], 46);
  assert.equal(firstRoundAt(history, 20)['13'], 41.5);
});

test('pointer in projected region shows forecast instead of snapping to last actual point', () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      clientWidth: 800, clientHeight: 400, offsetWidth: 240, style: {},
      addEventListener() {}, setAttribute() {}, getBoundingClientRect: () => ({ left: 0 }),
    });
    return elements.get(id);
  };
  const context = createContext({
    document: { getElementById: element },
    window: { addEventListener() {} },
    setInterval() {},
    fetch: async () => { throw new Error('offline'); },
    console: { error() {} },
  });
  runInContext(code, context);
  const history = [20, 40, 60].map((counted, index) => ({
    id: String(index), at: '2026-10-25T20:00:00-03:00', counted, validVotes: 1000,
    candidates: { '22': { percentage: 48 + index }, '13': { percentage: 52 - index } },
  }));
  context.historyFixture = history;
  runInContext(`state.data = {
    history: historyFixture,
    firstRound: { candidates: { '22': { percentage: 47 }, '13': { percentage: 45 } } }
  }; state.firstHistory = [
    { counted: 10, candidates: { '22': { percentage: 48 }, '13': { percentage: 42 } } },
    { counted: 100, candidates: { '22': { percentage: 47 }, '13': { percentage: 45 } } }
  ]; inspect(geometry().xp(80));`, context);
  assert.match(element('tooltip').innerHTML, /PROJEÇÃO · 80,00%/);
  assert.match(element('tooltip').innerHTML, /Flávio Bolsonaro: 51,00%/);
  assert.match(element('tooltip').innerHTML, /Lula: 49,00%/);
  assert.match(element('tooltip').innerHTML, /1º TURNO/);
  assert.equal(element('tooltip').hidden, false);
  assert.equal(runInContext('state.hover', context), null);
});
