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

owner="${GITHUB_REPOSITORY_OWNER}"
pr_number="$(gh api -X GET "repos/${GITHUB_REPOSITORY}/pulls" \
  -f state=open -f head="${owner}:${candidate_branch}" -f base=main \
  --jq '.[0].number // empty')"
if [ -z "${pr_number}" ]; then
  title="${GITHUB_WORKFLOW}: verified candidate ${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
  body="Protected-main candidate. Base: ${current_main_sha}. Candidate: ${candidate_sha}. Run: ${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}. Direct/force writes to main are forbidden; merge only after all required checks succeed."
  if ! pr_json="$(gh api --method POST "repos/${GITHUB_REPOSITORY}/pulls" \
      -f title="${title}" -f head="${candidate_branch}" -f base=main -f body="${body}" 2>/tmp/publish-candidate-pr.err)"; then
    cat /tmp/publish-candidate-pr.err >&2 || true
    echo "PENDING_EXTERNAL_PR:${candidate_branch}:${candidate_sha}" >&2
    exit 23
  fi
  pr_number="$(printf '%s' "${pr_json}" | jq -r '.number')"
fi
printf 'candidate_pr=%s\n' "${pr_number}"

required_workflows=(
  tablet-gpt-tcg-grader-main-alignment.yml
  repository-integrity-guard.yml
  selfrefine-full-repo.yml
  deep-selfrefine-guard.yml
  exhaustive-selfrefine-guard.yml
  tablet-termux-main-guard.yml
  android-updater-guard.yml
)
for workflow in "${required_workflows[@]}"; do
  gh api --method POST "repos/${GITHUB_REPOSITORY}/actions/workflows/${workflow}/dispatches" -f ref="${candidate_branch}"
done

required_checks=(
  'Tablet GPT TCG Grader Main Alignment'
  'Repository Integrity Guard'
  'Main SELFREFINE'
  'Deep SELFREFINE Guard'
  'Exhaustive SELFREFINE Guard'
  'Tablet Termux Main Guard'
  'Android Updater Guard'
)

deadline=$((SECONDS + 900))
while (( SECONDS < deadline )); do
  checks="$(gh api -H 'Accept: application/vnd.github+json' \
    "repos/${GITHUB_REPOSITORY}/commits/${candidate_sha}/check-runs?per_page=100")"
  pending=0
  failed=0
  for name in "${required_checks[@]}"; do
    state="$(printf '%s' "${checks}" | jq -r --arg name "${name}" \
      '[.check_runs[] | select(.name == $name)] | sort_by(.started_at // "") | last | if . == null then "missing" elif .status != "completed" then .status else (.conclusion // "unknown") end')"
    printf '%s: %s\n' "${name}" "${state}"
    case "${state}" in
      success) ;;
      failure|cancelled|timed_out|action_required|stale|skipped|neutral) failed=1 ;;
      *) pending=1 ;;
    esac
  done
  if (( failed )); then
    echo "REQUIRED_CHECK_FAILED:${candidate_sha}" >&2
    exit 24
  fi
  if (( ! pending )); then
    break
  fi
  sleep 20
done
if (( SECONDS >= deadline )); then
  echo "REQUIRED_CHECK_TIMEOUT:${candidate_sha}" >&2
  exit 25
fi

# The verified candidate is mergeable only while its exact validated base is
# still current.  Never rebase/reset/force a stale candidate into main.
git fetch origin +refs/heads/main:refs/remotes/origin/main
if [ "$(git rev-parse origin/main)" != "${current_main_sha}" ]; then
  echo "BASE_ADVANCED_BEFORE_MERGE:base=${current_main_sha}:current=$(git rev-parse origin/main)" >&2
  exit 26
fi

merge_json="$(gh api --method PUT "repos/${GITHUB_REPOSITORY}/pulls/${pr_number}/merge" \
  -f merge_method=merge -f sha="${candidate_sha}")"
if [ "$(printf '%s' "${merge_json}" | jq -r '.merged')" != 'true' ]; then
  printf '%s\n' "${merge_json}" >&2
  echo "MERGE_REJECTED:${pr_number}:${candidate_sha}" >&2
  exit 27
fi
merged_sha="$(printf '%s' "${merge_json}" | jq -r '.sha // empty')"
printf 'merged_pr=%s\nmerged_sha=%s\n' "${pr_number}" "${merged_sha}"

# Cleanup failure must never turn a successful protected-main merge into a
# forceful recovery attempt.
git push origin --delete "${candidate_branch}" || true
