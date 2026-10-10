#!/usr/bin/env node
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const source=fs.readFileSync("tcg_photo_result_v567.js","utf8");
let readyCallback=null;
const fakeDocument={
 readyState:"loading",
 addEventListener:(type,fn)=>{if(type==="DOMContentLoaded")readyCallback=fn;},
 querySelector:()=>null,
 getElementById:()=>null
};
const mockWindow={document:fakeDocument,fetch:async()=>({ok:true,json:async()=>JSON.parse(fs.readFileSync("tcg_game_registry.json","utf8"))})};
vm.runInNewContext(source,{window:mockWindow,console});
const api=mockWindow.TCGPhotoResultV567;
assert.equal(api.version,"v567");
assert.equal(typeof readyCallback,"function");
const p={region:"JP",asset:"HIT",game:{id:"pokemon"},cardName:"Pikachu",cardNumber:"025/165"};
const correct={game:"pokemon",region:"JP",cardName:"Pikachu",cardNumber:"025/165"};
assert.equal(api.strictMarketIdentity(correct,p),true);
for(const wrong of [
 {...p,region:"KR"},
 {...p,asset:"BOX"},
 {...p,game:{id:"naruto"}},
 {...p,cardName:"Charizard"},
 {...p,cardNumber:"25/165"},
 {...p,cardNumber:""},
]){
 assert.equal(api.strictMarketIdentity(correct,wrong),false,"different card/grade/region must not be bound");
}
assert.equal(api.strictMarketIdentity({...correct,region:"EN"},p),false,"English language must not default to US market");
assert.equal(api.strictMarketIdentity({...correct,cardName:""},p),false);
assert.equal(api.strictMarketIdentity(correct,{...p,cardName:""}),false);
(async()=>{
 const games=await api.eligibleGames();
 assert.ok(games.some(g=>g.id==="pokemon"&&g.grading===true));
 assert.ok(games.some(g=>g.canonical==="GUNDAM CARD GAME"&&g.state==="promoted"));
 assert.ok(games.some(g=>g.canonical==="Disney Lorcana"&&g.grading===false));
 assert.ok(games.every(g=>g.state==="core"||g.state==="promoted"));
 const snap=api.snapshot();
 assert.equal(snap.isVisible,false,"never fabricate a grade if photo analysis has not run");
 const html=fs.readFileSync("index.html","utf8");
 assert.ok(html.includes('<script src="tcg_photo_result_v567.js?v=567"></script>'));
 assert.ok(html.includes('<link rel="stylesheet" href="tcg_photo_result_v567.css?v=567">'));
 const rt=fs.readFileSync("tablet_runtime_manifest.py","utf8");
 const sw=fs.readFileSync("sw.js","utf8");
 const server=fs.readFileSync("tcg_updater.py","utf8");
 for(const ext of ["tcg_photo_result_v567.js","tcg_photo_result_v567.css"]){
   assert.ok(sw.includes("'./"+ext+"'"));
   assert.ok(server.includes("'"+ext+"'"));
   assert.ok(rt.includes('"'+ext+'"'));
 }
 assert.ok(source.includes("createElement("));
 assert.ok(!source.includes("innerHTML"));
 assert.ok(source.includes("PSA/BGS/CGC/TAG/BRG 공식 등급이 아닙니다"));
 assert.ok(!source.includes("PSA 10: 90%"));
 console.log("PASS V567: photo status, registry breadth, strict binding, no fake PSA, published runtime assets");
})().catch(e=>{console.error(e);process.exitCode=1});
