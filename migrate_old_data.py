#!/usr/bin/env python3
"""Safely merge user learning/recovery records from an older TCG_GRADER folder."""
from __future__ import annotations
import datetime as dt, json, os, shutil, sys
from pathlib import Path
from grading_self_learning import rebuild_store

FILES=('learning_store.json','auto_repair_memory.json','verification_history.json','tcg_live_data.json')

def read_json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError,TypeError):return default

def write_json(path,data):
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(temp,path)

def rows_merged(new_rows,old_rows,limit=500):
    unique={}
    for row in [*old_rows,*new_rows]:
        if not isinstance(row,dict):continue
        key=(str(row.get('time','')),str(row.get('company') or row.get('grader') or ''),str(row.get('actual','')),str(row.get('pred','')))
        unique[key]=row
    return list(unique.values())[-limit:]

def merge_learning(new,old):
    base={
        'version':2,
        'updated_at':max(str(new.get('updated_at') or ''),str(old.get('updated_at') or '')) or None,
        'v30_validation':rows_merged(new.get('v30_validation',[]),old.get('v30_validation',[])),
        'v11_validation':rows_merged(new.get('v11_validation',[]),old.get('v11_validation',[])),
        'confirmed_samples':rows_merged(new.get('confirmed_samples',[]),old.get('confirmed_samples',[]),limit=2000),
    }
    return rebuild_store(base)

def merge_history(new,old):
    unique={}
    for run in [*old.get('runs',[]),*new.get('runs',[])]:
        if not isinstance(run,dict):continue
        key=(str(run.get('checked_at','')),json.dumps(run.get('checks',[]),ensure_ascii=False,sort_keys=True));unique[key]=run
    runs=sorted(unique.values(),key=lambda x:str(x.get('checked_at','')))[-100:]
    updated=max([str(new.get('updated_at') or ''),str(old.get('updated_at') or ''),*[str(x.get('checked_at') or '') for x in runs]]) or None
    return {'version':max(int(new.get('version',1)),int(old.get('version',1))),'runs':runs,'updated_at':updated}

def max_count(a,b,key):
    try:return max(int(a.get(key,0)),int(b.get(key,0)))
    except (AttributeError,TypeError,ValueError):return 0

def merge_memory(new,old):
    out={'version':max(int(new.get('version',1)),int(old.get('version',1))),'updated_at':max(str(new.get('updated_at') or ''),str(old.get('updated_at') or '')) or None,
         'total_runs':max(int(new.get('total_runs',0)),int(old.get('total_runs',0))),'patterns':{},'files':{}}
    for key in set(new.get('patterns',{}))|set(old.get('patterns',{})):
        n=new.get('patterns',{}).get(key,{});o=old.get('patterns',{}).get(key,{})
        chosen=n if str(n.get('last_seen',''))>=str(o.get('last_seen','')) else o
        out['patterns'][key]={**o,**n,**chosen,'occurrences':max_count(n,o,'occurrences'),'successful_repairs':max_count(n,o,'successful_repairs')}
    for key in set(new.get('files',{}))|set(old.get('files',{})):
        n=new.get('files',{}).get(key,{});o=old.get('files',{}).get(key,{})
        out['files'][key]={**o,**n,'runs':max_count(n,o,'runs'),'recent_failures':max_count(n,o,'recent_failures'),'successful_repairs':max_count(n,o,'successful_repairs')}
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
        if (new/name).exists():shutil.copy2(new/name,backup/name)
    if (new/'.tcg_last_good').is_dir():shutil.copytree(new/'.tcg_last_good',backup/'.tcg_last_good')
    write_json(new/'learning_store.json',merge_learning(read_json(new/'learning_store.json',{}),read_json(old/'learning_store.json',{})))
    write_json(new/'auto_repair_memory.json',merge_memory(read_json(new/'auto_repair_memory.json',{}),read_json(old/'auto_repair_memory.json',{})))
    write_json(new/'verification_history.json',merge_history(read_json(new/'verification_history.json',{}),read_json(old/'verification_history.json',{})))
    new_live=read_json(new/'tcg_live_data.json',{});old_live=read_json(old/'tcg_live_data.json',{})
    write_json(new/'tcg_live_data.json',old_live if timestamp(old_live)>timestamp(new_live) else new_live)
    if (old/'.tcg_last_good').is_dir():shutil.copytree(old/'.tcg_last_good',new/'.tcg_last_good',dirs_exist_ok=True)
    return backup

if __name__=='__main__':
    try:
        if len(sys.argv)!=3:raise ValueError('usage: migrate_old_data.py OLD NEW')
        backup=migrate(sys.argv[1].strip('" '),sys.argv[2].strip('" '))
        print('[OK] Learning and recovery data safely merged.');print('New-folder backup:',backup)
    except Exception as exc:
        print('[ERROR]',type(exc).__name__,str(exc));raise SystemExit(1)
