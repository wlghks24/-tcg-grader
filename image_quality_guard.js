(()=>{
'use strict';
const BAD_WORDS=['logo','favicon','avatar','sprite','banner'];
function looksBadUrl(src){const s=String(src||'').toLowerCase();return !s.startsWith('https://')||BAD_WORDS.some(x=>s.includes(x));}
function fallbackFor(img){
  const parent=img.parentElement;if(!parent)return;
  let fb=parent.querySelector('.tcg-image-quality-fallback');
  if(!fb){
    fb=document.createElement('div');fb.className='tcg-image-quality-fallback';
    fb.textContent=(img.alt||'').toLowerCase().includes('box')?'📦 상품 이미지 확인 중':'🎴 카드 이미지 확인 중';
    fb.style.cssText='min-height:150px;display:flex;align-items:center;justify-content:center;color:#7a8797;font-weight:700;background:#f7f9fc;border-radius:12px;padding:16px;text-align:center';
    parent.insertBefore(fb,img.nextSibling);
  }
  img.style.display='none';fb.style.display='flex';img.dataset.qualityRejected='1';
}
function validate(img){
  if(!(img instanceof HTMLImageElement)||img.dataset.qualityChecked==='1')return;
  img.dataset.qualityChecked='1';
  const check=()=>{
    if(looksBadUrl(img.currentSrc||img.src)){fallbackFor(img);return;}
    const w=img.naturalWidth||0,h=img.naturalHeight||0;
    if(!w||!h){fallbackFor(img);return;}
    const ratio=w/h,area=w*h;
    // Product/card photos should not be tiny icons or full-page screenshots.
    if(area<12000 || ratio<0.28 || ratio>3.2 || (h>1400&&ratio<0.38)){fallbackFor(img);return;}
    img.style.objectFit='contain';img.style.maxHeight='340px';img.style.width='100%';
  };
  if(img.complete)check();else{img.addEventListener('load',check,{once:true});img.addEventListener('error',()=>fallbackFor(img),{once:true});}
}
function scan(root=document){root.querySelectorAll?.('.box-kb-card img,.analysis-box img,.catalog-thumb').forEach(validate);}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>scan());else scan();
new MutationObserver(m=>{for(const x of m)for(const n of x.addedNodes)if(n.nodeType===1){if(n.matches?.('img'))validate(n);scan(n);}}).observe(document.documentElement,{childList:true,subtree:true});
window.tcgValidateCatalogImages=()=>scan();
})();