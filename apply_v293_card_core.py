from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
V292_REF = "origin/audit/card-core-crosscheck-v292"
PORT_FILES = (
    "card_grading_valuation.py",
    "collection_verification_gate.py",
    "feature_contract.py",
    "grading_probability_v292.js",
    "index.html",
    "sw.js",
    "tablet_runtime_manifest.py",
    "tcg_updater.py",
    "test_card_core_crosscheck_v292.py",
    "test_tablet_app_dock_v275.py",
    "test_ui_version_coherence_v276.py",
    "ui_app_shell_v272.js",
    "update_market_prices.py",
)


def show(ref: str, path: str) -> str:
    proc = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True,
                          capture_output=True, check=True, timeout=30)
    return proc.stdout


def replace_exact(path: Path, old: str, new: str, *, count: int | None = None) -> None:
    text = path.read_text(encoding="utf-8")
    actual = text.count(old)
    if count is not None and actual != count:
        raise SystemExit(f"{path.name}: expected {count} occurrences, found {actual}: {old[:80]!r}")
    if actual == 0:
        raise SystemExit(f"{path.name}: missing patch anchor: {old[:100]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


for name in PORT_FILES:
    (ROOT / name).write_text(show(V292_REF, name), encoding="utf-8")

(ROOT / "market_period_filter_v293.js").write_text(r'''(function(root,factory){
'use strict';
const api=factory();
if(typeof module!=='undefined'&&module.exports)module.exports=api;
if(root)root.TCGMarketPeriodV293=api;
})(typeof window!=='undefined'?window:(typeof globalThis!=='undefined'?globalThis:null),function(){
'use strict';
const VERSION='v293-observation-window';
function periodDays(value){
 const match=String(value??'').match(/(?:최근\s*)?(7|30|90)\s*일/);
 return match?Number(match[1]):null;
}
function observedMillis(value){
 const text=String(value??'').trim();
 if(!text)return null;
 let millis;
 if(/^\d{4}-\d{2}-\d{2}$/.test(text))millis=Date.parse(text+'T00:00:00Z');
 else millis=Date.parse(text);
 return Number.isFinite(millis)?millis:null;
}
function withinPeriod(observed,period,now=Date.now()){
 const days=periodDays(period),stamp=observedMillis(observed),current=Number(now);
 if(days===null||stamp===null||!Number.isFinite(current))return false;
 const age=current-stamp;
 if(age < -24*60*60*1000)return false;
 return age <= days*24*60*60*1000;
}
return Object.freeze({VERSION,periodDays,observedMillis,withinPeriod});
});
''', encoding="utf-8")

index = ROOT / "index.html"
replace_exact(index,
    '<script src="./grading_probability_v292.js?v=292"></script>',
    '<script src="./grading_probability_v292.js?v=292"></script>\n<script src="./market_period_filter_v293.js?v=293"></script>', count=1)
replace_exact(index,
    ' if(gameFilter!=="ALL"&&game!==gameFilter)continue;\n const cardName=',
    ' if(gameFilter!=="ALL"&&game!==gameFilter)continue;\n'
    ' const observedAt=value.source_date||value.observed_on||value.checked_at||w.price_checked_at||w.checked_at||"";\n'
    ' if(!window.TCGMarketPeriodV293||!TCGMarketPeriodV293.withinPeriod(observedAt,period,Date.now()))continue;\n'
    ' const cardName=', count=1)
text = index.read_text(encoding="utf-8").replace('현재 거래시세<b>', '현재 시장가격<b>')
index.write_text(text, encoding="utf-8")

identity = ROOT / "card_identity_recognition.js"
replace_exact(identity,
    "function yearFromEvidence(input,text){\n const direct=Number(input?.year||input?.copyright_year||0);\n if(Number.isInteger(direct)&&direct>=1996&&direct<=2099)return direct;\n const t=generationText(text),years=[];\n for(const match of t.matchAll(/(?:©|COPYRIGHT\\s*)?\\s*((?:19|20)\\d{2})/g)){\n  const year=Number(match[1]);if(year>=1996&&year<=2099)years.push(year);\n }\n return years.length?Math.max(...years):null;\n}",
    "function yearFromEvidence(input,text){\n const maxYear=new Date().getUTCFullYear()+1;\n const direct=Number(input?.year||input?.copyright_year||0);\n if(Number.isInteger(direct)&&direct>=1996&&direct<=maxYear)return direct;\n const t=generationText(text),years=[];\n for(const match of t.matchAll(/(?:©|COPYRIGHT\\s*)?\\s*((?:19|20)\\d{2})/g)){\n  const year=Number(match[1]);if(year>=1996&&year<=maxYear)years.push(year);\n }\n return years.length?Math.max(...years):null;\n}", count=1)
replace_exact(identity,
    " if(['JP','JAPAN','JAPANESE','日本','日版'].includes(r))return 'JP';\n if(['US','USA','EN','ENGLISH'].includes(r))return 'US';\n if(['KR','KOREA','KOREAN','한국','한국판'].includes(r))return 'KR';",
    " if(['JP','JPN','JA','JAPAN','JAPANESE','日本','日本版','日版','JP版'].includes(r))return 'JP';\n if(['US','USA','EN','ENG','ENGLISH'].includes(r))return 'US';\n if(['KR','KOR','KO','KOREA','KOREAN','한국','한국판'].includes(r))return 'KR';", count=1)

shell = ROOT / "ui_app_shell_v272.js"
replace_exact(shell, 'probabilityTitle.textContent = "PSA 예상확률(휴리스틱)";',
              'probabilityTitle.textContent = "PSA 8/9/10 휴리스틱 분포";', count=1)

replace_exact(ROOT / "feature_contract.py", '"grading_probability_v292.js", "verify_vision_runtime.js",',
              '"grading_probability_v292.js", "market_period_filter_v293.js", "verify_vision_runtime.js",', count=1)
replace_exact(ROOT / "tablet_runtime_manifest.py", '"grading_probability_v292.js","card_identity_recognition.js",',
              '"grading_probability_v292.js","market_period_filter_v293.js","card_identity_recognition.js",', count=1)
replace_exact(ROOT / "tcg_updater.py", "'grading_probability_v292.js','card_identity_recognition.js'",
              "'grading_probability_v292.js','market_period_filter_v293.js','card_identity_recognition.js'", count=1)

worker = ROOT / "sw.js"
wtext = worker.read_text(encoding="utf-8")
if "tcg-v292-network-first-runtime" not in wtext:
    raise SystemExit("sw.js: expected finalized v292 cache token")
wtext = wtext.replace("tcg-v292-network-first-runtime", "tcg-v293-card-core-runtime")
wtext = wtext.replace("'./grading_probability_v292.js','./card_identity_recognition.js'",
                      "'./grading_probability_v292.js','./market_period_filter_v293.js','./card_identity_recognition.js'")
worker.write_text(wtext, encoding="utf-8")

for test_name in ("test_card_core_crosscheck_v292.py", "test_tablet_app_dock_v275.py", "test_ui_version_coherence_v276.py"):
    path = ROOT / test_name
    t = path.read_text(encoding="utf-8")
    t = t.replace("tcg-v292-network-first-runtime", "tcg-v293-card-core-runtime")
    t = t.replace("PSA 예상확률(휴리스틱)", "PSA 8/9/10 휴리스틱 분포")
    path.write_text(t, encoding="utf-8")

market_path = ROOT / "market_prices.json"
db = json.loads(market_path.read_text(encoding="utf-8"))
profiles = db.setdefault("graded_prices", {})
seed_evidence = {
    "JP|계승되는 의지 일본판 에이스 만화패러렐|HIT": {
        "PSA": {"10": {"source": "https://kream.co.kr/products/911415", "price_type": "sold",
                         "observed_on": "2026-09-22", "label": "PSA 10 공개 체결가 범위 중앙값 · 페이지 확인일"}}
    },
    "KR|릴리에 SM1M 065/060|HIT": {
        "BRG": {
            "9": {"source": "https://break.co.kr/", "price_type": "official_example", "observed_period": "2025-05",
                  "label": "BRG 공식 페이지 특정 카드 거래 예시"},
            "10": {"source": "https://break.co.kr/", "price_type": "official_example", "observed_period": "2025-05",
                   "label": "BRG 공식 페이지 특정 카드 거래 예시"},
        }
    },
}
for key, evidence in seed_evidence.items():
    if key not in profiles or not isinstance(profiles[key], dict):
        raise SystemExit(f"market_prices.json: missing expected graded profile {key}")
    profiles[key]["grade_price_evidence"] = evidence
market_path.write_text(json.dumps(db, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

(ROOT / "test_card_core_crosscheck_v293.py").write_text(r'''from __future__ import annotations
import json
from pathlib import Path
import subprocess
import unittest
import tablet_runtime_manifest
import tcg_updater
ROOT = Path(__file__).resolve().parent
class CardCoreCrosscheckV293Tests(unittest.TestCase):
    def node_json(self, script: str):
        p=subprocess.run(["node","-e",script],cwd=ROOT,text=True,capture_output=True,check=True,timeout=30)
        return json.loads(p.stdout)
    def test_market_period_filter_enforces_7_30_90_day_windows(self):
        out=self.node_json(r"""const p=require('./market_period_filter_v293.js');const now=Date.parse('2026-09-23T00:00:00Z');process.stdout.write(JSON.stringify({d7inside:p.withinPeriod('2026-09-16','최근 7일',now),d7outside:p.withinPeriod('2026-09-15','최근 7일',now),d30inside:p.withinPeriod('2026-08-24','최근 30일',now),d30outside:p.withinPeriod('2026-08-23','최근 30일',now),d90inside:p.withinPeriod('2026-06-25','최근 90일',now),missing:p.withinPeriod('','최근 7일',now),invalid:p.withinPeriod('bad','최근 30일',now),future:p.withinPeriod('2026-09-25','최근 90일',now),days:[p.periodDays('최근 7일'),p.periodDays('최근 30일'),p.periodDays('최근 90일')]}));""")
        self.assertEqual([7,30,90],out['days']); self.assertTrue(out['d7inside']); self.assertFalse(out['d7outside']); self.assertTrue(out['d30inside']); self.assertFalse(out['d30outside']); self.assertTrue(out['d90inside']); self.assertFalse(out['missing']); self.assertFalse(out['invalid']); self.assertFalse(out['future'])
    def test_price_ui_uses_period_filter_and_market_price_semantics(self):
        page=(ROOT/'index.html').read_text(encoding='utf-8'); self.assertIn('market_period_filter_v293.js?v=293',page); self.assertIn('TCGMarketPeriodV293.withinPeriod(observedAt,period,Date.now())',page); self.assertIn('현재 시장가격<b>',page); self.assertNotIn('현재 거래시세<b>',page)
    def test_generation_aliases_work_and_far_future_ocr_year_fails_closed(self):
        out=self.node_json(r"""const fs=require('fs'),vm=require('vm');global.window={};global.document={readyState:'loading',addEventListener(){},getElementById(){return null;}};global.localStorage={getItem(){return null;},setItem(){}};global.Option=function(){};vm.runInThisContext(fs.readFileSync('card_identity_recognition.js','utf8'));const a=global.window.TCGPokemonGeneration;process.stdout.write(JSON.stringify({jpn:a.infer({game:'pokemon',region:'JPN',ocr_text:'©2019 Pokémon'}),kor:a.infer({game:'pokemon',region:'KOR',ocr_text:'©2020 Pokémon'}),eng:a.infer({game:'pokemon',region:'ENG',ocr_text:'©2020 Pokémon'}),future:a.infer({game:'pokemon',region:'JP',ocr_text:'©2099 Pokémon'})}));""")
        self.assertEqual(8,out['jpn']['generation']); self.assertEqual(8,out['kor']['generation']); self.assertEqual(8,out['eng']['generation']); self.assertEqual('unknown',out['future']['status']); self.assertIsNone(out['future']['generation'])
    def test_probability_ui_is_explicitly_non_calibrated(self):
        page=(ROOT/'index.html').read_text(encoding='utf-8'); shell=(ROOT/'ui_app_shell_v272.js').read_text(encoding='utf-8'); server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8'); self.assertIn('window.tcgGradeProbabilityMeta',page); self.assertIn('calibrated:false',page); self.assertIn('PSA 8/9/10 휴리스틱 분포',shell); self.assertIn("'probability_claim':False",server)
    def test_v293_assets_are_fail_closed_tablet_runtime_dependencies(self):
        self.assertIn('grading_probability_v292.js',tablet_runtime_manifest.ACTIVE_RUNTIME_FILES); self.assertIn('market_period_filter_v293.js',tablet_runtime_manifest.ACTIVE_RUNTIME_FILES); self.assertIn('market_period_filter_v293.js',tcg_updater.PUBLIC_STATIC_FILES); worker=(ROOT/'sw.js').read_text(encoding='utf-8'); self.assertIn("const CACHE='tcg-v293-card-core-runtime';",worker); self.assertIn("'./market_period_filter_v293.js'",worker)
if __name__=='__main__': unittest.main(verbosity=2)
''', encoding="utf-8")
print("v293 card-core port + hardening applied")
