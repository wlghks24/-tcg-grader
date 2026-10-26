/* node --test execution/tests/test_tablet_unified_gallery_v676.cjs */
"use strict";
const t = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const gallery = require("../gallery/tablet_unified_gallery_v676.js");

const hex = n => String(n).repeat(32);
const catalog = () => {
  const source = {
    source_record_id: hex("a"), game_id: "pokemon", region: "CN-T", kind: "CARD",
    name: "收藏卡", source_url: "https://www.pokemon-card.com/",
    source_health: "HEALTHY", product_codes: ["SV1-001"]
  };
  const photo = {
    id: hex("b"), game_id: "pokemon", region: "CN-T", kind: "CARD",
    name: "收藏卡", card_metadata: { generation: "Scarlet/Violet", card_number: "001" },
    linked_to_existing_catalog: true, identity_verification: "CODE_MATCH",
    linked_source_record_id: source.source_record_id
  };
  const match = {
    source_record_id: source.source_record_id, id: photo.id, match: "CODE_MATCH",
    game_id: "pokemon", region: "CN-T", kind: "CARD", catalog_kind: "CARD"
  };
  return { ok: true, local_catalog: [photo], source_catalog: [source],
    catalog_matches: [match] };
};
t("region stays one CN tab but original CN-T edition survives", () => {
  assert.equal(gallery.regionTab("CN-T"),"CN");
  assert.equal(gallery.regionTab("CN-S"),"CN");
  assert.equal(gallery.regionTab("RU"),"");
  assert.equal(gallery.gameId("포켓몬 카드"),"pokemon");
  assert.equal(gallery.gameId("ONE PIECE"),"onepiece");
  assert.equal(gallery.gameId("나루토 카드"),"naruto");
});
t("exact source/image bridge links local image, metadata and safety note", () => {
  const rows=gallery.joinCatalog(catalog());
  assert.equal(rows.length,1);
  assert.equal(rows[0].image,"/api/local-card-images/file/"+hex("b"));
  assert.equal(rows[0].region,"CN");
  assert.equal(rows[0].edition,"CN-T");
  assert.equal(rows[0].metadata.generation,"Scarlet/Violet");
  assert.match(rows[0].review,/보류/);
  assert.equal(rows[0].price,"");
});
t("region and kind mismatch cannot borrow card image", () => {
  const data=catalog();
  data.catalog_matches[0].region="JP";
  const rows=gallery.joinCatalog(data);
  assert.equal(rows[0].image,"");
  assert.match(rows[0].imageState,/대기/);
  assert.equal(rows.filter(x=>x.image).length,1); // orphan stays separate
  assert.match(rows[1].imageState,/미연결/);
});
t("ambiguous image matches never auto-link", () => {
  const data=catalog();
  data.catalog_matches.push({...data.catalog_matches[0]});
  const rows=gallery.joinCatalog(data);
  assert.equal(rows[0].image,"");
});
t("unverified or dangerous URLs are rejected", () => {
  for(const bad of [
    "javascript:alert(1)", "http://pokemon-card.com/info",
    "https://attacker.example/", "https://pokemon-card.com.evil.example/",
    "https://user@pokemon-card.com/info", "https://pokemon-card.com:8080/",
    "https://pokemon-card.com/#fragment",
  ]) assert.equal(gallery.safeSource(bad),"");
  assert.ok(gallery.safeSource("https://www.onepiece-cardgame.kr/events.do"));
  assert.equal(gallery.localImage("../../etc/passwd"),"");
});
t("calendar facts not invented for movie tracking or invalid dates",()=>{
  const data={items:[
    {game:"나루토 카드",region:"KR",name_ko:"영화 개봉 추적",tracking_only:true,
      start_date:"2027-12-31",source:"https://naruto-official.com/en/news/"},
    {game:"원피스 카드",region:"JP",name_ko:"행사 개최",start_date:"2026-02-30",
      source:"https://onepiece-cardgame.com/"},
    {game:"포켓몬 카드",region:"KR",name_ko:"캠페인",start_date:"2026-10-20",
      source:"https://pokemon-card.com/"},
  ]};
  const rows=gallery.events(data);
  assert.equal(rows.length,3);
  assert.equal(rows[0].date,"");
  assert.equal(rows[1].date,"");
  assert.equal(rows[2].date,"2026-10-20");
  assert.equal(rows[2].image,"");
});
t("BOX prices always clearly labeled unverified",()=>{
  const rows=gallery.boxes({items:[
    {game:"ONE PIECE",region:"KR",asset:"BOX",name:"박스",product_code:"OPK-14",
      official_price:"₩48,000/BOX",source:"https://onepiece-cardgame.kr/products.do"},
    {game:"ONE PIECE",region:"KR",asset:"BOX",name:"박스",product_code:"OPK-14",
      official_price:"₩48,000/BOX",source:"https://onepiece-cardgame.kr/products.do"},
  ]});
  assert.equal(rows.length,1);
  assert.equal(rows[0].price,"₩48,000/BOX");
  assert.match(rows[0].pricing,/실거래가\/판매가 아님/);
  assert.equal(rows[0].image,"");
  const composition=gallery.boxes({items:[{
    game:"ONE PIECE",region:"KR",asset:"BOX",name:"8BOX",
    official_price:"8BOX 구성",source:"https://onepiece-cardgame.kr/products.do"
  }]});
  assert.equal(composition[0].price,"");
});
t("user filtering is bounded and does not change originals",()=>{
  const rows=gallery.joinCatalog(catalog());
  assert.equal(gallery.filterRows(rows,{game:"pokemon",region:"CN",type:"CARD",query:"SV1"}).length,1);
  assert.equal(gallery.filterRows(rows,{game:"pokemon",region:"JP",type:"CARD"}).length,0);
});
t("HTML refuses remote scripts/forms and no dynamic markup interpolation",()=>{
  const root=path.join(__dirname,"../..");
  const html=fs.readFileSync(path.join(root,"execution/gallery/tablet_unified_gallery_v676.html"),"utf8");
  const js=fs.readFileSync(path.join(root,"execution/gallery/tablet_unified_gallery_v676.js"),"utf8");
  const css=fs.readFileSync(path.join(root,"execution/gallery/tablet_unified_gallery_v676.css"),"utf8");
  assert.match(html,/default-src 'none'/);
  assert.match(html,/connect-src 'self'/);
  assert.match(css,/@media\(max-width:620px\)/);
  for(const id of ["card","box","event","linked"]) assert.match(html,new RegExp('id="fusion-stat-'+id+'"'));
  assert.doesNotMatch(js,/\.innerHTML\s*=/);
  assert.doesNotMatch(html,/<form\b/i);
});
