#!/usr/bin/env node
"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm");
const src=fs.readFileSync("tcg_local_collection_v505.js","utf8");
const detail=fs.readFileSync("tcg_card_detail_v566.js","utf8");
const photo=fs.readFileSync("tcg_photo_result_v567.js","utf8");
const a=src.indexOf("  function prefillFromMarket(input) {");
const z=src.indexOf("  window.TCGLocalCollectionV505=Object.freeze({prefillFromMarket});",a);
assert.ok(a>0&&z>a,"test actual published v505 bridge");
const core=src.slice(a,z);
function trial(input,changes={}){
  const calls=[];
  const state={
    blocked:false,GAMES:["Pokémon","ONE PIECE","NARUTO","GUNDAM CARD GAME","Disney Lorcana"],
    game:{value:"Pokémon"},region:{value:"KR"},asset:{value:"CARD",dispatchEvent:()=>calls.push("changed")},
    grade:{value:"미감정"},name:{value:""},number:{value:""},qty:{value:"1"},
    paid:{value:""},value:{value:""},panel:{open:false,scrollIntoView:()=>calls.push("scrolled")},
    status:{textContent:""},window:{confirm:()=>true,TCGFeatureCategoryNav:{closeFeatureView:()=>calls.push("closed")}},
    Event:class Event{},Number,Array,
    input
  };
  state.paid.focus=()=>calls.push("focused");
  Object.assign(state,changes);
  const result=vm.runInNewContext(core+"\nprefillFromMarket(input)",state);
  return {result:JSON.parse(JSON.stringify(result)),state,calls};
}
const good={game:"GUNDAM CARD GAME",region:"JP",asset:"CARD",name:"Sample Confirmed Card",
  number:"GD01-001",quantity:2};
const x=trial(good);
assert.equal(x.result.ok,true);
assert.equal(x.state.game.value,"GUNDAM CARD GAME");
assert.equal(x.state.region.value,"JP");
assert.equal(x.state.number.value,"GD01-001");
assert.equal(x.state.paid.value,"");
assert.equal(x.state.value.value,"");
assert.equal(x.state.grade.value,"미감정");
assert.equal(x.state.panel.open,true);
assert.deepEqual(x.calls,["changed","closed","scrolled","focused"]);
assert.equal(trial({...good,region:"EN"}).result.ok,false,"language cannot be a market region");
assert.equal(trial({...good,game:"WATCH"}).result.ok,false);
assert.equal(trial({...good,quantity:0}).result.ok,false);
assert.equal(trial({...good,name:""}).result.ok,false);
assert.equal(trial({...good,number:"A".repeat(37)}).result.ok,false);
assert.equal(trial(good,{blocked:true}).result.ok,false);
const refused=trial(good,{name:{value:"editing existing work"},window:{confirm:()=>false}});
assert.equal(refused.result.ok,false);assert.equal(refused.state.name.value,"editing existing work");
assert.ok(!src.includes('EN:"US"'),"do not promote English-language cards to US region silently");
assert.ok(detail.includes("api.prefillFromMarket(proposal)"));
assert.ok(!detail.includes("root.localStorage.setItem("),"no second holdings store");
assert.ok(detail.includes("root.localStorage?.getItem(STORE_KEY)"),"old local records should survive for manual recovery");
assert.ok(photo.includes("api.prefillFromMarket({game:"));
assert.ok(!photo.includes("root.localStorage.setItem("));
console.log("PASS V569: same collection store, valid manual prefill, no auto-save, draft protection, evidence safe");
