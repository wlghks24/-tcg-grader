"""Exact reviewed descendant for ambiguous cross-game HOT identities (V1033)."""
import hashlib
import json
from pathlib import Path
import subprocess
from execution.git_validation_cache import git_validation_output, git_validation_run

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / ".github/tablet-autonomy/hot_game_collision_v1033.json"
EXPECTED = {"schema": "tcg-hot-game-collision/v1033","baseline_commit": "1f5740d9af9aec3b28e5a29f4738db5b52232594","candidate_commit": "e77a2477124ac89578c1a46da245685ca852fb17","file": "box_knowledge_stats.js","before_sha256": "34e54c784ea1b94b694ddc643424b744728cd0bdd2be27865cfacc6e8e682f47","sha256": "bb20e7e21329b3e5cdebca3ecbdaa96477ac030a38eda37d94219950f8911583","bytes": 32690,"physical_tablet_verified": False,"runtime_data_modified": False}

def validate_hot_game_collision_v1033(name, prior_digest=None):
    assert name == EXPECTED["file"], "unreviewed HOT path"
    assert prior_digest in (None, EXPECTED["before_sha256"]), "wrong HOT prior digest"
    assert PROOF.is_file() and not PROOF.is_symlink(), "HOT proof missing or linked"
    assert json.loads(PROOF.read_bytes().decode("utf-8", "strict")) == EXPECTED, "HOT proof changed"

    base, candidate = EXPECTED["baseline_commit"], EXPECTED["candidate_commit"]

    def git(*args):
        command = ["git", *args]
        # Cache only reviewed SHA-to-SHA ancestry and fixed blob content.
        # Never cache candidate-to-HEAD checks or mutable live bytes.
        if args == ("merge-base", "--is-ancestor", base, candidate):
            git_validation_run(command, cwd=ROOT, capture_output=True,
                               check=True, timeout=30)
            return b""
        if (len(args) == 2 and args[0] == "show"
                and args[1].startswith((base + ":", candidate + ":"))):
            return git_validation_output(command, cwd=ROOT, timeout=30)
        return subprocess.check_output(command, cwd=ROOT, timeout=30)
    git("merge-base", "--is-ancestor", base, candidate)
    git("merge-base", "--is-ancestor", candidate, "HEAD")
    assert git("diff", "--name-only", base, candidate).decode().splitlines() == [name]
    before = git("show", base + ":" + name)
    reviewed = git("show", candidate + ":" + name)
    assert hashlib.sha256(before).hexdigest() == EXPECTED["before_sha256"]
    assert hashlib.sha256(reviewed).hexdigest() == EXPECTED["sha256"]
    assert len(reviewed) == EXPECTED["bytes"]

    path = ROOT / name
    assert path.is_file() and not path.is_symlink(), "HOT live path missing or linked"
    current = path.read_bytes()  # Never cache live bytes: tampering must fail.
    assert len(current) == EXPECTED["bytes"] and hashlib.sha256(current).hexdigest() == EXPECTED["sha256"]
    assert current == reviewed == git("show", "HEAD:" + name), "unreviewed live HOT bytes"
    return True
