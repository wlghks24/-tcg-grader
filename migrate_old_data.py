#!/usr/bin/env python3
"""Safely merge user learning/recovery records from an older TCG_GRADER folder."""
from __future__ import annotations
import datetime as dt, json, sys
from pathlib import Path
from safe_runtime import atomic_write_bytes, atomic_write_json, bounded_int as safe_int, safe_read_bytes, safe_read_text

FILES=('learning_store.json','auto_repair_memory.json','verification_history.json','tcg_live_data.json')
VERIFICATION_HISTORY_LIMIT=24
VERIFICATION_FULL_DETAIL_LIMIT=8

def _event_time(row):
    if not isinstance(row,dict):return ''
    return str(row.get('last_seen') or row.get('last_run') or row.get('timestamp') or '')

def read_json(path,default):
    try:return json.loads(safe_read_text(path))
    except (OSError,ValueError,TypeError):return default

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
    unique={}
    for row in [*old_rows,*new_rows]:
        if not isinstance(row,dict):continue
        key=(str(row.get('time','')),str(row.get('company') or row.get('grader') or ''),str(row.get('actual','')),str(row.get('pred','')))
        unique[key]=row
    return list(unique.values())[-limit:]

def merge_learning(new,old):
    return {'version':1,'updated_at':max(str(new.get('updated_at') or ''),str(old.get('updated_at') or '')) or None,
            'v30_validation':rows_merged(new.get('v30_validation',[]),old.get('v30_validation',[])),
            'v11_validation':rows_merged(new.get('v11_validation',[]),old.get('v11_validation',[]))}

def merge_history(new,old):
    new=new if isinstance(new,dict) else {};old=old if isinstance(old,dict) else {}
    unique={}
    for run in [*(old.get('runs') if isinstance(old.get('runs'),list) else []),*(new.get('runs') if isinstance(new.get('runs'),list) else [])]:
        if not isinstance(run,dict):continue
        key=(str(run.get('checked_at','')),json.dumps(run.get('checks',[]),ensure_ascii=False,sort_keys=True));unique[key]=run
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
                'resolution_confirmed':bool(state_chosen.get('resolution_confirmed'))}
            if label and label not in files:files.append(label)
        old_actions=o.get('successful_actions') if isinstance(o.get('successful_actions'),dict) else {};new_actions=n.get('successful_actions') if isinstance(n.get('successful_actions'),dict) else {}
        actions={}
        for action in set(old_actions)|set(new_actions):
            actions[str(action)[:400]]=max(safe_int(old_actions.get(action)),safe_int(new_actions.get(action)))
        history=[];seen=set()
        for event in [*(o.get('resolution_history') if isinstance(o.get('resolution_history'),list) else []),*(n.get('resolution_history') if isinstance(n.get('resolution_history'),list) else [])]:
            if not isinstance(event,dict):continue
            event_key=(str(event.get('timestamp','')),str(event.get('file','')),str(event.get('action','')),bool(event.get('resolved')))
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
        key=(str(row.get('group_id','')),str(row.get('first_seen','')))
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
    stamp=dt.datetime.now().strftime('%Y%m%d_%H%M%S');backup=new/'MIGRATION_BACKUP'/stamp;backup.mkdir(parents=True,exist_ok=False)
    for name in FILES:
        if (new/name).exists():copy_safe_file(new/name,backup/name)
    if (new/'.tcg_last_good').is_dir():copy_safe_tree(new/'.tcg_last_good',backup/'.tcg_last_good')
    write_json(new/'learning_store.json',merge_learning(read_json(new/'learning_store.json',{}),read_json(old/'learning_store.json',{})))
    write_json(new/'auto_repair_memory.json',merge_memory(read_json(new/'auto_repair_memory.json',{}),read_json(old/'auto_repair_memory.json',{})))
    write_json(new/'verification_history.json',merge_history(read_json(new/'verification_history.json',{}),read_json(old/'verification_history.json',{})))
    new_live=read_json(new/'tcg_live_data.json',{});old_live=read_json(old/'tcg_live_data.json',{})
    write_json(new/'tcg_live_data.json',old_live if timestamp(old_live)>timestamp(new_live) else new_live)
    if (old/'.tcg_last_good').is_dir():
        # v74: never overwrite the new version's verified last-good snapshots with older ones.
        # Only fill files that are genuinely missing in the new folder.
        dst_good=new/'.tcg_last_good';dst_good.mkdir(parents=True,exist_ok=True)
        for src in (old/'.tcg_last_good').iterdir():
            dst=dst_good/src.name
            if src.is_symlink():raise ValueError('심볼릭 링크 이전 복구자료는 허용되지 않습니다.')
            if src.is_file() and not dst.exists():copy_safe_file(src,dst)
    return backup

if __name__=='__main__':
    try:
        if len(sys.argv)!=3:raise ValueError('usage: migrate_old_data.py OLD NEW')
        backup=migrate(sys.argv[1].strip('" '),sys.argv[2].strip('" '))
        print('[OK] Learning and recovery data safely merged.');print('New-folder backup:',backup)
    except Exception as exc:
        print('[ERROR]',type(exc).__name__,str(exc));raise SystemExit(1)
