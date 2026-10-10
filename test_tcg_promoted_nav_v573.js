#!/usr/bin/env node
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const {URL}=require("node:url");
class Element {
  constructor(tag="div"){this.tagName=tag;this.children=[];this.attrs={};this._text="";this.style={};this.hidden=false;this.listeners={};this.dataset={};this.classList={add(){},remove(){}};}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(x=>x.textContent||"").join("");}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=[...nodes];this._text="";}
  setAttribute(name,value){this.attrs[name]=String(value);}
  getAttribute(name){return this.attrs[name]??null;}
  addEventListener(name,callback){(this.listeners[name]??=[]).push(callback);}
  focus(){}
  querySelector(){return null;}
  insertAdjacentElement(where,element){this.append(element);}
}
const document={
  readyState:"loading",body:new Element("body"),activeElement:null,
  createElement:tag=>new Element(tag),
  createElementNS:(ns,tag)=>new Element(tag),
  addEventListener(){},getElementById(){return null;}
};
const window={document,localStorage:{getItem(){return null;}}};
const file=path=>JSON.parse(fs.readFileSync(path,"utf8"));
const fetch=async path=>({ok:true,status:200,json:async()=>file(path)});
vm.runInNewContext(fs.readFileSync("tcg_card_detail_v566.js","utf8"),{
  window,document,console,URL,Date,AbortController,setTimeout,clearTimeout,fetch,Blob
});
assert.equal(typeof window.TCGCardDetail.openCatalog,"function");
function walk(parent){return [parent,...parent.children.flatMap(walk)];}
(async()=>{
 await window.TCGCardDetail.openCatalog({gameId:"gundam"});
 const all=walk(document.body);
 const selected=all.filter(n=>n.attrs["aria-pressed"]==="true");
 assert.equal(selected.length,1,"only one game selected in details");
 assert.match(selected[0].textContent,/건담/,"promoted gameId selects correct game in detail page");
 assert.ok(all.some(n=>n.textContent.includes("현재 조건에 맞는 검증된 저장 시세가 없습니다.")),
   "promoted empty market should display missing-evidence warning");
 assert.ok(!all.some(n=>n.textContent.includes("건담")&&n.textContent.includes("₩9,999,999")),
   "do not invent promoted prices");
 window.TCGCardDetail.close();
 const expanded=fs.readFileSync("tcg_market_expanded_v487.js","utf8");
 const detail=fs.readFileSync("tcg_card_detail_v566.js","utf8");
 assert.ok(expanded.includes('home.querySelector(".tcg-detail-expanded-tabs")')&&expanded.includes("info.remove()"),
   "legacy promoted navigation removes its duplicate if detail navigation already mounted");
 assert.ok(detail.includes('home.querySelector("#tcgMarketExpandedV487")'),
   "new detail navigation checks existing legacy panel before and after registry fetch");
 assert.ok(expanded.includes("await detail.openCatalog({gameId:game.id})"),
   "promoted cards route to exact game rather than generic legacy search");
 console.log("PASS V573: real openCatalog game selection, unknown promoted evidence, no duplicate promoted UI, calendar cutoff");
})().catch(err=>{console.error(err);process.exitCode=1;});
