"""Bounded local image neural challenger training; never enables live grading.

Input is a local, reviewed photo manifest, not collected listing/OCR guesses.
Identity and grade models are separated by game/language/grader. Existing live
calibration and weights are never overwritten. No synthetic production rows.
"""
from __future__ import annotations
import hashlib
import io
import json
import math
from pathlib import Path
import random
import time
from collections import Counter
from safe_runtime import safe_read_text, atomic_write_json, exclusive_file_lock

MIN_ROWS=1000
MAX_ROWS=4000
MAX_BYTES=8_000_000
MAX_SECONDS=30


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def checked_path(root, relative):
    path=Path(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('INVALID_LOCAL_PHOTO_PATH')
    target=root/path
    if any(p.is_symlink() for p in (target,*target.parents)):
        raise ValueError('SYMLINK_PHOTO_PATH')
    target.resolve().relative_to(root.resolve())
    return target


def pixels(data):
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(data)) as image:
        if image.width*image.height>20_000_000 or min(image.size)<64:
            raise ValueError('IMAGE_DIMENSIONS')
        image=ImageOps.exif_transpose(image).convert('RGB').resize((8,8))
        return [component/255 for rgb in image.get_flattened_data() for component in rgb]


def load_rows(root, manifest, registry, cache=None):
    payload=json.loads(safe_read_text(manifest,max_bytes=2_000_000))
    if not isinstance(payload,dict) or payload.get('schema')!=1 or not isinstance(payload.get('rows'),list):
        raise ValueError('INVALID_PHOTO_MANIFEST')
    if len(payload['rows'])>MAX_ROWS:raise ValueError('PHOTO_MANIFEST_ROW_LIMIT')
    rows=[];seen=set();rejected=Counter();new_images=0;new_bytes=0
    cache=cache or {}
    for row in payload['rows']:
        try:
            if not isinstance(row,dict):raise ValueError('INVALID_ROW')
            # Local human-review receipts are required in addition to the official
            # registry match. A public collector cannot write these receipts.
            if row.get('review_method')!='local_human_raw_photo_pair' or row.get('mode')!='raw':
                raise ValueError('RAW_PHOTO_PAIR_REVIEW_REQUIRED')
            scope=tuple(row.get(k) for k in ('game','language','company'))
            if scope[0] not in ('pokemon','onepiece','naruto') or scope[1] not in ('KR','JP','US','CN-S','CN-T'):
                raise ValueError('UNSUPPORTED_SCOPE')
            company,cert=scope[2],str(row.get('certification_id',''))
            official=registry.get(company+'|'+cert)
            if not official or official.get('verified') is not True:raise ValueError('CERT_NOT_VERIFIED')
            grade=official['grade']
            if type(grade) not in (int,float) or not math.isfinite(grade) or not 1<=grade<=10:
                raise ValueError('INVALID_OFFICIAL_GRADE')
            identity=row.get('card_identity')
            if not isinstance(identity,str) or not identity.strip() or len(identity)>180:
                raise ValueError('CARD_IDENTITY_REQUIRED')
            receipt_key=digest((scope,cert,identity,row.get('image_sha256')))
            stored=cache.get(receipt_key)
            if stored is not None:
                if stored.get('grade')!=grade or len(stored.get('x',[]))!=192 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in stored['x']):
                    raise ValueError('INVALID_FEATURE_RECEIPT')
                if stored.get('feature_digest')!=digest(stored['x']):raise ValueError('FEATURE_RECEIPT_HASH_MISMATCH')
                stored=dict(stored);stored['scope']=tuple(stored['scope'])
                if stored['scope']!=scope or stored.get('identity')!=identity or stored.get('receipt_key')!=receipt_key:
                    raise ValueError('FEATURE_RECEIPT_IDENTITY_MISMATCH')
                key=(company,cert)
                if key in seen or stored['image_hash'] in seen:raise ValueError('DUPLICATE_PHOTO_OR_CERT')
                seen.update((key,stored['image_hash']));rows.append(stored);continue
            if new_images>=16 or new_bytes>=128_000_000:
                raise ValueError('DEFERRED_IMAGE_ADMISSION_BUDGET')
            target=checked_path(root,row['image'])
            if target.stat().st_size>MAX_BYTES:raise ValueError('PHOTO_BYTES_LIMIT')
            data=target.read_bytes();new_images+=1;new_bytes+=len(data);sha=hashlib.sha256(data).hexdigest()
            if row.get('image_sha256')!=sha:raise ValueError('PHOTO_HASH_MISMATCH')
            # Decode and hash canonical pixels as well as bytes to deduplicate
            # identical photos in different containers before partitioning.
            features=pixels(data);ph=digest(features)
            key=(company,cert)
            if key in seen or ph in seen:raise ValueError('DUPLICATE_PHOTO_OR_CERT')
            seen.update((key,ph))
            group=digest((scope,identity))
            fold=int(group[:8],16)%10
            rows.append({'scope':scope,'identity':identity,'grade':float(grade),'x':features,
                         'receipt_key':receipt_key,'feature_digest':digest(features),'image_hash':ph,'group':group,'cert_group':digest((scope,cert)),'split':'holdout' if fold==0 else 'validation' if fold==1 else 'train'})
        except (ValueError,KeyError,OSError,TypeError) as exc:
            rejected[str(exc) if isinstance(exc,ValueError) else type(exc).__name__]+=1
    return rows,dict(rejected)


def predict(model,x):
    hidden=[math.tanh(sum(a*b for a,b in zip(w,x))+bias) for w,bias in zip(model['w'],model['b'])]
    logits=[sum(a*b for a,b in zip(w,hidden))+bias for w,bias in zip(model['v'],model['c'])]
    if model['task']=='grade':return [1/(1+math.exp(-max(-30,min(30,logits[0]))))]
    top=max(logits);values=[math.exp(v-top) for v in logits];total=sum(values)
    return [v/total for v in values]


def fit(rows,task,classes,deadline):
    rng=random.Random(660);width=len(rows[0]['x']);hidden=8;outputs=1 if task=='grade' else len(classes)
    m={'task':task,'classes':classes,'w':[[rng.uniform(-.05,.05) for _ in range(width)] for _ in range(hidden)],
       'b':[0.]*hidden,'v':[[rng.uniform(-.05,.05) for _ in range(hidden)] for _ in range(outputs)],'c':[0.]*outputs}
    for epoch in range(12):
        ordered=list(rows);rng.shuffle(ordered)
        for row in ordered:
            if time.monotonic()>deadline:raise TimeoutError('IMAGE_TRAINING_BUDGET')
            x=row['x'];h=[math.tanh(sum(a*b for a,b in zip(w,x))+b) for w,b in zip(m['w'],m['b'])]
            out=predict(m,x)
            if task=='grade':
                error=[(out[0]-(row['grade']-1)/9)*out[0]*(1-out[0])]
            else:error=[p-(i==classes.index(row['identity'])) for i,p in enumerate(out)]
            back=[sum(error[k]*m['v'][k][j] for k in range(outputs))*(1-h[j]*h[j]) for j in range(hidden)]
            for k in range(outputs):
                for j in range(hidden):m['v'][k][j]-=.03*error[k]*h[j]
                m['c'][k]-=.03*error[k]
            for j in range(hidden):
                for i in range(width):m['w'][j][i]-=.03*back[j]*x[i]
                m['b'][j]-=.03*back[j]
    return m


def metrics(model,rows):
    if model['task']=='grade':
        errors=[1+9*predict(model,r['x'])[0]-r['grade'] for r in rows]
        return {'mae':sum(abs(e) for e in errors)/len(errors),'overgrade_rate':sum(e>.5 for e in errors)/len(errors)}
    correct=0
    for row in rows:
        probabilities=predict(model,row['x'])
        correct+=model['classes'][max(range(len(probabilities)),key=probabilities.__getitem__)]==row['identity']
    return {'accuracy':correct/len(rows)}


def run(root,manifest,output,*,train=False,registry=None):
    root=Path(root).resolve();output=Path(output)
    if registry is None:
        from verified_grade_learning_v135 import registry_index
        registry=registry_index()
    with exclusive_file_lock(output/'cycle',timeout_seconds=.1,stale_seconds=600):
        cache_path=output/'admitted_features.json'
        cached=json.loads(safe_read_text(cache_path,max_bytes=25_000_000)) if cache_path.exists() else {}
        if not isinstance(cached,dict) or len(cached)>MAX_ROWS:raise ValueError('INVALID_FEATURE_CACHE')
        rows,rejected=load_rows(root,Path(manifest),registry,cached)
        atomic_write_json(cache_path,{r['receipt_key']:r for r in rows})
        scopes=sorted(set(r['scope'] for r in rows));reports=[];deadline=time.monotonic()+MAX_SECONDS
        if len(scopes)>8:raise ValueError('SCOPE_LIMIT')
        for scope in scopes:
            group=[r for r in rows if r['scope']==scope]
            for task in ('identity','grade'):
                def partition(row):
                    if task=='grade':return row['split']
                    fold=int(row['cert_group'][:8],16)%10
                    return 'holdout' if fold==0 else 'validation' if fold==1 else 'train'
                parts={s:[r for r in group if partition(r)==s] for s in ('train','validation','holdout')}
                classes=sorted(set(r['identity'] for r in group));counts=Counter(r['identity'] if task=='identity' else int(r['grade']) for r in group)
                gaps=[]
                if len(group)<MIN_ROWS:gaps.append('minimum_1000_independent_photos')
                if any(len(p)<100 for p in parts.values()):gaps.append('minimum_100_each_split')
                if len(counts)<2 or min(counts.values())<100:gaps.append('minimum_100_each_class')
                if task=='identity' and (len(classes)>32 or any(set(r['identity'] for r in p)!=set(classes) for p in parts.values())):gaps.append('identity_classes_not_covered_in_every_split')
                report={'scope':scope,'task':task,'rows':len(group),'rows_remaining':max(0,MIN_ROWS-len(group)),
                        'splits':{k:len(v) for k,v in parts.items()},'class_counts':dict(counts),'gaps':gaps,'training_attempted':False}
                fingerprint=digest([(r['group'],r['image_hash'],r['grade']) for r in group])
                path=output/(digest((scope,task))[:20]+'.challenger.json')
                previous=json.loads(safe_read_text(path,max_bytes=250_000)) if path.exists() else {}
                unchanged=previous.get('dataset_digest')==fingerprint
                report['training_skipped_unchanged_dataset']=unchanged
                if train and not gaps and not unchanged:
                    try:
                        model=fit(parts['train'], 'grade' if task=='grade' else 'identity',classes,deadline)
                        report.update(training_attempted=True,validation=metrics(model,parts['validation']),holdout=metrics(model,parts['holdout']))
                        # Challenger artifacts are auditable but never substituted
                        # for established live OCR/grading without deployment gates.
                        atomic_write_json(path,{'schema':1,'model':model,'report':report,'dataset_digest':fingerprint,'production_enabled':False})
                    except TimeoutError:report['gaps'].append('training_budget_exhausted')
                reports.append(report)
        result={'models':reports,'accepted_photos':len(rows),'rejected':rejected,'production_model_changed':False,'physical_tablet_verified':False,
                'missing_dataset':not rows,'next_action':'continue_verified_raw_photo_intake'}
        atomic_write_json(output/'status.json',result)
        return result


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--train',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.root,args.manifest,args.output,train=args.train),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
