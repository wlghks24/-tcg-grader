#!/usr/bin/env node
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const full=fs.readFileSync("tcg_market_expanded_v487.js","utf8");
const first=full.slice(0,full.indexOf("/* V505: low-cost"));
assert.ok(first.includes("new MutationObserver(protectMarketHomeLinks)"));
function verify(hasFrame) {
  let observer, links=0, dates=0, bad=0, prevented=0;
  const frames=[],fallback=[];
  let url="https://kream.co.kr/products/123";
  const tile={dataset:{}};
  const link={href:"",getAttribute(){return url;},replaceWith(span){
    assert.equal(span.textContent,"출처 URL 확인 필요");bad++;url="";
  }};
  const date={textContent:"자료일 2020-01-01",dataset:{},closest(){return tile;}};
  const listeners={};
  const home={
    contains(target){return target===link;},
    querySelector(){return null;},
    addEventListener(key,fn){listeners[key]=fn;},
    querySelectorAll(sel){
      if(sel===".tcg-market-tile-actions a"){links++;return url?[link]:[];}
      if(sel===".tcg-market-tile-date"){dates++;return [date];}
      return [];
    }
  };
  const document={
    getElementById(id){return id==="tcgMarketHome"?home:null;},
    createElement(){return {className:"",textContent:""};},
    addEventListener(){},visibilityState:"visible"
  };
  const context={document,window:{addEventListener(){}},MutationObserver:class{
    constructor(cb){observer=cb;}observe(){}
  },URL,Date,setInterval(){},setTimeout(fn,ms){assert.equal(ms,16);fallback.push(fn);}};
  if(hasFrame)context.requestAnimationFrame=fn=>frames.push(fn);
  vm.runInNewContext(first,context,{timeout:1500});
  assert.equal(links,1,"initial guard synchronous");
  assert.equal(dates,1);
  assert.equal(date.dataset.dateStatus,"expired");
  assert.equal(link.href,"https://kream.co.kr/products/123");
  url="https://kream.co.kr.evil.test/price";
  for(let i=0;i<200;i++)observer([]);
  assert.equal(links,1,"no O(N) rescans per mutation");
  const queue=hasFrame?frames:fallback;
  assert.equal(queue.length,1,"200 mutations => 1 recheck frame");
  listeners.click({target:{closest(){return link;}},preventDefault(){prevented++;},
    stopImmediatePropagation(){}});
  assert.equal(prevented,1,"unsafe link blocked before frame");
  queue.shift()();
  assert.equal(links,2);
  assert.equal(dates,2);
  assert.equal(bad,1,"unsafe link visibly replaced");
  for(let i=0;i<80;i++)observer([]);
  assert.equal(queue.length,1);
  queue.shift()();
  assert.equal(links,3);
}
verify(true);
verify(false);
console.log("PASS: V559 DOM batching, immediate security and no-rAF fallback");
