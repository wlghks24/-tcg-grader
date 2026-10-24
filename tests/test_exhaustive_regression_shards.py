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
        self.assertEqual([0,1,2,3],shards);self.assertIs(job['strategy']['fail-fast'],False)
        names=sorted(p for p in subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines() if '/' not in p and p.startswith('test_') and p.endswith('.py'))
        self.assertGreater(len(names),400)
        counts=collections.Counter(p for shard in shards for index,p in enumerate(names) if index%len(shards)==shard)
        self.assertEqual(set(names),set(counts));self.assertEqual({1},set(counts.values()))
        step=next(x for x in job['steps'] if x.get('name','').startswith('Run root production'))
        script=step['run']
        for token in ('for file in test_*.py; do','owner=$((index % shard_count))','index=$((index+1))','[ "$owner" -eq "$shard" ] || continue','python -m unittest discover -v -s . -p "$file"','python selfrefine_standalone_test_runner.py "$file"','if [ "$failed_count" -ne 0 ]; then exit 1; fi'):
            self.assertIn(token,script)
        self.assertLess(script.index('index=$((index+1))'),script.index('[ "$owner" -eq "$shard" ] || continue'))
        self.assertEqual(25,job['timeout-minutes'])

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
