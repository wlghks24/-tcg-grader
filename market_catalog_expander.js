(()=>{
'use strict';
function prefFromSignal(v){const n=Number(v||0);return n>=82?'매우 높음':n>=68?'높음':n>=52?'보통':'관찰 중'}
function hasPrice(value){const d=String(value?.display||'').trim();return !!d&&!/가격 확인 중|확인 중|미정/.test(d)}
function getArr(){try{return Array.isArray(COUNTRY_BOX_DATA)?COUNTRY_BOX_DATA:[]}catch(_){return []}}
function addOrEnrich(_row,key,value){
  const arr=getArr();if(!arr.length&&typeof COUNTRY_BOX_DATA==='undefined')return false;
  const [country,name,asset]=key.split('|');if(!country||!name||!asset)return false;
  const game=value.game||'확인 중';
  let item=arr.find(x=>x.country===country&&x.name===name);
  if(item){
    if(asset==='BOX'&&!item.boxImage&&value.image_url)item.boxImage=value.image_url;
    if(asset==='HIT'&&!item.cardImage&&value.image_url)item.cardImage=value.image_url;
    if(asset==='HIT'&&!item.hitName)item.hitName=value.card_name||name;
    if(asset==='HIT'&&!item.hit)item.hit=value.card_name||name;
    if(!item.preference||item.preference==='확인 중')item.preference=prefFromSignal(value.preference_signal);
    if(asset==='BOX'&&hasPrice(value))item.marketTrading=true;
    if(asset==='BOX'&&value.release_date&&!item.release)item.release=value.release_date;
    return false;
  }
  const isBox=asset==='BOX';
  const isTradingBox=isBox&&hasPrice(value);
  if(!value.discovered_market&&!isTradingBox)return false;
  item={country,game,name,native:value.product_name||name,release:value.release_date||'최근 시장 발견',
    preference:prefFromSignal(value.preference_signal),
    reason:value.discovered_market?`다중마켓 ${Math.max(1,(value.source_crosschecks||[]).length)}개 출처 교차발견`:'현재 공개 시장 가격 신호 확인',
    hit:isBox?'대표 HIT 자동수집 중':(value.card_name||name),hitName:isBox?'대표 HIT 자동수집 중':(value.card_name||name),
    source:value.source||'',marketDiscovered:!!value.discovered_market,marketTrading:isTradingBox};
  if(isBox&&value.image_url)item.boxImage=value.image_url;
  if(!isBox&&value.image_url)item.cardImage=value.image_url;
  arr.push(item);return true;
}
function addRelease(row){
  const arr=getArr();const country=String(row?.region||'').toUpperCase();
  if(!['KR','JP','US'].includes(country)||!row?.name||!row?.game)return false;
  const name=String(row.name).trim();let item=arr.find(x=>x.country===country&&x.name===name);
  if(item){
    if(row.release_date)item.release=row.release_date;
    if(row.price&&!item.officialPrice)item.officialPrice=row.price;
    if(row.source&&!item.source)item.source=row.source;
    item.releaseHistory=true;return false;
  }
  arr.push({country,game:row.game,name,native:name,release:row.release_date||row.release_window||'확인 중',
    preference:'확인 중',reason:'공식 출시이력에서 확인',hit:'대표 HIT 정보 확인 중',hitName:'대표 HIT 정보 확인 중',
    source:row.source||'',officialPrice:row.price||'',releaseHistory:true});
  return true;
}
async function loadJson(path){try{const r=await fetch(path+'?_='+Date.now(),{cache:'no-store'});if(!r.ok)return {};return await r.json()}catch(_){return {}}}
async function expand(){
  try{
    const [market,releases]=await Promise.all([loadJson('market_prices.json'),loadJson('releases.json')]);
    const entries=market.entries||{};let added=0,historyAdded=0;
    for(const row of (releases.items||[]))if(addRelease(row)){added++;historyAdded++}
    Object.entries(entries).forEach(([k,v])=>{if(addOrEnrich(v,k,v))added++});
    if(typeof renderBoxKnowledge==='function')renderBoxKnowledge();
    if(typeof renderCountryAnalysis==='function')renderCountryAnalysis();
    if(typeof renderTradeCatalog==='function')renderTradeCatalog();
    window.dispatchEvent(new CustomEvent('tcg-market-catalog-expanded',{detail:{added,historyAdded,total:Object.keys(entries).length,releaseHistory:(releases.items||[]).length}}));
  }catch(_e){}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(expand,350));else setTimeout(expand,350);
window.tcgExpandMarketCatalog=expand;
})();
