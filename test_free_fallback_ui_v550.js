#!/usr/bin/env node
"use strict";
// V550: execute real tablet source helpers without a network or graphical browser.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");

const key="KR|인페르노X|HIT";
const elements={
 identityCardName:{value:"메가리자몽X ex"},
 identityCardNumber:{value:"116/080"},
 identityRegion:{value:"KR"},
 identityMarketKey:{value:key},
 econCard:{options:[{value:key,textContent:"KR 메가리자몽X ex 116/080"}]},
};
const sandbox={
 document:{readyState:"loading",addEventListener(){},
           getElementById(id){return elements[id]||null}},
 window:{},
 location:{href:"http://127.0.0.1:8765/"},
 URL,Date,Number,Array,String,Intl,encodeURIComponent,
};
vm.createContext(sandbox);
const file=fs.readFileSync("grade_market_flow.js","utf8");
const tagged=file.replace(/\}\)\(\);\s*$/, "globalThis.__v550={sourceHealth,savedCrosscheckRows,safeReferenceUrl,setHealth:x=>linkHealth=x,setMarket:x=>platformMarket=x};})();");
assert.notEqual(tagged,file,"IIFE helper exposure for isolated testing must match");
vm.runInContext(tagged,sandbox,{timeout:1500,filename:"grade_market_flow.js"});
const bridge=sandbox.__v550;
const oldStamp=new Date().toISOString();
bridge.setHealth({updated_at:oldStamp,degraded_hosts:[
 {host:"kream.co.kr",transient:11,restricted:0},
 {host:"www.coupang.com",transient:0,restricted:1},
]});
assert.equal(bridge.sourceHealth("https://kream.co.kr/products/1").count,11);
assert.equal(bridge.sourceHealth("https://www.coupang.com/search").label,"자동접속 제한");
assert.equal(bridge.sourceHealth("https://fakekream.co.kr/products/1"),null);
bridge.setHealth({updated_at:"2025-01-01T00:00:00Z",degraded_hosts:[
 {host:"kream.co.kr",transient:11}]});
assert.equal(bridge.sourceHealth("https://kream.co.kr/products/1"),null,"stale audit not current status");
bridge.setHealth(null);
const price={source:"KREAM",price_krw:380000,observed_at:"2026-10-01T10:00:00+00:00",url:"https://kream.co.kr/products/123"};
bridge.setMarket({entries:{[key]:{source_crosschecks:[
 price,
 {source:"Collectory",price_krw:375000,observed_at:"2026-10-08T10:00:00Z",url:"https://collectory.cc/cards/1"},
 {source:"KREAM",price_krw:999999,observed_at:"2999-01-01T00:00:00Z",url:"https://kream.co.kr/products/1"},
 {source:"KREAM",price_krw:12,observed_at:"2026-10-08T10:00:00Z",url:"https://kream.co.kr/products/2"},
 {source:"unknown",price_krw:1e7,observed_at:"2026-10-08T10:00:00Z"},
]}}});
assert.equal(bridge.savedCrosscheckRows().length,2);
assert.equal(bridge.savedCrosscheckRows()[0].price_krw,380000);
assert.equal(bridge.safeReferenceUrl({url:"https://evil.example/"}, ""), "");
assert.ok(bridge.safeReferenceUrl({url:"https://collectory.cc/cards/1"},"").startsWith("https://"));
elements.identityCardNumber.value="116/081";
assert.equal(bridge.savedCrosscheckRows().length,0,"mismatched card number must not inherit price");
elements.identityCardNumber.value="116/080";
elements.identityRegion.value="JP";
assert.equal(bridge.savedCrosscheckRows().length,0,"JP/US variant cannot inherit KR price");
elements.identityRegion.value="KR";
elements.identityCardName.value="";
elements.identityCardNumber.value="";
assert.equal(bridge.savedCrosscheckRows().length,0,"clearing a card cannot leave previous prices visible");
assert.match(file,/if\(!name&&!number\)\{[^\n]*renderSavedCrosschecks\(\);return\}/,"identity reset must repaint saved prices");
process.stdout.write("V550 tablet free fallback and dated cached crosschecks: 12 assertions PASS\n");
