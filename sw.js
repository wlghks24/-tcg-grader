// v109: card identity OCR and confirmation-only visual learning.
const CACHE='tcg-v109-card-identity-ocr-learning';
const CORE=['./','./index.html','./grading_vision_engine.js','./grading_accuracy_v99.js','./card_identity_recognition.js','./vision_calibration.json','./manifest.webmanifest','./releases.json','./promo_events.json','./supplementary_candidates.json','./social_event_candidates.json','./purchase_sources.json','./purchase_signals.json','./market_prices.json','./market_watch.json','./exchange_rates.json','./icon.svg'];

self.addEventListener('install',event=>event.waitUntil(
  caches.open(CACHE).then(cache=>cache.addAll(CORE)).then(()=>self.skipWaiting())
));

self.addEventListener('activate',event=>event.waitUntil(
  caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key))))
    .then(()=>self.clients.claim())
));

async function rememberSuccessfulResponse(request,response){
  if(response&&response.ok&&response.type!=='opaque'){
    try{const cache=await caches.open(CACHE);await cache.put(request,response.clone())}
    catch(error){/* Storage quota failure must not break a successful live response. */}
  }
  return response;
}

async function unavailableResponse(request){
  const cached=await caches.match(request);
  if(cached)return cached;
  if(request.mode==='navigate'){
    const page=await caches.match('./index.html');
    if(page)return page;
    return new Response('오프라인 화면을 불러올 수 없습니다.',{
      status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store'}
    });
  }
  if(new URL(request.url).pathname.endsWith('.json')){
    return new Response(JSON.stringify({ok:false,error:'오프라인 상태이며 저장된 자료가 없습니다.'}),{
      status:503,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'}
    });
  }
  return new Response('오프라인 자료 없음',{
    status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store'}
  });
}

self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET')return;
  const url=new URL(event.request.url);
  if(url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;
  const fresh=event.request.mode==='navigate'||/\/(?:index\.html|releases\.json|promo_events\.json|supplementary_candidates\.json|social_event_candidates\.json|purchase_sources\.json|purchase_signals\.json|market_prices\.json|market_watch\.json|exchange_rates\.json)$/.test(url.pathname);
  if(fresh){
    event.respondWith(fetch(event.request).then(response=>rememberSuccessfulResponse(event.request,response))
      .catch(()=>unavailableResponse(event.request)));
    return;
  }
  event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request)
    .then(response=>rememberSuccessfulResponse(event.request,response))
    .catch(()=>unavailableResponse(event.request))));
});
