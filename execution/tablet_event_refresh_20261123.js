/* User-triggered local collection only; keep stored events on every failure. */
(() => {
  "use strict";
  function boot() {
    const button=document.getElementById("tcg-event-refresh"),status=document.getElementById("tcg-event-refresh-status");
    if (!button || !status || button.dataset.eventRefreshBound) return;
    button.dataset.eventRefreshBound="true";
    let busy=false;
    const validId=id=>typeof id==="string" && /^[A-Za-z0-9_-]{1,128}$/.test(id);
    const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
    async function request(url,options) {
      const controller=new AbortController(); let timer;
      try {
        const payload=await Promise.race([
          (async()=>{
            const response=await fetch(url,{...options,signal:controller.signal,cache:"no-store"});
            if (!response.ok) throw Error("HTTP "+response.status);
            return response.json();
          })(),
          new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(Error("응답 시간 초과"));},10000);})
        ]);
        if (!payload || typeof payload!=="object" || Array.isArray(payload) || payload.ok!==true) throw Error("invalid response");
        return payload;
      } finally { clearTimeout(timer); }
    }
    function eventResult(job) {
      const report=job.report;
      if (!report || typeof report!=="object" || !Array.isArray(report.results)) throw Error("missing report");
      const rows=report.results.filter(row=>row && row.file==="promo_events.json");
      if (rows.length!==1 || typeof rows[0].ok!=="boolean") throw Error("missing event result");
      const row=rows[0];
      for (const key of ["collection_errors","remaining_collection_errors"]) {
        if (row[key]!==undefined && !Array.isArray(row[key])) throw Error("invalid collection result");
      }
      return report.ok!==true || row.ok!==true || Boolean(row.error) || Boolean(row.recovered_after_retry)
        || Boolean(row.collection_errors?.length) || Boolean(row.remaining_collection_errors?.length);
    }
    button.addEventListener("click",async()=>{
      if (busy) return;
      busy=true;button.disabled=true;status.textContent="실제 수집 요청 중 · 기존 목록 유지";
      try {
        const started=await request("/api/run-auto-update",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
        if (started.accepted!==true || !validId(started.job_id) || (started.job && started.job.id!==started.job_id)) throw Error("invalid job id");
        const jobId=started.job_id,deadline=Date.now()+180000;
        for (let polls=0;polls<60 && Date.now()<deadline;polls++) {
          const data=await request("/api/update-job",{method:"GET"});
          const job=data.job;
          if (!job || typeof job!=="object" || job.id!==jobId) throw Error("job mismatch");
          if (job.state==="failed") throw Error("collection failed");
          if (job.state==="completed") {
            const degraded=eventResult(job);
            status.textContent=degraded
              ? "부분 수집 · 최신성 미확인: 행사 수집 오류·이전 자료 유지 가능성이 있습니다. 기존 화면을 유지합니다. 결과를 확인하고 직접 새로고침하세요."
              : "행사 수집 단계가 종료됐습니다. 현재 필터로 저장 목록을 다시 읽습니다. 개별 공식 발표·일정은 출처에서 확인하세요.";
            if (!degraded) { await wait(750); location.reload(); }
            return;
          }
          if (!["queued","running"].includes(job.state)) throw Error("invalid state");
          const progress=Number.isInteger(job.current) && Number.isInteger(job.total) && job.current>=0 && job.total>0 && job.current<=job.total
            ? " · "+job.current+"/"+job.total : "";
          status.textContent="출시·행사 실제 수집 "+(job.state==="queued"?"대기":"진행 중")+progress+" · 기존 목록 유지";
          await wait(2000);
        }
        throw Error("poll timeout");
      } catch (error) {
        const reasons={"invalid response":"서버 응답 형식 오류", "invalid job id":"접수된 작업 ID 확인 불가",
          "job mismatch":"다른 수집 작업으로 변경됨", "collection failed":"수집 작업 실패", "invalid state":"작업 상태 확인 불가",
          "missing report":"수집 보고서 누락", "missing event result":"행사 수집 결과 누락",
          "invalid collection result":"행사 수집 결과 형식 오류", "poll timeout":"작업 확인 시간 초과", "응답 시간 초과":"서버 응답 시간 초과"};
        const message=String(error?.message || "");
        const reason=Object.hasOwn(reasons,message) ? reasons[message]
          : (/^HTTP \d{3}$/.test(message) ? "서버 요청 실패 · "+message : "통신 또는 응답 읽기 오류");
        status.textContent="수집 완료를 확인하지 못했습니다: "+reason+". 기존 목록과 필터를 유지했습니다. 상태를 확인한 뒤 다시 시도하세요.";
        if (message==="poll timeout" || message==="응답 시간 초과") status.textContent+=" 화면의 상태 확인만 종료됐으며 서버 수집 작업을 중단한 것은 아닙니다.";
      } finally { busy=false;button.disabled=false; }
    });
  }
  if (document.readyState==="loading") document.addEventListener("DOMContentLoaded",boot,{once:true}); else boot();
})();
