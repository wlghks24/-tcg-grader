"""Device-local, read-only workspace acceptance; never starts or updates a server."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path

SCHEMA = 'tcg-card-box-library/v1017'
MAX_PAGE_BYTES = 4_000_000


REQUIRED_SOURCE = ('execution/tablet_backlog_priority_v893.py', 'execution/tablet_card_facts_v904.py', 'execution/tablet_card_view_v904.py', 'execution/tablet_catalog_bridge.py', 'execution/tablet_collection_receipt_v901.py', 'execution/tablet_display_fast_v901.py', 'execution/tablet_entity_store_v892.py', 'execution/tablet_event_coverage_v896.py', 'execution/tablet_event_freshness_v891.py', 'execution/tablet_event_refresh_20261123.js', 'execution/tablet_event_summary_v890.py', 'execution/tablet_feature_inventory_v894.py', 'execution/tablet_game_coverage_v907.py', 'execution/tablet_image_recheck_review_v887.py', 'execution/tablet_image_reciprocity_v887.py', 'execution/tablet_image_unified_v888.py', 'execution/tablet_live_view_v898.py', 'execution/tablet_menu_shell_v903.js', 'execution/tablet_menu_shell_v903.py', 'execution/tablet_provider_json_v900.py', 'execution/tablet_public_image_identity_audit_v887.py', 'execution/tablet_target_image_v895.py', 'execution/tablet_unified_runtime_v889.py', 'execution/tablet_unified_ui_v890.py', 'execution/tablet_workspace_verify_v1017.py')


def check_source(repo):
    repo = Path(repo)
    manifest = json.loads((repo / "integrity_manifest.json").read_text())["files"]
    for name in REQUIRED_SOURCE:
        path = repo / name
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("unsafe workspace source")
        raw = path.read_bytes()
        if manifest.get(name) != {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}:
            raise ValueError("workspace source mismatch")
        if path.suffix == ".py":
            compile(raw, str(path), "exec")
    return {"status": "WORKSPACE_SOURCE_VERIFIED", "physical_tablet_verified": False}


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.shell = False
        self.ids = set()
        self.scripts = []
        self.script = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'body':
            self.shell = attrs.get('data-tcg903-shell') == 'true'
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        if tag == 'script':
            self.script = []

    def handle_data(self, value):
        if self.script is not None:
            self.script.append(value)

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            self.scripts.append(''.join(self.script))
            self.script = None


def served_boot_digest(repo):
    """Match compose's exact controller concatenation from verified source."""
    repo = Path(repo)
    manifest_path = repo / 'integrity_manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > MAX_PAGE_BYTES:
        raise ValueError('workspace boot manifest unavailable')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))['files']
    if not isinstance(manifest, dict):
        raise ValueError('workspace boot manifest files invalid')
    scripts = []
    for name in ('execution/tablet_menu_shell_v903.js',
                 'execution/tablet_event_refresh_20261123.js'):
        path = repo / name
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
            raise ValueError('workspace boot asset unavailable')
        raw = path.read_bytes()
        if manifest.get(name) != {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}:
            raise ValueError('workspace boot asset mismatch')
        # read_text, used by compose, normalizes newlines. Normalize these
        # already verified bytes rather than rereading a mutable file.
        scripts.append(raw.decode('utf-8').replace('\r\n','\n').replace('\r','\n'))
    return hashlib.sha256('\n'.join(scripts).encode('utf-8')).hexdigest()


def assess(repo, report, document):
    """A matching server SHA alone must never accept the fallback hub UI."""
    from execution.tablet_runtime_handoff import matched
    from tablet_runtime_probe import git_state
    repo = Path(repo)
    expected = git_state(repo)['sha_full']
    errors = []
    if len(expected) != 40 or not matched(report, expected):
        errors.append('RUNNING_BUILD_MISMATCH')
    ui = report.get('health', {}).get('payload', {}).get('workspace_ui')
    if not isinstance(ui, dict):
        ui = {}
    if ui.get('schema') != SCHEMA:
        errors.append('WORKSPACE_RUNTIME_MISSING')
    for name, key in [('tablet_menu_shell_v903.py', 'shell_sha256'),
                      ('tablet_menu_shell_v903.js', 'script_sha256')]:
        path = repo / 'execution' / name
        if path.is_symlink() or not path.is_file():
            errors.append('WORKSPACE_ASSET_MISSING')
        elif hashlib.sha256(path.read_bytes()).hexdigest() != ui.get(key):
            errors.append('WORKSPACE_LOADED_ASSET_MISMATCH')
    if not isinstance(document, str) or len(document.encode('utf-8')) > MAX_PAGE_BYTES:
        errors.append('WORKSPACE_DOCUMENT_INVALID')
    else:
        page = Page(document)
        if not page.shell or not {'tcg903-drawer', 'tcg903-grid', 'tcg903-game',
                                  'tcg903-countries', 'tcg903-events'} <= page.ids:
            errors.append('WORKSPACE_NAVIGATION_MISSING')
        hashes = {hashlib.sha256(s.encode('utf-8')).hexdigest() for s in page.scripts}
        try:
            expected_boot = served_boot_digest(repo)
        except (OSError, ValueError, KeyError, TypeError, UnicodeError):
            errors.append('WORKSPACE_BOOT_ASSET_UNVERIFIED')
        else:
            if expected_boot not in hashes:
                errors.append('WORKSPACE_SERVED_SCRIPT_MISMATCH')
    return {'status': 'WORKSPACE_HTTP_VERIFIED' if not errors else 'HOLD',
            'running_build_sha': expected, 'errors': errors,
            'collection_ready': report.get('collection_health_ready') is True,
            'physical_tablet_verified': False,
            'verification_scope': 'LOCAL_HTTP_WORKSPACE_SOURCE_ONLY'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--check-source', action='store_true')
    args = parser.parse_args()
    from tablet_runtime_probe import build_report
    try:
        if args.check_source:
            print(json.dumps(check_source(args.repo)))
            return 0
        report = build_report(args.repo, probe_network=False)
        # Fixed loopback endpoint; no caller-controlled URL or redirects.
        from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with build_opener(ProxyHandler({}), NoRedirect).open('http://127.0.0.1:8765/index.html', timeout=5) as response:
            content = response.read(MAX_PAGE_BYTES + 1)
        if len(content) > MAX_PAGE_BYTES:
            raise ValueError('oversized workspace')
        result = assess(args.repo, report, content.decode('utf-8'))
    except (OSError, ValueError, KeyError, TypeError):
        result = {'status': 'HOLD', 'errors': ['WORKSPACE_READ_FAILED'], 'physical_tablet_verified': False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'WORKSPACE_HTTP_VERIFIED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
