/* Automatic PRIVATE image collector v4, registry-wide coverage with honest source status. */
(() => {
  'use strict';
  const base='/api/local-card-images';
  const wrap=document.getElementById('tcgImageLibraryV1');
  if(!wrap || document.getElementById('tcgAutoImageV2')) return;
  const panel=document.createElement('section');panel.id='tcgAutoImageV2';
  panel.style.cssText='margin:12px 0;padding:13px;border:1px solid #cbd5e1;border-radius:14px;background:#f8fafc;color:#0f172a';
  const heading=document.createElement('h3');heading.textContent='🔄 무료 자동 이미지 수집 v4 · 전체 게임 목록 감시 / 연결된 출처별 다운로드';
  heading.style.cssText='font-size:17px;margin:0 0 8px';panel.append(heading);
  const info=document.createElement('p');info.textContent='검증된 공개 카드 데이터 출처만 사용합니다. 사진은 태블릿 Pictures에 저장됩니다. 새 자동수집 사진은 해상도를 줄이지 않는 무손실 압축을 시도하고 더 작을 때만 적용합니다. 다른 판본으로 대체하지 않습니다.';info.style.cssText='font-size:13px;line-height:1.6';panel.append(info);
  const area=document.createElement('div');area.style.cssText='display:flex;gap:8px;flex-wrap:wrap;align-items:center';panel.append(area);
  const button=(label,secondary=false)=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.style.cssText='min-height:44px;background:'+(secondary?'#475569':'#155e75')+';color:white;border:0;border-radius:10px;padding:10px';area.append(b);return b;};
  const start=button('지금 자동 수집 시작');const stop=button('중지',true);
  const schedule=document.createElement('label');schedule.style.cssText='display:inline-flex;align-items:center;gap:5px;font-weight:600;font-size:13px';
  const check=document.createElement('input');check.type='checkbox';check.style.width='20px';check.style.height='20px';
  schedule.append(check,document.createTextNode('서버 실행 중 6시간 간격 자동'));area.append(schedule);
  const stat=document.createElement('p');stat.setAttribute('role','status');stat.style.cssText='white-space:pre-wrap;font-size:13px;line-height:1.6;margin:10px 0';panel.append(stat);
  const coverage=document.createElement('p');coverage.style.cssText='font-size:12px;color:#475569;line-height:1.6';panel.append(coverage);
  // form is nested inside details; insertBefore requires a direct child of wrap.
  const manualPanel=wrap.querySelector('.tcg-manual-optional');
  if(manualPanel&&manualPanel.parentNode===wrap)wrap.insertBefore(panel,manualPanel);
  else wrap.prepend(panel);
  let busy=false, poll=null, updating=false, seenProgress="";
  const json=async (url,payload)=>{
    const opt={cache:'no-store',credentials:'same-origin'};
    if(payload !== undefined){opt.method='POST';opt.headers={'Content-Type':'application/json'};opt.body=JSON.stringify(payload);}
    const response=await fetch(base+url,opt);
    const data=await response.json().catch(()=>({}));
    if(!response.ok||!data.ok)throw Error(data.error||'HTTP '+response.status);
    return data;
  };
  async function update(){
    if(updating)return;
    updating=true;
    try{
      const d=await json('/auto-status');
      check.checked=d.auto_enabled;
      const j=d.job||{},prev=d.last_result||{},current=j.running?j:prev;
      const progress=JSON.stringify([j.started_at,j.saved,j.finished_at]);
      if(progress!==seenProgress){
        seenProgress=progress;
        document.dispatchEvent(new Event("tcg-local-images-updated"));
      }
      stat.textContent=(j.running?'수집 진행 중':'대기')+' · 최근 '+(current.saved||0)+'장 저장 / '+(current.skipped||0)+'장 건너뜀 / '+(current.errors||0)+'개 오류'+
        (prev.issues&&prev.issues.length?'\n출처 오류: '+prev.issues.slice(0,2).join(' · '):'') +
        '\n로컬 저장 위치: Pictures/TCG_Card_Images';
      const budget=d.collection_policy;
      if(budget)stat.textContent+='\n최근 24시간 '+budget.saved_last_24h+'/'+budget.daily_limit+'장 · 회당 최대 '+budget.per_run_limit+'장 · 요청 간격 '+budget.request_spacing_seconds+'초 이상';
      const s=d.coverage?.supported_sources||[];
      coverage.textContent='자동 출처 연결 '+s.length+'개 지역/게임 조합 (등록 게임 '+(d.coverage?.game_count??'?')+'종). 현재: '+s.map(x=>x.game_id+'/'+x.region+' '+x.source).join(', ')+
        '. 출처 미연결: '+(d.coverage?.pending_source_count??'?')+'개 조합. 자동 연결이 없는 판본은 사진을 임의로 대체하지 않습니다. BOX/카드 이미지 범위는 연결된 출처에 한정됩니다.';
      start.disabled=Boolean(j.running)||busy;
      stop.disabled=!j.running||busy;
      if(!j.running && poll){clearInterval(poll);poll=null;const refresh=wrap.querySelector('.tcg-img-footer button');if(refresh)refresh.click();}
    }catch(ex){stat.textContent='자동수집 서버 연결 실패: '+ex.message;}
    finally{updating=false;}
  }
  start.addEventListener('click',async()=>{
    if(busy)return;busy=true;start.disabled=true;
    try{await json('/auto-start',{});stat.textContent='자동수집 요청 성공 · 다운로드 준비 중';
      if(!poll)poll=setInterval(update,3000);await update();}
    catch(ex){stat.textContent='시작 실패: '+ex.message;}finally{busy=false;}
  });
  stop.addEventListener('click',async()=>{try{await json('/auto-stop',{});await update();}catch(ex){stat.textContent='중지 오류: '+ex.message;}});
  check.addEventListener('change',async()=>{const value=check.checked;check.disabled=true;try{await json('/auto-enable',{enabled:value});await update();}catch(ex){stat.textContent='자동 실행 설정 실패: '+ex.message;check.checked=!value;}finally{check.disabled=false;}});
  update();
  // Reflect scheduled background saves too; do not wait for the 90-second catalog poll.
  setInterval(()=>{if(!document.hidden)void update();},5000);
})();
