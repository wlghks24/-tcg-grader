(()=>{
'use strict';
const esc=v=>String(v??'');
function prefFromSignal(v){const n=Number(v||0);return n>=82?'매우 높음':n>=68?'높음':n>=52?'보통':'관찰 중'}
function addOrEnrich(row,key,value){
  if(!Array.isArray(window.COUNTRY_BOX_DATA)&&typeof COUNTRY_BOX_DATA==='undefined')return false;
  const arr=typeof COUNTRY_BOX_DATA!=='undefined'?COUNTRY_BOX_DATA:window.COUNTRY_BOX_DATA;
  const [country,name,asset]=key.split('|');if(!country||!name||!asset)return false;
  const game=value.game||'확인 중';
  let item=arr.find(x=>x.country===country&&x.name===name);
  if(item){
    if(asset==='BOX'&&!item.boxImage&&value.image_url)item.boxImage=value.image_url;
    if(asset==='HIT'&&!item.cardImage&&value.image_url)item.cardImage=value.image_url;
    if(asset==='HIT'&&!item.hitName)item.hitName=value.card_name||name;
    if(asset==='HIT'&&!item.hit)item.hit=value.card_name||name;
    if(!item.preference||item.preference==='확인 중')item.preference=prefFromSignal(value.preference_signal);
    return false;
  }
  if(!value.discovered_market)return false;
  const isBox=asset==='BOX';
  item={country,game,name,native:value.product_name||name,release:value.source_date||'최근 시장 발견',
    preference:prefFromSignal(value.preference_signal),reason:`다중마켓 ${Math.max(1,(value.source_crosschecks||[]).length)}개 출처 교차발견`,
    hit:isBox?'대표 HIT 자동수집 중':(value.card_name||name),hitName:isBox?'대표 HIT 자동수집 중':(value.card_name||name),
    source:value.source||'',marketDiscovered:true};
  if(isBox&&value.image_url)item.boxImage=value.image_url;
  if(!isBox&&value.image_url)item.cardImage=value.image_url;
  arr.push(item);return true;
}
async function expand(){
  try{
    const r=await fetch('market_prices.json?_='+Date.now(),{cache:'no-store'});if(!r.ok)return;
    const d=await r.json(), entries=d.entries||{};let added=0;
    Object.entries(entries).forEach(([k,v])=>{if(addOrEnrich(v,k,v))added++});
    if(typeof renderBoxKnowledge==='function')renderBoxKnowledge();
    if(typeof renderCountryAnalysis==='function')renderCountryAnalysis();
    if(typeof renderTradeCatalog==='function')renderTradeCatalog();
    window.dispatchEvent(new CustomEvent('tcg-market-catalog-expanded',{detail:{added,total:Object.keys(entries).length}}));
  }catch(_e){}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(expand,350));else setTimeout(expand,350);
window.tcgExpandMarketCatalog=expand;
})();
