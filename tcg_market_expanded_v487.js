"use strict";
(() => {
  const home = document.getElementById("tcgMarketHome");
  if (!home) return;

  // Guard the V485 home source anchors without changing its immutable template.
  const VERIFIED_MARKET_SOURCE_HOSTS = Object.freeze([
    "kream.co.kr", "pokard.io", "tcgplayer.com", "snkrdunk.com",
    "ebay.com", "ebay.co.jp", "cardmarket.com", "mercari.com",
    "amazon.com", "amazon.co.jp", "collectory.cc", "justtcg.com",
    "tcgdex.net", "pavilion-tcg.com", "narutomarket.com"
  ]);
  function verifiedMarketSourceUrl(raw) {
    const value = String(raw || "").trim();
    if (!/^https:\/\//i.test(value) || value.length > 2048) return "";
    try {
      const url = new URL(value);
      if (url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443")) return "";
      const host = url.hostname.toLowerCase();
      return VERIFIED_MARKET_SOURCE_HOSTS.some(domain => host === domain || host.endsWith("." + domain)) ? url.href : "";
    } catch (_) { return ""; }
  }
  // V538: fail closed on calendar-impossible or future saved source dates.
  // The V485 template is intentionally immutable, so verify displayed dates
  // in the local same-origin enhancer without changing prices or requests.
  function verifiedMarketHomeDate(label, referenceDate = new Date()) {
    const m = /^자료일 (20\d{2}-\d{2}-\d{2})$/.exec(String(label || "").trim());
    if (!m) return false;
    const epoch = Date.parse(m[1] + "T00:00:00Z");
    if (!Number.isFinite(epoch) || new Date(epoch).toISOString().slice(0, 10) !== m[1]) return false;
    const today = Date.UTC(referenceDate.getFullYear(), referenceDate.getMonth(), referenceDate.getDate());
    return epoch <= today;
  }
  function marketHomeSourceAgeDays(label, referenceDate = new Date()) {
    if (!verifiedMarketHomeDate(label, referenceDate)) return null;
    const value = String(label).trim().slice("자료일 ".length);
    const today = Date.UTC(referenceDate.getFullYear(), referenceDate.getMonth(), referenceDate.getDate());
    return Math.floor((today - Date.parse(value + "T00:00:00Z")) / 86400000);
  }
  function protectMarketHomeDates() {
    for (const date of home.querySelectorAll(".tcg-market-tile-date")) {
      const label = String(date.textContent || "").trim();
      if (!label.startsWith("자료일 ")) continue;
      const days = marketHomeSourceAgeDays(label);
      if (days === null) {
        date.textContent = "자료일 검증 불가 · 가격 원문 재확인";
        date.dataset.dateStatus = "invalid";
      } else if (days > 14) {
        date.textContent = "과거 " + label + " · 최신 시세 아님";
        date.dataset.dateStatus = "stale";
      }
    }
  }
  function protectMarketHomeLinks() {
    for (const link of home.querySelectorAll(".tcg-market-tile-actions a")) {
      const safe = verifiedMarketSourceUrl(link.getAttribute("href"));
      if (safe) {
        if (link.href !== safe) link.href = safe;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      } else {
        const unavailable = document.createElement("span");
        unavailable.className = "tcg-market-art-empty";
        unavailable.textContent = "출처 URL 확인 필요";
        link.replaceWith(unavailable);
      }
    }
    protectMarketHomeDates();
  }
  home.addEventListener("click", event => {
    const link = event.target?.closest?.(".tcg-market-tile-actions a");
    if (!link || !home.contains(link)) return;
    if (!verifiedMarketSourceUrl(link.getAttribute("href"))) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  if (typeof MutationObserver === "function") {
    const observer = new MutationObserver(protectMarketHomeLinks);
    observer.observe(home, {childList: true, subtree: true});
  }
  protectMarketHomeLinks();
  const tabs = home.querySelector(".tcg-market-game-tabs");
  if (!tabs) return;
  const info = document.createElement("div");
  info.id = "tcgMarketExpandedV487";
  info.className = "tcg-market-expanded-v487";
  const label = document.createElement("p");
  label.textContent = "확장 카드게임 · 게임별 시세 검색 (등급측정 제외)";
  info.append(label);
  const links = document.createElement("div");
  links.className = "tcg-market-expanded-links";
  const status = document.createElement("p");
  status.setAttribute("aria-live", "polite");
  status.textContent = "확인된 확장 게임만 표시하며 가격·재고는 상세 검색에서 확인합니다.";
  info.append(links,status);
  tabs.insertAdjacentElement("afterend",info);
  const style=document.createElement("style");
  style.textContent=".tcg-market-expanded-v487{padding:10px 9px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;margin:6px 0 14px}.tcg-market-expanded-v487 p{margin:3px 0 7px;font-size:11px;color:#475569}.tcg-market-expanded-links{display:flex;gap:7px;overflow-x:auto;padding:4px 0}.tcg-market-expanded-links button{margin:0;width:auto;flex:none;min-height:44px;padding:8px 12px;border-radius:99px;background:#fff;color:#0f172a;border:1px solid #cbd5e1;font-size:12px}.tcg-market-expanded-links button:focus-visible{outline:3px solid #2563eb;outline-offset:2px}";
  // V516: screenshot readability and touch-safe controls. Cosmetic only:
  // do not alter saved evidence, game/edition, grading or purchase links.
  style.textContent += `
    .tcg-market-home .tcg-market-refresh,
    .tcg-market-home .tcg-market-game,
    .tcg-market-home .tcg-market-more,
    .tcg-market-home .tcg-market-tile-actions :is(button,a){
      min-height:48px;min-width:44px;touch-action:manipulation;
    }
    .tcg-market-home .tcg-market-refresh,
    .tcg-market-home .tcg-market-more,
    .tcg-market-home .tcg-market-tile-actions :is(button,a){
      font-size:12px;line-height:1.3;
    }
    .tcg-market-home .tcg-market-home-meta,
    .tcg-market-home .tcg-market-section-heading small,
    .tcg-market-home .tcg-market-tile-label,
    .tcg-market-home .tcg-market-tile-kind,
    .tcg-market-home .tcg-market-tile-date,
    .tcg-market-home .tcg-market-home-warning{
      font-size:12px;line-height:1.5;overflow-wrap:anywhere;
    }
    .tcg-market-home .tcg-market-tile-price{
      font-variant-numeric:tabular-nums;overflow-wrap:anywhere;word-break:break-word;
    }
    .tcg-market-home .tcg-market-tile-actions :is(button,a){
      padding:9px 5px;
    }
    @media(max-width:430px){
      .tcg-market-home .tcg-market-tile{flex-basis:clamp(160px,74vw,190px);}
      .tcg-market-home .tcg-market-section-heading{align-items:flex-start;}
    }
  `;
  document.head.append(style);
  fetch("tcg_game_registry.json",{cache:"no-store"}).then(r=>r.ok?r.json():null).then(data=>{
    if(!data || data.schema_version!==1 || !Array.isArray(data.games) || data.games.length>64)return;
    for(const game of data.games.filter(x=>x && x.state==="promoted" && x.capabilities?.market===true).slice(0,12)){
      if(typeof game.canonical!=="string" || typeof game.label_ko!=="string")continue;
      const btn=document.createElement("button");
      btn.type="button";
      btn.textContent=game.label_ko+" ›";
      btn.setAttribute("aria-label",game.label_ko+" 시세 검색");
      btn.addEventListener("click",async()=>{
        const sel=document.getElementById("v12Game");
        if(!sel || !Array.from(sel.options).some(x=>!x.disabled && x.value===game.canonical)){
          status.textContent="해당 확장 게임 선택이 아직 준비되지 않았습니다.";return;
        }
        sel.value=game.canonical;
        const query=document.getElementById("query12");
        if(query)query.value="";
        const link=document.querySelector('.feature-shortcut[data-feature-key="market-search"]');
        if(link)link.click();else status.textContent="시세 검색 메뉴를 찾지 못했습니다.";
      });
      links.append(btn);
    }
    if(!links.childElementCount)info.remove();
  }).catch(()=>info.remove());
})();

/* V505: low-cost, same-origin, offline-capable portfolio loaded after market home. */
(() => {
  if (!document.getElementById("tcgMarketHome") ||
      document.getElementById("tcgLocalCollectionV505Loader")) return;
  const script=document.createElement("script");
  script.id="tcgLocalCollectionV505Loader";
  script.src="tcg_local_collection_v505.js?v=505";
  script.async=false;
  document.body.appendChild(script);
})();
