"""L2 logistic review prioritizer with separate Platt calibration and temporal test.
Never grants verification. Never silently trains from model's own labels.
"""
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from datetime import datetime

FEATURES=('source_match','freshness','independent_support','field_completeness','conflict','parser_health')


def sigmoid(z):
    if z>=0: return 1/(1+math.exp(-min(z,700)))
    e=math.exp(max(z,-700));return e/(1+e)


def logit(weights,x): return weights[0]+sum(w*v for w,v in zip(weights[1:],x))


def vector(values):
    if not isinstance(values,dict) or set(values)!=set(FEATURES): raise ValueError('FEATURE_SCHEMA_MISMATCH')
    x=[values[k] for k in FEATURES]
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in x): raise ValueError('INVALID_FEATURE')
    return x


def timestamp(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None: raise ValueError('TIMEZONE_REQUIRED')
    return d.timestamp()


def wilson_upper(errors,total,z=1.96):
    if total==0: return 1.0
    p=errors/total;z2=z*z
    return (p+z2/(2*total)+z*math.sqrt(p*(1-p)/total+z2/(4*total*total)))/(1+z2/total)


class EvidenceLearner:
    def __init__(self, *, project, purpose, revision):
        if not all(isinstance(v,str) and v for v in (project,purpose,revision)): raise ValueError('SCOPE_REQUIRED')
        self.scope={'project':project,'purpose':purpose,'revision':revision}

    def fit(self,rows):
        if not isinstance(rows,list) or not 200<=len(rows)<=5000:
            return {'status':'INSUFFICIENT_OR_EXCESSIVE_LABELS','minimum':200,'maximum':5000,'model':None}
        data=[];ids=set();groups=set();synthetic=False;label_times={}
        for r in rows:
            if any(r.get(k)!=v for k,v in self.scope.items()): raise ValueError('TRAINING_SCOPE_MISMATCH')
            if r.get('label_source') not in ('human_audit','external_outcome') or not isinstance(r.get('label_reference'),str) or not r['label_reference']:
                raise ValueError('INDEPENDENT_LABEL_REQUIRED')
            if type(r.get('label')) is not int or r['label'] not in (0,1): raise ValueError('BINARY_LABEL_REQUIRED')
            if not isinstance(r.get('id'),str) or not r['id'] or not isinstance(r.get('origin_group'),str) or not r['origin_group']:
                raise ValueError('IDENTITY_REQUIRED')
            if r['id'] in ids or r['origin_group'] in groups: raise ValueError('DUPLICATE_ORIGIN_GROUP')
            if type(r.get('synthetic')) is not bool: raise ValueError('DATA_PROVENANCE_REQUIRED')
            ids.add(r['id']);groups.add(r['origin_group']);synthetic|=r['synthetic']
            label_times[r['id']]=timestamp(r['labeled_at'])
            if label_times[r['id']]<timestamp(r['observed_at']): raise ValueError('LABEL_PRECEDES_OBSERVATION')
            data.append((timestamp(r['observed_at']),vector(r['features']),r['label'],r['id']))
        data.sort(key=lambda r:r[0])
        a=int(len(data)*.6);b=int(len(data)*.8)
        train,calibration,test=data[:a],data[a:b],data[b:]
        if train[-1][0]>=calibration[0][0] or calibration[-1][0]>=test[0][0]: raise ValueError('TIME_SPLIT_OVERLAP')
        if max(label_times[r[3]] for r in train)>=calibration[0][0] or max(label_times[r[3]] for r in calibration)>=test[0][0]:
            raise ValueError('FUTURE_LABEL_LEAKAGE')
        if any(min(sum(r[2]==0 for r in s),sum(r[2]==1 for r in s))<20 for s in (train,calibration,test)):
            return {'status':'INSUFFICIENT_CLASS_COVERAGE','model':None}
        weights=[0.0]*(len(FEATURES)+1)
        # Bounded full-batch gradient descent; inputs already bounded to [0,1].
        for _ in range(300):
            gradient=[0.0]*len(weights)
            for _,x,y,_ in train:
                err=sigmoid(logit(weights,x))-y
                gradient[0]+=err
                for j,v in enumerate(x,1): gradient[j]+=err*v
            for j in range(len(weights)):
                weights[j]-=.4*(gradient[j]/len(train)+(.01*weights[j] if j else 0))
        # Positive slope keeps rank ordering. Fit only on the calibration partition.
        slope,offset=1.0,0.0
        logits=[(logit(weights,x),y) for _,x,y,_ in calibration]
        for _ in range(200):
            ga=gb=0.0
            for z,y in logits:
                err=sigmoid(slope*z+offset)-y;ga+=err*z;gb+=err
            slope=max(.01,min(10,slope-.05*ga/len(logits)))
            offset=max(-10,min(10,offset-.05*gb/len(logits)))
        predict=lambda x:sigmoid(slope*logit(weights,x)+offset)
        prevalence=sum(r[2] for r in train)/len(train)
        brier=sum((predict(x)-y)**2 for _,x,y,_ in test)/len(test)
        constant_brier=sum((prevalence-y)**2 for _,x,y,_ in test)/len(test)
        # Threshold is fixed before test; test is not used to tune it.
        threshold=.9
        negatives=sum(y==0 for _,_,y,_ in test)
        false_high=sum(y==0 and predict(x)>=threshold for _,x,y,_ in test)
        upper=wilson_upper(false_high,negatives)
        ece=0.0
        for low in (0,.2,.4,.6,.8):
            pairs=[(predict(x),y) for _,x,y,_ in test if low<=predict(x)<low+.2+ (1e-12 if low==.8 else 0)]
            if pairs: ece+=len(pairs)/len(test)*abs(sum(p for p,y in pairs)/len(pairs)-sum(y for p,y in pairs)/len(pairs))
        drift=max(abs(sum(r[1][j] for r in train)/len(train)-sum(r[1][j] for r in test)/len(test)) for j in range(len(FEATURES)))
        passed=brier<constant_brier and upper<=.2 and ece<=.15 and drift<=.25
        status='TEST_ONLY' if synthetic else 'READY_FOR_REVIEW_RANKING' if passed else 'REJECTED'
        model={'schema_version':4,'scope':self.scope,'features':list(FEATURES),'weights':weights,
               'calibration_slope':slope,'calibration_offset':offset,'threshold':threshold,
               'operational':passed and not synthetic,'training_fingerprint':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),
               'feature_means':[sum(r[1][j] for r in train)/len(train) for j in range(len(FEATURES))],
               'verification_authority':False}
        return {'status':status,'model':model,'metrics':{'brier':brier,'constant_brier':constant_brier,
                'ece_5_bins':ece,'false_high':false_high,'test_negatives':negatives,
                'false_high_wilson95_upper':upper,'feature_mean_drift':drift,
                'train':len(train),'calibration':len(calibration),'test':len(test),'statistical_gates_passed':passed}}

    def rank(self,features,model=None):
        x=vector(features)
        if model is None or model.get('operational') is not True:
            return {'status':'RULES_ONLY','review_priority':'HIGH' if features['conflict'] or features['field_completeness']<1 else 'NORMAL','can_verify':False}
        if model.get('scope')!=self.scope or model.get('features')!=list(FEATURES) or model.get('verification_authority') is not False:
            raise ValueError('MODEL_SCOPE_OR_SCHEMA_MISMATCH')
        weights=model.get('weights')
        if not isinstance(weights,list) or len(weights)!=len(FEATURES)+1 or any(type(w) not in (int,float) or not math.isfinite(w) for w in weights): raise ValueError('INVALID_MODEL')
        for key in ('calibration_slope','calibration_offset'):
            if type(model.get(key)) not in (int,float) or not math.isfinite(model[key]): raise ValueError('INVALID_MODEL')
        score=sigmoid(model['calibration_slope']*logit(weights,x)+model['calibration_offset'])
        return {'status':'ADVISORY_ONLY','estimated_label_probability':score,
                'review_priority':'HIGH' if features['conflict'] or features['field_completeness']<1 or score<.9 else 'NORMAL',
                'can_verify':False}

    def save_model(self,report,path):
        model=report.get('model')
        if report.get('status')!='READY_FOR_REVIEW_RANKING' or not isinstance(model,dict) or model.get('operational') is not True or model.get('scope')!=self.scope or report.get('metrics',{}).get('statistical_gates_passed') is not True:
            return {'status':'MODEL_NOT_PROMODED'}
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
        try:
            with os.fdopen(fd,'w') as stream:
                json.dump(report,stream,ensure_ascii=False,allow_nan=False);stream.flush();os.fsync(stream.fileno())
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        return {'status':'ADVISORY_MODEL_SAVED','path':str(path),'can_verify':False}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    for name in ('project','purpose','revision','input','report','model'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    if len({Path(p).resolve() for p in (args.input,args.report,args.model)})!=3:
        parser.error('input, report and model must use different paths')
    learner=EvidenceLearner(project=args.project,purpose=args.purpose,revision=args.revision)
    result=learner.fit(json.loads(Path(args.input).read_text()))
    report_path=Path(args.report);report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'training_status':result['status'],'save':learner.save_model(result,args.model)},ensure_ascii=False))
