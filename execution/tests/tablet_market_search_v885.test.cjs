'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {search} = require('../tablet_market_search_v885.js');
const rows = [
  {region:'KR', game:'ONE PIECE', kind:'BOX', name:'계승되는 의지'},
  {region:'JP', game:'ONE PIECE', kind:'BOX', name:'受け継がれる意志'},
  {region:'CN-S', game:'Pokémon', kind:'BOX', name:'英雄'},
  {region:'CN-T', game:'Pokémon', kind:'BOX', name:'英雄'},
  {region:'US', game:'Pokémon', kind:'HIT', name:'Charizard'},
];
const watch = {items: [
  {region:'KR',game:'ONE PIECE',asset:'BOX',name:'계승되는 의지',native:'[OPK-13] 계승되는 의지',product_code:'OPK-13'},
  {region:'JP',game:'ONE PIECE',asset:'BOX',name:'受け継がれる意志',native:'受け継がれる意志',product_code:'OP-13'},
  {region:'CN-S',game:'Pokémon',asset:'BOX',name:'英雄',product_code:'CN001'},
  {region:'CN-T',game:'Pokémon',asset:'BOX',name:'英雄',product_code:'TW001'},
]};
test('Korean, native Japanese, and exact product-code search', () => {
  assert.deepEqual(search(rows,watch,{query:'OPK-13'}), [rows[0]]);
  assert.deepEqual(search(rows,watch,{query:'受け継がれる意志'}), [rows[1]]);
  assert.deepEqual(search(rows,watch,{query:'일본판'}), [rows[1]]);
  assert.deepEqual(search(rows,watch,{query:'한국판'}), [rows[0]]);
});
test('China unified filter without merging separate identities', () => {
  assert.deepEqual(search(rows,watch,{region:'CN'}), [rows[2],rows[3]]);
  assert.deepEqual(search(rows,watch,{region:'CN-S'}), [rows[2]]);
  assert.deepEqual(search(rows,watch,{region:'CN-T'}), [rows[3]]);
  assert.deepEqual(search(rows,watch,{query:'중국판'}), [rows[2],rows[3]]);
  assert.deepEqual(search(rows,watch,{query:'CN001'}), [rows[2]]);
});
test('game/kind filters cannot cross-feed region identity', () => {
  assert.deepEqual(search(rows,watch,{region:'KR',game:'Pokémon'}), []);
  assert.deepEqual(search(rows,watch,{region:'US',kind:'BOX'}), []);
  assert.deepEqual(search(rows,watch,{query:'OP-13',region:'KR'}), []);
});
test('conflicting native/code evidence cannot inject aliases', () => {
  const ambiguous={items:[...watch.items,{...watch.items[0],product_code:'DIFFERENT'}]};
  assert.deepEqual(search(rows,ambiguous,{query:'OPK-13'}), []);
  assert.deepEqual(search(rows,ambiguous,{query:'계승되는 의지'}), [rows[0]]);
});
test('unknown filters and malformed payloads fail closed; bounded results', () => {
  assert.deepEqual(search(rows,watch,{region:'JP<script>'}), []);
  assert.deepEqual(search(rows,watch,{game:'Unknown game'}), []);
  assert.deepEqual(search(null,null,{query:'anything'}), []);
  assert.equal(search(rows,watch,{limit:2}).length,2);
});
