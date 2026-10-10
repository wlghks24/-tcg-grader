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
const good={verified:true,evidence_type:"completed_sale",currency:"KRW",price_krw:81000,date:"2026-07-26",grade:"PSA 10",source:"https://www.snkrdunk.com/"};
const fake={...good,verified:false,price_krw:10000000};
const evil={...good,source:"https://www.snkrdunk.com.evil.example/"};
const wrongCurrency={...good,currency:"JPY"};
const wrongGrade={...good,grade:"BGS 10"};
const ref={...good,evidence_type:"asking_price"};
const sample={verified_sales:[fake,evil,wrongCurrency,wrongGrade,ref,good,{...good,price_krw:94000,date:"2026-10-08"}]};
const sales=price.verifiedSales(sample);
assert.equal(sales.length,2);
assert.equal(price.rangeSales(sales,"PSA 10",0).length,2);
assert.equal(price.rangeSales(sales,"RAW",0).length,0);
assert.equal(price.rangeSales(sales,"PSA 10",3).length,2);
assert.equal(price.rangeSales(sales,"PSA 10",1).length,1);

const verifiedRow={region:"JP",asset:"HIT",game:{id:"pokemon"},cardName:"Pikachu",cardNumber:"025/165",setName:"151"};
const verifiedIdentity={region:"JP",game:"pokemon",cardName:"Pikachu",cardNumber:"025/165",setName:"151"};
assert.equal(price.strictIdentityMatch(verifiedRow,verifiedIdentity),true);
assert.equal(price.strictIdentityMatch(verifiedRow,{...verifiedIdentity,setName:"different set"}),false);
assert.equal(price.strictIdentityMatch({...verifiedRow,cardNumber:""},verifiedIdentity),false);
assert.equal(price.strictIdentityMatch(verifiedRow,{...verifiedIdentity,region:"US"}),false);
assert.equal(price.strictIdentityMatch(verifiedRow,{...verifiedIdentity,cardNumber:"025"}),false);
assert.equal(price.strictIdentityMatch({...verifiedRow,game:{id:"gundam"}},verifiedIdentity),false);

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
console.log("PASS V566: dynamic registry, promoted/WATCH, exact matching, strict sale filters, freshness, URL safety, mounted assets");
