"""Evidence-first verification. Learned scores can never override this gate."""
import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit

TTL={'identity':86400*30,'certificate':86400,'release':86400,'event':86400,
     'schedule':21600,'completed_sale':86400,'market_reference':3600,
     'disclosure':86400,'financial_statement':86400,'macro':86400,
     'box_office':86400,'license_policy':86400}
SCOPE={'identity':('set','number'),'certificate':('grader','cert_number'),
       'completed_sale':('condition','grade','currency','unit','quantity','price_basis','transaction_id'),
       'market_reference':('currency','unit','as_of','metric'),
       'financial_statement':('period','unit','consolidation','filing_id'),
       'disclosure':('filing_id',),'macro':('period','unit','series','vintage'),
       'box_office':('date','territory','metric'),'schedule':('territory','timezone'),
       'release':('edition',),'event':('venue',),'license_policy':('license_version',)}


def stamp(value):
    if not isinstance(value,str): raise ValueError('timestamp required')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None: raise ValueError('timezone required')
    return result.timestamp()


def canonical_url(value):
    u=urlsplit(value)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):
        raise ValueError('invalid source URL')
    query=urlencode(sorted((k,v) for k,v in parse_qsl(u.query,keep_blank_values=True) if not k.lower().startswith('utm_')))
    return urlunsplit(('https',u.hostname.lower(),u.path or '/',query,''))


def independent_count(items):
    # Connected components: A shares owner with B; B shares origin with C => one.
    parent=list(range(len(items)))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    seen={}
    for i,item in enumerate(items):
        for field in ('owner','origin','sha256','url'):
            key=(field,item[field])
            if key in seen: parent[find(i)]=find(seen[key])
            else: seen[key]=i
    return len({find(i) for i in range(len(items))})


class Verifier:
    def __init__(self, evidence_root, *, project, registry_path=None):
        self.root=Path(evidence_root).resolve()
        self.project=project
        path=Path(registry_path) if registry_path else Path(__file__).with_name('source_registry.json')
        self.registry={r['id']:r for r in json.loads(path.read_text())['sources']}

    def source_plan(self,kind,region,subject,*,limit=8,include_supporting=False):
        if type(limit) is not int or not 1<=limit<=32: raise ValueError('bounded source plan required')
        matching=[r for r in self.registry.values() if self.project in r['projects'] and kind in r['kinds']
                  and (subject in r['subjects'] or (subject in ('pokemon','onepiece','naruto') and 'cards' in r['subjects']) or (subject in ('pokemon','onepiece','naruto','anime') and 'anime' in r['subjects']))]
        if not include_supporting:
            matching=[r for r in matching if r.get('evidence_role','primary')=='primary']
        # Region match is GLOBAL only when the source declares it.
        matching=[r for r in matching if region in r['regions'] or 'GLOBAL' in r['regions']]
        matching.sort(key=lambda r:(r.get('evidence_role','primary')!='primary',r['discovery_status']!='PAGE_READ',r['id']))
        ordered=[];owners=set()
        for repeat in (False,True):
            for r in matching:
                if (r['owner_group'] in owners)!=repeat or r in ordered: continue
                ordered.append(r);owners.add(r['owner_group'])
        return ordered[:limit]

    def verify(self,claim,evidence,*,inspect,now=None):
        if not isinstance(claim,dict) or claim.get('project')!=self.project:
            raise ValueError('PROJECT_MISMATCH')
        kind=claim.get('kind')
        if kind not in TTL: raise ValueError('UNSUPPORTED_CLAIM_KIND')
        for key in ('id','entity','region','language','subject'):
            if not isinstance(claim.get(key),str) or not claim[key]: raise ValueError('INCOMPLETE_CLAIM')
        if 'value' not in claim or not isinstance(claim.get('scope'),dict) or any(k not in claim['scope'] or claim['scope'][k] in (None,'') for k in SCOPE[kind]):
            raise ValueError('INCOMPLETE_CLAIM_SCOPE')
        if not isinstance(evidence,list) or len(evidence)>32: raise ValueError('EVIDENCE_LIMIT')
        current=stamp(now) if now else datetime.now(timezone.utc).timestamp()
        accepted=[];rejected=[];contradictions=[]
        for e in evidence:
            eid=e.get('id','unknown') if isinstance(e,dict) else 'unknown'
            try:
                if not isinstance(e,dict): raise ValueError('INVALID_EVIDENCE')
                source=self.registry.get(e.get('source_id'))
                if not source or self.project not in source['projects'] or kind not in source['kinds']:
                    raise ValueError('SOURCE_PURPOSE_MISMATCH')
                if claim['region'] not in source['regions'] and 'GLOBAL' not in source['regions']:
                    raise ValueError('SOURCE_REGION_MISMATCH')
                if claim['subject'] not in source['subjects'] and not (claim['subject'] in ('pokemon','onepiece','naruto') and 'cards' in source['subjects']) and not (claim['subject'] in ('pokemon','onepiece','naruto','anime') and 'anime' in source['subjects']):
                    raise ValueError('SOURCE_SUBJECT_MISMATCH')
                for field in ('project','entity','region','language','kind','scope'):
                    if e.get(field)!=claim[field]: raise ValueError('IDENTITY_OR_SCOPE_MISMATCH')
                url=canonical_url(e['url'])
                allowed=set(source.get('allowed_hosts',[]))|{urlsplit(source['url']).hostname}
                if urlsplit(url).hostname not in allowed: raise ValueError('SOURCE_HOST_MISMATCH')
                age=current-stamp(e['fetched_at'])
                if age<0 or age>TTL[kind]: raise ValueError('STALE_OR_FUTURE_EVIDENCE')
                if e.get('snippet_only') is not False or not e.get('origin_key'):
                    raise ValueError('ORIGINAL_EVIDENCE_REQUIRED')
                body_path=(self.root/e['body_file']).resolve()
                if not body_path.is_relative_to(self.root) or not body_path.is_file(): raise ValueError('BODY_PATH_INVALID')
                if not 0<body_path.stat().st_size<=2_000_000: raise ValueError('BODY_SIZE_INVALID')
                body=body_path.read_bytes()
                sha=hashlib.sha256(body).hexdigest()
                if sha!=e.get('sha256'): raise ValueError('BODY_HASH_MISMATCH')
                reviewed=inspect(source,claim,e,body)
                if not isinstance(reviewed,dict) or reviewed.get('inspected') is not True or not isinstance(reviewed.get('reference'),str) or not reviewed['reference']:
                    raise ValueError('SEMANTIC_REVIEW_REQUIRED')
                if reviewed.get('source_capture_verified') is not True or not isinstance(reviewed.get('source_capture_reference'),str) or not reviewed['source_capture_reference']:
                    raise ValueError('SOURCE_CAPTURE_PROOF_REQUIRED')
                if reviewed.get('contradicts') is True:
                    contradictions.append(eid);continue
                if reviewed.get('matches') is not True or reviewed.get('value')!=claim['value']:
                    raise ValueError('VALUE_NOT_CONFIRMED')
                if kind=='completed_sale':
                    sale=reviewed.get('sale',{})
                    if sale.get('final') is not True or sale.get('status')!='SOLD' or sale.get('hidden_price') is not False:
                        raise ValueError('FINAL_SALE_REQUIRED')
                    if sale.get('transaction_id')!=claim['scope']['transaction_id'] or sale.get('currency')!=claim['scope']['currency']:
                        raise ValueError('TRANSACTION_MISMATCH')
                    if stamp(sale['sold_at'])>current: raise ValueError('FUTURE_SALE')
                    if type(sale.get('amount')) not in (int,float) or not math.isfinite(sale['amount']) or sale['amount']<=0 or sale['amount']!=claim['value']:
                        raise ValueError('REALIZED_AMOUNT_REQUIRED')
                if kind=='certificate' and reviewed.get('cert_record_match') is not True:
                    raise ValueError('CERT_RECORD_REQUIRED')
                role=source.get('evidence_role','primary')
                if role=='supporting_only':
                    if reviewed.get('official_account_verified') is not True or not isinstance(reviewed.get('account_reference'),str) or not reviewed['account_reference']:
                        raise ValueError('OFFICIAL_ACCOUNT_PROOF_REQUIRED')
                    if not isinstance(e.get('platform_post_id'),str) or not e['platform_post_id'] or not isinstance(e.get('author_id'),str) or not e['author_id']:
                        raise ValueError('SOCIAL_IDENTITY_REQUIRED')
                accepted.append({'id':eid,'owner':source['owner_group'],'origin':e['origin_key'],'sha256':sha,'url':url,
                                 'review_reference':reviewed['reference'],'role':role})
            except (ValueError,KeyError,TypeError,OSError) as exc:
                # Exception text may contain secrets: use only our known uppercase codes.
                code=str(exc)
                if not code.replace('_','').isalpha() or code.upper()!=code: code='INVALID_EVIDENCE'
                rejected.append({'id':eid,'code':code})
        groups=independent_count(accepted)
        primary_groups=independent_count([x for x in accepted if x['role']=='primary']) if any(x['role']=='primary' for x in accepted) else 0
        required=2 if kind in ('release','event','schedule') else 1
        status='CONFLICT' if contradictions else 'NEEDS_EVIDENCE' if groups<required or primary_groups<1 else 'VERIFIED_CROSSCHECK' if groups>=2 else 'VERIFIED_PRIMARY'
        return {'schema_version':6,'project':self.project,'claim_id':claim['id'],'kind':kind,'status':status,
                'verification_complete':status.startswith('VERIFIED_'),'independent_groups':groups,'required_groups':required,
                'primary_groups':primary_groups,
                'accepted':accepted,'rejected':rejected,'contradictions':contradictions,
                'next_action':'RESOLVE_CONFLICT' if contradictions else 'FETCH_MISSING_EVIDENCE' if groups<required else 'PERSIST_VERIFIED_RECEIPT',
                'model_may_override':False}

    def verify_and_record(self,claim,evidence,*,inspect,ledger_path,now=None):
        result=self.verify(claim,evidence,inspect=inspect,now=now)
        path=Path(ledger_path);path.parent.mkdir(parents=True,exist_ok=True)
        claim_hash=hashlib.sha256(json.dumps(claim,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        result_hash=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        # History is append-only by content hash; rechecking never erases a conflict.
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS binding (singleton INTEGER PRIMARY KEY, project TEXT)')
            db.execute('INSERT OR IGNORE INTO binding VALUES (1,?)',(self.project,))
            if db.execute('SELECT project FROM binding WHERE singleton=1').fetchone()[0]!=self.project:
                raise ValueError('LEDGER_PROJECT_MISMATCH')
            db.execute('CREATE TABLE IF NOT EXISTS receipts (claim_id TEXT, claim_hash TEXT, result_hash TEXT, checked_at TEXT, result TEXT, PRIMARY KEY(claim_hash,result_hash))')
            db.execute('INSERT OR IGNORE INTO receipts VALUES (?,?,?,?,?)',(claim['id'],claim_hash,result_hash,now or datetime.now(timezone.utc).isoformat(),json.dumps(result,ensure_ascii=False)))
        return result
