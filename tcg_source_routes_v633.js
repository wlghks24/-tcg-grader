/* V633 — zero-dependency source-link recovery for 30 TCG games.
 * External links are SEARCH ROUTES, never automatic manufacturer proof.
 * Browsers cannot reliably probe external HTTP status because of CORS.
 */
(function(root,factory){
  "use strict";
  const api=factory();
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  if(root&&root.document)root.TcgSourceRoutesV633=api;
})(typeof globalThis!=="undefined"?globalThis:this,function(){
  "use strict";
  function safeUrl(value){
    if(typeof value!=="string"||!value||value.length>1000)return null;
    try{
      const u=new URL(value);
      if(u.protocol!=="https:"||u.username||u.password||u.hash||
          (u.port&&u.port!=="443")||!u.hostname||u.hostname==="localhost"||
          /^\d+\.\d+\.\d+\.\d+$/.test(u.hostname)||
          /\.(local|test|invalid)$/.test(u.hostname))return null;
      return u;
    }catch(_){return null;}
  }
  function inSameSourceFamily(host,rootHost){
    const normalize=x=>String(x||"").toLowerCase().replace(/^(www\.|en\.|legacy\.)/,"");
    const h=normalize(host),r=normalize(rootHost);
    return h===r||h.endsWith("."+r)||r.endsWith("."+h);
  }
  function siteSearch(source,name,setCode){
    const u=safeUrl(source);if(!u)return null;
    const terms=["site:"+u.hostname];
    for(const value of [name,setCode]){
      if(typeof value==="string"&&value.trim()&&value.length<=180&&!/[\r\n"<>]/.test(value))
        terms.push('"'+value.trim()+'"');
    }
    return "https://www.google.com/search?q="+encodeURIComponent(terms.join(" "));
  }
  function sourceRoutes(product,registry){
    if(!product||!registry||!Array.isArray(registry.games))return null;
    const src=safeUrl(product.source);if(!src)return null;
    const game=registry.games.find(g=>g.canonical===product.game);
    if(!game)return null;
    const hub=safeUrl(game.official_source);
    const sameFamily=hub&&inSameSourceFamily(src.hostname,hub.hostname);
    return Object.freeze({
      original:src.href,
      officialIndex:sameFamily?hub.href:null,
      manufacturerSiteSearch:siteSearch(src.href,product.name,product.set_code),
      warning:"제조사 출처의 현재 접속 상태는 미검증입니다. 404·403·429·5xx면 원문 확인 후 수동 재검증하십시오."
    });
  }
  function classifyStatus(status){
    if(Number.isInteger(status)&&status>=200&&status<300)return "HTTP_OK_NOT_CONTENT_VERIFIED";
    if([301,302,303,307,308].includes(status))return "REDIRECT_REVIEW";
    if(status===404||status===410)return "BROKEN_LINK_REVIEW";
    if(status===401||status===403)return "ACCESS_RESTRICTED_UNVERIFIED";
    if(status===429)return "RATE_LIMIT_PAUSE";
    if([408,425,500,502,503,504].includes(status))return "TEMPORARY_FAILURE";
    return "UNVERIFIED";
  }
  return Object.freeze({safeUrl,siteSearch,sourceRoutes,classifyStatus,inSameSourceFamily});
});
