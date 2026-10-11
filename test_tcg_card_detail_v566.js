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
 review_status:"manual_verified",review_method:"source_page_crosscheck",reviewed_at:"2026-10-09"};
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
const sample={verified_sales:[fake,evil,wrongCurrency,wrongGrade,ref,good,{...good,price_krw:94000,date:"2026-10-08"}]};
const sales=price.verifiedSales(sample);
assert.equal(sales.length,2);
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
  cardName:"Pikachu",cardNumber:"025/165",setName:"151",printing:"",condition:"",language:"",
  date:"2026-10-08",display:"₩55,000",kind:"참고 공개가격",source:"https://www.snkrdunk.com/",
  verified_sales:[{verified:true,evidence_type:"completed_sale",grade:"PSA 9",currency:"KRW",
                   price_krw:85000,date:"2026-10-08",source:"https://www.ebay.com/itm/987654321098",
                   sale_id:"ebay:987654321098",review_status:"manual_verified",
                   review_method:"source_page_crosscheck",reviewed_at:"2026-10-09"}]
};
const photoIdentity={game:"pokemon",region:"JP",cardName:"Pikachu",cardNumber:"025/165"};
const evidenceWithoutSet=price.photoEvidenceFromSnapshot({rows:[validPhotoRow]},photoIdentity);
assert.equal(evidenceWithoutSet.status,"single_candidate");
assert.equal(evidenceWithoutSet.reference.display,"₩55,000");
assert.equal(evidenceWithoutSet.sales.length,0,"bare card name/number must not become verified grade price");
assert.equal(evidenceWithoutSet.variantConfirmed,false);
const evidenceWithSet=price.photoEvidenceFromSnapshot({rows:[validPhotoRow]},{...photoIdentity,setName:"151"});
assert.equal(evidenceWithSet.variantConfirmed,true);
assert.equal(evidenceWithSet.sales.length,1);
assert.equal(evidenceWithSet.sales[0].grade,"PSA 9");
for (const [facet,claimed] of [["printing","Unlimited"],["condition","Near Mint"],["language","Japanese"]]) {
  const output=price.photoEvidenceFromSnapshot({rows:[validPhotoRow]},
    {...photoIdentity,setName:"151",[facet]:claimed});
  assert.equal(output.status,"single_candidate","market reference can still be shown");
  assert.equal(output.variantConfirmed,false,
    "extra claimed "+facet+" must not establish missing source-side identity evidence");
  assert.equal(output.sales.length,0,
    "unverified "+facet+" must never promote completed-sale history");
}
assert.equal(price.photoEvidenceFromSnapshot({rows:[validPhotoRow]},{...photoIdentity,setName:"wrong"}).status,"not_found");
const printRow={...validPhotoRow,printing:"1st edition"};
assert.equal(price.photoEvidenceFromSnapshot({rows:[printRow]},{...photoIdentity,setName:"151"}).sales.length,0,
 "unspecified print variant must never promote graded sale");
assert.equal(price.photoEvidenceFromSnapshot({rows:[printRow]},{...photoIdentity,setName:"151",printing:"1st edition"}).sales.length,1);
const langRow={...validPhotoRow,language:"Japanese"};
assert.equal(price.photoEvidenceFromSnapshot({rows:[langRow]},{...photoIdentity,setName:"151"}).variantConfirmed,false);
assert.equal(price.photoEvidenceFromSnapshot({rows:[langRow]},{...photoIdentity,setName:"151",language:"Japanese"}).variantConfirmed,true);
assert.equal(price.photoEvidenceFromSnapshot({rows:[validPhotoRow,validPhotoRow]},{...photoIdentity,setName:"151"}).status,"ambiguous");
assert.equal(price.photoEvidenceFromSnapshot({rows:[validPhotoRow]},{...photoIdentity,region:"KR"}).status,"not_found");
const usRow={...validPhotoRow,region:"US"};
assert.equal(price.photoEvidenceFromSnapshot({rows:[usRow]},{...photoIdentity,region:"US",setName:"151"}).sales.length,1,"US requires explicit market region selection");
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
  assert.equal(normal.reviewCandidates.length,3,"public SOLD listing examples are quarantined as pending review");
  assert.deepEqual(normal.reviewCandidates.map(c=>c.game.id).sort(),["naruto","onepiece","pokemon"]);
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
assert.equal(price.marketCoverage(v586Snapshot,"pokemon").identifiedCards<=26,true);
assert.equal(price.marketCoverage(v586Snapshot,"pokemon").picturedBoxes<=26,true);
assert.equal(price.marketCoverage({rows:[{game:{id:"pokemon"},asset:"HIT",cardName:"A",cardNumber:"1",date:"",source:""}]},"pokemon").sourcedDated,0);
assert.equal(v586Candidates.find(c=>c.game.id==="pokemon").listingClaimedNumber,"040");
assert.equal(v586Candidates.find(c=>c.game.id==="onepiece").listingCertId,"168312211");
assert.ok(fs.readFileSync("tcg_card_detail_v566.js","utf8").includes("a[href],summary"),"keyboard trap includes summary");
console.log("PASS V586 game-by-game market coverage and quarantined listing data");

/* V585: market candidate isolation and fail-closed provenance. */
const v585CandidateFile=JSON.parse(fs.readFileSync("tcg_sale_review_candidates_v585.json","utf8"));
assert.equal(price.reviewSaleCandidates(v585CandidateFile,games).length,3);
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
