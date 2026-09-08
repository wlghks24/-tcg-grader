"""Paired evaluation and automatic selection among host-approved AI profiles.

Existing AI calls stay in the host. No weights training or fabricated evaluation.
"""
import asyncio
import hashlib
import json
import math
import sqlite3
from pathlib import Path


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def metric_valid(metric):
    return (isinstance(metric,dict) and type(metric.get('hard_gate')) is bool
        and type(metric.get('score')) in (float,int) and math.isfinite(metric['score']) and 0<=metric['score']<=1
        and type(metric.get('latency_ms')) in (float,int) and math.isfinite(metric['latency_ms']) and metric['latency_ms']>0
        and isinstance(metric.get('evidence'),str) and bool(metric['evidence']))


class ProfileLearner:
    def __init__(self, root, *, project, feature, revision, profiles, baseline):
        if not all(isinstance(x,str) and x for x in (project,feature,revision)):
            raise ValueError('project, feature and evaluator revision required')
        if not isinstance(profiles,dict) or baseline not in profiles or not all(isinstance(p,str) and p for p in profiles):
            raise ValueError('approved profiles and baseline required')
        self.profiles=json.loads(json.dumps(profiles))
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'profiles.sqlite'
        self.scope=fingerprint([project,feature,revision])
        self.registry=fingerprint(profiles)
        self.baseline=baseline
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS active (scope TEXT PRIMARY KEY, registry TEXT, profile TEXT, generation INTEGER)')
            db.execute('CREATE TABLE IF NOT EXISTS evaluations (scope TEXT, trial TEXT, report TEXT, PRIMARY KEY(scope,trial))')
            db.execute('INSERT OR IGNORE INTO active VALUES (?,?,?,0)',(self.scope,self.registry,baseline))
            if db.execute('SELECT registry FROM active WHERE scope=?',(self.scope,)).fetchone()[0]!=self.registry:
                raise ValueError('PROFILE_REGISTRY_CHANGED_USE_NEW_REVISION')

    def current(self):
        with sqlite3.connect(self.path) as db:
            profile,generation=db.execute('SELECT profile,generation FROM active WHERE scope=?',(self.scope,)).fetchone()
        return profile,generation

    def selected(self):
        profile,_=self.current()
        return profile,json.loads(json.dumps(self.profiles[profile]))

    async def improve(self, *, trial, candidate, cases, evaluate, budget=120, min_gain=.02):
        if not isinstance(trial,str) or not trial or candidate not in self.profiles:
            raise ValueError('explicit trial and approved candidate required')
        if not math.isfinite(budget) or budget<=0 or not .02<=min_gain<=1:
            raise ValueError('invalid limits')
        if not isinstance(cases,list) or not 6<=len(cases)<=100:
            raise ValueError('6..100 labeled cases required')
        ids=set();inputs=set();counts={'regression':0,'holdout':0}
        for case in cases:
            if not isinstance(case,dict) or case.get('split') not in counts or not isinstance(case.get('id'),str) or not case['id'] or 'input' not in case:
                raise ValueError('invalid case')
            input_hash=fingerprint(case['input'])
            if case['id'] in ids or input_hash in inputs:
                raise ValueError('DUPLICATE_OR_LEAKED_CASE')
            ids.add(case['id']);inputs.add(input_hash);counts[case['split']]+=1
        if min(counts.values())<3:
            raise ValueError('at least 3 regression and 3 independent holdout cases required')
        with sqlite3.connect(self.path) as db:
            previous=db.execute('SELECT report FROM evaluations WHERE scope=? AND trial=?',(self.scope,trial)).fetchone()
        if previous:
            return {'status':'TRIAL_ALREADY_RECORDED','report':json.loads(previous[0])}
        champion,generation=self.current()
        if candidate==champion:
            return {'status':'ALREADY_SELECTED'}
        async def compare():
            rows=[]
            for case in cases:
                metrics=[]
                for profile in (champion,candidate):
                    # Fresh copies prevent evaluator/proposer mutation of registry/cases.
                    value=await evaluate(profile,json.loads(json.dumps(self.profiles[profile])),json.loads(json.dumps(case)))
                    if not metric_valid(value):
                        raise ValueError('INVALID_EVALUATION_EVIDENCE')
                    metrics.append(value)
                rows.append({'case_id':case['id'],'input_hash':fingerprint(case['input']),
                             'split':case['split'],'baseline':metrics[0],'candidate':metrics[1]})
            return rows
        try:
            rows=await asyncio.wait_for(compare(),budget)
        except asyncio.TimeoutError:
            return {'status':'EVALUATION_TIMEOUT','selected':champion}
        # Every case must retain quality, pass a hard gate, and stay within
        # 10% latency overhead. Improvement must hold separately in each split.
        no_regression=all(r['candidate']['hard_gate'] is True and r['candidate']['score']>=r['baseline']['score'] and r['candidate']['latency_ms']<=r['baseline']['latency_ms']*1.1 for r in rows)
        gains={split:sum(r['candidate']['score']-r['baseline']['score'] for r in rows if r['split']==split)/counts[split] for split in counts}
        eligible=no_regression and all(g>=min_gain for g in gains.values())
        report={'status':'PROMOTED' if eligible else 'REJECTED','baseline':champion,'candidate':candidate,
                'gains':gains,'rows':rows,'evaluator_revision_scope':self.scope,'registry':self.registry,
                'production_quality':'NOT_YET_OBSERVED'}
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            latest=db.execute('SELECT profile,generation FROM active WHERE scope=?',(self.scope,)).fetchone()
            if latest!=(champion,generation):
                return {'status':'CHAMPION_CHANGED_REEVALUATE'}
            if db.execute('SELECT 1 FROM evaluations WHERE scope=? AND trial=?',(self.scope,trial)).fetchone():
                return {'status':'TRIAL_ALREADY_RECORDED'}
            if eligible:
                db.execute('UPDATE active SET profile=?,generation=generation+1 WHERE scope=?',(candidate,self.scope))
            db.execute('INSERT INTO evaluations VALUES (?,?,?)',(self.scope,trial,json.dumps(report)))
        return report

    def rollback(self, *, expected_profile, target_profile, evidence):
        if target_profile not in self.profiles or not isinstance(evidence,str) or not evidence:
            raise ValueError('approved rollback profile and evidence required')
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            profile,generation=db.execute('SELECT profile,generation FROM active WHERE scope=?',(self.scope,)).fetchone()
            if profile!=expected_profile:
                return {'status':'CHAMPION_CHANGED'}
            db.execute('UPDATE active SET profile=?,generation=generation+1 WHERE scope=?',(target_profile,self.scope))
            report={'status':'ROLLED_BACK','from':profile,'to':target_profile,'evidence':evidence}
            db.execute('INSERT INTO evaluations VALUES (?,?,?)',(self.scope,f'rollback:{generation}',json.dumps(report)))
        return report

    async def call(self, invoke, verify, *, request):
        """Use selected existing AI; revert profile for future calls if output fails.
        Does not retry this request, avoiding duplicated billable/side-effect calls.
        Host must bound invoke/verify and supply independent real verification.
        """
        profile,config=self.selected()
        output=await invoke(profile,config,request)
        try:
            valid=await verify(output)
        except asyncio.CancelledError:
            raise
        except Exception:
            valid=False
        if valid is not True:
            if profile!=self.baseline:
                self.rollback(expected_profile=profile,target_profile=self.baseline,evidence='HOST_OUTPUT_VALIDATION_FAILED')
            return {'status':'OUTPUT_REJECTED','profile':profile,'output':None}
        return {'status':'VERIFIED','profile':profile,'output':output}
