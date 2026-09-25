/* v326 fail-closed card metadata classification.
 * Separates identity/edition/set/rarity/variant/price binding so a plausible OCR
 * token cannot silently become a wrong market price.
 */
(function(root){
'use strict';
const GAMES=new Set(['pokemon','onepiece','naruto']);
const REGIONS=new Set(['KR','JP','US']);
const norm=v=>String(v??'').normalize?.('NFKC').toUpperCase().replace(/\s+/g,' ').trim();
const clean=v=>norm(v).replace(/[^0-9A-Z가-힣ぁ-んァ-ヶ一-龯/+.\- ]/g,'');
function game(v){const s=norm(v);if(/POK[ÉE]MON|포켓몬/.test(s))return'pokemon';if(/ONE\s*PIECE|원피스/.test(s))return'onepiece';if(/NARUTO|나루토/.test(s))return'naruto';return GAMES.has(String(v).toLowerCase())?String(v).toLowerCase():'unknown'}
function region(v){const s=norm(v).replace(/\s/g,'');if(/^(KR|KOR|KOREA|KOREAN|한국|한국판|한글판)$/.test(s))return'KR';if(/^(JP|JPN|JAPAN|JAPANESE|日本|日本版|일본판|일판)$/.test(s))return'JP';if(/^(US|USA|EN|ENG|ENGLISH|영문판|미국판)$/.test(s))return'US';return'UNKNOWN'}
function setCode(g,text){const s=norm(text);let m;if(g==='onepiece'&&(m=s.match(/\b(OP|ST|EB|PRB)[KJ-]?\s*-?\s*(\d{1,2})\b/)))return m[1]+'-'+m[2].padStart(2,'0');if(g==='naruto'&&(m=s.match(/\b(CP|NR|NAR|PR)[- ]?(\d{1,4})\b/)))return m[1]+'-'+m[2].padStart(3,'0');if(g==='pokemon'&&(m=s.match(/\b(SV\d+[A-Z]?|S\d+[A-Z]?|SM\d+[A-Z]?|XY\d+[A-Z]?|BW\d+[A-Z]?|MEG|PFL|ASC|POR|CRI|PBL|PAL|OBF|MEW|PAR|PAF|TEF|TWM|SFA|SCR|SSP|PRE|JTG|DRI|BLK|WHT)\b/)))return m[1];return''}
function rarity(g,text){const s=' '+norm(text)+' ';const ordered=g==='pokemon'?['SAR','UR','HR','SR','AR','CHR','CSR','ACE SPEC','RRR','RR','R','U','C','PROMO']:g==='onepiece'?['SP','SEC','L','SR','R','UC','C','P']:g==='naruto'?['MYTHIC','SECRET','SUPER RARE','RARE','UNCOMMON','COMMON','PROMO']:[];for(const r of ordered){const rx=new RegExp('(?:^|[^A-Z])'+r.replace(' ','\\s+')+'(?:$|[^A-Z])');if(rx.test(s))return r}return'UNKNOWN'}
function variant(g,text){const s=norm(text);if(/MANGA|만화\s*패러렐|コミパラ/.test(s))return'manga_parallel';if(/ALT(?:ERNATE)?\s*ART|패러렐|PARALLEL|パラレル/.test(s))return'parallel';if(/PROMO|프로모|プロモ/.test(s))return'promo';if(/1ST\s*EDITION|초판/.test(s))return'first_edition';return'base'}
function productType(text){const s=norm(text);if(/\bBOX\b|박스|BOOSTER BOX/.test(s))return'BOX';if(/PACK|팩\b/.test(s))return'PACK';return'CARD'}
function generation(g,code){if(g!=='pokemon')return{generation:null,generation_label:'해당 없음',era:'N/A'};if(/^SV/.test(code)||['PAL','OBF','MEW','PAR','PAF','TEF','TWM','SFA','SCR','SSP','PRE','JTG','DRI','BLK','WHT'].includes(code))return{generation:9,generation_label:'9세대',era:'SV'};if(/^S\d/.test(code))return{generation:8,generation_label:'8세대',era:'S'};if(/^SM/.test(code))return{generation:7,generation_label:'7세대',era:'SM'};if(/^XY/.test(code))return{generation:6,generation_label:'6세대',era:'XY'};if(/^BW/.test(code))return{generation:5,generation_label:'5세대',era:'BW'};if(['MEG','PFL','ASC','POR','CRI','PBL'].includes(code))return{generation:null,generation_label:'세대 단정 안 함',era:'MEGA'};return{generation:null,generation_label:'세대 확인 필요',era:'UNKNOWN'}}
function classify(input={}){
 const g=game(input.game),r=region(input.region),text=[input.card_name,input.card_number,input.product_name,input.ocr_text,input.market_key].filter(Boolean).join(' '),code=setCode(g,text),gen=generation(g,code),ra=rarity(g,text),v=variant(g,text),pt=productType(text);
 const identityKey=[g,r,clean(input.card_number),clean(input.card_name)].join('|');
 const variantKey=[identityKey,code,ra,v].join('|');
 const evidence=[g!=='unknown'&&'game',r!=='UNKNOWN'&&'region',input.card_number&&'card_number',input.card_name&&'card_name',code&&'set_code',ra!=='UNKNOWN'&&'rarity',v!=='base'&&'variant'].filter(Boolean);
 return {version:'v326',game:g,region:r,set_code:code,rarity:ra,variant:v,product_type:pt,...gen,identity_key:identityKey,variant_key:variantKey,evidence_count:evidence.length,evidence,status:g==='unknown'?'unknown':'classified'};
}
function bindPrice(card,market={}){
 const c=card?.version==='v326'?card:classify(card||{}),mg=game(market.game),mr=region(market.region),mtext=[market.card_name,market.card_number,market.product_name,market.market_key].filter(Boolean).join(' '),mc=setCode(mg,mtext),mra=rarity(mg,mtext),mv=variant(mg,mtext),mpt=productType(mtext);
 const conflicts=[];if(mg!=='unknown'&&c.game!==mg)conflicts.push('game');if(mr!=='UNKNOWN'&&c.region!=='UNKNOWN'&&c.region!==mr)conflicts.push('region');if(c.product_type!==mpt)conflicts.push('product_type');if(c.set_code&&mc&&c.set_code!==mc)conflicts.push('set_code');
 const cn=clean(c.identity_key.split('|')[2]),mn=clean(market.card_number);if(cn&&mn&&cn!==mn)conflicts.push('card_number');if(c.rarity!=='UNKNOWN'&&mra!=='UNKNOWN'&&c.rarity!==mra)conflicts.push('rarity');if(c.variant!==mv&&(c.variant!=='base'||mv!=='base'))conflicts.push('variant');
 const exact=conflicts.length===0&&c.game!=='unknown'&&c.region!=='UNKNOWN'&&c.product_type===mpt&&(c.product_type!=='CARD'||Boolean(cn&&mn));
 return {safe:exact,price_status:exact?'exact_variant_match':'blocked',conflicts,card_variant_key:c.variant_key,market_variant:{game:mg,region:mr,set_code:mc,rarity:mra,variant:mv,product_type:mpt},note:exact?'동일 판본/상품유형/카드번호 기준 가격 연결':'오인 시세 방지를 위해 자동 가격 연결 차단'};
}
root.TCGCardMetadata=Object.freeze({version:'v326',classify,bindPrice});
})(typeof window!=='undefined'?window:globalThis);
