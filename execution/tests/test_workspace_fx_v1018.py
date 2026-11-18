"""Actual inline FX code in an offline synthetic VM; no browser/network."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
STAMP = '2026-11-15T00:00:00.000Z'
JS = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[1],'utf8'),start=html.indexOf('const FX_MAX_AGE_MS='),end=html.indexOf('function notifyMarketFx()');
assert(start>=0&&end>start);const code=html.slice(start,end),NOW=Date.parse('2026-11-15T00:00:00.000Z');
class FrozenDate extends Date{static now(){return NOW}}
(async()=>{for(const row of JSON.parse(process.argv[2])){
 const badge={removed:false,remove(){this.removed=true}};
 const ctx={Date:FrozenDate,URL,fetch:async()=>({ok:true,json:async()=>row.payload}),fxRates:{JPY_KRW:9,USD_KRW:1400},fxUpdated:'old',fxTimestamp:'old',fxExpiryTimer:1,document:{querySelectorAll:()=>[badge]},renderCountryAnalysis(){},renderTradeCatalog(){},notifyMarketFx(){},setTimeout:()=>1,clearTimeout(){}};
 vm.createContext(ctx);vm.runInContext(code+';globalThis.run=loadExchangeRates',ctx);
 const result=await ctx.run(true);assert.equal(result.ok,row.accepted,row.name);
 if(!row.accepted){assert.equal(ctx.fxRates.USD_KRW,0,row.name);assert.equal(ctx.fxRates.JPY_KRW,0,row.name);assert.equal(ctx.fxTimestamp,'',row.name);assert.equal(badge.removed,true,row.name)}
 else{assert.equal(ctx.fxRates.USD_KRW,1400,row.name);assert.equal(ctx.fxRates.JPY_KRW,9,row.name)}
 if('eur' in row)assert.equal(ctx.fxRates.EUR_KRW,row.eur,row.name);
}console.log('PASS')})().catch(e=>{console.error(e.stack);process.exit(1)});
'''

class WorkspaceFxV1018Tests(unittest.TestCase):
    def payload(self, **changes):
        data = {'base':'KRW','source':'https://api.frankfurter.dev/v2/rates',
                'source_route':'frankfurter-v2','source_timestamp':STAMP,'updated_at':STAMP,
                'rates':{'JPY_KRW':9,'USD_KRW':1400,'EUR_KRW':1500}}
        data.update(changes)
        return data

    def run_cases(self, cases):
        result = subprocess.run(['node','-e',JS,str(ROOT/'index.html'),json.dumps(cases)],capture_output=True,text=True,timeout=20)
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertEqual('PASS',result.stdout.strip())

    def test_provenance_and_approved_source_routes(self):
        cases=[]
        for route,host in [('frankfurter-v2','api.frankfurter.dev'),('frankfurter-v1','api.frankfurter.dev'),('frankfurter-legacy','api.frankfurter.app')]:
            cases.append({'name':route,'payload':self.payload(source_route=route,source='https://'+host+'/rates'),'accepted':True})
        for key in ('base','source','source_route','source_timestamp','updated_at'):
            data=self.payload();del data[key]
            cases.append({'name':'missing '+key,'payload':data,'accepted':False})
        for source in ('http://api.frankfurter.dev/rates','https://evil.invalid/rates','https://api.frankfurter.dev.evil.invalid/rates','https://user:secret@api.frankfurter.dev/rates','https://api.frankfurter.dev:444/rates','https://api.frankfurter.dev\\@evil.invalid/rates','https://api.frankfurter.dev/\nrates'):
            cases.append({'name':source,'payload':self.payload(source=source),'accepted':False})
        for changes in ({'base':'USD'},{'source_route':'unknown'},{'source_route':'__proto__'}):
            cases.append({'name':str(changes),'payload':self.payload(**changes),'accepted':False})
        self.run_cases(cases)

    def test_both_dates_aware_calendar_and_age_limits(self):
        cases=[]
        for key in ('source_timestamp','updated_at'):
            for value,accepted in [('2026-11-12T00:00:00.000Z',True),('2026-11-11T23:59:59.999Z',False),('2026-11-15T06:00:00.000Z',True),('2026-11-15T06:00:00.001Z',False),('2026-11-15T09:00:00+09:00',True),('2026-11-15T00:00:00',False),('2026-11-15',False),('invalid',False),('2026-11-15T25:00:00Z',False),(True,False)]:
                cases.append({'name':key+':'+str(value),'payload':self.payload(**{key:value}),'accepted':accepted})
        self.run_cases(cases)

    def test_typed_rates_and_optional_euro(self):
        cases=[]
        for key in ('USD_KRW','JPY_KRW'):
            for value in (True,False,'1400',None,0,-1,{},[]):
                data=self.payload();data['rates'][key]=value
                cases.append({'name':key+':'+str(value),'payload':data,'accepted':False})
        for value in (True,'1500',None,0,-1,5001):
            data=self.payload();data['rates']['EUR_KRW']=value
            cases.append({'name':'EUR:'+str(value),'payload':data,'accepted':True,'eur':0})
        self.run_cases(cases)
