"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const mod=require("../../docs/tablet/v676/tablet_unified_dashboard_v676.js");
const ROOT=path.resolve(__dirname,"../..");
const pic="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",sourceId="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
function fixtures(){
  return {
    local:{ok:true,version:46,
      source_catalog:[{source_record_id:sourceId,game_id:"pokemon",region:"CN-T",kind:"BOX",
        name:"Special Collection BOX",source_health:"HEALTHY",
        source_url:"https://asia.pokemon-card.com/hk/products/",observed_release_date:"2026-08-03"}],
      local_catalog:[{id:pic,image_url:"/api/local-card-images/file/"+pic,game_id:"pokemon",
        region:"CN-T",kind:"BOX",name:"Special Collection BOX",card_metadata:{set_name:"Anniversary",generation:"9"},
        linked_to_existing_catalog:true,identity_verification:"CODE_MATCH",linked_source_record_id:sourceId}],
      catalog_matches:[{id:pic,source_record_id:sourceId,match:"CODE_MATCH",
        region:"CN-T",game_id:"pokemon",kind:"BOX",catalog_kind:"BOX",image_url:"/api/local-card-images/file/"+pic}]},
    events:{items:[{game:"포켓몬 카드",region:"JP",category:"collab",
      name_ko:"공식 콜라보 행사",source_grade:"official",
      source:"https://www.pokemon-card.com/info/005397.html",start_date:"2026-10-25"}]}
  };
}
test("unique exact code linking joins BOX image and metadata without grade or price fabrication",()=>{
  const f=fixtures(),r=mod.normalize(f.local,f.events);
  assert.equal(r.length,2);
  assert.equal(r[0].image,"/api/local-card-images/file/"+pic);
  assert.equal(r[0].imageEvidence,"CODE_MATCH");
  assert.equal(r[0].meta.generation,"9");
  assert.equal(r[0].group,"box");
  for(const row of r){
    assert.equal(row.price,null);assert.equal(row.grade,null);
    assert.equal(row.gradePrediction,null);assert.equal(row.listingPrice,null);
  }
  assert.equal(r[1].group,"event");
  assert.equal(r[1].category,"콜라보");
  assert.equal(r[1].image,"");
});
test("mismatched CN locality, game, or kind never creates a linked image",()=>{
  for(const field of ["region","game_id","kind"]){
    const f=fixtures();
    f.local.catalog_matches[0][field]=field==="region"?"CN-S":field==="game_id"?"onepiece":"CARD";
    const rows=mod.normalize(f.local,f.events);
    assert.equal(rows[0].image,"",field);
    assert.ok(rows.some(x=>x.imageEvidence==="UNLINKED_LOCAL_PHOTO"));
  }
});
test("other region printing is never cross-linked and one image cannot match two sources",()=>{
  const f=fixtures();
  f.local.source_catalog[0].region="CN-S";
  assert.equal(mod.normalize(f.local,null)[0].image,"");
  const g=fixtures();
  g.local.source_catalog.push({...g.local.source_catalog[0],source_record_id:"cccccccccccccccccccccccccccccccc"});
  g.local.catalog_matches.push({...g.local.catalog_matches[0],source_record_id:"cccccccccccccccccccccccccccccccc"});
  assert.equal(mod.normalize(g.local,null).filter(x=>x.imageEvidence==="CODE_MATCH").length,0);
  assert.equal(mod.normalize(g.local,null).filter(x=>x.imageEvidence==="UNLINKED_LOCAL_PHOTO").length,1);
});
test("local image IDs and external URL restrictions reject unsafe values",()=>{
  const f=fixtures();
  f.local.local_catalog[0].image_url="https://attacker.invalid/a.png";
  assert.equal(mod.normalize(f.local,null)[0].image,"");
  assert.equal(mod.imagePath({id:pic,image_url:"/api/local-card-images/file/"+pic+"/more"}),"");
  for(const url of ["http://www.pokemon-card.com/","https://user@www.pokemon-card.com/a",
    "https://pokemon-card.com.attacker.invalid/post","javascript:alert(1)",
    "https://127.0.0.1/test"]){
    assert.equal(mod.safeLink(url),"",url);
  }
});
test("unverified social candidates do not acquire official image or source status",()=>{
  const f=fixtures();
  f.events.items.push({game:"나루토 카드",region:"KR",category:"event",name_ko:"팬 게시물",
    source_grade:"social",source:"https://www.pokemon-card.com/info/005397.html"});
  const e=mod.normalize(null,f.events).at(-1);
  assert.equal(e.source,"");
  assert.equal(e.image,"");
  assert.match(e.sourceState,/재확인|검증/);
});
test("all-country CN unified filter and card BOX event tabs work",()=>{
  const f=fixtures(),rows=mod.normalize(f.local,f.events);
  assert.equal(mod.filterRows(rows,{country:"CN"}).length,1);
  assert.equal(mod.filterRows(rows,{country:"JP",group:"event"}).length,1);
  assert.equal(mod.filterRows(rows,{group:"card"}).length,0);
  assert.equal(mod.filterRows(rows,{group:"box",game:"pokemon",search:"Anniversary"}).length,1);
  assert.equal(mod.filterRows(rows,{group:"event",search:"콜라보"}).length,1);
});
test("duplicate canonical event records are shown once",()=>{
  const f=fixtures();
  f.events.items.push({...f.events.items[0]});
  assert.equal(mod.normalize(null,f.events).length,1);
});
test("no trusted data means empty board, never fabricated cards",()=>{
  assert.deepEqual(mod.normalize({},{}),[]);
  assert.deepEqual(mod.normalize(null,null),[]);
});
test("CN event with unspecified printing remains CN, never becomes simplified",()=>{
  const f=fixtures();
  f.events.items.push({game:"원피스 카드",region:"CN",category:"event",
    name_ko:"중국 행사 판본 미확인",source_grade:"social",source:"https://www.pokemon-card.com/"});
  const rows=mod.normalize(null,f.events);
  const event=rows.find(x=>x.name==="중국 행사 판본 미확인");
  assert.equal(event.region,"CN");
  assert.equal(mod.filterRows(rows,{country:"CN"}).length,1);
  assert.equal(event.image,"");
});
test("duplicate image or catalog identifiers are quarantined from automatic linkage",()=>{
  const f=fixtures();
  f.local.local_catalog.push({...f.local.local_catalog[0],name:"Different printing"});
  assert.equal(mod.normalize(f.local,null).filter(x=>x.image).length,0);
  const g=fixtures();
  g.local.source_catalog.push({...g.local.source_catalog[0],name:"Different BOX"});
  assert.equal(mod.normalize(g.local,null).filter(x=>x.imageEvidence==="CODE_MATCH").length,0);
});
test("review route obeys self-only CSP and never uses direct DOM HTML injection",()=>{
  const html=fs.readFileSync(path.join(ROOT,"docs/tablet/v676/tablet_unified_dashboard_v676.html"),"utf8");
  const js=fs.readFileSync(path.join(ROOT,"docs/tablet/v676/tablet_unified_dashboard_v676.js"),"utf8");
  assert.match(html,/script-src 'self';/);
  assert.match(html,/img-src 'self'; connect-src 'self'/);
  assert.match(html,/href="\.\.\/\.\.\/\.\.\/index\.html"/);
  assert.doesNotMatch(js,/\.innerHTML\s*=|\.insertAdjacentHTML\s*\(/);
  assert.doesNotMatch(js,/localStorage|sessionStorage|fetch\(.+method:\s*["']POST/);
  assert.match(html,/tablet_unified_dashboard_v676\.css/);
  assert.match(html,/tablet_unified_dashboard_v676\.js/);
});


test("the reviewed UI reads the actual v46 /catalog-links route, never the v1 album-only route",()=>{
  const js=fs.readFileSync(path.join(ROOT,"docs/tablet/v676/tablet_unified_dashboard_v676.js"),"utf8");
  assert.match(js,/fetchJSON\("\/api\/local-card-images\/catalog-links"\)/);
  assert.doesNotMatch(js,/fetchJSON\("\/api\/local-card-images"\)/);
});
test("a source match cannot override local image evidence or linked-source identity",()=>{
  for(const edit of [
    r=>{r.local_catalog[0].identity_verification="UNLINKED";},
    r=>{r.local_catalog[0].linked_to_existing_catalog=false;},
    r=>{r.local_catalog[0].linked_source_record_id="c".repeat(32);},
    r=>{r.catalog_matches[0].image_url="/api/local-card-images/file/"+"d".repeat(32);},
    r=>{r.catalog_matches[0].catalog_kind="CARD";},
    r=>{r.catalog_matches.push({...r.catalog_matches[0]});},
  ]){
    const sample=fixtures();edit(sample.local);
    const rows=mod.normalize(sample.local,null);
    assert.equal(rows.filter(x=>x.imageEvidence==="CODE_MATCH").length,0);
  }
});
