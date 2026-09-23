from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        if new in text:
            return
        raise SystemExit(f"expected patch target missing: {path.name}")
    if count != 1:
        raise SystemExit(f"expected one patch target in {path.name}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    ROOT / "index.html",
    "let p9only=Math.max(1,p9-p10),p8=Math.max(1,Math.min(60,(100-p9)*.65)),below=Math.max(0,100-p10-p9only-p8);\n window.tcgGradeProbabilities={8:p8,9:p9only,10:p10,below};",
    "const psaDist=window.TCGAccuracyV99?.normalizePsaProbabilities?window.TCGAccuracyV99.normalizePsaProbabilities(p10,p9):{10:Math.max(0,Math.min(100,p10)),9:0,8:0,below:100,psa9plus:Math.max(0,Math.min(100,p9))};\n p10=psaDist[10];p9=psaDist.psa9plus;const p9only=psaDist[9],p8=psaDist[8],below=psaDist.below;\n window.tcgGradeProbabilities={8:p8,9:p9only,10:p10,below};",
)

replace_once(
    ROOT / "grade_market_flow.js",
    "const wanted=editionCode(region),actual=String(row.card_region||'UNKNOWN').toUpperCase();\n if(wanted!=='UNKNOWN'&&actual===wanted)score+=20;\n else if(wanted!=='UNKNOWN'&&actual!=='UNKNOWN'&&actual!==wanted)score-=40;",
    "const wanted=editionCode(region),actual=editionCode(row.card_region||'UNKNOWN');\n if(wanted!=='UNKNOWN'&&actual===wanted)score+=20;\n else if(wanted!=='UNKNOWN'&&actual!=='UNKNOWN'&&actual!==wanted)return -999;",
)

print("v295 bounded card-core patch applied")
