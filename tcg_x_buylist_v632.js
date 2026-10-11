/* V632: tablet UI for free 30-TCG x 3-market X manual buylist queries.
 * Mirrors the broad-discovery default from tcg_x_buylist_search_v631.py.
 * No X API requests, no scraping, no price claims. */
(function(root,make){
  "use strict";
  const api=make();
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  if(root&&root.document){
    root.TcgXManualV632=api;
    const launch=()=>api.mount(root.document);
    if(root.document.readyState==="loading")root.document.addEventListener("DOMContentLoaded",launch,{once:true});
    else launch();
  }
})(typeof globalThis!=="undefined"?globalThis:this,function(){
  "use strict";
  const SHORT={pokemon:"ポケカ",onepiece:"ワンピカード",yugioh:"遊戯王",
    "weiss-schwarz":"ヴァイス",unionarena:"ユニアリ",digimon:"デジカ"};
  const JP_SEARCH_NAMES={
    naruto:"NARUTO",gundam:"ガンダムカード",dbsfw:"ドラゴンボール",
    lorcana:"ロルカナ",swu:"スターウォーズ アンリミテッド",
    riftbound:"リフトバウンド",mtg:"MTG","flesh-and-blood":"Flesh and Blood",
    "cardfight-vanguard":"ヴァンガード","hololive-ocg":"ホロカ",
    "shadowverse-evolve":"シャドウバース エボルヴ","grand-archive":"Grand Archive",
    "final-fantasy-tcg":"FFTCG","sorcery-contested-realm":"Sorcery Contested Realm",
    "godzilla-card-game":"ゴジラ カード","palworld-ocg":"パルワールド カード",
    "cyberpunk-tcg":"Cyberpunk TCG",elestrals:"Elestrals",
    "rush-of-ikorr":"Rush of Ikorr","cookierun-braverse":"クッキーラン ブレイバーズ",
    universus:"UniVersus","alpha-clash":"Alpha Clash",metazoo:"MetaZoo",wixoss:"WIXOSS"
  };
  const MARKETS={
    JP:{buy:["買取","買取表"],ex:["販売","オリパ","トレード","プレゼント","交換希望"],
      box:["BOX","ボックス","未開封"],lang:"ja",currency:"JPY"},
    KR:{buy:["매입","매입가","삽니다"],ex:["판매","오리파","교환","나눔","이벤트"],
      box:["BOX","박스","미개봉"],lang:"ko",currency:"KRW"},
    US:{buy:["buylist","we buy","buying cards"],ex:["giveaway","raffle","trade only","for sale","mystery box"],
      box:["booster box","sealed box","sealed"],lang:"en",currency:"USD"}
  };
  const RARITIES={
    JP:{pokemon:["SAR","UR","プロモ"],onepiece:["コミパラ","スーパーパラレル","SEC","シリアル"],
      yugioh:["クオシク","プリシク","20thシク","レリーフ"],
      "weiss-schwarz":["SSP","SP","SEC","サイン"],unionarena:["AP","パラレル","SR"],digimon:["SEC","SP","パラレル"]},
    KR:{pokemon:["SAR","UR","프로모"],onepiece:["코믹패러렐","SEC","시리얼"],
      yugioh:["쿼터센츄리 시크릿","프리즈마틱 시크릿"],
      "weiss-schwarz":["SSP","SP","SEC"],unionarena:["AP","SR","패러렐"],digimon:["SEC","SP","패러렐"]},
    US:{pokemon:["SIR","Hyper Rare","Promo"],onepiece:["Manga Rare","SEC","Serial"],
      yugioh:["Quarter Century Secret Rare","Starlight Rare","Ultimate Rare"],
      "weiss-schwarz":["SSP","SP","SEC"],unionarena:["AP","SR","Parallel"],digimon:["SEC","Alt Art","SP"]}
  };
  const quote=s=>s.includes(" ")?'"'+s+'"':s;
  const or=xs=>xs.length===1?quote(xs[0]):"("+xs.map(quote).join(" OR ")+")";
  function searchName(game,region){
    if(region==="JP")return SHORT[game.id]||JP_SEARCH_NAMES[game.id]||game.canonical;
    return region==="KR"?game.label_ko:game.canonical;
  }
  function query(game,region,kind,rarity,images=true,excludeNoise=true){
    if(!game||!game.id||!MARKETS[region]||!["card","box"].includes(kind))throw Error("INVALID_SEARCH_SCOPE");
    const m=MARKETS[region];
    const parts=[quote(searchName(game,region))];
    if(kind==="box"){if(rarity)throw Error("BOX_HAS_NO_RARITY");parts.push(or(m.box));}
    else if(rarity){
      const hints=RARITIES[region][game.id]||[];
      if(rarity==="ALL_HINTS"){if(hints.length)parts.push(or(hints));}
      else if(hints.includes(rarity))parts.push(quote(rarity));
      else throw Error("UNKNOWN_RARITY");
    }
    parts.push(or(m.buy));
    if(excludeNoise)parts.push(...m.ex.map(x=>"-"+quote(x)));
    if(images)parts.push("filter:images");
    return parts.join(" ");
  }
  function url(queryText){return "https://x.com/search?q="+encodeURIComponent(queryText)+"&f=live";}
  function validRegistry(raw){
    if(!raw||raw.schema_version!==1||!Array.isArray(raw.games)||raw.games.length!==30)return false;
    const ids=new Set();
    return raw.games.every(g=>{
      if(!g||typeof g.id!=="string"||ids.has(g.id)||typeof g.canonical!=="string"||
         typeof g.label_ko!=="string"||!Array.isArray(g.regions))return false;
      ids.add(g.id);return true;
    });
  }
  function mount(doc){
    const ids=["xGame","xRegion","xKind","xRarity","xQuery","xOpen","xStatus","xCoverage"];
    const els=ids.map(id=>doc.getElementById(id));
    if(!els.every(Boolean))return;
    const [game,region,kind,rarity,code,open,status,coverage]=els;
    const broad=doc.getElementById("xBroad");
    open.removeAttribute("href");
    const options=(control,values)=>{
      control.replaceChildren();
      values.forEach(([value,label])=>{
        const o=doc.createElement("option");o.value=value;o.textContent=label;control.appendChild(o);
      });
    };
    fetch("./tcg_game_registry.json",{cache:"no-store"}).then(r=>{
      if(!r.ok)throw Error("LOCAL_REGISTRY_UNAVAILABLE");return r.json();
    }).then(data=>{
      if(!validRegistry(data))throw Error("INVALID_30_GAME_REGISTRY");
      options(game,data.games.map(g=>[g.id,g.label_ko+" / "+g.canonical]));
      coverage.textContent="등록 30종 × 검색 지역 3곳 = 총 90개 검색 범위 · 정식 발매 미확인 국가는 조사만 수행";
      function refresh(){
        const g=data.games.find(g=>g.id===game.value);
        if(!g)return;
        const reg=region.value,boxed=kind.value==="box";
        const optionsList=RARITIES[reg][g.id]||[];
        const old=rarity.value;
        options(rarity,[["","전체 카드(레어도 제한 없음)"],...(optionsList.length?[["ALL_HINTS","레어도 후보 전체"]]:[]),
          ...optionsList.map(v=>[v,v])]);
        if(!boxed&&[...rarity.options].some(o=>o.value===old))rarity.value=old;
        rarity.disabled=boxed;
        const r=boxed?"":rarity.value;
        const text=query(g,reg,kind.value,r,true,!broad?.checked);
        code.textContent=text;
        open.href=url(text);
        open.setAttribute("rel","noopener noreferrer");
        open.setAttribute("target","_blank");
        const declared=g.regions.includes(reg)||g.regions.includes("GLOBAL");
        status.textContent=(declared?"등록된 게임·지역 범위":"이 국가의 정식판 여부 미확인 · 조사 전용")+
          " · "+MARKETS[reg].currency+" · 매장 매입 제시가 검색(실거래 시세 아님)";
      }
      // Preserve the user's rarity when possible, even after switching game/region.
      function changed(){refresh();}
      [game,region,kind].forEach(c=>c.addEventListener("change",changed));
      rarity.addEventListener("change",()=>{
        const g=data.games.find(g=>g.id===game.value);
        const text=query(g,region.value,kind.value,rarity.value,true,!broad?.checked);
        code.textContent=text;open.href=url(text);
      });
      if(broad)broad.addEventListener("change",refresh);
      refresh();
    }).catch(()=>{
      status.textContent="30종 레지스트리 확인 실패 · 임의로 검색 범위를 복원하지 않습니다.";
      open.removeAttribute("href");code.textContent="자료 확인 실패";
    });
  }
  return Object.freeze({SHORT,MARKETS,RARITIES,query,url,validRegistry,searchName,mount});
});
