from pathlib import Path

ROOT = Path(__file__).resolve().parent
P = ROOT / 'graded_photo_multi_source.py'
s = P.read_text(encoding='utf-8')

# 1) Preserve existing candidates instead of overwriting them on every rotating run.
old = "def collect()->dict:\n registry=_registry();rows=[];stats={};errors=[]\n"
new = "def collect()->dict:\n registry=_registry();stats={};errors=[]\n previous_payload=_load(OUT,{})\n previous_rows=previous_payload.get('records',[]) if isinstance(previous_payload,dict) else []\n if not isinstance(previous_rows,list): previous_rows=[]\n previous_rows=[x for x in previous_rows if isinstance(x,dict)]\n rows=list(previous_rows)\n previous_count=len(previous_rows)\n"
if old in s:
    s = s.replace(old, new, 1)
elif 'previous_count=len(previous_rows)' not in s:
    raise SystemExit('collect anchor not found')

# 2) Keep the grader company attached to each site-scoped query as a quarantine hint.
old = "return tuple(f'site:{src[\"domain\"]} {g} {company} graded card' for company in COMPANIES)"
new = "return tuple((company,f'site:{src[\"domain\"]} {g} {company} graded card') for company in COMPANIES)"
if old in s:
    s = s.replace(old, new, 1)
elif "tuple((company,f'site:" not in s:
    raise SystemExit('query return anchor not found')

old = "for q in _queries(src,game):\n  queries+=1\n  try:\n   rows,err=_query_rows(q,10);raw.extend(rows);errors.extend(err);diag['raw_results']+=len(rows)\n"
new = "for expected_company,q in _queries(src,game):\n  queries+=1\n  try:\n   qrows,err=_query_rows(q,10)\n   for rr in qrows:\n    if isinstance(rr,dict):\n     item=dict(rr);item['_expected_company']=expected_company;raw.append(item)\n   errors.extend(err);diag['raw_results']+=len(qrows)\n"
if old in s:
    s = s.replace(old, new, 1)
elif "for expected_company,q in _queries(src,game):" not in s:
    raise SystemExit('query loop anchor not found')

old = "  c=_company(blob)\n  if not c:continue\n  diag['company_matches']+=1\n"
new = "  c=_company(blob) or str(r.get('_expected_company') or '').upper()\n  if c not in COMPANIES:continue\n  diag['company_matches']+=1\n"
if old in s:
    s = s.replace(old, new, 1)
elif "_expected_company" not in s:
    raise SystemExit('company fallback anchor not found')

# 3) Add useful aggregate diagnostics to the printed summary.
old = "'status':'ok' if rows else 'no_candidates','queries_attempted':sum(int(x.get('queries',0)) for x in stats.values()),'markets_this_run':[x['id'] for x in active],'timed_out_sources':sum(bool(x.get('timed_out')) for x in stats.values()),'initial_full_collection':first_full_collection},"
new = "'status':'ok' if rows else 'no_candidates','queries_attempted':sum(int(x.get('queries',0)) for x in stats.values()),'markets_this_run':[x['id'] for x in active],'timed_out_sources':sum(bool(x.get('timed_out')) for x in stats.values()),'initial_full_collection':first_full_collection,'previous_candidates':previous_count,'raw_results':sum(int(x.get('raw_results',0)) for x in stats.values()),'domain_matches':sum(int(x.get('domain_matches',0)) for x in stats.values()),'company_matches':sum(int(x.get('company_matches',0)) for x in stats.values())},"
if old in s:
    s = s.replace(old, new, 1)
elif "'previous_candidates':previous_count" not in s:
    raise SystemExit('summary diagnostics anchor not found')

P.write_text(s, encoding='utf-8')
print('graded photo cumulative candidate patch applied')
