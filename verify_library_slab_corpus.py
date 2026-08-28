#!/usr/bin/env python3
"""Regression checks for the quarantine-first Library slab importer."""
from library_slab_corpus import detect_company, normalize_cert, normalize_grade, load_registry, load_reviewed_overrides
from pathlib import Path


def main() -> None:
    assert detect_company("PSA GEM MT 10 88411675") == "PSA"
    assert detect_company("Certified Guaranty CGC 9.5") == "CGC"
    assert detect_company("BECKETT PRISTINE 10") == "BGS"
    assert detect_company("TAG Technical Authentication") == "TAG"
    assert detect_company("BRG 0390653") == "BRG"
    assert detect_company("Pokemon TAG ALL STARS Bbrg break & company") == "BRG"
    assert detect_company("MIMIKYU GEM MT 88411674 barcode 88411674") == "PSA"
    assert normalize_cert("PSA", "2023 SV4A 88411675") == "88411675"
    assert normalize_cert("BRG", "BRG 0390653") == "0390653"
    assert normalize_grade("GEM MT 10") == 10.0
    assert normalize_grade("NM-MT 8") == 8.0
    registry = load_registry(Path(__file__).with_name("library_official_cert_registry.json"))
    assert registry[("PSA", "88411675")]["grade"] == 10
    assert all(row["officially_verified"] is True for row in registry.values())
    overrides = load_reviewed_overrides(Path(__file__).with_name("library_slab_reviewed_overrides.json"))
    assert overrides["IMG_6591.jpeg"] == "TAG"
    print("library slab corpus: 16 checks passed")


if __name__ == "__main__":
    main()
