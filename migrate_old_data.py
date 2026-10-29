#!/usr/bin/env python3
"""Safely merge user learning/recovery records from an older TCG_GRADER folder."""
from __future__ import annotations
import datetime as dt, json, math, secrets, sys
from pathlib import Path
from safe_runtime import atomic_write_bytes, atomic_write_json, bounded_int as safe_int, safe_read_bytes, safe_read_text, exclusive_file_lock

FILES=('learning_store.json','auto_repair_memory.json','verification_history.json','tcg_live_data.json')
VERIFICATION_HISTORY_LIMIT=24
VERIFICATION_FULL_DETAIL_LIMIT=8

def _event_time(row):
    if not isinstance(row,dict):return ''
    return str(row.get('last_seen') or row.get('last_run') or row.get('timestamp') or '')

def read_json(path,default):
    try:return json.loads(safe_read_text(path))
    except (OSError,ValueError,TypeError):return default

def _strict_migration_pairs(pairs):
    # JSON's normal duplicate-key last-wins rule can silently remove the first
    # confirmed_samples/official grade before conflict detection sees it.
    data={}
    for key,value in pairs:
        if key in data:
            raise ValueError('migration_duplicate_json_key')
        data[key]=value
    return data

def _reject_migration_nonfinite(value):
    # NaN/Infinity are not JSON and cannot be trusted calibration evidence.
    raise ValueError('migration_nonfinite_json_value: '+value)

def read_migration_source(path):
    """Existing user learning/recovery data must never silently become {}."""
    if path.is_symlink():
        raise ValueError('migration_source_symlink_blocked')
    if not path.exists():
        return {}
    try:
        data=json.loads(safe_read_text(path),object_pairs_hook=_strict_migration_pairs,
                        parse_constant=_reject_migration_nonfinite)
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        raise ValueError('migration_source_unreadable_or_invalid_json: '+path.name) from exc
    if not isinstance(data,dict):
        raise ValueError('migration_source_must_be_object: '+path.name)
    return data

def write_json(path,data):
    atomic_write_json(path,data,suffix='.migrate.tmp')

def copy_safe_file(source,destination):
    atomic_write_bytes(destination,safe_read_bytes(source),suffix='.migration-copy.tmp')

def copy_safe_tree(source,destination):
    if source.is_symlink() or destination.is_symlink():
        raise ValueError('심볼릭 링크 복구자료 폴더는 허용되지 않습니다.')
    destination.mkdir(parents=True,exist_ok=False)
    for item in source.rglob('*'):
        if item.is_symlink():
            raise ValueError('심볼릭 링크 복구자료는 허용되지 않습니다.')
        target=destination/item.relative_to(source)
        if item.is_dir():target.mkdir(parents=True,exist_ok=True)
        elif item.is_file():copy_safe_file(item,target)
        else:raise ValueError('일반 파일이 아닌 복구자료는 허용되지 않습니다.')

def rows_merged(new_rows,old_rows,limit=500):
    # Legacy V11/V30 evidence may share a timestamp, grader and grade while
    # representing different real cards or certifications. The coarse four-
    # column key discarded such distinct rows during version migration.
    return merge_v99_rows(new_rows,old_rows,limit=limit)

def merge_v99_rows(new_rows,old_rows,limit=1000):
    """Preserve distinct official-grade evidence without silently merging conflicts.

    The V99 learner deduplicates by certification and quarantines contradictory
    official grades. Migration must not collapse different certificates merely
    because the older v30 (time, company, actual, pred) key is absent.
    """
    seen=set()
    merged=[]
    old_rows=old_rows if isinstance(old_rows,list) else []
    new_rows=new_rows if isinstance(new_rows,list) else []
    # Do not silently erase malformed entries from historical V11/V30/V99
    # evidence; preserve both original files for manual review instead.
    if any(not isinstance(row,dict) for row in [*old_rows,*new_rows]):
        raise ValueError('migration_validation_row_must_be_object')
    for row in [*old_rows,*new_rows]:
        fingerprint=json.dumps(row,ensure_ascii=False,sort_keys=True)
        if fingerprint in seen:continue
        seen.add(fingerprint)
        merged.append(row)
    # History migration must never silently discard distinct verified evidence.
    # Its training window is a separate model concern; reject an over-capacity
    # migration without changing the old/new source files.
    if len(merged)>limit:
        raise ValueError('learning_evidence_capacity_exceeded')
    return merged



def merge_confirmed_rows(new_rows,old_rows,limit=2000):
    """Refuse ambiguous official grades before a later learner can pick one.

    V40 learning deduplication uses company/certificate identity and may pick
    the last matching sample. Migration has no proof that either disagreeing
    grade supersedes the other; abort before writing files instead.
    """
    old_rows=old_rows if isinstance(old_rows,list) else []
    new_rows=new_rows if isinstance(new_rows,list) else []
    # Never silently discard malformed rows from official confirmed evidence.
    # A historical bad row must remain available for manual recovery.
    if any(not isinstance(row,dict) for row in [*old_rows,*new_rows]):
        raise ValueError('migration_confirmed_sample_must_be_object')
    grades={}
    for row in [*old_rows,*new_rows]:
        company=str(row.get('company') or row.get('grader') or '').strip().upper()
        cert=str(row.get('cert_no') or row.get('cert') or '').strip()
        if not company or not cert:continue
        raw=row.get('actual_grade',row.get('actual'))
        try:
            value=float(raw) if not isinstance(raw,bool) else None
            value=value if value is not None and math.isfinite(value) else None
        except (TypeError,ValueError,OverflowError):
            value=None
        key=(company,cert)
        if key in grades and (value is None or grades[key] is None
                              or abs(value-grades[key])>1e-9):
            raise ValueError('confirmed_sample_cert_grade_conflict')
        grades[key]=value
    return merge_v99_rows(new_rows,old_rows,limit=limit)


def merge_learning(new,old):
    new=new if isinstance(new,dict) else {}
    old=old if isinstance(old,dict) else {}
    # A present but malformed V40 label collection is NOT an empty history.
    # Refuse to overwrite it with [] before a reviewer can recover the source.
    for source in (old,new):
        if 'confirmed_samples' in source and not isinstance(source['confirmed_samples'],list):
            raise ValueError('migration_confirmed_samples_must_be_list')
    # Preserve unknown newer schema fields as well as the V99 verified labels.
    # A migration is not allowed to silently drop future learning evidence.
    result={**old,**new}
    result.update({
        'version':max(safe_int(new.get('version'),1,1,999),safe_int(old.get('version'),1,1,999)),
        'updated_at':max(str(new.get('updated_at') or ''),str(old.get('updated_at') or '')) or None,
        'v30_validation':rows_merged(new.get('v30_validation',[]),old.get('v30_validation',[])),
        'v11_validation':rows_merged(new.get('v11_validation',[]),old.get('v11_validation',[])),
        'v99_validation':merge_v99_rows(new.get('v99_validation',[]),old.get('v99_validation',[])),
        # V40 introduced confirmed_samples; like V99 evidence, these must be
        # merged by full identity rather than the old v30 time/pred tuple.
        'confirmed_samples':merge_confirmed_rows(
            new.get('confirmed_samples',[]),old.get('confirmed_samples',[]),limit=2000),
    })
    return result

def merge_history(new,old):
    new=new if isinstance(new,dict) else {};old=old if isinstance(old,dict) else {}
    # Verification failures are forensic evidence. Never convert a malformed
    # present run list or one of its elements to an empty/partial history.
    # Reject before any backup or destination write can be started.
    for source in (old,new):
        if 'runs' in source:
            if not isinstance(source['runs'],list):
                raise ValueError('migration_verification_runs_must_be_list')
            if any(not isinstance(run,dict) for run in source['runs']):
                raise ValueError('migration_verification_run_must_be_object')
    unique={}
    for run in [*(old.get('runs') if isinstance(old.get('runs'),list) else []),*(new.get('runs') if isinstance(new.get('runs'),list) else [])]:
        if not isinstance(run,dict):continue
        # All retained provenance matters. Two same-second runs with the
        # same checks and result but distinct review IDs / signing receipts
        # are independent evidence; deduplicate only byte-equivalent JSON
        # objects (regardless of key ordering).
        key=json.dumps(run,ensure_ascii=False,sort_keys=True)
        unique[key]=run
    # Index the full-detail records once instead of scanning them for each
    # compacted row (quadratic with large verification histories).
    # Compare every surviving metadata field, not just time/pass/fail: a
    # different source ID or review result is independent audit evidence.
    def verification_summary(row, count):
        metadata={key:value for key,value in row.items()
                  if key not in ('checks','check_count','details_compacted')}
        return json.dumps([metadata,count],ensure_ascii=False,sort_keys=True)

    detailed_index={}
    for detail_key,detail in unique.items():
        if detail.get('details_compacted') is True:
            continue
        checks=detail.get('checks')
        if isinstance(checks,list):
            summary=verification_summary(detail,len(checks))
            detailed_index.setdefault(summary,[]).append(detail_key)
    # Never guess when two different full-detail runs have the same compact
    # representation. Ambiguity must fail before backup or destination writes.
    for compact_key,compact in list(unique.items()):
        if compact.get('details_compacted') is not True:
            continue
        count=compact.get('check_count')
        if type(count) is not int or count < 0:
            raise ValueError('migration_compacted_verification_invalid_count')
        candidates=detailed_index.get(verification_summary(compact,count),[])
        if len(candidates)>1:
            raise ValueError('migration_compacted_verification_ambiguous')
        if len(candidates)==1:
            del unique[compact_key]
    all_runs=sorted(unique.values(),key=lambda x:str(x.get('checked_at','')))
    runs=all_runs[-VERIFICATION_HISTORY_LIMIT:]
    for index,row in enumerate(runs[:-VERIFICATION_FULL_DETAIL_LIMIT]):
        checks=row.get('checks') if isinstance(row.get('checks'),list) else []
        if checks:
            compact=dict(row);compact['check_count']=len(checks);compact['checks']=[];compact['details_compacted']=True
            runs[index]=compact
    updated=max([str(new.get('updated_at') or ''),str(old.get('updated_at') or ''),*[str(x.get('checked_at') or '') for x in runs]]) or None
    lifetime_runs=max(len(all_runs),safe_int(new.get('lifetime_runs')),safe_int(old.get('lifetime_runs')))
    passed=max(sum(safe_int(x.get('pass_count')) for x in all_runs),safe_int(new.get('lifetime_passed_checks')),safe_int(old.get('lifetime_passed_checks')))
    failed=max(sum(safe_int(x.get('failure_count')) for x in all_runs),safe_int(new.get('lifetime_failed_checks')),safe_int(old.get('lifetime_failed_checks')))
    return {'version':2,'runs':runs,'updated_at':updated,'retention_limit':VERIFICATION_HISTORY_LIMIT,
            'full_detail_limit':VERIFICATION_FULL_DETAIL_LIMIT,'lifetime_runs':lifetime_runs,
            'lifetime_passed_checks':passed,'lifetime_failed_checks':failed,
            'pruned_runs':max(0,lifetime_runs-len(runs))}

def max_count(a,b,key):
    a=a if isinstance(a,dict) else {};b=b if isinstance(b,dict) else {}
    return max(safe_int(a.get(key),0),safe_int(b.get(key),0))

def _merge_monitor_history(new,old,limit=500):
    rows=[];seen=set()
    for row in [*(old if isinstance(old,list) else []),*(new if isinstance(new,list) else [])]:
        if not isinstance(row,dict):continue
        key=(str(row.get('timestamp','')),str(row.get('function','')),str(row.get('error_type','')),str(row.get('error_message','')),str(row.get('attempt','')))
        if key in seen:continue
        seen.add(key);rows.append(row)
    rows.sort(key=lambda x:str(x.get('timestamp','')))
    return rows[-limit:]

def merge_memory(new,old):
    # v74: malformed legacy counters must never abort migration, and v58+ monitor
    # learning must not disappear when moving to a newer folder.
    new=new if isinstance(new,dict) else {};old=old if isinstance(old,dict) else {}
    # A malformed but readable repair log is not empty evidence. Refuse to
    # discard failure/rollback records, including nested resolution events.
    # This validation is invoked during migration's preflight, before backups
    # or destination writes; legacy absent fields remain supported.
    for source in (old,new):
        if 'new_error_log' in source:
            log=source['new_error_log']
            if not isinstance(log,list):
                raise ValueError('migration_new_error_log_must_be_list')
            if any(not isinstance(row,dict) for row in log):
                raise ValueError('migration_new_error_row_must_be_object')
        if 'error_groups' in source:
            groups=source['error_groups']
            if not isinstance(groups,dict):
                raise ValueError('migration_error_groups_must_be_object')
            for group in groups.values():
                if not isinstance(group,dict):
                    raise ValueError('migration_error_group_must_be_object')
                if 'resolution_history' in group:
                    history=group['resolution_history']
                    if not isinstance(history,list):
                        raise ValueError('migration_resolution_history_must_be_list')
                    if any(not isinstance(event,dict) for event in history):
                        raise ValueError('migration_resolution_event_must_be_object')
    out={**old,**new}
    out.update({'version':max(safe_int(new.get('version'),1,1,999),safe_int(old.get('version'),1,1,999)),
         'updated_at':max(str(new.get('updated_at') or ''),str(old.get('updated_at') or '')) or None,
         'total_runs':max(safe_int(new.get('total_runs')),safe_int(old.get('total_runs'))),
         'patterns':{},'error_groups':{},'new_error_log':[],
         'files':{},'monitor_known_errors':{}})
    np=new.get('patterns') if isinstance(new.get('patterns'),dict) else {};op=old.get('patterns') if isinstance(old.get('patterns'),dict) else {}
    for key in set(np)|set(op):
        n=np.get(key,{}) if isinstance(np.get(key,{}),dict) else {};o=op.get(key,{}) if isinstance(op.get(key,{}),dict) else {}
        chosen=n if _event_time(n)>=_event_time(o) else o
        out['patterns'][key]={**o,**n,**chosen,'occurrences':max_count(n,o,'occurrences'),'successful_repairs':max_count(n,o,'successful_repairs')}
    nf=new.get('files') if isinstance(new.get('files'),dict) else {};of=old.get('files') if isinstance(old.get('files'),dict) else {}
    for key in set(nf)|set(of):
        n=nf.get(key,{}) if isinstance(nf.get(key,{}),dict) else {};o=of.get(key,{}) if isinstance(of.get(key,{}),dict) else {}
        chosen=n if _event_time(n)>=_event_time(o) else o
        out['files'][key]={**o,**n,**chosen,'runs':max_count(n,o,'runs'),'successful_repairs':max_count(n,o,'successful_repairs')}
        out['files'][key]['recent_failures']=safe_int(chosen.get('recent_failures'),0,0,4)
        out['files'][key]['clean_success_streak']=safe_int(chosen.get('clean_success_streak'),0)
    nk=new.get('monitor_known_errors') if isinstance(new.get('monitor_known_errors'),dict) else {};ok=old.get('monitor_known_errors') if isinstance(old.get('monitor_known_errors'),dict) else {}
    for key in set(nk)|set(ok):
        n=nk.get(key,{}) if isinstance(nk.get(key,{}),dict) else {};o=ok.get(key,{}) if isinstance(ok.get(key,{}),dict) else {}
        chosen=n if _event_time(n)>=_event_time(o) else o
        out['monitor_known_errors'][key]={**o,**n,**chosen,'occurrences':max_count(n,o,'occurrences'),'resolved_count':max_count(n,o,'resolved_count')}
    ng=new.get('error_groups') if isinstance(new.get('error_groups'),dict) else {};og=old.get('error_groups') if isinstance(old.get('error_groups'),dict) else {}
    for key in set(ng)|set(og):
        n=ng.get(key,{}) if isinstance(ng.get(key,{}),dict) else {};o=og.get(key,{}) if isinstance(og.get(key,{}),dict) else {}
        chosen=n if _event_time(n)>=_event_time(o) else o
        files=[]
        for value in [*(o.get('affected_files') if isinstance(o.get('affected_files'),list) else []),*(n.get('affected_files') if isinstance(n.get('affected_files'),list) else [])]:
            value=str(value)[:160]
            if value and value not in files:files.append(value)
        old_counts=o.get('file_counts') if isinstance(o.get('file_counts'),dict) else {};new_counts=n.get('file_counts') if isinstance(n.get('file_counts'),dict) else {}
        file_counts={}
        for name in set(old_counts)|set(new_counts):
            file_counts[str(name)[:160]]=max(safe_int(old_counts.get(name)),safe_int(new_counts.get(name)))
        old_states=o.get('file_states') if isinstance(o.get('file_states'),dict) else {};new_states=n.get('file_states') if isinstance(n.get('file_states'),dict) else {}
        file_states={}
        for name in set(old_states)|set(new_states):
            old_state=old_states.get(name,{}) if isinstance(old_states.get(name,{}),dict) else {}
            new_state=new_states.get(name,{}) if isinstance(new_states.get(name,{}),dict) else {}
            old_time=max(str(old_state.get('last_seen') or ''),str(old_state.get('last_clean_seen') or ''))
            new_time=max(str(new_state.get('last_seen') or ''),str(new_state.get('last_clean_seen') or ''))
            state_chosen=new_state if new_time>=old_time else old_state
            occurrences=max(safe_int(old_state.get('occurrences')),safe_int(new_state.get('occurrences')))
            resolved_count=min(occurrences,max(safe_int(old_state.get('resolved_count')),safe_int(new_state.get('resolved_count'))))
            label=str(name)[:160]
            file_states[label]={**old_state,**new_state,**state_chosen,
                'occurrences':occurrences,'resolved_count':resolved_count,
                'last_outcome':'resolved' if state_chosen.get('last_outcome')=='resolved' and resolved_count>=occurrences else 'unresolved',
                'clean_observations_after_error':safe_int(state_chosen.get('clean_observations_after_error')),
                'resolution_confirmed':state_chosen.get('resolution_confirmed') is True}
            if label and label not in files:files.append(label)
        old_actions=o.get('successful_actions') if isinstance(o.get('successful_actions'),dict) else {};new_actions=n.get('successful_actions') if isinstance(n.get('successful_actions'),dict) else {}
        actions={}
        for action in set(old_actions)|set(new_actions):
            actions[str(action)[:400]]=max(safe_int(old_actions.get(action)),safe_int(new_actions.get(action)))
        history=[];seen=set()
        for event in [*(o.get('resolution_history') if isinstance(o.get('resolution_history'),list) else []),*(n.get('resolution_history') if isinstance(n.get('resolution_history'),list) else [])]:
            if not isinstance(event,dict):continue
            # Distinct evidence may share second/file/action/outcome yet have
            # different receipts or reviewer IDs. Only exact event equality
            # is safe to coalesce during legacy repair-history migration.
            event_key=json.dumps(event,ensure_ascii=False,sort_keys=True)
            if event_key in seen:continue
            seen.add(event_key);history.append(event)
        history.sort(key=lambda row:str(row.get('timestamp','')))
        unresolved_files=[name for name,state in file_states.items() if state.get('last_outcome')!='resolved']
        merged_resolved=max(max_count(n,o,'resolved_count'),sum(safe_int(state.get('resolved_count')) for state in file_states.values()))
        out['error_groups'][key]={**o,**n,**chosen,
            'occurrences':max_count(n,o,'occurrences'),'resolved_count':max_count(n,o,'resolved_count'),
            'affected_files':files[-100:],'file_counts':file_counts,'file_states':file_states,
            'unresolved_files':unresolved_files[-100:],
            'last_outcome':'resolved' if file_states and not unresolved_files else 'unresolved',
            'successful_actions':actions,'resolution_history':history[-30:]}
        out['error_groups'][key]['resolved_count']=min(out['error_groups'][key]['occurrences'],merged_resolved)
    log=[];seen_log=set()
    for row in [*(old.get('new_error_log') if isinstance(old.get('new_error_log'),list) else []),*(new.get('new_error_log') if isinstance(new.get('new_error_log'),list) else [])]:
        if not isinstance(row,dict):continue
        # Two errors from the same group and second can still refer to
        # different files, actions or provenance. Preserve both unless the
        # complete JSON record is identical.
        key=json.dumps(row,ensure_ascii=False,sort_keys=True)
        if key in seen_log:continue
        seen_log.add(key);log.append(row)
    log.sort(key=lambda row:str(row.get('first_seen','')))
    out['new_error_log']=log[-200:]
    out['monitor_history']=_merge_monitor_history(new.get('monitor_history'),old.get('monitor_history'))
    return out

def timestamp(data):
    values=[data.get('updated_at')]
    if isinstance(data.get('auto_update'),dict):values.append(data['auto_update'].get('last_run'))
    best=dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    for raw in values:
        if not raw:continue
        try:
            parsed=dt.datetime.fromisoformat(str(raw).replace('Z','+00:00'))
            if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=dt.timezone.utc)
            best=max(best,parsed.astimezone(dt.timezone.utc))
        except ValueError:pass
    return best

def migrate(old_dir,new_dir):
    old,new=Path(old_dir).resolve(),Path(new_dir).resolve()
    if old==new:raise ValueError('old and new folders are identical')
    if not (old/'tcg_updater.py').is_file() or not (new/'tcg_updater.py').is_file():raise ValueError('invalid TCG_GRADER folder')
    # Serialize the complete read/backup/write/rollback cycle. Atomic writes
    # alone cannot prevent two migration processes from interleaving evidence.
    with exclusive_file_lock(new/'.tcg_migration',timeout_seconds=10):
        return _migrate_locked(old,new)

def _migrate_locked(old,new):
    if not (old/'tcg_updater.py').is_file() or not (new/'tcg_updater.py').is_file():
        raise ValueError('invalid TCG_GRADER folder')
    # Preflight both last-good trees BEFORE altering any learning/recovery files.
    # Otherwise a symlink encountered after four writes aborts migration only
    # after the new folder has already been partially changed.
    for snapshots in (old/'.tcg_last_good', new/'.tcg_last_good'):
        if snapshots.is_symlink() or (snapshots.is_dir() and any(
                item.is_symlink() for item in snapshots.rglob('*'))):
            raise ValueError('심볼릭 링크 복구자료는 허용되지 않습니다.')
    # Validate and merge ALL old/new records before the first destination write.
    # Previously a malformed later JSON document could be treated as empty and
    # overwrite user evidence after learning_store.json had already changed.
    source={name:(read_migration_source(old/name),
                  read_migration_source(new/name)) for name in FILES}
    old_learning,new_learning=source['learning_store.json']
    old_memory,new_memory=source['auto_repair_memory.json']
    old_history,new_history=source['verification_history.json']
    old_live,new_live=source['tcg_live_data.json']
    prepared={
        'learning_store.json':merge_learning(new_learning,old_learning),
        'auto_repair_memory.json':merge_memory(new_memory,old_memory),
        'verification_history.json':merge_history(new_history,old_history),
        'tcg_live_data.json':old_live if timestamp(old_live)>timestamp(new_live) else new_live,
    }
    # An attacker-controlled or accidentally linked backup root must not
    # redirect preservation files outside the selected destination folder.
    backup_root=new/'MIGRATION_BACKUP'
    if backup_root.is_symlink() or (backup_root.exists() and not backup_root.is_dir()):
        raise ValueError('migration_backup_directory_unsafe')
    original_bytes={name:(safe_read_bytes(new/name) if (new/name).exists() else None)
                    for name in FILES}
    stamp=dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+secrets.token_hex(4)
    backup=backup_root/stamp
    backup.mkdir(parents=True,exist_ok=False)
    for name in FILES:
        if original_bytes[name] is not None:
            copy_safe_file(new/name,backup/name)
    if (new/'.tcg_last_good').is_dir():
        copy_safe_tree(new/'.tcg_last_good',backup/'.tcg_last_good')

    # A failure after the first replacement used to leave a partially migrated
    # learning directory. Roll back caught I/O errors from the exact pre-write
    # bytes; preserve the backup for manual recovery if rollback itself fails.
    # A sudden process kill/power loss is NOT a multi-file atomic transaction.
    changed=[]
    added_good=[]
    good_dir=new/'.tcg_last_good'
    created_good_dir=False
    try:
        for name in FILES:
            changed.append(name)  # Include even a writer that raises after replace.
            write_json(new/name,prepared[name])
        if (old/'.tcg_last_good').is_dir():
            # Never overwrite the destination's existing verified snapshots.
            created_good_dir=not good_dir.exists()
            good_dir.mkdir(parents=True,exist_ok=True)
            for src in (old/'.tcg_last_good').iterdir():
                dst=good_dir/src.name
                if src.is_symlink():
                    raise ValueError('심볼릭 링크 이전 복구자료는 허용되지 않습니다.')
                if src.is_file() and not dst.exists():
                    added_good.append(dst)
                    copy_safe_file(src,dst)
    except Exception as original_error:
        rollback_errors=[]
        for path in reversed(added_good):
            try:
                if path.is_symlink():
                    raise ValueError('migration_rollback_symlink_blocked')
                path.unlink(missing_ok=True)
            except Exception as exc:
                rollback_errors.append('last_good:'+type(exc).__name__)
        if created_good_dir:
            try:
                good_dir.rmdir()
            except Exception as exc:
                rollback_errors.append('last_good_dir:'+type(exc).__name__)
        for name in reversed(changed):
            target=new/name
            try:
                previous=original_bytes[name]
                if previous is None:
                    if target.is_symlink():
                        raise ValueError('migration_rollback_symlink_blocked')
                    target.unlink(missing_ok=True)
                else:
                    atomic_write_bytes(target,previous,suffix='.migration-rollback.tmp')
            except Exception as exc:
                rollback_errors.append(name+':'+type(exc).__name__)
        if rollback_errors:
            raise RuntimeError('migration_rollback_failed: '+','.join(rollback_errors)) from original_error
        raise
    return backup

if __name__=='__main__':
    try:
        if len(sys.argv)!=3:raise ValueError('usage: migrate_old_data.py OLD NEW')
        backup=migrate(sys.argv[1].strip('" '),sys.argv[2].strip('" '))
        print('[OK] Learning and recovery data safely merged.');print('New-folder backup:',backup)
    except Exception as exc:
        print('[ERROR]',type(exc).__name__,str(exc));raise SystemExit(1)
