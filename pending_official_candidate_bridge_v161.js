(()=>{
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
let busy=false;
const proofFiles=new Map();
function style(){
  if(document.getElementById('gpdPendingOfficialV164Style'))return;
  const s=document.createElement('style');
  s.id='gpdPendingOfficialV164Style';
  s.textContent=`
#gpdPendingOfficialV161{margin-top:12px;border:1px solid #dbeafe;border-radius:14px;background:#fff;overflow:hidden}
.gpd-pending-toggle{width:100%;border:0;background:#eff6ff;color:#1e3a8a;padding:13px 15px;text-align:left;font-weight:900;font-size:13px;cursor:pointer}
.gpd-pending-body{padding:10px 12px}.gpd-pending-note{font-size:10px;line-height:1.55;color:#475569;margin:0 0 8px}
.gpd-pending-row{border-top:1px solid #e2e8f0;padding:10px 0}.gpd-pending-row:first-of-type{border-top:0}
.gpd-pending-title{font-size:12px;font-weight:900;color:#0f172a}.gpd-pending-meta{font-size:10px;color:#64748b;margin-top:3px;line-height:1.5}
.gpd-pending-certbox{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:7px;padding:7px 8px;border-radius:9px;background:#f8fafc;border:1px solid #e2e8f0}.gpd-pending-certbox b{font-size:11px;color:#0f172a}
.gpd-pending-copy{border:0;border-radius:8px;padding:7px 9px;background:#e0e7ff;color:#3730a3;font-size:10px;font-weight:900;cursor:pointer}
.gpd-pending-actions{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:8px;align-items:center}
.gpd-pending-open,.gpd-pending-pick,.gpd-pending-submit,.gpd-pending-notfound{border:0;border-radius:9px;padding:10px;font-size:10px;font-weight:900;text-decoration:none;display:flex;align-items:center;justify-content:center;white-space:nowrap;min-height:40px}
.gpd-pending-open{background:#2563eb;color:#fff}.gpd-pending-pick{background:#2563eb;color:#fff;cursor:pointer}.gpd-pending-submit{background:#0f766e;color:#fff;cursor:pointer}.gpd-pending-notfound{background:#fee2e2;color:#b91c1c;cursor:pointer}
.gpd-pending-submit:disabled,.gpd-pending-notfound:disabled{opacity:.38;cursor:not-allowed;filter:grayscale(.15)}
.gpd-pending-file{position:absolute!important;width:1px!important;height:1px!important;opacity:.001!important;pointer-events:none!important}
.gpd-pending-state{font-size:10px;margin-top:7px;color:#0f766e;font-weight:800;line-height:1.45;padding:6px 8px;border-radius:8px;background:#ecfdf5}
.gpd-pending-state.waiting{color:#92400e;background:#fffbeb}.gpd-pending-state.error{color:#b91c1c;background:#fef2f2}
.gpd-pending-warning{font-size:9px;margin-top:7px;padding:7px 8px;border-radius:8px;background:#fff7ed;color:#9a3412;line-height:1.5}
@media(max-width:620px){.gpd-pending-actions{grid-template-columns:1fr 1fr}.gpd-pending-open,.gpd-pending-pick,.gpd-pending-submit,.gpd-pending-notfound{width:100%}}
`;
  document.head.appendChild(s);
}
async function fileDataUrl(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result||''));r.onerror=()=>reject(new Error('파일을 읽지 못했습니다.'));r.readAsDataURL(file)})}
async function normalize(file){
  if(!file||!['image/jpeg','image/png'].includes(file.type))throw new Error('공식 조회 결과 화면을 JPG 또는 PNG로 선택하세요.');
  if(file.size>12_000_000)throw new Error('공식 조회 화면이 12MB를 초과합니다.');
  if(!globalThis.createImageBitmap)return fileDataUrl(file);
  const b=await createImageBitmap(file,{imageOrientation:'from-image'});
  try{
    const scale=Math.min(1,2200/Math.max(b.width,b.height));
    const c=document.createElement('canvas');
    c.width=Math.max(320,Math.round(b.width*scale));c.height=Math.max(320,Math.round(b.height*scale));
    const x=c.getContext('2d');if(!x)throw new Error('사진 변환 실패');
    x.fillStyle='#fff';x.fillRect(0,0,c.width,c.height);x.drawImage(b,0,0,c.width,c.height);
    for(const q of [.9,.82,.74]){const v=c.toDataURL('image/jpeg',q);if(v.length<8_000_000)return v}
    throw new Error('공식 조회 화면을 8MB 이하로 줄이지 못했습니다.');
  }finally{b.close?.()}
}
function anchor(){return document.getElementById('gpdExistingRevalidationStatus')||[...document.querySelectorAll('button')].find(b=>String(b.textContent||'').includes('기존 등록사진')&&String(b.textContent||'').includes('재검증'))}
async function load(){try{const r=await fetch('/api/pending-official-candidates?_='+Date.now(),{cache:'no-store'});if(!r.ok)return null;return await r.json()}catch(_){return null}}
function gameLabel(v){return ({pokemon:'포켓몬',onepiece:'원피스',naruto:'나루토'})[String(v||'').toLowerCase()]||String(v||'미분류')}
function officialOpenUrl(url,cert,company){const c=String(company||'').toUpperCase();if(c==='BRG')return 'https://www.brgcard.com/certification';if(c!=='BGS')return url;try{const u=new URL(url,location.href);u.searchParams.set('flag','1');u.searchParams.set('item_id',cert);u.searchParams.set('item_type','BGS');return u.toString()}catch(_){return url}}
async function copyText(text){const value=String(text||'').trim();if(!value)return false;try{if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(value);return true}}catch(_){}try{const t=document.createElement('textarea');t.value=value;t.setAttribute('readonly','');t.style.position='fixed';t.style.opacity='0';document.body.appendChild(t);t.select();const ok=document.execCommand('copy');t.remove();return !!ok}catch(_){return false}}
async function postProof(payload){const r=await fetch('/api/pending-official-candidate-proof',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(data.error||`처리 실패 (${r.status})`);return data}
function setState(el,text,kind=''){el.className='gpd-pending-state'+(kind?' '+kind:'');el.textContent=text}
function currentProof(row,input){return input?.files?.[0]||proofFiles.get(row.dataset.candidate)?.file||null}
async function render(){
  if(busy)return;busy=true;
  try{
    style();const a=anchor();if(!a)return;
    let box=document.getElementById('gpdPendingOfficialV161');
    if(!box){box=document.createElement('div');box.id='gpdPendingOfficialV161';a.insertAdjacentElement('afterend',box)}
    const p=await load();if(!p||!p.ok||!Number(p.pending_count||0)){box.hidden=true;return}
    box.hidden=false;const rows=Array.isArray(p.candidates)?p.candidates:[];const expanded=box.dataset.expanded==='1';
    box.innerHTML=`<button type="button" class="gpd-pending-toggle">${expanded?'▼':'▶'} 공식검증 미완료 ${Number(p.pending_count||0)}건 직접확인/등록</button><div class="gpd-pending-body" ${expanded?'':'hidden'}><p class="gpd-pending-note">공식 등급사 사이트에서 확인한 뒤 <b>② 갤러리에서 확인화면 선택</b>으로 저장된 캡처를 고르세요. 선택한 캡처는 화면 자동갱신 중에도 유지되며 <b>③ 검증완료 등록</b>과 <b>④ 조회결과 없음 → 후보삭제</b>가 활성화됩니다. <b>BRG 안내:</b> 인증번호가 포함된 직접 URL에서 서버 오류가 날 수 있어 BRG는 조회 폼만 열고 인증번호를 자동복사합니다. 붙여넣어 조회하세요. <b>Application error / server-side exception / Digest 화면은 조회결과 없음이 아니므로 ④로 삭제하지 마세요.</b></p>${rows.map(row=>{const cid=String(row.candidate_id||'');const cert=String(row.certification_id||'');const url=officialOpenUrl(String(row.official_reference_url||''),cert,row.company);const draft=proofFiles.get(cid);const ready=!!draft?.file;return `<div class="gpd-pending-row" data-candidate="${esc(cid)}" data-cert="${esc(cert)}"><div class="gpd-pending-title">${esc(row.company)} ${esc(row.grade)} · ${esc(gameLabel(row.game))}</div><div class="gpd-pending-meta">인증 ${esc(cert)} · ${esc(row.source||'공개후보')}</div><div class="gpd-pending-certbox"><b>인증번호 ${esc(cert)}</b><button type="button" class="gpd-pending-copy">인증번호 복사</button></div><div class="gpd-pending-actions"><a class="gpd-pending-open" href="${esc(url)}" target="_blank" rel="noopener noreferrer">① 공식조회 열기 + 번호복사</a><button type="button" class="gpd-pending-pick">${ready?'② 확인화면 다시선택':'② 갤러리에서 확인화면 선택'}</button><input type="file" class="gpd-pending-file" accept="image/jpeg,image/png"><button type="button" class="gpd-pending-submit" ${ready?'':'disabled'}>③ 검증완료 등록</button><button type="button" class="gpd-pending-notfound" ${ready?'':'disabled'}>④ 조회결과 없음 → 후보삭제</button></div><div class="gpd-pending-state ${ready?'':'waiting'}">${ready?`✓ 확인화면 선택 완료: ${esc(draft.name||'선택한 이미지')} · 이제 ③ 또는 ④를 누르세요.`:'먼저 ② 갤러리에서 확인화면 선택을 눌러 공식사이트 결과 캡처를 선택하세요.'}</div><div class="gpd-pending-warning">조회 결과가 정상 존재하면 ③, 공식사이트에 기록이 없으면 ④를 사용하세요. ④는 공식검증 완료 자료에는 적용되지 않습니다.</div></div>`}).join('')}</div>`;
    box.querySelector('.gpd-pending-toggle')?.addEventListener('click',()=>{box.dataset.expanded=expanded?'0':'1';render()});
    box.querySelectorAll('.gpd-pending-row').forEach(row=>{
      const input=row.querySelector('.gpd-pending-file'),pick=row.querySelector('.gpd-pending-pick'),button=row.querySelector('.gpd-pending-submit'),reject=row.querySelector('.gpd-pending-notfound'),state=row.querySelector('.gpd-pending-state'),copy=row.querySelector('.gpd-pending-copy'),open=row.querySelector('.gpd-pending-open'),cert=row.dataset.cert||'',cid=row.dataset.candidate||'';
      pick?.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();try{input.value=''}catch(_){}input?.removeAttribute('capture');input?.click()});
      copy?.addEventListener('click',async()=>{const ok=await copyText(cert);setState(state,ok?`인증번호 ${cert} 복사 완료 · 공식사이트 입력칸에 붙여넣기`:'인증번호 복사 실패 · 번호를 길게 눌러 직접 복사하세요.',ok?'':'error')});
      open?.addEventListener('click',()=>{copyText(cert).then(ok=>setState(state,ok?`인증번호 ${cert} 자동복사 완료 · 공식사이트에서 조회 후 화면을 캡처하세요.`:'공식사이트 열림 · 인증번호 자동복사 실패','waiting'))});
      input?.addEventListener('change',()=>{const file=input.files?.[0]||null;if(file){proofFiles.set(cid,{file,name:file.name||'공식조회화면'});button.disabled=false;reject.disabled=false;pick.textContent='② 확인화면 다시선택';setState(state,`✓ 확인화면 선택 완료: ${file.name||'선택한 이미지'} · ③/④ 활성화됨`)}else{proofFiles.delete(cid);button.disabled=true;reject.disabled=true;setState(state,'사진이 선택되지 않았습니다. ②를 다시 누르세요.','waiting')}});
      button?.addEventListener('click',async()=>{const file=currentProof(row,input);if(!file){setState(state,'② 확인화면을 먼저 선택하세요.','error');return}button.disabled=true;reject.disabled=true;setState(state,'공식 조회 화면 OCR 일치검사 중…','waiting');try{const proof_image=await normalize(file);const data=await postProof({candidate_id:cid,proof_image});if(!data.accepted){setState(state,'미등록: '+String(data.error||'정보 불일치'),'error');button.disabled=false;reject.disabled=false;return}proofFiles.delete(cid);setState(state,'✓ 공식검증 완료 · 학습자료 승격');setTimeout(()=>location.reload(),900)}catch(e){setState(state,'오류: '+String(e?.message||e),'error');button.disabled=false;reject.disabled=false}});
      reject?.addEventListener('click',async()=>{const file=currentProof(row,input);if(!file){setState(state,'②에서 "검색된 기록이 없습니다" 화면을 먼저 선택하세요.','error');return}const typed=prompt(`공식사이트에서 검색 기록이 없음을 확인했습니다.\n삭제 확인을 위해 인증번호 ${cert} 를 정확히 입력하세요.`,'');if(typed===null)return;const normalized=String(typed).replace(/[^A-Za-z0-9]/g,'').toUpperCase();const expected=String(cert).replace(/[^A-Za-z0-9]/g,'').toUpperCase();if(normalized!==expected){setState(state,'삭제 취소: 입력한 인증번호가 일치하지 않습니다.','error');return}if(!confirm('공식검증 완료 자료가 아닌 이 후보만 삭제합니다. 조회결과 없음 화면은 감사 증거로 보관됩니다. 계속할까요?'))return;button.disabled=true;reject.disabled=true;setState(state,'조회결과 없음 증거 보관 + 미검증 후보 삭제 중…','waiting');try{const proof_image=await normalize(file);const data=await postProof({action:'official_not_found',candidate_id:cid,proof_image,certification_id_confirmation:typed,confirm_no_record:true});if(!data.accepted||!data.deleted)throw new Error(data.error||'후보 삭제 실패');proofFiles.delete(cid);setState(state,`✓ 공식조회 결과 없음 확인 · 후보 ${Number(data.deleted_rows||1)}건 삭제 · 증거 보관 완료`);setTimeout(()=>location.reload(),900)}catch(e){setState(state,'삭제 실패: '+String(e?.message||e),'error');button.disabled=false;reject.disabled=false}});
    });
  }finally{busy=false}
}
function install(){
  render();
  setInterval(()=>{if(!document.hidden)render()},12000);
  const obs=new MutationObserver(muts=>{if(busy)return;const box=document.getElementById('gpdPendingOfficialV161');if(box&&muts.every(m=>box.contains(m.target)))return;setTimeout(render,250)});
  obs.observe(document.documentElement,{childList:true,subtree:true});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
