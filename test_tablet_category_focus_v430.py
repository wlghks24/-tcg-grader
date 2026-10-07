#!/usr/bin/env python3
"""V430/V470 guard for compact category focus navigation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JS = (ROOT / "feature_category_nav.js").read_text(encoding="utf-8")
CSS = (ROOT / "feature_category_nav.css").read_text(encoding="utf-8")


def test_details_hidden_until_category_and_feature_are_selected():
    assert "const categoryTargets = new Map();" in JS
    assert "const managedTargets = new Set();" in JS
    assert "const managedSurfaces = new Set();" in JS
    assert "function hideManagedSurfaces()" in JS
    assert "managedSurfaces.forEach((surface) => { surface.hidden = true; });" in JS
    assert "setCategoryContent(null);" in JS


def test_category_opens_menu_only_not_every_long_detail_surface():
    assert 'category.querySelectorAll(".feature-shortcut[href^=\'#\']")' in JS
    assert "function setCategoryContent(category)" in JS
    assert "(categoryTargets.get(category) || new Set()).forEach((target) => { target.hidden = false; });" not in JS
    assert 'document.body.setAttribute("data-feature-category-active"' in JS
    assert "상세화면은 한 번에 하나만 표시됩니다." in JS


def test_one_feature_view_has_back_and_collapse_controls():
    assert "function ensureFeatureToolbar(target, surface)" in JS
    assert 'back.textContent = "← 기능목록";' in JS
    assert 'collapse.textContent = "접기 ⌃";' in JS
    assert "function returnToCategory(category)" in JS
    assert "function closeFeatureView()" in JS
    assert 'document.body.setAttribute("data-feature-view-active"' in JS
    assert ".app-feature-viewbar" in CSS
    assert ".app-feature-back" in CSS
    assert ".app-feature-collapse" in CSS


def test_legacy_long_sections_are_kept_under_advanced_category_menu():
    assert "LEGACY_ADVANCED_RULES" in JS
    for token in (
        "🧪 v10 검증·오류보정",
        "📸 검증 사진 참고",
        "📈 실시간 데이터 업데이트 원칙",
        "🧠 누적 오류 보정",
        "🌐 실시간 반영이 안 되는 기능",
    ):
        assert token in JS
    assert "feature-category-advanced" in JS
    assert "feature-advanced-shortcut" in JS
    assert ".feature-category-advanced" in CSS
    assert ".feature-advanced-grid" in CSS


def test_home_returns_to_category_only_view():
    assert "categories.forEach((category) => { category.open = false; });" in JS
    assert "updateCategoryStatus(null);" in JS
    assert "scrollTarget(nav);" in JS


def test_shortcut_can_reveal_only_its_managed_surface():
    assert "function showManagedTarget(target)" in JS
    assert "showManagedTarget(target);" in JS
    assert "targetSurfaces.get(target) || surfaceForTarget(target)" in JS
    assert "hideManagedSurfaces();" in JS


def test_bottom_dock_maps_to_the_correct_category():
    assert "const DOCK_CATEGORY_BY_KEY = Object.freeze({" in JS
    assert '"purchase-finder":"purchase"' in JS
    assert '"market-search":"market"' in JS
    assert '"tablet-manager":"tablet"' in JS
    assert "categoryByKey(DOCK_CATEGORY_BY_KEY[item.key])" in JS


def test_v470_interaction_version_is_exposed_without_breaking_prior_api():
    assert 'version: "v30-tablet-manager-hub"' in JS
    assert 'uiVersion: "v407-video-neural-dock"' in JS
    assert 'categoryInteractionVersion: "v470-single-feature-view"' in JS
    assert "returnToCategory," in JS
    assert "closeFeatureView," in JS
