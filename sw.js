// v118: high-contrast game selector labels + representative category illustrations.
const CACHE='tcg-v118-game-selector-visual-fix';
const CORE=['./','./index.html','./grading_vision_engine.js','./grading_accuracy_v99.js','./card_identity_recognition.js','./vision_calibration.json','./manifest.webmanifest','./releases.json','./promo_events.json','./supplementary_candidates.json','./social_event_candidates.json','./purchase_sources.json','./purchase_signals.json','./market_prices.json','./market_watch.json','./exchange_rates.json','./icon.svg'];

const GAME_SELECTOR_STYLE=`
<style id="tcg-game-selector-v118">
/* v118: game names must remain readable regardless of global button/active styles. */
.simple-game-grid{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:10px!important}
.simple-game{
  min-height:92px!important;margin-top:8px!important;padding:10px 8px!important;
  display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:5px!important;
  background:#fff!important;color:#111827!important;border:2px solid #cbd5e1!important;
  font-size:0!important;font-weight:900!important;line-height:1.1!important;
  text-shadow:none!important;-webkit-text-fill-color:#111827!important;
  box-shadow:0 2px 8px #0f172a0d!important;
}
.simple-game::before{display:block!important;font-size:34px!important;line-height:1!important;filter:none!important}
.simple-game::after{display:block!important;font-size:18px!important;line-height:1.15!important;font-weight:900!important;letter-spacing:-.3px!important;color:#111827!important;-webkit-text-fill-color:#111827!important}
.simple-game[data-simple-game="pokemon"]{border-color:#60a5fa!important;background:linear-gradient(180deg,#eff6ff,#fff)!important}
.simple-game[data-simple-game="pokemon"]::before{content:'⚡'!important}
.simple-game[data-simple-game="pokemon"]::after{content:'포켓몬'!important;color:#1e3a8a!important;-webkit-text-fill-color:#1e3a8a!important}
.simple-game[data-simple-game="onepiece"]{border-color:#f87171!important;background:linear-gradient(180deg,#fff1f2,#fff)!important}
.simple-game[data-simple-game="onepiece"]::before{content:'👒'!important}
.simple-game[data-simple-game="onepiece"]::after{content:'원피스'!important;color:#7f1d1d!important;-webkit-text-fill-color:#7f1d1d!important}
.simple-game[data-simple-game="naruto"]{border-color:#fb923c!important;background:linear-gradient(180deg,#fff7ed,#fff)!important}
.simple-game[data-simple-game="naruto"]::before{content:'🥷'!important}
.simple-game[data-simple-game="naruto"]::after{content:'나루토'!important;color:#9a3412!important;-webkit-text-fill-color:#9a3412!important}
.simple-game.active{outline:3px solid #2563eb!important;outline-offset:1px!important;box-shadow:0 0 0 3px #dbeafe!important}
.simple-game:focus-visible{outline:4px solid #0f172a!important;outline-offset:2px!important}
@media(max-width:430px){
  .simple-game-grid{grid-template-columns:1fr!important}
  .simple-game{min-height:72px!important;flex-direction:row!important;gap:12px!important}
  .simple-game::before{font-size:30px!important}.simple-game::after{font-size:19px!important}
}
</style>`;

self.addEventListener('install',event=>event.waitUntil(
  caches.open(CACHE).then(cache=>cache.addAll(CORE)).then(()=>self.skipWaiting())
));

self.addEventListener('activate',event=>event.waitUntil(
  caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key))))
    .then(()=>self.clients.claim())
));

async function enhanceNavigationResponse(response){
  if(!response||!response.ok||response.type==='opaque')return response;
  const type=(response.headers.get('content-type')||'').toLowerCase();
  if(!type.includes('text/html'))return response;
  try{
    let text=await response.clone().text();
    if(!text.includes('id="tcg-game-selector-v118"')){
      text=text.includes('</head>')?text.replace('</head>',`${GAME_SELECTOR_STYLE}\n</head>`):`${GAME_SELECTOR_STYLE}\n${text}`;
    }
    const headers=new Headers(response.headers);
    headers.set('Content-Type','text/html; charset=utf-8');
    headers.set('Cache-Control','no-cache');
    headers.delete('Content-Length');
    return new Response(text,{status:response.status,statusText:response.statusText,headers});
  }catch(error){return response}
}

async function rememberSuccessfulResponse(request,response){
  if(response&&response.ok&&response.type!=='opaque'){
    try{const cache=await caches.open(CACHE);await cache.put(request,response.clone())}
    catch(error){/* Storage quota failure must not break a successful live response. */}
  }
  return response;
}

async function unavailableResponse(request){
  const cached=await caches.match(request);
  if(cached)return request.mode==='navigate'?enhanceNavigationResponse(cached):cached;
  if(request.mode==='navigate'){
    const page=await caches.match('./index.html');
    if(page)return enhanceNavigationResponse(page);
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
    event.respondWith(fetch(event.request)
      .then(response=>event.request.mode==='navigate'?enhanceNavigationResponse(response):response)
      .then(response=>rememberSuccessfulResponse(event.request,response))
      .catch(()=>unavailableResponse(event.request)));
    return;
  }
  event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request)
    .then(response=>rememberSuccessfulResponse(event.request,response))
    .catch(()=>unavailableResponse(event.request))));
});
