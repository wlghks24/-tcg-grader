(()=>{
'use strict';
const GLOBAL_KEY='__TCG_DUAL_PHOTO_BRIDGE_V158__';
if(globalThis[GLOBAL_KEY]?.loaded){
 globalThis[GLOBAL_KEY].duplicate_loads=(globalThis[GLOBAL_KEY].duplicate_loads||0)+1;
 return;
}
const bridgeState=globalThis[GLOBAL_KEY]={loaded:true,version:158,enhanced:false,duplicate_loads:0,manualProofStatusSync:true,integratedOfficialVerification:true,verifiedSlabRawLearning:true,recentManualToggle:true};
if(!document.getElementById('gpdDualBridgeForceV150')){
 const marker=document.createElement('meta');
 marker.id='gpdDualBridgeForceV150';
 marker.name='tcg-dual-photo-bridge';
 marker.content='inline-v158';
 document.head?.appendChild(marker);
}
let installed=false,submitting=false,proofSyncing=false,proofObserverInstalled=false;
const previewUrls={front:null,back:null};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function fileDataUrl(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||''));reader.onerror=()=>reject(new Error('파일을 읽지 못했습니다.'));reader.readAsDataURL(file)})}
async function normalize(file){
 if(!file||!['image/jpeg','image/png'].includes(file.type))throw new Error('앞면·뒷면 모두 JPG 또는 PNG로 선택하세요.');
 if(file.size>12_000_000)throw new Error('원본 사진 1장이 12MB를 초과합니다.');
 if(!globalThis.createImageBitmap)return fileDataUrl(file);
 const bitmap=await createImageBitmap(file,{imageOrientation:'from-image'});try{
  if(bitmap.width<320||bitmap.height<320)throw new Error('사진 해상도가 너무 작습니다.');
  const scale=Math.min(1,2200/Math.max(bitmap.width,bitmap.height));
  const canvas=document.createElement('canvas');canvas.width=Math.max(320,Math.round(bitmap.width*scale));canvas.height=Math.max(320,Math.round(bitmap.height*scale));
  const ctx=canvas.getContext('2d');if(!ctx)throw new Error('사진 변환을 시작하지 못했습니다.');
  ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);
  for(const q of [.9,.82,.74]){const value=canvas.toDataURL('image/jpeg',q);if(value.length<8_000_000)return value}
  throw new Error('사진을 6MB 이하로 줄이지 못했습니다.');
 }finally{bitmap.close?.()}
}
function formatBytes(bytes){const n=Number(bytes)||0;if(n>=1048576)return (n/1048576).toFixed(1)+'MB';if(n>=1024)return Math.round(n/1024)+'KB';return n+'B'}
function ensurePreviewStyle(){
 if(document.getElementById('gpdDualPreviewStyle'))return;
 const style=document.createElement('style');style.id='gpdDualPreviewStyle';style.textContent=`
 .gpd-dual-preview{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:11px 0 4px}
 .gpd-photo-preview{border:1px solid #cbd5e1;border-radius:12px;background:#f8fafc;overflow:hidden;min-width:0}
 .gpd-photo-preview-head{display:flex;align-items:center;justify-content:space-between;gap:6px;padding:8px 9px;background:#eef2ff;color:#1e3a8a;font-size:11px;font-weight:900}
 .gpd-photo-preview-state{font-size:9px;padding:3px 6px;border-radius:999px;background:#e2e8f0;color:#475569;white-space:nowrap}.gpd-photo-preview-state.ready{background:#dcfce7;color:#166534}
 .gpd-photo-preview-imgbox{height:230px;background:#111827;display:flex;align-items:center;justify-content:center;position:relative}
 .gpd-photo-preview-imgbox img{width:100%;height:100%;object-fit:contain;display:none}.gpd-photo-preview-imgbox.has-image img{display:block}
 .gpd-photo-preview-empty{color:#cbd5e1;text-align:center;font-size:11px;line-height:1.55;padding:12px}.gpd-photo-preview-imgbox.has-image .gpd-photo-preview-empty{display:none}
 .gpd-photo-preview-meta{padding:8px 9px;font-size:10px;color:#475569;line-height:1.45;min-height:48px;word-break:break-all}
 .gpd-recent-toggle-head{margin:13px 0 7px!important}
 .gpd-recent-toggle{width:100%;margin:0!important;padding:10px 12px!important;border:1px solid #cbd5e1!important;border-radius:10px!important;background:#f8fafc!important;color:#0f172a!important;font-weight:900!important;font-size:12px!important;text-align:left!important;cursor:pointer}
 .gpd-recent-toggle[aria-expanded="true"]{background:#eef2ff!important;color:#1e3a8a!important}
 .gpd-manual-rows.gpd-recent-collapsed>.gpd-manual-row{display:none!important}
 @media(max-width:520px){.gpd-dual-preview{grid-template-columns:1fr 1fr}.gpd-photo-preview-imgbox{height:190px}}
 @media(max-width:390px){.gpd-dual-preview{grid-template-columns:1fr}.gpd-photo-preview-imgbox{height:260px}}
 `;document.head.appendChild(style);
}
function previewMarkup(side,label){return `<div class="gpd-photo-preview" data-preview-card="${side}"><div class="gpd-photo-preview-head"><span>${label}</span><span class="gpd-photo-preview-state" data-preview-state="${side}">선택 전</span></div><div class="gpd-photo-preview-imgbox" data-preview-box="${side}"><img data-preview-img="${side}" alt="${label} 미리보기"><div class="gpd-photo-preview-empty">사진을 선택하면<br>여기에 바로 표시됩니다.</div></div><div class="gpd-photo-preview-meta" data-preview-meta="${side}">선택된 파일 없음</div></div>`}
function ensurePreviewArea(form){
 let area=document.getElementById('gpdDualPhotoPreview');if(area)return area;
 area=document.createElement('div');area.id='gpdDualPhotoPreview';area.className='gpd-dual-preview';area.innerHTML=previewMarkup('front','📷 앞면 미리보기')+previewMarkup('back','📷 뒷면 미리보기');
 const quick=form.querySelector('.gpd-manual-quick');if(quick)quick.insertAdjacentElement('afterend',area);else form.prepend(area);
 return area;
}
function ensureRegistrationPanelPresentation(form){
 const details=form?.closest('details.gpd-manual');if(!details)return;
 details.open=true;
 const summary=details.querySelector(':scope > summary');
 const eightZoneReady=Boolean(document.getElementById('gpdZonePanel')&&document.getElementById('gpdRevalidateExisting'));
 const label=eightZoneReady?'📷 등급사진 8구역 정밀등록':'📷 등급사진 간편등록';
 if(summary&&summary.textContent!==label)summary.textContent=label;
 bridgeState.eightZoneCompatible=eightZoneReady;
}
function clearPreviewUrl(side){if(previewUrls[side]){try{URL.revokeObjectURL(previewUrls[side])}catch(_){}previewUrls[side]=null}}
function showPreview(side,file,{registered=false}={}){
 const box=document.querySelector(`[data-preview-box="${side}"]`),img=document.querySelector(`[data-preview-img="${side}"]`),meta=document.querySelector(`[data-preview-meta="${side}"]`),state=document.querySelector(`[data-preview-state="${side}"]`);
 if(!box||!img||!meta||!state)return;
 if(!file){clearPreviewUrl(side);img.removeAttribute('src');box.classList.remove('has-image');meta.textContent='선택된 파일 없음';state.textContent='선택 전';state.classList.remove('ready');return;}
 clearPreviewUrl(side);previewUrls[side]=URL.createObjectURL(file);img.src=previewUrls[side];box.classList.add('has-image');meta.textContent=`${file.name||'사진'} · ${formatBytes(file.size)}`;state.textContent=registered?'등록 완료':'선택됨';state.classList.add('ready');
}
function markPreviewRegistered(){for(const side of ['front','back']){const state=document.querySelector(`[data-preview-state="${side}"]`);if(state&&document.querySelector(`[data-preview-box="${side}"]`)?.classList.contains('has-image')){state.textContent='등록 완료';state.classList.add('ready')}}}
function ensureRecentManualToggle(){
 const host=document.getElementById('gpdManualRows');if(!host)return false;
 const heading=host.querySelector(':scope > h4');if(!heading)return false;
 const rows=[...host.querySelectorAll(':scope > .gpd-manual-row')];
 heading.classList.add('gpd-recent-toggle-head');
 let button=heading.querySelector('.gpd-recent-toggle');
 if(!button){
  heading.textContent='';
  button=document.createElement('button');button.type='button';button.className='gpd-recent-toggle';button.setAttribute('aria-controls','gpdManualRows');
  button.addEventListener('click',()=>{const open=host.dataset.recentOpen!=='1';host.dataset.recentOpen=open?'1':'0';ensureRecentManualToggle()});
  heading.appendChild(button);
 }
 const open=host.dataset.recentOpen==='1';
 host.classList.toggle('gpd-recent-collapsed',!open);
 button.setAttribute('aria-expanded',open?'true':'false');
 const text=`${open?'▼':'▶'} 최근 수동등록 ${rows.length}건 ${open?'닫기':'보기'}`;if(button.textContent!==text)button.textContent=text;
 return true;
}
async function syncRecentManualProofState(){
 if(proofSyncing)return;
 const host=document.getElementById('gpdManualRows');if(!host)return;
 ensureRecentManualToggle();
 proofSyncing=true;
 try{
  const response=await fetch('/api/graded-photo-manual-registrations?_proof_state='+Date.now(),{cache:'no-store'});if(!response.ok)return;
  const payload=await response.json();const rows=Array.isArray(payload.registrations)?payload.registrations.slice(0,10):[];const domRows=[...host.querySelectorAll('.gpd-manual-row')];
  domRows.forEach((element,index)=>{
   const row=rows[index];if(!row)return;
   if(row.registration_id)element.dataset.registrationId=row.registration_id;
   const manualDone=row.manual_official_proof_registered===true&&(row.manual_official_proof_state==='matched'||row.verification_state==='manual_official_proof_matched'||row.verification_state==='verified_manual_official_page');
   const integratedOfficial=row.official_result===true&&(row.official_verification_source==='user_browser_official_page'||manualDone);
   if(!integratedOfficial)return;
   const rawReady=row.raw_grade_calibration_eligible===true&&row.raw_defect_learning_eligible===true;
   const rawActive=rawReady&&row.raw_proxy_learning_state==='active';
   const label=rawActive?'공식검증 완료 · RAW학습 활성':rawReady?'공식검증 완료 · RAW학습 누적':'공식검증 완료 · 통합관리';
   const badgeText=rawActive?'RAW학습 활성':rawReady?'RAW학습 누적':'공식검증 완료';
   const strong=element.querySelector('strong');if(strong&&strong.textContent!==label){strong.textContent=label;strong.className='ok';}
   const badge=element.querySelector('.gpd-manual-only-badge');if(badge&&badge.textContent!==badgeText){badge.textContent=badgeText;}
  });
 }catch(_){}finally{ensureRecentManualToggle();proofSyncing=false}
}
function installProofStateSync(){
 if(proofObserverInstalled)return;
 const host=document.getElementById('gpdManualRows');if(!host)return;
 proofObserverInstalled=true;
 let timer=0;const schedule=()=>{clearTimeout(timer);timer=setTimeout(()=>{ensureRecentManualToggle();syncRecentManualProofState()},120)};
 const observer=new MutationObserver(schedule);observer.observe(host,{childList:true,subtree:true});
 ensureRecentManualToggle();schedule();setInterval(()=>{ensureRecentManualToggle();syncRecentManualProofState()},4000);
}
function enhance(){
 const form=document.getElementById('gpdManualForm');if(!form)return false;
 ensureRegistrationPanelPresentation(form);ensurePreviewStyle();
 const existingBack=document.getElementById('gpdManualBackPhoto');
 if(existingBack){installed=true;bridgeState.enhanced=true;installProofStateSync();ensureRecentManualToggle();return true;}
 if(installed)return true;
 const front=document.getElementById('gpdManualPhoto');if(!front)return false;
 installed=true;
 const frontLabel=front.closest('label');if(frontLabel){const text=[...frontLabel.childNodes].find(n=>n.nodeType===Node.TEXT_NODE);if(text)text.textContent='② 등급 슬랩 앞면 사진';}
 const backLabel=document.createElement('label');backLabel.setAttribute('data-dual-back-label','1');backLabel.innerHTML='③ 등급 슬랩 뒷면 사진<input id="gpdManualBackPhoto" type="file" accept="image/jpeg,image/png" required>';
 frontLabel?.insertAdjacentElement('afterend',backLabel);
 const back=document.getElementById('gpdManualBackPhoto');
 const quick=form.querySelector('.gpd-manual-quick');if(quick)quick.style.gridTemplateColumns='minmax(120px,.55fr) minmax(0,1fr) minmax(0,1fr)';
 ensurePreviewArea(form);
 front.addEventListener('change',()=>showPreview('front',front.files?.[0]||null));
 back?.addEventListener('change',()=>showPreview('back',back.files?.[0]||null));
 const policy=form.querySelector('.gpd-manual-policy');if(policy)policy.innerHTML='카드게임을 선택하고 <b>등급 슬랩 앞면 + 뒷면 사진 2장</b>을 등록하세요. 앞면은 등급사·등급·인증번호 OCR에 사용하고 뒷면은 같은 카드의 증빙사진으로 저장합니다. <b>공식검증 완료 후에는 카드 영역만 추출해 RAW 결함·등급 보정학습에도 사용합니다.</b>';
 const button=document.getElementById('gpdManualSubmit');if(button)button.textContent='앞면 + 뒷면 2장 등록하기';
 form.addEventListener('submit',submit,true);installProofStateSync();ensureRecentManualToggle();
 bridgeState.enhanced=true;
 return true;
}
async function submit(event){
 event.preventDefault();event.stopImmediatePropagation();if(submitting)return;
 const front=document.getElementById('gpdManualPhoto')?.files?.[0],back=document.getElementById('gpdManualBackPhoto')?.files?.[0];
 const status=document.getElementById('gpdManualStatus'),button=document.getElementById('gpdManualSubmit');
 if(!front||!back){if(status)status.textContent='앞면과 뒷면 사진을 모두 선택하세요.';return;}
 submitting=true;if(button)button.disabled=true;if(status)status.textContent='앞면·뒷면 사진 메타데이터 제거·용량 최적화 중…';
 try{
  const [frontImage,backImage]=await Promise.all([normalize(front),normalize(back)]);if(frontImage===backImage)throw new Error('앞면과 뒷면에 같은 사진을 선택했습니다.');
  const gradeText=document.getElementById('gpdManualGrade')?.value.trim()||'';
  const body={entry_mode:'ocr_first_front_back',company:document.getElementById('gpdManualCompany')?.value||'',game:document.getElementById('gpdManualGame')?.value||'',grade:gradeText===''?null:Number(gradeText),certification_id:document.getElementById('gpdManualCert')?.value||'',card_name:document.getElementById('gpdManualCardName')?.value||'',card_number:document.getElementById('gpdManualCardNumber')?.value||'',filename:front.name||'',back_filename:back.name||'',image_data_url:frontImage,back_image_data_url:backImage,note:'manual_front_back_pair'};
  if(status)status.textContent='앞면 OCR + 뒷면 증빙사진을 같은 등록건으로 저장 중…';
  const response=await fetch('/api/graded-photo-manual-registration',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'});
  const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.error||`등록 실패(${response.status})`);
  markPreviewRegistered();if(status)status.textContent=data.duplicate?'기존 앞면 등록건에 뒷면 사진을 확인했습니다. 아래 미리보기는 방금 선택한 사진입니다.':'앞면·뒷면 2장 등록 완료 · 아래에서 방금 등록한 사진을 확인할 수 있습니다.';
  document.getElementById('gpdManualPhoto').value='';document.getElementById('gpdManualBackPhoto').value='';if(typeof window.loadManualRegistrations==='function')await window.loadManualRegistrations();await sleep(500);ensureRecentManualToggle();await syncRecentManualProofState();
 }catch(error){if(status)status.textContent=location.hostname.endsWith('github.io')?'PC·태블릿 로컬/Tailscale 서버 주소에서 등록하세요.':String(error?.message||'앞뒤 사진 등록 실패')}
 finally{submitting=false;if(button)button.disabled=false}
}
function boot(){let tries=0;const timer=setInterval(()=>{tries++;if(enhance()||tries>100)clearInterval(timer)},250)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();