(()=>{
'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const normCountry=v=>['KR','JP','US'].includes(v)?v:'ALL';
const validRelease=v=>{
  const s=String(v||'').trim();
  return !!s && !/최근 시장 발견|확인 중|미정|예정$/.test(s);
};
const validImage=v=>/^https:\/\//i.test(String(v||''));
const priced=v=>{
  const d=String(v?.display||'').trim();
  return !!d && !/가격 확인 중|확인 중|미정/.test(d);
};
function getCatalog(){
  try{return Array.isArray(COUNTRY_BOX_DATA)?COUNTRY_BOX_DATA:[]}catch(_){return []}
}
async function loadMarket(){
  try{
    const r=await fetch('market_prices.json?_='+Date.now(),{cache:'no-store'});
    if(!r.ok)return {entries:{}};
    const d=await r.json();return d&&typeof d==='object'?d:{entries:{}};
  }catch(_){return {entries:{}}}
}
function countryOfKey(key){return String(key||'').split('|')[0]||''}
function assetOfKey(key){return String(key||'').split('|')[2]||''}
function nameOfKey(key){return String(key||'').split('|')[1]||''}
function uniqueKey(country,name){return `${country}|${String(name||'').trim().toLowerCase()}`}
function ensureUi(){
  const count=$('boxKbCount');if(!count)return null;
  let panel=$('boxKnowledgeStats');
  if(!panel){
    panel=document.createElement('section');panel.id='boxKnowledgeStats';panel.className='boxkb-stats';
    panel.innerHTML=`
      <div class="boxkb-stat-grid">
        <article><span>📚 누적 출시 확인</span><strong id="boxStatReleased">-</strong><small>출시일이 확인된 BOX</small></article>
        <article><span>💹 현재 거래 확인</span><strong id="boxStatTrading">-</strong><small>현재 가격 신호가 있는 BOX</small></article>
        <article><span>🤖 자동발견 BOX</span><strong id="boxStatDiscovered">-</strong><small>다중마켓 교차발견</small></article>
        <article><span>🖼️ 이미지 확인 BOX</span><strong id="boxStatImages">-</strong><small>HTTPS 상품 이미지 확보</small></article>
      </div>
      <div id="boxStatNote" class="boxkb-stat-note">기본 등록 목록은 참고자료이며 시장 전체 수량을 뜻하지 않습니다.</div>`;
    count.insertAdjacentElement('afterend',panel);
  }
  return panel;
}
async function refresh(){
  if(!ensureUi())return;
  const country=normCountry(window.selectedBoxKbCountry||'ALL');
  const catalog=getCatalog();
  const market=await loadMarket();const entries=market.entries||{};
  const inCountry=c=>country==='ALL'||c===country;
  const released=new Set();const trading=new Set();const discovered=new Set();const images=new Set();const base=new Set();
  for(const x of catalog){
    const c=x.country||'';if(!inCountry(c))continue;
    const k=uniqueKey(c,x.name);base.add(k);
    if(validRelease(x.release))released.add(k);
    if(validImage(x.boxImage))images.add(k);
    if(x.marketDiscovered)discovered.add(k);
  }
  for(const [key,v] of Object.entries(entries)){
    if(assetOfKey(key)!=='BOX')continue;
    const c=countryOfKey(key);if(!inCountry(c))continue;
    const name=nameOfKey(key);const k=uniqueKey(c,name);
    if(priced(v))trading.add(k);
    if(v?.discovered_market)discovered.add(k);
    if(validImage(v?.image_url))images.add(k);
    if(validRelease(v?.source_date)||validRelease(v?.release_date))released.add(k);
  }
  $('boxStatReleased').textContent=`${released.size}개`;
  $('boxStatTrading').textContent=`${trading.size}개`;
  $('boxStatDiscovered').textContent=`${discovered.size}개`;
  $('boxStatImages').textContent=`${images.size}개`;
  const label=country==='KR'?'한국':country==='JP'?'일본':country==='US'?'미국':'전체 국가';
  const note=$('boxStatNote');if(note)note.textContent=`${label} 기준 · 기본 등록 ${base.size}개는 참고용이며, 위 숫자는 출시·시장·자동발견 자료를 각각 따로 집계합니다.`;
  const count=$('boxKbCount');if(count)count.textContent=`📦 ${label} BOX 지식베이스 · 기본등록 ${base.size}개 + 자동확장`;
}
window.addEventListener('tcg-market-catalog-expanded',()=>setTimeout(refresh,50));
document.addEventListener('click',e=>{
  const t=e.target.closest?.('button');if(!t)return;
  if(/한국|일본|미국|전체/.test(t.textContent||''))setTimeout(refresh,120);
});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(refresh,500));else setTimeout(refresh,500);
setInterval(refresh,60000);
window.refreshBoxKnowledgeStats=refresh;
})();
