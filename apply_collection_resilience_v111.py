#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"patch anchor missing: {label}")
    return text.replace(old, new, 1)


def patch_releases() -> None:
    path = ROOT / "update_releases.py"
    text = path.read_text(encoding="utf-8")

    onepiece_helper = r'''
def _parse_onepiece_jp_segmented(text: str, url: str) -> list[dict]:
    """Parse current/future JP product cards without depending on one DOM text order.

    Official pages have changed spacing, punctuation and label order several times.
    Anchor on the stable product code, then read only a bounded neighborhood for
    発売日 and the manufacturer price. This is a conservative third parser: a row
    is emitted only when code + date/month + JPY price are all present together.
    """
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    found = []
    seen = set()
    code_re = re.compile(r"\b(OP-\d+|EB-\d+|PRB-\d+)\b", re.I)
    date_re = re.compile(
        r"発売日.{0,90}?(20\d{2})\s*(?:[./年-])\s*(\d{1,2})"
        r"(?:\s*(?:[./月-])\s*(\d{1,2})\s*日?)?",
        re.I,
    )
    price_re = re.compile(r"(?:メーカー希望小売価格|希望小売価格|価格).{0,100}?([0-9][0-9,]{1,7})\s*円", re.I)
    product_words = re.compile(r"(?:ブースターパック|エクストラブースター|プレミアムブースター|ブースター)", re.I)
    for match in code_re.finditer(normalized):
        code = match.group(1).upper()
        left = max(0, match.start() - 180)
        right = min(len(normalized), match.end() + 520)
        segment = normalized[left:right]
        dm = date_re.search(segment)
        pm = price_re.search(segment)
        if not dm or not pm:
            continue
        y, m, d = dm.groups()
        try:
            year, month = int(y), int(m)
            day = int(d) if d else None
            price = int(pm.group(1).replace(",", ""))
            if not (1 <= month <= 12 and 1 <= price <= 1_000_000):
                continue
            if day is not None:
                dt.date(year, month, day)
        except (TypeError, ValueError):
            continue
        before = normalized[max(left, match.start() - 150):match.start()]
        words = list(product_words.finditer(before))
        title_start = words[-1].start() if words else max(0, len(before) - 100)
        title = re.sub(r"\s+", " ", before[title_start:]).strip(" -|:：/・")
        title = product_words.sub("", title, count=1).strip(" -|:：/・")
        if len(title) < 2:
            title = f"ONE PIECE {code}"
        key = (code, year, month, day, price)
        if key in seen:
            continue
        seen.add(key)
        row = {"game": "ONE PIECE", "region": "JP", "name": f"{title} [{code}]",
               "price": f"¥{price:,}/팩", "status": "공식 확인", "source": url,
               "parser": "segmented-code-date-price-v111"}
        if day is None:
            row.update({"release_date": None, "release_window": f"{year:04d}-{month:02d}",
                        "release_precision": "month", "release_label": f"{year:04d}년 {month}월"})
        else:
            row["release_date"] = dt.date(year, month, day).isoformat()
        found.append(row)
    return found

'''
    text = replace_once(
        text,
        "\ndef collect_onepiece_jp() -> list[dict]:\n",
        "\n" + onepiece_helper + "def collect_onepiece_jp() -> list[dict]:\n",
        "onepiece segmented parser",
    )
    old = "text = html_to_text(fetch(url)); found = _parse_onepiece_jp(text, url) or _parse_onepiece_jp_fallback(text, url)"
    new = "text = html_to_text(fetch(url)); found = (_parse_onepiece_jp(text, url) or _parse_onepiece_jp_fallback(text, url) or _parse_onepiece_jp_segmented(text, url))"
    text = replace_once(text, old, new, "onepiece parser chain")

    pokemon_helper = r'''
def _parse_pokemon_jp_segmented(text: str, url: str) -> list[dict]:
    """Conservative JP Pokémon parser resilient to whitespace/label-order drift."""
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    product_re = re.compile(r"(?:強化拡張パック|拡張パック|ハイクラスパック|コンセプトパック)", re.I)
    date_re = re.compile(
        r"(?:販売日|発売日).{0,90}?(20\d{2})\s*(?:年|[./-])\s*(\d{1,2})\s*(?:月|[./-])\s*(\d{1,2})\s*日?",
        re.I,
    )
    price_re = re.compile(r"(?:希望小売価格|メーカー希望小売価格|価格).{0,100}?([0-9][0-9,]{1,7})\s*円", re.I)
    found = []
    seen = set()
    for product in product_re.finditer(normalized):
        left = max(0, product.start() - 20)
        right = min(len(normalized), product.end() + 620)
        segment = normalized[left:right]
        dm = date_re.search(segment)
        pm = price_re.search(segment)
        if not dm or not pm:
            continue
        try:
            y, m, d = (int(value) for value in dm.groups())
            date = dt.date(y, m, d).isoformat()
            price = int(pm.group(1).replace(",", ""))
            if not (1 <= price <= 1_000_000):
                continue
        except (TypeError, ValueError):
            continue
        after = normalized[product.end():min(len(normalized), product.end() + 170)]
        quoted = re.search(r"[「『]\s*([^」』]{2,90})\s*[」』]", after)
        if quoted:
            name = re.sub(r"\s+", " ", quoted.group(1)).strip()
        else:
            stop = re.search(r"(?:販売日|発売日|希望小売価格|メーカー希望小売価格)", after)
            name = (after[:stop.start()] if stop else after[:100]).strip(" -|:：/・")
            name = re.sub(r"\s+", " ", name)
        if len(name) < 2:
            continue
        key = (name.casefold(), date, price)
        if key in seen:
            continue
        seen.add(key)
        found.append({"game": "Pokémon", "region": "JP", "name": name,
                      "release_date": date, "price": f"¥{price:,}/팩", "status": "공식 확인",
                      "source": url, "parser": "segmented-label-date-price-v111"})
    return found

'''
    text = replace_once(
        text,
        "\ndef collect_pokemon_jp() -> list[dict]:\n",
        "\n" + pokemon_helper + "def collect_pokemon_jp() -> list[dict]:\n",
        "pokemon segmented parser",
    )
    old = "text = html_to_text(fetch(url)); found = _parse_pokemon_jp(text, url) or _parse_pokemon_jp_fallback(text, url)"
    new = "text = html_to_text(fetch(url)); found = (_parse_pokemon_jp(text, url) or _parse_pokemon_jp_fallback(text, url) or _parse_pokemon_jp_segmented(text, url))"
    text = replace_once(text, old, new, "pokemon parser chain")
    path.write_text(text, encoding="utf-8")


def patch_graded_photo() -> None:
    path = ROOT / "graded_photo_multi_source.py"
    text = path.read_text(encoding="utf-8")
    old = "REFERENCE_LEARNING=ROOT/'graded_photo_reference_learning.json'\nLIBRARY_OFFICIAL=ROOT/'library_official_cert_registry.json'"
    new = "REFERENCE_LEARNING=ROOT/'graded_photo_reference_learning.json'\nBASELINE_VERIFIED=ROOT/'graded_photo_verified_seed_baseline.json'\nLAST_GOOD_CANDIDATES=ROOT/'.graded_photo_candidates.last_good.json'\nLIBRARY_OFFICIAL=ROOT/'library_official_cert_registry.json'"
    text = replace_once(text, old, new, "graded photo constants")

    text = replace_once(
        text,
        "for path in (VERIFIED,LIBRARY_OFFICIAL):\n  d=_load(path,{})",
        "for path in (VERIFIED,LIBRARY_OFFICIAL,BASELINE_VERIFIED):\n  d=_load(path,{})",
        "registry baseline",
    )
    text = replace_once(
        text,
        "for path in (VERIFIED,LIBRARY_OFFICIAL):\n  data=_load(path,{})",
        "for path in (VERIFIED,LIBRARY_OFFICIAL,BASELINE_VERIFIED):\n  data=_load(path,{})",
        "seed baseline",
    )

    reference_seed_helper = r'''
def _reference_learning_seed_rows()->list[dict]:
 """Rehydrate previously verified references if a mutable local registry was reset.

 The reference-learning file contains only rows that passed official verification;
 it is never used to promote an unverified marketplace label. This prevents a
 successful zero-result public search from erasing the last trustworthy candidate.
 """
 data=_load(REFERENCE_LEARNING,{})
 values=data.get('references',[]) if isinstance(data,dict) else []
 rows=[];seen=set()
 for item in values if isinstance(values,list) else []:
  if not isinstance(item,dict) or item.get('learning_scope')!='slab_label_and_source_reference_only':continue
  company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id'))
  try:grade=float(item.get('official_grade'))
  except (TypeError,ValueError,OverflowError):continue
  if company not in COMPANIES or not cert or not 1<=grade<=10 or (company,cert) in seen:continue
  seen.add((company,cert));official=str(item.get('official_reference_url') or lookup_url(company,cert))
  image_url=str(item.get('measurement_image_url') or '')[:1200]
  rows.append({'source_id':'reference_learning','source':f'{company} 이전 공식검증 참조','search_provider':'reference_learning',
               'url':official,'title':str(item.get('card_name') or f'{company} cert {cert}')[:260],'snippet':'',
               'image_url':image_url if image_url.startswith('https://') else '','company':company,'grade':grade,
               'certification_id':cert,'game':str(item.get('game') or 'unknown').lower(),'mode':'slab','source_weight':0.99,
               'official_result':True,'official_grade':grade,'official_reference_url':official,
               'verification_method':'persisted_reference_learning','status':'verified_reference',
               'learning_eligibility':'reference_learning_only','image_sha256':str(item.get('image_sha256') or '')[:64],
               'image_perceptual_hash':str(item.get('image_perceptual_hash') or '')[:32],
               'image_validated':bool(item.get('image_sha256')),'image_probe_status':'validated' if item.get('image_sha256') else 'not_available',
               'ocr_label_text':'','image_evidence_source':'persisted_verified_reference'})
 return rows

'''
    text = replace_once(
        text,
        "\ndef _library_candidate_seed_rows()->list[dict]:\n",
        "\n" + reference_seed_helper + "def _library_candidate_seed_rows()->list[dict]:\n",
        "reference seed helper",
    )

    old = "previous_payload=_load(OUT,{})\n previous_rows=previous_payload.get('records',[]) if isinstance(previous_payload,dict) else []\n if not isinstance(previous_rows,list):previous_rows=[]\n previous_rows=[dict(x) for x in previous_rows if isinstance(x,dict)]\n seeds=_registry_seed_rows();library_seeds=_library_candidate_seed_rows();rows=previous_rows+seeds+library_seeds;previous_count=len(previous_rows)"
    new = "previous_payload=_load(OUT,{})\n previous_rows=previous_payload.get('records',[]) if isinstance(previous_payload,dict) else []\n if not isinstance(previous_rows,list):previous_rows=[]\n previous_rows=[dict(x) for x in previous_rows if isinstance(x,dict)]\n if not previous_rows:\n  last_good=_load(LAST_GOOD_CANDIDATES,{})\n  fallback_rows=last_good.get('records',[]) if isinstance(last_good,dict) else []\n  if isinstance(fallback_rows,list):previous_rows=[dict(x) for x in fallback_rows if isinstance(x,dict)]\n seeds=_registry_seed_rows();reference_seeds=_reference_learning_seed_rows();library_seeds=_library_candidate_seed_rows();rows=previous_rows+seeds+reference_seeds+library_seeds;previous_count=len(previous_rows)"
    text = replace_once(text, old, new, "last-good and reference seeds")

    old = "'previous_candidates':previous_count,'registry_seed_count':len(seeds),\n                     'library_candidate_seed_count':len(library_seeds),"
    new = "'previous_candidates':previous_count,'registry_seed_count':len(seeds),\n                     'reference_learning_seed_count':len(reference_seeds),\n                     'baseline_verified_seed_count':sum(1 for x in seeds if str(x.get('source_id'))=='official_registry'),\n                     'library_candidate_seed_count':len(library_seeds),"
    text = replace_once(text, old, new, "summary seed counts")

    old = "atomic_write_json(LEARNING,learning_state,suffix='.graded-photo-adaptive.tmp')\n atomic_write_json(OUT,payload,suffix='.graded-photo.tmp');_save_learning(stats);return payload"
    new = "atomic_write_json(LEARNING,learning_state,suffix='.graded-photo-adaptive.tmp')\n if rows:\n  atomic_write_json(LAST_GOOD_CANDIDATES,payload,suffix='.graded-photo-last-good.tmp')\n atomic_write_json(OUT,payload,suffix='.graded-photo.tmp');_save_learning(stats);return payload"
    text = replace_once(text, old, new, "last-good snapshot save")
    path.write_text(text, encoding="utf-8")

    baseline = {
        "version": 1,
        "certifications": [
            {
                "company": "PSA",
                "certification_id": "88411675",
                "grade": 10,
                "verified": True,
                "official_reference_url": "https://www.psacard.com/cert/88411675/psa",
                "card_name": "2023 Pokemon Japanese SV4a Shiny Treasure ex #323 Espathra ex SSR",
                "game": "pokemon",
                "source": "immutable verified bootstrap copied from project verified registry"
            }
        ],
        "policy": "Known official-verified bootstrap only. Never add marketplace labels without official certification verification."
    }
    (ROOT / "graded_photo_verified_seed_baseline.json").write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    patch_releases()
    patch_graded_photo()
    print("collection resilience v111 patch applied")


if __name__ == "__main__":
    main()
