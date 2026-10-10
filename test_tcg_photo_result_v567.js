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
assert.equal(api.strictMarketIdentity({...correct,region:"US"},{...p,region:"US"}),true,"explicitly selected US market is supported");
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
 assert.ok(!source.includes("createObjectURL("),"untrusted files must be decoded and rasterized before preview");
 assert.ok(source.includes('canvas.toDataURL("image/png")'));
 assert.ok(source.includes("new Uint8Array(await selected.slice(0,12).arrayBuffer())"));


 assert.ok(source.includes("시세 국가 직접 확인"),"market region must be explicitly selectable");
 assert.ok(source.includes("confirmedMarketRegion"),"language and market region must be separate");
 assert.ok(source.includes("getPhotoMarketEvidence"),"photo results must request real evidence data");
 assert.ok(source.includes("priceEvidence.variantConfirmed"),"PSA result cells must require complete edition matching");
 assert.ok(source.includes("공개 참고자료"),"separate dated reference/listing prices from sold prices");
 assert.ok(source.includes("세트명 · 판매 근거 확인 시 필요"),"set identity confirmation must be visible");
 assert.ok(source.includes("variantDetailsOpen"),"keep advanced edition details open during redraw");
 assert.ok(source.includes("priceLoading"),"loading and unavailable states must be explicit");
 assert.ok(source.includes("safeSourceUrl"),"source link must use the market allowlist");
 assert.ok(!source.includes("marketEvidence.price_krw"),"never use unverified bare prices");
 assert.ok(source.includes("PSA/BGS/CGC/TAG/BRG 공식 등급이 아닙니다"));
 assert.ok(!source.includes("PSA 10: 90%"));
 console.log("PASS V567: photo status, registry breadth, strict binding, no fake PSA, published runtime assets");
})().catch(e=>{console.error(e);process.exitCode=1});

// V572: DOM lifecycle regression (real render path, not a string-only check).
function firstPaintScenario(initiallyVisible) {
 class FakeElement {
   constructor(tag){this.tagName=tag;this.children=[];this.style={};this.hidden=false;this.dataset={};this.textContent='';this.value='';this.attributes={};}
   append(...children){this.children.push(...children);}
   insertBefore(child){this.children.unshift(child);}
   replaceChildren(...children){this.children=children;}
   addEventListener(){}
   setAttribute(key,value){this.attributes[key]=value;}
   getAttribute(key){return this.attributes[key];}
   querySelector(){return null;}
 }
 const nodes={};
 for(const id of ['simpleGradeResult','simpleGradeNumber','simpleGradeV32','identityCardName','identityCardNumber','identityRegion','simplePokemonGeneration','pokemonGenerationTitle','pokemonGenerationMeta','simpleGradeConfidence','scoreCenter','scoreCorner','scoreEdge','scoreSurface']) nodes[id]=new FakeElement('div');
 nodes.simpleGradeResult.style.display=initiallyVisible?'block':'none';
 nodes.simpleGradeNumber.textContent='9';
 nodes.identityCardName.value='블래키ex';nodes.identityCardNumber.value='SV8a-217';nodes.identityRegion.value='JP';
 let visibilityObserver=null;
 class FakeObserver {
   constructor(callback){this.callback=callback;}
   observe(target,config){if(target===nodes.simpleGradeResult && config.attributeFilter?.includes('style'))visibilityObserver=this;}
 }
 const doc={readyState:'complete',createElement:tag=>new FakeElement(tag),getElementById:id=>nodes[id]||null,
   querySelector:selector=>selector.includes('.simple-game.active')?{dataset:{simpleGame:'pokemon'}}:null};
 const root={document:doc,MutationObserver:FakeObserver,fetch:async()=>({ok:true,json:async()=>registry})};
 vm.runInNewContext(source,{window:root,console});
 const panel=nodes.simpleGradeResult.children[0];
 assert.equal(panel?.id,'tcgPhotoResultV567');
 assert.equal(panel.hidden,!initiallyVisible,'visible grades must paint, hidden grades must stay hidden');
 if(initiallyVisible)assert.ok(panel.children.length>=5,'render the existing grade report on first paint');
 assert.ok(visibilityObserver,'observe source grade panel visibility');
 nodes.simpleGradeResult.style.display='none';visibilityObserver.callback();
 assert.equal(panel.hidden,true,'hide with source grade view');
 nodes.simpleGradeResult.style.display='block';visibilityObserver.callback();
 assert.equal(panel.hidden,false,'reopen without grade-number mutation');
 assert.ok(panel.children.length>=5);
}
firstPaintScenario(true);
firstPaintScenario(false);
console.log('PASS V572: pre-rendered grade and hide/show lifecycle without grade-number mutation');


// V574: exercise real retry buttons with a minimal DOM (not a source-string check).
async function transientRecoveryScenario() {
 class FakeElement {
   constructor(tag) {
     this.tagName=tag;this.children=[];this.parent=null;this.style={};this.hidden=false;
     this.dataset={};this.textContent="";this.value="";this.attributes={};this.listeners={};
   }
   append(...children) {for(const child of children){if(child&&typeof child==="object")child.parent=this;this.children.push(child);} }
   insertBefore(child) {child.parent=this;this.children.unshift(child);}
   replaceChildren(...children) {this.children=[];this.append(...children);}
   addEventListener(type,listener) {this.listeners[type]=listener;}
   setAttribute(name,value) {this.attributes[name]=value;}
   getAttribute(name) {return this.attributes[name];}
   querySelector(selector) {
     if(selector===".simple-game-grid")return null;
     if(selector===".tcg-photo-expanded")return find(this,n=>n.className==="tcg-photo-expanded");
     return null;
   }
   remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);}
 }
 function find(node,pred) {
   if(!node||typeof node!=="object")return null;
   if(pred(node))return node;
   for(const child of node.children||[]) {const found=find(child,pred);if(found)return found;}
   return null;
 }
 function click(root,label) {
   const target=find(root,n=>n.tagName==="button"&&n.textContent===label);
   assert.ok(target,"expected real button: "+label);
   assert.equal(typeof target.listeners.click,"function");
   target.listeners.click();
 }
 const tick=()=>new Promise(resolve=>setImmediate(resolve));
 const nodes={};
 for(const id of ["simpleGradeResult","simpleGradeNumber","simpleGradeV32",
   "identityCardName","identityCardNumber","identityRegion","simplePokemonGeneration",
   "pokemonGenerationTitle","pokemonGenerationMeta","simpleGradeConfidence",
   "scoreCenter","scoreCorner","scoreEdge","scoreSurface"])nodes[id]=new FakeElement("div");
 nodes.simpleGradeResult.style.display="block";
 nodes.simpleGradeNumber.textContent="9";
 nodes.identityCardName.value="피카츄";
 nodes.identityCardNumber.value="025/165";
 nodes.identityRegion.value="JP";
 let sourceTries=0,registryTries=0;
 const doc={readyState:"complete",
   createElement:tag=>new FakeElement(tag),
   getElementById:id=>nodes[id]||null,
   querySelector:sel=>sel.includes(".simple-game.active")?{dataset:{simpleGame:"pokemon"}}:null};
 const app={document:doc,fetch:async path=>{
   assert.equal(path,"tcg_game_registry.json");
   registryTries++;
   if(registryTries===1)throw Error("temporary registry timeout");
   return {ok:true,json:async()=>registry};
 },TCGCardDetail:{
   getPhotoMarketEvidence:async()=>{
     sourceTries++;
     if(sourceTries===1)throw Error("temporary market timeout");
     return {status:"not_found",reference:null,sales:[],variantConfirmed:false};
   }
 }};
 vm.runInNewContext(source,{window:app,console});
 await tick();await tick();
 const panel=nodes.simpleGradeResult.children[0];
 assert.equal(panel.hidden,false);
 assert.equal(sourceTries,1,"failed market fetch attempts once, no automatic retry loop");
 assert.equal(registryTries,1,"failed registry fetch attempts once, no automatic retry loop");
 const grade=find(panel,n=>n.className==="tcg-photo-rating");
 assert.equal(grade?.textContent,"9 / 10","preserve measured grade through network failures");
 click(panel,"시세 근거 다시 조회");
 await tick();await tick();
 assert.equal(sourceTries,2,"manual retry requests fresh evidence");
 assert.equal(find(panel,n=>n.className==="tcg-photo-rating")?.textContent,"9 / 10");
 assert.ok(!find(panel,n=>n.tagName==="button"&&n.textContent==="시세 근거 다시 조회"),
   "successful retry should hide the retry button");
 click(nodes.simpleGradeV32,"확장 게임 다시 불러오기");
 await tick();await tick();
 assert.equal(registryTries,2,"retry must actually request registry again");
 assert.ok(find(nodes.simpleGradeV32,n=>n.className==="tcg-photo-extended-form"),
   "promoted games should appear after registry recovers");
 assert.ok(!find(nodes.simpleGradeV32,n=>n.tagName==="button"&&n.textContent==="확장 게임 다시 불러오기"),
   "recovering the registry must remove the stale recovery button");
 console.log("PASS V574: market & TCG registry retry buttons recover without losing grade or looping");
}
transientRecoveryScenario().catch(e=>{console.error(e);process.exitCode=1;});
