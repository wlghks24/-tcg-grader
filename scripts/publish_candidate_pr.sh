#!/usr/bin/env bash
set -euo pipefail

for required in GH_TOKEN GITHUB_REPOSITORY GITHUB_RUN_ID GITHUB_RUN_ATTEMPT GITHUB_SHA GITHUB_WORKFLOW; do
  if [ -z "${!required:-}" ]; then
    echo "PUBLISH_PRECONDITION_MISSING:${required}" >&2
    exit 2
  fi
done

# The workflow must have started from the exact current main commit.  If main
# advanced while verification was running, fail closed rather than publishing
# a candidate that was not validated against the current base.
git fetch origin +refs/heads/main:refs/remotes/origin/main
run_base_sha="$(git rev-parse "${GITHUB_SHA}^{commit}")"
current_main_sha="$(git rev-parse origin/main)"
if [ "${run_base_sha}" != "${current_main_sha}" ]; then
  echo "BASE_ADVANCED: run_base=${run_base_sha} current_main=${current_main_sha}" >&2
  exit 20
fi

candidate_branch="auto/verified-candidate-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
candidate_sha="$(git rev-parse HEAD)"
if [ "${candidate_sha}" = "${current_main_sha}" ]; then
  echo "NO_CANDIDATE_COMMIT: HEAD still equals main" >&2
  exit 21
fi

# Never update main here. Publish only a new unique candidate branch.
git push origin "HEAD:refs/heads/${candidate_branch}"

pr_title="${GITHUB_WORKFLOW}: verified candidate ${GITHUB_RUN_ID}"
pr_body="Automated verified candidate from workflow '${GITHUB_WORKFLOW}'.\n\n- base main: ${current_main_sha}\n- candidate: ${candidate_sha}\n- run: ${GITHUB_RUN_ID}/${GITHUB_RUN_ATTEMPT}\n\nDirect writes to main are forbidden. Merge only after repository required checks pass."

existing_url="$(gh pr list --repo "${GITHUB_REPOSITORY}" --state open --head "${candidate_branch}" --json url --jq '.[0].url // empty')"
if [ -n "${existing_url}" ]; then
  echo "candidate_pr=${existing_url}"
  exit 0
fi

pr_url="$(gh pr create --repo "${GITHUB_REPOSITORY}" --base main --head "${candidate_branch}" --title "${pr_title}" --body "${pr_body}")"
echo "candidate_pr=${pr_url}"
