from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{path}: marker missing: {old!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Manga is a treatment/variant; SEC/SR/etc remain the underlying One Piece rarity.
patch(
    "card_metadata_classifier_v328.js",
    "g==='onepiece'?['MANGA','SP','SEC','L','SR','R','UC','C','P']",
    "g==='onepiece'?['SP','SEC','L','SR','R','UC','C','P']",
)

patch(
    "index.html",
    '<script src="ui_app_shell_v272.js?v=272"></script>\n<script src="card_identity_recognition.js?v=207"></script>',
    '<script src="ui_app_shell_v272.js?v=272"></script>\n<script src="card_metadata_classifier_v328.js?v=328"></script>\n<script src="card_identity_recognition.js?v=207"></script>',
)

page = (ROOT / "index.html").read_text(encoding="utf-8")
quick = r"""async function quickPrice(){
 const q=S('quickCardQuery').value.trim();
 if(!q){S('quickPriceResults').textContent='카드명 또는 카드번호를 입력하세요.';return}
 const region=String(S('identityRegion')?.value||'UNKNOWN').toUpperCase();
 if(region==='UNKNOWN'){S('quickPriceResults').innerHTML='<b>판본(KR/JP/US)을 먼저 확인하세요.</b> 판본 미확인 상태에서는 다른 판본 가격을 자동 혼합하지 않습니다.';return}
 const metadata=window.TCGCardMetadata;
 if(!metadata){S('quickPriceResults').textContent='카드 분류 모듈을 불러오지 못했습니다. 새로고침 후 다시 시도하세요.';return}
 S('quickPriceResults').textContent='동일 게임·판본·카드 근거를 확인하는 중…';
 try{
  const r=await fetch(`market_prices.json?t=${Date.now()}`,{cache:'no-store'}),d=await r.json(),entries=d.entries&&typeof d.entries==='object'?d.entries:{};
  const cardName=(S('identityCardName')?.value||q).trim(),cardNumber=(S('identityCardNumber')?.value||'').trim();
  const target=metadata.classify({game:simpleGame,region,card_name:cardName,card_number:cardNumber,ocr_text:q,condition:'raw'});
  const tokens=(q.toLowerCase().match(/[0-9a-z가-힣ぁ-んァ-ヶ一-龯]{2,}/g)||[]).slice(0,12),exact=[],reference=[];
  for(const [k,v] of Object.entries(entries)){
   if(!v||typeof v!=='object')continue;
   const keyRegion=String(k).split('|',1)[0].toUpperCase();
   const candidate=metadata.classify({game:v.game||'',region:keyRegion,card_name:v.card_name||'',card_number:v.card_number||'',product_name:v.product_name||'',title:v.title||'',market_key:k,rarity:v.rarity||'',variant:v.variant||'',grading_company:v.grading_company||'',grade:v.grade,condition:v.condition||''});
   if(candidate.game!==target.game||candidate.region!==target.region||candidate.product_type!=='CARD')continue;
   const blob=(k+' '+JSON.stringify(v)).toLowerCase(),tokenHit=!tokens.length||tokens.some(t=>blob.includes(t));
   if(!tokenHit)continue;
   const bound=metadata.bindPrice(target,candidate);
   if(bound.identity_safe)exact.push([k,v,bound]);else reference.push([k,v,bound]);
  }
  const rows=[...exact.slice(0,8),...reference.slice(0,Math.max(0,8-exact.length))];
  if(!rows.length){S('quickPriceResults').innerHTML='동일 게임·판본에서 일치 후보를 찾지 못했습니다. <b>카드번호·세트·희귀도까지 확인</b>하면 정확도가 올라갑니다.';return}
  S('quickPriceResults').innerHTML=rows.map(([k,v,bound])=>`<div class="price-item"><b>${bound.identity_safe?'✅ 카드번호·판본 일치':'⚠ 판본 일치 참고 · 추가확인 필요'} · ${escapeDisplayText(k)}</b><br><span class="muted">${Object.entries(v).filter(([a,b])=>['string','number'].includes(typeof b)).slice(0,8).map(([a,b])=>`${escapeDisplayText(a)}: ${escapeDisplayText(b)}`).join(' · ')}</span></div>`).join('');
 }catch(e){S('quickPriceResults').textContent='시세자료를 불러오지 못했습니다. 업데이트 후 다시 시도하세요.'}
}"""
# verify_browser_runtime intentionally loads this inline helper one physical line.
quick = "".join(line.strip() for line in quick.splitlines())
page2, count = re.subn(
    r"async function quickPrice\(\)\{.*?(?=\n S\('startAutoCamera'\)\.onclick=start;)",
    quick,
    page,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit(f"index.html quickPrice patch count={count}")
(ROOT / "index.html").write_text(page2, encoding="utf-8")

market = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
old = """function quoteScore(row,name,number,region){
 if(!row||row.platform!=='WYYYES')return -999;
 const title=norm(row.title),n=norm(name),cn=norm(number),qcn=norm(row.card_number);"""
new = """function quoteScore(row,name,number,region){
 if(!row||row.platform!=='WYYYES')return -999;
 const metadata=window.TCGCardMetadata;if(!metadata)return -999;
 const card=metadata.classify({game:window.tcgIdentityGame||'',region,card_name:name,card_number:number,condition:'raw'});
 const quote=metadata.classify({game:row.game||'',region:row.card_region||'UNKNOWN',card_name:row.card_name||row.title||'',card_number:row.card_number||'',product_name:row.product_name||row.title||'',title:row.title||'',market_key:row.market_key||'',rarity:row.rarity||'',variant:row.variant||'',grading_company:row.grading_company||'',grade:row.grade,condition:row.condition||''});
 const bound=metadata.bindPrice(card,quote);if(!bound.identity_safe)return -999;
 const title=norm(row.title),n=norm(name),cn=norm(number),qcn=norm(row.card_number);"""
if new not in market:
    if old not in market:
        raise SystemExit("grade_market_flow.js quoteScore marker missing")
    market = market.replace(old, new, 1)
old2 = """ const n=norm(name),cn=norm(number),direct=(el('identityMarketKey')?.value||'').trim();
 const directOption=options.find(option=>option.value===direct);"""
new2 = """ const n=norm(name),cn=norm(number),direct=(el('identityMarketKey')?.value||'').trim();
 if(!cn)return '';
 if(/^\\d+\\/\\d+$/.test(cn))return '';
 const directOption=options.find(option=>option.value===direct);"""
if new2 not in market:
    if old2 not in market:
        raise SystemExit("grade_market_flow.js findMarketKey marker missing")
    market = market.replace(old2, new2, 1)
(ROOT / "grade_market_flow.js").write_text(market, encoding="utf-8")

patch("tcg_updater.py", "'grading_accuracy_v99.js','card_identity_recognition.js','manual_dual_photo_bridge.js'", "'grading_accuracy_v99.js','card_metadata_classifier_v328.js','card_identity_recognition.js','manual_dual_photo_bridge.js'")
patch("tablet_runtime_manifest.py", '"grading_vision_engine.js","grading_accuracy_v99.js","card_identity_recognition.js",', '"grading_vision_engine.js","grading_accuracy_v99.js","card_metadata_classifier_v328.js","card_identity_recognition.js",')
patch("test_tablet_runtime_manifest_ui_assets_v254.py", '"index.html","grading_vision_engine.js","grading_accuracy_v99.js","card_identity_recognition.js",', '"index.html","grading_vision_engine.js","grading_accuracy_v99.js","card_metadata_classifier_v328.js","card_identity_recognition.js",')
patch("test_card_tablet_runtime_v300.py", '            "card_identity_recognition.js",\n            "grade_market_flow.js",', '            "card_identity_recognition.js",\n            "card_metadata_classifier_v328.js",\n            "grade_market_flow.js",')
patch("sw.js", "'./grading_accuracy_v99.js','./card_identity_recognition.js'", "'./grading_accuracy_v99.js','./card_metadata_classifier_v328.js','./card_identity_recognition.js'")
patch("feature_contract.py", '"card_identity_recognition.py", "card_identity_recognition.js", "card_identity_learning.json",', '"card_identity_recognition.py", "card_identity_recognition.js", "card_metadata_classifier_v328.js", "card_identity_learning.json",')
patch("feature_contract.py", '"card_identity_recognition.js", "tcgRecognizeCurrentCard"))', '"card_identity_recognition.js", "card_metadata_classifier_v328.js", "tcgRecognizeCurrentCard"))')
patch(".github/workflows/runtime-delivery-guard.yml", "      - 'card_identity_recognition.js'\n", "      - 'card_identity_recognition.js'\n      - 'card_metadata_classifier_v328.js'\n")
patch(".github/workflows/runtime-delivery-guard.yml", '          node --check card_identity_recognition.js\n', '          node --check card_identity_recognition.js\n          node --check card_metadata_classifier_v328.js\n          node verify_card_metadata_classifier_v328.js\n')
patch("verify_current_runtime.py", '                 ("browser_runtime",["node","verify_browser_runtime.js"],180,False),', '                 ("card_metadata_classifier_v328",["node","verify_card_metadata_classifier_v328.js"],60,False),\n                 ("browser_runtime",["node","verify_browser_runtime.js"],180,False),')

# Browser-runtime XSS probe now exercises the real fail-closed metadata module.
patch(
    "verify_browser_runtime.js",
    "function loadOneLine(name, asynchronous = false) {",
    "context.window = context;\nvm.runInContext(fs.readFileSync(path.join(__dirname, 'card_metadata_classifier_v328.js'), 'utf8'), context, { filename: 'card_metadata_classifier_v328.js' });\n\nfunction loadOneLine(name, asynchronous = false) {",
)
old_probe = '''  element("quickCardQuery").value = "pokemon";\n  context.fetch = async () => ({ json: async () => ({ entries: { [`pokemon-${attack}`]: { detail: attack } } }) });\n  await context.quickPrice();'''
new_probe = '''  element("quickCardQuery").value = "pokemon";\n  element("identityRegion").value = "KR";\n  element("identityCardName").value = "pokemon";\n  element("identityCardNumber").value = "SV1S001/078";\n  context.fetch = async () => ({ json: async () => ({ entries: { [`KR|pokemon-${attack}|HIT`]: { game: "Pokémon", card_name: `pokemon ${attack}`, card_number: "SV1S001/078", variant: "base", condition: "raw", detail: attack } } }) });\n  await context.quickPrice();'''
patch("verify_browser_runtime.js", old_probe, new_probe)
