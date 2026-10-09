#!/usr/bin/env node
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const full=fs.readFileSync("tcg_market_expanded_v487.js","utf8");
const first=full.slice(0,full.indexOf("/* V505: low-cost"));
assert.ok(first.includes("records.every(freePanelOnlyMutation)"));
function verify(hasFrame){
  let observer, linkScans=0, dateScans=0, blocked=0, replacements=0;
  const frames=[],fallback=[];
  let raw="https://kream.co.kr/products/123";
  const tile={dataset:{}};
  const date={textContent:"자료일 2020-01-01",dataset:{},
    closest(){return tile;}};
  const link={href:"",getAttribute(){return raw;},replaceWith(span){
    assert.equal(span.textContent,"출처 URL 확인 필요");
    replacements++;raw="";
  }};
  const panelNode={nodeType:1,closest(selector){
    return selector==="#tcgFreeFallbackV550Content" ? this : null;
  }};
  const panelText={nodeType:3,parentElement:panelNode};
  const externalNode={nodeType:1,closest(){return null;}};
  const events={};
  const home={contains(node){return node===link;},
    querySelector(){return null;},
    addEventListener(name,handler){events[name]=handler;},
    querySelectorAll(selector){
      if(selector===".tcg-market-tile-actions a"){
        linkScans++;
        return raw?[link]:[];
      }
      if(selector===".tcg-market-tile-date"){
        dateScans++;
        return [date];
      }
      return [];
    }
  };
  const doc={getElementById(name){return name==="tcgMarketHome"?home:null;},
    createElement(){return {className:"",textContent:""};},
    addEventListener(){},visibilityState:"visible"};
  const ctx={document:doc,window:{addEventListener(){}},URL,Date,setInterval(){},
    setTimeout(fn,ms){assert.equal(ms,16);fallback.push(fn);},
    MutationObserver:class{constructor(fn){observer=fn;}observe(){}}
  };
  if(hasFrame)ctx.requestAnimationFrame=fn=>frames.push(fn);
  vm.runInNewContext(first,ctx,{timeout:1500});
  assert.equal(linkScans,1,"initial verification must be synchronous");
  assert.equal(dateScans,1);
  assert.equal(date.dataset.dateStatus,"expired");
  for(let i=0;i<200;i++)observer([{target:panelNode}]);
  for(let i=0;i<100;i++)observer([{target:panelText}]);
  const queue=hasFrame?frames:fallback;
  assert.equal(queue.length,0,"300 panel mutations cannot schedule home scans");
  assert.equal(linkScans,1);
  raw="https://kream.co.kr.evil.invalid/forged";
  // Panel-only churn does not compromise the immediate market-tile click guard.
  events.click({target:{closest(){return link;}},
    preventDefault(){blocked++;},stopImmediatePropagation(){}});
  assert.equal(blocked,1);
  observer([{target:panelNode},{target:externalNode}]);
  assert.equal(queue.length,1,"mixed batch must not hide outside mutation");
  queue.shift()();
  assert.equal(linkScans,2);
  assert.equal(dateScans,2);
  assert.equal(replacements,1,"invalid card link must still be removed");
  for(let i=0;i<60;i++)observer([{target:externalNode}]);
  assert.equal(queue.length,1,"outside redraws still coalesce in a frame");
  queue.shift()();
  assert.equal(linkScans,3);
  // Unknown targets remain fail-closed instead of being silently ignored.
  observer([{target:null}]);
  assert.equal(queue.length,1);
  queue.shift()();
  assert.equal(linkScans,4);
}
verify(true);
verify(false);
console.log("PASS V561: ignore 300 internal panel mutations; preserve card-link security");
