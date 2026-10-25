const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { runInNewContext } = require('node:vm');

const code = readFileSync(join(__dirname, '../app.js'), 'utf8');
const trend = runInNewContext(`${code.split('\nfunction draw()')[0]}\ntrend;`);

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
