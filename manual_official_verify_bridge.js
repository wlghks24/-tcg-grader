(()=>{
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let installed=false;
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
 .gpd-official-fallback{margin-top:12px;border:1px solid #f59e0b55;background:#fffbeb;border-radius:13px;padding:11px;color:#78350f}
 .gpd-official-fallback h4{margin:0 0 5px;font-size:13px}.gpd-official-fallback p{font-size:10px;line-height:1.55;margin:4px 0;color:#92400e}
 .gpd-official-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;padding:10px 0;border-top:1px solid #fde68a;align-items:center}.gpd-official-row:first-of-type{margin-top:8px}
 .gpd-official-id{min-width:0}.gpd-official-id b,.gpd-official-id span,.gpd-official-id small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.gpd-official-id b{font-size:12px}.gpd-official-id span,.gpd-official-id small{font-size:10px;color:#92400e;margin-top:2px}
 .gpd-official-actions{display:grid;grid-template-columns:auto auto;gap:6px;align-items:center}.gpd-official-open,.gpd-official-proof{display:inline-flex;align-items:center;justify-content:center;border:0;border-radius:9px;padding:8px 9px;font-weight:800;font-size:10px;text-decoration:none;white-space:nowrap}.gpd-official-open{background:#2563eb;color:#fff}.gpd-official-proof{background:#0f766e;color:#fff;margin:0;width:auto}.gpd-official-file{display:none}.gpd-official-state{font-size:10px;font-weight:800;color:#047857;margin-top:3px}
 .gpd-official-help{margin-top:8px;padding:8px;border-radius:9px;background:#fff7ed;font-size:10px;line-height:1.6;color:#9a3412}
 @media(max-width:520px){.gpd-official-row{grid-template-columns:1fr}.gpd-official-actions{grid-template-columns:1fr 1fr}.gpd-official-open,.gpd-official-proof{width:100%}}
 `;document.head.appendChild(el);
}
function eligible(row){return row&&row.official_result!==true&&row.identity_complete&&row.official_reference_url}
function stateText(row){
 if(row.manual_official_proof_registered)return '공식 페이지 캡처 일치 · 참고등록 완료';
 if(row.manual_official_proof_state==='conflict')return '캡처의 등급사·인증번호·등급이 불일치';
 if(row.verification_state==='deferred_by_cooldown')return '자동조회 쿨다운 중';
 if(row.verification_state==='processing_failed')return '자동검증 실패 · 수동확인 가능';
 return '자동검증 대기 · 수동확인 가능';
}
async function loadStatus(){
 try{const response=await fetch('/api/manual-official-proof-status?_='+Date.now(),{cache:'no-store'});if(!response.ok)return null;return await response.json()}catch(_){return null}
}
async function render(){
 const host=document.getElementById('gpdManualRows');if(!host)return;
 let box=document.getElementById('gpdOfficialFallback');if(!box){box=document.createElement('div');box.id='gpdOfficialFallback';box.className='gpd-official-fallback';host.insertAdjacentElement('afterend',box)}
 const payload=await loadStatus();if(!payload){box.innerHTML='<h4>🔐 공식사이트 직접확인</h4><p>수동확인 상태를 불러오지 못했습니다.</p>';return}
 const rows=(Array.isArray(payload.registrations)?payload.registrations:[]).filter(eligible).slice(0,10);
 box.innerHTML=`<h4>🔐 403/429·쿨다운 시 공식사이트 직접확인</h4><p>자동 인증조회가 막히면 공식 등급사 페이지를 직접 열어 인증번호와 등급을 확인한 뒤, 그 결과 화면 캡처를 등록할 수 있습니다.</p>${rows.length?rows.map(row=>`<div class="gpd-official-row" data-official-row="${esc(row.registration_id)}"><div class="gpd-official-id"><b>${esc(row.company)} ${esc(row.grade)} · 인증 ${esc(row.certification_id)}</b><span>${esc(stateText(row))}</span>${row.retry_after_seconds?`<small>자동 재검증 대기 약 ${Math.ceil(Number(row.retry_after_seconds)/60)}분</small>`:''}${row.manual_official_proof_registered?'<div class="gpd-official-state">✓ 수동 참고등록 완료 · 나중에 자동 공식검증 시 승격</div>':''}</div><div class="gpd-official-actions"><a class="gpd-official-open" href="${esc(row.official_reference_url)}" target="_blank" rel="noopener noreferrer">① 공식조회 열기</a><label class="gpd-official-proof">② 확인화면 등록<input class="gpd-official-file" type="file" accept="image/jpeg,image/png" data-proof="${esc(row.registration_id)}"></label></div></div>`).join(''):'<div class="gpd-official-help">현재 직접확인이 필요한 완성된 인증정보 항목이 없습니다.</div>'}<div class="gpd-official-help">캡처 OCR에서 <b>등급사 + 인증번호 + 등급</b>이 현재 등록자료와 모두 일치해야 참고등록됩니다. 이 수동 캡처만으로는 RAW 카드 등급 보정값을 바꾸지 않으며, 이후 자동 공식조회가 성공하면 정상 공식검증으로 승격됩니다.</div>`;
 box.querySelectorAll('[data-proof]').forEach(input=>input.addEventListener('change',submitProof));
}
async function submitProof(event){
 const input=event.currentTarget,file=input.files?.[0],registrationId=input.dataset.proof,row=input.closest('.gpd-official-row'),label=row?.querySelector('.gpd-official-id span');
 if(!file||!registrationId)return;
 try{
  if(label)label.textContent='공식 조회 화면 OCR 확인 중…';
  const image=await normalize(file);
  const response=await fetch('/api/manual-official-proof',{method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',body:JSON.stringify({registration_id:registrationId,proof_image_data_url:image,filename:file.name||''})});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(data.error||`등록 실패(${response.status})`);
  if(!data.accepted){const conflicts=data.proof?.conflicts||[];throw new Error('공식 조회 화면 정보 불일치: '+conflicts.join(', '))}
  if(label)label.textContent='공식 페이지 캡처 일치 · 참고등록 완료';
  input.value='';await sleep(500);await render();
 }catch(error){if(label)label.textContent=String(error?.message||'공식 확인화면 등록 실패');input.value=''}
}
async function install(){
 if(installed)return;const host=document.getElementById('gpdManualRows');if(!host)return;installed=true;style();await render();
 const observer=new MutationObserver(()=>{if(document.getElementById('gpdManualRows'))render()});observer.observe(host,{childList:true,subtree:true});
 setInterval(render,30000);
}
function boot(){let tries=0;const timer=setInterval(()=>{tries++;if(document.getElementById('gpdManualRows')){clearInterval(timer);install()}else if(tries>80)clearInterval(timer)},250)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
