(()=>{
'use strict';
function prefFromSignal(v){
  if(typeof v!=='number'&&(typeof v!=='string'||!v.trim()))return '관찰 중';
  const n=Number(v);
  if(!Number.isFinite(n)||n<0||n>100)return '관찰 중';
  return n>=82?'매우 높음':n>=68?'높음':n>=52?'보통':'관찰 중';
}
function hasPrice(value){const d=String(value?.display||'').trim();return !!d&&!/가격 확인 중|확인 중|미정/.test(d)}
// A price alone is NOT verified recent activity. Use exact source dates in KST.
function hasRecentMarketEvidence(value){
  if(!value||typeof value!=='object'||Array.isArray(value)||!hasPrice(value))return false;
  if(value.link_status!=='정상')return false;
  const day=String(value.market_observed_at||value.source_date||'').trim();
  if(!/^20\d{2}-\d{2}-\d{2}$/.test(day))return false;
  const [year,month,date]=day.split('-').map(Number);
  const observed=Date.UTC(year,month-1,date),parsed=new Date(observed);
  if(parsed.getUTCFullYear()!==year||parsed.getUTCMonth()+1!==month||parsed.getUTCDate()!==date)return false;
  const kst=new Date(Date.now()+9*60*60*1000);
  const today=Date.UTC(kst.getUTCFullYear(),kst.getUTCMonth(),kst.getUTCDate());
  const age=(today-observed)/86400000;
  if(age<0||age>14)return false;
  try{
    const url=new URL(String(value.source||''));
    return url.protocol==='https:'&&!url.username&&!url.password&&(!url.port||url.port==='443');
  }catch(_){return false}
}
function getArr(){try{return Array.isArray(COUNTRY_BOX_DATA)?COUNTRY_BOX_DATA:[]}catch(_){return []}}
function addOrEnrich(_row,key,value){
  if(!value||typeof value!=='object'||Array.isArray(value)||typeof key!=='string')return false;
  const arr=getArr();if(!arr.length&&typeof COUNTRY_BOX_DATA==='undefined')return false;
  const parts=key.split('|');if(parts.length!==3)return false;
  const [country,name,asset]=parts;
  if(!['KR','JP','US','GLOBAL'].includes(country)||!name.trim()||!['BOX','HIT'].includes(asset))return false;
  const game=typeof value.game==='string'&&value.game.trim()?value.game.trim():'확인 중';
  let item=arr.find(x=>x&&x.country===country&&x.name===name&&String(x.game||'')===game);
  if(item){
    if(asset==='BOX'&&!item.boxImage&&value.image_url)item.boxImage=value.image_url;
    if(asset==='HIT'&&!item.cardImage&&value.image_url)item.cardImage=value.image_url;
    if(asset==='HIT'&&!item.hitName)item.hitName=value.card_name||name;
    if(asset==='HIT'&&!item.hit)item.hit=value.card_name||name;
    if(!item.preference||item.preference==='확인 중')item.preference=prefFromSignal(value.preference_signal);
    if(asset==='BOX')item.marketTrading=hasRecentMarketEvidence(value);
    if(asset==='BOX'&&value.release_date&&!item.release)item.release=value.release_date;
    return false;
  }
  const isBox=asset==='BOX';
  const isTradingBox=isBox&&hasRecentMarketEvidence(value);
  if(value.discovered_market!==true&&!isTradingBox)return false;
  item={country,game,name,native:value.product_name||name,release:value.release_date||'최근 시장 발견',
    preference:prefFromSignal(value.preference_signal),
    reason:value.discovered_market?`다중마켓 ${Math.max(1,(value.source_crosschecks||[]).length)}개 출처 교차발견`:'현재 공개 시장 가격 신호 확인',
    hit:isBox?'대표 HIT 자동수집 중':(value.card_name||name),hitName:isBox?'대표 HIT 자동수집 중':(value.card_name||name),
    source:value.source||'',marketDiscovered:value.discovered_market===true,marketTrading:isTradingBox};
  if(isBox&&value.image_url)item.boxImage=value.image_url;
  if(!isBox&&value.image_url)item.cardImage=value.image_url;
  arr.push(item);return true;
}
function addRelease(row){
  if(!row||typeof row!=='object'||Array.isArray(row))return false;
  const arr=getArr();const country=String(row.region||'').toUpperCase();
  if(!['KR','JP','US','GLOBAL'].includes(country)||typeof row.name!=='string'||!row.name.trim()||typeof row.game!=='string'||!row.game.trim())return false;
  const name=row.name.trim(),game=row.game.trim();
  let item=arr.find(x=>x&&x.country===country&&x.name===name&&String(x.game||'')===game);
  if(item){
    if(row.release_date)item.release=row.release_date;
    if(row.price&&!item.officialPrice)item.officialPrice=row.price;
    if(row.source&&!item.source)item.source=row.source;
    item.releaseHistory=true;return false;
  }
  arr.push({country,game,name,native:name,release:row.release_date||row.release_window||'확인 중',
    preference:'확인 중',reason:'공식 출시이력에서 확인',hit:'대표 HIT 정보 확인 중',hitName:'대표 HIT 정보 확인 중',
    source:row.source||'',officialPrice:row.price||'',releaseHistory:true});
  return true;
}
async function loadJson(path){try{const r=await fetch(path+'?_='+Date.now(),{cache:'no-store'});if(!r.ok)return {};return await r.json()}catch(_){return {}}}
async function expand(){
  try{
    const [market,releases]=await Promise.all([loadJson('market_prices.json'),loadJson('releases.json')]);
    const entries=market.entries||{};let added=0,historyAdded=0;
    const releaseRows=[...(Array.isArray(releases.items)?releases.items:[]),...(Array.isArray(releases.archive_items)?releases.archive_items:[])];
    for(const row of releaseRows)if(addRelease(row)){added++;historyAdded++;}
    Object.entries(entries).forEach(([k,v])=>{if(addOrEnrich(v,k,v))added++});
    if(typeof renderBoxKnowledge==='function')renderBoxKnowledge();
    if(typeof renderCountryAnalysis==='function')renderCountryAnalysis();
    if(typeof renderTradeCatalog==='function')renderTradeCatalog();
    window.dispatchEvent(new CustomEvent('tcg-market-catalog-expanded',{detail:{added,historyAdded,total:Object.keys(entries).length,releaseHistory:releaseRows.length}}));
  }catch(_e){}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(expand,350));else setTimeout(expand,350);
window.tcgExpandMarketCatalog=expand;
})();
