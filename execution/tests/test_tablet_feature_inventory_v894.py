from pathlib import Path
import re
import tempfile
import unittest
from execution import tablet_feature_inventory_v894 as features


class MigrationTests(unittest.TestCase):
    def test_all_real_sections_and_controls_preserved(self):
        source=(Path(__file__).resolve().parents[2]/'index.html').read_text()
        before=features.inventory(source);migrated=features.annotate(source);after=features.inventory(migrated)
        self.assertEqual(len(before['items']),len(after['items']))
        self.assertEqual(before['controls'],after['controls'])
        self.assertEqual([i['id'] for i in before['items']],[i['id'] for i in after['items']])
        self.assertTrue(all(i['marked'] for i in after['items']))
        self.assertEqual(migrated,features.annotate(migrated))
        restored=migrated
        for item in before['items']:
            new=item['opening'][:-1]+(' id="'+item['id']+'"' if item.get('assigned') else '')+' data-tcg-migration-target="true">'
            restored=restored.replace(new,item['opening'],1)
        self.assertEqual(source,restored)
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'index.html').write_text(source)
            page=features.render_directory(folder)
        for item in before['items']:self.assertIn('/index.html?target='+item['id'],page)
    def test_advanced_anonymous_sections_and_guides_receive_distinct_routes(self):
        source='<section><h2>시세</h2><button>삭제</button></section><section><div class="muted">사진 입력</div><input></section><details id="guide"><summary>실행 안내</summary></details>'
        rows=features.inventory(source)['items']
        self.assertEqual(3,len({r['id'] for r in rows}))
        self.assertEqual(['시세','사진 입력','실행 안내'],[r['label'] for r in rows])
        self.assertNotIn('onclick',features.annotate(source))
    def test_synthetic_id_collision_and_duplicate_source_ids(self):
        rows=features.inventory('<section></section><section id="migrationSection1"></section>')['items']
        self.assertNotEqual(rows[0]['id'],rows[1]['id'])
        with self.assertRaises(ValueError):features.inventory('<section id="x"></section><section id="x"></section>')
    def test_directory_escapes_untrusted_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'index.html').write_text('<section id="safe" aria-label="&lt;img onerror=alert(1)&gt;"></section>')
            page=features.render_directory(folder)
            self.assertIn('&lt;img',page);self.assertNotIn('<img',page)
    def test_result_sections_are_not_forced_visible(self):
        result=features.annotate('<section id="result" hidden style="display:none"><h2>분석 결과</h2></section>')
        self.assertIn(' hidden ',result);self.assertIn('display:none',result)
    def test_unsafe_index_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'other').write_text('x');(root/'index.html').symlink_to(root/'other')
            with self.assertRaises(ValueError):features.render_directory(root)

    def test_actual_handler_directory_and_original_page_use_identical_targets(self):
        import importlib.util
        import io
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        class Base:
            def _require_request_host(self):return True
            def send_response(self,code):self.code=code
            def send_header(self,*args):pass
            def end_headers(self):pass
            def json(self,payload,code=200):self.code=code
        root=Path(__file__).resolve().parents[1]
        deps={'tablet_image_auto_v2':SimpleNamespace(collect_once=lambda:None),
              'tablet_image_library_v1':SimpleNamespace(_local_request=lambda h:True),
              'execution.tablet_image_unified_v888':SimpleNamespace(repair_existing=None,export_html=None),
              'execution.tablet_image_recheck_review_v887':SimpleNamespace(read_live=None),
              'execution.tablet_entity_store_v892':SimpleNamespace(reconcile=None),
              'tcg_updater':SimpleNamespace(MAX_SAFE_FILE_BYTES=3_000_000,open_safe_binary=lambda p,**kw:p.open('rb'))}
        with patch.dict(sys.modules,deps),tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'index.html').write_text('<body><section><h2>고급 도구</h2><button id="delete">삭제</button></section></body>')
            spec=importlib.util.spec_from_file_location('reviewed_migration_runtime',root/'tablet_unified_runtime_v889.py')
            runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
            h=runtime.make_handler(Base)();h.directory=directory;h.wfile=io.BytesIO();h.path='/tablet-features';h.do_GET()
            self.assertEqual(200,h.code);self.assertIn('target=migrationSection1',h.wfile.getvalue().decode())
            h.wfile=io.BytesIO();h.path='/index.html?target=migrationSection1';h.do_GET()
            page=h.wfile.getvalue().decode();self.assertIn('id="migrationSection1" data-tcg-migration-target',page)
            self.assertIn('<button id="delete">삭제</button>',page)
            self.assertNotIn('target.click()',runtime.FEATURE_BOOT)

    def test_feature_boot_has_valid_javascript(self):
        import ast
        import shutil
        import subprocess
        if not shutil.which('node'):self.skipTest('Node unavailable')
        tree=ast.parse((Path(__file__).resolve().parents[1]/'tablet_unified_runtime_v889.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='FEATURE_BOOT' for t in n.targets))
        script=ast.literal_eval(node.value).replace('<script>','').replace('</script>','')
        result=subprocess.run(['node','--check'],input=script,text=True,capture_output=True,timeout=10)
        self.assertEqual(0,result.returncode,result.stderr)
