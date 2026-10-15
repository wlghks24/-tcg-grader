"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const source=fs.readFileSync(path.join(__dirname,"..","box_knowledge_stats.js"),"utf8");
const fakeDocument={readyState:"loading",addEventListener() {},getElementById(){return null}};
const fakeWindow={addEventListener() {}};
vm.runInNewContext(source,{window:fakeWindow,document:fakeDocument,Date,URL,setTimeout(){},setInterval(){}},{filename:"box_knowledge_stats.js"});
const summarize=fakeWindow.TCGBoxPriceSummaryV572?.summarize;
assert.equal(typeof summarize,"function","BOX pricing must be wired to actual tablet JS");
const date=new Date("2026-10-15T10:00:00Z");
const identity={country:"KR",name:"블랙볼트",game:"Pokémon"};
const key="KR|블랙볼트|BOX";
const legacy={game:"Pokémon",display:"₩50,000~₩58,000",source_date:"2026-10-08",source:"https://kream.co.kr/products/627575/"};
let result=summarize(legacy,identity,date);
assert.equal(result.low,50000);assert.equal(result.high,58000);
assert.equal(result.recommended,null);assert.equal(result.tier,"reference");
assert.match(result.reason,/시장 전체 최저·최고 아님/);
result=summarize({...legacy,display:"₩50,000"},identity,date);
assert.equal(result.low,null);assert.equal(result.high,null);assert.equal(result.single,50000);assert.equal(result.recommended,null);
for(const display of ["₩50,000/BOX","₩58,000~₩50,000","$40","50,000 원","<img src=x>","₩-999","₩0","₩999999999999999999999"]){
 const p=summarize({...legacy,display},identity,date);
 assert.equal(p.recommended,null);
 assert.equal(p.low,null);
}
assert.equal(summarize({...legacy,source_date:"2026-08-21"},identity,date).single,null,"old quote is not live");
assert.equal(summarize({...legacy,source_date:"2999-01-01"},identity,date).single,null,"future date cannot count");
assert.equal(summarize({...legacy,source:"http://kream.co.kr/products/a"},identity,date).single,null,"no HTTP");
assert.equal(summarize({...legacy,game:"ONE PIECE"},identity,date).single,null,"different TCG");
const sale=(id,host,price,overrides={})=>({product_key:key,unit:"BOX",sealed:true,currency:"KRW",price_krw:price,
 observed_at:"2026-10-13",evidence_type:"completed_sale",verified:true,
 review_method:"source_page_crosscheck",sale_id:id,source_url:"https://"+host+"/itm/"+id,...overrides});
const sales=[sale("ebay:12345678911","www.ebay.com",50000),sale("kream:12345678912","kream.co.kr",70000)];
result=summarize({...legacy,price_observations:sales},identity,date);
assert.equal(result.low,50000);assert.equal(result.high,70000);
assert.equal(result.recommended,60000);assert.equal(result.tier,"completed_sale");assert.equal(result.sources,2);
const duplicate=summarize({...legacy,price_observations:[sales[0],{...sales[0],source_url:"https://kream.co.kr/same"}]},identity,date);
assert.equal(duplicate.recommended,null);assert.equal(duplicate.count,1,"mirrored sale deduplicated");
assert.equal(summarize({...legacy,price_observations:[sales[0],sale("ebay:12345678914","www.ebay.com",90000)]},identity,date).recommended,null,"one marketplace is not independent two-source verification");
assert.equal(summarize({...legacy,price_observations:[sales[0],sale("kream:12345678913","kream.co.kr",90000,{product_key:"KR|다른박스|BOX"})]},identity,date).recommended,null,"no cross product");
assert.equal(summarize({...legacy,price_observations:[sales[0],sale("kream:12345678913","kream.co.kr",90000,{unit:"8BOX"})]},identity,date).recommended,null,"no mixed box units");
assert.equal(summarize({...legacy,price_observations:[sales[0],sale("kream:12345678913","kream.co.kr",90000,{sealed:false})]},identity,date).recommended,null,"no loose/open product");
assert.equal(summarize({...legacy,price_observations:[sales[0],sale("kream:12345678913","kream.co.kr",90000,{verified:false})]},identity,date).recommended,null,"claimed sale cannot become verified");
assert.equal(summarize({...legacy,price_observations:[sale("kream:12345678910","kream.co.kr",85000,{observed_at:"2026-08-03"})]},identity,date).recommended,null,"stale sale");
console.log("BOX v572 price panel regression: PASS (legacy range, identity, date, evidence, dedup, independence)");
