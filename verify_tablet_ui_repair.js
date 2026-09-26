'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('ui_app_shell_v272.js', 'utf8');
function definition(name) {
  const match = source.match(new RegExp(`  function ${name}\\([^]*?\\n  \\}`));
  assert.ok(match, name);
  return match[0];
}
const listeners = {};
const state = { signature: '', timer: 0 };
let syncs = 0;
let nextTimer = 0;
const timers = new Set();
const context = vm.createContext({
  window: { tcgGradeProbabilities: {}, addEventListener: (name, fn) => { listeners[name] = fn; } },
  document: { hidden: false },
  nodeText: () => '-',
  gradeCockpitState: state,
  syncGradeCockpit: () => { syncs++; },
  setInterval: () => { const id = ++nextTimer; timers.add(id); return id; },
  clearInterval: id => timers.delete(id),
});
vm.runInContext(['boundedNumber', 'probabilityText', 'formatCompanyGrade', 'stopGradeCockpitTimer', 'startGradeCockpitTimer'].map(definition).join('\n'), context);
for (const value of [undefined, null, '', ' ', false, true, [], {}, NaN, Infinity, -1, 101]) {
  context.window.tcgGradeProbabilities = {8: value, 9: value, 10: value};
  for (const grade of [8,9,10]) assert.equal(context.probabilityText(grade), '-');
}
for (const value of [undefined, null, '', ' ', false, true, [], {}, NaN, Infinity, 0, -1, 11]) {
  assert.equal(context.formatCompanyGrade('PSA', {PSA: value}), '대기');
}
context.window.tcgGradeProbabilities = {8: 0, 9: '42', 10: 100};
assert.equal(context.probabilityText(8), '0%');
assert.equal(context.probabilityText(9), '42%');
assert.equal(context.probabilityText(10), '100%');
assert.equal(context.formatCompanyGrade('PSA', {PSA: '9.5'}), '9.5 예상');
assert.equal(context.formatCompanyGrade('PSA', {PSA: 10}), '10 예상');
for (const name of ['pagehide', 'pageshow']) {
  const line = source.split('\n').find(line => line.includes(`window.addEventListener("${name}"`));
  assert.ok(line);
  assert.ok(!line.includes('once: true'));
  vm.runInContext(line, context);
}
context.startGradeCockpitTimer();
for (let i = 0; i < 3; i++) {
  listeners.pagehide();
  assert.equal(timers.size, 0);
  listeners.pageshow();
  listeners.pageshow();
  assert.equal(timers.size, 1);
}
assert.equal(syncs, 4);
console.log('PASS: missing/invalid grade and probability values; repeated page restore without timer leaks');

// Exercise the actual search function and check CSS against its boolean attributes.
function node(textContent, shortcuts = []) {
  const attrs = new Map();
  return {textContent, open: false, attrs,
    removeAttribute: name => attrs.delete(name),
    toggleAttribute: (name, enabled) => enabled ? attrs.set(name, '') : attrs.delete(name),
    querySelector: () => ({textContent}), querySelectorAll: () => shortcuts};
}
const gradeLink = node('카드 등급 OCR');
const tabletLink = node('태블릿 서버 상태');
const categories = [node('등급', [gradeLink]), node('태블릿', [tabletLink])];
const searchContext = vm.createContext({categories, clear: {}, status: {dataset: {}},
  normalize: value => String(value || '').normalize('NFKC').trim().toLowerCase()});
vm.runInContext(['searchableText','resetNode','filterFeatures'].map(definition).join('\n'), searchContext);
let result = searchContext.filterFeatures('ｏｃｒ');
assert.equal(result.visibleCategories, 1);
assert.equal(result.visibleShortcuts, 1);
assert.ok(categories[1].attrs.has('data-ui-filter-hidden'));
assert.ok(!categories[0].attrs.has('data-ui-filter-hidden'));
const css = fs.readFileSync('ui_app_shell_v272.css', 'utf8');
assert.match(css, /\.feature-category\[data-ui-filter-hidden\],\s*\.feature-shortcut\[data-ui-filter-hidden\]\{display:none!important\}/);
result = searchContext.filterFeatures('없는기능');
assert.equal(result.visibleCategories, 0);
assert.equal(searchContext.status.dataset.state, 'empty');
searchContext.filterFeatures('');
assert.ok(categories.every(item => !item.attrs.has('data-ui-filter-hidden')));
assert.ok(!gradeLink.attrs.has('data-ui-filter-hidden'));
assert.equal(searchContext.clear.disabled, true);
console.log('PASS: normalized search, no results, reset and CSS boolean-attribute contract');
