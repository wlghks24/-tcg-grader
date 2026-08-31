#!/usr/bin/env python3
"""V99 company-aware grading/calibration utilities.

Learns only from user-confirmed official grades. Corrections are downward-only,
company-separated, deduplicated by certification number, and accepted only if
cross-validation reduces error. Raw predictions are kept separate from already
calibrated predictions to prevent feedback loops.
"""
from __future__ import annotations
import hashlib, math, statistics
from typing import Any, Iterable

VERSION='v99-accuracy-selflearning-hardened'
COMPANIES=('PSA','BGS','CGC','TAG','BRG')
HALF=tuple(i/2 for i in range(2,21))
STEPS={
 'PSA':tuple(float(i) for i in range(1,11)),
 'BGS':HALF,'CGC':HALF,'BRG':HALF,
 'TAG':tuple(x for x in HALF if x!=9.5),
}
OFFICIAL={
 'PSA':{10:(45,25)},
 'BGS':{10:(50,40),9.5:(45,40),9:(45,30),8:(40,20),7:(35,15),6:(30,10),5:(25,10),4:(20,5),3:(15,5),2:(10,5)},
 # CGC publishes condition definitions but not a complete numeric centering table.
 # Keep only the public Gem Mint 10 tolerance as a hard gate; lower grades use
 # the conservative generic monotonic fallback instead of invented thresholds.
 'CGC':{10:(45,25)},
 # TAG numeric 10 uses the public Gem Mint 10 TCG centering tolerance.
 # Pristine 10 is stricter (about 51/49 front, 52/48 back) but has the same numeric grade.
 'TAG':{10:(45,35),9:(40,25),8.5:(37.5,15),8:(35,5)},'BRG':{},
}

def finite(v:Any)->float|None:
 try:x=float(v)
 except (TypeError,ValueError,OverflowError):return None
 return x if math.isfinite(x) else None

def clamp(v:float,a:float,b:float)->float:return max(a,min(b,v))

def quantize_down(company:str,value:float)->float:
 company=str(company or '').upper();v=finite(value)
 if company not in STEPS or v is None:return 1.0
 v=clamp(v,1,10);out=STEPS[company][0]
 for step in STEPS[company]:
  if step<=v+1e-9:out=step
  else:break
 return float(out)

def risk_to_grade(risk:float)->float:
 r=finite(risk)
 if r is None or r<0:return 1.0
 for limit,grade in ((5,10),(10,9.5),(16,9),(23,8.5),(31,8),(40,7.5),(50,7),(60,6),(70,5),(80,4),(88,3),(94,2)):
  if r<limit:return float(grade)
 return 1.0

def combine_defect_risk(surface:float,edge:float,corner:float)->float:
 values=[]
 for value,weight in ((surface,1.0),(edge,.90),(corner,.95)):
  x=finite(value)
  if x is not None:values.append(x*weight)
 return clamp(max(values) if values else 100,0,100)

def general_center_grade(front:float,back:float)->float:
 f,b=finite(front),finite(back)
 if f is None or b is None:return 1.0
 w=min(50,f,b)
 for threshold,grade in ((45,10),(40,9),(35,8),(30,7),(25,6),(20,5),(15,4),(10,3),(5,2)):
  if w>=threshold:return float(grade)
 return 1.0

def grade_by_center(front:float,back:float,company:str)->float:
 company=str(company or '').upper();f,b=finite(front),finite(back)
 if company not in COMPANIES or f is None or b is None or f<0 or b<0 or f>50 or b>50:return 1.0
 table=OFFICIAL[company]
 for grade in sorted(table,reverse=True):
  tf,tb=table[grade]
  if f>=tf and b>=tb:return float(grade)
 floor_limit=min(table)-.5 if table else 10
 return float(min(general_center_grade(f,b),floor_limit))

def estimate_raw_grade(front:float,back:float,surface:float,edge:float,corner:float,company:str)->float:
 return quantize_down(company,min(risk_to_grade(combine_defect_risk(surface,edge,corner)),grade_by_center(front,back,company)))

def _valid_actual(company:str,value:Any)->float|None:
 company=str(company or '').upper();x=finite(value)
 if company not in STEPS or x is None:return None
 return float(x) if any(abs(x-step)<1e-9 for step in STEPS[company]) else None

def valid_actual_grade(company:str,value:Any)->bool:
 return _valid_actual(company,value) is not None

def _cert(value:Any)->str:
 text=str(value or '').strip()
 return text if 4<=len(text)<=120 and all(ch.isalnum() or ch in '-_./' for ch in text) else ''

def sanitize_rows(payload:Any)->list[dict[str,Any]]:
 if not isinstance(payload,dict):return []
 # V99 is authoritative. Legacy V30 is imported only when no V99 rows exist,
 # preventing stale legacy records from overwriting a newer certified result.
 modern=payload.get('v99_validation',[])
 legacy=payload.get('v30_validation',[])
 source=(modern if isinstance(modern,list) and modern else legacy if isinstance(legacy,list) else [])[-1000:]
 dedup:dict[str,dict[str,Any]]={}
 conflicts:set[str]=set()
 for row in source:
  if not isinstance(row,dict) or row.get('official_result') is not True:continue
  company=str(row.get('company') or row.get('grader') or '').upper()
  if company not in COMPANIES:continue
  actual=_valid_actual(company,row.get('actual'))
  raw=finite(row.get('raw_pred',row.get('pred')))
  cert=_cert(row.get('certification_id') or row.get('cert_no'))
  if actual is None or raw is None or not 1<=raw<=10 or not cert:continue
  vision=row.get('vision') if isinstance(row.get('vision'),dict) else {}
  ac=finite(vision.get('analysisConfidence'));sc=finite(vision.get('surfaceConfidence'))
  if ac is not None and ac<55:continue
  if sc is not None and sc<35:continue
  key=f'{company}|{cert}'
  if key in conflicts:continue
  previous=dedup.get(key)
  if previous is not None and abs(float(previous['actual'])-actual)>1e-9:
   # Same certification cannot safely teach two different official grades.
   dedup.pop(key,None);conflicts.add(key);continue
  card_key=str(row.get('card_key') or '').strip()[:180]
  item={'company':company,'actual':actual,'raw_pred':raw,'certification_id':cert,
        'card_id':str(row.get('card_id') or card_key or cert)[:120]}
  if card_key:item['card_key']=card_key
  if vision:item['vision']=vision
  dedup[key]=item
 return list(dedup.values())

def _fold(card_id:str)->int:return int(hashlib.sha256(card_id.encode()).hexdigest()[:8],16)%5

def _tier(n:int)->float:return 0 if n<5 else .25 if n<10 else .5 if n<30 else .75 if n<60 else 1

def _candidate(rows:list[dict[str,Any]],evidence_n:int|None=None)->float:
 """Build a downward-only candidate without using holdout labels.

 ``evidence_n`` controls only the conservative strength tier. During grouped
 cross-validation we use the size of the full verified company dataset for
 that tier while computing the residual exclusively from the training fold.
 This avoids a boundary bug where a 10-row model could never prove a -0.5
 correction because every training fold temporarily fell below 10 rows and
 produced a no-op -0.25 correction. Holdout outcomes still decide whether the
 candidate is allowed to activate.
 """
 if not rows:return 0.0
 residual=[r['actual']-r['raw_pred'] for r in rows]
 med=statistics.median(residual)
 mad=statistics.median(abs(x-med) for x in residual) if residual else 0
 radius=max(.5,3*1.4826*mad)
 clipped=[clamp(x,med-radius,med+radius) for x in residual]
 robust=statistics.median(clipped)
 support=max(len(rows),int(evidence_n or len(rows)))
 return round(clamp(min(0,robust)*_tier(support),-.75,0)*20)/20

def apply_downward_correction(company:str,raw:Any,correction:Any)->float:
 company=str(company or '').upper();raw_value=finite(raw);corr=finite(correction)
 if company not in STEPS or raw_value is None:return 1.0
 corr=clamp(min(0,corr or 0),-1,0)
 if abs(corr)<0.5:return quantize_down(company,raw_value)
 value=clamp(raw_value+corr,1,10);steps=STEPS[company]
 # A downward correction that reaches the exact midpoint chooses the lower
 # valid grade. Smaller corrections are ignored above, so this is conservative
 # while remaining identical to the browser implementation.
 return float(min(steps,key=lambda step:(abs(step-value),step)))

def _metrics(rows:list[dict[str,Any]],correction:float,company:str)->tuple[float,float]:
 if not rows:return math.inf,math.inf
 err=[abs(apply_downward_correction(company,r['raw_pred'],correction)-r['actual']) for r in rows]
 return sum(err)/len(err),max(err)

def train_company_calibration(rows:Iterable[dict[str,Any]])->dict[str,dict[str,Any]]:
 rows=list(rows);out={}
 for company in COMPANIES:
  group=[r for r in rows if r['company']==company];n=len(group);unique=len({r['card_id'] for r in group})
  before_all=[];after_all=[];nonworse=0;used=0
  for fold in range(5):
   hold=[r for r in group if _fold(r['card_id'])==fold];train=[r for r in group if _fold(r['card_id'])!=fold]
   if not hold or len(train)<5:continue
   # Strength is based on total independently verified evidence, while the
   # candidate residual itself is computed only from this training fold.
   corr=_candidate(train,evidence_n=n);b,_=_metrics(hold,0,company);a,_=_metrics(hold,corr,company)
   before_all.extend(abs(apply_downward_correction(company,r['raw_pred'],0)-r['actual']) for r in hold)
   after_all.extend(abs(apply_downward_correction(company,r['raw_pred'],corr)-r['actual']) for r in hold)
   nonworse+=int(a<=b+1e-9);used+=1
  correction=_candidate(group,evidence_n=n)
  before=sum(before_all)/len(before_all) if before_all else math.inf
  after=sum(after_all)/len(after_all) if after_all else math.inf
  enabled=n>=10 and unique>=8 and used>=2 and correction<0 and after+.03<=before and nonworse/max(1,used)>=.6
  out[company]={'n':n,'unique_cards':unique,'folds':used,'nonworse_folds':nonworse,
                'enabled':bool(enabled),'correction':correction if enabled else 0.0,
                'cv_mae_before':None if math.isinf(before) else round(before,4),
                'cv_mae_after':None if math.isinf(after) else round(after,4),
                'reason':'cv-improved' if enabled else ('insufficient-labels' if n<10 or unique<8 else 'no-safe-cv-improvement')}
 return out

def apply_calibration(company:str,raw:float,models:dict[str,dict[str,Any]])->float:
 company=str(company or '').upper()
 if company not in STEPS:return 1.0
 row=models.get(company,{}) if isinstance(models,dict) else {}
 correction=finite(row.get('correction')) if isinstance(row,dict) and row.get('enabled') is True else 0
 return apply_downward_correction(company,raw,correction or 0)
