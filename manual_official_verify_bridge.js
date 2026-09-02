(()=>{
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let installed=false;
let recentDeleteSync=false;
let rendering=false;
let summaryObserverInstalled=false;
const proofDrafts=new Map();

function ensureDualPhotoBridge(){
 if(document.getElementById('gpdManualBackPhoto'))return;
 if(document.getElementById('gpdDualBridgeForceV150'))return;
 const script=document.createElement('script');
 script.id='gpdDualBridgeForceV150';
 script.src='./manual_dual_photo_bridge.js?v=150&force='+Date.now();
 script.async=false;
 script.setAttribute('data-purpose','force-front-back-manual-upload');
 document.head.appendChild(script);
}

function fileDataUrl(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||''));reader.onerror=()=>reject(new Error('파일을 읽지 못했습니다.'));reader.readAsDataURL(file)})}
async function normalize(file){
 if(!file||!['image/jpeg','image/png'].includes(file.type))throw new Error('공식 조회 결과 화면을 JPG 또는 PNG로 선택하세요.');
 if(file.size>12_000_000)throw new Error('공식 조회 화면이 12MB를 초과합니다.');
 if(!globalThis.createImageBitmap)return fileDataUrl(file);
 const bitmap=await createImageBitmap(file,{imageOrientation:'from-image'});try{
  const scale=Math.min(1,2200/Math.max(bitmap.width,bitmap.height));
  const canvas=document.createElement('canvas');canvas.width=Math.max(320,Math.round(bitmap.width*scale));canvas.height=Math.max(320,Math.round(bitmap.height*scale));
  const ctx=canvas.getContext('2d');if(!ctx)throw new Error('사진 변환을 시작하지 못했습니다.');
  ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);
  for(const quality of [.9,.82,.74]){const value=canvas.toDataURL('image/jpeg',quality);if(value.length<8_000_000)return value}
  throw new Error('공식 조회 화면을 6MB 이하로 줄이지 못했습니다.');
 }finally{bitmap.close?.()}
}

function style(){
 if(document.getElementById('gpdOfficialFallbackStyle'))return;
 const el=document.createElement('style');el.id='gpdOfficialFallbackStyle';el.textContent=`
 .gpd-official-fallback{display:block!important;margin-top:12px;border:1px solid #0f766e55;background:#f0fdfa;border-radius:13px;padding:11px;color:#134e4a}
 .gpd-official-fallback h4{margin:0 0 5px;font-size:13px}.gpd-official-fallback p{font-size:10px;line-height:1.55;margin:4px 0;color:#115e59}
 .gpd-official-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;padding:10px 0;border-top:1px solid #99f6e4;align-items:center}.gpd-official-row:first-of-type{margin-top:8px}
 .gpd-official-id{min-width:0}.gpd-official-id b,.gpd-official-id span,.gpd-official-id small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.gpd-official-id b{font-size:12px}.gpd-official-id span,.gpd-official-id small{font-size:10px;color:#115e59;margin-top:2px}
 .gpd-official-actions{display:grid;grid-template-columns:auto auto auto auto;gap:6px;align-items:center}.gpd-official-open,.gpd-official-proof,.gpd-official-submit,.gpd-official-delete,.gpd-recent-delete{display:inline-flex;align-items:center;justify-content:center;border:0;border-radius:9px;padding:8px 9px;font-weight:800;font-size:10px;text-decoration:none;white-space:nowrap}.gpd-official-open{background:#2563eb;color:#fff}.gpd-official-proof{background:#2563eb;color:#fff;margin:0;width:auto}.gpd-official-submit{background:#0f766e;color:#fff;margin:0;width:auto;cursor:pointer}.gpd-official-submit:disabled{opacity:.38;cursor:not-allowed}.gpd-official-delete,.gpd-recent-delete{background:#fee2e2!important;color:#b91c1c!important;cursor:pointer}.gpd-official-delete:disabled,.gpd-recent-delete:disabled{opacity:.55;cursor:wait}.gpd-official-file{display:none}.gpd-official-state{font-size:10px;font-weight:800;color:#047857;margin-top:3px}
 .gpd-official-help{margin-top:8px;padding:8px;border-radius:9px;background:#ecfdf5;font-size:10px;line-height:1.6;color:#065f46}
 .gpd-manual-only-badge{display:inline-flex;align-items:center;padding:7px 9px;border-radius:9px;background:#ecfdf5;color:#047857;font-size:10px;font-weight:900;white-space:nowrap}
 .gpd-manual-row .gpd-recent-delete{width:auto;margin:0;padding:7px 9px;font-size:10px}
 @media(max-width:620px){.gpd-official-row{grid-template-columns:1fr}.gpd-official-actions{grid-template-columns:1fr 1fr}.gpd-official-delete{grid-column:1/-1}.gpd-official-open,.gpd-official-proof,.gpd-official-submit,.gpd-official-delete{width:100%}}
 @media(max-width:420px){.gpd-manual-row .gpd-recent-delete{grid-column:1/-1;width:100%}}
 `;document.head.appendChild(el);
}

function countFromCard(card){
 const text=String(card?.querySelector('b')?.textContent||'');
 const match=text.match(/\d[\d,]*/);if(!match)return 0;
 const value=Number(match[0].replace(/,/g,''));return Number.isFinite(value)?value:0;
}
function mergeVerifiedLearningSummary(){
 const summary=document.querySelector('#gpdBody .gpd-summary');if(!summary)return false;
 const cards=[...summary.children];
 const official=cards.find(card=>['공식검증','공식검증·학습반영'].includes(String(card.querySelector('span')?.textContent||'').trim()));
 const reference=cards.find(card=>String(card.querySelector('span')?.textContent||'').trim()==='참고학습 반영');
 const cert=cards.find(card=>String(card.querySelector('span')?.textContent||'').trim()==='인증번호 확보');
 if(!official)return false;
 const merged=Math.max(countFromCard(official),countFromCard(reference));
 const label=official.querySelector('span'),value=official.querySelector('b');
 const mergedText=`${merged.toLocaleString()}세트 · 사진 ${(merged*2).toLocaleString()}장`;
 if(label&&label.textContent!=='공식검증·학습반영')label.textContent='공식검증·학습반영';
 if(value&&value.textContent!==mergedText)value.textContent=mergedText;
 if(reference)reference.remove();
 if(cert){
  const certCount=countFromCard(cert),certValue=cert.querySelector('b'),certText=`${certCount.toLocaleString()}개`;
  if(certValue&&certValue.textContent!==certText)certValue.textContent=certText;
 }
 const footer=document.querySelector('#gpdBody .gpd-foot .gpd-safe');
 const footerText='공식검증은 카드 세트 기준 · 앞면+뒷면 사진은 모두 학습에 사용 · 인증번호는 고유번호 기준';
 if(footer&&footer.textContent!==footerText)footer.textContent=footerText;
 return true;
}
function installSummaryObserver(){
 if(summaryObserverInstalled)return;
 const body=document.getElementById('gpdBody');if(!body)return;
 summaryObserverInstalled=true;
 let timer=0;
 const observer=new MutationObserver(()=>{
  clearTimeout(timer);
  timer=setTimeout(()=>mergeVerifiedLearningSummary(),40);
 });
 observer.observe(body,{childList:true,subtree:false});
 setTimeout(mergeVerifiedLearningSummary,200);
 setTimeout(mergeVerifiedLearningSummary,800);
 setTimeout(mergeVerifiedLearningSummary,1800);
}

function suppressAutoRetry(){
 const host=document.getElementById('gpdManualRows');if(!host)return;
 host.querySelectorAll('button').forEach(button=>{
  const label=String(button.textContent||'').trim();
  if(label==='재검증'||label.includes('자동검증')){
   button.hidden=true;button.disabled=true;button.setAttribute('aria-hidden','true');
   const row=button.closest('.gpd-manual-row');
   if(row&&!row.querySelector('.gpd-manual-only-badge')){
    const badge=document.createElement('span');badge.className='gpd-manual-only-badge';badge.textContent='공식사이트 수동확인';
    button.insertAdjacentElement('afterend',badge);
   }
  }
 });
}
async function injectRecentDeleteButtons(){
 if(recentDeleteSync)return;
 const host=document.getElementById('gpdManualRows');if(!host)return;
 recentDeleteSync=true;
 try{
  const response=await fetch('/api/graded-photo-manual-registrations?_='+Date.now(),{cache:'no-store'});if(!response.ok)return;
  const payload=await response.json(),rows=Array.isArray(payload.registrations)?payload.registrations.slice(0,10):[],domRows=[...host.querySelectorAll('.gpd-manual-row')];
  domRows.forEach((element,index)=>{
   const row=rows[index];if(!row||row.official_result===true||!row.registration_id)return;
   element.dataset.registrationId=row.registration_id;
   if(element.querySelector('.gpd-recent-delete'))return;
   const button=document.createElement('button');button.type='button';button.className='gpd-recent-delete';button.dataset.deleteRegistration=row.registration_id;button.textContent='🗑 삭제/취소';button.addEventListener('click',deleteRegistration);element.appendChild(button);
  });
 }catch(_){}finally{recentDeleteSync=false}
}

function eligible(row){return row&&row.official_result!==true&&row.identity_complete&&row.official_reference_url}
function stateText(row){
 if(row.manual_official_proof_registered)return row.manual_official_proof_match_mode==='official_page_company_cert_plus_exact_slab_ocr_grade'?'공식페이지 인증번호 + 슬랩 등급 OCR 일치 · 공식검증 완료':'공식 페이지 캡처 일치 · 공식검증 완료';
 if(row.manual_official_proof_state==='ocr_incomplete_needs_review'||row.verification_state==='manual_official_proof_needs_review')return '공식페이지 OCR 일부 누락 · 다시 등록 가능 (카드 격리 안함)';
 if(row.manual_official_proof_state==='conflict_needs_review'||row.verification_state==='manual_official_proof_conflict_needs_review')return '확인화면 OCR 충돌 후보 · 다시 확인 필요 (카드 격리 안함)';
 if(row.manual_official_proof_state==='conflict')return '이전 확인화면 OCR 불일치 기록 · 재등록 가능';
 if(row.verification_state==='manual_official_verification_required')return '공식사이트 수동확인 대기';
 if(row.verification_state==='manual_input_required')return '등급사·인증번호·등급 직접입력 필요';
 if(row.verification_state==='deferred_by_cooldown')return '기존 자동조회 대기자료 · 수동확인으로 전환';
 if(row.verification_state==='processing_failed')return '기존 자동검증 실패자료 · 수동확인으로 전환';
 return '공식사이트 수동확인 가능';
}
async function loadStatus(){
 try{const response=await fetch('/api/manual-official-proof-status?_='+Date.now(),{cache:'no-store'});if(!response.ok)return null;return await response.json()}catch(_){return null}
}

async function render(){
 if(rendering)return;rendering=true;
 try{
  ensureDualPhotoBridge();mergeVerifiedLearningSummary();suppressAutoRetry();injectRecentDeleteButtons();
  const host=document.getElementById('gpdManualRows');if(!host)return;
  let box=document.getElementById('gpdOfficialFallback');if(!box){box=document.createElement('div');box.id='gpdOfficialFallback';box.className='gpd-official-fallback';host.insertAdjacentElement('afterend',box)}
  const payload=await loadStatus();if(!payload){box.innerHTML='<h4>🔐 공식사이트 수동확인</h4><p>수동확인 상태를 불러오지 못했습니다.</p>';return}
  const rows=(Array.isArray(payload.registrations)?payload.registrations:[]).filter(eligible).slice(0,10);
  box.innerHTML=`<h4>🔐 자동 인증조회 OFF · 공식사이트 직접확인</h4><p>PSA/BGS/CGC/TAG/BRG 자동 인증조회는 사용하지 않습니다. 인증번호가 있는 자료는 공식 등급사 페이지를 사용자가 직접 열어 확인한 뒤 결과 화면을 등록합니다.</p>${rows.length?rows.map(row=>`<div class="gpd-official-row" data-official-row="${esc(row.registration_id)}"><div class="gpd-official-id"><b>${esc(row.company)} ${esc(row.grade)} · 인증 ${esc(row.certification_id)}</b><span>${esc(stateText(row))}</span>${row.manual_official_proof_registered?'<div class="gpd-official-state">✓ 공식검증 완료 · 통합학습 반영</div>':''}</div><div class="gpd-official-actions"><a class="gpd-official-open" href="${esc(row.official_reference_url)}" target="_blank" rel="noopener noreferrer">① 공식조회 열기</a><label class="gpd-official-proof">② 확인화면 선택<input class="gpd-official-file" type="file" accept="image/jpeg,image/png" data-proof="${esc(row.registration_id)}"></label><button type="button" class="gpd-official-submit" data-submit-proof="${esc(row.registration_id)}" disabled>③ 검증완료 등록</button><button type="button" class="gpd-official-delete" data-delete-registration="${esc(row.registration_id)}">🗑 잘못등록 삭제/취소</button></div></div>`).join(''):'<div class="gpd-official-help">현재 직접확인이 필요한 완성된 인증정보 항목이 없습니다.</div>'}<div class="gpd-official-help"><b>수동확인 통합관리:</b> 잘못 올린 미검증 자료는 <b>최근 수동등록</b>과 <b>공식사이트 직접확인</b> 양쪽의 삭제/취소 버튼으로 제거할 수 있습니다. 삭제하면 앞면·뒷면·수동 확인화면과 해당 등록목록을 함께 정리합니다. 공식검증 완료 자료는 삭제할 수 없습니다.<br>공식사이트 일치가 확인된 앞면·뒷면은 공식검증 자료로 통합관리하며 card-only ROI 방식의 RAW 결함/등급 보정학습 후보에도 사용합니다.</div>`;
  box.querySelectorAll('[data-proof]').forEach(input=>input.addEventListener('change',event=>{
   const file=event.currentTarget.files?.[0]||null,id=event.currentTarget.dataset.proof,row=event.currentTarget.closest('.gpd-official-row'),button=row?.querySelector('[data-submit-proof]'),label=row?.querySelector('.gpd-official-id span');
   if(file&&id){proofDrafts.set(id,file);if(button)button.disabled=false;if(label)label.textContent=`✓ 확인화면 선택 완료: ${file.name||'선택한 이미지'} · ③ 검증완료 등록을 누르세요.`}
   else{proofDrafts.delete(id);if(button)button.disabled=true}
  }));
  box.querySelectorAll('[data-submit-proof]').forEach(button=>button.addEventListener('click',submitProof));
  box.querySelectorAll('[data-delete-registration]').forEach(button=>button.addEventListener('click',deleteRegistration));
  mergeVerifiedLearningSummary();suppressAutoRetry();injectRecentDeleteButtons();
 }finally{rendering=false}
}

async function deleteRegistration(event){
 const button=event.currentTarget,registrationId=button.dataset.deleteRegistration,row=button.closest('.gpd-official-row,.gpd-manual-row');
 const title=row?.querySelector('b')?.textContent||registrationId||'이 자료';
 if(!registrationId)return;
 if(!globalThis.confirm(`잘못 올린 자료를 삭제할까요?\n\n${title}\n\n앞면·뒷면 사진과 수동 확인화면, 해당 등록목록이 함께 삭제됩니다. 공식검증 완료 자료는 삭제되지 않습니다.`))return;
 const old=button.textContent;button.disabled=true;button.textContent='삭제 중…';
 try{
  const response=await fetch('/api/manual-official-proof',{method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',body:JSON.stringify({action:'delete_registration',registration_id:registrationId})});
  const data=await response.json().catch(()=>({}));
  if(!response.ok||!data.deleted)throw new Error(data.error||`삭제 실패(${response.status})`);
  row?.remove();await sleep(250);location.reload();
 }catch(error){button.disabled=false;button.textContent=old;globalThis.alert(String(error?.message||'삭제하지 못했습니다.'))}
}
async function submitProof(event){
 const button=event.currentTarget,registrationId=button.dataset.submitProof,row=button.closest('.gpd-official-row'),label=row?.querySelector('.gpd-official-id span'),file=proofDrafts.get(registrationId);
 if(!file||!registrationId){if(label)label.textContent='② 확인화면을 먼저 선택하세요.';return}
 const old=button.textContent;button.disabled=true;button.textContent='검증 중…';
 try{
  if(label)label.textContent='공식 조회 화면 OCR 일치검사 중…';
  const image=await normalize(file);
  const response=await fetch('/api/manual-official-proof',{method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',body:JSON.stringify({registration_id:registrationId,proof_image_data_url:image,filename:file.name||''})});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(data.error||`등록 실패(${response.status})`);
  if(!data.accepted){
   const conflicts=data.proof?.conflicts||[],missing=data.proof?.missing||[];
   if(data.reason==='official_page_screenshot_ocr_incomplete')throw new Error(`공식페이지 OCR 정보 부족(${missing.join(', ')||'일부 항목'}) · 주소창/인증번호/등급이 보이게 다시 캡처하세요.`);
   throw new Error(`공식 조회 화면 일치검사 실패${conflicts.length?': '+conflicts.join(', '):''}`);
  }
  proofDrafts.delete(registrationId);
  if(label)label.textContent='✓ 공식사이트 직접확인 + 첨부화면 일치 · 검증완료';
  button.textContent='✓ 검증완료';
  await sleep(500);await render();
 }catch(error){button.disabled=false;button.textContent=old;if(label)label.textContent=String(error?.message||'공식 확인화면 등록 실패')}
}

async function install(){
 if(installed)return;const host=document.getElementById('gpdManualRows');if(!host)return;
 installed=true;ensureDualPhotoBridge();style();installSummaryObserver();mergeVerifiedLearningSummary();suppressAutoRetry();injectRecentDeleteButtons();await render();
 const observer=new MutationObserver(()=>{ensureDualPhotoBridge();suppressAutoRetry();injectRecentDeleteButtons()});observer.observe(host,{childList:true,subtree:true});
 setInterval(()=>{mergeVerifiedLearningSummary();render()},30000);
}
function boot(){let tries=0;const timer=setInterval(()=>{tries++;if(document.getElementById('gpdManualRows')){clearInterval(timer);ensureDualPhotoBridge();install()}else if(tries>80)clearInterval(timer)},250)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();