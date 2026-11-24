#!/usr/bin/env bash
set -euo pipefail

for required in GH_TOKEN GITHUB_REPOSITORY GITHUB_REPOSITORY_OWNER GITHUB_RUN_ID GITHUB_RUN_ATTEMPT GITHUB_SHA GITHUB_WORKFLOW; do
  if [ -z "${!required:-}" ]; then
    echo "PUBLISH_PRECONDITION_MISSING:${required}" >&2
    exit 2
  fi
done

# Fail closed unless this run started from the exact current main commit.
# A workflow dispatched from a stale/non-main ref must never be able to promote
# its local commit into protected main.
git fetch origin +refs/heads/main:refs/remotes/origin/main
run_base_sha="$(git rev-parse "${GITHUB_SHA}^{commit}")"
current_main_sha="$(git rev-parse origin/main)"
if [ "${run_base_sha}" != "${current_main_sha}" ]; then
  echo "BASE_ADVANCED:run_base=${run_base_sha}:current_main=${current_main_sha}" >&2
  exit 20
fi
if ! git merge-base --is-ancestor "${current_main_sha}" HEAD; then
  echo "CANDIDATE_NOT_DESCENDED_FROM_MAIN:${current_main_sha}" >&2
  exit 21
fi

candidate_sha="$(git rev-parse HEAD^{commit})"
if [ "${candidate_sha}" = "${current_main_sha}" ]; then
  echo "NO_CANDIDATE_COMMIT:HEAD still equals main" >&2
  exit 22
fi

candidate_branch="auto/verified-candidate-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
# Publish only an isolated candidate ref; never write main from this helper.
git push origin "HEAD:refs/heads/${candidate_branch}"

# Load the reviewed helper from the base commit, not the candidate working tree.
trusted="$(mktemp -d)"
trap 'rm -rf -- "$trusted"' EXIT
git --no-replace-objects archive "$current_main_sha" execution/deferred_publish_handoff.py execution/deferred_publish_policy.py execution/deferred_publish_tree.py | tar -xf - -C "$trusted"
python -I -c 'import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module("execution.deferred_publish_handoff",run_name="__main__")' "$trusted" code "$current_main_sha" "$candidate_sha" "$candidate_branch"
