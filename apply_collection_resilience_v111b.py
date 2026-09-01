#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PATH=ROOT/'graded_photo_multi_source.py'


def replace_once(text,old,new,label):
    if new in text:
        return text
    if old not in text:
        raise RuntimeError('missing '+label)
    return text.replace(old,new,1)


def main():
    text=PATH.read_text(encoding='utf-8')
    # A project baseline is emergency bootstrap only. It must not add an extra
    # verified row when a device/test already has a valid local registry.
    text=replace_once(text,
        "for path in (VERIFIED,LIBRARY_OFFICIAL,BASELINE_VERIFIED):\n  d=_load(path,{})",
        "for path in (VERIFIED,LIBRARY_OFFICIAL):\n  d=_load(path,{})",
        'registry path')
    anchor="  if c in COMPANIES and cert and (r.get('verified') is True or r.get('officially_verified') is True or r.get('official_result') is True):out[(c,cert)]=g\n return out\n\ndef _library_verified_evidence"
    replacement="""  if c in COMPANIES and cert and (r.get('verified') is True or r.get('officially_verified') is True or r.get('official_result') is True):out[(c,cert)]=g
 if not out:
  d=_load(BASELINE_VERIFIED,{})
  values=d.get('certifications',[]) if isinstance(d,dict) else []
  for r in values if isinstance(values,list) else []:
   if not isinstance(r,dict):continue
   c=str(r.get('company') or '').upper();cert=normalize_cert(r.get('certification_id') or r.get('cert_no'))
   try:g=float(r.get('grade') if r.get('grade') is not None else r.get('actual'))
   except (TypeError,ValueError,OverflowError):continue
   if c in COMPANIES and cert and 1<=g<=10 and (r.get('verified') is True or r.get('officially_verified') is True or r.get('official_result') is True):out[(c,cert)]=g
 return out

def _library_verified_evidence"""
    text=replace_once(text,anchor,replacement,'registry fallback')

    text=replace_once(text,
        "for path in (VERIFIED,LIBRARY_OFFICIAL,BASELINE_VERIFIED):\n  data=_load(path,{})",
        "for path in (VERIFIED,LIBRARY_OFFICIAL):\n  data=_load(path,{})",
        'seed path')
    anchor="                'image_evidence_source':'prevalidated_library_photo' if evidence.get('image_sha256') else 'not_available'})\n return rows\n\ndef _reference_learning_seed_rows"
    replacement="""                'image_evidence_source':'prevalidated_library_photo' if evidence.get('image_sha256') else 'not_available'})
 if not rows:
  data=_load(BASELINE_VERIFIED,{})
  values=data.get('certifications',[]) if isinstance(data,dict) else []
  for item in values if isinstance(values,list) else []:
   if not isinstance(item,dict):continue
   company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id') or item.get('cert_no'))
   try:grade=float(item.get('grade') if item.get('grade') is not None else item.get('actual'))
   except (TypeError,ValueError,OverflowError):continue
   verified=item.get('verified') is True or item.get('officially_verified') is True or item.get('official_result') is True
   if not verified or company not in COMPANIES or not cert or not 1<=grade<=10:continue
   official=str(item.get('official_reference_url') or lookup_url(company,cert))
   rows.append({'source_id':'official_registry','source':f'{company} 공식 인증조회','search_provider':'official_registry',
                'url':official,'title':str(item.get('card_name') or f'{company} cert {cert}')[:260],'snippet':'','image_url':'',
                'company':company,'grade':grade,'certification_id':cert,'game':str(item.get('game') or 'unknown').lower(),
                'mode':'slab','source_weight':1.0,'official_result':True,'official_grade':grade,
                'official_reference_url':official,'verification_method':'immutable_verified_baseline_fallback',
                'status':'verified_reference','learning_eligibility':'reference_learning_only','image_validated':False,
                'image_probe_status':'not_available','ocr_label_text':'','image_evidence_source':'not_available',
                'baseline_bootstrap':True})
 return rows

def _reference_learning_seed_rows"""
    text=replace_once(text,anchor,replacement,'seed fallback')
    text=text.replace("'baseline_verified_seed_count':sum(1 for x in seeds if str(x.get('source_id'))=='official_registry'),",
                      "'baseline_verified_seed_count':sum(1 for x in seeds if x.get('baseline_bootstrap') is True),",1)
    PATH.write_text(text,encoding='utf-8')
    print('conditional verified baseline v111b applied')

if __name__=='__main__':
    main()
