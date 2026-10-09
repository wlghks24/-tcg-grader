#!/usr/bin/env node
"use strict";
// V560: synthetic tablet DOM regression, no third-party browser or network.
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm");
const full=fs.readFileSync("tcg_market_expanded_v487.js","utf8");
const start=full.lastIndexOf("/* V550: local-only free source handoff.");
assert.ok(start>0);
function run(hasFrame){
  const frames=[],timers=[],events={},nodes=[],fetches=[];
  let game="NARUTO",renders=0;
  const fields={};
  for(const id of ["identityCardName","identityCardNumber","identityRegion","identityMarketKey"])
    fields[id]={id,value:id==="identityRegion"?"KR":""};
  function make(tag){
    const x={tag,style:{},childNodes:[],handlers:{},
      appendChild(v){this.childNodes.push(v);},
      replaceChildren(){this.childNodes=[];renders++;},
      setAttribute(){},
      addEventListener(k,fn){this.handlers[k]=fn;}};
    nodes.push(x);return x;
  }
  const home=make("div");
  home.querySelector=()=>({dataset:{game}});
  const document={
    getElementById(id){return id==="tcgMarketHome"?home:fields[id]||nodes.find(x=>x.id===id)||null;},
    createElement:make,
    addEventListener(k,fn){events[k]=fn;}
  };
  const context={window:{},document,Date,URL,Number,Array,String,encodeURIComponent,
    fetch(url){fetches.push(url);return new Promise(()=>{});},
    setTimeout(fn,ms){assert.equal(ms,16);timers.push(fn);}
  };
  if(hasFrame)context.requestAnimationFrame=fn=>frames.push(fn);
  vm.runInNewContext(full.slice(start),context,{timeout:1500});
  const panel=nodes.find(x=>x.id==="tcgFreeFallbackV550");
  assert.ok(panel);
  panel.open=true;panel.handlers.toggle();
  assert.equal(renders,1,"panel open renders once");
  assert.deepEqual(fetches,["market_prices.json"],"non-Pokémon tab skips large official list");
  for(let i=0;i<200;i++)events.input({target:{id:"otherAppInput"}});
  assert.equal(renders,1,"unrelated inputs never rebuild the panel");
  const queue=hasFrame?frames:timers;
  assert.equal(queue.length,0);
  fields.identityCardName.value="리자몽 ex";
  for(let i=0;i<200;i++)events.input({target:fields.identityCardName});
  assert.equal(queue.length,1,"200 identity events coalesce to one frame");
  assert.equal(renders,1,"typing must not synchronously repaint");
  queue.shift()();assert.equal(renders,2);
  fields.identityCardNumber.value="116/080";
  events.input({target:fields.identityCardNumber});
  events.change({target:fields.identityCardNumber});
  assert.equal(renders,3,"change immediately updates identity");
  queue.shift()();
  assert.equal(renders,3,"pending frame does not repaint unchanged identity");
  game="Pokémon";
  events.click({target:{closest(){return {};}}});
  assert.equal(fetches.filter(x=>x==="purchase_sources.json").length,1,
    "Pokémon official list is lazy, once per panel lifetime");
  for(let i=0;i<100;i++)events.change({target:{id:"irrelevant"}});
  assert.equal(fetches.filter(x=>x==="purchase_sources.json").length,1);
}
run(true);
run(false);
console.log("PASS V560: scoped events, coalesced panel painting, lazy source loading");
