'use strict';
const assert=require('assert');
const v=require('./grading_accuracy_v99.js');
assert.strictEqual(v.VERSION,'v99-accuracy-selflearning-hardened');
assert.strictEqual(v.quantizeDown('PSA',9.9),9);
assert.strictEqual(v.quantizeDown('TAG',9.9),9);
assert.strictEqual(v.quantizeDown('BGS',9.7),9.5);
assert.strictEqual(v.quantizeDown('INVALID',9.9),1);
assert.strictEqual(v.validActualGrade('BGS',9.5),true);
assert.strictEqual(v.validActualGrade('BGS',9.3),false);
assert.strictEqual(v.validActualGrade('TAG',9.5),false);
let prev=Infinity;
for(let r=0;r<=100;r+=2){const g=v.estimateRawGrade(50,50,r,r,r,'BGS');assert(g<=prev);prev=g}
prev=Infinity;
for(let c=50;c>=5;c-=1){const g=v.estimateRawGrade(c,c,0,0,0,'PSA');assert(g<=prev);prev=g}
assert(v.estimateRawGrade(50,50,2,70,2,'BGS')<v.estimateRawGrade(50,50,2,2,2,'BGS'));
assert(v.estimateRawGrade(50,50,2,2,70,'BGS')<v.estimateRawGrade(50,50,2,2,2,'BGS'));
assert.strictEqual(v.applyDownwardCorrection('PSA',10,-.25),10);
assert.strictEqual(v.applyDownwardCorrection('PSA',10,-.5),9);
assert.strictEqual(v.applyDownwardCorrection('INVALID',10,-1),1);
assert.strictEqual(v.gradeByCenter(35,15,'BGS'),7);
assert.strictEqual(v.gradeByCenter(30,10,'BGS'),6);
assert.strictEqual(v.gradeByCenter(40,40,'CGC'),9);
assert.strictEqual(v.gradeByCenter(45,35,'TAG'),10);
assert.strictEqual(v.gradeByCenter(40,25,'TAG'),9);
assert.strictEqual(v.gradeByCenter(37.5,15,'TAG'),8.5);
assert.strictEqual(v.quantizeDown('BGS',v.gradeByCenter(9,50,'BGS')),1.5);
console.log('PASS: V99 company scale + TAG public gates + valid grade axes + defect monotonic + centering monotonic + edge/corner grade caps + emitted-grade downward correction');
