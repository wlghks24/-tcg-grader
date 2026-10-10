"use strict";
/* V505: offline-first collection. Entered estimates never become verified market evidence. */
(() => {
  const home=document.getElementById("tcgMarketHome");
  if(!home||document.getElementById("tcgLocalCollectionV505"))return;
  const KEY="tcg-local-collection-v505",LIMIT=200,FILE_LIMIT=160000;
  const GAMES=["Pokémon","ONE PIECE","NARUTO","GUNDAM CARD GAME","UNION ARENA","DRAGON BALL SUPER: FUSION WORLD","Disney Lorcana","Star Wars: Unlimited","Riftbound: League of Legends","Magic: The Gathering","Yu-Gi-Oh!","Digimon Card Game","기타 TCG"];
  const GAME_LABELS=Object.freeze({"Pokémon":"포켓몬","ONE PIECE":"원피스","NARUTO":"나루토","GUNDAM CARD GAME":"건담","UNION ARENA":"유니온 아레나","DRAGON BALL SUPER: FUSION WORLD":"드래곤볼 Fusion World","Disney Lorcana":"디즈니 로카나","Star Wars: Unlimited":"스타워즈 언리미티드","Riftbound: League of Legends":"리프트바운드","Magic: The Gathering":"매직: 더 개더링","Yu-Gi-Oh!":"유희왕","Digimon Card Game":"디지몬 카드게임","기타 TCG":"기타 카드게임 · 수동"});
  const GRADES=["미감정","PSA 8","PSA 9","PSA 10","BGS 9","BGS 9.5","BGS 10","CGC 9","CGC 10","TAG 10","BRG 9","BRG 10"];
  function node(tag,text,cls){
    const el=document.createElement(tag);
    if(text!==null&&text!==undefined)el.textContent=String(text);
    if(cls)el.className=cls;
    return el;
  }
  const won=n=>"₩"+Math.round(n).toLocaleString("ko-KR");
  function integer(value,min,max){
    // Strict import boundary: booleans, arrays, whitespace and number syntax
    // coercions must never become a real holding, purchase cost or valuation.
    if(typeof value!=="number"&&typeof value!=="string")return null;
    if(typeof value==="string"&&!/^(0|[1-9][0-9]*)$/.test(value))return null;
    const n=Number(value);
    return Number.isSafeInteger(n)&&n>=min&&n<=max?n:null;
  }
  function normalize(raw){
    if(!raw||typeof raw!=="object"||Array.isArray(raw))return null;
    if(typeof raw.name!=="string"||(raw.number!==undefined&&typeof raw.number!=="string"))return null;
    const name=raw.name.trim(),number=String(raw.number||"").trim();
    const {game,region,asset,grade}=raw;
    const qty=integer(raw.qty,1,1000),paid=integer(raw.paid,0,100000000);
    const value=raw.value===null?null:integer(raw.value,1,100000000);
    const id=integer(raw.id,1,Number.MAX_SAFE_INTEGER);
    if(!id||!name||name.length>90||number.length>36||!GAMES.includes(game)||
      !["KR","JP","US"].includes(region)||!["CARD","BOX"].includes(asset)||
      !GRADES.includes(grade)||(asset==="BOX"&&grade!=="미감정")||
      qty===null||paid===null||(raw.value!==null&&value===null))return null;
    return {id,name,number,game,region,asset,grade,qty,paid,value};
  }
  const panel=node("details",null,"tcg-local-collection-v505");panel.id="tcgLocalCollectionV505";
  const summary=node("summary","▣ 내 컬렉션 · 보유 카드/BOX","tcg-local-collection-summary");
  const badge=node("span","0장","tcg-local-collection-badge");summary.append(badge);panel.append(summary);
  panel.append(node("p","단말 브라우저에만 저장 · 직접 입력 평가액은 실거래 시세가 아닙니다. 확장 게임은 보유기록용이며 등급측정이 자동 활성화되지 않습니다.","tcg-local-collection-note"));
  const metrics=node("div",null,"tcg-local-collection-metrics");panel.append(metrics);
  const form=node("form",null,"tcg-local-collection-form");
  function select(title,choices){
    const label=node("label");label.append(node("span",title));const el=node("select");
    for(const [value,name] of choices){const opt=node("option",name);opt.value=value;el.append(opt);}
    label.append(el);form.append(label);return el;
  }
  function input(title,type,attrs){
    const label=node("label");label.append(node("span",title));const el=node("input");
    el.type=type;
    for(const [name,value] of Object.entries(attrs))el.setAttribute(name,String(value));
    label.append(el);form.append(label);return el;
  }
  const game=select("게임",GAMES.map(x=>[x,GAME_LABELS[x]||x]));
  const region=select("판본",[["KR","한국판"],["JP","일본판"],["US","영문판"]]);
  const asset=select("종류",[["CARD","카드"],["BOX","BOX"]]);
  const grade=select("상태·등급",GRADES.map(x=>[x,x]));
  const name=input("상품명/카드명","text",{required:"",maxlength:90,placeholder:"정확한 카드·BOX 이름"});
  const number=input("카드번호(선택)","text",{maxlength:36,placeholder:"OP13-001 등"});
  const qty=input("수량","number",{required:"",min:1,max:1000,step:1,value:1});
  const paid=input("개당 매입가(₩)","number",{required:"",min:0,max:100000000,step:1});
  const value=input("개당 수동 평가액(₩, 선택)","number",{min:1,max:100000000,step:1});
  const add=node("button","＋ 컬렉션 등록","tcg-local-collection-primary");
  add.type="submit";form.append(add);panel.append(form);
  const actions=node("div",null,"tcg-local-collection-actions");
  const exportButton=node("button","JSON 백업");exportButton.type="button";
  const restoreLabel=node("label","JSON 복원","tcg-local-collection-file");
  const restore=node("input");restore.type="file";restore.accept=".json,application/json";
  restore.setAttribute("aria-label","로컬 컬렉션 JSON 백업 복원");
  restoreLabel.append(restore);actions.append(exportButton,restoreLabel);panel.append(actions);
  const status=node("p","브라우저 데이터를 지우기 전에 JSON으로 백업하세요.","tcg-local-collection-note");
  status.setAttribute("role","status");status.setAttribute("aria-live","polite");panel.append(status);
  const list=node("div",null,"tcg-local-collection-list");panel.append(list);
  home.append(panel);
  const style=node("style");
  style.textContent=".tcg-local-collection-v505{border:1px solid #dce0e9;border-radius:18px;overflow:hidden;margin:16px 0;background:#fff;color:#17181e}.tcg-local-collection-summary{cursor:pointer;padding:17px 15px;display:flex;justify-content:space-between;align-items:center;gap:10px;background:#17181e;color:#fff;font-weight:850;list-style:none;font-size:15px}.tcg-local-collection-summary::-webkit-details-marker{display:none}.tcg-local-collection-badge{font-size:12px;color:#dbeafe;white-space:nowrap}.tcg-local-collection-note{margin:12px;color:#64748b;font-size:12px;line-height:1.55}.tcg-local-collection-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:10px 12px}.tcg-local-collection-metrics article{padding:10px 7px;border-radius:12px;background:#f1f5f9;min-width:0}.tcg-local-collection-metrics b{display:block;font-size:13px;overflow-wrap:anywhere}.tcg-local-collection-metrics small{display:block;margin-top:3px;color:#64748b;font-size:10px}.tcg-local-collection-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:10px 12px}.tcg-local-collection-form label{font-size:11px;font-weight:750;color:#334155;min-width:0}.tcg-local-collection-form label span{display:block;margin-bottom:5px}.tcg-local-collection-form input,.tcg-local-collection-form select{box-sizing:border-box;display:block;width:100%;min-height:45px;background:#fff;color:#111827;border-radius:9px;border:1px solid #cbd5e1;padding:8px;font-size:13px}.tcg-local-collection-primary{grid-column:1/-1;background:#ef3340!important;color:white!important;border:0!important;border-radius:11px!important;min-height:48px!important;font-weight:850!important}.tcg-local-collection-actions{display:flex;gap:9px;padding:0 12px}.tcg-local-collection-actions button,.tcg-local-collection-file{display:grid;place-items:center;min-height:44px;flex:1;border:1px solid #cbd5e1;border-radius:10px;background:#f8fafc;color:#334155;font-size:12px;font-weight:700;position:relative;cursor:pointer}.tcg-local-collection-file{overflow:hidden}.tcg-local-collection-file input{position:absolute;inset:0;opacity:0;width:100%;cursor:pointer}.tcg-local-collection-list{max-height:480px;overflow:auto;display:grid;gap:8px;padding:8px 12px 14px}.tcg-local-collection-entry{border:1px solid #e2e8f0;border-radius:12px;padding:12px;background:#f8fafc}.tcg-local-collection-entry h5{font-size:13px;margin:0 0 7px;color:#0f172a}.tcg-local-collection-entry p{font-size:11px;color:#475569;margin:4px 0}.tcg-local-collection-entry button{min-height:44px;padding:9px 14px;border:1px solid #fecaca;border-radius:9px;background:#fff;color:#9f1239;margin-top:7px}.tcg-local-collection-v505 :is(summary,input,select,button):focus-visible{outline:3px solid #2563eb;outline-offset:2px}@media(max-width:445px){.tcg-local-collection-form{grid-template-columns:1fr}.tcg-local-collection-metrics b{font-size:11px}}";
  document.head.append(style);
  // V533: screenshot-informed market-home touch/readability finish.
  // Use the existing local style node; leave immutable V485 markup/CSS untouched.
  style.textContent+=`
    #tcgMarketHome .tcg-market-refresh,
    #tcgMarketHome .tcg-market-game,
    #tcgMarketHome .tcg-market-more,
    #tcgMarketHome .tcg-market-tile-actions button,
    #tcgMarketHome .tcg-market-tile-actions a {
      min-height:48px!important;
      padding:9px 10px!important;
      font-size:13px!important;
      line-height:1.35!important;
      white-space:normal!important;
      overflow-wrap:anywhere;
    }
    #tcgMarketHome .tcg-market-home-head p,
    #tcgMarketHome .tcg-market-home-meta,
    #tcgMarketHome .tcg-market-section-heading small,
    #tcgMarketHome .tcg-market-tile-label,
    #tcgMarketHome .tcg-market-tile-kind,
    #tcgMarketHome .tcg-market-tile-date,
    #tcgMarketHome .tcg-market-home-warning,
    #tcgMarketHome .tcg-market-art-empty {
      font-size:12px!important;
      line-height:1.5!important;
      overflow-wrap:anywhere;
    }
    #tcgMarketHome .tcg-market-tile-price {
      font-size:18px!important;
      font-variant-numeric:tabular-nums;
      line-height:1.4!important;
      overflow-wrap:anywhere;
    }
    #tcgMarketHome .tcg-market-tile-actions {gap:7px;}
    #tcgMarketHome :is(button,a):focus-visible {
      outline:3px solid #2563eb!important;
      outline-offset:2px!important;
    }
  `;
  let lots=[],blocked=false;
  try{
    const raw=localStorage.getItem(KEY);
    if(raw){
      if(raw.length>FILE_LIMIT)throw Error("size");
      const data=JSON.parse(raw);
      if(data?.version!==1||!Array.isArray(data.items)||data.items.length>LIMIT)throw Error("schema");
      const valid=data.items.map(normalize);
      if(valid.some(x=>!x)||new Set(valid.map(x=>x.id)).size!==valid.length)throw Error("duplicate_or_invalid");
      lots=valid;
    }
  }catch(_){
    blocked=true;
    status.textContent="기존 보유내역을 읽을 수 없어 덮어쓰기를 차단했습니다. JSON 백업으로 확인해 주세요.";
  }
  function persist(){
    if(blocked)return false;
    try{localStorage.setItem(KEY,JSON.stringify({version:1,items:lots}));return true;}
    catch(_){blocked=true;add.disabled=true;status.textContent="저장 실패: 용량/권한을 확인하고 백업하세요.";return false;}
  }
  function render(){
    const spent=lots.reduce((a,x)=>a+x.paid*x.qty,0),priced=lots.filter(x=>x.value!==null);
    const basis=priced.reduce((a,x)=>a+x.paid*x.qty,0),mark=priced.reduce((a,x)=>a+x.value*x.qty,0);
    badge.textContent=lots.reduce((a,x)=>a+x.qty,0).toLocaleString("ko-KR")+"장";
    metrics.replaceChildren();
    for(const [heading,n] of [["매입금액",won(spent)],["수동 평가",priced.length?won(mark):"미확인"],["입력분 손익",priced.length?(mark-basis>=0?"+":"−")+won(Math.abs(mark-basis)):"미확인"]]){
      const cell=node("article");cell.append(node("b",n),node("small",heading));metrics.append(cell);
    }
    list.replaceChildren();
    if(!lots.length)list.append(node("p","아직 등록된 카드·BOX가 없습니다.","tcg-local-collection-note"));
    for(const row of lots.slice().reverse()){
      const box=node("article",null,"tcg-local-collection-entry");
      box.append(node("h5",row.name),node("p",row.game+" · "+row.region+" · "+row.asset+" · "+row.grade+(row.number?" · "+row.number:"")),node("p",row.qty+"개 · 매입 "+won(row.paid)+" /개 · "+(row.value===null?"평가액 미입력":"직접 입력 평가 "+won(row.value)+" /개")));
      const remove=node("button","기록 삭제");remove.type="button";
      remove.setAttribute("aria-label",row.name+" 보유기록 삭제");
      remove.addEventListener("click",()=>{
        if(blocked||!window.confirm("해당 보유기록을 삭제할까요? 삭제 전 백업을 권장합니다."))return;
        const before=lots;lots=lots.filter(x=>x.id!==row.id);
        if(!persist()){lots=before;return;}render();
      });
      box.append(remove);list.append(box);
    }
    if(blocked){add.disabled=true;}
  }
  asset.addEventListener("change",()=>{grade.disabled=asset.value==="BOX";if(grade.disabled)grade.value="미감정";});
  form.addEventListener("submit",event=>{
    event.preventDefault();
    if(blocked)return;
    if(lots.length>=LIMIT){status.textContent="최대 200건까지 저장할 수 있습니다. 먼저 백업하세요.";return;}
    const record=normalize({id:Math.max(Date.now(),lots.reduce((a,x)=>Math.max(a,x.id+1),1)),name:name.value,number:number.value,game:game.value,region:region.value,asset:asset.value,grade:asset.value==="BOX"?"미감정":grade.value,qty:qty.value,paid:paid.value,value:value.value===""?null:value.value});
    if(!record){status.textContent="상품명·판본·가격·수량을 확인하세요.";return;}
    lots.push(record);
    if(!persist()){lots.pop();return;}
    name.value="";number.value="";paid.value="";value.value="";qty.value="1";
    status.textContent="로컬 보유기록이 저장됐습니다. 자동 실거래 시세가 아닙니다.";
    render();
  });
  exportButton.addEventListener("click",()=>{
    let payload;
    try{payload=localStorage.getItem(KEY)||JSON.stringify({version:1,items:lots});}
    catch(_){status.textContent="백업 자료에 접근할 수 없습니다.";return;}
    const url=URL.createObjectURL(new Blob([payload],{type:"application/json"}));
    const link=node("a");link.href=url;link.download="tcg-collection-local.json";
    document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    status.textContent="JSON 다운로드를 요청했습니다. 기기에 실제 저장됐는지 확인하세요.";
  });
  restore.addEventListener("change",async()=>{
    const file=restore.files?.[0];restore.value="";
    if(!file)return;
    if(file.size>FILE_LIMIT){status.textContent="JSON 파일이 너무 큽니다.";return;}
    try{
      const parsed=JSON.parse(await file.text());
      if(parsed?.version!==1||!Array.isArray(parsed.items)||parsed.items.length>LIMIT)throw Error("schema");
      const values=parsed.items.map(normalize);
      if(values.some(x=>!x)||new Set(values.map(x=>x.id)).size!==values.length)throw Error("invalid");
      if(!window.confirm("현재 컬렉션을 JSON 파일 내용으로 교체할까요? 기존 데이터를 먼저 백업하세요."))return;
      const before=lots;
      blocked=false;lots=values;
      if(!persist()){lots=before;blocked=true;add.disabled=true;return;}
      add.disabled=false;
      status.textContent="검증된 로컬 JSON으로 복원했습니다.";render();
    }catch(_){status.textContent="JSON 내용이 올바르지 않아 복원을 차단했습니다.";}
  });
  // V516: Transfer only confirmed, visible card identity into the local entry form.
  // A predicted grade or an API price must never become a certified grade/holding.
  function measuredIdentity(){
    const cockpit=document.getElementById("gradeResultCockpit");
    if(!cockpit||cockpit.dataset.state!=="ready")return null;
    const token=document.querySelector("[data-simple-game].active")?.dataset?.simpleGame||"";
    const gameName=({pokemon:"Pokémon",onepiece:"ONE PIECE",naruto:"NARUTO"})[token];
    const read=id=>String(document.getElementById(id)?.value||"").trim();
    const title=read("identityCardName"),cardNumber=read("identityCardNumber"),edition=read("identityRegion");
    const regionCode=({KR:"KR",JP:"JP",EN:"US"})[edition];
    if(!gameName||!regionCode||!title||title==="인식 대기"||title==="-"
       ||!cardNumber||cardNumber==="-"||title.length>90||cardNumber.length>36)return null;
    return {game:gameName,region:regionCode,name:title,number:cardNumber};
  }
  const importMeasuredButton=node("button","📷 최근 측정 카드 가져오기","tcg-local-collection-import-v516");
  importMeasuredButton.type="button";
  form.insertBefore(importMeasuredButton,add);
  style.textContent+=".tcg-local-collection-import-v516{grid-column:1/-1;min-height:48px!important;border:1px solid #2563eb!important;background:#eff6ff!important;color:#1d4ed8!important;border-radius:11px!important;font-weight:850!important}#gradeCockpitAddCollectionV516{grid-column:1/-1;min-height:48px!important;background:#ecfdf5!important;color:#065f46!important;border:1px solid #6ee7b7!important}.tcg-local-collection-import-v516:focus-visible,#gradeCockpitAddCollectionV516:focus-visible{outline:3px solid #2563eb;outline-offset:2px}";
  function prefillMeasuredCard(){
    if(blocked){
      const warning="기존 컬렉션 자료를 읽지 못해 가져오기와 저장이 차단됐습니다. 백업 파일을 확인하고 검증된 JSON으로 복원하세요.";
      status.textContent=warning;
      const cockpitStatus=document.getElementById("gradeCockpitCollectionStatusV516");
      if(cockpitStatus)cockpitStatus.textContent=warning;
      return false;
    }
    const measured=measuredIdentity();
    if(!measured){
      const message="측정 완료 후 카드명·카드번호·게임·판본(KR/JP/EN)을 먼저 확인하세요. 자동 등록하지 않습니다.";
      status.textContent=message;
      const cockpitStatus=document.getElementById("gradeCockpitCollectionStatusV516");
      if(cockpitStatus)cockpitStatus.textContent=message;
      return false;
    }
    game.value=measured.game;region.value=measured.region;asset.value="CARD";
    asset.dispatchEvent(new Event("change",{bubbles:true}));
    grade.disabled=false;grade.value="미감정";
    name.value=measured.name;number.value=measured.number;qty.value="1";
    paid.value="";value.value="";
    status.textContent="인식 정보만 입력했습니다. 카드명·번호·판본을 직접 확인하고 매입가를 입력해 등록하세요. AI 예상 등급과 시세는 저장하지 않았습니다.";
    panel.open=true;
    if(typeof window.TCGFeatureCategoryNav?.closeFeatureView==="function")window.TCGFeatureCategoryNav.closeFeatureView();
    setTimeout(()=>panel.scrollIntoView?.({block:"start",behavior:"smooth"}),100);
    return true;
  }
  // V569: one collection writer. Market/photo pages may prefill, never auto-save
  // estimates, confidence, grade, purchase cost, or market evidence as holdings.
  function prefillFromMarket(input) {
    if (blocked) return {ok:false,reason:"저장소 오류 또는 손상된 기존 기록이 있어 입력을 차단했습니다. JSON 백업을 먼저 확인하세요."};
    if (!input || typeof input!=="object" || Array.isArray(input)) return {ok:false,reason:"카드 정보가 유효하지 않습니다."};
    const accepted={game:input.game,region:input.region,asset:input.asset,name:input.name,number:input.number,quantity:input.quantity};
    if(!GAMES.includes(accepted.game)||!["KR","JP","US"].includes(accepted.region)||
      !["CARD","BOX"].includes(accepted.asset)||typeof accepted.name!=="string"||
      !accepted.name.trim()||accepted.name.trim().length>90||
      typeof accepted.number!=="string"||accepted.number.trim().length>36||
      !Number.isSafeInteger(accepted.quantity)||accepted.quantity<1||accepted.quantity>1000)
      return {ok:false,reason:"게임·지역·종류·카드명·번호·수량이 보유기록 조건에 맞지 않습니다."};
    // Avoid stealing user-entered acquisition details from an in-progress form.
    if ((paid.value!==""||value.value!==""||name.value!=="") &&
        !window.confirm("작성 중인 컬렉션 입력이 있습니다. 저장되지 않은 입력을 바꾸시겠습니까?"))
      return {ok:false,reason:"작성 중이던 입력을 유지했습니다."};
    game.value=accepted.game;region.value=accepted.region;asset.value=accepted.asset;
    asset.dispatchEvent(new Event("change",{bubbles:true}));
    grade.value="미감정";
    name.value=accepted.name.trim();number.value=accepted.number.trim();
    qty.value=String(accepted.quantity);paid.value="";value.value="";
    panel.open=true;
    status.textContent="카드명·판본·수량만 가져왔습니다. 매입가를 직접 확인하고 [컬렉션 등록]을 눌러야 저장됩니다. AI 등급·시세는 가져오지 않았습니다.";
    if(typeof window.TCGFeatureCategoryNav?.closeFeatureView==="function")
      window.TCGFeatureCategoryNav.closeFeatureView();
    panel.scrollIntoView?.({block:"start"});
    paid.focus?.();
    return {ok:true,reason:"컬렉션 입력란에 정보가 준비되었습니다. 매입가 확인 후 직접 저장해 주세요."};
  }
  window.TCGLocalCollectionV505=Object.freeze({prefillFromMarket});
  importMeasuredButton.addEventListener("click",prefillMeasuredCard);
  function attachGradeCollectionButton(){
    const host=document.querySelector("#gradeResultCockpit .grade-cockpit-purchase-actions");
    if(!host)return false;
    if(document.getElementById("gradeCockpitAddCollectionV516"))return true;
    const button=node("button","＋ 내 컬렉션에 등록");
    button.id="gradeCockpitAddCollectionV516";
    button.type="button";
    button.addEventListener("click",prefillMeasuredCard);
    const message=node("span","측정 정보를 확인한 후 수동 등록합니다.");
    message.id="gradeCockpitCollectionStatusV516";
    message.setAttribute("role","status");
    message.setAttribute("aria-live","polite");
    message.style.cssText="grid-column:1/-1;font-size:12px;line-height:1.5;color:#475569";
    host.append(button,message);
    return true;
  }
  if(!attachGradeCollectionButton()&&typeof MutationObserver==="function"){
    const anchor=document.getElementById("autoGradeMarketFlow");
    if(anchor){
      const observer=new MutationObserver(()=>{if(attachGradeCollectionButton())observer.disconnect();});
      observer.observe(anchor,{subtree:true,childList:true});
      window.addEventListener("pagehide",()=>observer.disconnect(),{once:true});
    }
  }
  render();
})();