#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def replace_once(text,old,new,label):
    if new in text:
        return text
    count=text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}")
    return text.replace(old,new,1)


def patch_android(text):
    old='''restore_runtime_snapshot() {
  snapshot="$1"
  manifest="$snapshot/manifest.tsv"
  [ -f "$manifest" ] || return 0
  restore_ok=1
  while IFS='|' read -r kind changed; do
    [ -n "$changed" ] || continue
    if [ "$kind" = "FILE" ]; then
      mkdir -p "$(dirname "$changed")" 2>/dev/null || restore_ok=0
      rm -f "$changed" 2>/dev/null || restore_ok=0
      cp -p "$snapshot/files/$changed" "$changed" 2>/dev/null || restore_ok=0
    elif [ "$kind" = "DELETED" ]; then
      rm -f "$changed" 2>/dev/null || restore_ok=0
    fi
  done < "$manifest"
  [ "$restore_ok" = "1" ]
}
'''
    new='''restore_runtime_snapshot() {
  snapshot="$1"
  manifest="$snapshot/manifest.tsv"
  # A missing/tampered manifest is a restore failure, never a successful no-op.
  [ -d "$snapshot" ] && [ ! -L "$snapshot" ] || return 1
  [ -f "$manifest" ] && [ ! -L "$manifest" ] || return 1
  restore_ok=1
  while IFS='|' read -r kind changed; do
    [ -n "$changed" ] || continue
    # The manifest is local state. Even if it is corrupted or replaced, it may
    # never make the updater overwrite/delete files outside the runtime allowlist.
    if ! is_runtime_path "$changed"; then
      restore_ok=0
      continue
    fi
    if [ "$kind" = "FILE" ]; then
      source_file="$snapshot/files/$changed"
      if [ -L "$source_file" ] || [ ! -f "$source_file" ]; then
        restore_ok=0
        continue
      fi
      restore_tmp=".${changed}.tcg-restore.$$"
      rm -f "$restore_tmp" 2>/dev/null || restore_ok=0
      if cp -p "$source_file" "$restore_tmp" 2>/dev/null; then
        # mv replaces a destination symlink itself instead of following it,
        # closing the rm+cp symlink race window on the restored runtime file.
        mv -f "$restore_tmp" "$changed" 2>/dev/null || restore_ok=0
      else
        restore_ok=0
      fi
      rm -f "$restore_tmp" 2>/dev/null || true
    elif [ "$kind" = "DELETED" ]; then
      rm -f "$changed" 2>/dev/null || restore_ok=0
    else
      restore_ok=0
    fi
  done < "$manifest"
  [ "$restore_ok" = "1" ]
}
'''
    text=replace_once(text,old,new,'harden restore manifest')
    old='''  stamp="$(date +%Y%m%d_%H%M%S 2>/dev/null || date +%s)"
  mkdir -p "$RUNTIME_BACKUP_DIR" || return 1
  snapshot="$(mktemp -d "$RUNTIME_BACKUP_DIR/${stamp}_${before}_to_${remote_short}_XXXXXX")" || return 1
'''
    new='''  stamp="$(date +%Y%m%d_%H%M%S 2>/dev/null || date +%s)"
  if [ -L "$RUNTIME_BACKUP_DIR" ]; then
    echo "[안전] 런타임 보존 폴더가 심볼릭 링크라 업데이트를 중단합니다."
    return 1
  fi
  mkdir -p "$RUNTIME_BACKUP_DIR" || return 1
  snapshot="$(mktemp -d "$RUNTIME_BACKUP_DIR/${stamp}_${before}_to_${remote_short}_XXXXXX")" || return 1
'''
    return replace_once(text,old,new,'reject backup-dir symlink')


def patch_verify(text):
    old='''grep -Fq 'mktemp -d "$RUNTIME_BACKUP_DIR/' ANDROID_UPDATE_AND_START.sh
grep -Fq 'if [ -L "$changed" ]; then' ANDROID_UPDATE_AND_START.sh
grep -Fq 'fatal_restore_error=1' ANDROID_UPDATE_AND_START.sh
'''
    new='''grep -Fq 'mktemp -d "$RUNTIME_BACKUP_DIR/' ANDROID_UPDATE_AND_START.sh
grep -Fq 'if [ -L "$RUNTIME_BACKUP_DIR" ]; then' ANDROID_UPDATE_AND_START.sh
grep -Fq 'if [ -L "$changed" ]; then' ANDROID_UPDATE_AND_START.sh
grep -Fq 'if ! is_runtime_path "$changed"; then' ANDROID_UPDATE_AND_START.sh
grep -Fq '[ -f "$manifest" ] && [ ! -L "$manifest" ] || return 1' ANDROID_UPDATE_AND_START.sh
grep -Fq 'restore_tmp=".${changed}.tcg-restore.$$"' ANDROID_UPDATE_AND_START.sh
grep -Fq 'fatal_restore_error=1' ANDROID_UPDATE_AND_START.sh
'''
    return replace_once(text,old,new,'tablet snapshot integrity contracts')


def main():
    targets={'ANDROID_UPDATE_AND_START.sh':patch_android,'VERIFY_TABLET_FINAL.sh':patch_verify}
    changed=[]
    for name,fn in targets.items():
        path=ROOT/name
        before=path.read_text(encoding='utf-8')
        after=fn(before)
        if after != before:
            path.write_text(after,encoding='utf-8')
            changed.append(name)
    print('Android snapshot v3 changed: '+(', '.join(changed) if changed else 'none'))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
