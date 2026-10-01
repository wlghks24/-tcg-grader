#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [
    "test_tablet_gpt_tcg_grader_sync_v369.py",
    "test_tablet_gpt_tcg_grader_sync_v370.py",
    "test_tablet_gpt_tcg_grader_sync_v371.py",
    "test_tablet_gpt_tcg_grader_sync_v372.py",
    "test_tablet_gpt_tcg_grader_sync_v373.py",
    "test_tablet_gpt_tcg_grader_sync_v374.py",
]
IMPORT = "from sync_v376_successor_test_support import assert_v376_successor\n"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def load(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def save(name: str, text: str) -> None:
    (ROOT / name).write_text(text, encoding="utf-8")


def add_import(text: str, name: str) -> str:
    if IMPORT in text:
        return text
    return replace_once(text, "import unittest\n", "import unittest\n\n" + IMPORT, f"{name}:import")


def patch_v369(name: str) -> None:
    text = add_import(load(name), name)
    old = '''                                self.assertEqual(
                                    [],
                                    watched_paths(successor375, candidate375["candidate_commit"]),
                                    "verified v375 successor has uncovered watched changes",
                                )'''
    new = '''                                after375 = watched_paths(
                                    successor375, candidate375["candidate_commit"]
                                )
                                if after375:
                                    assert_v376_successor(self, after375)
                                else:
                                    self.assertEqual([], after375)'''
    save(name, replace_once(text, old, new, f"{name}:v375-tail"))


def patch_v370(name: str) -> None:
    text = add_import(load(name), name)
    old = '''                            self.assertEqual(
                                [],
                                watched_paths(successor375, candidate375["candidate_commit"]),
                                "verified v375 successor has uncovered watched changes",
                            )'''
    new = '''                            after375 = watched_paths(
                                successor375, candidate375["candidate_commit"]
                            )
                            if after375:
                                assert_v376_successor(self, after375)
                            else:
                                self.assertEqual([], after375)'''
    save(name, replace_once(text, old, new, f"{name}:v375-tail"))


def patch_v371(name: str) -> None:
    text = add_import(load(name), name)
    old = '''                        v375_path = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
                        v375_contract, v375_candidate = _verify_successor(
                            self,
                            v375_path,
                            "2b1112318fa23f4e8edd525695ee3711ea715e18",
                            "d7c8577b514abdbbc15ba9323c4c0deb1945efed",
                            after374,
                        )
                        self.assertEqual(
                            [], watched_paths(v375_contract, v375_candidate["candidate_commit"])
                        )'''
    new = '''                        v375_path = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
                        v375_commit = "d7c8577b514abdbbc15ba9323c4c0deb1945efed"
                        v375_first_hop = watched_paths(
                            v374_contract, v374_candidate["candidate_commit"], v375_commit
                        )
                        v375_contract, v375_candidate = _verify_successor(
                            self,
                            v375_path,
                            "2b1112318fa23f4e8edd525695ee3711ea715e18",
                            v375_commit,
                            v375_first_hop,
                        )
                        after375 = watched_paths(v375_contract, v375_candidate["candidate_commit"])
                        self.assertEqual(
                            sorted(after374), sorted(set(v375_first_hop) | set(after375))
                        )
                        if after375:
                            assert_v376_successor(self, after375)
                        else:
                            self.assertEqual([], after375)'''
    save(name, replace_once(text, old, new, f"{name}:v375-hop"))


def patch_v372(name: str) -> None:
    text = add_import(load(name), name)
    old = '''                    v375_path = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
                    v375_contract, v375_candidate = _verify_successor(
                        self,
                        v375_path,
                        "2b1112318fa23f4e8edd525695ee3711ea715e18",
                        "d7c8577b514abdbbc15ba9323c4c0deb1945efed",
                        after374,
                    )
                    self.assertEqual(
                        [], watched_paths(v375_contract, v375_candidate["candidate_commit"])
                    )'''
    new = '''                    v375_path = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
                    v375_commit = "d7c8577b514abdbbc15ba9323c4c0deb1945efed"
                    v375_first_hop = watched_paths(
                        v374_contract, v374_candidate["candidate_commit"], v375_commit
                    )
                    v375_contract, v375_candidate = _verify_successor(
                        self,
                        v375_path,
                        "2b1112318fa23f4e8edd525695ee3711ea715e18",
                        v375_commit,
                        v375_first_hop,
                    )
                    after375 = watched_paths(v375_contract, v375_candidate["candidate_commit"])
                    self.assertEqual(
                        sorted(after374), sorted(set(v375_first_hop) | set(after375))
                    )
                    if after375:
                        assert_v376_successor(self, after375)
                    else:
                        self.assertEqual([], after375)'''
    save(name, replace_once(text, old, new, f"{name}:v375-hop"))


def patch_v373(name: str) -> None:
    text = add_import(load(name), name)
    old = '''                self.assertEqual(
                    after374,
                    watched_paths(successor375, sc375["base_main_sha"], sc375["candidate_commit"]),
                )
                self.assertEqual([], watched_paths(successor375, sc375["candidate_commit"]))'''
    new = '''                v375_first_hop = watched_paths(
                    successor, sc["candidate_commit"], sc375["candidate_commit"]
                )
                self.assertEqual(
                    v375_first_hop,
                    watched_paths(successor375, sc375["base_main_sha"], sc375["candidate_commit"]),
                )
                after375 = watched_paths(successor375, sc375["candidate_commit"])
                self.assertEqual(
                    sorted(after374), sorted(set(v375_first_hop) | set(after375))
                )
                if after375:
                    assert_v376_successor(self, after375)
                else:
                    self.assertEqual([], after375)'''
    text = replace_once(text, old, new, f"{name}:v375-hop")
    old_cmd = '''            if v374_cmd in main_text:
                self.assertIn('\"tablet_autonomous_evolution_v374.py\"', manifest_text)
            else:
                self.assertIn(v375_cmd, main_text)
                self.assertIn('\"tablet_autonomous_evolution_v375.py\"', manifest_text)'''
    new_cmd = '''            if v374_cmd in main_text:
                self.assertIn('\"tablet_autonomous_evolution_v374.py\"', manifest_text)
            elif v375_cmd in main_text:
                self.assertIn('\"tablet_autonomous_evolution_v375.py\"', manifest_text)
            else:
                v376_cmd = "python tablet_autonomous_evolution_v376.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills"
                self.assertIn(v376_cmd, main_text)
                self.assertIn('\"tablet_autonomous_evolution_v376.py\"', manifest_text)
                assert_v376_successor(
                    self,
                    ["main", "tablet_autonomous_evolution_v376.py", "tablet_runtime_manifest.py"],
                )'''
    save(name, replace_once(text, old_cmd, new_cmd, f"{name}:runtime-route"))


def patch_v374(name: str) -> None:
    text = add_import(load(name), name)
    old = '''        self.assertEqual(sorted(candidate["watched_paths"]), successor_relevant)
        self.assertEqual(relevant, successor_relevant)
        self.assertEqual([], watched_paths(successor, candidate["candidate_commit"]))'''
    new = '''        self.assertEqual(sorted(candidate["watched_paths"]), successor_relevant)
        after375 = watched_paths(successor, candidate["candidate_commit"])
        self.assertEqual(
            sorted(relevant), sorted(set(successor_relevant) | set(after375))
        )
        if after375:
            assert_v376_successor(self, after375)
        else:
            self.assertEqual([], after375)'''
    save(name, replace_once(text, old, new, f"{name}:v375-successor"))


patch_v369(FILES[0])
patch_v370(FILES[1])
patch_v371(FILES[2])
patch_v372(FILES[3])
patch_v373(FILES[4])
patch_v374(FILES[5])
print("V376 historical successor delegation patches applied")
