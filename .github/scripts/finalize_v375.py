from pathlib import Path


def replace_idempotent(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"expected one old or existing new target in {path}: old={count} new={text.count(new)}"
        )
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


v369_old = '''                            self.assertEqual(
                                [],
                                watched_paths(successor374, candidate374["candidate_commit"]),
                                "verified v374 successor has uncovered watched changes",
                            )'''
v369_new = '''                            after374 = watched_paths(successor374, candidate374["candidate_commit"])
                            if after374:
                                successor375, candidate375 = assert_successor_generation(
                                    self,
                                    "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V374.json",
                                    "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v374_delta.json",
                                    "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json",
                                )
                                sixth_hop = watched_paths(
                                    successor374,
                                    candidate374["candidate_commit"],
                                    candidate375["candidate_commit"],
                                )
                                self.assertEqual(sorted(sixth_hop), sorted(candidate375["watched_paths"]))
                                self.assertEqual(
                                    [],
                                    watched_paths(successor375, candidate375["candidate_commit"]),
                                    "verified v375 successor has uncovered watched changes",
                                )
                            else:
                                self.assertEqual([], after374)'''
replace_idempotent("test_tablet_gpt_tcg_grader_sync_v369.py", v369_old, v369_new)

v370_old = '''                        self.assertEqual(
                            [],
                            watched_paths(successor374, candidate374["candidate_commit"]),
                            "verified v374 successor has uncovered watched changes",
                        )'''
v370_new = '''                        after374 = watched_paths(successor374, candidate374["candidate_commit"])
                        if after374:
                            successor375, candidate375 = assert_successor_generation(
                                self,
                                "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V374.json",
                                "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v374_delta.json",
                                "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json",
                            )
                            fifth_hop = watched_paths(
                                successor374,
                                candidate374["candidate_commit"],
                                candidate375["candidate_commit"],
                            )
                            self.assertEqual(sorted(fifth_hop), sorted(candidate375["watched_paths"]))
                            self.assertEqual(
                                [],
                                watched_paths(successor375, candidate375["candidate_commit"]),
                                "verified v375 successor has uncovered watched changes",
                            )
                        else:
                            self.assertEqual([], after374)'''
replace_idempotent("test_tablet_gpt_tcg_grader_sync_v370.py", v370_old, v370_new)

helper_old = '''def assert_v374_successor(testcase, relevant):
    contract, candidate = _verify_successor(
        testcase, V374_CONTRACT, V374_SOURCE, V374_CANDIDATE, relevant
    )
    testcase.assertEqual([], watched_paths(contract, V374_CANDIDATE))
    return contract, candidate'''
helper_new = '''def assert_v374_successor(testcase, relevant):
    return _verify_successor(
        testcase, V374_CONTRACT, V374_SOURCE, V374_CANDIDATE, relevant
    )'''
replace_idempotent("test_tablet_gpt_tcg_grader_sync_v371.py", helper_old, helper_new)
replace_idempotent("test_tablet_gpt_tcg_grader_sync_v372.py", helper_old, helper_new)

v371_old = '''                if after373:
                    assert_v374_successor(self, after373)
                else:
                    self.assertEqual([], after373)'''
v371_new = '''                if after373:
                    third_hop = watched_paths(
                        v373_contract, v373_candidate["candidate_commit"], V374_CANDIDATE
                    )
                    v374_contract, v374_candidate = assert_v374_successor(self, third_hop)
                    after374 = watched_paths(v374_contract, v374_candidate["candidate_commit"])
                    if after374:
                        v375_path = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
                        v375_contract, v375_candidate = _verify_successor(
                            self,
                            v375_path,
                            "2b1112318fa23f4e8edd525695ee3711ea715e18",
                            "d7c8577b514abdbbc15ba9323c4c0deb1945efed",
                            after374,
                        )
                        self.assertEqual(
                            [], watched_paths(v375_contract, v375_candidate["candidate_commit"])
                        )
                    else:
                        self.assertEqual([], after374)
                else:
                    self.assertEqual([], after373)'''
replace_idempotent("test_tablet_gpt_tcg_grader_sync_v371.py", v371_old, v371_new)

v372_old = '''            if after373:
                assert_v374_successor(self, after373)
            else:
                self.assertEqual([], after373)'''
v372_new = '''            if after373:
                second_hop = watched_paths(
                    v373_contract, v373_candidate["candidate_commit"], V374_CANDIDATE
                )
                v374_contract, v374_candidate = assert_v374_successor(self, second_hop)
                after374 = watched_paths(v374_contract, v374_candidate["candidate_commit"])
                if after374:
                    v375_path = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
                    v375_contract, v375_candidate = _verify_successor(
                        self,
                        v375_path,
                        "2b1112318fa23f4e8edd525695ee3711ea715e18",
                        "d7c8577b514abdbbc15ba9323c4c0deb1945efed",
                        after374,
                    )
                    self.assertEqual(
                        [], watched_paths(v375_contract, v375_candidate["candidate_commit"])
                    )
                else:
                    self.assertEqual([], after374)
            else:
                self.assertEqual([], after373)'''
replace_idempotent("test_tablet_gpt_tcg_grader_sync_v372.py", v372_old, v372_new)

v373_compare_old = '''            self.assertEqual(later, watched_paths(successor, sc["base_main_sha"], sc["candidate_commit"]))'''
v373_compare_new = '''            first_hop = watched_paths(contract, CANDIDATE, sc["candidate_commit"])
            self.assertEqual(
                first_hop,
                watched_paths(successor, sc["base_main_sha"], sc["candidate_commit"]),
            )'''
replace_idempotent("test_tablet_gpt_tcg_grader_sync_v373.py", v373_compare_old, v373_compare_new)

v373_tail_old = '''            self.assertEqual([], watched_paths(successor, sc["candidate_commit"]))'''
v373_tail_new = '''            after374 = watched_paths(successor, sc["candidate_commit"])
            if after374:
                successor375 = read(
                    ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
                )
                sc375 = successor375["candidate_sync"]
                self.assertEqual(
                    "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V374.json",
                    successor375["prior_contract"],
                )
                self.assertEqual(
                    "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v374_delta.json",
                    successor375["prior_delta_snapshot"],
                )
                self.assertEqual(
                    "2b1112318fa23f4e8edd525695ee3711ea715e18", sc375["base_main_sha"]
                )
                self.assertEqual(
                    "d7c8577b514abdbbc15ba9323c4c0deb1945efed", sc375["candidate_commit"]
                )
                self.assertEqual(
                    after374,
                    watched_paths(successor375, sc375["base_main_sha"], sc375["candidate_commit"]),
                )
                self.assertEqual([], watched_paths(successor375, sc375["candidate_commit"]))
            else:
                self.assertEqual([], after374)'''
replace_idempotent("test_tablet_gpt_tcg_grader_sync_v373.py", v373_tail_old, v373_tail_new)

v373_meta_old = '''            self.assertIn(
                "python tablet_autonomous_evolution_v374.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
                main_text,
            )
            self.assertIn('"tablet_autonomous_evolution_v374.py"', manifest_text)'''
v373_meta_new = '''            v374_cmd = "python tablet_autonomous_evolution_v374.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills"
            v375_cmd = "python tablet_autonomous_evolution_v375.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills"
            if v374_cmd in main_text:
                self.assertIn('"tablet_autonomous_evolution_v374.py"', manifest_text)
            else:
                self.assertIn(v375_cmd, main_text)
                self.assertIn('"tablet_autonomous_evolution_v375.py"', manifest_text)'''
replace_idempotent("test_tablet_gpt_tcg_grader_sync_v373.py", v373_meta_old, v373_meta_new)
