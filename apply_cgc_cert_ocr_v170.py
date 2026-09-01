#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"target not found in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


corpus = Path("library_slab_corpus.py")

replace_once(
    corpus,
    '''            bgs_cert_targeted = False\n            for name, fraction, scale, threshold, psm in passes:\n''',
    '''            bgs_cert_targeted = False\n            cgc_cert_targeted = False\n            for name, fraction, scale, threshold, psm in passes:\n''',
)

old_tail = '''                    combined = " | ".join(texts)\n                    company, cert, grade = _fields_from_text(combined)\n\n                if profile == "adaptive" and company and cert and grade is not None:\n                    break\n'''
new_tail = '''                    combined = " | ".join(texts)\n                    company, cert, grade = _fields_from_text(combined)\n\n                # CGC labels commonly print the certification number as a small\n                # 10+ digit line near the center/bottom of the white top label.\n                # Android/Termux fast OCR can read CGC + GEM MINT 10 while skipping\n                # that serial. Run a digits-only label-band recovery pass only\n                # after CGC identity is already supported and the cert is missing.\n                if not cgc_cert_targeted and cert is None and company == "CGC":\n                    cgc_cert_targeted = True\n                    recovered = None\n                    cgc_regions = (\n                        ("cgc_center_label_digits_psm6", 0.25, 0.05, 0.78, 0.23, 2200, 6, False),\n                        ("cgc_center_label_digits_psm11", 0.34, 0.08, 0.74, 0.22, 2400, 11, True),\n                    )\n                    for pass_name, left, top, right, bottom, target_width, cert_psm, threshold2 in cgc_regions:\n                        cert_crop = _prepare_region_crop(\n                            source, left, top, right, bottom, target_width, threshold2\n                        )\n                        cert_text, cert_error = _run_tesseract(\n                            cert_crop, cert_psm, whitelist="0123456789"\n                        )\n                        used.append(pass_name)\n                        if cert_error:\n                            errors.append(cert_error)\n                        recovered = normalize_cert("CGC", cert_text or "")\n                        if recovered:\n                            texts.append(f"CGC CERT {recovered}")\n                            break\n                    combined = " | ".join(texts)\n                    company, cert, grade = _fields_from_text(combined)\n\n                if profile == "adaptive" and company and cert and grade is not None:\n                    break\n'''
replace_once(corpus, old_tail, new_tail)

# CGC front labels often show the overall grade as standalone "GEM MINT 10".
evidence = Path("graded_photo_evidence.py")
old_grade_fragment = '''    re.compile(r"\\b(10|9\\.5|9|8\\.5|8|7\\.5|7|6\\.5|6|5\\.5|5|4\\.5|4|3\\.5|3|2\\.5|2|1\\.5|1)\\s*(?:PRISTINE|BLACK\\s+LABEL|GEM\\s*(?:MT|MINT)|MINT|NM-MT|NEAR\\s+MINT)\\b", re.I),\n    re.compile(r"(?:등급|그레이드|감정)\\s*(10|9\\.5|9|8\\.5|8|7\\.5|7|6\\.5|6|5\\.5|5|4\\.5|4|3\\.5|3|2\\.5|2|1\\.5|1)", re.I),\n'''
new_grade_fragment = '''    re.compile(r"\\b(10|9\\.5|9|8\\.5|8|7\\.5|7|6\\.5|6|5\\.5|5|4\\.5|4|3\\.5|3|2\\.5|2|1\\.5|1)\\s*(?:PRISTINE|BLACK\\s+LABEL|GEM\\s*(?:MT|MINT)|MINT|NM-MT|NEAR\\s+MINT)\\b", re.I),\n    re.compile(r"\\b(?:GEM\\s*(?:MT|MINT)|PRISTINE|BLACK\\s+LABEL|MINT|NM-MT|NEAR\\s+MINT)\\s*(10|9\\.5|9|8\\.5|8|7\\.5|7|6\\.5|6|5\\.5|5|4\\.5|4|3\\.5|3|2\\.5|2|1\\.5|1)\\b", re.I),\n    re.compile(r"(?:등급|그레이드|감정)\\s*(10|9\\.5|9|8\\.5|8|7\\.5|7|6\\.5|6|5\\.5|5|4\\.5|4|3\\.5|3|2\\.5|2|1\\.5|1)", re.I),\n'''
replace_once(evidence, old_grade_fragment, new_grade_fragment)

print("CGC targeted certificate OCR v170 applied")
