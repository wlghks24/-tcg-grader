#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def replace_once(path,old,new):
    target=ROOT/path
    text=target.read_text(encoding='utf-8')
    count=text.count(old)
    if count!=1:
        raise SystemExit(f'{path}: expected one replacement, got {count}')
    target.write_text(text.replace(old,new,1),encoding='utf-8')

replace_once(
    'test_error_recovery_learning_v134.py',
    '            self.assertEqual(result["rates"],initial["rates"])\n            self.assertEqual(result["collection_status"],"기존 확인환율 유지")\n',
    '            self.assertEqual(result["rates"],{})\n            self.assertEqual(result["collection_status"],"사용 가능한 확인환율 없음")\n'
)

replace_once(
    'test_tablet_gpt_tcg_grader_sync_v349.py',
    '        changed=subprocess.check_output(["git","diff","--name-only",f"{SOURCE}..HEAD"],text=True).splitlines()\n',
    '        changed=subprocess.check_output(["git","diff","--name-only",SOURCE],text=True).splitlines()\n'
)

print('[OK] amended v350 regression expectations')
