"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const {test}=require("node:test");
const m=require("../../tablet_unified_dashboard_v676.js");
const A="a".repeat(32),B="b".repeat(32),C="c".repeat(32);
const local=(id=A,kind="CARD",region="KR")=>({
 id,kind,region,game_id:"pokemon",name:"Pikachu",image_url:"/api/local-card-images/file/"+id,
 linked_to_existing_catalog:true,identity_verification:"CODE_MATCH",linked_source_record_id:B,
 card_metadata:{set_name:"Future",generation:"9",card_number:"012/100"}
});
const source=()=>({source_record_id:B,game_id:"pokemon",kind:"CARD",region:"KR",name:"Pikachu 012",
 source_url:"https://www.pokemon-card.com/official",product_codes:["012"]});
const match=()=>({id:A,source_record_id:B,match:"CODE_MATCH",image_url:"/api/local-card-images/file/"+A,
 game_id:"pokemon",region:"KR",kind:"CARD",catalog_kind:"CARD"});
const linked=()=>({ok:true,local_catalog:[local()],source_catalog:[source()],
 catalog_matches:[match()],summary:{catalog_to_image_gaps:0},source_errors:[]});
test("strict image ids and no external/credential image references",()=>{
 assert.equal(m.photoPath(local()),"/api/local-card-images/file/"+A);
 assert.equal(m.photoPath({...local(),image_url:"https://evil.example/box.png"}),"");
 assert.equal(m.photoPath({...local(),image_url:"/api/local-card-images/file/"+C}),"");
 assert.equal(m.photoPath({...local(),id:"../../etc/passwd"}),"");
});
test("official and marketplace sources accept HTTPS without userinfo",()=>{
 assert.equal(m.safeLink("https://www.pokemon-card.com/official"),"https://www.pokemon-card.com/official");
 for(const url of ["javascript:alert(1)","http://www.pokemon-card.com/","https://user:secret@www.pokemon-card.com/",
   "https://evil-pokemon-card.com/","https://127.0.0.1/private","https://www.pokemon-card.com:8080/x"])
   assert.equal(m.safeLink(url),"",url);
});
test("matching exact id, code, kind, edition and symmetric evidence links photo",()=>{
 const model=m.makeRows(linked(),{items:[]},{items:[]},{items:[]});
 assert.equal(model.linked,1);
 assert.equal(model.entries[0].image,"/api/local-card-images/file/"+A);
 assert.equal(model.entries[0].region,"KR");
 assert.equal(model.entries[0].generation,"9");
 assert.equal(model.entries[0].grade,"미확인");
});
test("region/edition/kind mismatch and ambiguous matches never join photos",()=>{
 for(const mutation of [
    x=>x.source_catalog[0].region="JP",
    x=>x.source_catalog[0].kind="BOX",
    x=>x.catalog_matches[0].region="JP",
    x=>x.catalog_matches[0].match="NAME_ONLY",
    x=>x.catalog_matches[0].image_url="/api/local-card-images/file/"+C,
    x=>x.catalog_matches.push(match()),
    x=>x.local_catalog[0].identity_verification="UNLINKED",
    x=>x.local_catalog[0].linked_to_existing_catalog=false,
    x=>x.source_catalog.push(source()),
 ]){
  const r=linked();mutation(r);assert.equal(m.linkRecords(r).size,0);
 }
});
test("local cards and BOX are visible independently without invented grades or prices",()=>{
 const card={...local(),id:A,linked_to_existing_catalog:false};
 const box={...local(C,"BOX","CN-S"),name:"Special Box",linked_to_existing_catalog:false};
 const model=m.makeRows(null,{items:[card,box]},null,null);
 assert.equal(model.entries.length,2);
 assert.deepEqual(model.entries.map(x=>x.category).sort(),["BOX","CARD"]);
 assert.equal(model.entries[0].grade,"미확인");
 assert.equal(model.entries[0].price,"미확인");
 assert.equal(m.select(model.entries,{region:"CN"}).length,1);
 assert.equal(m.select(model.entries,{region:"JP"}).length,0);
});
test("event and collaboration listing is only source tagged, never auto-image matched",()=>{
 const e={items:[{name_ko:"EXHIBITION",category:"collab",game:"Pokemon",region:"JP",
 source:"https://www.pokemon-card.com/info/005397.html",source_grade:"official",start_date:"2026-09-01"}]};
 const m0=m.makeRows(linked(),{items:[]},{items:[]},e);
 assert.equal(m.select(m0.entries,{kind:"EVENT"}).length,1);
 assert.equal(m0.events,1);
 assert.equal(m.select(m0.entries,{q:"exhibi"}).length,1);
 assert.equal(m0.entries.at(-1).image,"");
 assert.equal(m0.entries.at(-1).marketVerified,false);
});
test("malicious event data and untrusted price input are not HTML interpreted",()=>{
 const e={items:[null,{name_ko:"<img src=x onerror=alert(1)>",category:"event",
 region:"KR",game:"Test",source:"javascript:alert(1)"}]};
 const watch={items:[{name:"<script>alert(1)</script>",region:"KR",game:"Pokemon",asset:"BOX",
 source:"https://kream.co.kr/products/123",official_price:"₩50000"}]};
 const data=m.makeRows(null,{items:[]},watch,e);
 assert.equal(data.entries.length,1);
 assert.equal(data.entries[0].marketVerified,false);
});
test("preview read-only / CSS and no write endpoints, unsafe HTML helpers",()=>{
 const html=fs.readFileSync(path.join(__dirname,"../../tablet_unified_dashboard_v676.html"),"utf8");
 const js=fs.readFileSync(path.join(__dirname,"../../tablet_unified_dashboard_v676.js"),"utf8");
 assert.match(html,/tablet_unified_dashboard_v676\.js/);
 assert.match(html,/connect-src 'self'/);
 assert.doesNotMatch(js,/innerHTML|insertAdjacentHTML|eval\(|localStorage|sessionStorage|fetch\(.+method\s*:\s*['"]POST/);
 assert.doesNotMatch(js,/train_if_ready|\/api\/local-card-images\/save|model.*write/);
});
