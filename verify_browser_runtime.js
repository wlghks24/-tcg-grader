#!/usr/bin/env node
"use strict";

// Execute the real inline browser functions against damaged storage and hostile data.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
const lines = html.split(/\r?\n/);
const records = new Map();
const elements = new Map();
const createdObjectUrls = [];
const releasedObjectUrls = [];
let storageUnavailable = false;
let imageShouldFail = false;

class BrowserRuntimeURL extends URL {
  static createObjectURL(file) {
    if (!file || file.invalid) throw new TypeError("invalid image file");
    const objectUrl = `blob:tcg-runtime/${createdObjectUrls.length}`;
    createdObjectUrls.push(objectUrl);
    return objectUrl;
  }

  static revokeObjectURL(objectUrl) {
    releasedObjectUrls.push(objectUrl);
  }
}

class BrowserRuntimeImage {
  set src(value) {
    this.objectUrl = value;
    if (imageShouldFail) this.onerror(new Error("image decode failed"));
    else this.onload();
  }

  get src() {
    return this.objectUrl;
  }
}

const localStorage = {
  getItem(key) {
    if (storageUnavailable) throw new Error("storage disabled");
    return records.has(key) ? records.get(key) : null;
  },
  setItem(key, value) {
    records.set(key, String(value));
  },
  removeItem(key) {
    records.delete(key);
  },
};

function element(id) {
  if (!elements.has(id)) elements.set(id, { id, value: "", innerHTML: "", textContent: "" });
  return elements.get(id);
}

const context = vm.createContext({
  URL: BrowserRuntimeURL,
  Image: BrowserRuntimeImage,
  console,
  localStorage,
  document: { getElementById: element },
  HKEY: "history",
  V11KEY: "v11",
  V11CORR: "correction",
  V17KEY: "pending",
  V30CAL: "calibration",
  GRADING_COMPANIES: ["PSA", "BGS", "CGC", "TAG", "BRG"],
  OFFICIAL: {
    PSA: { 10: { f: 45, b: 25 }, 9: { f: 40, b: 30 }, 8: { f: 30, b: 20 } },
    BGS: { 10: { f: 50, b: 40 }, 9.5: { f: 45, b: 40 }, 9: { f: 45, b: 30 }, 8: { f: 40, b: 20 } },
    CGC: { 10: { f: 45, b: 25 }, 9.5: { f: 40, b: 30 }, 9: { f: 40, b: 30 } },
    TAG: { 10: { f: 49, b: 48 } },
    BRG: {},
  },
  COUNTRY_BOX_DATA: [],
  LEARNING_PRICE_DATA: {},
  popularityMarketEntries: {},
  popularityMarketKeys: new Set(),
  marketWatchEntries: {},
  gradedPriceProfiles: {},
  gradingCostDefaults: {},
  gameKorean: { "Pokémon": "포켓몬 카드" },
  fxRates: { JPY_KRW: 8.7, USD_KRW: 1380 },
  fxUpdated: "2026-08-25",
  simpleGame: "pokemon",
  profiles: { pokemon: { name: "Pokémon" } },
  S: element,
  $: element,
  renderCountryAnalysis() {},
  renderTradeCatalog() {},
  populateEconomicsCards() {},
});

function loadOneLine(name, asynchronous = false) {
  const prefix = `${asynchronous ? "async " : ""}function ${name}(`;
  const line = lines.find((item) => item.trimStart().startsWith(prefix));
  assert.ok(line, `Missing browser function: ${name}`);
  vm.runInContext(line.trim(), context, { filename: `index.html:${name}` });
}

function loadBlock(name) {
  const expression = new RegExp(`^function ${name}\\([^\\n]*\\)\\{[\\s\\S]*?^\\}`, "m");
  const match = expression.exec(html);
  assert.ok(match, `Missing multiline browser function: ${name}`);
  vm.runInContext(match[0], context, { filename: `index.html:${name}` });
}

function loadAsyncBlock(name) {
  const expression = new RegExp(`^async function ${name}\\([^\\n]*\\)\\{[\\s\\S]*?^\\}`, "m");
  const match = expression.exec(html);
  assert.ok(match, `Missing multiline async browser function: ${name}`);
  vm.runInContext(match[0], context, { filename: `index.html:${name}` });
}

async function main() {
  for (const name of ["loadCardImage", "load", "v6Load", "v7Image", "v30Load", "cardInputFile", "escapeDisplayText", "safeStoredJson", "safeVisionFeatures", "validCompanyActual", "safeExternalUrl", "trustedPromoOfficialUrl", "renderHistory", "v11Get", "v11Correction", "v17get", "foreignKrw", "finiteMoney", "normalizeGradePrices"]) {
    loadOneLine(name);
  }
  loadBlock("safeGradeRows");
  loadBlock("v20render");
  loadBlock("v20LearningHtml");
  loadBlock("v30GetCal");
  loadBlock("mergeLearning");
  loadBlock("renderTradeCatalog");
  loadBlock("calculateGradingEconomics");
  loadBlock("qualityGrade");
  loadOneLine("generalCenterGrade");
  loadBlock("tagScoreToGrade");
  loadBlock("gradeByCenter");
  loadBlock("g");
  loadBlock("gt");
  loadBlock("normalizedSupplementaryItems");
  loadBlock("normalizedSocialEventItems");
  loadBlock("renderPromos");
  for (const name of ["purchaseUrl", "haversineKm", "sourceProbability", "probLabel", "currentPurchaseQuery"]) {
    loadOneLine(name);
  }
  loadBlock("renderNearbyPurchase");
  loadBlock("renderPurchaseSources");
  loadOneLine("quickPrice", true);
  loadAsyncBlock("v13LoadAllPriceData");
  loadAsyncBlock("loadPopularitySignals");
  loadAsyncBlock("loadExchangeRates");

  for (const name of ["loadCardImage", "load", "v6Load", "v7Image", "v30Load"]) {
    const image = await context[name]({ name });
    assert.ok(image instanceof BrowserRuntimeImage, `${name} did not return the loaded image`);
    assert.equal(image.src, createdObjectUrls.at(-1));
  }
  assert.deepEqual(releasedObjectUrls, createdObjectUrls, "successful image URLs were not released");
  imageShouldFail = true;
  await assert.rejects(context.v7Image({ name: "broken image" }), /image decode failed/);
  imageShouldFail = false;
  assert.deepEqual(releasedObjectUrls, createdObjectUrls, "failed image URL was not released");
  await assert.rejects(context.loadCardImage({ invalid: true }), /invalid image file/);
  assert.equal((html.match(/\bnew Image\(\)/g) || []).length, 1, "duplicate browser image implementations remain");
  const nativeFile = { name: "manual.jpg" }, capturedFile = { name: "camera.jpg" };
  element("front").files = [nativeFile];
  assert.equal(context.cardInputFile("front"), nativeFile);
  element("front")._tcgCapturedFile = capturedFile;
  assert.equal(context.cardInputFile("front"), capturedFile, "camera fallback file did not take priority");
  element("front")._tcgCapturedFile = null;

  assert.equal(context.escapeDisplayText('<img src=x onerror="x">'), "&lt;img src=x onerror=&quot;x&quot;&gt;");
  assert.equal(context.safeExternalUrl("javascript:alert(1)"), "#");
  assert.equal(context.safeExternalUrl("http://example.com/"), "#");
  assert.equal(context.safeExternalUrl("https://user@example.com/"), "#");
  for (const unsafe of ["https://localhost/", "https://localhost.localdomain/", "https://printer.local/", "https://127.0.0.1/", "https://192.168.0.5/", "https://172.16.1.2/", "https://[::1]/", "https://example.com:8443/", "https://example.com/\nsecret", "https://example.com/\\private", `https://example.com/${"x".repeat(2050)}`]) {
    assert.equal(context.safeExternalUrl(unsafe), "#", `Unsafe external URL accepted: ${unsafe}`);
  }
  assert.equal(context.safeExternalUrl("https://example.com/cards"), "https://example.com/cards");
  assert.equal(context.safeExternalUrl("https://example.com:443/cards"), "https://example.com/cards");

  assert.equal(context.trustedPromoOfficialUrl("https://one-piece.com/news/79329/index.html"), true);
  for (const unsafe of ["https://namu.wiki/w/movie", "https://one-piece.com.evil.example/movie", "http://one-piece.com/news", "https://user@one-piece.com/news", "https://one-piece.com:8443/news"]) {
    assert.equal(context.trustedPromoOfficialUrl(unsafe), false, `Unofficial movie source accepted: ${unsafe}`);
  }
  context.promoData = {
    updated_at: "2026-08-25T00:00:00Z",
    coverage: { expected_game_region_pairs: 9, watched_game_region_pairs: 9, covered_game_region_pairs: 9, movie_game_region_pairs: 9 },
    items: [{ game: "원피스 카드", region: "JP", category: "movie", name_ko: "THE ONE PIECE", name_native: "Netflix", start_date: "2027-02-01", end_date: "2027-02-28", claim_deadline: "2027-02-28", date_precision: "month", date_label: "2027년 2월 공개 예정 · 정확한 날짜 미발표", media_type: "streaming_series", reward: "공식 영상", condition: "공식 발표", source: "https://one-piece.com/news/79329/index.html" },
      { game: "나루토 카드", region: "US", category: "movie", name_ko: "미국 나루토 영화", start_date: "2026-08-25", end_date: "2027-12-31", claim_deadline: "2027-12-31", date_precision: "unannounced", date_label: "개봉일 공식 미발표", tracking_only: true, reward: "제작 발표", condition: "개봉일 미발표", source: "https://naruto-official.com/en/news/01_2649" }],
  };
  context.supplementaryData = { updated_at: "2026-08-25T00:00:00Z", items: [
    { game: "원피스 카드", region: "JP", category: "movie", title: "THE ONE PIECE duplicate", source: "https://one-piece.com/news/79329/index.html", source_tier: "A", verified: true, dates: [], release_window: "2027-02", date_precision: "month", date_label: "2027년 2월 공개 예정 · 정확한 날짜 미발표" },
    { game: "나루토 카드", region: "KR", category: "movie", title: '<img src=x onerror="leak()">', source: "https://namu.wiki/w/movie", source_tier: "C", verified: true, official_source: "https://naruto-official.com/en/news/01_2649", dates: [] },
  ] };
  context.socialEventData = { updated_at: "2026-08-28T00:00:00Z", items: [
    { game: "포켓몬 카드", region: "KR", category: "collaboration", title: "포켓몬 공식 SNS 콜라보", source: "https://www.instagram.com/p/ABC123/", source_kind: "instagram", source_tier: "A-social", source_label: "Instagram 공식계정", official_account_verified: true, verification_origin: "https://www.pokemonkorea.co.kr/", dates: ["2026-09-20"], excerpt: "공식 콜라보 안내", confidence: 0.96, status: "공식 SNS 후보" }
  ] };
  const candidates = context.normalizedSupplementaryItems();
  assert.equal(candidates[0].source_grade, "official");
  assert.equal(candidates[0].start_date, "2027-02-01");
  assert.equal(candidates[0].end_date, "2027-02-28");
  assert.equal(candidates[1].source_grade, "supplementary", "Unconfirmed community claim was promoted");
  for (const id of ["promoGame", "promoFilter", "promoType", "promoSourceGrade"]) element(id).value = "ALL";
  context.renderPromos();
  const promoHtml = element("promoList").innerHTML;
  assert.match(promoHtml, /공식 SNS/);
  assert.match(promoHtml, /포켓몬 공식 SNS 콜라보/);
  assert.equal((promoHtml.match(/79329\/index\.html/g) || []).length, 1, "Official and supplementary movie cards were duplicated");
  assert.match(promoHtml, /2027년 2월 공개 예정 · 정확한 날짜 미발표/);
  assert.match(promoHtml, /공식발표 추적/);
  assert.match(promoHtml, /공식 영상·애니메이션/);
  assert.ok(!promoHtml.includes("2027-02-01"), "Internal month boundary shown as confirmed release day");
  assert.ok(!promoHtml.includes("2027-12-31"), "Internal review deadline shown as movie release day");
  assert.ok(!promoHtml.includes("<img src=x"), "Supplementary title was not escaped");
  assert.match(element("promoCoverage").textContent, /공식 출처 감시 9\/9/);
  element("promoSourceGrade").value = "confirmed";
  context.renderPromos();
  assert.ok(!element("promoList").innerHTML.includes("namu.wiki"), "Unconfirmed community claim entered confirmed filter");

  context.PURCHASE_TERMS = { Pokemon: { KR: "포켓몬 카드", JP: "ポケモンカード", US: "Pokemon cards" } };
  context.ASSET_TERMS = { all: "카드 BOX 박스 팩" };
  context.RETAILER_LABELS = {
    convenience: "편의점", hypermarket: "대형마트", stationery: "문구점",
    toy: "완구점", bookstore: "서점·팬시", cardshop: "카드 전문점",
    discount: "생활·할인매장", general: "일반 매장",
  };
  context.purchaseChannel = "all";
  context.purchaseLiveSignals = {};
  context.purchaseLocation = { lat: 37.3219, lon: 126.8309, label: '<img src=x onerror="location()">' };
  context.purchaseData = {
    updated_at: "2026-08-26T00:00:00Z",
    sources: [
      { name: "CU 편의점 주변 매장", region: "KR", games: ["Pokemon"], type: "map", channel: "offline", retailer_category: "convenience", url_template: "https://map.naver.com/p/search/CU%20{query}", inventory_status: "TCG 취급·재고 미확인" },
      { name: "GS25 편의점 주변 매장", region: "KR", games: ["Pokemon"], type: "map", channel: "offline", retailer_category: "convenience", url_template: "https://map.naver.com/p/search/GS25%20{query}", inventory_status: "TCG 취급·재고 미확인" },
      { name: "이마트 안산고잔점", region: "KR", games: ["Pokemon"], type: "map", channel: "offline", retailer_category: "hypermarket", url: "https://map.naver.com/p/search/emart", address: "경기도 안산시 단원구 원포공원1로 46", lat: 37.302925, lon: 126.813203, inventory_status: "TCG 취급·재고 미확인" },
      { name: "알파문구 경기대점", region: "KR", games: ["Pokemon"], type: "map", channel: "offline", retailer_category: "stationery", url: "https://map.naver.com/p/search/alpha", address: "경기도 수원시 영통구 대학3로 7", lat: 37.299769, lon: 127.042176, note: '<img src=x onerror="store()">', inventory_status: "TCG 취급·재고 미확인" },
      { name: "손상된 게임 분류", region: "KR", games: null, type: "map", channel: "offline", retailer_category: "convenience", url: "https://example.com/store" },
    ],
  };
  element("purchaseGame").value = "Pokemon";
  element("purchaseQuery").value = "테스트 카드";
  element("purchaseAreaText").value = "안산";
  element("purchaseAsset").value = "all";
  element("purchaseSort").value = "nearby";
  element("purchaseRetailerType").value = "convenience";
  context.renderPurchaseSources();
  assert.match(element("purchaseRegionGrid").innerHTML, /CU 편의점 주변 매장/);
  assert.match(element("purchaseRegionGrid").innerHTML, /GS25 편의점 주변 매장/);
  assert.ok(!element("purchaseRegionGrid").innerHTML.includes("이마트 안산고잔점"), "Hypermarket entered convenience-store filter");
  assert.match(decodeURIComponent(element("purchaseNearby").innerHTML), /편의점/);
  assert.match(element("purchaseUpdated").textContent, /구매처 5곳/);
  element("purchaseRetailerType").value = "hypermarket";
  context.renderPurchaseSources();
  assert.match(element("purchaseRegionGrid").innerHTML, /이마트 안산고잔점/);
  assert.ok(!element("purchaseRegionGrid").innerHTML.includes("CU 편의점"), "Convenience store entered hypermarket filter");
  assert.match(element("purchaseNearby").innerHTML, /이마트 안산고잔점/);
  assert.ok(!element("purchaseRegionGrid").innerHTML.includes("<img src=x"), "Purchase location label escaped the XSS guard");
  element("purchaseRetailerType").value = "stationery";
  context.renderPurchaseSources();
  assert.match(element("purchaseRegionGrid").innerHTML, /알파문구 경기대점/);
  assert.match(element("purchaseRegionGrid").innerHTML, /재고 미확인/);
  assert.ok(!element("purchaseRegionGrid").innerHTML.includes("<img src=x"), "Stationery-shop note escaped the XSS guard");
  assert.match(decodeURIComponent(element("purchaseNearby").innerHTML), /문구점/);
  element("purchaseRetailerType").value = "ALL";
  context.purchaseChannel = "offline";
  context.renderPurchaseSources();
  assert.match(element("purchaseRegionGrid").innerHTML, /CU 편의점 주변 매장/);
  assert.match(element("purchaseRegionGrid").innerHTML, /알파문구 경기대점/);
  assert.ok(!element("purchaseRegionGrid").innerHTML.includes("손상된 게임 분류"), "Malformed store game list caused an unsafe match");

  records.set("broken", "{not json");
  assert.equal(context.safeStoredJson("broken", []).length, 0);
  records.set("wrong-shape", JSON.stringify({ value: 1 }));
  assert.equal(context.safeStoredJson("wrong-shape", []).length, 0);
  storageUnavailable = true;
  assert.equal(context.safeStoredJson("broken", []).length, 0);
  storageUnavailable = false;

  const validRows = context.safeGradeRows([
    null,
    { company: "BAD", actual: 9, pred: 9 },
    { company: "PSA", actual: "NaN", pred: 9 },
    { company: "PSA", actual: 9, pred: 10, injected: "must be removed", mode: "raw" },
    { company: "TAG", actual: 10, pred: 9, injected: "must be removed", mode: "slab" },
    { company: "BRG", actual: 8, pred: 7, injected: "must be removed", mode: "raw" },
  ]);
  assert.equal(validRows.length, 3);
  assert.equal(validRows[0].company, "PSA");
  assert.equal(validRows[0].injected, undefined);
  assert.equal(validRows[0].mode, "raw");
  assert.equal(validRows[1].company, "TAG");
  assert.equal(validRows[1].injected, undefined);
  assert.equal(validRows[1].mode, "slab");
  assert.equal(validRows[2].company, "BRG");
  assert.equal(validRows[2].injected, undefined);

  const brgEconomics = context.calculateGradingEconomics({
    buy: 100, raw: 120, prices: { 8: 150, 9: 250, 10: 500 },
    gradingFee: 50, shipping: 30, sellingFee: 10, company: "BRG", grade: 9,
  });
  assert.equal(brgEconomics.company, "BRG");
  assert.equal(brgEconomics.grade, 9);
  assert.equal(brgEconomics.expectedSale, 250);
  assert.equal(brgEconomics.expectedProfit, 45);
  assert.equal(brgEconomics.breakEven, 200);
  assert.equal(brgEconomics.roi, 25);
  assert.equal(brgEconomics.rows.length, 10);
  assert.equal(brgEconomics.rows[9].sale, 500);
  const normalized = context.calculateGradingEconomics({
    buy: -1, raw: 100, prices: { 1: -20, 10: "bad" },
    gradingFee: -1, shipping: -1, sellingFee: 999, company: "BAD", grade: 99,
  });
  assert.equal(normalized.company, "PSA");
  assert.equal(normalized.grade, 10);
  assert.equal(normalized.feeRate, 0.4);
  assert.equal(normalized.expectedSale, 0);
  assert.equal(normalized.totalCost, 0);
  assert.equal(context.finiteMoney(Number.POSITIVE_INFINITY), 0);
  assert.equal(context.finiteMoney(true), 0);
  assert.equal(context.finiteMoney(1e308), 1_000_000_000_000);
  assert.equal(context.normalizeGradePrices(Object.create({ 10: 999 }))[10], 0);
  assert.equal(context.calculateGradingEconomics(null).grade, 1);
  assert.ok(Number.isFinite(context.calculateGradingEconomics({buy:1e308,gradingFee:1e308,shipping:1e308,grade:Infinity,sellingFee:Infinity}).totalCost));

  assert.equal(context.qualityGrade(0), 10);
  assert.equal(context.qualityGrade(90), 1);
  assert.equal(context.qualityGrade(Number.NaN), 1);
  assert.equal(context.qualityGrade(-1), 1);
  assert.equal(context.generalCenterGrade(50, 50), 10);
  assert.equal(context.generalCenterGrade(3, 50), 1);
  assert.equal(context.generalCenterGrade(Number.POSITIVE_INFINITY, 50), 1);
  assert.equal(context.tagScoreToGrade(1000).condition, "PRISTINE");
  assert.equal(context.tagScoreToGrade(990).grade, 10);
  assert.equal(context.tagScoreToGrade(989).condition, "GEM MINT");
  assert.equal(context.tagScoreToGrade(950).grade, 10);
  assert.equal(context.tagScoreToGrade(949).grade, 9);
  assert.equal(context.tagScoreToGrade(850).grade, 8.5);
  assert.equal(context.tagScoreToGrade(99), null);
  assert.equal(context.tagScoreToGrade(Number.NaN), null);
  assert.equal(context.gradeByCenter(49, 48, "TAG"), 10);
  assert.equal(context.gradeByCenter(40, 40, "TAG"), 9);
  assert.equal(context.gradeByCenter(Number.POSITIVE_INFINITY, 40, "TAG"), 1);
  assert.equal(context.gradeByCenter(50, 50, "BAD"), 1);
  assert.equal(context.gradeByCenter(20, 20, "BRG"), 5);
  assert.equal(context.g(50, 50, 90, "BRG"), 1);
  assert.equal(context.g(50, 50, 5, "TAG"), 10);
  assert.equal(context.g(50, 50, 5.1, "TAG"), 9);
  assert.equal(context.safeGradeRows([{company:"TAG",actual:9.5,pred:9.5}]).length, 0);
  assert.equal(context.gt(9.5, "TAG"), "9");
  assert.match(context.gt(10, "TAG"), /950~1000/);

  records.set("history", "{broken");
  context.renderHistory();
  assert.match(element("history").innerHTML, /저장된 검사 결과가 없습니다/);
  records.set("history", JSON.stringify([{ game: "<img src=x>", time: "<script>", summary: "<svg>" }]));
  context.renderHistory();
  assert.ok(!element("history").innerHTML.includes("<img"));
  assert.ok(!element("history").innerHTML.includes("<script"));
  assert.ok(element("history").innerHTML.includes("&lt;img"));

  records.set("correction", JSON.stringify({ PSA: "broken", BGS: 5, CGC: -2 }));
  const correction = context.v11Correction();
  assert.equal(correction.PSA, 0);
  assert.equal(correction.BGS, 1);
  assert.equal(correction.CGC, 0);
  records.set("pending", JSON.stringify([null, "bad", { name: "ok" }]));
  assert.equal(context.v17get().length, 1);

  records.set("calibration", JSON.stringify({ PSA: { n: "7", meanError: 0.2, correction: 9, strength: 4 }, BGS: { correction: "bad" } }));
  const calibration = context.v30GetCal();
  assert.equal(calibration.PSA.n, 7);
  assert.equal(calibration.PSA.correction, 1);
  assert.equal(calibration.PSA.strength, 1);
  assert.equal(calibration.BGS, undefined);

  const first = { time: "one", company: "PSA", actual: 9, pred: 10 };
  const second = { time: "two", company: "BGS", actual: 9, pred: 9 };
  assert.equal(context.mergeLearning([first], [first, second]).length, 2);

  const attack = '<img src=x onerror="alert(76)">';
  context.v20render({
    updated_at: attack,
    pending: [{ source: attack, status: attack, error: attack, url: "javascript:alert(1)" }],
    auto_update: { enabled: true, interval_hours: attack, next_run: attack },
  });
  assert.ok(!element("v20out").innerHTML.includes("<img"));
  assert.ok(!element("v20out").innerHTML.includes("javascript:"));

  const learningHtml = context.v20LearningHtml(
    { issues: [{ name: attack, severity: attack, error_code: attack, detail: attack,
      probable_cause: attack, resolution_steps: [attack] }] },
    { total_runs: 9, summary: { error_group_count: 1, new_group_count: 1, unresolved_group_count: 1 },
      groups: [{ title: attack, code: attack, occurrences: 3, analysis_status: attack,
        affected_files: [attack], probable_cause: attack, resolution_steps: [attack] }],
      safety: attack },
    { successful_passes: 6, completed_passes: 6 },
  );
  assert.ok(!learningHtml.includes("<img"));
  assert.ok(!learningHtml.includes("<script"));
  assert.ok(learningHtml.includes("&lt;img"));

  for (const id of ["tradeCountry", "tradeAsset", "tradeGame"]) element(id).value = "ALL";
  element("tradeSort").value = "PRICE";
  element("tradeQuery").value = "";
  const key = `KR|${attack}|BOX`;
  context.popularityMarketEntries = {
    [key]: {
      game: "Pokémon",
      product_name: attack,
      official_price: `¥100 ${attack}`,
      display: `₩100 ${attack}`,
      kind: attack,
      market: attack,
      transactions: attack,
      source_date: attack,
      source: "javascript:alert(1)",
    },
  };
  context.fxUpdated = attack;
  context.renderTradeCatalog();
  assert.ok(!element("tradeCatalogList").innerHTML.includes("<img"));
  assert.ok(!element("tradeCatalogList").innerHTML.includes("javascript:"));
  assert.ok(element("tradeCatalogList").innerHTML.includes("&lt;img"));

  element("quickCardQuery").value = "pokemon";
  context.fetch = async () => ({ json: async () => ({ entries: { [`pokemon-${attack}`]: { detail: attack } } }) });
  await context.quickPrice();
  assert.ok(!element("quickPriceResults").innerHTML.includes("<img"));
  assert.ok(element("quickPriceResults").innerHTML.includes("&lt;img"));

  context.fetch = async () => { throw new Error("simulated offline"); };
  const failedPriceLoad = await context.v13LoadAllPriceData();
  assert.equal(failedPriceLoad.ok, false);
  assert.deepEqual(Array.from(failedPriceLoad.errors), ["가격자료", "판매·재발매자료"]);
  const failedMarketLoad = await context.loadPopularitySignals(true);
  assert.equal(failedMarketLoad.ok, false);
  assert.equal(failedMarketLoad.priceOk, false);
  assert.equal(failedMarketLoad.watchOk, false);
  const failedFxLoad = await context.loadExchangeRates(true);
  assert.equal(failedFxLoad.ok, false);
  assert.deepEqual(Array.from(failedFxLoad.errors), ["환율자료"]);

  context.fetch = async (url) => ({
    ok: true,
    status: 200,
    json: async () => String(url).includes("market_prices")
      ? { entries: { "KR|TEST|BOX": { display: "₩1" } }, graded_prices: {}, grading_cost_defaults: {} }
      : String(url).includes("market_watch")
        ? { items: [{ region: "KR", name: "TEST", asset: "BOX" }] }
        : { rates: { JPY_KRW: 8.7, USD_KRW: 1380 }, updated_at: "2026-08-25" },
  });
  assert.equal((await context.v13LoadAllPriceData()).complete, true);
  assert.equal((await context.loadPopularitySignals(true)).ok, true);
  assert.equal((await context.loadExchangeRates(true)).ok, true);

  assert.ok(!/JSON\.parse\(localStorage\.getItem/.test(html), "Unsafe direct localStorage parsing remains");
  assert.ok(!html.includes('fetch(`/api/update?t=${Date.now()}`,{cache:'), "Top update still performs a GET mutation");
  assert.ok(html.includes("window.tcgStartUpdateJob=startJob"), "Background updater is not shared with top update");
  assert.ok(html.includes('id="v20apply"'), "PC/tablet approval handler has no button");
  assert.ok(html.includes('id="v17sources"'), "Manual source link list is missing");
  assert.ok(!html.includes("window.open("), "Multi-popup source launcher remains");
  for (const tag of html.match(/<a\b[^>]*target="_blank"[^>]*>/g) || []) {
    assert.match(tag, /rel="[^"]*noopener[^"]*noreferrer[^"]*"/, `Unsafe new-window link: ${tag}`);
  }
  assert.ok(html.includes('window.tcgStartUpdateJob("/api/run-auto-update","PC·태블릿 최신정보 수집")'), "PC/tablet update still bypasses background job");
  assert.ok(html.includes('window.tcgStartUpdateJob("/api/run-auto-update","모바일 요청 최신정보 수집")'), "Mobile update still bypasses background job");
  console.log("PASS: browser storage recovery, shared image loaders and URL cleanup, all link buttons and safe new-window links, convenience/hypermarket/stationery filters, Ansan distance, explicit offline states, background update contract, grade validation and XSS guards");
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
