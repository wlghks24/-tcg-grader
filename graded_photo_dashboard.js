(()=>{
'use strict';
const COMPANIES=['PSA','BGS','CGC','TAG','BRG'];
const GAMES={pokemon:'포켓몬',onepiece:'원피스',naruto:'나루토'};
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const n=v=>Number.isFinite(Number(v))?Number(v):0;
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let running=false;
let manualSubmitting=false;
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
 if(!document.getElementById('gpdManualStyle')){const style=document.createElement('style');style.id='gpdManualStyle';style.textContent=`.gpd-manual{margin-top:12px;border:1px solid #bfdbfe;border-radius:13px;background:#fff;padding:11px}.gpd-manual summary{cursor:pointer;font-weight:850;color:#1e3a8a}.gpd-manual form{margin-top:12px}.gpd-manual-quick{display:grid;grid-template-columns:minmax(130px,.7fr) minmax(0,1.7fr);gap:9px}.gpd-manual-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.gpd-manual label{display:flex;flex-direction:column;gap:5px;color:#475569;font-size:11px;font-weight:750}.gpd-manual input,.gpd-manual select{width:100%;min-width:0;margin:0;padding:10px;border:1px solid #cbd5e1;border-radius:9px;background:#fff;color:#0f172a;font:inherit}.gpd-manual-extra{margin:10px 0;border:1px dashed #94a3b8;border-radius:9px;padding:9px}.gpd-manual-extra summary{color:#475569;font-size:11px}.gpd-manual-extra .gpd-manual-grid{margin-top:9px}.gpd-manual-policy{margin:9px 0;padding:9px;border-radius:9px;background:#ecfdf5;color:#047857;font-size:11px;line-height:1.5}.gpd-manual #gpdManualSubmit{width:100%;margin:0;background:#0f766e}.gpd-manual-status{margin-top:8px;color:#475569;font-size:11px}.gpd-manual-rows h4{margin:13px 0 7px}.gpd-manual-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;align-items:center;padding:9px 0;border-top:1px solid #e2e8f0}.gpd-manual-row>div{display:flex;flex-direction:column;min-width:0}.gpd-manual-row b,.gpd-manual-row span,.gpd-manual-row small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.gpd-manual-row b{font-size:12px;color:#0f172a}.gpd-manual-row span,.gpd-manual-row small{font-size:10px;color:#64748b}.gpd-manual-row strong{font-size:10px}.gpd-manual-row strong.ok{color:#047857}.gpd-manual-row strong.wait{color:#1d4ed8}.gpd-manual-row strong.warn{color:#b45309}.gpd-manual-row button{width:auto;margin:0;padding:7px 9px;font-size:10px;background:#475569}@media(max-width:640px){.gpd-manual-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:420px){.gpd-manual-quick,.gpd-manual-grid{grid-template-columns:1fr}.gpd-manual-row{grid-template-columns:minmax(0,1fr) auto}.gpd-manual-row button{grid-column:1/-1;width:100%}}`;document.head.appendChild(style)}
 const anchor=document.getElementById('v11')||document.querySelector('[id*="validation"]')||document.querySelector('.card');
 const box=document.createElement('section');box.id='gradedPhotoDashboard';box.className='graded-photo-dashboard card';
 box.innerHTML=`<div class="gpd-head"><div><h2>📊 등급사진 수집·검증 현황</h2><p>eBay·Google 공개검색·Amazon·KREAM·당근 등 후보를 OCR과 등급사 공식 인증조회로 교차검증합니다.</p></div><button id="gpdRefresh" type="button">강화 수집 실행</button></div><div id="gpdRunStatus" class="gpd-run-status">미검증 판매사진과 수동입력값은 원본 카드 등급 보정에 사용하지 않습니다.</div>
 <details class="gpd-manual"><summary>📷 자동수집 실패 시 간편등록</summary><form id="gpdManualForm"><div class="gpd-manual-quick"><label>① 카드게임<select id="gpdManualGame" required>${Object.entries(GAMES).map(([value,label])=>`<option value="${value}">${label}</option>`).join('')}</select></label><label>② 등급 슬랩 앞면 사진<input id="gpdManualPhoto" type="file" accept="image/jpeg,image/png" required></label></div><details class="gpd-manual-extra"><summary>OCR이 잘 못 읽을 때만 정보 직접입력(선택)</summary><div class="gpd-manual-grid"><label>등급사<select id="gpdManualCompany"><option value="">사진에서 자동인식</option>${COMPANIES.map(c=>`<option value="${c}">${c}</option>`).join('')}</select></label><label>표시 등급<input id="gpdManualGrade" type="number" min="1" max="10" step="0.5" placeholder="자동인식"></label><label>인증번호<input id="gpdManualCert" type="text" maxlength="24" autocomplete="off" placeholder="사진에서 자동인식"></label><label>카드명(선택)<input id="gpdManualCardName" type="text" maxlength="180" placeholder="예: 피카츄"></label><label>카드번호(선택)<input id="gpdManualCardNumber" type="text" maxlength="60" placeholder="예: 001/100"></label></div></details><div class="gpd-manual-policy">게임 선택과 사진 1장만으로 등록할 수 있습니다. OCR이 등급사·등급·인증번호를 자동입력하고, 세 항목이 공식 조회와 일치한 사진만 참고학습에 반영합니다. 미확인 사진은 격리되며 RAW 결함 보정학습에는 사용하지 않습니다.</div><button id="gpdManualSubmit" type="submit">사진 1장으로 간편등록</button><div id="gpdManualStatus" class="gpd-manual-status">PC·태블릿 로컬/Tailscale 서버에서 사용할 수 있습니다.</div></form><div id="gpdManualRows" class="gpd-manual-rows"></div></details>
 <div id="gpdBody" class="gpd-body"><div class="gpd-loading">수집 현황을 불러오는 중…</div></div>`;
 if(anchor&&anchor.parentNode)anchor.parentNode.insertBefore(box,anchor.nextSibling);else document.querySelector('.app')?.appendChild(box);
 box.querySelector('#gpdRefresh')?.addEventListener('click',runCollection);
 box.querySelector('#gpdManualForm')?.addEventListener('submit',submitManualRegistration);
 box.querySelector('#gpdManualRows')?.addEventListener('click',event=>{const id=event.target?.dataset?.retry;if(id)retryManualVerification(id)});
 loadManualRegistrations();return box;
}

function fileDataUrl(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||''));reader.onerror=()=>reject(new Error('file-read'));reader.readAsDataURL(file)})}
async function normalizedPhoto(file){
 if(!file||!['image/jpeg','image/png'].includes(file.type))throw new Error('JPG 또는 PNG 사진을 선택하세요.');
 if(file.size>12_000_000)throw new Error('원본 사진이 12MB를 초과합니다.');
 if(!globalThis.createImageBitmap)return fileDataUrl(file);
 const bitmap=await createImageBitmap(file,{imageOrientation:'from-image'});try{
  if(bitmap.width<320||bitmap.height<320)throw new Error('사진 해상도가 너무 작습니다.');
  const scale=Math.min(1,2200/Math.max(bitmap.width,bitmap.height)),canvas=document.createElement('canvas');canvas.width=Math.max(320,Math.round(bitmap.width*scale));canvas.height=Math.max(320,Math.round(bitmap.height*scale));const ctx=canvas.getContext('2d');if(!ctx)throw new Error('사진 변환을 시작하지 못했습니다.');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);for(const quality of [.9,.82,.74]){const value=canvas.toDataURL('image/jpeg',quality);if(value.length<8_000_000)return value}throw new Error('사진을 6MB 이하로 줄이지 못했습니다.');
 }finally{bitmap.close?.()}
}
function manualState(row){if(row.official_result===true)return ['공식검증 참고학습','ok'];if(row.verification_state==='manual_input_required')return ['정보 직접입력 필요','warn'];if(row.verification_state==='deferred_by_cooldown')return ['등급사 쿨다운 대기','wait'];if(row.status==='quarantine')return ['불일치 격리','warn'];if(['queued','ocr_running'].includes(row.verification_state))return ['OCR·공식검증 중','wait'];if(row.verification_state==='processing_failed')return ['처리 재시도 필요','warn'];return ['공식검증 대기','wait']}
function renderManualRegistrations(payload){
 const target=document.getElementById('gpdManualRows');if(!target)return;const rows=Array.isArray(payload.registrations)?payload.registrations:[];
 if(!rows.length){target.innerHTML='<div class="gpd-empty">수동등록 사진이 없습니다.</div>';return}
 target.innerHTML=`<h4>최근 수동등록</h4>${rows.slice(0,10).map(row=>{const [label,klass]=manualState(row),retry=row.official_result!==true&&row.verification_state!=='manual_input_required',company=row.company||row.ocr_company||'자동인식 대기',grade=row.claimed_grade??row.ocr_grade??'-',cert=row.certification_id||row.ocr_certification_id||'자동인식 대기';return `<div class="gpd-manual-row"><div><b>${esc(company)} ${esc(grade)} · ${esc(GAMES[row.game]||row.game)}</b><span>인증 ${esc(cert)}${row.card_name?` · ${esc(row.card_name)}`:''}</span><small>${esc(row.image_width)}×${esc(row.image_height)} · ${esc(row.created_at)}</small></div><strong class="${klass}">${label}</strong>${retry?`<button type="button" data-retry="${esc(row.registration_id)}">재검증</button>`:''}</div>`}).join('')}`;
}
function manualVerificationFinished(payload,registrationId){const rows=Array.isArray(payload?.registrations)?payload.registrations:[];const row=rows.find(item=>item.registration_id===registrationId);return Boolean(row&&!['queued','ocr_running'].includes(String(row.verification_state||'')))}
async function loadManualRegistrations(){
 const target=document.getElementById('gpdManualRows');try{const response=await fetch('/api/graded-photo-manual-registrations?_='+Date.now(),{cache:'no-store'});if(!response.ok)throw new Error('manual-status');const payload=await response.json();renderManualRegistrations(payload);return payload}catch(_){if(target)target.innerHTML=location.hostname.endsWith('github.io')?'<div class="gpd-empty">수동등록은 PC·태블릿의 로컬/Tailscale 서버 주소에서 실행하세요.</div>':'<div class="gpd-error">수동등록 현황을 불러오지 못했습니다.</div>';return null}
}
async function submitManualRegistration(event){
 event.preventDefault();if(manualSubmitting)return;const status=document.getElementById('gpdManualStatus'),button=document.getElementById('gpdManualSubmit'),file=document.getElementById('gpdManualPhoto')?.files?.[0];manualSubmitting=true;button.disabled=true;status.textContent='사진 개인정보 메타데이터 제거·용량 최적화 중…';
 try{const image=await normalizedPhoto(file);status.textContent='안전등록 후 OCR·공식 인증조회 대기열에 추가 중…';const gradeText=document.getElementById('gpdManualGrade').value.trim();const body={entry_mode:'ocr_first',company:document.getElementById('gpdManualCompany').value,game:document.getElementById('gpdManualGame').value,grade:gradeText===''?null:Number(gradeText),certification_id:document.getElementById('gpdManualCert').value,card_name:document.getElementById('gpdManualCardName').value,card_number:document.getElementById('gpdManualCardNumber').value,filename:file?.name||'',image_data_url:image};const response=await fetch('/api/graded-photo-manual-registration',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'});const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.error||`등록 실패(${response.status})`);status.textContent=data.duplicate?'같은 사진이 이미 등록되어 기존 항목을 표시합니다.':'등록 완료 · 사진에서 등급정보를 자동인식합니다.';document.getElementById('gpdManualPhoto').value='';const registrationId=data.registration?.registration_id;for(let i=0;i<12;i++){await sleep(1500);const payload=await loadManualRegistrations();if(manualVerificationFinished(payload,registrationId)){const row=payload?.registrations?.find(item=>item.registration_id===registrationId);if(row?.verification_state==='manual_input_required')status.textContent='OCR이 일부 정보를 읽지 못했습니다. 선택 입력란을 펼쳐 정보와 같은 사진을 다시 등록하세요.';break}}await load();
 }catch(error){status.textContent=location.hostname.endsWith('github.io')?'GitHub Pages가 아닌 PC·태블릿 로컬/Tailscale 서버 주소에서 등록하세요.':String(error?.message||'수동등록을 완료하지 못했습니다.')}
 finally{manualSubmitting=false;button.disabled=false}
}
async function retryManualVerification(registrationId){
 const status=document.getElementById('gpdManualStatus');status.textContent='공식 인증 재검증을 요청했습니다.';try{const response=await fetch('/api/retry-graded-photo-manual-verification',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({registration_id:registrationId}),cache:'no-store'});if(!response.ok)throw new Error('retry');for(let i=0;i<8;i++){await sleep(1500);const payload=await loadManualRegistrations();if(manualVerificationFinished(payload,registrationId))break}}catch(_){status.textContent='재검증을 시작하지 못했습니다. 쿨다운 후 다시 시도하세요.'}
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
 const companyStats=payload.company_stats&&typeof payload.company_stats==='object'?payload.company_stats:{};const byCompany=Object.fromEntries(COMPANIES.map(c=>[c,0]));
 const gameStats=payload.game_stats&&typeof payload.game_stats==='object'?payload.game_stats:{};const byGame=Object.fromEntries(Object.keys(GAMES).map(g=>[g,0]));
 const sourceMap={};rows.forEach(r=>{const company=companyOf(r),game=gameOf(r),source=sourceOf(r);if(company in byCompany)byCompany[company]++;if(game in byGame)byGame[game]++;sourceMap[source]=(sourceMap[source]||0)+1});COMPANIES.forEach(c=>{if(!byCompany[c])byCompany[c]=n(companyStats[c]?.candidates)});Object.keys(GAMES).forEach(g=>{if(!byGame[g])byGame[g]=n(gameStats[g]?.candidates)});
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
 for(const url of urls){try{const join=url.includes('?')?'&':'?';const response=await fetch(url+join+'_='+Date.now(),{cache:'no-store'});if(!response.ok)continue;render(await response.json());loadManualRegistrations();return}catch(_){}}
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
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>load(),{once:true});else load();document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&!running&&!manualSubmitting)load()});setInterval(()=>{if(document.visibilityState==='visible'&&!running&&!manualSubmitting)load()},60000);
})();
