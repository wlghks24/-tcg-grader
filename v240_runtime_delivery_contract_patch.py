from pathlib import Path


def replace_once(path_name: str, old: str, new: str, label: str) -> None:
    path=Path(path_name)
    text=path.read_text(encoding='utf-8')
    count=text.count(old)
    if count!=1:
        raise SystemExit(f'{label} anchor mismatch: {count}')
    path.write_text(text.replace(old,new,1),encoding='utf-8')

replace_once(
    'tablet_runtime_manifest.py',
    '"index.html","safe_runtime.py","collection_runtime_health.py","tablet_runtime_manifest.py",',
    '"index.html","safe_runtime.py","runtime_sre_metrics.py","collection_runtime_health.py","tablet_runtime_manifest.py",',
    'tablet runtime SRE metrics',
)

replace_once(
    'runtime_bundle_guard_v143.py',
    'REQUIRED_FILES = (\n    "safe_runtime.py",\n',
    'REQUIRED_FILES = (\n    "safe_runtime.py",\n    "runtime_sre_metrics.py",\n',
    'runtime bundle SRE metrics',
)

replace_once(
    'test_runtime_delivery_guards.py',
    "    assert 'no-store, no-cache, must-revalidate, max-age=0' in server\n",
    "    assert 'private, no-cache, must-revalidate, max-age=0' in server\n"
    "    assert \"self.headers.get('If-None-Match','').strip()==etag\" in server\n"
    "    assert 'self.send_response(304)' in server\n"
    "    assert \"self.send_header('ETag',etag)\" in server\n"
    "    assert 'no-store, no-cache, must-revalidate, max-age=0' not in server\n",
    'runtime delivery cache contract',
)

path=Path('test_sre_runtime_performance_v240.py')
text=path.read_text(encoding='utf-8')
footer='\n\nif __name__ == "__main__":\n    unittest.main()\n'
if text.count(footer)!=1:
    raise SystemExit('SRE test footer anchor mismatch')
addition='''\n\n    def test_runtime_metrics_module_is_in_tablet_and_bundle_ssot(self):\n        import tablet_runtime_manifest\n        import runtime_bundle_guard_v143\n        self.assertIn("runtime_sre_metrics.py", tablet_runtime_manifest.ACTIVE_RUNTIME_FILES)\n        self.assertIn("runtime_sre_metrics.py", runtime_bundle_guard_v143.REQUIRED_FILES)\n'''
path.write_text(text.replace(footer,addition+footer,1),encoding='utf-8')
