/* v207 OCR + Pokémon generation display: 1/4/8 OCR with evidence-bounded era inference. */
(()=>{
'use strict';
const MEMORY_KEY='tcg_card_identity_learning_v1',MAX_LOCAL=500;
const byId=id=>document.getElementById(id);
const safeText=value=>String(value??'').replace(/[\u0000-\u001f\u007f]/g,' ').trim().slice(0,180);
const gameName=value=>['pokemon','onepiece','naruto'].includes(value)?value:'pokemon';

function generationText(value){return String(value??'').normalize?.('NFKC').toUpperCase().replace(/[\u0000-\u001f\u007f]/g,' ').replace(/\s+/g,' ').trim().slice(0,8000)}
function expansionFromCardNumber(value){
 const n=generationText(value).replace(/\s+/g,'');
 let m;
 if((m=n.match(/^SV(?:-?P|\d{1,2}[A-Z]{0,2})/)))return m[0];
 if((m=n.match(/^SM\d{1,2}[A-Z]{0,2}/)))return m[0];
 if((m=n.match(/^S(?!M|V)\d{1,2}[A-Z]{0,2}/)))return m[0];
 if((m=n.match(/^M\d[A-Z]?/)))return m[0];
 if((m=n.match(/^XY\d{0,2}[A-Z]{0,2}/)))return m[0]||'XY';
 if((m=n.match(/^BW\d{0,2}[A-Z]{0,2}/)))return m[0]||'BW';
 if((m=n.match(/^DPT?[A-Z0-9]{0,4}/)))return m[0];
 return '';
}
function expansionFromOcr(text){
 const t=generationText(text),patterns=[
  /(?:^|[^A-Z0-9])(SV(?:-?P|\d{1,2}[A-Z]{0,2}))(?=[^A-Z0-9]|$)/,
  /(?:^|[^A-Z0-9])(SM\d{1,2}[A-Z]{0,2})(?=[^A-Z0-9]|$)/,
  /(?:^|[^A-Z0-9])(S(?!M|V)\d{1,2}[A-Z]{0,2})(?=[^A-Z0-9]|$)/,
  /(?:^|[^A-Z0-9])(M\d[A-Z]?)(?=[^A-Z0-9]|$)/,
  /(?:^|[^A-Z0-9])(XY\d{0,2}[A-Z]{0,2})(?=[^A-Z0-9]|$)/,
  /(?:^|[^A-Z0-9])(BW\d{0,2}[A-Z]{0,2})(?=[^A-Z0-9]|$)/,
  /(?:^|[^A-Z0-9])(DPT?[A-Z0-9]{0,4})(?=[^A-Z0-9]|$)/
 ];
 for(const pattern of patterns){const m=t.match(pattern);if(m)return m[1]}
 return '';
}
function regulationFromEvidence(input,text){
 const direct=generationText(input?.regulation_mark||'').match(/^[A-J]$/)?.[0]||'';
 if(direct)return direct;
 const t=generationText(text);
 const m=t.match(/(?:REGULATION|REG\.?|レギュレーション|레귤레이션)(?:\s*(?:MARK|マーク|마크))?\s*[:#-]?\s*([A-J])(?:\b|$)/);
 return m?.[1]||'';
}
function yearFromEvidence(input,text){
 const direct=Number(input?.year||input?.copyright_year||0);
 if(Number.isInteger(direct)&&direct>=1996&&direct<=2099)return direct;
 const t=generationText(text),years=[];
 for(const match of t.matchAll(/(?:©|COPYRIGHT\s*)?\s*((?:19|20)\d{2})/g)){
  const year=Number(match[1]);if(year>=1996&&year<=2099)years.push(year);
 }
 return years.length?Math.max(...years):null;
}
function generationBySetCode(code){
 const c=generationText(code).replace(/\s+/g,'');
 if(/^SV/.test(c))return {generation:9,generation_label:'9세대',series:'스칼렛&바이올렛',era:'SV'};
 if(/^M\d/.test(c))return {generation:9,generation_label:'9세대 계열',series:'MEGA 시리즈',era:'MEGA'};
 if(/^SM/.test(c))return {generation:7,generation_label:'7세대',series:'썬&문',era:'SM'};
 if(/^S(?!M|V)\d/.test(c))return {generation:8,generation_label:'8세대',series:'소드&실드',era:'S'};
 if(/^XY/.test(c))return {generation:6,generation_label:'6세대',series:'XY',era:'XY'};
 if(/^BW/.test(c))return {generation:5,generation_label:'5세대',series:'BW',era:'BW'};
 if(/^DPT?/.test(c))return {generation:4,generation_label:'4세대',series:/^DPT/.test(c)?'DPt':'DP',era:/^DPT/.test(c)?'DPt':'DP'};
 return null;
}
function generationByRegulation(mark){
 if(/^[ABC]$/.test(mark))return {generation:7,generation_label:'7세대',series:'썬&문',era:'SM'};
 if(/^[DEF]$/.test(mark))return {generation:8,generation_label:'8세대',series:'소드&실드',era:'S'};
 if(/^[GHI]$/.test(mark))return {generation:9,generation_label:'9세대',series:'스칼렛&바이올렛',era:'SV'};
 if(mark==='J')return {generation:9,generation_label:'9세대 계열',series:'MEGA/현행 시리즈',era:'MEGA'};
 return null;
}
function generationByYear(year){
 if(year>=2023)return {generation:9,generation_label:'9세대',series:'SV/MEGA 시대',era:'CURRENT'};
 if(year>=2020)return {generation:8,generation_label:'8세대',series:'소드&실드 시대',era:'S'};
 if(year>=2017)return {generation:7,generation_label:'7세대',series:'썬&문 시대',era:'SM'};
 if(year>=2014)return {generation:6,generation_label:'6세대',series:'XY 시대',era:'XY'};
 if(year>=2011)return {generation:5,generation_label:'5세대',series:'BW 시대',era:'BW'};
 if(year>=2007)return {generation:4,generation_label:'4세대',series:'DP/DPt 시대',era:'DP'};
 return null;
}
function inferPokemonGeneration(input={}){
 const game=String(input.game||'pokemon').trim().toLowerCase();
 if(game!=='pokemon')return {status:'not_applicable',game,generation:null,confidence:0,basis:[]};
 const text=[input.ocr_text,input.card_name,input.market_key].map(generationText).filter(Boolean).join(' ');
 const expansion=expansionFromCardNumber(input.card_number)||expansionFromOcr(text);
 const byExpansion=generationBySetCode(expansion);
 if(byExpansion)return {status:'estimated',game:'pokemon',...byExpansion,expansion_code:expansion,regulation_mark:regulationFromEvidence(input,text)||'',year:yearFromEvidence(input,text),confidence:.98,confidence_level:'high',basis:[`확장팩 코드 ${expansion}`],note:byExpansion.era==='MEGA'?'MEGA는 별도 TCG 시리즈명이므로 세대와 시리즈를 함께 표시합니다.':'확장팩 코드 기준 추정'};
 const regulation=regulationFromEvidence(input,text),byReg=generationByRegulation(regulation);
 if(byReg)return {status:'estimated',game:'pokemon',...byReg,expansion_code:'',regulation_mark:regulation,year:yearFromEvidence(input,text),confidence:.88,confidence_level:'medium',basis:[`레귤레이션 마크 ${regulation}`],note:'레귤레이션 마크는 플레이 규정 표기이며 세대는 시리즈 대응으로 추정'};
 const year=yearFromEvidence(input,text),byYear=generationByYear(year);
 if(byYear)return {status:'estimated',game:'pokemon',...byYear,expansion_code:'',regulation_mark:'',year,confidence:.64,confidence_level:'low',basis:[`©/제작연도 ${year}`],note:'연도만 확인되어 세대는 보조 추정'};
 if(year&&year<2007)return {status:'legacy',game:'pokemon',generation:null,generation_label:'고전 카드',series:'초기~ADV/PCG 계열',era:'LEGACY',expansion_code:'',regulation_mark:'',year,confidence:.55,confidence_level:'low',basis:[`©/제작연도 ${year}`],note:'고전 카드는 확장팩 코드 확인 전 세대 번호를 단정하지 않습니다.'};
 return {status:'unknown',game:'pokemon',generation:null,generation_label:'세대 확인 필요',series:'확장팩 코드·레귤레이션·©연도 OCR 부족',era:'UNKNOWN',expansion_code:'',regulation_mark:'',year:null,confidence:0,confidence_level:'unknown',basis:[],note:'근거가 부족해 세대를 생성하지 않았습니다.'};
}
function renderPokemonGeneration(info,game='pokemon'){
 const box=byId('simplePokemonGeneration');if(!box)return info;
 const isPokemon=gameName(game)==='pokemon';box.hidden=!isPokemon;if(!isPokemon)return info;
 const badge=byId('pokemonGenerationBadge'),title=byId('pokemonGenerationTitle'),meta=byId('pokemonGenerationMeta');
 if(!info||info.status==='pending'){if(badge)badge.textContent='…';if(title)title.textContent='세대 판별 중…';if(meta)meta.textContent='앞면 OCR에서 확장팩 코드 · 레귤레이션 · ©연도를 확인합니다.';return info}
 if(info.status==='estimated'){if(badge)badge.textContent=info.generation_label||(`${info.generation}세대`);if(title)title.textContent=`${info.generation_label||info.generation+'세대'} · ${info.series}`;const evidence=[info.expansion_code&&`확장팩 ${info.expansion_code}`,info.regulation_mark&&`레귤레이션 ${info.regulation_mark}`,info.year&&`©${info.year}`].filter(Boolean);if(meta)meta.textContent=`${evidence.join(' · ')||info.basis?.join(' · ')||'OCR 근거'} · 신뢰도 ${info.confidence_level==='high'?'높음':info.confidence_level==='medium'?'중간':'보조'}`;return info}
 if(badge)badge.textContent=info.status==='legacy'?'고전':'?';if(title)title.textContent=info.status==='legacy'?info.generation_label:'세대 확인 필요';if(meta)meta.textContent=info.status==='legacy'?`${info.series}${info.year?' · ©'+info.year:''} · 확장팩 코드 확인 권장`:'확장팩 코드·레귤레이션·©연도를 충분히 읽지 못했습니다.';return info
}
window.TCGPokemonGeneration=Object.freeze({version:'v207',infer:inferPokemonGeneration,render:renderPokemonGeneration});
function localRows(){try{const value=JSON.parse(localStorage.getItem(MEMORY_KEY)||'[]');return Array.isArray(value)?value.filter(row=>row&&row.confirmed===true).slice(-MAX_LOCAL):[]}catch(_){return []}}
function hamming(a,b){if(!/^[0-9a-f]{16}$/.test(a)||!/^[0-9a-f]{16}$/.test(b))return 65;let value=BigInt('0x'+a)^BigInt('0x'+b),count=0;while(value){count+=Number(value&1n);value>>=1n}return count}
async function imageArtifacts(file){const image=await window.loadCardImage(file),w=image.naturalWidth,h=image.naturalHeight;if(!w||!h||w*h>24000000)throw new Error('image_dimensions');const scale=Math.min(1,1400/w,1900/h),dataCanvas=document.createElement('canvas');dataCanvas.width=Math.max(1,Math.round(w*scale));dataCanvas.height=Math.max(1,Math.round(h*scale));const dataCtx=dataCanvas.getContext('2d');if(!dataCtx)throw new Error('canvas');dataCtx.drawImage(image,0,0,dataCanvas.width,dataCanvas.height);const hashCanvas=document.createElement('canvas');hashCanvas.width=9;hashCanvas.height=8;const hashCtx=hashCanvas.getContext('2d',{willReadFrequently:true});if(!hashCtx)throw new Error('canvas');hashCtx.drawImage(image,0,0,9,8);const pixels=hashCtx.getImageData(0,0,9,8).data,gray=[];for(let i=0;i<pixels.length;i+=4)gray.push((pixels[i]*299+pixels[i+1]*587+pixels[i+2]*114)/1000);let bits=0n;for(let y=0;y<8;y++)for(let x=0;x<8;x++)bits=(bits<<1n)|(gray[y*9+x]>gray[y*9+x+1]?1n:0n);return {hash:bits.toString(16).padStart(16,'0'),data:dataCanvas.toDataURL('image/jpeg',.84)}}
async function browserText(file){if(typeof window.TextDetector!=='function'||typeof createImageBitmap!=='function')return '';try{const bitmap=await createImageBitmap(file),rows=await new TextDetector().detect(bitmap);bitmap.close?.();return rows.map(row=>row.rawValue||'').join(' ').slice(0,5000)}catch(_){return ''}}
function learnedCandidates(hash,game){const rows=localRows().filter(row=>row.game===game),counts=new Map();for(const row of rows){const key=[row.card_name,row.card_number,row.market_key].join('|');counts.set(key,(counts.get(key)||0)+1)}const hits=[];for(const row of rows){const distance=hamming(hash,row.image_hash),key=[row.card_name,row.card_number,row.market_key].join('|');if(distance===0||(distance<=8&&(counts.get(key)||0)>=3))hits.push({...row,confidence:distance===0?.999:Math.max(.86,.98-distance*.012),matched_by:distance===0?'confirmed_exact_image':'confirmed_visual_learning'})}return hits.sort((a,b)=>b.confidence-a.confidence).slice(0,5)}
function mergeCandidates(rows){const found=new Map();for(const row of rows.filter(Boolean)){const key=[row.card_name,row.card_number,row.market_key].join('|'),old=found.get(key);if(!old||Number(row.confidence)>Number(old.confidence))found.set(key,row)}return [...found.values()].sort((a,b)=>Number(b.confidence)-Number(a.confidence)).slice(0,5)}
function updateGenerationForCandidate(row){
 const game=gameName(window.tcgIdentityGame||'pokemon');
 const info=inferPokemonGeneration({game,ocr_text:window.tcgIdentityOcrText||'',card_name:row?.card_name||'',card_number:row?.card_number||'',market_key:row?.market_key||'',region:row?.region||byId('identityRegion')?.value||'UNKNOWN'});
 renderPokemonGeneration(info,game);window.tcgPokemonGeneration=info;return info;
}
function displayCandidates(rows){const select=byId('identityCandidates');select.innerHTML='';if(!rows.length){select.append(new Option('일치 후보 없음 · 직접 확인 입력',''));updateGenerationForCandidate(null);return}rows.forEach((row,index)=>{const option=new Option(`${Math.round(Number(row.confidence)*100)}% · ${row.card_name}${row.card_number?' · '+row.card_number:''}`,String(index));select.append(option)});select._rows=rows;select.value='0';applyCandidate(rows[0])}
function applyCandidate(row){if(!row){updateGenerationForCandidate(null);return}byId('identityCardName').value=safeText(row.card_name);byId('identityCardNumber').value=safeText(row.card_number);byId('identityMarketKey').value=safeText(row.market_key);byId('identityRegion').value=['KR','JP','US'].includes(row.region)?row.region:'UNKNOWN';updateGenerationForCandidate(row)}
async function recognize(game){const resolvedGame=gameName(game);window.tcgIdentityGame=resolvedGame;renderPokemonGeneration({status:'pending'},resolvedGame);const file=window.tcgCardInputFile?.('front');if(!file){byId('identityStatus').textContent='앞면 사진이 없어 카드명을 인식할 수 없습니다.';updateGenerationForCandidate(null);return null}const status=byId('identityStatus');status.textContent='🔎 카드명·카드번호·포켓몬 세대 자동 인식 중…';try{const [{hash,data},text]=await Promise.all([imageArtifacts(file),browserText(file)]);window.tcgIdentityImageHash=hash;let candidates=learnedCandidates(hash,resolvedGame),server=null;const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),120000);try{const response=await fetch('/api/recognize-card',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({game:resolvedGame,region:byId('identityRegion')?.value||'UNKNOWN',image_hash:hash,image_data:data,ocr_text:text}),signal:controller.signal,cache:'no-store'});server=await response.json().catch(()=>null);if(response.ok){if(server?.image_hash)window.tcgIdentityImageHash=server.image_hash;candidates=mergeCandidates([...candidates,...(server?.candidates||[])])}}catch(_){/* Static PWA or optional OCR unavailable: browser OCR/confirmed visual memory remain usable. */}finally{clearTimeout(timer)}window.tcgIdentityOcrText=generationText(server?.ocr_text||text);displayCandidates(candidates);const best=candidates[0],generation=updateGenerationForCandidate(best||null);if(best){const diag=server?.ocr_diagnostics||{},passes=Number(diag.pass_count||0),stages=Array.isArray(diag.stages_completed)?diag.stages_completed:[],cross=diag.cross_validation?.cross_validated===true;status.textContent=`✅ 후보 ${Math.round(best.confidence*100)}% · OCR ${stages.length===3?'1차 전체→2차 4분할→3차 8분할 완료':stages.length+'단계'}${passes?' · '+passes+'영역':''}${cross?' · 교차검증 일치':''}${resolvedGame==='pokemon'&&generation?.status==='estimated'?' · '+generation.generation_label:''} · 자동 추정값은 아래에서 확인해야 학습됩니다.`}else if(['tesseract_not_installed','dependency_not_installed'].includes(server?.ocr_error)){status.textContent='OCR 구성요소가 없어 자동 문자 인식을 못했습니다. 카드명·번호를 한 번 확인 저장하면 이후 동일 카드 재인식에 학습됩니다.'}else{status.textContent='일치 후보를 찾지 못했습니다. 카드명·번호를 확인 입력한 뒤 학습해 주세요.'}return {hash:window.tcgIdentityImageHash,candidates,generation}}catch(_){status.textContent='카드 문자 인식 중 오류가 발생했습니다. 카드 전체가 선명한 앞면 사진인지 확인해 주세요.';updateGenerationForCandidate(null);return null}}
function saveLocal(row){const rows=localRows(),same=rows.filter(item=>item.image_hash===row.image_hash),conflict=same.some(item=>[item.card_name,item.card_number,item.market_key,item.game].join('|')!==[row.card_name,row.card_number,row.market_key,row.game].join('|'));if(conflict)return {ok:false,conflict:true};const duplicate=rows.some(item=>[item.image_hash,item.card_name,item.card_number,item.market_key,item.game].join('|')===[row.image_hash,row.card_name,row.card_number,row.market_key,row.game].join('|'));if(!duplicate)rows.push(row);localStorage.setItem(MEMORY_KEY,JSON.stringify(rows.slice(-MAX_LOCAL)));const count=rows.filter(item=>[item.card_name,item.card_number,item.market_key,item.game].join('|')===[row.card_name,row.card_number,row.market_key,row.game].join('|')).length;return {ok:true,count}}
async function confirmIdentity(){const hash=window.tcgIdentityImageHash||'',name=safeText(byId('identityCardName').value),number=safeText(byId('identityCardNumber').value).toUpperCase().replace(/\s+/g,''),game=gameName(window.tcgIdentityGame||'pokemon');if(!/^[0-9a-f]{16}$/.test(hash)||!name){byId('identityStatus').textContent='앞면 사진과 확인된 카드명이 필요합니다.';return}const row={confirmed:true,image_hash:hash,game,card_name:name,card_number:number,market_key:safeText(byId('identityMarketKey').value),region:byId('identityRegion').value};const local=saveLocal(row);if(!local.ok){byId('identityStatus').textContent='⚠️ 같은 사진에 서로 다른 카드명이 입력되어 학습을 중단했습니다.';return}let serverSaved=false;try{const response=await fetch('/api/confirm-card-identity',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(row),cache:'no-store'});if(response.ok)serverSaved=(await response.json()).ok===true}catch(_){}byId('quickCardQuery').value=[name,number].filter(Boolean).join(' ');if(game==='pokemon'){const generation=inferPokemonGeneration({game,ocr_text:window.tcgIdentityOcrText||'',card_name:name,card_number:number,region:row.region});renderPokemonGeneration(generation,game);window.tcgPokemonGeneration=generation}byId('identityStatus').textContent=`✅ 인식 결과 확인 완료 · 이 카드 ${local.count}회 확인 학습${local.count>=3?' · 유사 사진 재인식 활성화':''}${serverSaved?' · 서버 동기화':''}`;byId('quickPriceSearch')?.click()}
function init(){const select=byId('identityCandidates');if(!select)return;select.addEventListener('change',()=>applyCandidate(select._rows?.[Number(select.value)]));byId('identityConfirm')?.addEventListener('click',confirmIdentity);byId('identityRetry')?.addEventListener('click',()=>recognize(window.tcgIdentityGame||'pokemon'));byId('identityCardNumber')?.addEventListener('input',()=>{if(gameName(window.tcgIdentityGame||'pokemon')==='pokemon'){const generation=inferPokemonGeneration({game:'pokemon',ocr_text:window.tcgIdentityOcrText||'',card_name:byId('identityCardName')?.value||'',card_number:byId('identityCardNumber')?.value||'',region:byId('identityRegion')?.value||'UNKNOWN'});renderPokemonGeneration(generation,'pokemon');window.tcgPokemonGeneration=generation}});window.tcgRecognizeCurrentCard=game=>recognize(gameName(game));window.tcgCardIdentityLearning=Object.freeze({version:'v207-ocr-generation-display',rows:()=>localRows().length,recognize:window.tcgRecognizeCurrentCard,generation:window.TCGPokemonGeneration})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
