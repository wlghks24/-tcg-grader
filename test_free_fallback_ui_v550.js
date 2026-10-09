#!/usr/bin/env node
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const code=fs.readFileSync("tcg_market_expanded_v487.js","utf8");
const pos=code.lastIndexOf("/* V550: local-only free source handoff.");
assert.ok(pos>0,"independent market-home addon must be present");
const addon=code.slice(pos);
const root={childNodes:[],appendChild(x){this.childNodes.push(x)}};
function fakeElement(tag){
 return {tag,childNodes:[],style:{},addEventListener(){},appendChild(x){this.childNodes.push(x)},
  replaceChildren(){this.childNodes=[]}};
}
const win={};
const context={
 window:win,document:{
  getElementById(id){return id==="tcgMarketHome"?root:null},
  createElement:fakeElement,addEventListener(){}},
 URL,Date,Number,Array,String,
 fetch:async()=>({ok:false}),
 encodeURIComponent,
};
vm.runInNewContext(addon,context,{filename:"tcg_market_expanded_v487.js",timeout:1500});
assert.equal(root.childNodes.length,1,"native details section mounted");
assert.equal(root.childNodes[0].tag,"details");
const policy=win.tcgFreeFallbackPolicyV550;
assert.ok(policy && typeof policy.recentProvider==="function");
const clock=Date.now();
const provider={updated_at:new Date(clock).toISOString(),degraded_hosts:[
 {host:"kream.co.kr",transient:11,restricted:0},
 {host:"www.coupang.com",restricted:1,transient:0}
]};
assert.equal(policy.recentProvider(provider,"www.kream.co.kr",clock).count,11);
assert.equal(policy.recentProvider(provider,"coupang.com",clock).reason,"자동접속 제한");
assert.equal(policy.recentProvider(provider,"fakekream.co.kr",clock),null);
assert.equal(policy.recentProvider({...provider,updated_at:"2025-01-01T00:00:00Z"},"kream.co.kr",clock),null);
const key="KR|인페르노X|HIT";
const price={
 source:"KREAM",price_krw:380000,observed_at:"2026-10-01T10:00:00+00:00",
 url:"https://kream.co.kr/products/123",confidence:0.99
};
const data={entries:{[key]:{
 card_name:"메가리자몽X ex",card_number:"116/080",
 source_crosschecks:[
 price,
 {source:"Collectory",price_krw:375000,confidence:0.9,
  observed_at:"2026-10-08T10:00:00Z",url:"https://collectory.cc/cards/1"},
 {...price,observed_at:"2999-01-01T00:00:00Z"},
 {...price,url:"https://evil.example/products/123"},
 {...price,confidence:0.1},
 {...price,price_krw:-1}
]}}};
const ctx={key,name:"메가리자몽X ex",number:"116/080",region:"KR"};
assert.equal(policy.savedPrior(data,ctx,clock).length,2,"two dated and supported cached sources only");
assert.equal(policy.savedPrior(data,{...ctx,region:"JP"},clock).length,0);
assert.equal(policy.savedPrior(data,{...ctx,number:"116/081"},clock).length,0);
assert.equal(policy.savedPrior(data,{...ctx,name:"다른 카드"},clock).length,0);
assert.equal(policy.savedPrior({entries:{}},ctx,clock).length,0);
assert.equal(policy.savedPrior(data,{...ctx,key:"JP|인페르노X|HIT"},clock).length,0);
assert.match(addon,/noopener noreferrer/);
assert.match(addon,/KREAM 체결가로 대체하지 않습니다/);
assert.match(addon,/현재가 아님/);
process.stdout.write("V550 free provider fallback UI: 15 deterministic assertions PASS\n");
