"""CI fan-out preserves every isolated root test and the final required gate."""
import collections,json,subprocess,unittest
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]

class ExhaustiveRegressionShardsTests(unittest.TestCase):
    def workflow(self):
        return yaml.safe_load((ROOT/'.github/workflows/exhaustive-selfrefine-guard.yml').read_text())

    def test_partition_covers_every_tracked_root_module_once(self):
        job=self.workflow()['jobs']['root_regressions']
        shards=job['strategy']['matrix']['shard']
        self.assertEqual(list(range(16)),shards);self.assertIs(job['strategy']['fail-fast'],False)
        names=sorted(p for p in subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines() if '/' not in p and p.startswith('test_') and p.endswith('.py'))
        self.assertGreater(len(names),400)
        counts=collections.Counter(p for shard in shards for index,p in enumerate(names) if index%len(shards)==shard)
        self.assertEqual(set(names),set(counts));self.assertEqual({1},set(counts.values()))
        step=next(x for x in job['steps'] if x.get('name','').startswith('Run root production'))
        script=step['run']
        self.assertIn('shard_count=16',script)
        for token in ('for file in test_*.py; do','owner=$((index % shard_count))','index=$((index+1))','[ "$owner" -eq "$shard" ] || continue','python -m unittest discover -v -s . -p "$file"','python selfrefine_standalone_test_runner.py "$file"','if [ "$failed_count" -ne 0 ]; then exit 1; fi'):
            self.assertIn(token,script)
        self.assertLess(script.index('index=$((index+1))'),script.index('[ "$owner" -eq "$shard" ] || continue'))
        self.assertEqual(25,job['timeout-minutes'])

    def test_main_alignment_sync_fanout_covers_every_generation_exactly_once(self):
        workflow=yaml.safe_load((ROOT/'.github/workflows/tablet-gpt-tcg-grader-main-alignment.yml').read_text())
        job=workflow['jobs']['sync-generations']
        shards=job['strategy']['matrix']['shard']
        self.assertEqual(list(range(16)),shards)
        self.assertIs(job['strategy']['fail-fast'],False)
        self.assertEqual(10,job['timeout-minutes'])
        names=[Path(n) for n in subprocess.check_output(
            ['git','ls-files','test_tablet_gpt_tcg_grader_sync_v*.py'],
            cwd=ROOT,text=True).splitlines()
            if n.startswith('test_tablet_gpt_tcg_grader_sync_v') and n.endswith('.py')]
        names.sort(key=lambda p:int(p.stem.rsplit('v',1)[1]))
        self.assertGreater(len(names),16)
        groups=[names[i::len(shards)] for i in shards]
        self.assertTrue(all(groups))
        counts=collections.Counter(p for group in groups for p in group)
        self.assertEqual(set(names),set(counts))
        self.assertEqual({1},set(counts.values()))
        step=next(item for item in job['steps']
                  if item.get('name','').startswith('Verify every discovered generation'))
        script=step['run']
        for token in ("groups = [tests[i::16] for i in range(16)]",
                      'assert tests and all(groups)',
                      'assert len({p for group in groups for p in group}) == sum(map(len, groups)) == len(tests)',
                      "selected = groups[int(os.environ['SYNC_SHARD'])]",
                      'python -m unittest -v "${tests[@]}"'):
            self.assertIn(token,script)
        final=workflow['jobs']['alignment']
        self.assertEqual('sync-generations',final['needs'])
        self.assertEqual(10,final['timeout-minutes'])
        scripts='\n'.join(str(item.get('run','')) for item in final['steps'])
        self.assertIn('Fail visibly when watched changes are not covered by the latest verified delta',
                      [item.get('name') for item in final['steps']])
        self.assertIn('requires_exact_watched_path_match',scripts)
        self.assertIn('post_merge_coverage_allowed',scripts)

    def test_final_gate_requires_every_shard_and_preserves_nested_and_runtime_checks(self):
        job=self.workflow()['jobs']['exhaustive']
        self.assertEqual(['root_regressions'],job['needs']);self.assertEqual('${{ always() }}',job['if'])
        gate=job['steps'][0]
        self.assertEqual('${{ needs.root_regressions.result }}',gate['env']['ROOT_SHARDS_RESULT'])
        self.assertEqual('test "$ROOT_SHARDS_RESULT" = success',gate['run'])
        self.assertEqual('Exhaustive SELFREFINE Guard',job['name']);self.assertEqual(25,job['timeout-minutes'])
        scripts='\n'.join(s.get('run','') for s in job['steps'])
        for command in ('python -m unittest discover -v -s instagram_tcg_content', 'python verify_all.py','TCG_FINAL_SKIP_HEAD_MATCH=1 bash VERIFY_TABLET_FINAL.sh','python security_self_audit.py --fail-on medium','python main_selfrefine_gate.py'):
            self.assertIn(command,scripts)
        from verify_critical_feature_matrix_v25 import verify
        self.assertEqual([],verify()['failures'])
