'use strict';
// Pure, deterministic review tests. Never evaluate downloaded HTML as code.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {search} = require('../tablet_market_search_v885.js');
const html = fs.readFileSync(path.resolve(__dirname,'../tablet_market_hub_v886_preview.html'),'utf8');
const source = fs.readFileSync(path.resolve(__dirname,'../tablet_market_search_v885.js'),'utf8');

const rows = [
  {region:'KR',game:'ONE PIECE',kind:'BOX',name:'계승되는 의지'},
  {region:'JP',game:'ONE PIECE',kind:'BOX',name:'受け継がれる意志'},
  {region:'CN-S',game:'Pokémon',kind:'BOX',name:'英雄'},
  {region:'CN-T',game:'Pokémon',kind:'BOX',name:'英雄'},
  {region:'US',game:'Pokémon',kind:'HIT',name:'Charizard'}
];
const watch={items:[
  {region:'KR',game:'ONE PIECE',asset:'BOX',name:'계승되는 의지',product_code:'OPK-13'},
  {region:'CN-S',game:'Pokémon',asset:'BOX',name:'英雄',product_code:'CN001'},
  {region:'CN-T',game:'Pokémon',asset:'BOX',name:'英雄',product_code:'TW001'}
]};
test('screen has one inline script with exact approved V885 source',()=>{
  assert.equal(html.split('<script>').length,2);
  assert.equal(html.split('</script>').length,2);
  assert.ok(html.includes('<script>\n'+source+'\n'),'inline preview and reviewed search module have identical source bytes');
  assert.doesNotMatch(html,/method:\s*['"]POST['"]/);
  assert.doesNotMatch(html,/innerHTML\s*=/);
});
test('card price tile targets market, not scanner-only preview',()=>{
  assert.match(html,/<button class="tile orange" data-page="market"[^>]*>[\s\S]*?카드 시세확인/);
  assert.doesNotMatch(html,/<button class="tile orange" data-page="scanner"/);
});
test('home and market game controls share the same selected game state',()=>{
  assert.ok(html.includes("state.game=g;state.limit=24;$('marketGame').value=g"));
  assert.ok(html.includes("state.game=$('marketGame').value"));
  assert.ok(html.includes("String(x.dataset.game===state.game)"));
  assert.ok(html.includes("const rows=window.TCGTabletMarketSearchV885.search(state.rows,state.watch"));
  assert.ok(html.includes("state.watch=val(1)"));
});
test('country selection supports CN combined without conflating language codes',()=>{
  assert.match(html,/<option value="CN">중국판 전체<\/option>/);
  assert.match(html,/<option value="CN-S">중국 간체<\/option>/);
  assert.match(html,/<option value="CN-T">중국 번체<\/option>/);
  assert.deepEqual(search(rows,watch,{region:'CN',game:'Pokémon'}),[rows[2],rows[3]]);
  assert.deepEqual(search(rows,watch,{region:'CN-S',game:'Pokémon'}),[rows[2]]);
  assert.deepEqual(search(rows,watch,{region:'CN-T',game:'Pokémon'}),[rows[3]]);
});
test('combined keywords and game/edition boundaries are enforced by running search',()=>{
  assert.deepEqual(search(rows,watch,{query:'원피스 한국판 OPK-13'}),[rows[0]]);
  assert.deepEqual(search(rows,watch,{query:'포켓몬 중국판'}),[rows[2],rows[3]]);
  assert.deepEqual(search(rows,watch,{query:'OPK-13',region:'JP'}),[]);
  assert.deepEqual(search(rows,watch,{query:'포켓몬',game:'NARUTO'}),[]);
});

test('quick country tabs are connected to the exact market dropdown and guard separate China identities',()=>{
  assert.match(html,/id="marketRegionTabs" aria-label="국가별 빠른 선택"/);
  assert.ok(html.includes("MARKET_REGIONS=[['ALL','전체'],['KR','한국판'],['JP','일본판'],['US','미국판'],['CN','중국판']]"));
  assert.ok(html.includes("b.dataset.region=region"));
  assert.ok(html.includes("$('marketRegion').value=region;state.limit=24;syncRegionTabs();renderMarket()"));
  assert.ok(html.includes("$('marketRegion').addEventListener('change',()=>{state.limit=24;syncRegionTabs();renderMarket()}"));
  assert.deepEqual(search(rows,watch,{region:'KR'}),[rows[0]]);
  assert.deepEqual(search(rows,watch,{region:'JP'}),[rows[1]]);
  assert.deepEqual(search(rows,watch,{region:'US'}),[rows[4]]);
  assert.deepEqual(search(rows,watch,{region:'CN'}),[rows[2],rows[3]]);
});
test('changing search context resets pagination and more results remain bounded',()=>{
  assert.ok(html.includes("$('marketGame').value=state.game;state.limit=24;go('market')"));
  assert.ok(html.includes("state.game=g;state.limit=24;$('marketGame').value=g"));
  assert.ok(html.includes("$('marketKind').addEventListener('change',()=>{state.limit=24;renderMarket()}"));
  assert.ok(html.includes("state.limit=Math.min(5000,state.limit+24)"));
  assert.equal(search(rows,watch,{limit:2}).length,2);
  assert.equal(search(rows,watch,{limit:10000}).length,rows.length);
});
