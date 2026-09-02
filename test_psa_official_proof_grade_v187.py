#!/usr/bin/env python3
import manual_official_proof as proof


def main() -> None:
    text = "PSA CERTIFICATION 94320987 2021 POKEMON JAPANESE XERNEAS EX GEM MT"
    evidence = {"company": "PSA", "certification_id": "94320987", "grade": None}
    result = proof._match_proof(
        row={}, text=text, evidence=evidence,
        company="PSA", cert="94320987", expected_grade=10.0,
    )
    assert result["matched"] is True, result
    assert result["grade_match"] is True, result
    assert result["contextual_grade_candidates"] == [10.0], result
    assert proof._game_from_official_text(text) == "pokemon"

    wrong_cert = proof._match_proof(
        row={}, text="PSA CERTIFICATION 11111111 GEM MT", evidence={"company": "PSA", "certification_id": "11111111", "grade": None},
        company="PSA", cert="94320987", expected_grade=10.0,
    )
    assert wrong_cert["matched"] is False, wrong_cert
    assert "certification_id" in wrong_cert["missing"], wrong_cert
    assert wrong_cert["contextual_grade_candidates"] == [], wrong_cert

    explicit_wrong_grade = proof._match_proof(
        row={}, text="PSA CERTIFICATION 94320987 GRADE 9 GEM MT", evidence={"company": "PSA", "certification_id": "94320987", "grade": None},
        company="PSA", cert="94320987", expected_grade=10.0,
    )
    assert explicit_wrong_grade["matched"] is False, explicit_wrong_grade
    assert "official_proof_grade_mismatch" in explicit_wrong_grade["conflicts"], explicit_wrong_grade
    assert explicit_wrong_grade["contextual_grade_candidates"] == [], explicit_wrong_grade

    assert proof._game_from_official_text("2024 ONE PIECE CARD GAME") == "onepiece"
    assert proof._game_from_official_text("NARUTO CARD") == "naruto"
    assert proof._game_from_official_text("UNRELATED CARD") == ""
    print("[OK] PSA official proof grade fallback v187")


if __name__ == "__main__":
    main()
