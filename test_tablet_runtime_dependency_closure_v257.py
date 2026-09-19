#!/usr/bin/env python3
from __future__ import annotations
import ast
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

import tablet_runtime_manifest as manifest
import tcg_updater

ROOT=Path(__file__).resolve().parent

class _ScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()!="script":
            return
        values=dict(attrs)
        src=values.get("src")
        if src:
            self.sources.append(src)

def _normalize(value):
    text=str(value or "").strip()
    if not text or text.startswith(("http://","https://","//","data:","blob:","#")):
        return None
    text=text.split("?",1)[0].split("#",1)[0].strip()
    while text.startswith("./"):
        text=text[2:]
    text=text.lstrip("/")
    return text or None

def _index_scripts():
    parser=_ScriptParser()
    parser.feed((ROOT/"index.html").read_text(encoding="utf-8"))
    return {asset for raw in parser.sources if (asset:=_normalize(raw))}

def _sw_core():
    source=(ROOT/"sw.js").read_text(encoding="utf-8")
    match=re.search(r"const\s+CORE\s*=\s*\[(.*?)\]\s*;",source,re.S)
    if not match:
        raise AssertionError("service-worker CORE list missing")
    return {asset for raw in re.findall(r"['\"]([^'\"]+)['\"]",match.group(1)) if (asset:=_normalize(raw))}

def _startup_local_imports():
    tree=ast.parse((ROOT/"tcg_updater.py").read_text(encoding="utf-8"),filename="tcg_updater.py")
    modules=set()
    for node in tree.body:
        if isinstance(node,ast.Import):
            modules.update(alias.name.split(".",1)[0] for alias in node.names)
        elif isinstance(node,ast.ImportFrom) and node.module and node.level==0:
            modules.add(node.module.split(".",1)[0])
    return {f"{module}.py" for module in modules if (ROOT/f"{module}.py").is_file()}

class TabletRuntimeDependencyClosureV257Tests(unittest.TestCase):
    def test_manifest_has_no_duplicates_and_audits_dependency_graph(self):
        self.assertEqual(len(manifest.ACTIVE_RUNTIME_FILES),len(set(manifest.ACTIVE_RUNTIME_FILES)))
        result=manifest.audit(ROOT,compile_python=False)
        self.assertEqual([],result.get("dependency_errors"),result)
        self.assertEqual([],result.get("duplicates"),result)

    def test_every_local_index_script_is_fail_closed_public_and_precached(self):
        scripts=_index_scripts()
        self.assertTrue(scripts)
        self.assertTrue(scripts.issubset(set(manifest.ACTIVE_RUNTIME_FILES)),scripts-set(manifest.ACTIVE_RUNTIME_FILES))
        self.assertTrue(scripts.issubset(set(tcg_updater.PUBLIC_STATIC_FILES)),scripts-set(tcg_updater.PUBLIC_STATIC_FILES))
        core=_sw_core()
        self.assertTrue(scripts.issubset(core),scripts-core)

    def test_service_worker_functional_assets_are_manifested_and_public(self):
        core=_sw_core()
        functional={name for name in core if Path(name).suffix.lower() in {".js",".css",".webmanifest",".svg"}}
        functional.update({"vision_calibration.json","grading_company_updates.json"}&core)
        self.assertTrue(functional.issubset(set(manifest.ACTIVE_RUNTIME_FILES)),functional-set(manifest.ACTIVE_RUNTIME_FILES))
        self.assertTrue(core.issubset(set(tcg_updater.PUBLIC_STATIC_FILES)),core-set(tcg_updater.PUBLIC_STATIC_FILES))
        missing={name for name in core if not (ROOT/name).is_file()}
        self.assertEqual(set(),missing)

    def test_server_startup_local_imports_are_fail_closed(self):
        imports=_startup_local_imports()
        self.assertIn("grading_accuracy_v99.py",imports)
        self.assertIn("server_security_guard.py",imports)
        self.assertTrue(imports.issubset(set(manifest.ACTIVE_RUNTIME_FILES)),imports-set(manifest.ACTIVE_RUNTIME_FILES))

    def test_grading_static_fallback_is_public_precached_and_fail_closed(self):
        name="grading_company_updates.json"
        self.assertIn(name,tcg_updater.PUBLIC_STATIC_FILES)
        self.assertIn(name,_sw_core())
        self.assertIn(name,manifest.ACTIVE_RUNTIME_FILES)
        source=(ROOT/"grading_costs_live.js").read_text(encoding="utf-8")
        self.assertIn("/grading_company_updates.json?t=",source)

    def test_service_worker_cache_generation_was_rotated(self):
        source=(ROOT/"sw.js").read_text(encoding="utf-8")
        self.assertIn("const CACHE='tcg-v257-network-first-runtime';",source)
        self.assertNotIn("tcg-v205-network-first-runtime",source)

if __name__=="__main__":
    unittest.main()
