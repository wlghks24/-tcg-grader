#!/data/data/com.termux/files/usr/bin/bash
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
if [ -n "${TCG_REPO_DIR:-}" ] && [ -d "${TCG_REPO_DIR}/.git" ]; then
  cd "$TCG_REPO_DIR"
elif [ -n "$SCRIPT_DIR" ]; then
  cd "$SCRIPT_DIR"
fi

# Safe tablet updater. Device-local ignored learning/photos are never reset.
# Tracked runtime JSON may change while the server is running. Before a fast-
# forward those known runtime files are snapshotted, restored to the tracked
# baseline, then the checkout advances to the verified official main. A remotely
# bootstrapped copy of this updater is also recognized as safe so an old tablet
# can repair the updater itself without being trapped by its own local modification.
UPDATE_LOCK_DIR=".tcg_android_update.lock"
UPDATE_LOCK_PID="$UPDATE_LOCK_DIR/pid"
RUNTIME_BACKUP_DIR=".tcg_runtime_preserved"
SELF_PATH="ANDROID_UPDATE_AND_START.sh"
OFFICIAL_REPO="wlghks24/-tcg-grader"
OFFICIAL_HTTPS="https://github.com/wlghks24/-tcg-grader.git"

is_official_origin() {
  case "${1:-}" in
    https://github.com/wlghks24/-tcg-grader|https://github.com/wlghks24/-tcg-grader.git|https://github.com/wlghks24/-tcg-grader/|https://github.com/wlghks24/-tcg-grader.git/|git@github.com:wlghks24/-tcg-grader|git@github.com:wlghks24/-tcg-grader.git|ssh://git@github.com/wlghks24/-tcg-grader|ssh://git@github.com/wlghks24/-tcg-grader.git)
      return 0 ;;
    *) return 1 ;;
  esac
}

cleanup_update_lock() {
  rm -rf "$UPDATE_LOCK_DIR" 2>/dev/null || true
}

acquire_update_lock() {
  if mkdir "$UPDATE_LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$UPDATE_LOCK_PID"
    return 0
  fi
  old_pid=""
  if [ -r "$UPDATE_LOCK_PID" ]; then
    old_pid="$(cat "$UPDATE_LOCK_PID" 2>/dev/null || true)"
  fi
  case "$old_pid" in
    ''|*[!0-9]*) old_pid="" ;;
  esac
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    echo "[OK] Android 업데이트 작업이 이미 실행 중입니다(PID $old_pid)."
    exit 0
  fi
  rm -rf "$UPDATE_LOCK_DIR" 2>/dev/null || true
  mkdir "$UPDATE_LOCK_DIR" 2>/dev/null || {
    echo "[안내] 업데이트 잠금을 만들 수 없어 현재 버전으로 서버를 시작합니다."
    return 1
  }
  printf '%s\n' "$$" > "$UPDATE_LOCK_PID"
}

is_runtime_path() {
  case "$1" in
    tcg_live_data.json|releases.json|market_watch.json|market_prices.json|promo_events.json|purchase_sources.json|purchase_signals.json|social_stock_signals.json|exchange_rates.json|graded_photo_candidates.json|supplementary_candidates.json|social_event_candidates.json|web_discovery_candidates.json|link_health_report.json|auto_update_report.json|auto_update_issues.json|auto_repair_memory.json|adaptive_collection_stats.json|adaptive_collection_stats.json.bak|verified_certifications.json|learning_store.json|vision_self_learning_report.json|vision_calibration.json|ebay_grader_candidates.json|card_identity_learning.json|source_collection_stats.json|source_collection_stats.json.bak|precollect_status.json|graded_photo_reference_learning.json|library_verified_slab_references.json|graded_photo_source_learning.json|verified_slab_raw_learning_v155.json|verified_slab_training_archive.json|event_gap_learning.json|existing_photo_revalidation_v160.json|manual_collected_pair_queue.json|manual_official_proof_references.json|market_public_crosscheck_state.json|pending_official_candidate_rejections.json|box_hit_market_candidates.json|box_hit_market_learning.json|collector_self_heal_memory.json|graded_file_learning_report.json|graded_photo_official_cache.json|release_history_progress.json|manual_event_evidence.json|release_parser_learning.json)
      return 0 ;;
    *) return 1 ;;
  esac
}

append_line() {
  current="$1"
  value="$2"
  if [ -n "$current" ]; then
    printf '%s\n%s' "$current" "$value"
  else
    printf '%s' "$value"
  fi
}

restore_runtime_snapshot() {
  snapshot="$1"
  manifest="$snapshot/manifest.tsv"
  [ -f "$manifest" ] || return 0
  while IFS='|' read -r kind changed; do
    [ -n "$changed" ] || continue
    if [ "$kind" = "FILE" ]; then
      mkdir -p "$(dirname "$changed")" 2>/dev/null || true
      cp -p "$snapshot/files/$changed" "$changed" 2>/dev/null || true
    elif [ "$kind" = "DELETED" ]; then
      rm -f "$changed" 2>/dev/null || true
    fi
  done < "$manifest"
}

backup_and_normalize_runtime() {
  runtime_paths="$1"
  remote_short="$2"
  snapshot=""
  [ -n "$runtime_paths" ] || return 0

  stamp="$(date +%Y%m%d_%H%M%S 2>/dev/null || date +%s)"
  snapshot="$RUNTIME_BACKUP_DIR/${stamp}_${before}_to_${remote_short}"
  mkdir -p "$snapshot/files" || return 1
  : > "$snapshot/manifest.tsv"
  printf 'from=%s\nto=%s\ncreated_at=%s\n' "$before" "$remote_short" "$stamp" > "$snapshot/meta.txt"

  snapshot_ok=1
  while IFS= read -r changed; do
    [ -n "$changed" ] || continue
    if [ -e "$changed" ]; then
      mkdir -p "$snapshot/files/$(dirname "$changed")" || snapshot_ok=0
      cp -p "$changed" "$snapshot/files/$changed" || snapshot_ok=0
      printf 'FILE|%s\n' "$changed" >> "$snapshot/manifest.tsv"
    else
      printf 'DELETED|%s\n' "$changed" >> "$snapshot/manifest.tsv"
    fi
  done <<EOF
$runtime_paths
EOF

  if [ "$snapshot_ok" != "1" ]; then
    echo "[안전] 로컬 런타임 자료 백업에 실패하여 업데이트를 중단합니다."
    return 1
  fi

  echo "[OK] 로컬 런타임 변경 백업 완료: $snapshot"
  while IFS= read -r changed; do
    [ -n "$changed" ] || continue
    if ! git restore --worktree --source=HEAD -- "$changed"; then
      echo "[안전] $changed 기준복원 실패 · 원본 자료를 되돌리고 업데이트를 중단합니다."
      restore_runtime_snapshot "$snapshot"
      return 1
    fi
  done <<EOF
$runtime_paths
EOF
  return 0
}

LOCKED=0
if acquire_update_lock; then
  LOCKED=1
fi
trap '[ "${LOCKED:-0}" = "1" ] && cleanup_update_lock || true' EXIT INT TERM

before="local"
after="local"
updated=0
snapshot=""

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git config --local core.fileMode false >/dev/null 2>&1 || true

  before="$(git rev-parse --short=8 HEAD 2>/dev/null || echo local)"
  branch="$(git branch --show-current 2>/dev/null || true)"
  can_update=1
  remote_ready=0
  runtime_dirty_paths=""
  bootstrap_dirty_paths=""

  if [ "$branch" != "main" ]; then
    echo "[안내] 현재 브랜치가 main이 아닙니다(${branch:-detached}). 자동 업데이트는 건너뜁니다."
    can_update=0
  elif ! git diff --cached --quiet --ignore-submodules --; then
    echo "[안전] staged 변경이 있어 자동 업데이트를 건너뜁니다. 사용자가 준비한 변경은 자동으로 건드리지 않습니다."
    can_update=0
  fi

  if [ "$can_update" = "1" ]; then
    origin_url="$(git remote get-url origin 2>/dev/null || true)"
    if ! is_official_origin "$origin_url"; then
      echo "[안전] origin 원격 저장소가 공식 TCG 저장소($OFFICIAL_REPO)가 아닙니다."
      echo "       현재 origin: ${origin_url:-없음}"
      echo "       원격 코드는 받지 않고 현재 검증된 로컬 버전으로 시작합니다."
      can_update=0
    fi
  fi

  if [ "$can_update" = "1" ]; then
    echo "[업데이트] 공식 GitHub main 최신 상태를 확인합니다..."
    # Fetch from the pinned canonical repository URL, not a mutable local remote.
    if git fetch --prune "$OFFICIAL_HTTPS" main:refs/remotes/origin/main; then
      remote_ready=1
    else
      echo "[안내] 네트워크/GitHub 연결 문제로 업데이트 확인을 건너뜁니다. 현재 버전으로 시작합니다."
      can_update=0
    fi
  fi

  if [ "$can_update" = "1" ] && [ "$remote_ready" = "1" ]; then
    dirty_paths="$(git diff --name-only --ignore-submodules --)"
    unsafe_paths=""
    if [ -n "$dirty_paths" ]; then
      while IFS= read -r changed; do
        [ -z "$changed" ] && continue
        if is_runtime_path "$changed"; then
          runtime_dirty_paths="$(append_line "$runtime_dirty_paths" "$changed")"
        elif [ "$changed" = "$SELF_PATH" ] && git diff --quiet origin/main -- "$changed"; then
          bootstrap_dirty_paths="$(append_line "$bootstrap_dirty_paths" "$changed")"
        else
          unsafe_paths="${unsafe_paths}${unsafe_paths:+, }$changed"
        fi
      done <<EOF
$dirty_paths
EOF
    fi

    if [ -n "$unsafe_paths" ]; then
      echo "[안전] 코드/설정 추적파일에 로컬 수정이 있어 자동 업데이트를 건너뜁니다: $unsafe_paths"
      can_update=0
    fi
    if [ -n "$runtime_dirty_paths" ]; then
      echo "[OK] 정상 수집/학습으로 변경된 런타임 JSON만 감지했습니다. 충돌 시 자동 보존 후 최신 main으로 진행합니다."
    fi
    if [ -n "$bootstrap_dirty_paths" ]; then
      echo "[OK] 원격 main과 동일한 Android 업데이트 스크립트를 감지했습니다. 자기복구용 변경으로 안전하게 인정합니다."
    fi
  fi

  if [ "$can_update" = "1" ] && [ "$remote_ready" = "1" ]; then
    local_head="$(git rev-parse HEAD 2>/dev/null || true)"
    remote_head="$(git rev-parse origin/main 2>/dev/null || true)"
    if [ -n "$remote_head" ] && [ "$local_head" != "$remote_head" ]; then
      remote_short="$(git rev-parse --short=8 origin/main 2>/dev/null || echo remote)"

      if [ -n "$runtime_dirty_paths" ]; then
        if ! backup_and_normalize_runtime "$runtime_dirty_paths" "$remote_short"; then
          can_update=0
        else
          snapshot="$(find "$RUNTIME_BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n 1)"
        fi
      fi

      if [ "$can_update" = "1" ] && [ -n "$bootstrap_dirty_paths" ]; then
        while IFS= read -r changed; do
          [ -n "$changed" ] || continue
          if ! git restore --worktree --source=HEAD -- "$changed"; then
            echo "[안전] 자기복구 스크립트 기준복원 실패로 업데이트를 중단합니다: $changed"
            can_update=0
            break
          fi
        done <<EOF
$bootstrap_dirty_paths
EOF
      fi

      if [ "$can_update" = "1" ]; then
        if git merge --ff-only origin/main; then
          updated=1
          if [ -n "$runtime_dirty_paths" ]; then
            echo "[OK] 충돌하던 추적 런타임 JSON은 보존본을 남기고 원격 검증자료를 적용했습니다."
            echo "[OK] 수동등록/학습/검사사진 등 기기 로컬 자료는 건드리지 않았습니다."
          fi
          if [ -n "$bootstrap_dirty_paths" ]; then
            echo "[OK] Android 업데이트 스크립트 자기복구 완료. 이후 업데이트는 일반 실행으로 처리됩니다."
          fi
        else
          echo "[안전] main fast-forward 실패. 보존한 로컬 런타임 자료를 원래 상태로 복원합니다."
          if [ -n "$snapshot" ]; then
            restore_runtime_snapshot "$snapshot"
          fi
          if [ -n "$bootstrap_dirty_paths" ]; then
            git restore --worktree --source=origin/main -- "$SELF_PATH" 2>/dev/null || true
          fi
        fi
      fi
    else
      echo "[OK] 이미 최신 main입니다."
    fi
  fi

  after="$(git rev-parse --short=8 HEAD 2>/dev/null || echo local)"
fi

if [ "$updated" = "1" ]; then
  echo "[OK] Android 코드 업데이트 완료: $before -> $after"
else
  echo "[OK] Android 실행 빌드: $after"
fi

if [ ! -s "START_TCG_UPDATER_ANDROID.sh" ]; then
  echo "[오류] START_TCG_UPDATER_ANDROID.sh 파일이 없습니다."
  exit 1
fi

if [ "${LOCKED:-0}" = "1" ]; then
  cleanup_update_lock
  LOCKED=0
fi

exec bash START_TCG_UPDATER_ANDROID.sh
