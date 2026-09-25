/* v302 edition-aware OCR + generation precision: preserve 1-4-8 OCR contract, add KR/JP/US evidence, modern EN set codes and edition-safe learning. */
(()=>{
'use strict';
const MEMORY_KEY='tcg_card_identity_learning_v1',MAX_LOCAL=500;
const byId=id=>document.getElementById(id);
const safeText=value=>String(value??'').replace(/[\u0000-\u001f\u007f]/g,' ').trim().slice(0,180);
const gameName=value=>['pokemon','onepiece','naruto'].includes(value)?value:'pokemon';
const REGION_CODES=new Set(['KR','JP','US']);
const EN_SV_CODES=new Set(['SVI','PAL','OBF','MEW','PAR','PAF','TEF','TWM','SFA','SCR','SSP','PRE','JTG','DRI','BLK','WHT']);
const EN_MEGA_CODES=new Set(['MEG','PFL','ASC','POR','CRI','PBL']);
const EN_SET_CODES=new Set([...EN_SV_CODES,...EN_MEGA_CODES]);
const META_VARIANTS=new Set(['UNKNOWN','MANGA','PARALLEL','ALT_ART','FULL_ART','SPECIAL_ART','PROMO','STAMPED','FIRST_EDITION']);
const META_FINISHES=new Set(['UNKNOWN','HOLO','REVERSE_HOLO','FOIL','NON_HOLO']);
const META_RARITIES=new Set(['UNKNOWN','BWR','MUR','SAR','CSR','CHR','SSR','RRR','SEC','SR','UR','HR','AR','SP','TR','RR','R','U','C','L']);
function metaUpper(value){return String(value??'').normalize?.('NFKC').toUpperCase()||String(value??'').toUpperCase()}
function normalizeSetCodeMeta(value){const t=metaUpper(value).replace(/\s+/g,'').replace(/[—–]/g,'-');if(EN_SET_CODES.has(t))return t;if(/^(?:SV|SM|S|M|XY|BW|DPT?|DP)\d{1,2}[A-Z]{0,2}$/.test(t))return t;let m=t.match(/^(OP|ST|EB|PRB)-?(\d{1,2})$/);if(m)return m[1]+String(Number(m[2])).padStart(2,'0');if(t==='P'||t==='CP')return t;return ''}
function inferSetCodeMeta(value,game='pokemon'){const raw=metaUpper(value),compact=raw.replace(/\s+/g,''),g=gameName(game);let m;if(g==='onepiece'){m=raw.match(/(?:^|[^A-Z0-9])(OP|ST|EB|PRB)-?(\d{1,2})(?=[^A-Z0-9]|$)/)||compact.match(/(?:^|[^A-Z0-9])(OP|ST|EB|PRB)-?(\d{1,2})(?=[^A-Z0-9]|$)/);if(m)return normalizeSetCodeMeta(m[1]+m[2]);if(/(?:^|[^A-Z0-9])P-?\d{1,3}(?=[^A-Z0-9]|$)/.test(raw))return 'P';return ''}if(g==='naruto'){return /(?:^|[^A-Z0-9])CP-?\d{1,3}(?=[^A-Z0-9]|$)/.test(raw)?'CP':''}m=raw.match(new RegExp(`(?:^|[^A-Z0-9])(${[...EN_SET_CODES].join('|')})(?=\\s*[- ]?\\s*\\d{1,3}|[^A-Z0-9]|$)`));if(m)return m[1];m=compact.match(/(?:^|[^A-Z0-9])((?:SV|SM|S|M|XY|BW|DPT?|DP)\d{1,2}[A-Z]{0,2})(?=\d|[-/]|$)/);return m?normalizeSetCodeMeta(m[1]):''}
function normalizeVariantMeta(value){let t=metaUpper(value).trim().replace(/[- ]/g,'_'),map={MANGA_RARE:'MANGA',ALT:'ALT_ART',ALTERNATE_ART:'ALT_ART',ALTERNATIVE_ART:'ALT_ART',FA:'FULL_ART',FULLART:'FULL_ART',SPECIALART:'SPECIAL_ART',PROMOTIONAL:'PROMO','1ST_EDITION':'FIRST_EDITION'};t=map[t]||t;return META_VARIANTS.has(t)?t:'UNKNOWN'}
function inferVariantMeta(value){const t=metaUpper(value),rules=[['MANGA',/(?:\bMANGA(?:\s+RARE)?\b|만화\s*패러렐|망가\s*패러렐|コミパラ)/i],['ALT_ART',/(?:\bALT(?:ERNATE|ERNATIVE)?\s*ART\b|\bALT\s*ART\b|얼터너티브\s*아트|대체\s*일러스트)/i],['FULL_ART',/(?:\bFULL\s*ART\b|풀\s*아트|\bFA\b)/i],['SPECIAL_ART',/(?:\bSPECIAL\s*ART\b|스페셜\s*아트)/i],['PROMO',/(?:\bPROMO(?:TIONAL)?\b|프로모|プロモ)/i],['STAMPED',/(?:\bSTAMPED\b|스탬프|スタンプ)/i],['FIRST_EDITION',/(?:\b1ST\s*EDITION\b|\bFIRST\s*EDITION\b|초판)/i],['PARALLEL',/(?:\bPARALLEL\b|패러렐|パラレル|(?:^|[^A-Z0-9])(?:R|L|SR|SEC)-P(?:[^A-Z0-9]|$))/i]];for(const [label,re] of rules)if(re.test(t))return label;return 'UNKNOWN'}
function normalizeFinishMeta(value){let t=metaUpper(value).trim().replace(/[- ]/g,'_'),map={REVERSE:'REVERSE_HOLO',REVERSEHOLO:'REVERSE_HOLO',HOLOFOIL:'HOLO',NONHOLO:'NON_HOLO'};t=map[t]||t;return META_FINISHES.has(t)?t:'UNKNOWN'}
function inferFinishMeta(value){const t=metaUpper(value);if(/(?:\bREVERSE\s*HOLO(?:FOIL)?\b|리버스\s*홀로|リバース)/i.test(t))return 'REVERSE_HOLO';if(/(?:\bNON[- ]?HOLO\b|논\s*홀로)/i.test(t))return 'NON_HOLO';if(/(?:\bHOLO(?:GRAPHIC|FOIL)?\b|홀로|ホロ)/i.test(t))return 'HOLO';if(/(?:\bFOIL\b|포일|箔)/i.test(t))return 'FOIL';return 'UNKNOWN'}
function normalizeRarityMeta(value){const t=metaUpper(value).replace(/[^A-Z]/g,'');return META_RARITIES.has(t)?t:'UNKNOWN'}
function inferRarityMeta(value){const t=metaUpper(value);for(const r of ['BWR','MUR','SAR','CSR','CHR','SSR','RRR','SEC','SR','UR','HR','AR','SP','TR','RR'])if(new RegExp(`(?:^|[^A-Z0-9])${r}(?=[^A-Z0-9]|$)`).test(t))return r;return 'UNKNOWN'}
function inferCardFamilyMeta(game,setCode){const g=gameName(game),c=normalizeSetCodeMeta(setCode);if(g==='onepiece'){if(c.startsWith('OP'))return 'BOOSTER';if(c.startsWith('ST'))return 'STARTER';if(c.startsWith('EB'))return 'EXTRA_BOOSTER';if(c.startsWith('PRB'))return 'PREMIUM_BOOSTER';if(c==='P')return 'PROMO'}if(g==='naruto'&&c==='CP')return 'PROMO';if(g==='pokemon'&&(EN_SET_CODES.has(c)||/^(?:SV|SM|S|M|XY|BW|DPT?|DP)\d/.test(c)))return 'EXPANSION';return 'UNKNOWN'}
function identityMetadata(input={}){const g=gameName(input.game||window.tcgIdentityGame||'pokemon'),blob=[input.ocr_text,input.card_name,input.card_number,input.market_key,input.product_name].map(metaUpper).filter(Boolean).join(' ');const set_code=normalizeSetCodeMeta(input.set_code)||inferSetCodeMeta(`${input.card_number||''} ${blob}`,g);let variant=normalizeVariantMeta(input.variant);if(variant==='UNKNOWN')variant=inferVariantMeta(blob);let finish=normalizeFinishMeta(input.finish);if(finish==='UNKNOWN')finish=inferFinishMeta(blob);let rarity=normalizeRarityMeta(input.rarity);if(rarity==='UNKNOWN')rarity=inferRarityMeta(blob);return {set_code,variant,finish,rarity,card_family:inferCardFamilyMeta(g,set_code)}}
function metaSearchTokens(meta){const map={MANGA:'Manga',PARALLEL:'Parallel',ALT_ART:'Alt Art',FULL_ART:'Full Art',SPECIAL_ART:'Special Art',PROMO:'Promo',STAMPED:'Stamped',FIRST_EDITION:'1st Edition',HOLO:'Holo',REVERSE_HOLO:'Reverse Holo',FOIL:'Foil',NON_HOLO:'Non-Holo'};return [meta?.set_code,meta?.rarity,map[meta?.variant],map[meta?.finish]].filter(Boolean)}
window.TCGCardIdentityMeta=Object.freeze({version:'v322',infer:identityMetadata,searchTokens:metaSearchTokens,normalizeVariant:normalizeVariantMeta,normalizeFinish:normalizeFinishMeta,normalizeRarity:normalizeRarityMeta,normalizeSetCode:normalizeSetCodeMeta});

function generationText(value){return String(value??'').replace(/Ⓒ/g,'©').normalize?.('NFKC').toUpperCase().replace(/[\u0000-\u001f\u007f]/g,' ').replace(/\s+/g,' ').trim().slice(0,8000)}
function normalizeRegion(value){const r=generationText(value).replace(/\s+/g,'');if(['JP','JAPAN','JAPANESE','日本','日版','日本版'].includes(r))return 'JP';if(['US','USA','EN','ENGLISH','영문판','미국판'].includes(r))return 'US';if(['KR','KOREA','KOREAN','한국','한국판','한글판'].includes(r))return 'KR';return 'UNKNOWN'}
function inferEditionFromText(value){
 const raw=String(value??'').normalize?.('NFKC')||String(value??''),upper=generationText(raw),signals=[];
 const add=(region,basis,confidence,extra={})=>signals.push({region,basis,confidence,...extra});
 if(/(?:\b(?:KR|KOREA|KOREAN)\b|한국판|한글판|국판)/i.test(upper))add('KR','explicit_region_label',.99);
 if(/(?:\b(?:JP|JAPAN|JAPANESE)\b|日本版|日版)/i.test(upper))add('JP','explicit_region_label',.99);
 if(/(?:\b(?:US|USA|EN|ENGLISH)\b|영문판|미국판)/i.test(upper))add('US','explicit_region_label',.99);
 const hangul=(raw.match(/[가-힣]/g)||[]).length,kana=(raw.match(/[ぁ-んァ-ヶー]/g)||[]).length;
 if(hangul>=2)add('KR','hangul_script',.96,{count:hangul});
 if(kana>=2)add('JP','kana_script',.96,{count:kana});
 const englishSet=upper.match(new RegExp(`(?:^|[^A-Z0-9])(${[...EN_SET_CODES].join('|')})\\s*[- ]?\\s*\\d{1,3}(?:\\s*/\\s*\\d{2,3})?(?=[^A-Z0-9]|$)`));
 if(englishSet)add('US',`english_set_code_${englishSet[1]}`,.92);
 const regions=[...new Set(signals.map(row=>row.region))].sort();
 if(regions.length>1)return {region:'UNKNOWN',confidence:0,basis:'edition_evidence_conflict',conflict:true,signals};
 if(!regions.length)return {region:'UNKNOWN',confidence:0,basis:'insufficient_evidence',conflict:false,signals:[]};
 const region=regions[0],matching=signals.filter(row=>row.region===region);
 return {region,confidence:Math.max(...matching.map(row=>row.confidence)),basis:[...new Set(matching.map(row=>row.basis))].join('+'),conflict:false,signals:matching};
}

function expansionFromCardNumber(value){
 const n=generationText(value).replace(/\s+/g,'');
 let m;
 if((m=n.match(new RegExp(`^(${[...EN_SET_CODES].join('|')})(?=\\d|[-/])`))))return m[1];
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
  new RegExp(`(?:^|[^A-Z0-9])(${[...EN_SET_CODES].join('|')})\\s*[- ]?\\s*\\d{1,3}(?:\\s*/\\s*\\d{2,3})?(?=[^A-Z0-9]|$)`),
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
 for(const match of t.matchAll(/(?:©|\(C\)|COPYRIGHT\s*)\s*((?:19|20)\d{2})/g)){
  const year=Number(match[1]);if(year>=1996&&year<=2099)years.push(year);
 }
 return years.length?Math.max(...years):null;
}
function generationBySetCode(code){
 const c=generationText(code).replace(/\s+/g,'');
 if(EN_MEGA_CODES.has(c))return {generation:null,generation_label:'세대 단정 안 함',series:'MEGA Evolution 시리즈',era:'MEGA',set_region:'US'};
 if(EN_SV_CODES.has(c))return {generation:9,generation_label:'9세대',series:'스칼렛&바이올렛',era:'SV',set_region:'US'};
 if(/^SV/.test(c))return {generation:9,generation_label:'9세대',series:'스칼렛&바이올렛',era:'SV'};
 if(/^M\d/.test(c))return {generation:null,generation_label:'세대 단정 안 함',series:'MEGA 시리즈',era:'MEGA'};
 if(/^SM/.test(c))return {generation:7,generation_label:'7세대',series:'썬&문',era:'SM'};
 if(/^S(?!M|V)\d/.test(c))return {generation:8,generation_label:'8세대',series:'소드&실드',era:'S'};
 if(/^XY/.test(c))return {generation:6,generation_label:'6세대',series:'XY',era:'XY'};
 if(/^BW/.test(c))return {generation:5,generation_label:'5세대',series:'BW',era:'BW'};
 if(/^DPT?/.test(c))return {generation:4,generation_label:'4세대',series:/^DPT/.test(c)?'DPt':'DP',era:/^DPT/.test(c)?'DPt':'DP'};
 return null;
}
function generationByRegulation(mark){
 if(!/^[A-J]$/.test(mark))return null;
 return {generation:null,generation_label:'세대 단정 안 함',series:`레귤레이션 ${mark} 시기`,era:'REGULATION',context_only:true};
}
function generationRegion(value){return normalizeRegion(value)}
function generationByYear(year,region){
 if(!Number.isInteger(year))return null;
 if(generationRegion(region)==='JP'){
  if(year>=2025)return {generation:null,generation_label:'세대 단정 안 함',series:'SV/MEGA 전환·현행 TCG 시기',era:'CURRENT'};
  if(year>=2023)return {generation:9,generation_label:'9세대',series:'스칼렛&바이올렛 시대',era:'SV'};
  if(year>=2019)return {generation:8,generation_label:'8세대',series:'소드&실드 시대',era:'S'};
  if(year>=2016)return {generation:7,generation_label:'7세대',series:'썬&문 시대',era:'SM'};
  if(year>=2013)return {generation:6,generation_label:'6세대',series:'XY 시대',era:'XY'};
  if(year>=2010)return {generation:5,generation_label:'5세대',series:'BW 시대',era:'BW'};
  if(year>=2006)return {generation:4,generation_label:'4세대',series:'DP/DPt 시대',era:'DP'};
  return null;
 }
 if(year>=2025)return {generation:null,generation_label:'세대 단정 안 함',series:'SV/MEGA 전환·현행 TCG 시기',era:'CURRENT'};
 if(year>=2023)return {generation:9,generation_label:'9세대',series:'스칼렛&바이올렛 시대',era:'SV'};
 if(year>=2020)return {generation:8,generation_label:'8세대',series:'소드&실드 시대',era:'S'};
 if(year>=2017)return {generation:7,generation_label:'7세대',series:'썬&문 시대',era:'SM'};
 if(year>=2014)return {generation:6,generation_label:'6세대',series:'XY 시대',era:'XY'};
 if(year>=2011)return {generation:5,generation_label:'5세대',series:'BW 시대',era:'BW'};
 if(year>=2007)return {generation:4,generation_label:'4세대',series:'DP/DPt 시대',era:'DP'};
 return null;
}
function generationYearRange(era){
 const ranges={DP:[2006,2011],BW:[2010,2014],XY:[2013,2017],SM:[2016,2020],S:[2019,2023],SV:[2022,2026],MEGA:[2025,2028],CURRENT:[2025,2028]};
 return ranges[era]||null;
}
function generationYearConflict(base,year,expansion,regulation){
 if(!base||!Number.isInteger(year))return null;
 const range=generationYearRange(base.era);if(!range||year>=range[0]&&year<=range[1])return null;
 return {status:'conflict',game:'pokemon',generation:null,generation_label:'근거 충돌',series:'세트/레귤레이션과 ©연도 재확인',era:'CONFLICT',expansion_code:expansion||'',regulation_mark:regulation||'',year,confidence:0,confidence_level:'conflict',basis:[base.era&&`시리즈 ${base.era}`,`©/제작연도 ${year}`].filter(Boolean),note:'세트·레귤레이션 시기와 OCR 연도가 넓은 허용범위 밖이라 세대를 단정하지 않았습니다.'};
}
function generationConflict(inputRegion,byExpansion,expansion){
 const setRegion=normalizeRegion(byExpansion?.set_region||'UNKNOWN');
 if(inputRegion!=='UNKNOWN'&&setRegion!=='UNKNOWN'&&inputRegion!==setRegion){
  return {status:'conflict',game:'pokemon',generation:null,generation_label:'근거 충돌',series:'판본/세트코드 재확인',era:'CONFLICT',expansion_code:expansion||'',regulation_mark:'',year:null,confidence:0,confidence_level:'conflict',basis:[`선택 판본 ${inputRegion}`,`세트코드 판본 ${setRegion}`],note:'판본과 세트코드 근거가 충돌해 세대를 단정하지 않았습니다.'};
 }
 return null;
}
function inferPokemonGeneration(input={}){
 const game=String(input.game||'pokemon').trim().toLowerCase();
 if(game!=='pokemon')return {status:'not_applicable',game,generation:null,confidence:0,basis:[]};
 const text=[input.ocr_text,input.card_name,input.market_key].map(generationText).filter(Boolean).join(' ');
 const inputRegion=normalizeRegion(input?.region),year=yearFromEvidence(input,text);
 const expansion=expansionFromCardNumber(input.card_number)||expansionFromOcr(text);
 const byExpansion=generationBySetCode(expansion);
 const regulation=regulationFromEvidence(input,text),byReg=generationByRegulation(regulation);
 const conflict=generationConflict(inputRegion,byExpansion,expansion);
 if(conflict){conflict.year=year;conflict.regulation_mark=regulation||'';return conflict}
 const timeConflict=generationYearConflict(byExpansion,year,expansion,regulation);
 if(timeConflict)return timeConflict;
 if(byExpansion){
  const generationBasis=[`확장팩/세트 코드 ${expansion}`];
  if(year)generationBasis.push(`©/제작연도 ${year}`);
  const contextBasis=byReg?[`레귤레이션 마크 ${regulation}`]:[];
  const evidence_count=generationBasis.length;
  return {status:'estimated',game:'pokemon',...byExpansion,expansion_code:expansion,regulation_mark:regulation||'',year,confidence:evidence_count>=2?.995:.98,confidence_level:'high',evidence_count,context_evidence_count:contextBasis.length,basis:[...generationBasis,...contextBasis],note:byExpansion.era==='MEGA'?'MEGA는 별도 TCG 시리즈/블록이므로 TCG 시리즈와 포켓몬 세대 번호를 분리해 표시합니다.':(byReg?'확장팩/세트 코드가 세대 근거이며 레귤레이션 마크는 사용 가능 시기 문맥으로만 표시합니다.':'확장팩/세트 코드와 독립 OCR 근거를 교차검증한 추정')};
 }
 if(byReg){
  const basis=[`레귤레이션 마크 ${regulation}`];if(year)basis.push(`©/제작연도 ${year}`);
  return {status:'context_only',game:'pokemon',...byReg,expansion_code:'',regulation_mark:regulation,year,confidence:.50,confidence_level:'context',evidence_count:0,context_evidence_count:1,basis,note:'레귤레이션 마크는 대회 사용 가능성 표기이며 사용 가능 범위를 관리하므로 포켓몬 세대 번호로 변환하지 않습니다.'};
 }
 const byYear=generationByYear(year,input?.region);
 if(byYear)return {status:'estimated',game:'pokemon',...byYear,expansion_code:'',regulation_mark:'',year,confidence:.58,confidence_level:'low',evidence_count:1,context_evidence_count:0,basis:[`©/제작연도 ${year}`],note:'연도만 확인되어 세대/시리즈는 보조 추정입니다.'};
 if(year&&year<2007)return {status:'legacy',game:'pokemon',generation:null,generation_label:'고전 카드',series:'초기~ADV/PCG 계열',era:'LEGACY',expansion_code:'',regulation_mark:'',year,confidence:.55,confidence_level:'low',evidence_count:1,context_evidence_count:0,basis:[`©/제작연도 ${year}`],note:'고전 카드는 확장팩 코드 확인 전 세대 번호를 단정하지 않습니다.'};
 return {status:'unknown',game:'pokemon',generation:null,generation_label:'세대 확인 필요',series:'확장팩 코드·©연도 OCR 부족',era:'UNKNOWN',expansion_code:'',regulation_mark:regulation||'',year:null,confidence:0,confidence_level:'unknown',evidence_count:0,context_evidence_count:byReg?1:0,basis:byReg?[`레귤레이션 마크 ${regulation}`]:[],note:'세대 근거가 부족해 번호를 생성하지 않았습니다.'};
}
function renderPokemonGeneration(info,game='pokemon'){
 const box=byId('simplePokemonGeneration');if(!box)return info;
 const isPokemon=gameName(game)==='pokemon';box.hidden=!isPokemon;if(!isPokemon)return info;
 const badge=byId('pokemonGenerationBadge'),title=byId('pokemonGenerationTitle'),meta=byId('pokemonGenerationMeta');
 if(!info||info.status==='pending'){if(badge)badge.textContent='…';if(title)title.textContent='세대 판별 중…';if(meta)meta.textContent='앞면 OCR에서 확장팩/세트 코드 · 레귤레이션 · ©연도를 확인합니다.';return info}
 if(info.status==='conflict'){if(badge)badge.textContent='!';if(title)title.textContent='세대/판본 근거 충돌';if(meta)meta.textContent=`${info.basis?.join(' · ')||'OCR 근거 충돌'} · 자동 분류 중단 · 카드번호/판본을 확인해 주세요.`;return info}
 if(info.status==='context_only'){if(badge)badge.textContent='?';if(title)title.textContent=`세대 확인 필요 · 레귤레이션 ${info.regulation_mark||''}`.trim();if(meta)meta.textContent='레귤레이션은 사용 가능 시기 표기이며 세대 번호 근거로 사용하지 않습니다. 확장팩/세트 코드 또는 ©연도를 확인해 주세요.';return info}
 if(info.status==='estimated'){if(badge)badge.textContent=info.generation_label||(`${info.generation}세대`);if(title)title.textContent=`${info.generation_label||info.generation+'세대'} · ${info.series}`;const evidence=[info.expansion_code&&`확장팩/세트 ${info.expansion_code}`,info.regulation_mark&&`레귤레이션 ${info.regulation_mark}(문맥)`,info.year&&`©${info.year}`].filter(Boolean);if(meta)meta.textContent=`${evidence.join(' · ')||info.basis?.join(' · ')||'OCR 근거'} · 신뢰도 ${info.confidence_level==='high'?'높음':info.confidence_level==='medium'?'중간(보조)':'보조'}`;return info}
 if(badge)badge.textContent=info.status==='legacy'?'고전':'?';if(title)title.textContent=info.status==='legacy'?info.generation_label:'세대 확인 필요';if(meta)meta.textContent=info.status==='legacy'?`${info.series}${info.year?' · ©'+info.year:''} · 확장팩 코드 확인 권장`:'확장팩/세트 코드·©연도를 충분히 읽지 못했습니다.';return info
}
window.TCGPokemonGeneration=Object.freeze({version:'v320',infer:inferPokemonGeneration,render:renderPokemonGeneration,inferRegion:inferEditionFromText});
function localRows(){try{const value=JSON.parse(localStorage.getItem(MEMORY_KEY)||'[]');return Array.isArray(value)?value.filter(row=>row&&row.confirmed===true).slice(-MAX_LOCAL):[]}catch(_){return []}}
function hamming(a,b){if(!/^[0-9a-f]{16}$/.test(a)||!/^[0-9a-f]{16}$/.test(b))return 65;let value=BigInt('0x'+a)^BigInt('0x'+b),count=0;while(value){count+=Number(value&1n);value>>=1n}return count}
function blobDataUrl(blob){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||''));reader.onerror=()=>reject(new Error('image_encode'));reader.readAsDataURL(blob)})}
async function canvasJpegDataUrl(canvas){if(typeof canvas.toBlob==='function'){for(const quality of [.84,.76,.68]){const blob=await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error('image_encode')),'image/jpeg',quality));if(blob.size<=6_000_000)return blobDataUrl(blob)}throw new Error('image_payload_too_large')}for(const quality of [.84,.76,.68]){const value=canvas.toDataURL('image/jpeg',quality);if(value.length<8_000_000)return value}throw new Error('image_payload_too_large')}
async function imageArtifacts(file){const image=await window.loadCardImage(file),w=image.naturalWidth,h=image.naturalHeight;if(!w||!h||w*h>24000000)throw new Error('image_dimensions');const scale=Math.min(1,1400/w,1900/h),dataCanvas=document.createElement('canvas');dataCanvas.width=Math.max(1,Math.round(w*scale));dataCanvas.height=Math.max(1,Math.round(h*scale));const dataCtx=dataCanvas.getContext('2d');if(!dataCtx)throw new Error('canvas');dataCtx.drawImage(image,0,0,dataCanvas.width,dataCanvas.height);const hashCanvas=document.createElement('canvas');hashCanvas.width=9;hashCanvas.height=8;const hashCtx=hashCanvas.getContext('2d',{willReadFrequently:true});if(!hashCtx)throw new Error('canvas');hashCtx.drawImage(image,0,0,9,8);const pixels=hashCtx.getImageData(0,0,9,8).data,gray=[];for(let i=0;i<pixels.length;i+=4)gray.push((pixels[i]*299+pixels[i+1]*587+pixels[i+2]*114)/1000);let bits=0n;for(let y=0;y<8;y++)for(let x=0;x<8;x++)bits=(bits<<1n)|(gray[y*9+x]>gray[y*9+x+1]?1n:0n);return {hash:bits.toString(16).padStart(16,'0'),data:await canvasJpegDataUrl(dataCanvas)}}
async function browserText(file){if(typeof window.TextDetector!=='function'||typeof createImageBitmap!=='function')return '';try{const bitmap=await createImageBitmap(file),rows=await new TextDetector().detect(bitmap);bitmap.close?.();return rows.map(row=>row.rawValue||'').join(' ').slice(0,5000)}catch(_){return ''}}
function learnedCandidates(hash,game,region='UNKNOWN'){const requested=normalizeRegion(region),rows=localRows().filter(row=>row.game===game&&(requested==='UNKNOWN'||normalizeRegion(row.region)===requested)),counts=new Map();for(const row of rows){const meta=identityMetadata({...row,game}),key=[row.card_name,row.card_number,row.market_key,normalizeRegion(row.region),meta.set_code,meta.variant,meta.finish,meta.rarity].join('|');counts.set(key,(counts.get(key)||0)+1)}const hits=[];for(const row of rows){const meta=identityMetadata({...row,game}),distance=hamming(hash,row.image_hash),key=[row.card_name,row.card_number,row.market_key,normalizeRegion(row.region),meta.set_code,meta.variant,meta.finish,meta.rarity].join('|');if(distance===0||(distance<=8&&(counts.get(key)||0)>=3))hits.push({...row,...meta,confidence:distance===0?.999:Math.max(.86,.98-distance*.012),matched_by:distance===0?'confirmed_exact_image':'confirmed_visual_learning'})}return hits.sort((a,b)=>b.confidence-a.confidence).slice(0,5)}
function mergeCandidates(rows){const found=new Map();for(const row of rows.filter(Boolean)){const meta=identityMetadata({...row,game:row.game||window.tcgIdentityGame||'pokemon'}),item={...row,...meta},key=[item.card_name,item.card_number,item.market_key,normalizeRegion(item.region),item.set_code,item.variant,item.finish,item.rarity].join('|'),old=found.get(key);if(!old||Number(item.confidence)>Number(old.confidence))found.set(key,item)}return [...found.values()].sort((a,b)=>Number(b.confidence)-Number(a.confidence)).slice(0,5)}
function filterCandidatesByRegion(rows,region){const requested=normalizeRegion(region);return requested==='UNKNOWN'?rows:rows.filter(row=>normalizeRegion(row?.region)===requested)}
function setMetaField(id,value){const node=byId(id);if(!node)return;const v=String(value||'');if(node.tagName==='SELECT'){if([...node.options].some(o=>o.value===v))node.value=v;else node.value='UNKNOWN'}else node.value=v}
function metaLabel(value){return ({UNKNOWN:'확인 필요',MANGA:'만화 패러렐',PARALLEL:'패러렐',ALT_ART:'얼터너티브 아트',FULL_ART:'풀아트',SPECIAL_ART:'스페셜 아트',PROMO:'프로모',STAMPED:'스탬프',FIRST_EDITION:'초판',HOLO:'홀로',REVERSE_HOLO:'리버스 홀로',FOIL:'포일',NON_HOLO:'논홀로',BOOSTER:'부스터',STARTER:'스타터',EXTRA_BOOSTER:'엑스트라 부스터',PREMIUM_BOOSTER:'프리미엄 부스터',EXPANSION:'확장팩'})[value]||value||'확인 필요'}
function renderIdentityClassification(meta,game){const box=byId('identityClassification');if(!box)return;const g=gameName(game||window.tcgIdentityGame||'pokemon'),parts=[meta?.set_code&&`세트 ${meta.set_code}`,meta?.card_family&&meta.card_family!=='UNKNOWN'&&metaLabel(meta.card_family),meta?.variant&&meta.variant!=='UNKNOWN'&&metaLabel(meta.variant),meta?.finish&&meta.finish!=='UNKNOWN'&&metaLabel(meta.finish),meta?.rarity&&meta.rarity!=='UNKNOWN'&&`레어도 ${meta.rarity}`].filter(Boolean);const scope=g==='pokemon'?'포켓몬 세대는 아래 세대 판정에서 별도 표시':g==='onepiece'?'원피스는 포켓몬식 세대번호 대신 OP/ST/EB/PRB/P 세트계열로 구분':'나루토는 포켓몬식 세대번호를 적용하지 않고 공식 세트/프로모 코드로 구분';box.textContent=`${parts.length?parts.join(' · '):'세트/버전/레어도 확인 필요'} · ${scope}`}
function applyIdentityMeta(row){const game=gameName(window.tcgIdentityGame||'pokemon'),meta=identityMetadata({game,ocr_text:window.tcgIdentityOcrText||'',card_name:row?.card_name||'',card_number:row?.card_number||'',market_key:row?.market_key||'',set_code:row?.set_code,variant:row?.variant,finish:row?.finish,rarity:row?.rarity});setMetaField('identitySetCode',meta.set_code);setMetaField('identityVariant',meta.variant);setMetaField('identityFinish',meta.finish);setMetaField('identityRarity',meta.rarity==='UNKNOWN'?'':meta.rarity);renderIdentityClassification(meta,game);return meta}
function clearIdentityMeta(){setMetaField('identitySetCode','');setMetaField('identityVariant','UNKNOWN');setMetaField('identityFinish','UNKNOWN');setMetaField('identityRarity','');renderIdentityClassification(identityMetadata({game:window.tcgIdentityGame||'pokemon'}),window.tcgIdentityGame||'pokemon')}
function metaCandidateLabel(row){const meta=identityMetadata({...row,game:row?.game||window.tcgIdentityGame||'pokemon'}),parts=[meta.set_code,meta.rarity,meta.variant!=='UNKNOWN'?metaLabel(meta.variant):'',meta.finish!=='UNKNOWN'?metaLabel(meta.finish):''].filter(Boolean);return parts.length?' · '+parts.join(' · '):''}
function updateGenerationForCandidate(row){
 const game=gameName(window.tcgIdentityGame||'pokemon');
 const info=inferPokemonGeneration({game,ocr_text:window.tcgIdentityOcrText||'',card_name:row?.card_name||'',card_number:row?.card_number||'',market_key:row?.market_key||'',region:byId('identityRegion')?.value||'UNKNOWN'});
 renderPokemonGeneration(info,game);window.tcgPokemonGeneration=info;return info;
}
function displayCandidates(rows,opts={}){const select=byId('identityCandidates');select.innerHTML='';select._rows=rows;if(!rows.length){select.append(new Option('일치 후보 없음 · 직접 확인 입력',''));updateGenerationForCandidate(null);clearIdentityMeta();return}if(opts.autoApply===false){select.append(new Option('후보가 겹칩니다 · 세트/버전까지 직접 선택해 확인',''));rows.forEach((row,index)=>{const region=REGION_CODES.has(String(row.region||'').toUpperCase())?` · ${String(row.region).toUpperCase()}`:'';select.append(new Option(`${Math.round(Number(row.confidence)*100)}% · ${row.card_name}${row.card_number?' · '+row.card_number:''}${metaCandidateLabel(row)}${region}`,String(index)))});select.value='';updateGenerationForCandidate(null);clearIdentityMeta();return}rows.forEach((row,index)=>{const region=REGION_CODES.has(String(row.region||'').toUpperCase())?` · ${String(row.region).toUpperCase()}`:'';select.append(new Option(`${Math.round(Number(row.confidence)*100)}% · ${row.card_name}${row.card_number?' · '+row.card_number:''}${metaCandidateLabel(row)}${region}`,String(index)))});select.value='0';applyCandidate(rows[0],opts)}
function applyCandidate(row,opts={}){if(!row){updateGenerationForCandidate(null);clearIdentityMeta();return}const current=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN'),candidateRegion=normalizeRegion(row.region),allowRegionAutofill=opts.allowRegionAutofill===true;if(byId('identityCardName'))byId('identityCardName').value=safeText(row.card_name);if(byId('identityCardNumber'))byId('identityCardNumber').value=safeText(row.card_number);if(allowRegionAutofill&&current==='UNKNOWN'&&candidateRegion!=='UNKNOWN'&&byId('identityRegion'))byId('identityRegion').value=candidateRegion;const effective=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN'),marketLinkBlocked=opts.marketLinkBlocked===true||effective==='UNKNOWN'||(candidateRegion!=='UNKNOWN'&&effective!==candidateRegion);if(byId('identityMarketKey'))byId('identityMarketKey').value=marketLinkBlocked?'':safeText(row.market_key);applyIdentityMeta(row);updateGenerationForCandidate(row)}
async function recognize(game){
 const resolvedGame=gameName(game);window.tcgIdentityGame=resolvedGame;renderPokemonGeneration({status:'pending'},resolvedGame);
 const file=window.tcgCardInputFile?.('front');if(!file){byId('identityStatus').textContent='앞면 사진이 없어 카드명을 인식할 수 없습니다.';updateGenerationForCandidate(null);return null}
 const status=byId('identityStatus');status.textContent='🔎 카드명·카드번호·판본·포켓몬 세대 자동 인식 중…';
 try{
  const [{hash,data},text]=await Promise.all([imageArtifacts(file),browserText(file)]);window.tcgIdentityImageHash=hash;
  const selected=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN'),browserRegion=inferEditionFromText(text),requestRegion=selected!=='UNKNOWN'?selected:browserRegion.region;
  const browserConflict=browserRegion.conflict===true||(selected!=='UNKNOWN'&&browserRegion.region!=='UNKNOWN'&&selected!==browserRegion.region);
  let candidates=learnedCandidates(hash,resolvedGame,requestRegion),server=null;
  async function request(region){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),120000);try{const response=await fetch('/api/recognize-card',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({game:resolvedGame,region,image_hash:hash,image_data:data,ocr_text:text}),signal:controller.signal,cache:'no-store'});const payload=await response.json().catch(()=>null);return response.ok?payload:null}catch(_){return null}finally{clearTimeout(timer)}}
  server=await request(requestRegion);
  if(server?.image_hash)window.tcgIdentityImageHash=server.image_hash;
  const identityConflict=browserConflict||server?.region_conflict===true;
  const identityAmbiguous=server?.identity_ambiguous===true||server?.region_ambiguous===true||server?.market_ambiguous===true||server?.metadata_ambiguous===true;
  if(server&&!identityConflict)candidates=mergeCandidates([...candidates,...(server.candidates||[])]);
  let detected=inferEditionFromText(server?.ocr_text||text),effectiveRegion=selected!=='UNKNOWN'?selected:(browserRegion.region!=='UNKNOWN'?browserRegion.region:detected.region);
  if(identityConflict){
   window.tcgIdentityOcrText=generationText(server?.ocr_text||text);
   candidates=[];effectiveRegion='UNKNOWN';
   if(byId('identityRegion'))byId('identityRegion').value='UNKNOWN';
   if(byId('identityCardName'))byId('identityCardName').value='';
   if(byId('identityCardNumber'))byId('identityCardNumber').value='';
   if(byId('identityMarketKey'))byId('identityMarketKey').value='';clearIdentityMeta();
   displayCandidates([]);updateGenerationForCandidate(null);
   status.textContent='⚠️ 한판·일판·영판 근거가 충돌해 자동 카드 선택·세대·시세 연결을 중단했습니다. 판본과 카드번호를 직접 확인해 주세요.';
   return {hash:window.tcgIdentityImageHash,candidates:[],generation:null,region:'UNKNOWN',region_conflict:true};
  }
  if(effectiveRegion!=='UNKNOWN')candidates=filterCandidatesByRegion(candidates,effectiveRegion);
  if(selected==='UNKNOWN'&&requestRegion==='UNKNOWN'&&effectiveRegion!=='UNKNOWN'){
   const retry=await request(effectiveRegion);if(retry){server=retry;if(retry.image_hash)window.tcgIdentityImageHash=retry.image_hash;candidates=filterCandidatesByRegion(mergeCandidates([...candidates,...(retry.candidates||[])]),effectiveRegion);detected=inferEditionFromText(retry.ocr_text||server?.ocr_text||text)}
  }
  window.tcgIdentityOcrText=generationText(server?.ocr_text||text);
  if(selected==='UNKNOWN'&&effectiveRegion!=='UNKNOWN'&&byId('identityRegion'))byId('identityRegion').value=effectiveRegion;
  const marketLinkBlocked=server?.market_link_blocked===true||effectiveRegion==='UNKNOWN';
  if(identityAmbiguous){
   if(byId('identityCardName'))byId('identityCardName').value='';if(byId('identityCardNumber'))byId('identityCardNumber').value='';if(byId('identityMarketKey'))byId('identityMarketKey').value='';clearIdentityMeta();
   displayCandidates(candidates,{autoApply:false,marketLinkBlocked:true});
   status.textContent='⚠️ 카드/판본 후보가 근접해 자동 선택과 시세 연결을 중단했습니다. 후보를 직접 선택하고 카드번호·판본을 확인해 주세요.';
   return {hash:window.tcgIdentityImageHash,candidates,generation:null,region:effectiveRegion,identity_ambiguous:true,market_link_blocked:true};
  }
  displayCandidates(candidates,{marketLinkBlocked});const best=candidates[0],generation=updateGenerationForCandidate(best||null);
  if(best){const diag=server?.ocr_diagnostics||{},passes=Number(diag.pass_count||0),stages=Array.isArray(diag.stages_completed)?diag.stages_completed:[],cross=diag.cross_validation?.cross_validated===true,edition=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN');status.textContent=`✅ 후보 ${Math.round(best.confidence*100)}%${edition!=='UNKNOWN'?' · 판본 '+edition:' · 판본 확인 필요'} · OCR ${stages.length===3?'1차 전체→2차 4분할→3차 8분할 완료':stages.length+'단계'}${passes?' · '+passes+'영역':''}${cross?' · 교차검증 일치':''}${resolvedGame==='pokemon'&&generation?.status==='estimated'?' · '+generation.generation_label:''}${marketLinkBlocked?' · 시세 자동연결 보류':''} · 자동 추정값은 아래에서 확인해야 학습됩니다.`}
  else if(['tesseract_not_installed','dependency_not_installed'].includes(server?.ocr_error)){status.textContent='OCR 구성요소가 없어 자동 문자 인식을 못했습니다. 판본·카드명·번호를 확인 저장하면 이후 동일 카드 재인식에 학습됩니다.'}
  else{status.textContent='일치 후보를 찾지 못했습니다. 판본·카드명·번호를 확인 입력한 뒤 학습해 주세요.'}
  return {hash:window.tcgIdentityImageHash,candidates,generation,region:normalizeRegion(byId('identityRegion')?.value||'UNKNOWN'),market_link_blocked:marketLinkBlocked}
 }catch(_){status.textContent='카드 문자 인식 중 오류가 발생했습니다. 카드 전체가 선명한 앞면 사진인지 확인해 주세요.';updateGenerationForCandidate(null);return null}
}
function identityCoreKey(item){const meta=identityMetadata({...item,game:item.game||window.tcgIdentityGame||'pokemon'});return [item.card_name,item.card_number,item.market_key,item.game,meta.set_code,meta.variant,meta.finish,meta.rarity].join('|')}
function identityKey(item){return [identityCoreKey(item),normalizeRegion(item.region)].join('|')}
function saveLocal(row){
 const rows=localRows(),targetCore=identityCoreKey(row),targetRegion=normalizeRegion(row.region);let duplicate=false,conflict=false,count=0;
 for(let i=0;i<rows.length;i++){
  const item=rows[i],sameHash=item.image_hash===row.image_hash;if(!sameHash)continue;
  if(identityCoreKey(item)!==targetCore){conflict=true;break}
  const oldRegion=normalizeRegion(item.region);
  if(oldRegion!=='UNKNOWN'&&targetRegion!=='UNKNOWN'&&oldRegion!==targetRegion){conflict=true;break}
  if(oldRegion==='UNKNOWN'&&targetRegion!=='UNKNOWN'){rows[i]={...item,region:targetRegion};duplicate=true}
  else if(oldRegion!=='UNKNOWN'&&targetRegion==='UNKNOWN'){row.region=oldRegion;duplicate=true}
  else duplicate=true;
 }
 if(conflict)return {ok:false,conflict:true};
 const targetKey=identityKey(row);count=rows.filter(item=>identityKey(item)===targetKey).length;
 if(!duplicate){rows.push(row);count++}else if(!count)count=rows.filter(item=>identityCoreKey(item)===targetCore).length;
 localStorage.setItem(MEMORY_KEY,JSON.stringify(rows.slice(-MAX_LOCAL)));return {ok:true,count,region:normalizeRegion(row.region)}
}
async function confirmIdentity(){
 const hash=window.tcgIdentityImageHash||'',name=safeText(byId('identityCardName').value),number=safeText(byId('identityCardNumber').value).toUpperCase().replace(/\s+/g,''),game=gameName(window.tcgIdentityGame||'pokemon');if(!/^[0-9a-f]{16}$/.test(hash)||!name){byId('identityStatus').textContent='앞면 사진과 확인된 카드명이 필요합니다.';return}
 const selected=normalizeRegion(byId('identityRegion').value),detected=inferEditionFromText(window.tcgIdentityOcrText||''),region=selected!=='UNKNOWN'?selected:detected.region,meta=identityMetadata({game,ocr_text:window.tcgIdentityOcrText||'',card_name:name,card_number:number,market_key:safeText(byId('identityMarketKey').value),set_code:byId('identitySetCode')?.value||'',variant:byId('identityVariant')?.value||'UNKNOWN',finish:byId('identityFinish')?.value||'UNKNOWN',rarity:byId('identityRarity')?.value||''});
 const row={confirmed:true,image_hash:hash,game,card_name:name,card_number:number,market_key:safeText(byId('identityMarketKey').value),region,...meta};
 const local=saveLocal(row);if(!local.ok){byId('identityStatus').textContent='⚠️ 같은 사진에 서로 다른 카드/판본 정보 또는 버전 정보가 입력되어 학습을 중단했습니다.';return}
 if(byId('identityRegion')&&local.region!=='UNKNOWN')byId('identityRegion').value=local.region;applyIdentityMeta(row);
 let serverSaved=false;try{const response=await fetch('/api/confirm-card-identity',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(row),cache:'no-store'});if(response.ok)serverSaved=(await response.json()).ok===true}catch(_){}
 const query=[name,number,...metaSearchTokens(meta)].filter(Boolean).join(' ');byId('quickCardQuery').value=query;
 if(game==='pokemon'){const generation=inferPokemonGeneration({game,ocr_text:window.tcgIdentityOcrText||'',card_name:name,card_number:number,region:row.region});renderPokemonGeneration(generation,game);window.tcgPokemonGeneration=generation}
 byId('identityStatus').textContent=`✅ 인식 결과 확인 완료 · ${local.region!=='UNKNOWN'?local.region+' 판본 · ':''}${meta.set_code?'세트 '+meta.set_code+' · ':''}${meta.variant!=='UNKNOWN'?metaLabel(meta.variant)+' · ':''}이 카드 ${local.count}회 확인 학습${local.count>=3?' · 동일 판본 유사 사진 재인식 활성화 · 동일 버전 확인':''}${serverSaved?' · 서버 동기화':''}`;byId('quickPriceSearch')?.click()
}
function refreshIdentityMetadataFromInputs(){const meta=identityMetadata({game:window.tcgIdentityGame||'pokemon',ocr_text:window.tcgIdentityOcrText||'',card_name:byId('identityCardName')?.value||'',card_number:byId('identityCardNumber')?.value||'',market_key:byId('identityMarketKey')?.value||'',set_code:byId('identitySetCode')?.value||'',variant:byId('identityVariant')?.value||'UNKNOWN',finish:byId('identityFinish')?.value||'UNKNOWN',rarity:byId('identityRarity')?.value||''});renderIdentityClassification(meta,window.tcgIdentityGame||'pokemon');return meta}
function refreshGenerationFromInputs(){refreshIdentityMetadataFromInputs();if(gameName(window.tcgIdentityGame||'pokemon')!=='pokemon')return null;const generation=inferPokemonGeneration({game:'pokemon',ocr_text:window.tcgIdentityOcrText||'',card_name:byId('identityCardName')?.value||'',card_number:byId('identityCardNumber')?.value||'',region:byId('identityRegion')?.value||'UNKNOWN'});renderPokemonGeneration(generation,'pokemon');window.tcgPokemonGeneration=generation;return generation}
function init(){const select=byId('identityCandidates');if(!select)return;select.addEventListener('change',()=>applyCandidate(select._rows?.[Number(select.value)],{allowRegionAutofill:true}));byId('identityConfirm')?.addEventListener('click',confirmIdentity);byId('identityRetry')?.addEventListener('click',()=>recognize(window.tcgIdentityGame||'pokemon'));byId('identityCardNumber')?.addEventListener('input',refreshGenerationFromInputs);byId('identityCardName')?.addEventListener('input',refreshIdentityMetadataFromInputs);byId('identityRegion')?.addEventListener('change',refreshGenerationFromInputs);['identitySetCode','identityVariant','identityFinish','identityRarity'].forEach(id=>byId(id)?.addEventListener('change',refreshIdentityMetadataFromInputs));window.tcgRecognizeCurrentCard=game=>recognize(gameName(game));window.tcgCardIdentityLearning=Object.freeze({version:'v315-evidence-isolated-confirmed-learning',metadataVersion:'v321',rows:()=>localRows().length,recognize:window.tcgRecognizeCurrentCard,generation:window.TCGPokemonGeneration,metadata:window.TCGCardIdentityMeta});refreshIdentityMetadataFromInputs()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
