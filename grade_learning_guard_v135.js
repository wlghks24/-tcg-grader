/* TCG Grader v135 verified-learning browser guard
 * The page may keep historical/local validation rows for display, but grade
 * correction is applied only from the server's registry-gated model.
 * UI status separates verified slab/reference photos from RAW correction rows.
 */
(()=>{
'use strict';
const MODEL_KEY='tcg_verified_grade_model_v135';
const PHOTO_STATS_KEY='tcg_verified_photo_counts_v174';
const ROW_KEY='tcg_v99_validation';
const COMPANIES=['PSA','BGS','CGC','TAG','BRG'];
let safeModel=null;
let officialPhotoCounts=null;
let refreshing=false;
let photoRefreshing=false;

const number=value=>{const n=Number(value);return Number.isFinite(n)?n:null};
const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
function readJson(key,fallback){try{const value=JSON.parse(localStorage.getItem(key)||'null');return value??fallback}catch(_){return fallback}}
function writeJson(key,value){try{localStorage.setItem(key,JSON.stringify(value))}catch(_){}}
function validModel(value){return value&&value.ok===true&&Number(value.version)>=135&&value.companies&&typeof value.companies==='object'}

function currentVisionBucket(){
 const s=window.tcgVisionSnapshot;if(!s)return null;
 const front=number(s.frontCenter?.worst),back=number(s.backCenter?.worst);
 const surface=Math.max(number(s.frontSurface?.risk)||0,number(s.backSurface?.risk)||0);
 if(front===null||back===null||!Number.isFinite(surface))return null;
 const center=Math.min(front,back),centerBand=center>=47?'centered':center>=44?'minor-offcenter':'offcenter';
 const surfaceBand=surface<15?'surface-low':surface<35?'surface-medium':'surface-high';
 const multi=!!(s.frontSurface?.multiAngle&&s.backSurface?.multiAngle);
 return `${centerBand}|${surfaceBand}|${multi?'multi':'single'}`;
}

function safeCorrection(company){
 const entry=safeModel?.companies?.[company];
 let correction=entry?.enabled===true&&Number.isFinite(Number(entry.correction))?Number(entry.correction):0;
 const bucket=currentVisionBucket();
 if(bucket){
   const profile=safeModel?.vision_profiles?.[`${company}|${bucket}`];
   if(profile?.enabled===true&&Number.isFinite(Number(profile.correction)))correction+=Number(profile.correction);
 }
 return Math.max(-1,Math.min(0,correction));
}

function applyVerifiedCalibration(company,pred){
 const raw=number(pred);company=String(company||'').toUpperCase();
 if(raw===null||!COMPANIES.includes(company))return pred;
 const correction=safeCorrection(company);
 if(window.TCGAccuracyV99?.applyDownwardCorrection)return window.TCGAccuracyV99.applyDownwardCorrection(company,raw,correction);
 return Math.max(1,Math.min(10,raw+correction));
}

window.v30ApplyCalibration=applyVerifiedCalibration;
window.TCGVerifiedLearningV135={
 apply:applyVerifiedCalibration,
 model:()=>safeModel,
 referenceCounts:()=>officialPhotoCounts,
 refresh:()=>refreshModel(true),
 refreshReferences:()=>refreshReferenceStats(true),
 version:135,
 uiVersion:174,
};

function photoCompany(row){return String(row?.company||row?.grader||row?.grading_company||row?.provider||'').toUpperCase()}
function photoStatus(row){return String(row?.status||row?.verification_status||row?.learning_status||'').toLowerCase()}
function isInactivePhoto(row){const s=photoStatus(row),d=String(row?.disposition||row?.rejection_reason||'').toLowerCase();return row?.deleted===true||row?.rejected===true||row?.active===false||s.includes('deleted')||s.includes('rejected')||d.includes('official_record_not_found')||d.includes('rejected')||d.includes('deleted')}
function isOfficialPhoto(row){const s=photoStatus(row);return row?.official_result===true||row?.verified===true||row?.official_verified===true||s==='verified_reference'||s.includes('공식검증')}
function emptyPhotoCounts(){return Object.fromEntries(COMPANIES.map(company=>[company,0]))}
function photoCountsFromPayload(payload){
 const counts=emptyPhotoCounts();
 const rows=Array.isArray(payload?.records)?payload.records:Array.isArray(payload?.items)?payload.items:null;
 if(rows){
   for(const row of rows){
     if(!row||typeof row!=='object'||isInactivePhoto(row)||!isOfficialPhoto(row))continue;
     const company=photoCompany(row);if(company in counts)counts[company]++;
   }
   return counts;
 }
 const stats=payload?.company_stats&&typeof payload.company_stats==='object'?payload.company_stats:{};
 for(const company of COMPANIES){const value=number(stats?.[company]?.verified_references);if(value!==null)counts[company]=Math.max(0,Math.round(value))}
 return counts;
}
async function refreshReferenceStats(force=false){
 if(photoRefreshing)return officialPhotoCounts;
 if(!force&&officialPhotoCounts)return officialPhotoCounts;
 photoRefreshing=true;
 try{
   const staticFirst=location.hostname.endsWith('github.io');
   const urls=staticFirst?['graded_photo_candidates.json','/api/graded-photo-learning']:['/api/graded-photo-learning','graded_photo_candidates.json'];
   for(const url of urls){
     try{
       const join=url.includes('?')?'&':'?';
       const response=await fetch(`${url}${join}_=${Date.now()}`,{cache:'no-store'});
       if(!response.ok)continue;
       const data=await response.json();officialPhotoCounts=photoCountsFromPayload(data);writeJson(PHOTO_STATS_KEY,officialPhotoCounts);return officialPhotoCounts;
     }catch(_){}
   }
   throw new Error('photo stats unavailable');
 }catch(_){
   const cached=readJson(PHOTO_STATS_KEY,null);
   officialPhotoCounts=cached&&typeof cached==='object'?cached:null;
   return officialPhotoCounts;
 }finally{photoRefreshing=false}
}

function policyMinimumRows(){const value=number(safeModel?.policy?.minimum_rows_to_enable);return value!==null&&value>0?Math.round(value):10}
function policyMinimumCards(){const value=number(safeModel?.policy?.minimum_unique_cards_to_enable);return value!==null&&value>0?Math.round(value):8}
function totalCalibrationRows(){return COMPANIES.reduce((sum,company)=>sum+Math.max(0,Math.round(number(safeModel?.companies?.[company]?.n)||0)),0)}
function progressText(n,minRows){return n>=minRows?`${n}건 · 기준충족`:`${n}/${minRows}건`}

function patchLegacyUi(){
 const calibration=document.getElementById('v30calibration');
 const guide=calibration?.querySelector('p.muted');
 if(guide&&(/5건 미만/.test(guide.textContent)||/과대평가·과소평가/.test(guide.textContent))){
   guide.textContent=`등급사별 공식검증된 원본 카드 비교기록만 보정에 사용합니다. 최소 ${policyMinimumRows()}건·서로 다른 카드 ${policyMinimumCards()}장 전에는 보정값을 0.00으로 유지하며, 슬랩 등급사진은 공식확인·참고학습으로 별도 집계합니다.`;
 }
 const total=totalCalibrationRows();
 const summary=document.getElementById('validationSummary');
 if(summary&&total===0&&['검증 기록 없음','보정 비교기록 없음 · 등급사진 공식검증과는 별도 집계'].includes(summary.textContent.trim()))summary.textContent='보정 비교기록 없음 · 등급사진 공식검증과는 별도 집계';
 const calibrationStatus=document.getElementById('calibrationStatus');
 if(calibrationStatus&&total===0&&['보정 전','보정 비교기록 0건 · 공식검증 사진과 별도'].includes(calibrationStatus.textContent.trim()))calibrationStatus.textContent='보정 비교기록 0건 · 공식검증 사진과 별도';
 const qualityStatus=document.getElementById('qualityStatus');
 if(qualityStatus&&total===0&&['검증 데이터 없음','공식검증 사진은 참고학습 · RAW 보정비교는 아직 없음'].includes(qualityStatus.textContent.trim()))qualityStatus.textContent='공식검증 사진은 참고학습 · RAW 보정비교는 아직 없음';
}

function decorateCalibrationCards(){
 if(!safeModel)return;
 const minRows=policyMinimumRows();
 for(const company of COMPANIES){
   const grade=document.getElementById(`cal${company}`);const card=grade?.closest('.metric');if(!card)continue;
   let detail=card.querySelector('.v135-calibration-progress');
   if(!detail){detail=document.createElement('small');detail.className='v135-calibration-progress';detail.style.cssText='display:block;margin-top:7px;font-size:11px;line-height:1.45;color:#64748b;font-weight:650';card.appendChild(detail)}
   const n=Math.max(0,Math.round(number(safeModel.companies?.[company]?.n)||0));
   const official=number(officialPhotoCounts?.[company]);
   detail.textContent=`공식검증 사진 ${official===null?'확인 중':`${Math.max(0,Math.round(official))}건`} · 보정비교 ${progressText(n,minRows)}`;
 }
}

function statusBox(){
 let box=document.getElementById('v135VerifiedLearningStatus');
 if(box)return box;
 const parent=document.getElementById('v30calibration')||document.getElementById('v30validation');
 if(!parent)return null;
 box=document.createElement('div');box.id='v135VerifiedLearningStatus';box.className='status';box.style.margin='10px 0';
 const stats=parent.querySelector('.validation-stats');if(stats)parent.insertBefore(box,stats);else parent.appendChild(box);return box;
}
function renderStatus(note=''){
 patchLegacyUi();
 const box=statusBox();if(!box)return;
 if(!safeModel){box.innerHTML=`🔒 <b>공식검증 보정학습</b> · 안전모델 연결 대기${note?`<br>${esc(note)}`:''}`;return}
 const minRows=policyMinimumRows();
 const lines=COMPANIES.map(company=>{
   const row=safeModel.companies?.[company]||{},n=Math.max(0,Math.round(number(row.n)||0)),enabled=row.enabled===true;
   const official=number(officialPhotoCounts?.[company]);
   const state=enabled?`보정 ${Number(row.correction||0).toFixed(2)}`:(n>=minRows?'교차검증 대기':`${Math.max(0,minRows-n)}건 더 필요`);
   return `<div style="display:flex;justify-content:space-between;gap:10px;padding:4px 0"><b>${company}</b><span>공식검증 사진 ${official===null?'확인 중':`${Math.max(0,Math.round(official))}건`} · 보정비교 ${progressText(n,minRows)} · ${esc(state)}</span></div>`;
 });
 box.innerHTML=`🔒 <b>공식검증 사진 / RAW 보정비교 분리 현황</b><div style="margin-top:6px">${lines.join('')}</div><span class="muted">보정비교는 원본 카드 선측정 → 실제등급·인증번호 공식확인 순서로 자동 등록 · 최소 ${minRows}건/서로 다른 카드 ${policyMinimumCards()}장 · 상향보정 금지${note?` · ${esc(note)}`:''}</span>`;
 decorateCalibrationCards();
}

async function refreshModel(force=false){
 if(refreshing)return safeModel;refreshing=true;
 try{
   const response=await fetch(`/api/learning-model-status?t=${Date.now()}`,{cache:'no-store'});
   if(!response.ok)throw new Error(`HTTP ${response.status}`);
   const data=await response.json();if(!validModel(data))throw new Error('invalid v135 model');
   safeModel=data;writeJson(MODEL_KEY,data);await refreshReferenceStats(force);renderStatus();return data;
 }catch(error){
   const cached=readJson(MODEL_KEY,null);
   safeModel=validModel(cached)?cached:null;
   await refreshReferenceStats(force);
   renderStatus(safeModel?'오프라인: 마지막 서버 검증모델 사용':'서버 미연결: 보정 0');
   return safeModel;
 }finally{refreshing=false}
}

function latestCandidate(){
 const rows=readJson(ROW_KEY,[]);if(!Array.isArray(rows)||!rows.length)return null;
 const row=rows[rows.length-1];if(!row||typeof row!=='object')return null;
 const company=String(row.company||row.grader||'').toUpperCase(),cert=String(row.certification_id||row.cert_no||'').trim();
 const actual=number(row.actual),raw=number(row.raw_pred);
 if(!COMPANIES.includes(company)||row.official_result!==true||!/^[A-Za-z0-9._/-]{4,120}$/.test(cert)||actual===null||raw===null)return null;
 return {rows,row,index:rows.length-1,company,cert,actual,raw};
}
function markRejected(candidate,reason){
 if(!candidate)return;
 const rows=candidate.rows,row={...candidate.row,official_result:false,server_verified:false,v135_verification_error:String(reason||'official verification required').slice(0,180)};
 rows[candidate.index]=row;writeJson(ROW_KEY,rows.slice(-500));
 try{window.v30Compute?.();window.v97ComputeVisionCalibration?.();window.v30RenderValidation?.()}catch(_){}
}
function markAccepted(candidate,sample){
 if(!candidate)return;
 const rows=candidate.rows,row={...candidate.row,official_result:true,server_verified:true,verification_method:'official_registry_gate_v135'};
 if(sample?.certification_id)row.certification_id=sample.certification_id;
 rows[candidate.index]=row;writeJson(ROW_KEY,rows.slice(-500));
}

async function submitLatest(){
 const candidate=latestCandidate();if(!candidate){renderStatus('보정비교 저장 대기: 원본 선측정·실제등급·공식 인증번호를 모두 확인하세요');return}
 const row=candidate.row;
 const payload={
   company:candidate.company,
   certification_id:candidate.cert,
   actual_grade:candidate.actual,
   raw_pred:candidate.raw,
   pred:number(row.pred)??candidate.raw,
   mode:String(row.mode||'raw'),game:String(row.game||'unknown'),
   card_key:String(row.card_key||'').slice(0,180),card_id:String(row.card_id||'').slice(0,120),
   vision:row.vision&&typeof row.vision==='object'?row.vision:undefined,
 };
 const box=statusBox();if(box)box.innerHTML='🔎 <b>공식검증 보정학습</b> · 인증 레지스트리와 원시예측 교차확인 중…';
 try{
   const response=await fetch('/api/learning-sample',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   let data={};try{data=await response.json()}catch(_){}
   if(!response.ok||data.accepted!==true){
     markRejected(candidate,data.reason||data.error||`HTTP ${response.status}`);
     await refreshModel(true);renderStatus('해당 기록은 보정학습에서 제외됨');return;
   }
   markAccepted(candidate,data.sample);
   if(validModel(data.model)){safeModel=data.model;writeJson(MODEL_KEY,data.model);await refreshReferenceStats(true);renderStatus('새 공식검증 보정비교 기록 반영 완료')}
   else await refreshModel(true);
 }catch(_){
   markRejected(candidate,'server verification unavailable');
   await refreshModel(true);
 }
}

function hook(){
 window.v30ApplyCalibration=applyVerifiedCalibration;
 patchLegacyUi();
 refreshModel(true);
 const save=document.getElementById('saveValidation');
 save?.addEventListener('click',()=>setTimeout(submitLatest,220));
 document.getElementById('recalcCalibration')?.addEventListener('click',()=>setTimeout(()=>refreshModel(true),250));
 let checks=0;const timer=setInterval(()=>{checks++;if(window.v30ApplyCalibration!==applyVerifiedCalibration)window.v30ApplyCalibration=applyVerifiedCalibration;patchLegacyUi();if(checks>30)clearInterval(timer)},300);
 setInterval(()=>refreshModel(false),30000);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',hook,{once:true});else hook();
})();
