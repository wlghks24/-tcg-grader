from pathlib import Path

P=Path(__file__).resolve().parent/'graded_photo_multi_source.py'
s=P.read_text(encoding='utf-8')
old="""def _queries(src:dict,game:str)->tuple[str,...]:
 g={'pokemon':'Pokemon','onepiece':'One Piece','naruto':'Naruto'}[game]
 return (f'site:{src[\"domain\"]} {g} (PSA OR BGS OR CGC OR TAG OR BRG) (10 OR 9.5 OR graded OR slab)',)
"""
new="""def _queries(src:dict,game:str)->tuple[str,...]:
 g={'pokemon':'Pokemon','onepiece':'One Piece','naruto':'Naruto'}[game]
 # Simple per-grader queries are deliberately used here. Public search engines
 # often return zero or unrelated rows for long nested OR expressions.
 return tuple(f'site:{src[\"domain\"]} {g} {company} graded card' for company in COMPANIES)
"""
if old not in s:
    raise SystemExit('query block not found')
s=s.replace(old,new,1)

# Record raw/domain/company pass counts so zero-result runs are diagnosable.
old2="""def _discover_source_game(src:dict,game:str)->tuple[list[dict],list[str],int]:
 raw=[];errors=[];queries=0
"""
new2="""def _discover_source_game(src:dict,game:str)->tuple[list[dict],list[str],int,dict]:
 raw=[];errors=[];queries=0
 diag={'raw_results':0,'domain_matches':0,'company_matches':0}
"""
if old2 not in s:
    raise SystemExit('discover signature not found')
s=s.replace(old2,new2,1)

old3="""   rows,err=_query_rows(q,10);raw.extend(rows);errors.extend(err)
"""
new3="""   rows,err=_query_rows(q,10);raw.extend(rows);errors.extend(err);diag['raw_results']+=len(rows)
"""
s=s.replace(old3,new3,1)

old4="""  candidates.setdefault(url,r)
 out=[]
"""
new4="""  candidates.setdefault(url,r)
 diag['domain_matches']=len(candidates)
 out=[]
"""
if old4 not in s:
    raise SystemExit('candidate anchor not found')
s=s.replace(old4,new4,1)

old5="""  if not c:continue
  g=_grade(blob,c);cert=_cert(blob);image=str(r.get('image_url') or '')
"""
new5="""  if not c:continue
  diag['company_matches']+=1
  g=_grade(blob,c);cert=_cert(blob);image=str(r.get('image_url') or '')
"""
if old5 not in s:
    raise SystemExit('company anchor not found')
s=s.replace(old5,new5,1)

old6=""" return out,errors,queries

def _collect_public_source(src:dict):
 found=[];errors=[];queries=0
 for game in GAMES:
  rows,err,q=_discover_source_game(src,game);found.extend(rows);errors.extend(err);queries+=q
"""
new6=""" return out,errors,queries,diag

def _collect_public_source(src:dict):
 found=[];errors=[];queries=0;diag={'raw_results':0,'domain_matches':0,'company_matches':0}
 for game in GAMES:
  rows,err,q,d=_discover_source_game(src,game);found.extend(rows);errors.extend(err);queries+=q
  for k in diag: diag[k]+=int(d.get(k,0))
"""
if old6 not in s:
    raise SystemExit('collect source anchor not found')
s=s.replace(old6,new6,1)

old7=""" return src['id'],list(seen.values())[:MAX_PER_SOURCE],errors,queries
"""
new7=""" return src['id'],list(seen.values())[:MAX_PER_SOURCE],errors,queries,diag
"""
s=s.replace(old7,new7,1)

old8="""   sid,found,errs,queries=fut.result();rows.extend(found)
   stats[sid]={'candidates':len(found),'image_hits':sum(bool(x.get('image_url')) for x in found),'verified_hits':0,'errors':len(errs),'queries':queries}
"""
new8="""   sid,found,errs,queries,diag=fut.result();rows.extend(found)
   stats[sid]={'candidates':len(found),'image_hits':sum(bool(x.get('image_url')) for x in found),'verified_hits':0,'errors':len(errs),'queries':queries,**diag}
"""
if old8 not in s:
    raise SystemExit('future result anchor not found')
s=s.replace(old8,new8,1)

P.write_text(s,encoding='utf-8')
print('graded photo simple queries + diagnostics applied')
