#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, html
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

OFFICIAL = {
    'PSA': {'home':'https://www.psacard.com/cert','direct':'https://www.psacard.com/cert/{cert}'},
    'BGS': {'home':'https://www.beckett.com/grading/card-lookup','direct':'https://www.beckett.com/grading/card-lookup?item_id={cert}&item_type=BGS'},
    'CGC': {'home':'https://www.cgccards.com/certlookup/','direct':'https://www.cgccards.com/certlookup/'},
    'TAG': {'home':'https://taggrading.com/pages/cert-search','direct':'https://taggrading.com/pages/cert-search'},
    'BRG': {'home':'https://break.co.kr/','direct':'https://break.co.kr/'},
}

def _clean_cert(value):
    return re.sub(r'[^A-Za-z0-9.-]','',str(value or '').strip())[:120]

def lookup_url(company, cert):
    company=str(company or '').upper()
    cert=_clean_cert(cert)
    cfg=OFFICIAL.get(company)
    if not cfg:return ''
    return cfg['direct'].format(cert=quote(cert)) if '{cert}' in cfg['direct'] else cfg['direct']

def _fetch(url, timeout=10):
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 TCG-Grader/1.0','Accept':'text/html,application/xhtml+xml'})
    with urlopen(req,timeout=timeout) as r:
        raw=r.read(900000)
        return raw.decode(r.headers.get_content_charset() or 'utf-8','ignore')

def _text(raw):
    raw=re.sub(r'(?is)<script.*?</script>|<style.*?</style>',' ',raw)
    raw=re.sub(r'(?s)<[^>]+>',' ',raw)
    return re.sub(r'\s+',' ',html.unescape(raw)).strip()

def _grade_from_text(company, text):
    patterns=[]
    if company=='BGS': patterns=[r'FINAL\s+GRADE\s*([0-9]+(?:\.[0-9])?)']
    elif company=='PSA': patterns=[r'(?:Grade|GRADE)\s*(?:PSA\s*)?([0-9]+(?:\.[0-9])?)\b']
    for p in patterns:
        m=re.search(p,text,re.I)
        if m:
            try:
                g=float(m.group(1))
                if 1<=g<=10:return g
            except ValueError:pass
    return None

def verify_cert(company, cert):
    company=str(company or '').upper(); cert=_clean_cert(cert)
    if company not in OFFICIAL:return {'ok':False,'verified':False,'error':'지원하지 않는 등급사'}
    if len(cert)<4:return {'ok':False,'verified':False,'error':'인증번호를 확인하세요','official_url':OFFICIAL[company]['home']}
    url=lookup_url(company,cert)
    result={'ok':True,'verified':False,'company':company,'certification_id':cert,'official_url':url,'grade':None,'mode':'official_lookup'}
    # Only PSA/BGS currently expose stable direct result pages we can safely parse.
    if company not in ('PSA','BGS'):
        result['notice']='공식 조회 페이지에서 결과 확인이 필요합니다. 등급을 읽지 못한 상태에서는 자동학습하지 않습니다.'
        return result
    try:
        text=_text(_fetch(url))
        if cert.lower() not in text.lower():
            result['notice']='공식 페이지에서 인증번호 일치를 확인하지 못했습니다.'
            return result
        grade=_grade_from_text(company,text)
        if grade is None:
            result['notice']='공식 페이지는 열렸지만 등급을 안전하게 추출하지 못했습니다.'
            return result
        result.update({'verified':True,'grade':grade,'notice':'공식 인증번호와 등급을 확인했습니다.'})
        return result
    except (URLError,HTTPError,TimeoutError,OSError):
        result['notice']='공식 사이트 응답 제한으로 자동확인하지 못했습니다. 공식 조회 페이지를 사용하세요.'
        return result
