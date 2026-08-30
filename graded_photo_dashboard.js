(()=>{
'use strict';
const COMPANIES=['PSA','BGS','CGC','TAG','BRG'];
const GAMES={pokemon:'포켓몬',onepiece:'원피스',naruto:'나루토'};
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const n=v=>Number.isFinite(Number(v))?Number(v):0;
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let running=false;
function companyOf(r){return String(r.company||r.grader||r.grading_company||r.provider||'').toUpperCase()}
function gameOf(r){const value=String(r.game||'').toLowerCase().replace(/[\s_-]+/g,'');if(value==='onepiece')return 'onepiece';if(value==='naruto')return 'naruto';if(value==='pokemon'||value==='pokémon')return 'pokemon';return 'unknown'}
function sourceOf(r){return String(r.source||r.market||r.source_name||r.search_provider||'기타')}
function statusOf(r){return String(r.status||r.verification_status||r.learning_status||'').toLowerCase()}
function isVerified(r){const s=statusOf(r);return r.official_result===true||r.verified===true||r.official_verified===true||s==='verified_reference'||s.includes('공식검증')}
function isReferenceLearning(r){return isVerified(r)&&String(r.learning_eligibility||'').includes('reference')}
function isRawEligible(r){return ['calibration_eligible','training_eligible'].includes(String(r.learning_eligibility||''))||r.calibration_eligible===true}
function isQuarantine(r){return !isVerified(r)||Boolean(r.evidence_conflicts?.length)||statusOf(r).includes('quarantine')}
function latestOf(rows,payload){const vals=rows.map(r=>r.collected_at||r.updated_at||r.verified_at||r.created_at).filter(Boolean).sort();return vals.at(-1)||payload.created_at||payload.updated_at||'-'}
function insertPanel(){
 if(document.getElementById('gradedPhotoDashboard'))return document.getElementById('gradedPhotoDashboard');
 const anchor=document.getElementById('v11')||document.querySelector('[id*="validation"]')||document.querySelector('.card');
 const box=document.createElement('section');box.id='gradedPhotoDashboard';box.className='graded-photo-dashboard card';
 box.innerHTML=`<div class="gpd-head"><div><h2>📊 등급사진 수집·검증 현황</h2><p>eBay·Google 공개검색·Amazon·KREAM·당근 등 후보를 OCR과 등급사 공식 인증조회로 교차검증합니다.</p></div><button id="gpdRefresh" type="button">강화 수집 실행</button></div><div id="gpdRunStatus" class="gpd-run-status">미검증 판매사진은 원본 카드 등급 보정에 사용하지 않습니다.</div><div id="gpdBody" class="gpd-body"><div class="gpd-loading">수집 현황을 불러오는 중…</div></div>`;
 if(anchor&&anchor.parentNode)anchor.parentNode.insertBefore(box,anchor.nextSibling);else document.querySelector('.app')?.appendChild(box);
 box.querySelector('#gpdRefresh')?.addEventListener('click',runCollection);return box;
}
function sourceHealth(payload){
 const stats=payload.source_stats&&typeof payload.source_stats==='object'?payload.source_stats:{};
 const rows=Object.entries(stats).sort((a,b)=>n(b[1]?.candidates)-n(a[1]?.candidates)||a[0].localeCompare(b[0]));
 if(!rows.length)return '<div class="gpd-empty">아직 출처 실행기록이 없습니다.</div>';
 return `<div class="gpd-health">${rows.slice(0,18).map(([id,s])=>{const state=s?.timed_out?'시간초과':n(s?.errors)>0?'오류/폴백':n(s?.queries)>0?'확인완료':'이번 회차 대기';return `<div><span>${esc(id)}</span><b>${n(s?.candidates)}건</b><small class="${state==='확인완료'?'ok':state==='이번 회차 대기'?'wait':'warn'}">${state} · 쿼리 ${n(s?.queries)} · 오류 ${n(s?.errors)}</small></div>`}).join('')}</div>`;
}
function diagnosticHtml(payload){
 const errors=Array.isArray(payload.errors)?payload.errors.filter(Boolean).slice(0,8):[];
 const config=payload.configuration||{};const probe=payload.image_probe_stats||{};const official=payload.official_verification_stats||{};const learning=payload.collection_learning_stats||{};const termCount=Object.values(learning.verified_identifiers||{}).reduce((sum,rows)=>sum+(Array.isArray(rows)?rows.length:0),0);
 return `<div class="gpd-diagnostics"><div><b>사진 OCR·최적선택</b><span>사진시도 ${n(probe.attempted)} · 후보행 ${n(probe.rows_attempted)} · 대체사진 ${n(probe.gallery_alternate_attempts)} · 정상 ${n(probe.validated)} · 문자판독 ${n(probe.ocr_readable)} · 인증번호 ${n(probe.certs_extracted)}</span></div><div><b>업체·게임 공정배분</b><span>15개 조합 중 ${n(payload.summary?.game_grader_buckets_covered)}개 확보 · 저장한도 제외 ${n(payload.summary?.candidate_cap_dropped)}건 · 공식조회 ${n(official.live_verified)}/${n(official.live_attempts)}</span></div><div><b>수집 자가학습 v${n(learning.version)}</b><span>검색학습 ${n(learning.query_runs)}회 · 업체경로 ${n(learning.grader_routes_tracked)}개 · 저조업체 재탐색 ${n(payload.summary?.undercovered_recovery_queries)}회 · 측정사진학습 ${n(learning.measurement_ready_feedback)}건 · 중복학습 차단 ${n(learning.duplicate_feedback_ignored)+n(payload.summary?.near_duplicate_references_suppressed)}건</span></div><div><b>연결 상태</b><span>Google CSE ${config.google_cse_configured?'연결':'미설정·공개검색 폴백'} · eBay API ${config.ebay_oauth_configured?'연결':'미설정·공개검색 폴백'}</span></div>${errors.length?`<div class="gpd-errors"><b>최근 폴백 원인</b><span>${errors.map(esc).join(' · ')}</span></div>`:''}</div>`;
}
function render(payload){
 const body=document.getElementById('gpdBody');if(!body)return;
 const rows=Array.isArray(payload.records)?payload.records:Array.isArray(payload.items)?payload.items:[];
 const summary=payload.summary||{};const verified=rows.filter(isVerified).length||n(summary.verified_references);const references=rows.filter(isReferenceLearning).length||n(summary.reference_learning_count);const rawEligible=rows.filter(isRawEligible).length||n(summary.raw_grade_calibration_eligible);const quarantine=rows.filter(isQuarantine).length||n(summary.quarantined);const total=rows.length||n(summary.total_candidates);
 const companyStats=payload.company_stats&&typeof payload.company_stats==='object'?payload.company_stats:{};const byCompany=Object.fromEntries(COMPANIES.map(c=>[c,rows.filter(r=>companyOf(r)===c).length||n(companyStats[c]?.candidates)]));
 const gameStats=payload.game_stats&&typeof payload.game_stats==='object'?payload.game_stats:{};const byGame=Object.fromEntries(Object.keys(GAMES).map(g=>[g,rows.filter(r=>gameOf(r)===g).length||n(gameStats[g]?.candidates)]));
 const sourceMap={};rows.forEach(r=>{const s=sourceOf(r);sourceMap[s]=(sourceMap[s]||0)+1});
 const sources=Object.entries(sourceMap).sort((a,b)=>b[1]-a[1]).slice(0,15);const providers=Object.entries(payload.provider_stats||{}).sort((a,b)=>n(b[1])-n(a[1])).slice(0,10);
 body.innerHTML=`<div class="gpd-summary"><div><span>전체 후보</span><b>${total.toLocaleString()}건</b></div><div><span>공식검증</span><b>${verified.toLocaleString()}건</b></div><div><span>측정용 앞면</span><b>${n(summary.measurement_photo_ready).toLocaleString()}건</b></div><div><span>참고학습 반영</span><b>${references.toLocaleString()}건</b></div><div><span>원본보정 학습</span><b>${rawEligible.toLocaleString()}건</b></div><div><span>사진 검증</span><b>${n(summary.validated_images).toLocaleString()}건</b></div><div><span>OCR 판독</span><b>${n(summary.ocr_readable).toLocaleString()}건</b></div><div><span>인증번호 확보</span><b>${n(summary.certifications_resolved).toLocaleString()}건</b></div><div><span>격리 후보</span><b>${quarantine.toLocaleString()}건</b></div></div>
 <div class="gpd-section"><h3>등급사별 확보량</h3><div class="gpd-companies">${COMPANIES.map(c=>`<div class="gpd-company"><b>${c}</b><strong>${byCompany[c].toLocaleString()}</strong><span>장 · 게임 ${n(companyStats[c]?.games_covered)}/3 · 사진검증 ${n(companyStats[c]?.validated_images)} · 측정참고 ${n(companyStats[c]?.measurement_ready)} · 공식 ${n(companyStats[c]?.verified_references)}</span></div>`).join('')}</div></div>
 <div class="gpd-section"><h3>게임별 등급사진 확보량</h3><div class="gpd-companies">${Object.entries(GAMES).map(([g,label])=>`<div class="gpd-company"><b>${label}</b><strong>${byGame[g].toLocaleString()}</strong><span>장</span></div>`).join('')}</div></div>
 <div class="gpd-section"><h3>후보 출처별 수집량</h3>${sources.length?`<div class="gpd-sources">${sources.map(([s,c])=>`<div><span>${esc(s)}</span><b>${c.toLocaleString()}건</b></div>`).join('')}</div>`:'<div class="gpd-empty">아직 출처별 후보가 없습니다.</div>'}</div>
 <div class="gpd-section"><h3>검색 공급자별 확보량</h3>${providers.length?`<div class="gpd-providers">${providers.map(([s,c])=>`<span>${esc(s)} <b>${n(c)}건</b></span>`).join('')}</div>`:'<div class="gpd-empty">검색 공급자 기록이 없습니다.</div>'}</div>
 <div class="gpd-section"><h3>출처 실행상태</h3>${sourceHealth(payload)}</div>${diagnosticHtml(payload)}
 <div class="gpd-foot"><span>최근 수집: ${esc(latestOf(rows,payload))}</span><span class="gpd-safe">공식검증 참고학습과 원본 결함 보정학습은 완전히 분리</span></div>`;
}
async function load(){
 insertPanel();const body=document.getElementById('gpdBody');
 const staticFirst=location.hostname.endsWith('github.io');
 const urls=staticFirst?['graded_photo_candidates.json','/api/graded-photo-learning']:['/api/graded-photo-learning','graded_photo_candidates.json'];
 for(const url of urls){try{const join=url.includes('?')?'&':'?';const response=await fetch(url+join+'_='+Date.now(),{cache:'no-store'});if(!response.ok)continue;render(await response.json());return}catch(_){}}
 if(body)body.innerHTML='<div class="gpd-error">현황을 불러오지 못했습니다. PC 또는 태블릿 로컬 서버 접속인지 확인하세요.</div>';
}
async function jobStatus(){const response=await fetch('/api/graded-photo-collection-status?_='+Date.now(),{cache:'no-store'});if(!response.ok)throw new Error('status');return response.json()}
async function runCollection(){
 if(running)return;running=true;const button=document.getElementById('gpdRefresh'),status=document.getElementById('gpdRunStatus');button.disabled=true;button.textContent='수집 시작 중…';status.textContent='공개 출처를 확인하고 사진 OCR·공식 인증조회까지 진행합니다.';
 try{
  const response=await fetch('/api/run-graded-photo-collection',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',cache:'no-store'});
  const data=await response.json().catch(()=>({}));
  if(!response.ok&&(response.status!==409||!['queued','running'].includes(String(data.job?.state||''))))throw new Error(data.error||'start');
  for(let i=0;i<120;i++){
   const job=await jobStatus();const state=job.state||'running';status.textContent=job.message||`강화 수집 ${state}`;
   if(state==='completed'||state==='failed'){await load();if(state==='failed')throw new Error(job.error||'collection failed');break}
   await sleep(3000);
  }
 }catch(_){status.textContent=location.hostname.endsWith('github.io')?'GitHub Pages에서는 저장된 현황만 표시됩니다. 실제 수집은 PC·태블릿 로컬 서버에서 실행하세요.':'강화 수집을 시작하지 못했습니다. 서버 상태와 최근 오류를 확인하세요.';await load()}
 finally{running=false;button.disabled=false;button.textContent='강화 수집 실행'}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>load(),{once:true});else load();setInterval(()=>{if(!running)load()},60000);
})();
