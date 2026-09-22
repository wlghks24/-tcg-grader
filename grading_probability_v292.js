(function(root,factory){
'use strict';
const api=factory();
if(typeof module!=='undefined'&&module.exports)module.exports=api;
if(root)root.TCGGradeProbabilityV292=api;
})(typeof window!=='undefined'?window:(typeof globalThis!=='undefined'?globalThis:null),function(){
'use strict';
const VERSION='v292-grade-aware-heuristic';
const MODEL='heuristic_uncertainty_not_empirically_calibrated';

function finite(value){
 if(value===null||value===undefined||typeof value==='boolean'||(typeof value==='string'&&!value.trim()))return null;
 const number=Number(value);
 return Number.isFinite(number)?number:null;
}
function clamp(value,min,max){return Math.max(min,Math.min(max,value))}
function logistic(value){
 if(value>=40)return 1;
 if(value<=-40)return 0;
 return 1/(1+Math.exp(-value));
}
function round6(value){return Math.round(value*1e6)/1e6}
function insufficient(reason){
 return Object.freeze({
  version:VERSION,status:'insufficient_evidence',model:MODEL,calibrated:false,
  exact:Object.freeze({8:0,9:0,10:0}),p9plus:0,below8:100,
  analysisConfidence:null,reason:String(reason||'required evidence missing')
 });
}
function estimate(input={}){
 const grade=finite(input.psaGrade),confidence=finite(input.analysisConfidence);
 const front=finite(input.front),back=finite(input.back);
 const surface=finite(input.surfaceRisk),edge=finite(input.edgeRisk),corner=finite(input.cornerRisk);
 if(grade===null||grade<1||grade>10)return insufficient('PSA raw/calibrated grade missing or invalid');
 if(confidence===null||confidence<0||confidence>100)return insufficient('analysis confidence missing or invalid');
 if(front===null||back===null||front<0||front>50||back<0||back>50)return insufficient('centering evidence missing or invalid');
 for(const [name,value] of [['surface',surface],['edge',edge],['corner',corner]]){
  if(value===null||value<0||value>100)return insufficient(`${name} evidence missing or invalid`);
 }

 // This is intentionally an uncertainty display, not a learned population model.
 // The authoritative V99 grade already incorporates centering and defect evidence.
 // Confidence only widens/lowers the distribution; it can never promote the grade.
 const uncertainty=(100-confidence)/100;
 const effectiveGrade=clamp(grade-uncertainty*0.75,1,10);
 const sigma=0.45+uncertainty*0.55;
 const ge10=100*logistic((effectiveGrade-9.5)/sigma);
 const ge9=100*logistic((effectiveGrade-8.5)/sigma);
 const ge8=100*logistic((effectiveGrade-7.5)/sigma);
 let p10=Math.max(0,ge10);
 let p9=Math.max(0,ge9-ge10);
 let p8=Math.max(0,ge8-ge9);
 let below=Math.max(0,100-ge8);
 const total=p8+p9+p10+below;
 if(!Number.isFinite(total)||total<=0)return insufficient('probability normalization failed');
 const scale=100/total;
 p8=round6(p8*scale);p9=round6(p9*scale);p10=round6(p10*scale);
 below=round6(Math.max(0,100-p8-p9-p10));
 return Object.freeze({
  version:VERSION,status:'estimated',model:MODEL,calibrated:false,
  exact:Object.freeze({8:p8,9:p9,10:p10}),p9plus:round6(p9+p10),below8:below,
  analysisConfidence:confidence,effectiveGrade:round6(effectiveGrade),sigma:round6(sigma),
  evidence:Object.freeze({front,back,surfaceRisk:surface,edgeRisk:edge,cornerRisk:corner}),
  note:'PSA 8/9/10 값은 사진 기반 예상등급과 분석 신뢰도로 만든 휴리스틱 불확실성 분포이며 실제 PSA 모집단 확률 또는 공식 통계가 아닙니다.'
 });
}
return Object.freeze({VERSION,MODEL,estimate});
});
