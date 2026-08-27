#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''One-shot source upgrader for safe grading self-learning v2.

The script is idempotent. It patches the existing v31 app instead of replacing
the large index.html by hand, then lets the normal verification suite run.
'''
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def write_if_changed(path: Path, text: str) -> bool:
    old = path.read_text(encoding="utf-8")
    if text == old:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def patch_index() -> bool:
    path = ROOT / "index.html"
    text = path.read_text(encoding="utf-8")
    tag = '<script src="./grading_self_learning.js?v=2"></script>'
    if tag in text:
        return False
    marker = "</body></html>"
    if marker not in text:
        raise RuntimeError("index.html closing marker not found")
    text = text.replace(marker, f"{tag}\n{marker}", 1)
    return write_if_changed(path, text)


def patch_service_worker() -> bool:
    path = ROOT / "sw.js"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"const CACHE='([^']+)';", "const CACHE='tcg-v31-self-learning-v2';", text, count=1)
    if "'./grading_self_learning.js'" not in text:
        old = "'./index.html','./manifest.webmanifest'"
        new = "'./index.html','./grading_self_learning.js','./manifest.webmanifest'"
        if old not in text:
            raise RuntimeError("sw.js CORE marker not found")
        text = text.replace(old, new, 1)
    return write_if_changed(path, text)


def patch_updater() -> bool:
    path = ROOT / "tcg_updater.py"
    text = path.read_text(encoding="utf-8")

    import_line = (
        "from grading_self_learning import "
        "append_confirmed_sample, rebuild_store, model_status, calibrate_prediction, sanitize_legacy_rows\n"
    )
    if import_line not in text:
        marker = "from urllib.request import Request, urlopen\n"
        if marker not in text:
            raise RuntimeError("tcg_updater import marker not found")
        text = text.replace(marker, marker + import_line, 1)

    old_learning = re.compile(
        r"def learning_store\(\):\n"
        r"(?:    .*\n)+?"
        r"\ndef valid_learning_rows\(rows\):\n"
        r"(?:    .*\n)+?"
        r"    return clean\n",
        re.M,
    )
    new_learning = '''def learning_store():
    fallback={'version':2,'updated_at':None,'v30_validation':[],'v11_validation':[],
              'confirmed_samples':[],'calibration':{}}
    return rebuild_store(load_json_file(LEARNING_STORE,fallback))

def valid_learning_rows(rows):
    return sanitize_legacy_rows(rows)
'''
    if "return sanitize_legacy_rows(rows)" not in text:
        text, count = old_learning.subn(new_learning, text, count=1)
        if count != 1:
            raise RuntimeError("tcg_updater learning functions patch failed")

    get_marker = "        if path=='/api/learning-store': return self.json(learning_store())\n"
    get_extra = (
        get_marker
        + "        if path=='/api/learning-model-status': return self.json(model_status(learning_store()))\n"
    )
    if "/api/learning-model-status" not in text:
        if get_marker not in text:
            raise RuntimeError("learning GET marker not found")
        text = text.replace(get_marker, get_extra, 1)

    block_re = re.compile(
        r"        if post_path=='/api/learning-store':\n"
        r"(?:            .*\n)+?"
        r"        if post_path!='/api/apply': return self\.json\(\{'ok':False,'error':'없는 API'\},404\)\n",
        re.M,
    )
    new_post = '''        if post_path in ('/api/learning-store','/api/learning-sample','/api/grade-calibrate'):
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size<=0 or size>1000000:return self.json({'ok':False,'error':'학습자료 크기 오류'},400)
                incoming=json.loads(self.rfile.read(size).decode('utf-8'))
                if not isinstance(incoming,dict):return self.json({'ok':False,'error':'학습자료 형식 오류'},400)
                if post_path=='/api/learning-store':
                    current=learning_store()
                    current['v30_validation']=valid_learning_rows(incoming.get('v30_validation',[]))
                    current['v11_validation']=valid_learning_rows(incoming.get('v11_validation',[]))
                    current['updated_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
                    data=rebuild_store(current)
                    save_json_atomic(LEARNING_STORE,data)
                    saved=len(data.get('v30_validation',[]))+len(data.get('v11_validation',[]))+len(data.get('confirmed_samples',[]))
                    return self.json({'ok':True,'saved':saved,'updated_at':data['updated_at'],'model':model_status(data)})
                if post_path=='/api/learning-sample':
                    if incoming.get('verified') is not True:
                        return self.json({'ok':False,'error':'실제 확정등급 확인(verified=true)이 필요합니다.'},400)
                    data=append_confirmed_sample(learning_store(),incoming)
                    save_json_atomic(LEARNING_STORE,data)
                    return self.json({'ok':True,'saved':len(data.get('confirmed_samples',[])),'model':model_status(data)})
                company=str(incoming.get('company') or '').upper()
                prediction=incoming.get('prediction')
                result=calibrate_prediction(learning_store(),company,prediction,game=incoming.get('game'))
                return self.json({'ok':True,**result})
            except (ValueError,TypeError,json.JSONDecodeError):
                return self.json({'ok':False,'error':'학습자료 형식 오류'},400)
        if post_path=='/api/learning-rebuild':
            try:
                data=learning_store();data['updated_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
                data=rebuild_store(data);save_json_atomic(LEARNING_STORE,data)
                return self.json(model_status(data))
            except Exception as exc:return self.json({'ok':False,'error':str(exc)},500)
        if post_path!='/api/apply': return self.json({'ok':False,'error':'없는 API'},404)
'''
    if "/api/learning-sample" not in text:
        text, count = block_re.subn(new_post, text, count=1)
        if count != 1:
            raise RuntimeError("tcg_updater POST learning API patch failed")

    return write_if_changed(path, text)


def patch_migration() -> bool:
    path = ROOT / "migrate_old_data.py"
    text = path.read_text(encoding="utf-8")
    import_line = "from grading_self_learning import rebuild_store\n"
    if import_line not in text:
        marker = "from pathlib import Path\n"
        if marker not in text:
            raise RuntimeError("migration import marker not found")
        text = text.replace(marker, marker + import_line, 1)

    old_re = re.compile(
        r"def merge_learning\(new,old\):\n"
        r"(?:    .*\n)+?"
        r"\ndef merge_history",
        re.M,
    )
    replacement = '''def merge_learning(new,old):
    base={
        'version':2,
        'updated_at':max(str(new.get('updated_at') or ''),str(old.get('updated_at') or '')) or None,
        'v30_validation':rows_merged(new.get('v30_validation',[]),old.get('v30_validation',[])),
        'v11_validation':rows_merged(new.get('v11_validation',[]),old.get('v11_validation',[])),
        'confirmed_samples':rows_merged(new.get('confirmed_samples',[]),old.get('confirmed_samples',[]),limit=2000),
    }
    return rebuild_store(base)

def merge_history'''
    if "'confirmed_samples':rows_merged" not in text:
        text, count = old_re.subn(replacement, text, count=1)
        if count != 1:
            raise RuntimeError("migration learning patch failed")
    return write_if_changed(path, text)


def upgrade_learning_store() -> bool:
    from grading_self_learning import rebuild_store

    path = ROOT / "learning_store.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        data = {}
    new = rebuild_store(data)
    if new.get("updated_at") is None and data.get("updated_at"):
        new["updated_at"] = data["updated_at"]
    rendered = json.dumps(new, ensure_ascii=False, indent=2) + "\n"
    return write_if_changed(path, rendered)


def main() -> None:
    changed = {
        "index.html": patch_index(),
        "sw.js": patch_service_worker(),
        "tcg_updater.py": patch_updater(),
        "migrate_old_data.py": patch_migration(),
        "learning_store.json": upgrade_learning_store(),
    }
    print(json.dumps(changed, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
