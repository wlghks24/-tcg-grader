#!/usr/bin/env python3
import json, random, subprocess, sys
from pathlib import Path
import grading_accuracy_v99 as py

ROOT=Path(__file__).resolve().parent
rng=random.Random(990228)
vectors=[]
for company in py.COMPANIES:
    for _ in range(1200):
        front=round(rng.uniform(0,50),2);back=round(rng.uniform(0,50),2)
        surface=round(rng.uniform(0,100),2);edge=round(rng.uniform(0,100),2);corner=round(rng.uniform(0,100),2)
        raw=round(rng.uniform(1,10),2);corr=round(rng.uniform(-1.5,.5),2)
        vectors.append([company,front,back,surface,edge,corner,raw,corr])
# explicit boundaries and unsupported company
for company in py.COMPANIES:
    for front,back in [(50,50),(49,48),(45,35),(40,25),(37.5,15),(35,5),(30,10),(10,5),(9,50),(0,0)]:
        vectors.append([company,front,back,0,0,0,10,-.5])
vectors.append(['INVALID',50,50,0,0,0,10,-1])
script=r'''
const fs=require('fs'),v=require('./grading_accuracy_v99.js');
const rows=JSON.parse(fs.readFileSync(0,'utf8'));
const out=rows.map(x=>({center:v.gradeByCenter(x[1],x[2],x[0]),raw:v.estimateRawGrade(x[1],x[2],x[3],x[4],x[5],x[0]),corr:v.applyDownwardCorrection(x[0],x[6],x[7])}));
process.stdout.write(JSON.stringify(out));
'''
proc=subprocess.run(['node','-e',script],cwd=ROOT,input=json.dumps(vectors),text=True,capture_output=True,timeout=60,check=True)
js=json.loads(proc.stdout)
checks=0
for x,j in zip(vectors,js):
    company,front,back,surface,edge,corner,raw,corr=x
    expected={
        'center':py.grade_by_center(front,back,company),
        'raw':py.estimate_raw_grade(front,back,surface,edge,corner,company),
        'corr':py.apply_downward_correction(company,raw,corr),
    }
    for key in expected:
        if abs(float(expected[key])-float(j[key]))>1e-9:
            raise AssertionError((key,x,expected[key],j[key]))
        checks+=1
print(json.dumps({'ok':True,'vectors':len(vectors),'comparisons':checks},ensure_ascii=False))
