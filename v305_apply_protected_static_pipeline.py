#!/usr/bin/env python3
from pathlib import Path

BRANCH = 'fix/protected-static-data-pipeline-v305'
BOOTSTRAP = Path('.github/workflows/v305-protected-static-pipeline-bootstrap.yml')
SELF = Path(__file__)
HEALTH = Path('.github/workflows/repository-health-v239.yml')
TEMP_MARKER = '\n  v305-bootstrap:\n'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} marker not found')
    return text.replace(old, new, 1)


def rewrite_static_refresh() -> None:
    path = Path('.github/workflows/tcg-static-data-refresh.yml')
    text = path.read_text(encoding='utf-8')
    text = replace_once(
        text,
        'permissions:\n  contents: write\n',
        'permissions:\n  actions: write\n  checks: read\n  contents: write\n  pull-requests: write\n',
        'static permissions',
    )
    text = replace_once(text, '    timeout-minutes: 35\n', '    timeout-minutes: 60\n', 'static timeout')

    start_marker = '      - name: Commit validated static data snapshot\n'
    end_marker = '      - name: Upload publish evidence\n'
    start = text.find(start_marker)
    end = text.find(end_marker, start + 1)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit('static direct-publish block not found')

    replacement = '''      - name: Commit validated static data candidate\n        id: candidate\n        if: steps.stage.outputs.changed == 'true'\n        shell: bash\n        run: |\n          set -euo pipefail\n          python fault_injection_healing.py --diagnose\n          python - <<'PY'\n          import json\n          from pathlib import Path\n          import fault_injection_healing as healing\n\n          root = Path('.').resolve()\n          payload = json.loads((root / 'integrity_manifest.json').read_text(encoding='utf-8'))\n          listed = set((payload.get('files') or {}).keys())\n          current = {path.relative_to(root).as_posix() for path in healing.tracked_files(root)}\n          if listed != current:\n              raise SystemExit(f'integrity manifest coverage mismatch: missing={sorted(current-listed)[:20]} extra={sorted(listed-current)[:20]}')\n          PY\n          git add -- integrity_manifest.json\n          git diff --cached --check\n\n          base_sha="$(git rev-parse HEAD)"\n          candidate_branch="auto/static-data-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"\n          git switch -c "${candidate_branch}"\n          git config user.name 'github-actions[bot]'\n          git config user.email '41898282+github-actions[bot]@users.noreply.github.com'\n          git commit -m 'data: refresh validated TCG static snapshot'\n          candidate_sha="$(git rev-parse HEAD)"\n\n          git fetch origin main\n          if [ "$(git rev-parse origin/main)" != "${base_sha}" ]; then\n            echo "published=false" >> "$GITHUB_OUTPUT"\n            echo "reason=main advanced after validation; discard local candidate" >> "$GITHUB_OUTPUT"\n            exit 0\n          fi\n\n          git push origin "HEAD:refs/heads/${candidate_branch}"\n          export BASE_SHA="${base_sha}" CANDIDATE_BRANCH="${candidate_branch}" CANDIDATE_SHA="${candidate_sha}"\n          python - <<'PY'\n          import hashlib\n          import json\n          import os\n          from pathlib import Path\n\n          names = tuple('releases.json promo_events.json supplementary_candidates.json social_event_candidates.json purchase_signals.json social_stock_signals.json market_prices.json market_watch.json purchase_sources.json exchange_rates.json grading_company_updates.json graded_photo_candidates.json source_collection_stats.json adaptive_collection_stats.json auto_update_report.json auto_update_issues.json tcg_live_data.json'.split())\n          files = []\n          for name in names:\n              raw = Path(name).read_bytes()\n              json.loads(raw)\n              files.append({'name': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})\n          payload = {\n              'schema_version': 1,\n              'repository': os.environ['GITHUB_REPOSITORY'],\n              'run_id': os.environ['GITHUB_RUN_ID'],\n              'run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),\n              'base_sha': os.environ['BASE_SHA'],\n              'candidate_branch': os.environ['CANDIDATE_BRANCH'],\n              'candidate_sha': os.environ['CANDIDATE_SHA'],\n              'files': files,\n          }\n          Path('STATIC_DATA_CANDIDATE.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')\n          PY\n          echo "branch=${candidate_branch}" >> "$GITHUB_OUTPUT"\n          echo "commit=${candidate_sha}" >> "$GITHUB_OUTPUT"\n          echo "base=${base_sha}" >> "$GITHUB_OUTPUT"\n          echo "published=true" >> "$GITHUB_OUTPUT"\n          echo "reason=validated candidate branch published" >> "$GITHUB_OUTPUT"\n\n      - name: Upload protected-main candidate evidence\n        if: steps.candidate.outputs.published == 'true'\n        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a\n        with:\n          name: tcg-static-data-candidate-${{ github.run_id }}-${{ github.run_attempt }}\n          path: |\n            STATIC_DATA_CANDIDATE.json\n            releases.json\n            promo_events.json\n            supplementary_candidates.json\n            social_event_candidates.json\n            purchase_signals.json\n            social_stock_signals.json\n            market_prices.json\n            market_watch.json\n            purchase_sources.json\n            exchange_rates.json\n            grading_company_updates.json\n            graded_photo_candidates.json\n            source_collection_stats.json\n            adaptive_collection_stats.json\n            auto_update_report.json\n            auto_update_issues.json\n            tcg_live_data.json\n            integrity_manifest.json\n            STATIC_DATA_PUBLISH_REPORT.json\n          if-no-files-found: error\n          retention-days: 14\n\n      - name: Promote candidate through protected main\n        id: promote\n        if: steps.candidate.outputs.published == 'true'\n        shell: bash\n        env:\n          GH_TOKEN: ${{ github.token }}\n          REPO: ${{ github.repository }}\n          CANDIDATE_BRANCH: ${{ steps.candidate.outputs.branch }}\n          CANDIDATE_SHA: ${{ steps.candidate.outputs.commit }}\n          BASE_SHA: ${{ steps.candidate.outputs.base }}\n        run: |\n          set -euo pipefail\n          owner="${GITHUB_REPOSITORY_OWNER}"\n          pr_number="$(gh api -X GET "repos/${REPO}/pulls" -f state=open -f head="${owner}:${CANDIDATE_BRANCH}" -f base=main --jq '.[0].number // empty')"\n\n          if [ -z "${pr_number}" ]; then\n            title="data: validated static snapshot ${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"\n            body="Protected-main candidate from TCG Static Data Refresh. Base: ${BASE_SHA}. Candidate: ${CANDIDATE_SHA}. Run: ${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}. Only validated public JSON and integrity metadata are eligible."\n            if ! pr_json="$(gh api --method POST "repos/${REPO}/pulls" -f title="${title}" -f head="${CANDIDATE_BRANCH}" -f base=main -f body="${body}" 2>/tmp/create-pr.err)"; then\n              cat /tmp/create-pr.err >&2 || true\n              echo 'status=PENDING_EXTERNAL_PR' >> "$GITHUB_OUTPUT"\n              echo 'GitHub Actions PR creation is unavailable; retain candidate branch for external protected-main promotion.'\n              exit 0\n            fi\n            pr_number="$(printf '%s' "${pr_json}" | jq -r '.number')"\n          fi\n          echo "pr_number=${pr_number}" >> "$GITHUB_OUTPUT"\n\n          required_workflows=(\n            tablet-gpt-tcg-grader-main-alignment.yml\n            repository-integrity-guard.yml\n            selfrefine-full-repo.yml\n            deep-selfrefine-guard.yml\n            exhaustive-selfrefine-guard.yml\n            tablet-termux-main-guard.yml\n            android-updater-guard.yml\n          )\n          for workflow in "${required_workflows[@]}"; do\n            gh api --method POST "repos/${REPO}/actions/workflows/${workflow}/dispatches" -f ref="${CANDIDATE_BRANCH}"\n          done\n\n          required_checks=(\n            'Tablet GPT TCG Grader Main Alignment'\n            'Repository Integrity Guard'\n            'Main SELFREFINE'\n            'Deep SELFREFINE Guard'\n            'Exhaustive SELFREFINE Guard'\n            'Tablet Termux Main Guard'\n            'Android Updater Guard'\n          )\n          deadline=$((SECONDS + 900))\n          while (( SECONDS < deadline )); do\n            checks="$(gh api -H 'Accept: application/vnd.github+json' "repos/${REPO}/commits/${CANDIDATE_SHA}/check-runs?per_page=100")"\n            pending=0\n            failed=0\n            for name in "${required_checks[@]}"; do\n              state="$(printf '%s' "${checks}" | jq -r --arg name "${name}" '[.check_runs[] | select(.name == $name)] | sort_by(.started_at // "") | last | if . == null then "missing" elif .status != "completed" then .status else (.conclusion // "unknown") end')"\n              printf '%s: %s\\n' "${name}" "${state}"\n              case "${state}" in\n                success) ;;\n                failure|cancelled|timed_out|action_required|stale|skipped|neutral) failed=1 ;;\n                *) pending=1 ;;\n              esac\n            done\n            if (( failed )); then\n              echo 'status=REQUIRED_CHECK_FAILED' >> "$GITHUB_OUTPUT"\n              exit 1\n            fi\n            if (( ! pending )); then\n              break\n            fi\n            sleep 20\n          done\n          if (( SECONDS >= deadline )); then\n            echo 'status=REQUIRED_CHECK_TIMEOUT' >> "$GITHUB_OUTPUT"\n            exit 1\n          fi\n\n          git fetch origin main\n          if [ "$(git rev-parse origin/main)" != "${BASE_SHA}" ]; then\n            echo 'status=BASE_ADVANCED' >> "$GITHUB_OUTPUT"\n            echo 'Protected main advanced before merge; leave candidate PR open for a fresh collection run.'\n            exit 0\n          fi\n\n          merge_json="$(gh api --method PUT "repos/${REPO}/pulls/${pr_number}/merge" -f merge_method=merge -f sha="${CANDIDATE_SHA}")"\n          if [ "$(printf '%s' "${merge_json}" | jq -r '.merged')" != 'true' ]; then\n            printf '%s\\n' "${merge_json}" >&2\n            echo 'status=MERGE_REJECTED' >> "$GITHUB_OUTPUT"\n            exit 1\n          fi\n          echo 'status=MERGED' >> "$GITHUB_OUTPUT"\n          gh api --method POST "repos/${REPO}/actions/workflows/gpt-tcg-drive-package.yml/dispatches" -f ref=main\n          git push origin --delete "${CANDIDATE_BRANCH}" || true\n\n'''
    text = text[:start] + replacement + text[end:]
    old_summary = '            echo "- publish policy: validated public JSON only; no force push"\n'
    new_summary = ('            echo "- publish policy: validated candidate branch -> PR -> seven required checks -> protected-main merge; no direct/force push"\n'
                   '            echo "- candidate branch: ${{ steps.candidate.outputs.branch || \'none\' }}"\n'
                   '            echo "- promotion status: ${{ steps.promote.outputs.status || \'not-attempted\' }}"\n')
    text = replace_once(text, old_summary, new_summary, 'static summary')
    if 'git push origin HEAD:main' in text:
        raise SystemExit('direct main push still present')
    path.write_text(text, encoding='utf-8')


def rewrite_drive_package() -> None:
    path = Path('.github/workflows/gpt-tcg-drive-package.yml')
    text = path.read_text(encoding='utf-8')
    for line in (
        "      - 'tablet_gdrive_publish.py'\n",
        "      - 'tablet_gdrive_sync.py'\n",
        "      - 'tablet_collection_publish.py'\n",
        "      - '.github/workflows/gpt-tcg-drive-package.yml'\n",
    ):
        if line not in text:
            raise SystemExit(f'package trigger marker missing: {line.strip()}')
        text = text.replace(line, '', 1)
    path.write_text(text, encoding='utf-8')


def add_regression() -> None:
    test = '''import unittest\nfrom pathlib import Path\n\n\nclass ProtectedStaticPipelineV305Tests(unittest.TestCase):\n    def setUp(self):\n        self.refresh = Path('.github/workflows/tcg-static-data-refresh.yml').read_text(encoding='utf-8')\n        self.package = Path('.github/workflows/gpt-tcg-drive-package.yml').read_text(encoding='utf-8')\n\n    def test_static_refresh_never_direct_pushes_main(self):\n        self.assertNotIn('git push origin HEAD:main', self.refresh)\n        self.assertIn('auto/static-data-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}', self.refresh)\n        self.assertIn('pull-requests: write', self.refresh)\n        self.assertIn('actions: write', self.refresh)\n        self.assertIn('checks: read', self.refresh)\n\n    def test_exact_required_checks_gate_merge(self):\n        for value in (\n            'tablet-gpt-tcg-grader-main-alignment.yml', 'Repository Integrity Guard',\n            'selfrefine-full-repo.yml', 'Main SELFREFINE',\n            'deep-selfrefine-guard.yml', 'Deep SELFREFINE Guard',\n            'exhaustive-selfrefine-guard.yml', 'Exhaustive SELFREFINE Guard',\n            'tablet-termux-main-guard.yml', 'Tablet Termux Main Guard',\n            'android-updater-guard.yml', 'Android Updater Guard',\n            'Tablet GPT TCG Grader Main Alignment',\n        ):\n            self.assertIn(value, self.refresh)\n        self.assertIn('$(git rev-parse origin/main)', self.refresh)\n        self.assertIn('-f merge_method=merge -f sha="${CANDIDATE_SHA}"', self.refresh)\n\n    def test_drive_package_push_trigger_is_exact_data_surface(self):\n        push = self.package.split('  push:\\n', 1)[1].split('  workflow_dispatch:\\n', 1)[0]\n        for forbidden in ('tablet_gdrive_publish.py', 'tablet_gdrive_sync.py', 'tablet_collection_publish.py', '.github/workflows/gpt-tcg-drive-package.yml'):\n            self.assertNotIn(forbidden, push)\n        for required in tuple('releases.json promo_events.json supplementary_candidates.json social_event_candidates.json purchase_signals.json social_stock_signals.json market_prices.json market_watch.json purchase_sources.json exchange_rates.json grading_company_updates.json graded_photo_candidates.json source_collection_stats.json adaptive_collection_stats.json auto_update_report.json auto_update_issues.json tcg_live_data.json'.split()):\n            self.assertIn(required, push)\n        self.assertIn('  workflow_dispatch:', self.package)\n\n    def test_fail_closed_fallback_and_no_bypass(self):\n        self.assertIn('PENDING_EXTERNAL_PR', self.refresh)\n        self.assertIn('REQUIRED_CHECK_FAILED', self.refresh)\n        self.assertIn('REQUIRED_CHECK_TIMEOUT', self.refresh)\n        self.assertIn('BASE_ADVANCED', self.refresh)\n        self.assertNotIn('--admin', self.refresh)\n        self.assertNotIn('--force', self.refresh)\n        self.assertIn('gpt-tcg-drive-package.yml/dispatches', self.refresh)\n\n\nif __name__ == '__main__':\n    unittest.main()\n'''
    Path('test_protected_static_pipeline_v305.py').write_text(test, encoding='utf-8')

    guard_path = Path('.github/workflows/repository-integrity-guard.yml')
    guard = guard_path.read_text(encoding='utf-8')
    old = 'python -m unittest -v test_code_map_fast_route_v195.py test_ai_auto_tracker.py test_market_ai_auto_tracker.py'
    new = old + ' test_protected_static_pipeline_v305.py'
    guard_path.write_text(replace_once(guard, old, new, 'integrity regression hook'), encoding='utf-8')


def restore_temporary_surface() -> None:
    health = HEALTH.read_text(encoding='utf-8')
    if TEMP_MARKER not in health:
        raise SystemExit('temporary health bootstrap marker not found')
    health = health.split(TEMP_MARKER, 1)[0].rstrip() + '\n'
    HEALTH.write_text(health, encoding='utf-8')
    BOOTSTRAP.unlink(missing_ok=True)
    SELF.unlink(missing_ok=True)


def main() -> None:
    rewrite_static_refresh()
    rewrite_drive_package()
    add_regression()
    restore_temporary_surface()
    print('v305 protected static pipeline transformed')


if __name__ == '__main__':
    main()
