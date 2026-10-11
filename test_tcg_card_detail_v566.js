#!/usr/bin/env node
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const price = require("./tcg_card_detail_v566.js");
const registry = JSON.parse(fs.readFileSync("tcg_game_registry.json", "utf8"));
const games = price.eligibleGames(registry);
assert.ok(games.some(g => g.canonical === "Pokémon" && g.state === "core"));
assert.ok(games.some(g => g.canonical === "GUNDAM CARD GAME" && g.state === "promoted"));
assert.ok(games.some(g => g.canonical === "Disney Lorcana" && g.state === "promoted"));
assert.ok(games.every(g => ["core","promoted"].includes(g.state)));
assert.ok(games.every(g => typeof g.canonical === "string" && g.canonical.length));
const synthetic = {entries:{
  "JP|Verified Gundam|HIT":{game:"GUNDAM CARD GAME",display:"¥800",kind:"RAW 공개 참고가",source_date:"2026-10-08",source:"https://www.tcgplayer.com"},
  "JP|Watch Placeholder|HIT":{game:"Unreviewed Watch Game",display:"₩9,999",source_date:"2026-10-08"},
  "JP|Invalid Price|HIT":{game:"GUNDAM CARD GAME",display:""},
  "JP|Not-A-Box|SECRET":{game:"GUNDAM CARD GAME",display:"₩9,999"},
  "JP|Verified Gundam|BOX":{game:"GUNDAM CARD GAME",display:"₩75,000",source_date:"2099-01-01"}
}};
const rows = price.parseRecords(synthetic,games);
assert.equal(rows.length,2,"explicit promoted game supported; WATCH, invalid, unverified excluded");
assert.ok(rows.every(r=>r.game.canonical==="GUNDAM CARD GAME"));
assert.equal(rows.find(r=>r.asset==="BOX").date,"","future publication date is not verified");
assert.equal(price.safeUrl("https://kream.co.kr.evil.example/"),"");
assert.equal(price.safeUrl("http://kream.co.kr/"),"");
assert.equal(price.safeUrl("https://user:pass@kream.co.kr/"),"");
assert.equal(price.safeUrl("https://www.snkrdunk.com/"),"https://www.snkrdunk.com/");
assert.equal(price.validDate("2026-02-30"),"");
assert.equal(price.validDate("2099-01-01"),"");
assert.equal(price.verifiedSales(rows[0]).length,0,"do not promote display prices to sales");
const good={verified:true,evidence_type:"completed_sale",currency:"KRW",price_krw:81000,date:"2026-07-26",grade:"PSA 10",
 source:"https://www.ebay.com/itm/123456789012",sale_id:"ebay:123456789012",
 review_status:"manual_verified",review_method:"source_page_crosscheck",reviewed_at:"2026-10-09",
 game:"pokemon",region:"JP",card_name:"Pikachu",card_number:"025/165",set_name:"151",
 printing:"Standard",language:"Japanese",condition:"Graded"};
const fake={...good,verified:false,price_krw:10000000};
const evil={...good,source:"https://www.ebay.com.evil.example/itm/123456789012"};
const wrongCurrency={...good,currency:"JPY"};
const wrongGrade={...good,grade:"BGS 10"};
const ref={...good,evidence_type:"asking_price"};
assert.equal(price.saleProof({...good,source:"https://www.ebay.com/"}),false,"homepages cannot prove sold events");
assert.equal(price.saleProof({...good,sale_id:"ebay:999999999999"}),false,"listing ID must match page");
assert.equal(price.saleProof({...good,review_status:"pending"}),false,"unreviewed candidates must stay out of sold prices");
assert.equal(price.saleProof({...good,reviewed_at:"2026-01-01"}),false,"review before sale invalid");
assert.equal(price.saleProof(good),true,"checked specific sale evidence accepted");
const second={...good,price_krw:94000,date:"2026-10-08",source:"https://www.ebay.com/itm/123456789013",sale_id:"ebay:123456789013"};
const sample={asset:"HIT",game:{id:"pokemon"},region:"JP",cardName:"Pikachu",cardNumber:"025/165",setName:"151",
 printing:"Standard",language:"Japanese",condition:"Graded",verified_sales:[fake,evil,wrongCurrency,wrongGrade,ref,good,second]};
const sales=price.verifiedSales(sample);
assert.equal(sales.length,2);
assert.equal(sales[0].saleId,"ebay:123456789012","audit identity remains attached to verified event");
const duplicatedRow={...sample,id:"duplicate-source-card-row",verified_sales:[good]};
assert.equal(price.distinctVerifiedSaleCount([sample,duplicatedRow]),2,
 "one completed eBay listing copied into two saved price records counts only once");
assert.equal(price.marketCoverage({rows:[sample,duplicatedRow],images:{},reviewCandidates:[]},"pokemon").verifiedCompletedSales,2,
 "per-game coverage must not double-count mirrored sale events");
assert.equal(price.distinctVerifiedSaleCount([{...sample,verified_sales:[{...good,source:"https://www.ebay.com.evil.example/itm/123456789012"}]}]),0,
 "unsafe domain must never inflate completed transactions");
assert.equal(price.distinctVerifiedSaleCount(null),0,"malformed market data fails closed");
assert.equal(price.verifiedSales({...sample,verified_sales:[good,{...good,price_krw:999999,date:"2026-10-08"}]}).length,1,
 "same eBay listing must count once even with revised price/date");
assert.equal(price.verifiedSales({...sample,verified_sales:[{...good,card_number:"999/165"}]}).length,0,
 "other card numbers must not share a verified sale");
assert.equal(price.verifiedSales({...sample,verified_sales:[{...good,set_name:"different set"}]}).length,0,
 "other sets must not share a verified sale");
assert.equal(price.verifiedSales({...sample,verified_sales:[{...good,game:"onepiece"}]}).length,0,
 "other games must not share a verified sale");
assert.equal(price.verifiedSales({...sample,verified_sales:[{...good,language:"English"}]}).length,0,
 "other language variants must not share a verified sale");
assert.equal(price.verifiedSales({...sample,verified_sales:[{...good,card_number:""}]}).length,0,
 "unidentified sold card cannot become a graded price");
assert.equal(price.verifiedSales({...sample,setName:"",verified_sales:[good]}).length,0,
 "market row without its set cannot accept completed sales");
for(const field of ["printing","language","condition"]){
 assert.equal(price.verifiedSales({...sample,[field]:"",verified_sales:[good]}).length,0,
   "blank market "+field+" is unknown, not verified matching variant");
 assert.equal(price.verifiedSales({...sample,verified_sales:[{...good,[field]:""}]}).length,0,
   "blank sale "+field+" must not inherit other side's identity");
}
assert.equal(price.verifiedSales({...sample,printing:"",language:"",condition:"",
  verified_sales:[{...good,printing:"",language:"",condition:""}]}).length,0,
 "both sides missing variant details must never yield fabricated grade averages");
assert.equal(price.rangeSales(sales,"PSA 10",0).length,2);
assert.equal(price.rangeSales(sales,"RAW",0).length,0);
assert.equal(price.rangeSales(sales,"PSA 10",3).length,2);
assert.equal(price.rangeSales(sales,"PSA 10",1).length,1);

assert.equal(price.calendarMonthCutoff(1,new Date("2026-03-31T12:30:00Z")),"2026-02-28","March-end month clamp");
assert.equal(price.calendarMonthCutoff(1,new Date("2024-03-31T12:30:00Z")),"2024-02-29","leap-year clamp");
assert.equal(price.calendarMonthCutoff(3,new Date("2026-10-11T08:00:00Z")),"2026-07-11");
assert.equal(price.calendarMonthCutoff(6,new Date("2026-10-11T08:00:00Z")),"2026-04-11");
assert.equal(price.calendarMonthCutoff(12,new Date("2026-10-11T08:00:00Z")),"2025-10-11");
assert.equal(price.calendarMonthCutoff(0,new Date("2026-10-11T08:00:00Z")),"");
const boundaryDates=["2026-07-10","2026-07-11","2026-07-12"].map(date=>({date,price:85000,grade:"PSA 10"}));
assert.deepEqual(price.rangeSales(boundaryDates,"PSA 10",3,new Date("2026-10-11T08:00:00Z")).map(x=>x.date),["2026-07-11","2026-07-12"],"calendar cutoff should include boundary but exclude prior day");


const verifiedRow={region:"JP",asset:"HIT",game:{id:"pokemon"},cardName:"Pikachu",cardNumber:"025/165",setName:"151"};
const verifiedIdentity={region:"JP",game:"pokemon",cardName:"Pikachu",cardNumber:"025/165",setName:"151"};
assert.equal(price.strictIdentityMatch(verifiedRow,verifiedIdentity),true);
assert.equal(price.strictIdentityMatch(verifiedRow,{...verifiedIdentity,setName:"different set"}),false);
assert.equal(price.strictIdentityMatch({...verifiedRow,cardNumber:""},verifiedIdentity),false);
assert.equal(price.strictIdentityMatch(verifiedRow,{...verifiedIdentity,region:"US"}),false);
assert.equal(price.strictIdentityMatch(verifiedRow,{...verifiedIdentity,cardNumber:"025"}),false);
assert.equal(price.strictIdentityMatch({...verifiedRow,game:{id:"gundam"}},verifiedIdentity),false);


const validPhotoRow={
  region:"JP",asset:"HIT",game:{id:"pokemon",canonical:"Pokémon"},
  cardName:"Pikachu",cardNumber:"025/165",setName:"151",printing:"Standard",condition:"Graded",language:"Japanese",
  date:"2026-10-08",display:"₩55,000",kind:"참고 공개가격",source:"https://www.snkrdunk.com/",
  verified_sales:[{verified:true,evidence_type:"completed_sale",grade:"PSA 9",currency:"KRW",
                   price_krw:85000,date:"2026-10-08",source:"https://www.ebay.com/itm/987654321098",
                   sale_id:"ebay:987654321098",review_status:"manual_verified",
                   review_method:"source_page_crosscheck",reviewed_at:"2026-10-09",
                    game:"pokemon",region:"JP",card_name:"Pikachu",card_number:"025/165",set_name:"151",
                    printing:"Standard",language:"Japanese",condition:"Graded"}]
};
const photoIdentity={game:"pokemon",region:"JP",cardName:"Pikachu",cardNumber:"025/165"};
const evidenceWithoutSet=price.photoEvidenceFromSnapshot({rows:[validPhotoRow]},photoIdentity);
assert.equal(evidenceWithoutSet.status,"single_candidate");
assert.equal(evidenceWithoutSet.reference.display,"₩55,000");
assert.equal(evidenceWithoutSet.sales.length,0,"bare card name/number must not become verified grade price");
assert.equal(evidenceWithoutSet.variantConfirmed,false);
const evidenceWithSet=price.photoEvidenceFromSnapshot({rows:[validPhotoRow]},{...photoIdentity,setName:"151"});
assert.equal(evidenceWithSet.variantConfirmed,false,"set match alone cannot verify omitted variant details");
assert.equal(evidenceWithSet.sales.length,0,"set-only photo lookup must not display graded transaction history");
const fullPhotoIdentity={...photoIdentity,setName:"151",printing:"Standard",language:"Japanese",condition:"Graded"};
const evidenceWithAllFacets=price.photoEvidenceFromSnapshot({rows:[validPhotoRow]},fullPhotoIdentity);
assert.equal(evidenceWithAllFacets.variantConfirmed,true);
assert.equal(evidenceWithAllFacets.sales.length,1);
assert.equal(evidenceWithAllFacets.sales[0].grade,"PSA 9");
assert.equal(price.photoEvidenceFromSnapshot({rows:[{...validPhotoRow,verified_sales:[{...validPhotoRow.verified_sales[0],card_number:"999/165"}]}]},
 fullPhotoIdentity).sales.length,0,"photo lookup must reject different card sale");
for (const [facet,claimed] of [["printing","Unlimited"],["condition","Near Mint"],["language","English"]]) {
  const output=price.photoEvidenceFromSnapshot({rows:[validPhotoRow]},
    {...fullPhotoIdentity,[facet]:claimed});
  assert.equal(output.status,"single_candidate","market reference can still be shown");
  assert.equal(output.variantConfirmed,false,
    "extra claimed "+facet+" must not establish missing source-side identity evidence");
  assert.equal(output.sales.length,0,
    "unverified "+facet+" must never promote completed-sale history");
}
assert.equal(price.photoEvidenceFromSnapshot({rows:[validPhotoRow]},{...photoIdentity,setName:"wrong"}).status,"not_found");
const printRow={...validPhotoRow,printing:"1st edition",verified_sales:validPhotoRow.verified_sales.map(s=>({...s,printing:"1st edition"}))};
assert.equal(price.photoEvidenceFromSnapshot({rows:[printRow]},{...photoIdentity,setName:"151"}).sales.length,0,
 "unspecified print variant must never promote graded sale");
assert.equal(price.photoEvidenceFromSnapshot({rows:[printRow]},{...fullPhotoIdentity,printing:"1st edition"}).sales.length,1);
const langRow={...validPhotoRow,language:"English",verified_sales:validPhotoRow.verified_sales.map(s=>({...s,language:"English"}))};
assert.equal(price.photoEvidenceFromSnapshot({rows:[langRow]},fullPhotoIdentity).variantConfirmed,false);
assert.equal(price.photoEvidenceFromSnapshot({rows:[langRow]},{...fullPhotoIdentity,language:"English"}).variantConfirmed,true);
assert.equal(price.photoEvidenceFromSnapshot({rows:[validPhotoRow,validPhotoRow]},{...photoIdentity,setName:"151"}).status,"ambiguous");
assert.equal(price.photoEvidenceFromSnapshot({rows:[validPhotoRow]},{...photoIdentity,region:"KR"}).status,"not_found");
const usRow={...validPhotoRow,region:"US",verified_sales:validPhotoRow.verified_sales.map(s=>({...s,region:"US"}))};
const regionMismatchRow={...validPhotoRow,region:"US"};
assert.equal(price.photoEvidenceFromSnapshot({rows:[regionMismatchRow]},{...photoIdentity,region:"US",setName:"151"}).sales.length,0,
 "a US market row with JP transaction must never show a verified sale");
assert.equal(price.photoEvidenceFromSnapshot({rows:[usRow]},{...fullPhotoIdentity,region:"US"}).sales.length,1,"US requires explicit market region selection");
assert.equal(price.photoEvidenceFromSnapshot({rows:[usRow]},{...photoIdentity,region:"EN",setName:"151"}).status,"identity_incomplete","EN language must never infer US market");
assert.equal(price.photoEvidenceFromSnapshot({rows:[validPhotoRow]},{...photoIdentity,cardNumber:""}).status,"identity_incomplete");
const noDatedRow={...validPhotoRow,date:"",source:""};
assert.equal(price.photoEvidenceFromSnapshot({rows:[noDatedRow]},{...photoIdentity,setName:"151"}).reference,null);

const saved=JSON.parse(fs.readFileSync("market_prices.json","utf8"));
const live=price.parseRecords(saved,games);
assert.ok(live.length>0,"existing real stored cards or boxes remain visible");
assert.ok(live.every(r=>r.game.state==="core"||r.game.state==="promoted"));
assert.ok(live.every(r=>price.verifiedSales(r).every(s=>s.source.startsWith("https://"))));
const source=fs.readFileSync("index.html","utf8");
assert.equal((source.match(/tcg_card_detail_v566\.js\?v=566/g)||[]).length,1);
assert.equal((source.match(/tcg_card_detail_v566\.css\?v=566/g)||[]).length,1);
const py=fs.readFileSync("tablet_runtime_manifest.py","utf8");
for(const file of ["tcg_card_detail_v566.js","tcg_card_detail_v566.css"]) assert.ok(py.includes('"'+file+'"'));
const savedSource=fs.readFileSync("tcg_card_detail_v566.js","utf8");
assert.ok(!savedSource.includes("card_number:row.cardNumber"),"sensitive OCR identity must not be persisted");
assert.ok(!savedSource.includes("purchase_krw:p"),"financial acquisition cost must not enter localStorage");
console.log("PASS V566: dynamic registry, promoted/WATCH, exact matching, strict sale filters, freshness, URL safety, mounted assets");


assert.equal(price.safeCatalogImageUrl("https://i.ebayimg.com/images/g/sample/s-l400.jpg"),"https://i.ebayimg.com/images/g/sample/s-l400.jpg");
assert.equal(price.safeCatalogImageUrl("https://thumbnail.coupangcdn.com/thumbnails/example.png"),"https://thumbnail.coupangcdn.com/thumbnails/example.png");
assert.equal(price.safeCatalogImageUrl("https://i.ebayimg.com.attacker.invalid/x.jpg"),"");
assert.equal(price.safeCatalogImageUrl("javascript:alert(1)"),"");
assert.equal(price.safeCatalogImageUrl("https://user:secret@i.ebayimg.com/a.jpg"),"");
assert.equal(price.safeCatalogImageUrl("https://localhost/image.png"),"");
(async () => {
  const market = JSON.parse(fs.readFileSync("market_prices.json","utf8"));
  const images = JSON.parse(fs.readFileSync("catalog_image_manifest.json","utf8"));
  const candidateFile = JSON.parse(fs.readFileSync("tcg_sale_review_candidates_v585.json","utf8"));
  const request = (failImage=false,failMarket=false,failRegistry=false) => async path => {
    if((failImage&&path==="catalog_image_manifest.json")||(failMarket&&path==="market_prices.json")||
        (failRegistry&&path==="tcg_game_registry.json"))return {ok:false,status:404};
    return {ok:true,json:async()=>path==="tcg_game_registry.json"?registry:path==="market_prices.json"?market:path==="tcg_sale_review_candidates_v585.json"?candidateFile:images};
  };
  const normal=await price.loadSnapshot(request(),undefined);
  assert.ok(normal.rows.length>0);
  assert.equal(normal.reviewCandidates.length,14,"all 12 registry-supported games have quarantined SOLD references");
  assert.deepEqual(normal.reviewCandidates.map(c=>c.game.id).sort(),["dbsfw","digimon","gundam","lorcana","mtg","naruto","onepiece","pokemon","riftbound","riftbound","riftbound","swu","unionarena","yugioh"]);
  assert.ok(normal.reviewCandidates.every(c=>c.source.includes("/itm/")));
  assert.ok(normal.reviewCandidates.every(c=>!c.verified),"SOLD listing pages never auto-promote to KRW verified sales");
  assert.ok(Object.keys(normal.images).length>0);
  const withoutImage=await price.loadSnapshot(request(true),undefined);
  assert.ok(withoutImage.rows.length>0,"valid registry and prices survive missing images");
  assert.deepEqual(Object.keys(withoutImage.images),[],"missing catalog must stay empty, never fake images");
  await assert.rejects(()=>price.loadSnapshot(request(false,true),undefined),/HTTP 404/);
  await assert.rejects(()=>price.loadSnapshot(request(false,false,true),undefined),/HTTP 404/);
  const storedGames=new Set(withoutImage.rows.map(row=>row.game.id));
  assert.ok(storedGames.size<=games.length,"only games with real evidence counted as priced");
  console.log("PASS V568: optional catalog, actual market evidence coverage, strict image trust and required price/registry fail-closed");
})().catch(e=>{console.error(e);process.exitCode=1;});


// V575: real promise behavior, not a source-string test. Cache public snapshots
// briefly to avoid 3 JSON downloads for each confirmed set/printing/condition.
(async () => {
  let clock=1000, loads=0, release;
  const cache=price.createPhotoSnapshotCache(()=>{
    loads++;
    return new Promise(resolve=>{release=resolve;});
  },30000,()=>clock);
  const p1=cache.get(), p2=cache.get();
  await Promise.resolve(); // lazy loader invoked only once
  assert.equal(loads,1,"concurrent photo identities must share public snapshot fetch");
  release({snapshot:"first"});
  const [first,second]=await Promise.all([p1,p2]);
  assert.strictEqual(first,second,"inflight callers share the same evidence snapshot");
  assert.strictEqual(await cache.get(),first);
  assert.equal(loads,1,"confirmed variant change within TTL must not refetch JSON");
  clock=30999;
  assert.strictEqual(await cache.get(),first,"fresh for the full TTL");
  clock=31000;
  const expired=cache.get();
  await Promise.resolve();
  assert.equal(loads,2,"expired snapshot is refreshed");
  release({snapshot:"after TTL"});
  assert.equal((await expired).snapshot,"after TTL");
  cache.clear();
  const afterClear=cache.get();
  await Promise.resolve();
  assert.equal(loads,3,"cleared snapshot refetches");
  release({snapshot:"clear"});
  await afterClear;

  let resolves=[];
  const racing=price.createPhotoSnapshotCache(
    ()=>new Promise(resolve=>resolves.push(resolve)),30000,()=>clock);
  const old=racing.get();
  await Promise.resolve();
  const newest=racing.get(true);
  await Promise.resolve();
  assert.equal(resolves.length,2);
  resolves[1]({version:"new"});
  assert.equal((await newest).version,"new");
  resolves[0]({version:"old"});
  assert.equal((await old).version,"old","older caller may finish but not overwrite cache");
  assert.equal((await racing.get()).version,"new","late stale result cannot clobber refreshed evidence");

  let attempts=0;
  const flaky=price.createPhotoSnapshotCache(async()=>{
    attempts++;
    if(attempts===1)throw Error("temporary-offline");
    return {ok:true};
  },30000,()=>clock);
  await assert.rejects(()=>flaky.get(),/temporary-offline/);
  assert.equal((await flaky.get()).ok,true,"failed load is not cached");
  assert.equal(attempts,2);

  assert.throws(()=>price.createPhotoSnapshotCache(null),/invalid/);
  assert.throws(()=>price.createPhotoSnapshotCache(()=>{},Infinity),/invalid/);
  console.log("PASS V575: concurrent photo evidence cache, expiry, forced refresh, stale-race and retry");
})().catch(error=>{console.error(error);process.exitCode=1;});

/* V581: missing card identification must stay visible in market list.
 * These labels are metadata, not proof of a completed sale or photograph. */
assert.deepEqual(price.storedCardListIdentity({asset:"HIT",name:"피카츄 행사",cardName:"피카츄",cardNumber:"025/165"}),
 {title:"피카츄",note:"저장된 카드번호 025/165 · 세트·판본은 상세에서 확인"});
assert.equal(price.storedCardListIdentity({asset:"HIT",name:"세트 묶음",cardName:"",cardNumber:""}).note,
 "카드명·번호 미확인 · 동일 카드 실거래 연결 보류");
assert.ok(price.storedCardListIdentity({asset:"HIT",name:"매물",cardName:"리자몽",cardNumber:""}).note.includes("카드번호 미확인"));
assert.equal(price.storedCardListIdentity({asset:"BOX",name:"테라스탈 페스타 ex"}).title,"테라스탈 페스타 ex");
const fileMarket=JSON.parse(fs.readFileSync("market_prices.json","utf8"));
const savedIdentities=price.parseRecords(fileMarket,games);
assert.ok(savedIdentities.some(r=>r.asset==="HIT"&&r.cardName&&r.cardNumber));
assert.ok(savedIdentities.filter(r=>r.asset==="HIT").every(r=>price.storedCardListIdentity(r).title.length>0));
console.log("PASS V581: stored card identity appears, missing number never becomes verified sale");

// V584: verify default compact catalog filtering instead of 12 expanded game buttons.
const catalogUI=fs.readFileSync("tcg_card_detail_v566.js","utf8");
const catalogCSS=fs.readFileSync("tcg_card_detail_v566.css","utf8");
assert.ok(catalogUI.includes('const gamePicker=el("details","game-picker")'));
assert.ok(catalogUI.includes('summary.setAttribute("aria-label","카드게임 선택 필터 열기")'));
assert.ok(catalogUI.includes("gamePicker.append(summary,tabs);wrap.append(gamePicker);"));
assert.ok(!catalogUI.includes("wrap.append(tabs);"),"all-game tabs may not appear without user selection");
assert.ok(catalogCSS.includes(".tcg-detail-game-picker-summary:focus-visible"));
console.log("PASS V584: catalog card-game filters collapsed, current selected name visible");
// V590: the home view's 9 promoted shortcut buttons must also be collapsed.
assert.ok(catalogUI.includes('const wrapper=el("details","expanded-games")'));
assert.ok(catalogUI.includes('summary.setAttribute("aria-label","확장 카드게임 선택 펼치기")'));
assert.ok(catalogUI.includes("wrapper.append(summary,expanded);"));
assert.ok(catalogUI.includes('original.insertAdjacentElement("afterend",wrapper);'));
assert.ok(!catalogUI.includes('original.insertAdjacentElement("afterend",expanded);'),"promoted game pills cannot remain exposed by default");
assert.ok(catalogCSS.includes(".tcg-detail-expanded-games-summary:focus-visible"));
assert.ok(catalogCSS.includes(".tcg-detail-expanded-games[open] .tcg-detail-expanded-tabs"));
console.log("PASS V590: selected-only promoted game home menu, touch sizing and accessible disclosure");

/* V586: support does not imply actual price/photo/identity/verified-sale coverage. */
const v586Rows=price.parseRecords(JSON.parse(fs.readFileSync("market_prices.json","utf8")),games);
const v586Candidates=price.reviewSaleCandidates(JSON.parse(fs.readFileSync("tcg_sale_review_candidates_v585.json","utf8")),games);
const v586Snapshot={rows:v586Rows,reviewCandidates:v586Candidates,images:JSON.parse(fs.readFileSync("catalog_image_manifest.json","utf8")).items};
assert.equal(v586Rows.length,38);
for(const [game,n] of [["pokemon",26],["onepiece",11],["naruto",1],["gundam",0]])
 assert.equal(price.marketCoverage(v586Snapshot,game).references,n);
for(const game of ["pokemon","onepiece","naruto"]){
 assert.equal(price.marketCoverage(v586Snapshot,game).reviewPending,1);
 assert.equal(price.marketCoverage(v586Snapshot,game).verifiedCompletedSales,0);
}
for(const [game,n] of [["unionarena",1],["riftbound",3],["gundam",1],["lorcana",1],["dbsfw",1],["swu",1],["mtg",1],["yugioh",1],["digimon",1]]){
 assert.equal(price.marketCoverage(v586Snapshot,game).references,0,"promoted SOLD review not a stored reference price");
 assert.equal(price.marketCoverage(v586Snapshot,game).reviewPending,n,"promoted SOLD candidates stay quarantined");
 assert.equal(price.marketCoverage(v586Snapshot,game).verifiedCompletedSales,0);
}
assert.equal(price.marketCoverage(v586Snapshot,"pokemon").identifiedCards<=26,true);
assert.equal(price.marketCoverage(v586Snapshot,"pokemon").picturedBoxes<=26,true);
assert.equal(price.marketCoverage({rows:[{game:{id:"pokemon"},asset:"HIT",cardName:"A",cardNumber:"1",date:"",source:""}]},"pokemon").sourcedDated,0);
assert.equal(v586Candidates.find(c=>c.game.id==="pokemon").listingClaimedNumber,"040");
assert.equal(v586Candidates.find(c=>c.game.id==="onepiece").listingCertId,"168312211");
assert.ok(fs.readFileSync("tcg_card_detail_v566.js","utf8").includes("a[href],summary"),"keyboard trap includes summary");
console.log("PASS V586 game-by-game market coverage and quarantined listing data");

/* V585: market candidate isolation and fail-closed provenance. */
const v585CandidateFile=JSON.parse(fs.readFileSync("tcg_sale_review_candidates_v585.json","utf8"));
assert.equal(price.reviewSaleCandidates(v585CandidateFile,games).length,14);
const v598Reviewed=price.reviewSaleCandidates(v585CandidateFile,games);
assert.equal(new Set(v598Reviewed.map(c=>c.game.id)).size,12,
 "all twelve core/promoted TCGs have at least one quarantined source, no trade claims");
assert.equal(new Set(v598Reviewed.map(c=>c.listingId)).size,14,"listing-id dedup preserved");
for(const id of ["swu","mtg","yugioh","digimon"]){
 const perGame=v598Reviewed.filter(r=>r.game.id===id);
 assert.equal(perGame.length,1,"one review candidate in each newly added game");
 assert.equal(perGame[0].cardNumber,"","seller listing claim cannot become verified card number");
 assert.equal(price.marketCoverage(v586Snapshot,id).verifiedCompletedSales,0);
}
for(const id of ["gundam","lorcana","dbsfw"]){
 const rows=price.reviewSaleCandidates(v585CandidateFile,games).filter(c=>c.game.id===id);
 assert.equal(rows.length,1,"newly reviewed games remain separate pending sources");
 assert.equal(rows[0].cardNumber,"","listing card number is not externally verified");
 assert.equal(price.marketCoverage(v586Snapshot,id).verifiedCompletedSales,0,"no simulated real trades");
}
assert.equal(v585CandidateFile.sale_review_candidates.find(c=>c.game==="dbsfw").listing_claimed_card_number,"FB09-037");
assert.ok(v585CandidateFile.sale_review_candidates.find(c=>c.game==="dbsfw").reason.includes("FB05-099"),"seller mismatch must survive stored review evidence");
const v595Yone=price.reviewSaleCandidates(v585CandidateFile,games).filter(r=>r.game.id==="riftbound");
assert.equal(v595Yone.length,3,"different Yone listings remain separate candidates");
assert.equal(new Set(v595Yone.map(r=>r.listingId)).size,3,"different listing IDs remain distinct");
assert.ok(v595Yone.every(r=>r.cardNumber===""),"card number unknown must remain unknown");
assert.equal(price.marketCoverage(v586Snapshot,"riftbound").verifiedCompletedSales,0,"SOLD page does not verify KRW settled price");
assert.equal(price.reviewSaleCandidates({sale_review_candidates:[
 {...v585CandidateFile.sale_review_candidates[0],source:"https://www.ebay.com.evil.invalid/itm/188631270673"},
 {...v585CandidateFile.sale_review_candidates[0],listing_id:"100000000000"},
 {...v585CandidateFile.sale_review_candidates[0],review_status:"manual_verified"},
 {...v585CandidateFile.sale_review_candidates[0],currency:"KRW"}]},games).length,0);
assert.equal(price.verifiedSales({verified_sales:v585CandidateFile.sale_review_candidates}).length,0,
 "pending and USD sale candidates must not contribute to average or graph");
const v585Ui=fs.readFileSync("tcg_card_detail_v566.js","utf8");
assert.ok(v585Ui.includes('el("details","review")'),"sold review queue should be collapsed");
assert.ok(v585Ui.includes("판매완료 원문 확인"),"source link must be auditable");
console.log("PASS V585: completed sale proof, USD candidate quarantine and collapsed review UI");

// V592: verified-price detail is initially compact and native summaries remain accessible.
assert.ok(catalogUI.includes('el("details","empty-grades")'));
assert.ok(catalogUI.includes('el("details","advanced")'));
assert.ok(catalogUI.includes("advancedSales.append(recent);wrap.append(advancedSales)"));
assert.ok(catalogUI.includes("advancedGrade.append(roi);wrap.append(advancedGrade)"));
assert.ok(catalogUI.includes('gradeSection.append(el("p","empty"'));
assert.ok(catalogCSS.includes(".tcg-detail-advanced-summary:focus-visible"));
console.log("PASS V592: compact no-sale grade cards and collapsed advanced price evidence");

// V593: only source-crosschecked card illustrations may appear; never
// treat artwork or source asking prices as training or completed sales.
const cardWithImage=live.find(r=>r.game.id==="naruto"&&r.cardNumber==="CP-001");
assert.ok(cardWithImage,"source-researched NARUTO CP-001 is in stored references");
assert.equal(price.safeUrl("https://narutomarket.com/en/market/chakra-card-cp-001-gen-con-2026"),
 "https://narutomarket.com/en/market/chakra-card-cp-001-gen-con-2026");
assert.equal(price.safeUrl("https://narutomarket.com.evil.invalid/en/market/foo"),"");
assert.equal(price.safeCatalogImageUrl("https://narutomarket.com/user/avatar.webp"),"");
assert.equal(price.safeCatalogImageUrl("https://narutomarket.com/uploads/card.webp?next=evil"),"");
assert.ok(price.sourceProvidedCardImage(cardWithImage).includes("__carta.webp"),"researched picture should render");
// V609: generic source image provenance requires set, printing, language and region.
const manualArt={
 ...cardWithImage,game:{id:"pokemon"},region:"JP",cardName:"Pikachu",
 cardNumber:"025/165",setName:"151",printing:"Standard",language:"Japanese",
 source:"https://narutomarket.com/en/market/chakra-card-cp-001-gen-con-2026",
 imageReview:"source_page_crosschecked",imageCardName:"Pikachu",
 imageCardNumber:"025/165",imageSetName:"151",imagePrinting:"Standard",
 imageLanguage:"Japanese",imageRegion:"JP"
};
assert.ok(price.sourceProvidedCardImage(manualArt),"fully identified illustration is permitted");
for(const damaged of [
 {imageSetName:""}, {imageSetName:"Base Set"}, {imagePrinting:""},
 {imagePrinting:"Parallel"}, {imageLanguage:""}, {imageLanguage:"English"},
 {imageRegion:""}, {imageRegion:"KR"}, {setName:"Other"},
 {printing:"Foil"}, {language:"English"}, {imageCardNumber:"025/999"},
 {imageReview:"review_pending"}
]){
 assert.equal(price.sourceProvidedCardImage({...manualArt,...damaged}),"",
   "unknown or contradictory illustration variant must not be borrowed");
}
const parsedExplicit=price.parseRecords({entries:{
 "JP|Pikachu image variant|HIT":{
   game:"Pokémon",display:"¥1,000",card_name:"Pikachu",card_number:"025/165",
   set_name:"151",printing:"Standard",language:"Japanese",
   source:manualArt.source,image_url:manualArt.imageUrl,
   image_review_status:"source_page_crosschecked",
   image_card_name:"Pikachu",image_card_number:"025/165",
   image_set_name:"151",image_printing:"Standard",
   image_language:"Japanese",image_region:"JP"
 }}},games)[0];
assert.equal(price.sourceProvidedCardImage(parsedExplicit),manualArt.imageUrl);
assert.equal(price.sourceProvidedCardImage({...parsedExplicit,imageLanguage:"Korean"}),"");
assert.equal(price.sourceProvidedCardImage({...cardWithImage,cardNumber:"CP-002"}),"");
assert.equal(price.sourceProvidedCardImage({...cardWithImage,cardName:"Unknown"}),"");
assert.equal(price.sourceProvidedCardImage({...cardWithImage,imageReview:"review_pending"}),"");
assert.equal(price.sourceProvidedCardImage({...cardWithImage,source:"https://www.ebay.com/itm/123456789012"}),"");
assert.equal(price.sourceProvidedCardImage({...cardWithImage,asset:"BOX"}),"");
assert.equal(price.sourceProvidedCardImage({...cardWithImage,imageUrl:"https://narutomarket.com.evil.invalid/uploads/card.webp"}),"");
assert.ok(price.cardEvidenceGaps(cardWithImage).some(x=>x.includes("실거래 0건")));
assert.ok(price.cardEvidenceGaps({...cardWithImage,cardNumber:""}).some(x=>x.includes("카드번호 미확인")));
assert.equal(price.marketCoverage(v586Snapshot,"naruto").picturedCards,1);
assert.equal(price.marketCoverage(v586Snapshot,"naruto").setNamedCards,0);
assert.equal(price.marketCoverage(v586Snapshot,"onepiece").picturedCards,0);
assert.ok(catalogUI.includes("사진·카드정보·시세 근거 확인"),"card evidence details must remain collapsed");
assert.ok(catalogUI.includes("sourceProvidedCardImage(row)"),"safe source-specific card image must be used");
assert.equal(price.verifiedSales(cardWithImage).length,0,"asking-price observation must not imply a completed trade");
console.log("PASS V593: safe card image source, exact matching, checklist and honest sale gates");
// V598: image previews have the same provenance barrier as detail art.
assert.equal(price.storedListArtwork(cardWithImage,{}),price.sourceProvidedCardImage(cardWithImage));
assert.equal(price.storedListArtwork({...cardWithImage,cardNumber:"OTHER"},{}),"");
assert.equal(price.storedListArtwork({...cardWithImage,imageReview:"review_pending"},{}),"");
assert.equal(price.storedListArtwork({asset:"BOX",name:"X",region:"KR"},{"X":{region:"JP",url:"https://image.homeplus.kr/a.jpg"}}),"");
assert.equal(price.storedListArtwork({asset:"BOX",name:"X",region:"KR"},{"X":{region:"KR",url:"https://untrusted.invalid/a.jpg"}}),"");
assert.equal(price.storedListArtwork({asset:"BOX",name:"X",region:"KR",game:{id:"pokemon",canonical:"Pokémon"}},{"X":{region:"KR",url:"https://image.homeplus.kr/a.jpg"}}),
  price.safeCatalogImageUrl("https://image.homeplus.kr/a.jpg"));
assert.ok(catalogUI.includes('r.setName,r.printing,r.language,r.condition].join(" ")'));
assert.ok(catalogUI.includes('img.loading="lazy";img.decoding="async"'));
assert.ok(catalogCSS.includes(".tcg-detail-result-image"));
assert.equal(price.verifiedSales(cardWithImage).length,0);
console.log("PASS V598: safe thumbnail source and searchable variant metadata");
// V613: two unrelated games sharing a generic product title must never
// show the other title's product artwork, even on a trusted image host.
const crossGamePokemon = {asset:"BOX",name:"Starter Deck",region:"KR",game:{id:"pokemon",canonical:"Pokémon"}};
const crossGameOnePiece = {asset:"BOX",name:"Starter Deck",region:"KR",game:{id:"onepiece",canonical:"ONE PIECE"}};
const sampleBoxImage = {region:"KR",url:"https://image.homeplus.kr/source-matched.jpg"};
const disputedBoxes = [crossGamePokemon,crossGameOnePiece];
assert.equal(price.verifiedBoxArtwork(crossGamePokemon,{"Starter Deck":sampleBoxImage},disputedBoxes),"");
assert.equal(price.storedListArtwork(crossGameOnePiece,{"Starter Deck":sampleBoxImage},disputedBoxes),"");
assert.equal(price.marketCoverage({rows:disputedBoxes,images:{"Starter Deck":sampleBoxImage}},"pokemon").picturedBoxes,0);
assert.equal(price.marketCoverage({rows:disputedBoxes,images:{"Starter Deck":sampleBoxImage}},"onepiece").picturedBoxes,0);
assert.equal(price.verifiedBoxArtwork(crossGamePokemon,{"Starter Deck":sampleBoxImage},[crossGamePokemon]),
             sampleBoxImage.url);
assert.equal(price.verifiedBoxArtwork(crossGamePokemon,{"Starter Deck":{...sampleBoxImage,game:"onepiece"}},[crossGamePokemon]),"",
             "audited image game identity mismatch must fail closed");
assert.equal(price.verifiedBoxArtwork(crossGamePokemon,{"Starter Deck":{...sampleBoxImage,game:"pokemon"}},[crossGamePokemon]),
             sampleBoxImage.url);
assert.equal(price.verifiedBoxArtwork(crossGamePokemon,{"Starter Deck":{...sampleBoxImage,game:"Pokémon"}},[crossGamePokemon]),
             sampleBoxImage.url,"canonical game labels are accepted when exact");
assert.equal(price.verifiedBoxArtwork(crossGamePokemon,{"Starter Deck":{...sampleBoxImage,region:"JP"}},[crossGamePokemon]),"");
assert.equal(price.verifiedBoxArtwork({...crossGamePokemon,game:undefined},{"Starter Deck":sampleBoxImage},[crossGamePokemon]),"");
assert.equal(price.verifiedBoxArtwork(crossGamePokemon,{"Starter Deck":{...sampleBoxImage,url:"https://image.homeplus.kr.evil.invalid/a.jpg"}},[crossGamePokemon]),"");
assert.ok(catalogUI.includes('storedListArtwork(row,data.images,data.rows)'),
          "thumbnail must use full snapshot to detect collisions");
assert.ok(catalogUI.includes('verifiedBoxArtwork(row,data.images,data.rows)'),
          "detail artwork must use the same provenance gate");
console.log("PASS V613: cross-game BOX collision and audited-image provenance gates");
