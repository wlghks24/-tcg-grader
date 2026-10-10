#!/usr/bin/env node
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const collection=fs.readFileSync("tcg_local_collection_v505.js","utf8");
const market=fs.readFileSync("tcg_card_detail_v566.js","utf8");
const photo=fs.readFileSync("tcg_photo_result_v567.js","utf8");
const css=fs.readFileSync("tcg_card_detail_v566.css","utf8");
const start=collection.indexOf('  function prepareMarketEntry(source){');
const stop=collection.indexOf('  window.TCGLocalCollectionV505=',start);
assert.ok(start>=0&&stop>start,"authoritative V505 handoff must exist");
const implementation=collection.slice(start,stop);
const blank=()=>({value:"",disabled:false});
const globals={
  blocked:false,
  status:{textContent:""},
  GAMES:["Pokémon","ONE PIECE","NARUTO","GUNDAM CARD GAME","Disney Lorcana"],
  game:blank(),region:blank(),asset:blank(),grade:blank(),name:blank(),number:blank(),qty:blank(),paid:blank(),value:blank(),
  panel:{open:false,scrollIntoView(){}},add:blank(),
  window:{confirm(){return true;},TCGFeatureCategoryNav:{closeFeatureView(){}}},
  Event:class Event{constructor(type,args){this.type=type;this.bubbles=args.bubbles}},
  setTimeout(callback){/* No implicit writes, scrolling is mocked. */}
};
let assetChange=0;
globals.asset.dispatchEvent=event=>{assert.equal(event.type,"change");assetChange++;globals.grade.disabled=globals.asset.value==="BOX";};
vm.runInNewContext(implementation+"\nthis.marketPrefill=prepareMarketEntry;",globals,{timeout:1000});
const prepare=globals.marketPrefill;
assert.equal(typeof prepare,"function");
assert.equal(prepare({game:"Pokémon",region:"JP",asset:"HIT",name:"피카츄",cardNumber:"025/060"}),true);
assert.equal(globals.game.value,"Pokémon");
assert.equal(globals.region.value,"JP");
assert.equal(globals.asset.value,"CARD");
assert.equal(globals.name.value,"피카츄");
assert.equal(globals.number.value,"025/060");
assert.equal(globals.grade.value,"미감정");
assert.equal(globals.paid.value,"");
assert.equal(globals.value.value,"");
assert.equal(globals.qty.value,"1");
assert.equal(globals.panel.open,true);
assert.ok(globals.status.textContent.includes("자동 저장하지"));
assert.equal(prepare({game:"GUNDAM CARD GAME",region:"KR",asset:"BOX",name:"Verified box",cardNumber:""}),true);
assert.equal(globals.name.value,"Verified box");
assert.equal(globals.asset.value,"BOX");
assert.equal(globals.grade.disabled,true);
assert.equal(prepare({game:"Disney Lorcana",region:"US",asset:"HIT",name:"Unverified",cardNumber:""}),true);
assert.equal(globals.name.value,"","a card name must not auto-fill without its number");
assert.equal(globals.number.value,"");
assert.ok(globals.status.textContent.includes("카드번호가 모두 확인"));
const before=globals.name.value;
assert.equal(prepare({game:"Watch Game",region:"KR",asset:"HIT",name:"X",cardNumber:"123"}),false);
assert.equal(globals.name.value,before);
assert.equal(prepare({game:"Pokémon",region:"UNKNOWN",asset:"HIT",name:"X",cardNumber:"123"}),false);
assert.equal(prepare({game:"Pokémon",region:"KR",asset:"PSA 10",name:"X",cardNumber:"123"}),false);
assert.equal(prepare({game:"Pokémon",region:"KR",asset:"HIT",name:"X".repeat(91),cardNumber:"12"}),false);
globals.blocked=true;
assert.equal(prepare({game:"Pokémon",region:"KR",asset:"HIT",name:"Pika",cardNumber:"12"}),false);
assert.ok(globals.status.textContent.includes("차단"));
assert.equal(assetChange,3);
globals.blocked=false;
// Existing unsaved draft is never overwritten without a user decision.
globals.name.value="Draft to keep";globals.number.value="8888";
globals.paid.value="2500";globals.value.value="8000";
globals.qty.value="5";
const draft={name:globals.name.value,number:globals.number.value,
  paid:globals.paid.value,value:globals.value.value,qty:globals.qty.value};
globals.window.confirm=()=>false;
assert.equal(prepare({game:"Pokémon",region:"JP",asset:"HIT",name:"Changed",cardNumber:"123"}),false);
for(const [key,val] of Object.entries(draft))assert.equal(globals[key].value,val);
assert.equal(assetChange,3,"declined replacement must not trigger change");
globals.window.confirm=()=>true;
assert.equal(prepare({game:"Pokémon",region:"JP",asset:"HIT",name:"Changed",cardNumber:"123"}),true);
assert.equal(globals.name.value,"Changed");
assert.equal(globals.paid.value,"");
assert.equal(globals.value.value,"");
assert.equal(globals.qty.value,"1");
assert.equal(assetChange,4);
assert.ok(!collection.includes('EN:"US"'),"English language must not be silently mapped to US marketplace");
assert.ok(market.includes('if(ok)close(false)'),"modal must not recapture focus");

assert.ok(!implementation.includes("setItem(")&&!implementation.includes("persist("),"no automatic holdings write");
assert.ok(market.includes("TCGLocalCollectionV505"));
assert.ok(market.includes("prepareMarketEntry"));
assert.ok(!market.includes("root.localStorage.setItem(STORE_KEY"),"do not revive duplicate V566 holdings");
assert.ok(market.includes("이전 임시 기록 백업(JSON)"));
assert.ok(market.includes("original.insertAdjacentElement("));
assert.ok(market.includes('g.state==="promoted"'));
assert.ok(market.includes("=>void open({gameId:g.id})"));
assert.ok(css.includes(".tcg-detail-expanded-tabs"));
assert.ok(css.includes("min-height:48px!important"));
for(const metric of ["scoreCenter","scoreCorner","scoreEdge","scoreSurface","simpleGradeConfidence"])assert.ok(photo.includes('"'+metric+'"'));
const names=JSON.parse(fs.readFileSync("tcg_game_registry.json","utf8")).games;
assert.equal(names.filter(g=>g.state==="promoted"&&g.capabilities?.market===true).length,9);
console.log("PASS V569: single holdings source, manual confirmation, legacy backup, promoted-game tabs, score-update observers");
