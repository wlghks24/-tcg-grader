"use strict";
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const {test}=require("node:test");
const html=fs.readFileSync(path.join(__dirname,"..","index.html"),"utf8");
const lines=html.split(/\r?\n/);
function makeContext(){
 const c=vm.createContext({
  URL, console, Date,
  fxRates:{JPY_KRW:8.7,USD_KRW:1380,EUR_KRW:1520},
  fxTimestamp:new Date().toISOString(),
  fxUpdated:new Date().toISOString().slice(0,10),
  fxExpiryTimer:null,
  FX_MAX_AGE_MS:72*60*60*1000,
  FX_MAX_FUTURE_SKEW_MS:6*60*60*1000,
  renderCountryAnalysis(){},renderTradeCatalog(){},scheduleFxExpiry(){},
  clearFxConversionDisplay(){},escapeDisplayText:x=>String(x)
 });
 const one=name=>{
  const prefix="function "+name+"(";
  const line=lines.find(x=>x.trimStart().startsWith(prefix));
  assert.ok(line, "missing single-line browser function: "+name);
  vm.runInContext(line,c,{filename:name});
 };
 const block=(name,async=false)=>{
  const p=new RegExp("^"+(async?"async ":"")+"function "+name+"\\([^\\n]*\\)\\{[\\s\\S]*?^\\}","m");
  const m=p.exec(html);
  assert.ok(m,"missing multiline browser function: "+name);
  vm.runInContext(m[0],c,{filename:name});
 };
 one("fxTimestampFresh");
 one("foreignKrw");
 one("clearExpiredFx");
 block("marketAmountKrw");
 block("loadExchangeRates",true);
 return c;
}
const validEntry=()=>({amount:22.5,currency:"USD",price_type:"sold",grading_state:"raw",region:"US",card_number:"CP-001",variant:"standard",observed_on:new Date().toISOString(),source:"https://www.ebay.com/itm/123456"});
test("verified EUR direct conversion",()=>{
 const c=makeContext();
 assert.match(c.foreignKrw("EUR 0.34"),/₩500/);
 assert.match(c.foreignKrw("€1.00"),/₩1,500/);
});
test("price ranges keep both converted bounds, not last or midpoint",()=>{
 const c=makeContext();
 assert.match(c.foreignKrw("$10 ~ $20"),/₩13,800 ~ ₩27,600/);
 assert.match(c.foreignKrw("¥1,000~¥2,000"),/₩8,700 ~ ₩17,400/);
});
test("ambiguous and mixed currency fails closed",()=>{
 const c=makeContext();
 for(const text of ["¥1000~2000","$10 ~ EUR 20","€0,34","¥5 + ¥6","€1.00 ~ €0.50"]){
  assert.equal(c.foreignKrw(text),"",text);
 }
});
test("invalid or expired FX is never used to compute EUR",()=>{
 const c=makeContext();
 c.fxRates.EUR_KRW=0;
 assert.equal(c.foreignKrw("EUR 2.00"),"");
 c.fxRates.EUR_KRW=1520;
 c.fxTimestamp=new Date(Date.now()-73*3600*1000).toISOString();
 assert.equal(c.foreignKrw("EUR 2.00"),"");
});
test("display text never directly becomes an economics price",()=>{
 const c=makeContext();
 for(const display of ["₩1,000,000","¥50,000 ~ ¥70,000","$100 ~ $200","EUR 0.34"]){
  assert.equal(c.marketAmountKrw(display),0);
 }
});
test("graded slab or asking price cannot auto-fill raw economics",()=>{
 const c=makeContext();
 for(const field of [{grading_state:"PSA10"},{price_type:"asking"},{price_type:"api_reference"},{variant:""},{card_number:""}]){
  assert.equal(c.marketAmountKrw({...validEntry(),...field}),0);
 }
});
test("only identified, recent completed raw-card sale is accepted",()=>{
 const c=makeContext();
 assert.equal(c.marketAmountKrw(validEntry()),Math.round(22.5*1380));
 assert.equal(c.marketAmountKrw({...validEntry(),amount:300,currency:"KRW"}),300);
});
test("stale, future, unsafe source, nonnumeric input fail closed",()=>{
 const c=makeContext();
 const e=validEntry();
 for(const val of [
  {observed_on:new Date(Date.now()-32*86400000).toISOString()},
  {observed_on:new Date(Date.now()+3*86400000).toISOString()},
  {source:"http://example.org/sale"},
  {source:"https://user:password@example.org/sale"},
  {amount:"23"},{amount:Infinity},{currency:"BTC"},{region:"XX"}
 ]){
  assert.equal(c.marketAmountKrw({...e,...val}),0,JSON.stringify(val));
 }
});
test("foreign pricing requires fresh reference FX",()=>{
 const c=makeContext();
 c.fxTimestamp=new Date(Date.now()-73*3600*1000).toISOString();
 assert.equal(c.marketAmountKrw(validEntry()),0);
 assert.equal(c.marketAmountKrw({...validEntry(),currency:"KRW"}),23);
});
test("oldest source timestamp determines expiry, never refreshed just by collection time",async()=>{
 const c=makeContext();
 const now=new Date().toISOString();
 const earlier=new Date(Date.now()-2*3600*1000).toISOString();
 c.fetch=async()=>({ok:true,json:async()=>({
  rates:{JPY_KRW:8.7,USD_KRW:1380,EUR_KRW:1520},
  updated_at:now,source_timestamp:earlier,source_route:"frankfurter-v2",
  source:"https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY,EUR"
 })});
 const result=await c.loadExchangeRates(false);
 assert.equal(result.ok,true);
 assert.equal(c.fxTimestamp,earlier);
 assert.equal(c.fxRates.EUR_KRW,1520);
});
test("missing source observation fails entire FX cache and clears values",async()=>{
 const c=makeContext();
 c.fetch=async()=>({ok:true,json:async()=>({
  rates:{JPY_KRW:8.7,USD_KRW:1380,EUR_KRW:1520},
  updated_at:new Date().toISOString()
 })});
 const result=await c.loadExchangeRates();
 assert.equal(result.ok,false);
 assert.equal(c.fxRates.USD_KRW,0);
 assert.equal(c.fxRates.EUR_KRW,0);
});
test("EUR source must match a verified provider route; USD/JPY remain compatible",async()=>{
 const c=makeContext();
 const now=new Date().toISOString();
 c.fetch=async()=>({ok:true,json:async()=>({
  rates:{JPY_KRW:8.7,USD_KRW:1380,EUR_KRW:1520},
  updated_at:now,source_timestamp:now,source_route:"frankfurter-v2",
  source:"https://malicious.example/api.frankfurter.dev/v2/rates"
 })});
 const result=await c.loadExchangeRates();
 assert.equal(result.ok,true);
 assert.equal(c.fxRates.EUR_KRW,0);
 assert.equal(c.fxRates.USD_KRW,1380);
});
test("invalid optional EUR rate does not break verified USD/JPY",async()=>{
 const c=makeContext();
 const now=new Date().toISOString();
 c.fetch=async()=>({ok:true,json:async()=>({
  rates:{JPY_KRW:8.7,USD_KRW:1380,EUR_KRW:"1520"},
  updated_at:now,source_timestamp:now,source_route:"frankfurter-v2",
  source:"https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY,EUR"
 })});
 const result=await c.loadExchangeRates();
 assert.equal(result.ok,true);
 assert.equal(c.fxRates.USD_KRW,1380);
 assert.equal(c.fxRates.EUR_KRW,0);
});
test("source older than 72h cannot be revived by a recent saved timestamp",async()=>{
 const c=makeContext();
 c.fetch=async()=>({ok:true,json:async()=>({
  rates:{JPY_KRW:8.7,USD_KRW:1380,EUR_KRW:1520},
  updated_at:new Date().toISOString(),
  source_timestamp:new Date(Date.now()-73*3600*1000).toISOString(),
  source_route:"frankfurter-v2",
  source:"https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY,EUR"
 })});
 const result=await c.loadExchangeRates();
 assert.equal(result.ok,false);
 assert.equal(c.foreignKrw("EUR 10"),"");
});
