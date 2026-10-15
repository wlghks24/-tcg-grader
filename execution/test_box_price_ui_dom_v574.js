#!/usr/bin/env node
/* V574: price-widget interaction smoke test with bounded DOM and network stubs.
   Does not claim screenshot or Lenovo proof. No npm packages or external services. */
'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const all = fs.readFileSync('box_knowledge_stats.js','utf8');
const token = '/* V572: BOX observed price bounds';
const code = all.slice(all.lastIndexOf(token));
assert.ok(code.startsWith(token),'V572 quote is missing');

const today = new Date(Date.now()+9*60*60*1000).toISOString().slice(0,10);
const key = 'JP|메가 심포니아|BOX';
const base = {game:'Pokémon',display:'₩37,000',source_date:today,
              source:'https://pokard.io/',link_status:'정상'};
const product = {game:'Pokémon',country:'JP',name:'메가 심포니아'};
function sold(id, price){
  const ebay=id==='ebay';
  return {game:'Pokémon',product_key:key,unit:'BOX',unit_quantity:1,sealed:true,
    price_krw:price,currency:'KRW',verification_status:'verified',
    evidence_type:'completed_sale',source_id:id,
    source_url:ebay?'https://www.ebay.com/itm/12345678901':'https://kream.co.kr/products/42',
    lineage_key:id+':first',sale_id:ebay?'ebay:12345678901':'kream:456',
    observed_at:today,reviewed_at:today,review_status:'manual_verified',
    review_method:'source_page_crosscheck',transaction_finality:'sold'};
}

async function fixture(priceData, options={}){
  const timers=[],handlers={},events={};
  let quote=null,observerConnected=false,requests=0;
  const body = {appendChild(element){quote=element}};
  const card = {querySelector(selector){
    if(selector==='.boxm-quote')return quote;
    if(selector==='.box-kb-body')return body;
    return null;
  }};
  const box={querySelectorAll(selector){assert.equal(selector,'.box-kb-card');return [card]}};
  const doc={
    readyState:'loading',
    getElementById(id){return id==='box12'?box:null},
    querySelector(sel){
      return sel==='.box-kb-country.active'?{dataset:{kbCountry:'JP'}}:null;
    },
    createElement(tag){
      assert.equal(tag,'section');
      return {className:'',innerHTML:'',setAttribute(name,value){
        assert.equal(name,'aria-label');assert.ok(value.includes('BOX 관측 가격'));
      }};
    },
    addEventListener(name,callback){handlers[name]=callback}
  };
  const window={addEventListener(name,callback){events[name]=callback}};
  const ctx={
    document:doc,window,COUNTRY_BOX_DATA:[product],
    URL,Date,Intl,Math,Number,Object,Array,Set,
    setTimeout(fn){timers.push(fn);return 1},
    setInterval(){return 1},
    MutationObserver:class{observe(element,settings){
      assert.equal(element,box);assert.equal(settings.childList,true);
      observerConnected=true;
    }},
    fetch:async path=>{
      requests++;
      assert.ok(path.startsWith('market_prices.json?box_price='));
      if(options.fetchError)throw new Error('offline');
      return {ok:true,json:async()=>({entries:priceData})};
    },
  };
  vm.runInNewContext(code,ctx,{timeout:1200});
  assert.equal(typeof handlers.DOMContentLoaded,'function');
  handlers.DOMContentLoaded();
  for(let n=0;n<15;n++){
    await Promise.resolve();
    for(const f of timers.splice(0,timers.length))f();
  }
  assert.ok(observerConnected,'catalog mutation observer not attached');
  assert.equal(requests,1,'one bounded fetch per page init');
  assert.ok(quote,'price comparison surface not appended');
  assert.ok(quote.innerHTML.includes('관측 최저가'));
  assert.ok(quote.innerHTML.includes('관측 최고가'));
  assert.ok(quote.innerHTML.includes('판매추천가'));
  return quote.innerHTML;
}

(async()=>{
  const single=await fixture({[key]:base});
  assert.ok(single.includes('₩37,000'),single);
  assert.ok(single.includes('단일 출처 표시가격'));
  assert.ok(single.includes('근거 부족'));
  assert.ok(!single.includes('₩40,000'));
  const matched=await fixture({[key]:{
     game:'Pokémon',box_price_evidence:[sold('ebay',30000),sold('kream',50000)]
  }});
  assert.ok(matched.includes('₩30,000'));
  assert.ok(matched.includes('₩50,000'));
  assert.ok(matched.includes('₩40,000'));
  assert.ok(matched.includes('완료거래'));
  const mismatch=await fixture({[key]:{...base,game:'ONE PIECE'}});
  assert.ok(!mismatch.includes('₩37,000'));
  assert.ok(mismatch.includes('게임과 BOX 가격 자료 불일치'));
  const offline=await fixture({}, {fetchError:true});
  assert.ok(offline.includes('근거 부족'));
  const stale=await fixture({[key]:{...base,source_date:'2020-01-01'}});
  assert.ok(stale.includes('근거 부족'));
  console.log('V574 DOM SMOKE PASS: 5 price render/offline/mismatch scenarios');
})().catch(error=>{console.error(error);process.exitCode=1});
