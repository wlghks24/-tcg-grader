"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const script=fs.readFileSync(path.resolve(__dirname,"../tablet_event_refresh_20261123.js"),"utf8");
let passed=0;
const result=(changes={})=>({ok:true,results:[{file:"promo_events.json",ok:true,...changes}]});
const started={ok:true,accepted:true,job_id:"job-1",job:{id:"job-1"}};
const completed=(report=result())=>({ok:true,job:{id:"job-1",state:"completed",report}});
function fixture(replies) {
  const calls=[],timers=new Map(),messages=[],listeners={};let clock=0,next=0,reloads=0;
  const button={dataset:{},disabled:false,addEventListener:(name,fn)=>{listeners[name]=fn;}};
  const status={set textContent(text){messages.push(text);},get textContent(){return messages.at(-1)||"";}};
  const location={href:"http://127.0.0.1:8765/index.html?pane=events&event_region=KR&event_query=골드",reload:()=>{reloads++;}};
  const fetch=async(url,options)=>{
    calls.push({url,options});
    const reply=typeof replies==="function"?replies(calls.length,url):replies.shift();
    if (reply instanceof Error) throw reply;
    if (reply==="HANG") return new Promise(()=>{});
    if (reply==="BODY_HANG") return {ok:true,json:()=>new Promise(()=>{})};
    if (reply==="HTTP") return {ok:false,status:503};
    return {ok:true,json:async()=>reply};
  };
  vm.runInNewContext(script,{document:{readyState:"complete",getElementById:id=>id==="tcg-event-refresh"?button:status},fetch,location,AbortController,Date:{now:()=>clock},setTimeout:(fn,ms)=>{const id=++next;timers.set(id,{fn,time:clock+ms});return id;},clearTimeout:id=>timers.delete(id)});
  async function settle(promise) {
    let done=false,error;promise.then(()=>{done=true;},e=>{error=e;done=true;});
    for(let steps=0;steps<2000&&!done;steps++) {
      for(let i=0;i<30;i++)await Promise.resolve();
      if(done)break;
      const first=[...timers.entries()].sort((a,b)=>a[1].time-b[1].time)[0];
      if(first){timers.delete(first[0]);clock=first[1].time;first[1].fn();}
    }
    assert(done,"bounded async task finished");if(error)throw error;
    assert.equal(timers.size,0,"request timers are cleaned up");
  }
  return {calls,messages,button,status,location,click:()=>listeners.click(),settle,reloads:()=>reloads};
}
async function test(label,run){await run();passed++;console.log("PASS "+label);}
(async()=>{
  await test("GET mounting never starts collection",async()=>{const f=fixture([]);assert.equal(f.calls.length,0);assert.equal(f.button.disabled,false);});
  await test("same job queued and running then completed reloads current filter URL",async()=>{
    const f=fixture([started,{ok:true,job:{id:"job-1",state:"queued",current:0,total:8}},{ok:true,job:{id:"job-1",state:"running",current:5,total:8}},completed()]);
    const before=f.location.href;await f.settle(f.click());assert.equal(f.reloads(),1);assert.equal(f.location.href,before);
    assert.equal(f.calls[0].url,"/api/run-auto-update");assert.equal(f.calls[0].options.method,"POST");assert.equal(f.calls[0].options.body,"{}");
    assert(f.calls.slice(1).every(r=>r.url==="/api/update-job"&&r.options.method==="GET"));
    assert(f.messages.some(s=>s.includes("대기")&&s.includes("0/8")));assert(f.messages.some(s=>s.includes("진행 중")&&s.includes("5/8")));
    assert.match(f.status.textContent,/단계가 종료/);assert.equal(f.button.disabled,false);
  });
  for(const [label,response] of [["failed",{ok:true,job:{id:"job-1",state:"failed"}}],["different job",{ok:true,job:{id:"job-2",state:"completed",report:result()}}],["malformed",{ok:true,job:{id:"job-1",state:"bogus"}}],["missing report",{ok:true,job:{id:"job-1",state:"completed"}}]]) {
    await test(label+" preserves existing list without reload",async()=>{const f=fixture([started,response]);await f.settle(f.click());assert.equal(f.reloads(),0);assert.match(f.status.textContent,/기존 목록과 필터를 유지/);assert.equal(f.button.disabled,false);});
  }
  for(const [label,response] of [["HTTP","HTTP"],["network",Error("offline")],["bad id",{ok:true,accepted:true,job_id:"../../bad"}],["rejected",{ok:false}],["request timeout","HANG"],["JSON body timeout","BODY_HANG"]]) {
    await test(label+" allows explicit retry and never fabricates completion",async()=>{const f=fixture([response]);await f.settle(f.click());assert.equal(f.calls.length,1);assert.equal(f.reloads(),0);assert.match(f.status.textContent,/완료를 확인하지 못/);assert.equal(f.button.disabled,false);});
  }
  for(const row of [{ok:false},{collection_errors:["fetch failed"]},{remaining_collection_errors:["stale"]},{recovered_after_retry:true},{error:"failed"}]) {
    await test("partial event result keeps warning and existing screen until manual reload",async()=>{const f=fixture([started,completed(result(row))]);await f.settle(f.click());assert.equal(f.reloads(),0);assert.match(f.status.textContent,/최신성 미확인/);assert.match(f.status.textContent,/직접 새로고침/);assert(!f.status.textContent.includes("갱신 성공"));});
  }
  await test("malformed event errors do not reload",async()=>{const f=fixture([started,completed(result({collection_errors:"error"}))]);await f.settle(f.click());assert.equal(f.reloads(),0);});
  await test("duplicate clicks join the single local operation",async()=>{const f=fixture([started,completed()]);const first=f.click();assert.equal(f.button.disabled,true);const second=f.click();await f.settle(Promise.all([first,second]));assert.equal(f.calls.filter(c=>c.options.method==="POST").length,1);assert.equal(f.reloads(),1);});
  await test("failed request can be retried by another user click",async()=>{const f=fixture([Error("offline"),started,completed()]);await f.settle(f.click());await f.settle(f.click());assert.equal(f.calls.filter(c=>c.options.method==="POST").length,2);assert.equal(f.reloads(),1);});
  await test("poll budget stops repeated running state without new collection",async()=>{const f=fixture(n=>n===1?started:{ok:true,job:{id:"job-1",state:"running"}});await f.settle(f.click());assert.equal(f.calls.length,61);assert.equal(f.reloads(),0);assert.match(f.status.textContent,/시간 초과/);assert.match(f.status.textContent,/서버 수집 작업을 중단한 것은 아닙니다/);});
  console.log("Event refresh DOM: "+passed+" tests passed");
})().catch(error=>{console.error(error);process.exitCode=1;});
