const CACHE='tcg-v31-tablet-auto-secure-34';
const CORE=['./','./index.html','./manifest.webmanifest','./releases.json','./promo_events.json','./purchase_sources.json','./market_prices.json','./market_watch.json','./exchange_rates.json','./icon.svg'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET' || new URL(event.request.url).pathname.startsWith('/api/')) return;
  const url=new URL(event.request.url),fresh=event.request.mode==='navigate'||/\/(?:index\.html|releases\.json|promo_events\.json|purchase_sources\.json|market_prices\.json|market_watch\.json|exchange_rates\.json)$/.test(url.pathname);
  if(fresh){event.respondWith(fetch(event.request).then(response=>{const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy));return response}).catch(()=>caches.match(event.request).then(x=>x||caches.match('./index.html'))));return}
  event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request).then(response=>{const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy));return response}).catch(()=>caches.match('./index.html'))));
});
