"use strict";
// V638: real-code BOX market pricing tests; no paid providers or fake production prices.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");
const source=fs.readFileSync(path.join(root,"box_knowledge_stats.js"),"utf8");
const css=fs.readFileSync(path.join(root,"box_knowledge_stats.css"),"utf8");
const market=JSON.parse(fs.readFileSync(path.join(root,"market_prices.json"),"utf8"));
new vm.Script(source, {filename:"box_knowledge_stats.js"});
const p1=source.indexOf("function parseDate(");
const p2=source.indexOf("function ensureGameToolbar(",p1);
const p3=source.indexOf("function daysOld(");
const p4=source.indexOf("function freshnessPoints(",p3);
assert.ok(p1>=0&&p2>p1&&p3>p2&&p4>p3,"exact source helper boundaries required");
const setup=String.raw`
const assert=globalAssert;
const marketCache={entries:{}};
function assetOfKey(k){return String(k||'').split('|')[2]||''}
function countryOfKey(k){return String(k||'').split('|')[0]||''}
function nameOfKey(k){return String(k||'').split('|')[1]||''}
const priced=v=>!!String(v?.display||'').trim();
`;
const cases=String.raw`
const day=offset=>{const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()+offset);return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-')};
const boxKey='JP|인페르노 X|BOX';
const good={game:'Pokémon',display:'₩50,000~₩58,000',source_date:day(-2),link_status:'정상',
  source:'https://kream.co.kr/products/12345',kind:'최근 관측 매물'};
const asEntries=v=>({[boxKey]:v});
const parsed=boxMarketAssessment('JP','인페르노 X','Pokémon',asEntries(good));
assert.equal(parsed.low,50000);
assert.equal(parsed.high,58000);
assert.equal(parsed.unit,'KRW');
assert.equal(parsed.recommended,null,"one listing can never become a completed-sale recommendation");
assert.match(parsed.basis,/단일 출처 관측범위/);
for(const different of [
 ['KR','인페르노 X','Pokémon'],['JP','인페르노 X','ONE PIECE'],['JP','다른 이름','Pokémon']
])assert.equal(boxMarketAssessment(...different,asEntries(good)).low,null,"exact-edition identity required");
const homepage=boxMarketAssessment('JP','인페르노 X','Pokémon',asEntries({...good,source:'https://pokard.io/'}));
assert.equal(homepage.low,null);
assert.equal(homepage.recorded,good.display);
for(const v of [
 {...good,source_date:day(-15)}, {...good,source_date:day(1)},
 {...good,source_date:'2026-02-31'}, {...good,link_status:'네트워크 지연'},
 {...good,source:'https://example.com/products/1'}, {...good,source:'http://kream.co.kr/products/123'}
])assert.equal(boxMarketAssessment('JP','인페르노 X','Pokémon',asEntries(v)).low,null,"stale/unsafe data must fail closed");
assert.equal(boxMarketAssessment('JP','인페르노 X','Pokémon',{'JP|인페르노 X|HIT':good}).low,null,"HIT cannot be BOX");
assert.equal(boxMarketAssessment('JP','인페르노 X 8BOX','Pokémon',{'JP|인페르노 X 8BOX|BOX':good}).low,null,"bundles cannot be one BOX");
assert.equal(boxMarketAssessment('JP','인페르노 X','Pokémon',asEntries({...good,box_quantity:8})).low,null);
assert.equal(boxParseRange('₩999~₩200'),null);
assert.equal(boxParseRange('50,000원'),null);
assert.equal(boxParseRange('₩50,000~$58,000'),null);
assert.equal(boxParseRange('₩50,000~₩58,000').high,58000);
const sold=(id,price,url)=>({
 verified:true,evidence_class:'completed',sealed:true,unit:'BOX',box_quantity:1,currency:'KRW',
 country:'JP',game:'Pokémon',product_name:'인페르노 X',transaction_id:id,
 price_krw:price,sold_at:day(-1),source_url:url
});
const completed=[
 sold('A1',60000,'https://kream.co.kr/products/123'),
 sold('A2',65000,'https://kream.co.kr/products/123'),
 sold('B1',62000,'https://www.ebay.com/itm/123')
];
const verified=boxMarketAssessment('JP','인페르노 X','Pokémon',asEntries({...good,completed_sales:completed}));
assert.equal(verified.low,60000);
assert.equal(verified.high,65000);
assert.equal(verified.recommended,62250,"recommendation is median of source medians");
assert.match(verified.basis,/완료거래 3건/);
const duplicate=boxMarketAssessment('JP','인페르노 X','Pokémon',asEntries({...good,completed_sales:[completed[0],completed[0],completed[2]]}));
assert.equal(duplicate.recommended,null,"duplicate transaction must not satisfy minimum sample count");
const misprinted=boxMarketAssessment('JP','인페르노 X','Pokémon',asEntries({...good,completed_sales:[completed[0],{...completed[1],country:'KR'},completed[2]]}));
assert.equal(misprinted.recommended,null,"edition conflicts must not count");
const outlier=boxMarketAssessment('JP','인페르노 X','Pokémon',asEntries({...good,completed_sales:[completed[0],completed[1],{...completed[2],price_krw:190000}]}));
assert.equal(outlier.recommended,null,"unexplained extreme spread must fail closed");
assert.equal(boxMarketAssessment('JP','인페르노 X','Pokémon',realData.entries).recommended,null,"stored unverified single-source quotes cannot create a sale recommendation");
console.log("PASS V638: strict BOX edition, single-box, source, stale, sale sample, duplicate, outlier, safe recommendation");
`;
vm.runInNewContext(setup+source.slice(p1,p2)+"\n"+source.slice(p3,p4)+"\n"+cases,
 {URL,Date,globalAssert:assert,realData:market,console}, {timeout:4000});
assert.match(css,/boxkb-market-price-grid/);
assert.match(css,/min-height:44px/);


const officialStart=source.indexOf("function officialBoxPriceText(");
const officialEnd=source.indexOf("function trusted(p)",officialStart);
assert.ok(officialStart>=0 && officialEnd>officialStart,"official price formatting must remain testable");
const officialFn=source.slice(officialStart,officialEnd);
const prices=vm.runInNewContext(officialFn+String.raw`
[
 officialBoxPriceText({amount:48000,currency:'KRW',unit:'BOX'},'KR','BOX'),
 officialBoxPriceText({amount:5280,currency:'JPY',unit:'BOX'},'JP','BOX'),
 officialBoxPriceText({amount:119.99,currency:'USD',unit:'BOX'},'US','BOX'),
 officialBoxPriceText({amount:180,currency:'JPY',unit:'PACK'},'JP','BOOSTER_PACK'),
 officialBoxPriceText({amount:5280,currency:'USD',unit:'BOX'},'JP','BOX'),
 officialBoxPriceText({amount:0,currency:'KRW',unit:'BOX'},'KR','BOX')
]`,{Intl},{timeout:2000});
assert.equal(prices[0],'제조사 정가 48,000원 / BOX');
assert.equal(prices[1],'제조사 정가 ¥5,280 / BOX');
assert.equal(prices[2],'제조사 정가 $119.99 / BOX');
assert.equal(prices[3],'제조사 정가 ¥180 / 팩');
assert.equal(prices[4],'제조사 정가 미확인');
assert.equal(prices[5],'제조사 정가 미확인');
