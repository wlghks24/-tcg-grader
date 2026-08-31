/* TCG Grader v135 verified-learning browser guard
 * The page may keep historical/local validation rows for display, but grade
 * correction is applied only from the server's registry-gated model.
 */
(()=>{
'use strict';
const MODEL_KEY='tcg_verified_grade_model_v135';
const ROW_KEY='tcg_v99_validation';
const COMPANIES=['PSA','BGS','CGC','TAG','BRG'];
let safeModel=null;
let refreshing=false;

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

// Replace every earlier local calibration hook. Local rows remain useful as a
// visible history but cannot affect grades until the server verifies them.
window.v30ApplyCalibration=applyVerifiedCalibration;
window.TCGVerifiedLearningV135={
 apply:applyVerifiedCalibration,
 model:()=>safeModel,
 refresh:()=>refreshModel(true),
 version:135,
};

function statusBox(){
 let box=document.getElementById('v135VerifiedLearningStatus');
 if(box)return box;
 const parent=document.getElementById('v30calibration')||document.getElementById('v30validation');
 if(!parent)return null;
 box=document.createElement('div');box.id='v135VerifiedLearningStatus';box.className='status';box.style.marginTop='10px';
 parent.appendChild(box);return box;
}
function renderStatus(note=''){
 const box=statusBox();if(!box)return;
 if(!safeModel){box.innerHTML=`🔒 <b>v135 공식검증 학습게이트</b> · 안전모델 연결 대기${note?`<br>${esc(note)}`:''}`;return}
 const lines=COMPANIES.map(company=>{const row=safeModel.companies?.[company]||{};const enabled=row.enabled===true;return `${company} ${Number(row.n||0)}건 · ${enabled?'보정 '+Number(row.correction||0).toFixed(2):'관찰/대기'}`});
 box.innerHTML=`🔒 <b>v135 공식검증 학습게이트</b><br>${lines.join(' · ')}<br><span class="muted">공식 인증 레지스트리 일치 + RAW 원시예측만 학습 · 카드단위 교차검증 · 상향보정 금지${note?` · ${esc(note)}`:''}</span>`;
}

async function refreshModel(force=false){
 if(refreshing)return safeModel;refreshing=true;
 try{
   const response=await fetch(`/api/learning-model-status?t=${Date.now()}`,{cache:'no-store'});
   if(!response.ok)throw new Error(`HTTP ${response.status}`);
   const data=await response.json();if(!validModel(data))throw new Error('invalid v135 model');
   safeModel=data;writeJson(MODEL_KEY,data);renderStatus();return data;
 }catch(error){
   const cached=readJson(MODEL_KEY,null);
   safeModel=validModel(cached)?cached:null;
   // A cached server-verified model may be used offline. Never rebuild from
   // arbitrary browser validation rows.
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
 const candidate=latestCandidate();if(!candidate)return;
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
 const box=statusBox();if(box)box.innerHTML='🔎 <b>v135</b> · 공식 인증 레지스트리와 원시예측 교차확인 중…';
 try{
   const response=await fetch('/api/learning-sample',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   let data={};try{data=await response.json()}catch(_){}
   if(!response.ok||data.accepted!==true){
     markRejected(candidate,data.reason||data.error||`HTTP ${response.status}`);
     await refreshModel(true);renderStatus('해당 기록은 학습에서 제외됨');return;
   }
   markAccepted(candidate,data.sample);
   if(validModel(data.model)){safeModel=data.model;writeJson(MODEL_KEY,data.model);renderStatus('새 공식검증 기록 반영 완료')}
   else await refreshModel(true);
 }catch(_){
   // Network failure does not promote the row. Keep it as reference history but
   // prevent it from training the local/browser correction.
   markRejected(candidate,'server verification unavailable');
   await refreshModel(true);
 }
}

function hook(){
 window.v30ApplyCalibration=applyVerifiedCalibration;
 refreshModel(true);
 const save=document.getElementById('saveValidation');
 save?.addEventListener('click',()=>setTimeout(submitLatest,220));
 document.getElementById('recalcCalibration')?.addEventListener('click',()=>setTimeout(()=>refreshModel(true),250));
 // Other scripts may redefine v30ApplyCalibration later; reassert the verified
 // gate after startup and before typical user interaction.
 let checks=0;const timer=setInterval(()=>{checks++;if(window.v30ApplyCalibration!==applyVerifiedCalibration)window.v30ApplyCalibration=applyVerifiedCalibration;if(checks>30)clearInterval(timer)},300);
 setInterval(()=>refreshModel(false),30000);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',hook,{once:true});else hook();
})();
