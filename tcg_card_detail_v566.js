/* V566: registry-driven, evidence-gated card price detail. Device-local UI only. */
(function (root) {
"use strict";
const HOSTS = ["pokard.io","kream.co.kr","snkrdunk.com","tcgplayer.com","ebay.com","ebay.co.jp","mercari.com","collectory.cc","cardmarket.com","justtcg.com","tcgdex.net","pavilion-tcg.com","psacard.com","pricecharting.com","wyyyes.com","tcgfish.net","130point.com"];
const REGIONS = {KR:"한국판",JP:"일본판",US:"북미판"};
const IMAGE_HOSTS = new Set(["image.homeplus.kr","thumbnail.coupangcdn.com","i.ebayimg.com","static.wixstatic.com","www.gate-to-the-games.de","pbs.twimg.com","cdn11.bigcommerce.com","tcgame.com.au","feenturm.de","kream-phinf.pstatic.net","flow.xosoft.kr","files.cardgameshop.be","cdn.aukro.cz","ec.treasure-f.com","item-shopping.c.yimg.jp","storage.googleapis.com","thecardvault.co.uk","cdn.shopify.com","packflipps.com","collectorstore.com","tradingcardworld.store","i5.walmartimages.com"]);
function safeCatalogImageUrl(value) {
  try {
    const u = new URL(String(value || ""));
    if (u.protocol !== "https:" || u.username || u.password || (u.port && u.port !== "443")) return "";
    return IMAGE_HOSTS.has(u.hostname.toLowerCase()) ? u.href : "";
  } catch (_) { return ""; }
}

const STORE_KEY = "tcg-card-detail-v566-collection";
function clean(s) { return String(s == null ? "" : s).normalize("NFKC").trim(); }
function normal(s) { return clean(s).toLocaleLowerCase("en"); }
function safeUrl(value) {
  try {
    const u = new URL(String(value || ""));
    if (u.protocol !== "https:" || u.username || u.password || (u.port && u.port !== "443")) return "";
    const host = u.hostname.toLowerCase();
    return HOSTS.some(h => host === h || host.endsWith("." + h)) ? u.href : "";
  } catch (_) { return ""; }
}
function validDate(value) {
  const s = String(value || "");
  if (!/^20\d{2}-\d{2}-\d{2}$/.test(s)) return "";
  const t = Date.parse(s + "T00:00:00Z");
  return Number.isFinite(t) && new Date(t).toISOString().slice(0,10) === s && t <= Date.now() ? s : "";
}
function eligibleGames(registry) {
  if (!registry || registry.schema_version !== 1 || !Array.isArray(registry.games)) return [];
  const seen = new Set();
  return registry.games.slice(0,64).filter(g => {
    if (!g || !["core","promoted"].includes(g.state) || g.capabilities?.market !== true) return false;
    const id = clean(g.canonical);
    if (!id || id.length > 100 || seen.has(id)) return false;
    seen.add(id); return true;
  }).map(g => ({id:clean(g.id), canonical:clean(g.canonical), label:clean(g.label_ko || g.canonical),
    state:g.state, grading:g.capabilities.grading === true,
    aliases:[g.canonical,g.label_ko].concat(Array.isArray(g.aliases)?g.aliases.slice(0,16):[]).map(normal)}));
}
function parseRecords(data, games) {
  if (!data || !data.entries || typeof data.entries !== "object" || Array.isArray(data.entries)) return [];
  const lookup = new Map();
  games.forEach(g => g.aliases.forEach(a => { if(a && !lookup.has(a)) lookup.set(a,g); }));
  const rows = [];
  for (const [key, item] of Object.entries(data.entries).slice(0,2000)) {
    const bits = key.split("|");
    if(bits.length !== 3 || !REGIONS[bits[0]] || !["HIT","BOX"].includes(bits[2]) || !item || typeof item !== "object") continue;
    const game = lookup.get(normal(item.game));
    if (!game || typeof item.display !== "string" || !clean(item.display)) continue;
    rows.push({id:key,region:bits[0],name:clean(bits[1]).slice(0,150),asset:bits[2],game,
      display:clean(item.display).slice(0,80),kind:clean(item.kind).slice(0,160),
      date:validDate(item.source_date),source:safeUrl(item.source),
      market:clean(item.market).slice(0,100),description:clean(item.transactions).slice(0,240),
      cardName:clean(item.card_name).slice(0,160),cardNumber:clean(item.card_number).slice(0,50),
      setName:clean(item.set_name).slice(0,150),printing:clean(item.printing).slice(0,80),
      language:clean(item.language).slice(0,40),condition:clean(item.condition).slice(0,60),
      verified_sales:item.verified_sales,psa_population:item.psa_population});
  }
  return rows.sort((a,b) => (b.date || "").localeCompare(a.date || "") || a.name.localeCompare(b.name,"ko"));
}
function verifiedSales(row) {
  if (!row || !Array.isArray(row.verified_sales)) return [];
  const seen = new Set();
  return row.verified_sales.slice(0,120).filter(s => s && s.verified === true &&
      s.evidence_type === "completed_sale" && s.currency === "KRW" &&
      Number.isSafeInteger(s.price_krw) && s.price_krw > 0 &&
      ["RAW","PSA 8","PSA 9","PSA 10"].includes(s.grade) &&
      validDate(s.date) && safeUrl(s.source)).filter(s => {
        const identity=[s.date,s.grade,s.price_krw,safeUrl(s.source)].join("|");
        if(seen.has(identity))return false;
        seen.add(identity);return true;
      }).map(s => ({
        date:s.date,price:s.price_krw,grade:s.grade,source:safeUrl(s.source)
      })).sort((a,b) => a.date.localeCompare(b.date));
}
function priceKrw(value) {
  return Number.isSafeInteger(value) && value > 0 ? "₩"+value.toLocaleString("ko-KR") : "자료 없음";
}
function calendarMonthCutoff(months, today=new Date()) {
  if(months===0)return "";
  if(!Number.isInteger(months)||months<1||months>36||!(today instanceof Date)||!Number.isFinite(today.getTime()))return "";
  const first=new Date(Date.UTC(today.getUTCFullYear(),today.getUTCMonth()-months,1));
  const monthLast=new Date(Date.UTC(first.getUTCFullYear(),first.getUTCMonth()+1,0)).getUTCDate();
  return new Date(Date.UTC(first.getUTCFullYear(),first.getUTCMonth(),Math.min(today.getUTCDate(),monthLast))).toISOString().slice(0,10);
}
function rangeSales(sales, grade, months, today=new Date()) {
  const cutoff=calendarMonthCutoff(months,today);
  return sales.filter(s => s.grade === grade && (!cutoff || s.date >= cutoff));
}
function strictIdentityMatch(row,identity) {
  if(!row||!identity||row.asset!=="HIT"||!["KR","JP","US"].includes(identity.region))return false;
  if(row.region!==identity.region || row.game?.id!==identity.game)return false;
  const exact=v=>clean(v).replace(/\s+/g," ").toLocaleLowerCase("en");
  if(!row.cardName||!row.cardNumber||!identity.cardName||!identity.cardNumber)return false;
  if(exact(row.cardName)!==exact(identity.cardName)||exact(row.cardNumber)!==exact(identity.cardNumber))return false;
  if(identity.setName&&(!row.setName||exact(identity.setName)!==exact(row.setName)))return false;
  return true;
}
function photoEvidenceFromSnapshot(snapshot, identity) {
  const empty = reason => ({status:reason, reference:null, sales:[],variantConfirmed:false});
  if(!identity || !identity.cardName || !identity.cardNumber ||
     !["KR","JP","US"].includes(identity.region) || !identity.game)return empty("identity_incomplete");
  const records=Array.isArray(snapshot?.rows)?snapshot.rows:[];
  const matches=records.filter(row=>strictIdentityMatch(row,identity));
  if(!matches.length)return empty("not_found");
  if(matches.length!==1)return empty("ambiguous");
  const row=matches[0], normalized=v=>normal(v).replace(/\s+/g," ");
  // Extra user-supplied print, language or condition details cannot prove a
  // marketplace row which never recorded those details. Keep its reference
  // listing visible, but withhold "same variant" graded completed-sale claims.
  const facets=["printing","condition","language"];
  const variantConfirmed=!!(identity.setName && row.setName &&
    normalized(identity.setName)===normalized(row.setName) &&
    facets.every(field=>{
      const observed=normalized(row[field]),claimed=normalized(identity[field]);
      return observed ? claimed===observed : !claimed;
    }));
  const reference=row.source && row.date ? {
    display:row.display,kind:row.kind || "자료 유형 미확인",
    date:row.date,source:row.source,asset:row.asset
  }:null;
  return {status:"single_candidate",reference,
    // A uniquely named card/number is not a proven set/print/condition identity.
    sales:variantConfirmed?verifiedSales(row):[],
    variantConfirmed, game:row.game?.canonical || "",region:row.region};
}
/* V575: bounded in-memory coalescing for unchanged public snapshot data.
 * No persistent storage, remote inference, or unverified sale-price promotion.
 * An explicit refresh invalidates previous generations without stale overwrite. */
function createPhotoSnapshotCache(loader, ttlMs=30000, clock=()=>Date.now()) {
  if(typeof loader!=="function"||!Number.isInteger(ttlMs)||ttlMs<0||ttlMs>60000)
    throw Error("invalid photo snapshot cache");
  let data=null,expires=0,pending=null,generation=0;
  function clear(){generation++;data=null;expires=0;pending=null;}
  function get(forceRefresh=false){
    const time=Number(clock());
    if(!forceRefresh && data!==null && Number.isFinite(time) && time<expires)
      return Promise.resolve(data);
    if(!forceRefresh && pending)return pending;
    const myGeneration=++generation;
    data=null;expires=0;
    const promise=Promise.resolve().then(loader).then(snapshot=>{
      if(myGeneration===generation){
        data=snapshot;
        expires=Number(clock())+ttlMs;
        pending=null;
      }
      return snapshot;
    },error=>{
      if(myGeneration===generation){data=null;expires=0;pending=null;}
      throw error;
    });
    pending=promise;
    return promise;
  }
  return Object.freeze({get,clear});
}
const API = Object.freeze({safeUrl,safeCatalogImageUrl,validDate,eligibleGames,parseRecords,verifiedSales,rangeSales,calendarMonthCutoff,strictIdentityMatch,loadSnapshot,photoEvidenceFromSnapshot,createPhotoSnapshotCache,storedCardListIdentity});
if (typeof module !== "undefined" && module.exports) module.exports = API;
if (!root || !root.document) return;
const document = root.document;
let view = null, body = null, chosen = "ALL", search = "", data = null, previousFocus = null, current = null, selectedRange = 0;
function el(tag, cls, value) {
  const n = document.createElement(tag);
  if (cls) n.className = "tcg-detail-" + cls;
  if (value !== undefined) n.textContent = String(value);
  return n;
}
function button(label, fn, cls) {
  const b = el("button",cls || "button",label); b.type="button";b.addEventListener("click",fn);return b;
}
function nodeBlock(title,desc) {
  const section=el("section","panel");section.append(el("h3","section-title",title));
  if(desc)section.append(el("p","hint",desc));return section;
}
function safeAnchor(label,href) {
  const url=safeUrl(href);
  if(!url)return el("span","muted","확인 가능한 출처 링크 없음");
  const a=el("a","anchor",label);a.href=url;a.target="_blank";a.rel="noopener noreferrer";return a;
}
function ensureView() {
  if (view) return;
  view=el("div","scrim");view.hidden=true;
  view.setAttribute("role","dialog");view.setAttribute("aria-modal","true");view.setAttribute("aria-label","카드 시세 상세");
  const shell=el("div","shell");
  const head=el("header","head");
  head.append(button("‹ 뒤로", () => { if(current){current=null;renderCatalog();}else close(); },"back"));
  head.append(el("strong","heading","카드 시세 상세"));
  head.append(button("닫기",close,"close"));
  body=el("main","body");body.id="tcgCardDetailBody";body.tabIndex=-1;
  shell.append(head,body);view.append(shell);document.body.append(view);
  view.addEventListener("click",e=>{if(e.target===view)close();});
}
function show() {
  ensureView();
  previousFocus=document.activeElement;
  view.hidden=false;document.body.classList.add("tcg-detail-open");
  body.focus();
}
function close(restoreFocus=true) {
  if(!view)return;
  view.hidden=true;document.body.classList.remove("tcg-detail-open");
  if(restoreFocus && previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
}
document.addEventListener("keydown",e=>{
  if(!view || view.hidden)return;
  if(e.key==="Escape"){e.preventDefault();close();return;}
  if(e.key!=="Tab")return;
  const controls=Array.from(view.querySelectorAll("button:not([disabled]),input:not([disabled]),a[href]"))
    .filter(n=>n.getClientRects().length>0);
  if(!controls.length){e.preventDefault();body.focus();return;}
  const first=controls[0],last=controls[controls.length-1],active=document.activeElement;
  if(e.shiftKey&&(active===first||active===body||!view.contains(active))){e.preventDefault();last.focus();}
  else if(!e.shiftKey&&(active===last||active===body||!view.contains(active))){e.preventDefault();first.focus();}
});
async function loadSnapshot(fetcher, signal) {
  async function read(path) {
    const response = await fetcher(path, {cache:"no-store",signal});
    if(!response.ok) throw Error("HTTP " + response.status + ": " + path);
    return response.json();
  }
  // Registry and market evidence are essential; product images are optional.
  const [registry, market] = await Promise.all([read("tcg_game_registry.json"),read("market_prices.json")]);
  const games=eligibleGames(registry);
  if(!games.length || !market || !market.entries || typeof market.entries!=="object" || Array.isArray(market.entries)) {
    throw Error("invalid registry / market schema");
  }
  const catalog=await read("catalog_image_manifest.json").catch(()=>null);
  const images=catalog && catalog.items && typeof catalog.items==="object" && !Array.isArray(catalog.items)?catalog.items:{};
  return {games,rows:parseRecords(market,games),images,updated:clean(market.updated_at).slice(0,25)};
}
async function load() {
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),10000);
  try { data=await loadSnapshot((path,options)=>fetch(path,options),controller.signal); }
  finally {clearTimeout(timer);}
}
function renderLoading(text) {body.replaceChildren(el("p","notice",text));}
function mkPill(label,active,fn) {
  const b=button(label,fn,"pill");b.setAttribute("aria-pressed",String(active));return b;
}
function renderCatalog() {
  current=null;
  if(!data){renderLoading("가격 자료를 불러오지 못했습니다. 새로고침 후 다시 시도해 주세요.");return;}
  const wrap=el("div","catalog");
  wrap.append(el("h2","title","카드 시세 찾기"),el("p","hint","등록·검증된 게임의 저장 자료만 표시합니다. WATCH 게임과 미검증 가격은 자동 포함하지 않습니다."));
  const observedGames=new Set(data.rows.map(r=>r.game.id)).size;
  const knownSales=data.rows.reduce((n,r)=>n+verifiedSales(r).length,0);
  wrap.append(el("p","hint","등록 게임 "+data.games.length+"종 중 실제 가격자료가 있는 게임 "+observedGames+"종 · 저장 참고자료 "+data.rows.length+"건 · 검증 완료 실거래 "+knownSales+"건"));
  if(!knownSales)wrap.append(el("p","notice","등급별 PSA·RAW 실거래가 확인되지 않아 가격 그래프·평균은 표시하지 않습니다. 수집 지원과 실거래 확보는 다른 단계입니다."));
  const inp=el("input","search");inp.type="search";inp.placeholder="카드명·BOX 이름 검색";inp.value=search;inp.setAttribute("aria-label","카드 시세 검색");
  inp.addEventListener("input",()=>{search=inp.value.slice(0,100);renderResults(results);});wrap.append(inp);
  const tabs=el("div","tabs");
  tabs.append(mkPill("전체",chosen==="ALL",()=>{chosen="ALL";renderCatalog();}));
  data.games.forEach(g=>tabs.append(mkPill(g.label+(g.state==="promoted"?" · 확장":""),chosen===g.canonical,()=>{chosen=g.canonical;renderCatalog();})));
  wrap.append(tabs);
  const results=el("div","results");wrap.append(results);
  wrap.append(el("p","hint","출처별 공개 표시가격과 실제 체결가는 다릅니다. 등급·판본·카드번호가 없는 자료는 동일 카드로 합산하지 않습니다."));
  body.replaceChildren(wrap);renderResults(results);
}
// V581: show stored card names/numbers without claiming unverified identity.
function storedCardListIdentity(row){
 if(!row||row.asset!=="HIT")return {title:clean(row?.name||""),note:""};
 const title=clean(row.cardName)||clean(row.name);
 const number=clean(row.cardNumber);
 const name=clean(row.cardName);
 const note=name&&number
  ?"저장된 카드번호 "+number+" · 세트·판본은 상세에서 확인"
  :!name&&!number
   ?"카드명·번호 미확인 · 동일 카드 실거래 연결 보류"
   :!name?"카드명 미확인 · 저장된 번호 "+number
          :"카드번호 미확인 · 동일 카드 실거래 연결 보류";
 return {title,note};
}
function renderResults(results) {
  const q=normal(search);
  const rows=data.rows.filter(r=>(chosen==="ALL"||r.game.canonical===chosen) &&
    (!q||normal(r.name+" "+r.cardName+" "+r.cardNumber).includes(q)));
  results.replaceChildren(el("p","hint","저장 자료 "+rows.length+"건 · 최근 파일 갱신 "+(data.updated||"미확인")));
  if (!rows.length) {
    results.append(el("p","empty","현재 조건에 맞는 검증된 저장 시세가 없습니다. 등록된 게임이어도 가격 수집 범위가 비어 있을 수 있습니다."));
    return;
  }
  const grid=el("div","grid");
  rows.slice(0,100).forEach(row=>{
    const card=button("",()=>{}, "result");card.replaceChildren();
    card.append(el("span","eyebrow",row.game.label+" · "+REGIONS[row.region]+" · "+(row.asset==="BOX"?"BOX":"카드")));
    const identity=storedCardListIdentity(row);
    card.append(el("strong","result-title",identity.title));
    if(identity.note)card.append(el("small","muted",identity.note));
    card.append(el("strong","result-price",row.display));
    card.append(el("small","muted",(row.kind||"가격 유형 미확인")+" · "+(row.date||"관측일 미확인")));
    card.addEventListener("click",()=>renderDetail(row));grid.append(card);
  });results.append(grid);
  if(rows.length>100)results.append(el("p","hint","상위 100건만 표시합니다. 검색어로 좁혀 주세요."));
}
function lineChart(points) {
  const unique=new Map();points.forEach(p=>unique.set(p.date,p.price));
  const entries=Array.from(unique).sort((a,b)=>a[0].localeCompare(b[0]));
  if(entries.length<2)return el("p","empty","동일 카드·동일 등급의 날짜가 다른 검증 거래 2건 이상 필요합니다.");
  const min=Math.min(...entries.map(p=>p[1])),max=Math.max(...entries.map(p=>p[1]));
  const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
  svg.setAttribute("viewBox","0 0 680 220");svg.setAttribute("role","img");
  svg.setAttribute("aria-label","실거래 "+entries.length+"개 날짜의 가격 추이");
  const line=document.createElementNS("http://www.w3.org/2000/svg","polyline");
  line.setAttribute("fill","none");line.setAttribute("stroke","#ef334c");line.setAttribute("stroke-width","4");
  const denom=Math.max(1,max-min);
  line.setAttribute("points",entries.map((p,i)=>(24+i*632/(entries.length-1)).toFixed(1)+","+(188-(p[1]-min)*145/denom).toFixed(1)).join(" "));
  svg.append(line);return svg;
}
function renderDetail(row) {
  current=row;selectedRange=0;
  const sales=verifiedSales(row);
  const wrap=el("div","detail");
  wrap.append(el("p","eyebrow",row.game.label+" · "+REGIONS[row.region]+" · "+row.game.state.toUpperCase()));
  const hero=el("section","hero");
  const art=el("div","art");
  const image=data.images[row.name];
  if(row.asset==="BOX"&&image&&image.region===row.region&&safeCatalogImageUrl(image.url)){
    const img=el("img","art-image");img.src=safeCatalogImageUrl(image.url);img.alt=row.name+" 제품 이미지";img.loading="lazy";
    img.addEventListener("error",()=>{img.remove();art.append(el("span","muted","확인된 이미지 없음"));},{once:true});art.append(img);
  }else art.append(el("span","muted","확인된 카드 이미지 없음"));
  const info=el("div","info");
  info.append(el("h2","title",row.cardName||row.name),el("p","hint",row.name));
  info.append(el("p","hint",[row.cardNumber&&"번호 "+row.cardNumber,row.setName,row.printing,row.language,row.condition].filter(Boolean).join(" · ") || "정확한 카드번호·판본·상태 미확인"));
  info.append(el("strong","hero-price",row.display));
  info.append(el("p","hint","저장된 "+(row.kind||"공개 참고가")+" · 자료일 "+(row.date||"확인 필요")));
  info.append(el("p","warning","실시간 가격·PSA 평균 거래가로 해석하지 마세요. 가격 유형과 실제 체결 여부를 분리했습니다."));
  hero.append(art,info);wrap.append(hero);
  const gradeSection=nodeBlock(row.asset==="BOX"?"가격 자료":"등급별 가격","최근 실거래·평균은 검증된 체결 기록만 계산합니다.");
  const cards=el("div","grades");const labels=row.asset==="BOX"?["BOX"]:["RAW","PSA 8","PSA 9","PSA 10"];
  labels.forEach(g=>{
    const stat=el("div","grade");
    stat.append(el("strong","grade-title",g));
    const filtered=sales.filter(s=>s.grade===g);
    stat.append(el("strong","grade-price",filtered.length?priceKrw(filtered[filtered.length-1].price):"—"));
    stat.append(el("p","hint","최근 검증 체결 "+(filtered.length?filtered[filtered.length-1].date:"자료 없음")));
    stat.append(el("p","hint","평균 "+(filtered.length?priceKrw(Math.round(filtered.reduce((s,v)=>s+v.price,0)/filtered.length)):"—")+" · "+filtered.length+"건"));
    cards.append(stat);
  });gradeSection.append(cards);wrap.append(gradeSection);
  const sources=nodeBlock("판매처 시세 비교","동일 판본의 확인된 출처만 표시하며 다른 상품 가격을 자동 결합하지 않습니다.");
  const comparison=el("div","comparison");
  comparison.append(el("div","compare-source",(row.market||"출처 미확인")+" · "+row.display));
  comparison.append(safeAnchor("가격 자료 출처 열기 ↗",row.source));
  comparison.append(el("p","hint","KREAM·SNKRDUNK 등 다른 판매처의 동일 SKU가 확인되지 않았다면 가격을 추정하지 않습니다."));
  sources.append(comparison);wrap.append(sources);
  if(row.asset==="HIT"){
    const trend=nodeBlock("실거래 가격 추이","같은 등급의 검증 거래가 2건 이상일 때만 그래프를 그립니다.");
    const select=el("div","tabs"),chart=el("div","chart");
    const kind=normal(row.kind);
    const grade=kind.includes("psa10")||kind.includes("psa 10")?"PSA 10":kind.includes("psa9")||kind.includes("psa 9")?"PSA 9":kind.includes("psa8")||kind.includes("psa 8")?"PSA 8":"RAW";
    const update=()=>{
      select.replaceChildren();
      [[3,"3개월"],[6,"6개월"],[12,"1년"],[0,"전체"]].forEach(([months,label])=>select.append(mkPill(label,months===selectedRange,()=>{selectedRange=months;update();})));
      chart.replaceChildren(lineChart(rangeSales(sales,grade,selectedRange)));
    };
    update();trend.append(select,chart,el("p","hint","표시 등급: "+grade+" · 공개 참고가격은 그래프 계산에서 제외"));wrap.append(trend);
    const recent=nodeBlock("최근 검증 거래 내역");
    const matching=sales.slice().reverse().slice(0,20);
    if(!matching.length)recent.append(el("p","empty","완료된 실거래로 검증된 기록이 없습니다."));
    matching.forEach(s=>{
      const line=el("div","trade");line.append(el("span","",s.date+" · "+s.grade),el("strong","",priceKrw(s.price)),safeAnchor("근거 ↗",s.source));recent.append(line);
    });wrap.append(recent);
    const pop=nodeBlock("PSA 인구 리포트");
    const population=row.psa_population;
    if(population&&population.verified===true&&Number.isSafeInteger(population.total)&&population.total>=0&&safeUrl(population.source)){
      pop.append(el("p","hint","확인된 PSA POP "+population.total+"장"),safeAnchor("PSA 인구 근거 ↗",population.source));
    }else pop.append(el("p","empty","해당 카드·판본의 공식 PSA POP 자료가 확인되지 않았습니다."));
    wrap.append(pop);
    const roi=nodeBlock("등급별 투자 수익률");
    roi.append(el("p","empty","RAW·등급별 실거래와 실질 매입가·감정/배송 수수료가 확보되기 전에는 수익률을 표시하지 않습니다."));
    wrap.append(roi);
  }
  const portfolio=nodeBlock("내 컬렉션에 등록","기존 보유자산 화면(V505)의 등록 양식 하나만 사용합니다. 매입가·수량·카드정보는 확인 후 직접 등록하며, 이 화면에서는 자동 저장하지 않습니다.");
  const feedback=el("p","hint","카드번호가 확인되지 않았다면 기존 보유자산 양식에서 직접 입력합니다.");
  feedback.setAttribute("role","status");
  portfolio.append(button("내 컬렉션 등록 양식 열기",()=>{
    const api=root.TCGLocalCollectionV505;
    if(!api||typeof api.prepareMarketEntry!=="function"){
      feedback.textContent="기존 컬렉션을 열 수 없습니다. 화면을 새로고침하고 내 컬렉션에서 직접 등록하세요.";
      return;
    }
    const ok=api.prepareMarketEntry({game:row.game.canonical,region:row.region,asset:row.asset,
      name:row.cardName||row.name,cardNumber:row.cardNumber,quantity:1});
    if(ok)close(false); // allow the canonical collection form to receive focus
    else feedback.textContent="기존 컬렉션이 손상됐거나 상품 분류가 미확인입니다. 기존 데이터를 덮어쓰지 않고 등록을 보류했습니다.";
  },"save"),feedback);
  // Historic V566 quantity records remain untouched. Never silently migrate or delete
  // records that lack the necessary card number, set and acquisition-cost identity.
  try{
    const legacy=root.localStorage?.getItem(STORE_KEY);
    if(legacy){
      const previous=JSON.parse(legacy);
      if(!Array.isArray(previous)||previous.length>1000||legacy.length>160000)throw Error("legacy-size");
      portfolio.append(el("p","warning","이전 버전의 임시 수량 기록 "+previous.length+"건이 별도 보관돼 있습니다. 자동 합산하지 않습니다. 파일로 백업하고 실제 보유내역을 확인해 기존 컬렉션에 직접 옮기세요."));
      portfolio.append(button("이전 임시 기록 백업(JSON)",()=>{
        try{
          const data=root.localStorage.getItem(STORE_KEY);
          if(!data||data.length>160000||!Array.isArray(JSON.parse(data)))throw Error("invalid");
          const blob=new Blob([data],{type:"application/json"});
          const url=root.URL.createObjectURL(blob);
          const a=el("a");a.href=url;a.download="tcg-v566-legacy-quantity-backup.json";
          document.body.append(a);a.click();a.remove();
          setTimeout(()=>root.URL.revokeObjectURL(url),1000);
          feedback.textContent="기록의 JSON 다운로드를 요청했습니다. 실제 파일 저장을 확인해 주세요. 원본 로컬 기록은 그대로 유지합니다.";
        }catch(_){feedback.textContent="구버전 임시 기록에 접근하지 못했습니다. 원본은 변경하지 않았습니다.";}
      },"button"));
    }
  }catch(_){
    portfolio.append(el("p","warning","구버전 임시 기록을 해석할 수 없습니다. 원본 데이터를 보존했으며 자동 병합을 차단했습니다."));
  }
  wrap.append(portfolio);
  wrap.append(el("p","footer","이 화면은 저장 자료 조회용입니다. 시세·투자수익·감정등급을 보장하지 않습니다."));
  body.replaceChildren(wrap);body.scrollTop=0;
}
async function open(match) {
  if(view&&!view.hidden)return;
  show();renderLoading("검증된 카드·시장 자료를 읽고 있습니다…");
  try {
    await load();
    chosen=match?.gameId ? data.games.find(g=>g.id===match.gameId)?.canonical || "ALL" : "ALL";
    search="";
    if(match && !match.gameId){
      const found=data.rows.find(r=>r.name===match.name&&r.region===match.region&&r.asset===match.asset);
      if(found){chosen=found.game.canonical;renderDetail(found);return;}
    }
    renderCatalog();
  }catch(_){renderLoading("게임 등록부 또는 시세자료를 읽지 못했습니다. 인터넷/로컬 저장파일을 확인한 뒤 다시 열어주세요.");}
}
async function attachExpandedTabs(home){
  const original=home?.querySelector(".tcg-market-game-tabs");
  if(!original||home.querySelector(".tcg-detail-expanded-tabs")||home.querySelector("#tcgMarketExpandedV487"))return;
  try{
    const response=await fetch("tcg_game_registry.json",{cache:"no-store"});
    if(!response.ok)throw Error("registry unavailable");
    const games=eligibleGames(await response.json()).filter(g=>g.state==="promoted");
    if(!games.length||home.querySelector("#tcgMarketExpandedV487")||home.querySelector(".tcg-detail-expanded-tabs"))return;
    const expanded=el("div","expanded-tabs");
    expanded.setAttribute("role","group");
    expanded.setAttribute("aria-label","확장 TCG 시세 선택");
    expanded.append(el("span","muted","확장 TCG · 검증된 자료만 표시"));
    games.forEach(g=>expanded.append(button(g.label,()=>void open({gameId:g.id}),"extension-tab")));
    original.insertAdjacentElement("afterend",expanded);
  }catch(_){/* Existing all-TCG detail menu remains usable on offline/error states. */}
}
function attach() {
  const home=document.getElementById("tcgMarketHome");
  const heading=home?.querySelector(".tcg-market-home-head");
  if(!heading||heading.querySelector(".tcg-detail-launch"))return;
  const launch=button("전체 카드 상세 보기 ›",()=>void open(),"launch");heading.append(launch);
  void attachExpandedTabs(home);
}
document.addEventListener("click",e=>{
  const btn=e.target?.closest?.("#tcgMarketHome .tcg-market-tile-actions button");
  if(!btn||clean(btn.textContent)!=="시세 상세")return;
  const tile=btn.closest(".tcg-market-tile"),section=btn.closest(".tcg-market-home-section");
  const title=tile?.querySelector(".tcg-market-tile-name")?.textContent;
  const label=tile?.querySelector(".tcg-market-tile-label")?.textContent || "";
  const region=Object.keys(REGIONS).find(k=>label.startsWith(REGIONS[k]));
  const asset=section?.querySelector("h4")?.textContent?.includes("BOX")?"BOX":"HIT";
  if(!title||!region)return;
  e.preventDefault();e.stopImmediatePropagation();
  void open({name:title,region,asset});
},true);
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",attach,{once:true});
else attach();
async function openFromPhoto(identity){
  if(!identity||!identity.cardName||!identity.cardNumber||!["KR","JP","US"].includes(identity.region))return false;
  if(view&&!view.hidden)return false;
  show();renderLoading("검증된 동일 카드·판본 시세를 대조하고 있습니다…");
  try{
    await load();
    const matching=data.rows.filter(row=>strictIdentityMatch(row,identity));
    if(matching.length===1 && photoEvidenceFromSnapshot(data,identity).variantConfirmed){
      chosen=matching[0].game.canonical;
      renderDetail(matching[0]);return true;
    }
    chosen=data.games.find(g=>g.id===identity.game)?.canonical || "ALL";
    search=clean(identity.cardName).slice(0,70);
    renderCatalog();
    if(matching.length>1)body.prepend(el("p","notice","카드명과 번호는 일치하지만 서로 다른 세트 또는 판본 후보가 있습니다. 자동으로 하나를 선택하지 않았습니다."));
    else if(matching.length===1)body.prepend(el("p","notice","같은 이름·번호의 후보는 있지만 세트·인쇄판·언어·상태가 모두 검증되지 않았습니다. 실거래로 확정하지 말고 직접 확인하세요."));
    else body.prepend(el("p","notice","게임·지역·카드번호까지 일치하는 검증된 시세가 없습니다. 검색 목록을 수동으로 검토하세요."));
    return false;
  }catch(_){renderLoading("시세를 읽지 못했습니다. 새로고침하여 다시 시도해 주세요.");return false;}
}
const photoSnapshotCache=createPhotoSnapshotCache(async()=>{
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),10000);
  try {
    return await loadSnapshot((path,options)=>fetch(path,options),controller.signal);
  } finally {clearTimeout(timer);}
});
async function getPhotoMarketEvidence(identity,{forceRefresh=false}={}) {
  const snapshot=await photoSnapshotCache.get(forceRefresh===true);
  return photoEvidenceFromSnapshot(snapshot,identity);
}
root.TCGCardDetail=Object.freeze({openCatalog:(selection)=>open(selection),openFromPhoto,getPhotoMarketEvidence,safeSourceUrl:safeUrl,version:"v571",close});
})(typeof window!=="undefined"?window:null);
