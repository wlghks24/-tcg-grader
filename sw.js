// v159 refreshes paired eight-zone registration and oblique-light cross-check features.
const CACHE='tcg-v159-eight-zone-oblique-crosscheck';
const CORE=['./','./index.html','./purchase_ui_polish.css','./ui_polish_v121.css','./ui_tablet_refine_v122.css','./graded_photo_dashboard.js','./graded_photo_dashboard.css','./graded_photo_candidates.json','./auto_market_center.js','./auto_market_center.css','./auto_validation_flow.js','./auto_validation_flow.css','./box_knowledge_stats.js','./box_knowledge_stats.css','./grade_market_flow.js','./grade_market_flow.css','./grading_costs_live.js','./grading_costs_live.css','./grading_proxy_costs.js','./grading_proxy_costs.css','./grading_total_cost.js','./grading_total_cost.css','./image_quality_guard.js','./inventory_lookup.js','./inventory_lookup.css','./market_catalog_expander.js','./multi_market_prices.js','./multi_market_prices.css','./grading_vision_engine.js','./grading_accuracy_v99.js','./card_identity_recognition.js','./vision_calibration.json','./manifest.webmanifest','./releases.json','./promo_events.json','./supplementary_candidates.json','./social_event_candidates.json','./purchase_sources.json','./purchase_signals.json','./market_prices.json','./market_watch.json','./exchange_rates.json','./icon.svg'];

const GAME_SELECTOR_STYLE=`
<style id="tcg-game-selector-v118">
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

const READABILITY_STYLE=`
<style id="tcg-readability-v129">
/* Force readable text on the app's intentional white/light panels. This is injected
   by the service worker so it still works when an external CSS link is stale or missing. */
.simple-grade-card,.validation-hub,.workflow-card,.precision-hub,.economics-card,
.grading-total-panel,.multi-market-panel,.auto-validation-panel,.graded-photo-dashboard,
.update-panel,.workflow-part,.precision-step,.precision-tool,.compact-details,
.validation-stats .metric,.economics-result,.v13-result-card,.capture-tile{
  color-scheme:light!important;
}

.simple-grade-title,
.simple-grade-card h1,.simple-grade-card h2,.simple-grade-card h3,.simple-grade-card h4,
.validation-hub h1,.validation-hub h2,.validation-hub h3,.validation-hub h4,
.workflow-card h1,.workflow-card h2,.workflow-card h3,.workflow-card h4,
.precision-hub h1,.precision-hub h2,.precision-hub h3,.precision-hub h4,
.economics-card h1,.economics-card h2,.economics-card h3,.economics-card h4,
.grading-total-panel h1,.grading-total-panel h2,.grading-total-panel h3,.grading-total-panel h4,
.multi-market-panel h1,.multi-market-panel h2,.multi-market-panel h3,.multi-market-panel h4,
.auto-validation-panel h1,.auto-validation-panel h2,.auto-validation-panel h3,.auto-validation-panel h4,
.graded-photo-dashboard h1,.graded-photo-dashboard h2,.graded-photo-dashboard h3,.graded-photo-dashboard h4,
.update-panel h1,.update-panel h2,.update-panel h3,.update-panel h4,
.workflow-part h3,.precision-step-title,.precision-tool h4,.capture-label,
.validation-stats .metric b,.economics-result b,.v13-result-title{
  color:#0f172a!important;
  -webkit-text-fill-color:#0f172a!important;
  opacity:1!important;
  text-shadow:none!important;
  mix-blend-mode:normal!important;
}

.simple-grade-sub,.simple-grade-card .simple-note,.simple-grade-card .muted,
.validation-hub p,.validation-hub label,.validation-hub legend,.validation-hub .muted,
.workflow-card p,.workflow-card label,.workflow-card legend,.workflow-card .muted,
.precision-hub p,.precision-hub label,.precision-hub legend,.precision-hub .muted,
.economics-card p,.economics-card label,.economics-card legend,.economics-card .muted,
.grading-total-panel p,.grading-total-panel label,.grading-total-panel .muted,
.multi-market-panel p,.multi-market-panel label,.multi-market-panel .muted,
.auto-validation-panel p,.auto-validation-panel label,.auto-validation-panel .muted,
.graded-photo-dashboard p,.graded-photo-dashboard label,.graded-photo-dashboard .muted,
.update-panel p,.update-panel label,.update-panel .muted,.update-step-note,
.capture-tile .muted,.guide-note,.analysis-native,.analysis-sub,.v13-result-native,
.validation-stats .metric{
  color:#475569!important;
  -webkit-text-fill-color:#475569!important;
  opacity:1!important;
  text-shadow:none!important;
  mix-blend-mode:normal!important;
}

.validation-hub .workflow-part,.validation-hub .compact-details,
.validation-stats .metric,.workflow-card .workflow-part,
.precision-hub .precision-step,.precision-hub .precision-tool,
.capture-tile,.economics-result,.v13-result-card{
  background:#fff!important;
  border-color:#cbd5e1!important;
}

.validation-hub input,.validation-hub select,.validation-hub textarea,
.workflow-card input,.workflow-card select,.workflow-card textarea,
.precision-hub input,.precision-hub select,.precision-hub textarea,
.economics-card input,.economics-card select,.economics-card textarea,
.grading-total-panel input,.grading-total-panel select,.grading-total-panel textarea,
.simple-grade-card input,.simple-grade-card select,.simple-grade-card textarea{
  background:#fff!important;
  color:#0f172a!important;
  -webkit-text-fill-color:#0f172a!important;
  border-color:#64748b!important;
  opacity:1!important;
}
.validation-hub input::placeholder,.validation-hub textarea::placeholder,
.workflow-card input::placeholder,.workflow-card textarea::placeholder,
.precision-hub input::placeholder,.precision-hub textarea::placeholder,
.economics-card input::placeholder,.economics-card textarea::placeholder,
.simple-grade-card input::placeholder,.simple-grade-card textarea::placeholder{
  color:#64748b!important;
  -webkit-text-fill-color:#64748b!important;
  opacity:1!important;
}

/* Keep intentional dark action/status blocks readable. */
.simple-grade-card button,.validation-hub button,.workflow-card button,
.precision-hub button,.economics-card button,.grading-total-panel button,
.update-panel button,.camera-status,.gpd-company{
  -webkit-text-fill-color:currentColor!important;
}
.simple-grade-card button:not(.simple-game),.validation-hub button,.workflow-card button,
.precision-hub button,.economics-card button,.grading-total-panel button,.update-panel button{
  color:#fff!important;
}
.simple-game,.simple-game .game-label{
  color:#0f172a!important;
  -webkit-text-fill-color:#0f172a!important;
}

@media(max-width:650px){
  .validation-hub .grid2,.validation-actions,.validation-stats{
    grid-template-columns:1fr!important;min-width:0!important;
  }
  .validation-hub input,.validation-hub select,.simple-grade-card input,.simple-grade-card select{
    max-width:100%!important;min-width:0!important;
  }
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
    const styles=[];
    if(!text.includes('id="tcg-game-selector-v118"'))styles.push(GAME_SELECTOR_STYLE);
    if(!text.includes('id="tcg-readability-v129"'))styles.push(READABILITY_STYLE);
    if(styles.length){
      const block=styles.join('\n');
      text=text.includes('</head>')?text.replace('</head>',`${block}\n</head>`):`${block}\n${text}`;
    }
    const headers=new Headers(response.headers);
    headers.set('Content-Type','text/html; charset=utf-8');
    headers.set('Cache-Control','no-cache, no-store, must-revalidate');
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
  const fresh=event.request.mode==='navigate'||/\/(?:index\.html|graded_photo_candidates\.json|releases\.json|promo_events\.json|supplementary_candidates\.json|social_event_candidates\.json|purchase_sources\.json|purchase_signals\.json|market_prices\.json|market_watch\.json|exchange_rates\.json)$/.test(url.pathname);
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
