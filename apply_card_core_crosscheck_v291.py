#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "grading_accuracy_v99.js",
    "  const finite=x=>Number.isFinite(Number(x));\n",
    """  const finite=x=>{\n    if(x===null||x===undefined||typeof x==='boolean')return false;\n    if(typeof x==='string'&&!x.trim())return false;\n    return Number.isFinite(Number(x));\n  };\n""",
)
replace_once(
    "grading_accuracy_v99.js",
    """  function combineDefectRisk(surface,edge,corner){\n    const values=[surface,Number(edge)*0.90,Number(corner)*0.95].filter(finite).map(Number);\n    return values.length?clamp(Math.max(...values),0,100):100;\n  }\n""",
    """  function combineDefectRisk(surface,edge,corner){\n    const inputs=[[surface,1.0],[edge,0.90],[corner,0.95]];\n    if(!inputs.every(([value])=>finite(value)))return 100;\n    return clamp(Math.max(...inputs.map(([value,weight])=>Number(value)*weight)),0,100);\n  }\n""",
)

replace_once(
    "grading_accuracy_v99.py",
    """def finite(v:Any)->float|None:\n try:x=float(v)\n except (TypeError,ValueError,OverflowError):return None\n return x if math.isfinite(x) else None\n""",
    """def finite(v:Any)->float|None:\n if v is None or isinstance(v,bool) or (isinstance(v,str) and not v.strip()):return None\n try:x=float(v)\n except (TypeError,ValueError,OverflowError):return None\n return x if math.isfinite(x) else None\n""",
)
replace_once(
    "grading_accuracy_v99.py",
    """def combine_defect_risk(surface:float,edge:float,corner:float)->float:\n values=[]\n for value,weight in ((surface,1.0),(edge,.90),(corner,.95)):\n  x=finite(value)\n  if x is not None:values.append(x*weight)\n return clamp(max(values) if values else 100,0,100)\n""",
    """def combine_defect_risk(surface:float,edge:float,corner:float)->float:\n values=[]\n for value,weight in ((surface,1.0),(edge,.90),(corner,.95)):\n  x=finite(value)\n  if x is None:return 100\n  values.append(x*weight)\n return clamp(max(values),0,100)\n""",
)

replace_once(
    "card_grading_valuation.py",
    """def estimate_grades(values: Mapping[str, Any]) -> dict[str, Any]:\n    \"\"\"Estimate five grades conservatively using published information only.\"\"\"\n    card = GradeInputs.from_mapping(values)\n""",
    """def estimate_grades(values: Mapping[str, Any]) -> dict[str, Any]:\n    \"\"\"Estimate five grades conservatively using published information only.\"\"\"\n    if not isinstance(values, Mapping):\n        return {\"ok\": False, \"status\": \"FAILED\", \"reason\": \"카드 분석자료 형식 오류\", \"grades\": {}}\n    required = (\"centering_front\", \"centering_back\", \"corners\", \"edges\", \"surface\", \"micro_flaws\", \"is_authentic\")\n    missing = [name for name in required if name not in values or values.get(name) is None]\n    if missing:\n        return {\"ok\": False, \"status\": \"FAILED\", \"reason\": \"카드 분석자료 부족: \" + \", \".join(missing), \"grades\": {}}\n    card = GradeInputs.from_mapping(values)\n""",
)

old_year = """function generationByYear(year){\n if(year>=2023)return {generation:9,generation_label:'9세대',series:'SV/MEGA 시대',era:'CURRENT'};\n if(year>=2020)return {generation:8,generation_label:'8세대',series:'소드&실드 시대',era:'S'};\n if(year>=2017)return {generation:7,generation_label:'7세대',series:'썬&문 시대',era:'SM'};\n if(year>=2014)return {generation:6,generation_label:'6세대',series:'XY 시대',era:'XY'};\n if(year>=2011)return {generation:5,generation_label:'5세대',series:'BW 시대',era:'BW'};\n if(year>=2007)return {generation:4,generation_label:'4세대',series:'DP/DPt 시대',era:'DP'};\n return null;\n}\n"""
new_year = """function generationRegion(value){\n const r=generationText(value).replace(/\\s+/g,'');\n if(['JP','JAPAN','JAPANESE','日本','日版'].includes(r))return 'JP';\n if(['US','USA','EN','ENGLISH'].includes(r))return 'US';\n if(['KR','KOREA','KOREAN','한국','한국판'].includes(r))return 'KR';\n return 'UNKNOWN';\n}\nfunction generationByYear(year,region){\n if(!Number.isInteger(year))return null;\n if(generationRegion(region)==='JP'){\n  if(year>=2023)return {generation:9,generation_label:'9세대',series:'SV/MEGA 시대',era:'CURRENT'};\n  if(year>=2019)return {generation:8,generation_label:'8세대',series:'소드&실드 시대',era:'S'};\n  if(year>=2016)return {generation:7,generation_label:'7세대',series:'썬&문 시대',era:'SM'};\n  if(year>=2013)return {generation:6,generation_label:'6세대',series:'XY 시대',era:'XY'};\n  if(year>=2010)return {generation:5,generation_label:'5세대',series:'BW 시대',era:'BW'};\n  if(year>=2006)return {generation:4,generation_label:'4세대',series:'DP/DPt 시대',era:'DP'};\n  return null;\n }\n if(year>=2023)return {generation:9,generation_label:'9세대',series:'SV/MEGA 시대',era:'CURRENT'};\n if(year>=2020)return {generation:8,generation_label:'8세대',series:'소드&실드 시대',era:'S'};\n if(year>=2017)return {generation:7,generation_label:'7세대',series:'썬&문 시대',era:'SM'};\n if(year>=2014)return {generation:6,generation_label:'6세대',series:'XY 시대',era:'XY'};\n if(year>=2011)return {generation:5,generation_label:'5세대',series:'BW 시대',era:'BW'};\n if(year>=2007)return {generation:4,generation_label:'4세대',series:'DP/DPt 시대',era:'DP'};\n return null;\n}\n"""
replace_once("card_identity_recognition.js", old_year, new_year)
replace_once(
    "card_identity_recognition.js",
    "const year=yearFromEvidence(input,text),byYear=generationByYear(year);",
    "const year=yearFromEvidence(input,text),byYear=generationByYear(year,input?.region);",
)

print("v291 card core patch applied")
