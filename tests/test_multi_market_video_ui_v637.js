"use strict";
// V637: regression tests for stale market-price UI and mobile accessibility.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ROOT = path.resolve(__dirname, "..");
const js = fs.readFileSync(path.join(ROOT,"multi_market_prices.js"),"utf8");
const css = fs.readFileSync(path.join(ROOT,"multi_market_prices.css"),"utf8");
new vm.Script(js, {filename:"multi_market_prices.js"});
const START = "\nlet marketRequestSequence=0,marketRequestController=null;";
const END = "\nfunction boot(){";
const first = js.indexOf(START), last = js.indexOf(END,first);
assert.ok(first>=0 && last>first, "Expected exactly one guarded request implementation");
assert.equal(js.indexOf(START,first+1),-1,"Duplicate request guard");
const functionSource=js.slice(first,last);

function harness(){
 const elements={
  query12:{value:"첫 번째 카드"},market12:{value:"JP"},v12Game:{value:"Pokémon"},
  multiMarketSummary:{className:"",innerHTML:""},multiMarketNote:{textContent:"outdated"}
 };
 for(const id of ["multiMarketVariant","multiMarketRecommendation","multiMarketHistory","multiMarketGrade","multiMarketReferences","multiMarketRows","multiMarketSources"])
  elements[id]={hidden:false,innerHTML:"old card price"};
 const pending=[],rendered=[],state={__multiMarketPrices:{stale:true}};
 let fetchImpl=(url,opts)=>new Promise(resolve=>pending.push({url,opts,resolve}));
 const env={
  $:id=>elements[id]||null,window:state,mount:()=>true,render:data=>rendered.push(data),
  renderRecent:()=>{},variantTerms:{},getFetch:()=>fetchImpl
 };
 const factory=new vm.Script(`(function(env){
  let lastBaseQuery="",variantOverride="",marketPrinting="ALL",marketCondition="ALL";
  const $=env.$,mount=env.mount,render=env.render,renderRecent=env.renderRecent;
  const variantTerms=env.variantTerms,window=env.window;
  const fetch=(...args)=>env.getFetch()(...args);
  ${functionSource}
  return {load};
 })`,{filename:"test_multi_market_video_ui_v637_harness.js"}).runInNewContext(Object.create(null),{timeout:2000});
 return { ...factory(env),elements,pending,rendered,state,setFetch:v=>{fetchImpl=v;} };
}
async function main(){
 const h=harness();
 const first=h.load();
 assert.equal(h.state.__multiMarketPrices,null,"New request must hide old market snapshot");
 assert.equal(h.elements.multiMarketRecommendation.innerHTML,"","Old recommendation must be hidden");
 h.elements.query12.value="두 번째 카드";
 const second=h.load();
 assert.equal(h.pending.length,2);
 h.pending[1].resolve({ok:true,json:async()=>({ok:true,query:"두 번째 카드"})});
 await second;
 h.pending[0].resolve({ok:true,json:async()=>({ok:true,query:"첫 번째 카드"})});
 await first;
 assert.deepEqual(h.rendered.map(x=>x.query),["두 번째 카드"],"Late stale reply must not overwrite newer card");
 assert.equal(h.state.__multiMarketPrices.query,"두 번째 카드");
 h.elements.query12.value="실패하는 카드";
 h.setFetch(async()=>{throw new Error("offline");});
 await h.load();
 assert.equal(h.state.__multiMarketPrices,null,"Failed request must clear old result");
 assert.match(h.elements.multiMarketSummary.innerHTML,/수집 실패/);
 h.elements.query12.value="";
 await h.load();
 assert.equal(h.state.__multiMarketPrices,null,"Empty query must not re-expose old result");
 assert.match(h.elements.multiMarketSummary.innerHTML,/카드 인식 후/);
 assert.match(css,/-webkit-line-clamp:unset/,"Titles must expand on narrow viewports");
 assert.match(css,/min-height:44px/,"Touch targets must be >=44px");
 console.log("PASS V637: syntax, concurrent request ordering, stale-value suppression, failure/empty reset, mobile readability");
}
main().catch(err=>{console.error(err);process.exitCode=1;});
