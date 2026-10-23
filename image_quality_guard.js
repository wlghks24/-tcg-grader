(()=>{
'use strict';
const BAD_WORDS=['logo','favicon','avatar','sprite','banner'];
const watched=new WeakSet();
const CATALOG_SELECTOR='.box-kb-card img,.analysis-box img,.catalog-thumb,.tcg-v45-record img';
const LOCAL_IMAGE=/^\/api\/local-card-images\/file\/[a-f0-9]{32}$/;
function looksBadUrl(src){
  const raw=String(src||'');
  if(LOCAL_IMAGE.test(raw))return false;
  try{
    const url=new URL(raw);
    if(typeof location!=='undefined'&&url.origin===location.origin&&LOCAL_IMAGE.test(url.pathname)&&!url.search&&!url.hash)return false;
    return url.protocol!=='https:'||Boolean(url.username||url.password)||BAD_WORDS.some(x=>url.pathname.toLowerCase().includes(x));
  }catch(_){return true;}
}
function fallbacks(img){return img.parentElement?.querySelectorAll?.('.tcg-image-quality-fallback,.box-kb-fallback,.analysis-image-wait')||[];}
function fallbackFor(img){
  const parent=img.parentElement;if(!parent)return;
  let fb=parent.querySelector('.tcg-image-quality-fallback');
  if(!fb){
    fb=document.createElement('div');fb.className='tcg-image-quality-fallback';
    fb.textContent=(img.alt||'').toLowerCase().includes('box')?'📦 상품 이미지 확인 중':'🎴 카드 이미지 확인 중';
    fb.style.cssText='min-height:150px;display:flex;align-items:center;justify-content:center;color:#7a8797;font-weight:700;background:#f7f9fc;border-radius:12px;padding:16px;text-align:center';
    parent.insertBefore(fb,img.nextSibling);
  }
  for(const item of fallbacks(img))item.style.display=item===fb?'flex':'none';
  img.style.display='none';img.dataset.qualityRejected='1';
}
function check(img){
  if(looksBadUrl(img.currentSrc||img.src)){fallbackFor(img);return;}
  const w=img.naturalWidth||0,h=img.naturalHeight||0,ratio=w/h;
  // Readable card/product photo geometry is still required for local images.
  if(!w||!h||w*h<12000||ratio<0.28||ratio>3.2||(h>1400&&ratio<0.38)){fallbackFor(img);return;}
  img.dataset.qualityChecked='1';delete img.dataset.qualityRejected;
  img.style.display='block';img.style.objectFit='contain';img.style.maxHeight='340px';img.style.width='100%';
  for(const item of fallbacks(img))item.style.display='none';
}
function validate(img){
  if(!(img instanceof HTMLImageElement))return;
  // Listeners follow the image element across source replacement. A previous
  // rejection must not permanently reject a later verified local photo.
  if(!watched.has(img)){
    watched.add(img);
    img.addEventListener('load',()=>check(img));
    img.addEventListener('error',()=>fallbackFor(img));
  }
  if(img.complete)check(img);
}
function scan(root=document){root.querySelectorAll?.(CATALOG_SELECTOR).forEach(validate);}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>scan());else scan();
new MutationObserver(m=>{for(const x of m){
  if(x.type==='attributes'){if(x.target.matches?.(CATALOG_SELECTOR))validate(x.target);continue;}
  for(const n of x.addedNodes||[])if(n.nodeType===1){if(n.matches?.(CATALOG_SELECTOR))validate(n);scan(n);}
}}).observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['src','srcset']});
window.tcgValidateCatalogImages=()=>scan();
})();
