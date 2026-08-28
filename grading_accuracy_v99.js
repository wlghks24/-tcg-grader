/* TCG Grader V99 grading core: conservative, monotonic, company-aware. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  root.TCGAccuracyV99=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const VERSION='v99-accuracy-selflearning-hardened';
  const COMPANIES=['PSA','BGS','CGC','TAG','BRG'];
  const HALF=Array.from({length:19},(_,i)=>(i+2)/2);
  const STEPS={
    PSA:[1,2,3,4,5,6,7,8,9,10],
    BGS:HALF,
    CGC:HALF,
    BRG:HALF,
    TAG:HALF.filter(x=>x!==9.5),
  };
  const OFFICIAL={
    PSA:{10:{f:45,b:25}},
    BGS:{10:{f:50,b:40},9.5:{f:45,b:40},9:{f:45,b:30},8:{f:40,b:20},7:{f:35,b:15},6:{f:30,b:10},5:{f:25,b:10},4:{f:20,b:5},3:{f:15,b:5},2:{f:10,b:5}},
    // CGC does not publish a complete numeric centering table for every grade.
    // Do not invent 9.5/9 thresholds; lower grades use the monotonic fallback.
    CGC:{10:{f:45,b:25}},
    // Numeric TAG 10 includes Gem Mint 10. Pristine 10 is stricter but shares grade 10.
    TAG:{10:{f:45,b:35},9:{f:40,b:25},8.5:{f:37.5,b:15},8:{f:35,b:5}},
    BRG:{},
  };
  const finite=x=>Number.isFinite(Number(x));
  const clamp=(x,a,b)=>Math.max(a,Math.min(b,Number(x)));
  function validSteps(company){return STEPS[String(company||'').toUpperCase()]||[]}
  function validActualGrade(company,value){
    if(!finite(value))return false;
    const steps=validSteps(company),n=Number(value);return steps.some(step=>Math.abs(step-n)<1e-9);
  }
  function quantizeDown(company,value){
    const steps=validSteps(company);if(!finite(value)||!steps.length)return 1;
    const v=clamp(value,1,10);
    let out=steps[0];
    for(const step of steps){if(step<=v+1e-9)out=step;else break}
    return out;
  }
  function riskToGrade(risk){
    const r=Number(risk);if(!Number.isFinite(r)||r<0)return 1;
    if(r<5)return 10;if(r<10)return 9.5;if(r<16)return 9;if(r<23)return 8.5;
    if(r<31)return 8;if(r<40)return 7.5;if(r<50)return 7;if(r<60)return 6;
    if(r<70)return 5;if(r<80)return 4;if(r<88)return 3;if(r<94)return 2;return 1;
  }
  function combineDefectRisk(surface,edge,corner){
    const values=[surface,Number(edge)*0.90,Number(corner)*0.95].filter(finite).map(Number);
    return values.length?clamp(Math.max(...values),0,100):100;
  }
  function generalCenterGrade(front,back){
    if(!finite(front)||!finite(back))return 1;
    const w=Math.min(50,Number(front),Number(back));
    return w>=45?10:w>=40?9:w>=35?8:w>=30?7:w>=25?6:w>=20?5:w>=15?4:w>=10?3:w>=5?2:1;
  }
  function gradeByCenter(front,back,company){
    company=String(company||'').toUpperCase();
    if(!COMPANIES.includes(company)||!finite(front)||!finite(back))return 1;
    front=Number(front);back=Number(back);if(front<0||back<0||front>50||back>50)return 1;
    const t=OFFICIAL[company]||{};
    for(const grade of Object.keys(t).map(Number).sort((a,b)=>b-a)){
      if(front>=t[grade].f&&back>=t[grade].b)return grade;
    }
    const keys=Object.keys(t).map(Number);
    return Math.min(generalCenterGrade(front,back),keys.length?Math.min(...keys)-0.5:10);
  }
  function estimateRawGrade(front,back,surface,edge,corner,company){
    company=String(company||'').toUpperCase();
    const defect=riskToGrade(combineDefectRisk(surface,edge,corner));
    const center=gradeByCenter(front,back,company);
    return quantizeDown(company,Math.min(defect,center));
  }
  function applyDownwardCorrection(company,raw,correction){
    const steps=validSteps(company);if(!steps.length||!finite(raw))return 1;
    const corr=Math.min(0,Math.max(-1,Number(correction)||0));
    if(Math.abs(corr)<0.5)return quantizeDown(company,Number(raw));
    const value=clamp(Number(raw)+corr,1,10);
    return steps.reduce((best,step)=>{const d=Math.abs(step-value),bd=Math.abs(best-value);return d<bd-1e-12||(Math.abs(d-bd)<=1e-12&&step<best)?step:best},steps[0]);
  }
  return Object.freeze({VERSION,COMPANIES,STEPS,OFFICIAL,validSteps,validActualGrade,quantizeDown,riskToGrade,combineDefectRisk,generalCenterGrade,gradeByCenter,estimateRawGrade,applyDownwardCorrection});
});
