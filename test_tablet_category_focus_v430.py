#!/usr/bin/env python3
"""V430 guard for recording-derived category focus navigation."""
from pathlib import Path

ROOT=Path(__file__).resolve().parent
JS=(ROOT/"feature_category_nav.js").read_text(encoding="utf-8")

def test_details_hidden_until_category_selected():
    assert "const categoryTargets = new Map();" in JS
    assert "const managedTargets = new Set();" in JS
    assert "setCategoryContent(null);" in JS
    assert "managedTargets.forEach((target) => { target.hidden = true; });" in JS

def test_category_reveals_only_its_declared_targets():
    assert 'category.querySelectorAll(".feature-shortcut[href^=\'#\']")' in JS
    assert "(categoryTargets.get(category) || new Set()).forEach((target) => { target.hidden = false; });" in JS
    assert 'document.body.setAttribute("data-feature-category-active"' in JS

def test_home_returns_to_category_only_view():
    assert "categories.forEach((category) => { category.open = false; });" in JS
    assert "updateCategoryStatus(null);" in JS
    assert "scrollTarget(nav);" in JS

def test_shortcut_can_reveal_managed_target():
    assert "function showManagedTarget(target)" in JS
    assert "showManagedTarget(target);" in JS
