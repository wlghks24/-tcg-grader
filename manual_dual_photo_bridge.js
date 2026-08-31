(()=>{
'use strict';
let installed=false,submitting=false;
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
function enhance(){
 const form=document.getElementById('gpdManualForm');if(!form||installed)return false;installed=true;
 const front=document.getElementById('gpdManualPhoto');if(!front)return false;
 const frontLabel=front.closest('label');if(frontLabel){const text=[...frontLabel.childNodes].find(n=>n.nodeType===Node.TEXT_NODE);if(text)text.textContent='② 등급 슬랩 앞면 사진';}
 const backLabel=document.createElement('label');backLabel.innerHTML='③ 등급 슬랩 뒷면 사진<input id="gpdManualBackPhoto" type="file" accept="image/jpeg,image/png" required>';
 frontLabel?.insertAdjacentElement('afterend',backLabel);
 const quick=form.querySelector('.gpd-manual-quick');if(quick){quick.style.gridTemplateColumns='minmax(120px,.55fr) minmax(0,1fr) minmax(0,1fr)';}
 const policy=form.querySelector('.gpd-manual-policy');if(policy)policy.innerHTML='카드게임을 선택하고 <b>등급 슬랩 앞면 + 뒷면 사진 2장</b>을 모두 등록합니다. 앞면은 등급사·등급·인증번호 OCR에 사용하고, 뒷면은 같은 등록건의 별도 증빙사진으로 저장합니다. 두 사진이 모두 있어야 수동등록을 진행하며, 공식사이트 확인 전에는 RAW 등급 보정학습에 사용하지 않습니다.';
 const button=document.getElementById('gpdManualSubmit');if(button)button.textContent='앞면 + 뒷면 2장으로 수동등록';
 form.addEventListener('submit',submit,true);
 return true;
}
async function submit(event){
 event.preventDefault();event.stopImmediatePropagation();if(submitting)return;
 const front=document.getElementById('gpdManualPhoto')?.files?.[0];
 const back=document.getElementById('gpdManualBackPhoto')?.files?.[0];
 const status=document.getElementById('gpdManualStatus'),button=document.getElementById('gpdManualSubmit');
 if(!front||!back){if(status)status.textContent='앞면과 뒷면 사진을 모두 선택하세요.';return;}
 submitting=true;if(button)button.disabled=true;if(status)status.textContent='앞면·뒷면 사진 메타데이터 제거·용량 최적화 중…';
 try{
  const [frontImage,backImage]=await Promise.all([normalize(front),normalize(back)]);
  if(frontImage===backImage)throw new Error('앞면과 뒷면에 같은 사진을 선택했습니다.');
  const gradeText=document.getElementById('gpdManualGrade')?.value.trim()||'';
  const body={
   entry_mode:'ocr_first_front_back',
   company:document.getElementById('gpdManualCompany')?.value||'',
   game:document.getElementById('gpdManualGame')?.value||'',
   grade:gradeText===''?null:Number(gradeText),
   certification_id:document.getElementById('gpdManualCert')?.value||'',
   card_name:document.getElementById('gpdManualCardName')?.value||'',
   card_number:document.getElementById('gpdManualCardNumber')?.value||'',
   filename:front.name||'',back_filename:back.name||'',
   image_data_url:frontImage,back_image_data_url:backImage,
   note:'manual_front_back_pair'
  };
  if(status)status.textContent='앞면 OCR + 뒷면 증빙사진을 같은 등록건으로 저장 중…';
  const response=await fetch('/api/graded-photo-manual-registration',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'});
  const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.error||`등록 실패(${response.status})`);
  if(status)status.textContent=data.duplicate?'기존 앞면 등록건에 뒷면 사진을 확인했습니다.':'앞면·뒷면 2장 등록 완료 · 공식사이트 수동확인 대기';
  document.getElementById('gpdManualPhoto').value='';document.getElementById('gpdManualBackPhoto').value='';
  if(typeof window.loadManualRegistrations==='function')await window.loadManualRegistrations();
  await sleep(500);
 }catch(error){if(status)status.textContent=location.hostname.endsWith('github.io')?'PC·태블릿 로컬/Tailscale 서버 주소에서 등록하세요.':String(error?.message||'앞뒤 사진 등록 실패');}
 finally{submitting=false;if(button)button.disabled=false;}
}
function boot(){let tries=0;const timer=setInterval(()=>{tries++;if(enhance()||tries>100)clearInterval(timer)},250)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
