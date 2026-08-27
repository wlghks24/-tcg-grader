/* TCG Grader safe self-learning v2
 * - Verified actual grades only.
 * - Separate calibration per PSA/BGS/CGC/BRG/TAG.
 * - Never claims to reproduce proprietary grading.
 * - Stores raw prediction before calibration to prevent feedback loops.
 */
(()=>{
"use strict";

const COMPANIES=["PSA","BGS","CGC","BRG","TAG"];
const V30KEY="tcg_v30_validation";
const V11KEY="tcg_pregrader_v11_validation";
const MODELKEY="tcg_self_learning_model_v2";
const STEPS={
  PSA:[1,2,3,4,5,6,7,8,9,10],
  BGS:Array.from({length:19},(_,i)=>(i+2)/2),
  CGC:Array.from({length:19},(_,i)=>(i+2)/2),
  BRG:Array.from({length:19},(_,i)=>(i+2)/2),
  TAG:Array.from({length:19},(_,i)=>(i+2)/2)
};

const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const number=x=>{const n=Number(x);return Number.isFinite(n)?n:null};
const median=a=>{const s=a.filter(Number.isFinite).sort((x,y)=>x-y);if(!s.length)return 0;const m=Math.floor(s.length/2);return s.length%2?s[m]:(s[m-1]+s[m])/2};
const nearest=(company,value)=>{
  const a=STEPS[company]||STEPS.BGS;
  return a.reduce((best,x)=>Math.abs(x-value)<Math.abs(best-value)||(Math.abs(x-value)===Math.abs(best-value)&&x<best)?x:best,a[0]);
};
const gameName=()=>{
  for(const name of ["pokemon","onepiece","naruto"]){
    if(document.getElementById(name)?.classList.contains("active"))return name;
  }
  return "unknown";
};

function readRows(){
  const result=[];
  for(const key of [V30KEY,V11KEY]){
    let rows=[];try{rows=JSON.parse(localStorage.getItem(key)||"[]")}catch(e){}
    if(!Array.isArray(rows))continue;
    for(const row of rows){
      const company=String(row.company||row.grader||"").toUpperCase();
      const actual=number(row.actual),raw=number(row.raw_pred??row.predicted_raw??row.pred);
      if(!COMPANIES.includes(company)||actual===null||raw===null||actual<1||actual>10||raw<1||raw>10)continue;
      result.push({...row,company,actual,raw_pred:raw});
    }
  }
  const map=new Map();
  for(const row of result){
    const cert=String(row.cert_no||row.cert||"").trim();
    const key=cert?`${row.company}|cert|${cert}`:
      `${row.time||""}|${row.company}|${row.actual}|${row.raw_pred}|${row.card_key||""}`;
    map.set(key,row);
  }
  return [...map.values()];
}

function localModel(){
  const rows=readRows(),companies={};
  for(const company of COMPANIES){
    const r=rows.filter(x=>x.company===company),n=r.length;
    const residuals=r.map(x=>x.actual-x.raw_pred),med=median(residuals);
    const mad=median(residuals.map(x=>Math.abs(x-med)));
    const radius=Math.max(1,3*1.4826*mad);
    const cardCounts={};
    r.forEach(x=>{const k=String(x.card_key||"");if(k)cardCounts[k]=(cardCounts[k]||0)+1});
    let weighted=0,totalWeight=0;
    residuals.forEach((residual,i)=>{
      const card=String(r[i].card_key||""),weight=card?1/Math.sqrt(cardCounts[card]||1):1;
      weighted+=clamp(residual,med-radius,med+radius)*weight;totalWeight+=weight;
    });
    const robust=totalWeight?weighted/totalWeight:0;
    const mae=n?r.reduce((s,x)=>s+Math.abs(x.actual-x.raw_pred),0)/n:0;
    const tier=n<5?["observe",0,0]:n<10?["conservative",.25,.25]:n<30?["limited",.5,.5]:n<60?["strong",.75,.75]:["mature",1,.75];
    companies[company]={
      n,state:tier[0],strength:tier[1],
      correction:tier[2]?clamp(robust*tier[1],-tier[2],tier[2]):0,
      mae,game_adjustments:{}
    };
  }
  return {ok:true,version:2,companies,source:"browser"};
}

function model(){
  try{
    const m=JSON.parse(localStorage.getItem(MODELKEY)||"null");
    if(m&&m.version===2&&m.companies)return m;
  }catch(e){}
  return localModel();
}

async function loadServerModel(){
  try{
    const r=await fetch(`/api/learning-model-status?t=${Date.now()}`,{cache:"no-store"});
    if(!r.ok)throw new Error("status");
    const data=await r.json();
    if(!data.ok||data.version!==2||!data.companies)throw new Error("schema");
    data.source="server";
    localStorage.setItem(MODELKEY,JSON.stringify(data));
    renderStatus();
    return data;
  }catch(e){
    const local=localModel();
    localStorage.setItem(MODELKEY,JSON.stringify(local));
    renderStatus();
    return local;
  }
}

function apply(company,pred,game){
  const raw=number(pred);if(raw===null)return pred;
  const m=model(),entry=m.companies?.[company]||{};
  let correction=number(entry.correction)||0;
  const g=game||gameName();
  if(g!=="unknown")correction+=number(entry.game_adjustments?.[g]?.correction)||0;
  return nearest(company,clamp(raw+correction,1,10));
}

window.tcgLastRawGrades=window.tcgLastRawGrades||{};
const previousApply=window.v30ApplyCalibration;
window.v30ApplyCalibration=function(company,pred){
  const raw=number(pred);
  if(raw!==null)window.tcgLastRawGrades[company]=raw;
  if(!COMPANIES.includes(company))return typeof previousApply==="function"?previousApply(company,pred):pred;
  return apply(company,pred,gameName());
};

window.selfLearningEstimateExtraCompanies=function(coreRaw){
  const values=COMPANIES.slice(0,3).map(c=>number(window.tcgLastRawGrades[c]??coreRaw?.[c])).filter(x=>x!==null);
  if(!values.length)return {};
  const base=median(values),out={};
  for(const company of ["BRG","TAG"]){
    window.tcgLastRawGrades[company]=base;
    out[company]=apply(company,base,gameName());
  }
  return out;
};

function ensureOptions(select,values){
  if(!select)return;
  const current=new Set([...select.options].map(x=>x.value||x.textContent));
  for(const value of values){
    if(current.has(String(value)))continue;
    const opt=document.createElement("option");opt.value=String(value);opt.textContent=String(value);select.appendChild(opt);
  }
}
function setGradeOptions(select,company){
  if(!select)return;
  const current=select.value,vals=[...(STEPS[company]||STEPS.BGS)].sort((a,b)=>b-a);
  select.innerHTML="";
  vals.forEach(v=>{const o=document.createElement("option");o.value=String(v);o.textContent=String(v);select.appendChild(o)});
  if(vals.map(String).includes(current))select.value=current;
}
function subgradeOptions(){
  return '<option value="">미입력</option>'+[10,9.5,9,8.5,8,7.5,7,6.5,6,5.5,5,4.5,4,3.5,3,2.5,2,1.5,1].map(x=>`<option value="${x}">${x}</option>`).join("");
}
function ensureLearningDetailUI(){
  if(document.getElementById("selfLearnDetails"))return;
  const save=document.getElementById("saveValidation");if(!save)return;
  const details=document.createElement("details");
  details.id="selfLearnDetails";details.className="compact-details";
  details.innerHTML=`<summary>🧠 학습자료 상세정보 입력 (선택)</summary>
  <p class="muted">같은 카드 반복자료를 구분하고 BGS 서브그레이드를 보존할 때 사용합니다. 인증번호가 있으면 중복 학습을 자동 차단합니다.</p>
  <div class="grid2"><label>카드명<input id="selfLearnCardName" placeholder="예: Umbreon VMAX"></label><label>인증번호<input id="selfLearnCert" placeholder="예: 0016892969"></label></div>
  <div class="grid2"><label>세트<input id="selfLearnSet" placeholder="예: Evolving Skies"></label><label>카드번호<input id="selfLearnCardNo" placeholder="예: 215/203"></label></div>
  <div id="selfLearnBgsBox"><div class="muted"><b>BGS 서브그레이드</b> — BGS 카드일 때만 입력</div><div class="guide-unit-grid">
  <label>Centering<select id="selfLearnCentering">${subgradeOptions()}</select></label><label>Corners<select id="selfLearnCorners">${subgradeOptions()}</select></label><label>Edges<select id="selfLearnEdges">${subgradeOptions()}</select></label><label>Surface<select id="selfLearnSurface">${subgradeOptions()}</select></label>
  </div></div>`;
  save.parentNode.insertBefore(details,save);
}
function updateCompanyControls(){
  const company=document.getElementById("actualCompany")?.value||"PSA";
  setGradeOptions(document.getElementById("actualGrade"),company);
  const quick=document.getElementById("v11grader")?.value||"PSA";
  setGradeOptions(document.getElementById("v11actual"),quick);
  const bgs=document.getElementById("selfLearnBgsBox");if(bgs)bgs.style.display=company==="BGS"?"block":"none";
}
function ensureCompanyUI(){
  ensureOptions(document.getElementById("actualCompany"),["BRG","TAG"]);
  ensureOptions(document.getElementById("v11grader"),["BRG","TAG"]);
  ensureLearningDetailUI();

  const p10=document.getElementById("p10"),table=p10?.closest("table");
  if(table&&!document.getElementById("brg10")){
    const rows=[...table.rows];
    for(const name of ["BRG","TAG"]){const th=document.createElement("th");th.textContent=name;rows[0].appendChild(th)}
    for(const [rowIndex,ids] of [[1,["brg10","tag10"]],[2,["brg9","tag9"]]]){
      for(const id of ids){const td=document.createElement("td");td.id=id;td.textContent="-";rows[rowIndex].appendChild(td)}
    }
    const note=document.createElement("p");note.className="muted";note.id="extraCompanyNote";
    note.textContent="BRG·TAG는 실제 확정등급 검증기록을 회사별로 분리해 보수 보정합니다. 표본이 부족하면 공통 결함점수의 참고 후보만 표시합니다.";
    table.insertAdjacentElement("afterend",note);
  }
  const stats=document.querySelector("#v30calibration .validation-stats");
  if(stats&&!document.getElementById("calBRG")){
    for(const company of ["BRG","TAG"]){
      const box=document.createElement("div");box.className="metric";
      box.innerHTML=`${company} 보정<b id="cal${company}">0.00</b>`;stats.appendChild(box);
    }
  }
  const calibration=document.getElementById("v30calibration");
  if(calibration&&!document.getElementById("selfLearningStatus")){
    const status=document.createElement("div");status.id="selfLearningStatus";status.className="status";status.style.marginTop="8px";calibration.appendChild(status);
  }
  updateCompanyControls();
}

function metadata(company){
  const value=id=>String(document.getElementById(id)?.value||"").trim();
  const card_name=value("selfLearnCardName"),set_name=value("selfLearnSet"),card_no=value("selfLearnCardNo"),cert_no=value("selfLearnCert");
  const card_key=[gameName(),set_name,card_name,card_no].filter(Boolean).join("|");
  const out={game:gameName()};
  if(card_name)out.card_name=card_name;if(set_name)out.set_name=set_name;if(card_no)out.card_no=card_no;if(cert_no)out.cert_no=cert_no;if(card_key)out.card_key=card_key;
  if(company==="BGS"){
    const subgrades={};
    for(const [key,id] of [["centering","selfLearnCentering"],["corners","selfLearnCorners"],["edges","selfLearnEdges"],["surface","selfLearnSurface"]]){
      const n=number(document.getElementById(id)?.value);if(n!==null)subgrades[key]=n;
    }
    if(Object.keys(subgrades).length)out.subgrades=subgrades;
  }
  return out;
}
function decorateRow(row,company){
  const raw=number(window.tcgLastRawGrades?.[company]);
  if(raw!==null)row.raw_pred=raw;
  Object.assign(row,metadata(company),{verified:true});
  return row;
}
async function postConfirmedSample(row){
  if(!row||number(row.raw_pred??row.pred)===null)return {ok:false};
  const payload={...row,company:String(row.company||row.grader||"").toUpperCase(),actual_grade:row.actual,raw_pred:row.raw_pred??row.pred,verified:true,source:"app_confirmed"};
  try{
    const r=await fetch("/api/learning-sample",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    if(!r.ok)throw new Error("learning-sample");
    return await r.json();
  }catch(e){return {ok:false,offline:true}}
}

function formatGrade(x){return number(x)===null?"-":Number(x).toFixed(Number.isInteger(Number(x))?0:1)}
function renderExtraGrades(){
  const grades=window.tcgLastGrades||{};
  for(const company of ["BRG","TAG"]){
    const prefix=company.toLowerCase(),g=number(grades[company]);
    const hi=document.getElementById(prefix+"10"),lo=document.getElementById(prefix+"9");
    if(hi)hi.textContent=formatGrade(g);
    if(lo)lo.textContent=g===null?"-":formatGrade(Math.min(g,9));
  }
}
function waitForCoreGrades(attempt=0){
  const grades=window.tcgLastGrades||{};
  if(["PSA","BGS","CGC"].every(c=>number(grades[c])!==null)){
    Object.assign(grades,window.selfLearningEstimateExtraCompanies(window.tcgLastRawGrades));renderExtraGrades();return;
  }
  if(attempt<30)setTimeout(()=>waitForCoreGrades(attempt+1),100);
}

function renderStatus(){
  ensureCompanyUI();
  const m=model(),stateKo={observe:"관찰",conservative:"보수",limited:"제한 적용",strong:"강화 적용",mature:"성숙"};
  for(const company of COMPANIES){
    const e=m.companies?.[company]||{},el=document.getElementById("cal"+company);
    if(el)el.textContent=(number(e.correction)||0).toFixed(2);
  }
  const box=document.getElementById("selfLearningStatus");if(!box)return;
  const lines=COMPANIES.map(company=>{
    const e=m.companies?.[company]||{};
    return `<b>${company}</b> ${e.n||0}건 · ${stateKo[e.state]||"관찰"} · 보정 ${(number(e.correction)||0).toFixed(2)} · MAE ${(number(e.mae)||0).toFixed(2)}`;
  });
  box.innerHTML=`🧠 <b>자가학습 v2</b> · ${m.source==="server"?"PC·태블릿 중앙 저장":"브라우저 로컬 저장"}<br>${lines.join("<br>")}<br><span class="muted">확정등급만 학습 · 5건 미만 미적용 · 업체별 모델 분리 · 인증번호 중복제거 · 동일카드 반복표본 영향 완화</span>`;
}

async function refreshAfterSave(row){
  localStorage.setItem(MODELKEY,JSON.stringify(localModel()));renderStatus();
  await postConfirmedSample(row);
  if(typeof window.syncLearningToServer==="function")await window.syncLearningToServer().catch(()=>{});
  await loadServerModel();
}
function annotateLatestValidation(){
  let rows=[];try{rows=JSON.parse(localStorage.getItem(V30KEY)||"[]")}catch(e){return}
  if(!rows.length)return;
  const row=rows[rows.length-1],company=String(row.company||"").toUpperCase();
  decorateRow(row,company);localStorage.setItem(V30KEY,JSON.stringify(rows.slice(-500)));
  refreshAfterSave(row);
}
function saveExtraCompanyValidation(event){
  const company=String(document.getElementById("actualCompany")?.value||"").toUpperCase();
  if(!["BRG","TAG"].includes(company))return;
  event.preventDefault();event.stopImmediatePropagation();
  const actual=number(document.getElementById("actualGrade")?.value),grades=window.tcgLastGrades||{},pred=number(grades[company]);
  if(actual===null||pred===null){alert("먼저 앞면과 뒷면 사진으로 자동 분석을 완료하세요.");return}
  let rows=[];try{rows=JSON.parse(localStorage.getItem(V30KEY)||"[]")}catch(e){}
  const row=decorateRow({time:new Date().toISOString(),company,actual,pred,mode:window.v30Mode||"raw"},company);
  rows.push(row);localStorage.setItem(V30KEY,JSON.stringify(rows.slice(-500)));
  if(typeof window.v30RenderValidation==="function")window.v30RenderValidation();
  refreshAfterSave(row);
}
function annotateLatestQuickValidation(){
  try{
    const rows=JSON.parse(localStorage.getItem(V11KEY)||"[]");
    if(!rows.length)return;
    const row=rows[rows.length-1],company=String(row.grader||row.company||"").toUpperCase();
    decorateRow(row,company);localStorage.setItem(V11KEY,JSON.stringify(rows.slice(-200)));
    refreshAfterSave(row);
  }catch(e){}
}

function hook(){
  ensureCompanyUI();renderStatus();loadServerModel();
  document.getElementById("actualCompany")?.addEventListener("change",updateCompanyControls);
  document.getElementById("v11grader")?.addEventListener("change",updateCompanyControls);
  document.getElementById("analyze")?.addEventListener("click",()=>{window.tcgLastRawGrades={};setTimeout(()=>waitForCoreGrades(),0)});
  const save=document.getElementById("saveValidation");
  save?.addEventListener("click",saveExtraCompanyValidation,true);
  save?.addEventListener("click",()=>setTimeout(()=>{
    const company=String(document.getElementById("actualCompany")?.value||"").toUpperCase();
    if(!["BRG","TAG"].includes(company))annotateLatestValidation();
  },80));
  document.getElementById("v11save")?.addEventListener("click",()=>setTimeout(annotateLatestQuickValidation,80));
  document.getElementById("recalcCalibration")?.addEventListener("click",()=>setTimeout(()=>{localStorage.setItem(MODELKEY,JSON.stringify(localModel()));renderStatus();loadServerModel();},80));
}

if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",hook);else hook();
})();
