#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime, timezone

# Official-source baseline verified 2026-08-29. Variable checkout shipping is never fabricated.
COMPANIES={
 'PSA':{
  'source':'https://www.psacard.com/submit',
  'currency':'USD','shipping':'checkout_calculated','insurance':'tier_max_insured_value',
  'services':[
   {'name':'Regular','fee':79.99,'max_insured_value':1500},
   {'name':'Express','fee':149.00,'max_insured_value':2500},
   {'name':'Super Express','fee':349.00,'max_insured_value':5000},
   {'name':'Walk-Through','fee':599.00,'max_insured_value':10000},
   {'name':'Premium +','fee':999.00,'max_insured_value':25000},
  ],
 },
 'BGS':{
  'source':'https://www.beckett.com/grading','currency':'USD','shipping':'checkout_calculated','insurance':'return_shipping_and_insurance_variable',
  'services':[
   {'name':'Base','fee':14.95,'availability':'paused'},
   {'name':'Base + Subgrades','fee':17.95,'availability':'paused'},
   {'name':'Standard','fee':34.95,'availability':'paused'},
   {'name':'Express','fee':79.95,'availability':'open'},
   {'name':'Priority','fee':124.95,'availability':'open'},
  ],
 },
 'CGC':{
  'source':'https://www.cgccards.com/submit/services-fees/cgc-grading/?view=cards','currency':'USD','shipping':'checkout_calculated','insurance':'declared_value_tier',
  'services':[
   {'name':'Bulk','fee':17.00,'min_cards':25,'max_value':500},
   {'name':'Economy','fee':20.00,'max_value':1000},
   {'name':'Standard','fee':55.00,'max_value':3000},
   {'name':'Express','fee':100.00,'max_value':10000},
   {'name':'WalkThrough','fee':300.00,'max_value':100000},
  ],
 },
 'TAG':{
  'source':'https://taggrading.com/pages/pricing','currency':'USD','shipping':'return_shipping_flat_at_checkout','insurance':'included_by_tier',
  'services':[
   {'name':'Basic','fee':22.00,'min_cards':10,'insurance_per_card':300},
   {'name':'Standard','fee':39.00,'insurance_per_card':500},
   {'name':'Express','fee':59.00,'insurance_per_card':1000},
   {'name':'Priority','fee':149.00,'insurance_per_card':2500},
   {'name':'Walkthrough','fee':299.00,'insurance_per_card':5000},
  ],
  'extras':[{'name':'Submission Kit','fee':49.95,'currency':'USD','coverage_order':1000,'region':'US only'},
            {'name':'Return Shipping Insurance','fee':14.99,'currency':'USD','coverage_order':1000}],
 },
 'BRG':{
  'source':'https://break.co.kr/','currency':'KRW','shipping':'domestic_carrier_actual','insurance':'carrier_actual',
  'services':[
   {'name':'Regular','fee':19800},
   {'name':'Express','fee':39800},
   {'name':'Bulk','fee':13800,'min_cards':20},
   {'name':'Reholder','fee':9800},
   {'name':'BRG GEN','fee':9800},
  ],
  'extras':[{'name':'오토 등급','fee':3000,'currency':'KRW'}],
 },
}

def get_grading_costs():
    return {
      'ok':True,
      'checked_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
      'refresh_hours':6,
      'companies':COMPANIES,
      'notice':'공식 고정요금만 자동 계산합니다. 국제/국내 배송비와 일부 보험료는 목적지·수량·신고가액에 따라 체크아웃/택배사에서 달라지므로 실제 결제값을 사용해야 합니다.',
    }
