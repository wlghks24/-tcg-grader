/* V567: unified photo-result report; reads existing validated capture / identity DOM only. */
(function(root){
"use strict";
if(!root||!root.document)return;
const d=root.document;
const q=id=>d.getElementById(id);
const regionName={KR:"한국어판",JP:"일본어판",EN:"영어판",UNKNOWN:"판본 미확인"};
const core={pokemon:"포켓몬",onepiece:"원피스",naruto:"나루토"};
let rootPanel=null,lookupReady=false,known=[];
let manualSetName="",manualPrinting="",manualCondition="",manualLanguage="",lastCardIdentity="",priceKey="",priceEvidence=null,priceLoading=false,priceFailed=false;
function clean(value,max=140){return String(value==null?"":value).normalize("NFKC").trim().slice(0,max);}
function node(tag,cls,txt){const e=d.createElement(tag);if(cls)e.className="tcg-photo-"+cls;if(txt!==undefined)e.textContent=String(txt);return e;}
function btn(label,run,cls="action"){const e=node("button",cls,label);e.type="button";e.addEventListener("click",run);return e;}
function activeGame(){const selected=d.querySelector("#simpleGradeV32 .simple-game.active[data-simple-game]")||d.querySelector(".simple-game.active[data-simple-game]");return clean(selected?.dataset.simpleGame,40)||"unknown";}
function gradeSnapshot(){
 const visible=q("simpleGradeResult")?.style.display!=="none";
 const n=Number(q("simpleGradeNumber")?.textContent);
 const game=activeGame();
 return {game,gameLabel:core[game]||"선택 게임 확인 필요",isVisible:visible&&Number.isInteger(n)&&n>=1&&n<=10,
  grade:visible&&Number.isInteger(n)&&n>=1&&n<=10?n:null,
  confidence:clean(q("simpleGradeConfidence")?.textContent,130),
  cardName:clean(q("identityCardName")?.value),cardNumber:clean(q("identityCardNumber")?.value,40),
  setName:manualSetName,printing:manualPrinting,condition:manualCondition,language:manualLanguage,
  region:clean(q("identityRegion")?.value,12),
  generation:game==="pokemon"&&!q("simplePokemonGeneration")?.hidden?clean(q("pokemonGenerationTitle")?.textContent,100):"",
  generationMeta:game==="pokemon"&&!q("simplePokemonGeneration")?.hidden?clean(q("pokemonGenerationMeta")?.textContent,180):"",
  scores:Object.fromEntries(["Center","Corner","Edge","Surface"].map(k=>[k,parseInt(q("score"+k)?.textContent||"",10)]))
 };
}
function safeImage() {
 const p=q("autoFrontPreview"),f=q("fp");
 const source=p?.getAttribute("src")||f?.getAttribute("src")||"";
 if(!(source.startsWith("blob:")||/^data:image\/(?:png|jpeg|webp);base64,/i.test(source)))return "";
 return source;
}
function metricGrid(s){
 const grid=node("div","metrics");
 const titles={Center:"센터링",Corner:"코너",Edge:"엣지",Surface:"표면"};
 for(const k of Object.keys(titles)){const n=s.scores[k];const card=node("div","metric");
   card.append(node("span","muted",titles[k]),node("strong","metric-score",Number.isFinite(n)&&n>=0&&n<=100?n+" / 100":"측정값 없음"));
   grid.append(card);}
 return grid;
}
function section(title,summary){const e=node("section","section");e.append(node("h3","section-title",title));if(summary)e.append(node("p","hint",summary));return e;}
function notify(text){if(rootPanel){let alert=rootPanel.querySelector("[data-tcg-photo-status]");if(alert)alert.textContent=text;}}
async function loadGames(){
 if(lookupReady)return known;
 lookupReady=true;
 try{
 const r=await root.fetch("tcg_game_registry.json",{cache:"no-store"});
 if(!r.ok)throw Error("registry");
 const payload=await r.json();
 if(!payload||payload.schema_version!==1||!Array.isArray(payload.games))throw Error("schema");
 known=payload.games.filter(g=>g&&["core","promoted"].includes(g.state)&&g.capabilities?.market===true)
   .map(g=>({id:clean(g.id,64),canonical:clean(g.canonical,100),label:clean(g.label_ko||g.canonical,80),
     grading:g.state==="core"&&g.capabilities?.grading===true,state:g.state}));
 }catch(_){known=[];}
 return known;
}
function strictMarketIdentity(s,row){
 if(!s||!row||!s.cardName||!s.cardNumber||!["KR","JP"].includes(s.region))return false;
 if(row.region!==s.region||row.asset!=="HIT")return false;
 if(!row.game||row.game.id!==s.game)return false;
 if(!row.cardName||!row.cardNumber)return false;
 const n=x=>clean(x).replace(/\s+/g," ").toLocaleLowerCase("en");
 return n(row.cardName)===n(s.cardName)&&n(row.cardNumber)===n(s.cardNumber);
}
async function showMarket(s){
 const api=root.TCGCardDetail;
 if(!api||typeof api.openFromPhoto!=="function"){notify("시장 상세 모듈이 준비되지 않았습니다. 시세 탭에서 검색해 주세요.");return;}
 if(!s.cardName||!s.cardNumber){notify("카드명과 카드번호가 모두 확인돼야 정확한 거래가와 연결할 수 있습니다. 먼저 OCR 결과를 확인해 주세요.");return;}
 if(!["KR","JP"].includes(s.region)){notify("영어판은 북미판과 동일하지 않습니다. 실제 판매 지역을 확인한 뒤 시세를 연결하세요.");return;}
 try{const result=await api.openFromPhoto({game:s.game,region:s.region,cardName:s.cardName,cardNumber:s.cardNumber,setName:s.setName,printing:s.printing,condition:s.condition,language:s.language});if(!result)notify("동일 카드·번호·판본의 확인된 거래가가 없습니다. 상세 목록에서 다른 후보를 수동 확인할 수 있습니다.");}
 catch(_){notify("시세 상세 페이지를 열지 못했습니다. 인터넷과 저장자료를 확인해 주세요.");}
}
function priceIdentityKey(s){
 return [s.game,s.region,s.cardName,s.cardNumber,s.setName,s.printing,s.condition,s.language].map(x=>clean(x,120)).join("|");
}
function updatePriceEvidence(s){
 const identityReady=!!(s.cardName && s.cardNumber && ["KR","JP"].includes(s.region));
 if(!identityReady){priceKey="";priceEvidence=null;priceLoading=false;priceFailed=false;return;}
 const key=priceIdentityKey(s);
 if(priceKey===key)return;
 priceKey=key;priceEvidence=null;priceFailed=false;priceLoading=true;
 const api=root.TCGCardDetail;
 if(!api||typeof api.getPhotoMarketEvidence!=="function"){
   priceLoading=false;priceFailed=true;return;
 }
 void api.getPhotoMarketEvidence({game:s.game,region:s.region,cardName:s.cardName,
   cardNumber:s.cardNumber,setName:s.setName,printing:s.printing,condition:s.condition,language:s.language}).then(info=>{
   if(key!==priceKey)return;
   priceEvidence=info;priceLoading=false;priceFailed=false;render();
 }).catch(()=>{
   if(key!==priceKey)return;
   priceEvidence=null;priceLoading=false;priceFailed=true;render();
 });
}
function priceRow(box,label,content){
 const el=node("div","price-row");
 el.append(node("strong","price-row-label",label),node("span","price-row-value",content));
 box.append(el);
}
function gradeEvidence(label){
 if(!priceEvidence?.variantConfirmed||!Array.isArray(priceEvidence.sales))return [];
 return priceEvidence.sales.filter(x=>x.grade===label);
}
function render(){
 if(!rootPanel)return;
 const s=gradeSnapshot();
 if(!s.isVisible){rootPanel.hidden=true;priceKey="";priceEvidence=null;return;}
 const cardIdentity=[s.game,s.region,s.cardName,s.cardNumber].join("|");
 if(cardIdentity!==lastCardIdentity){lastCardIdentity=cardIdentity;manualSetName="";manualPrinting="";manualCondition="";manualLanguage="";s.setName="";s.printing="";s.condition="";s.language="";}
 updatePriceEvidence(s);
 rootPanel.hidden=false;
 rootPanel.replaceChildren();
 const hero=section("촬영 카드 분석 결과","앞면·뒷면 사진 기반 참고정보입니다. 실물감정 등급이나 현재 체결가를 보장하지 않습니다.");
 const deck=node("div","hero");
 const art=node("div","art");
 const url=safeImage();
 if(url){const img=node("img","preview");img.alt="촬영한 카드 앞면";img.loading="lazy";img.src=url;art.append(img);}
 else art.append(node("p","muted","앞면 사진 확인 필요"));
 const main=node("div","primary");
 main.append(node("p","eyebrow",s.gameLabel+" · "+(regionName[s.region]||"판본 확인 필요")));
 main.append(node("h2","name",s.cardName||"카드명 확인 필요"));
 main.append(node("p","hint",s.cardNumber?"카드번호 "+s.cardNumber:"카드번호 미확인 · 정확한 시세 연결 보류"));
 const g=node("div","generation");g.append(node("span","muted",s.game==="pokemon"?"세대 / 시리즈":"시리즈 / 발매 탄"));
 g.append(node("strong","",s.generation&&!/판별 중|확인|대기|미확인/i.test(s.generation)?s.generation:"세대·시리즈 근거 부족"));main.append(g);
 if(s.generationMeta)main.append(node("p","hint",s.generationMeta));
 const edition=node("label","set-confirm");
 edition.append(node("span","muted","세트명 · 판매 근거 확인 시 필요 (선택 입력)"));
 const setInput=node("input","set-entry");
 setInput.type="text";setInput.maxLength=100;setInput.placeholder="카드의 정확한 세트명 확인 후 입력";
 setInput.value=manualSetName;setInput.setAttribute("aria-label","검증된 세트 이름");
 setInput.addEventListener("change",()=>{const value=clean(setInput.value,100);if(value!==manualSetName){manualSetName=value;render();}});
 edition.append(setInput);main.append(edition);
 const advanced=node("details","variant-details");
 const summary=node("summary","variant-summary","판본 세부정보 입력 (인쇄판·상태·언어)");advanced.append(summary);
 const variantFields=[
  ["printing","인쇄 변형","초판·패러렐·프로모 표시",manualPrinting],
  ["condition","카드 상태","RAW·미개봉 등 실제 상태",manualCondition],
  ["language","언어 표기","Korean / Japanese 등 판매 근거 표기",manualLanguage]
 ];
 variantFields.forEach(([field,title,placeholder,value])=>{
   const wrapper=node("label","set-confirm");
   wrapper.append(node("span","muted",title));
   const input=node("input","set-entry");input.type="text";input.maxLength=80;
   input.placeholder=placeholder;input.value=value;input.setAttribute("aria-label",title);
   input.addEventListener("change",()=>{
     const next=clean(input.value,80);
     if(field==="printing" && manualPrinting!==next)manualPrinting=next;
     else if(field==="condition" && manualCondition!==next)manualCondition=next;
     else if(field==="language" && manualLanguage!==next)manualLanguage=next;
     else return;
     render();
   });
   wrapper.append(input);advanced.append(wrapper);
 });
 main.append(advanced);
 const score=node("div","score");score.append(node("span","muted","사진 기반 사전등급"),node("strong","rating",String(s.grade)+" / 10"));
 main.append(score,node("p","hint",s.confidence||"측정 신뢰도 정보 없음"));
 main.append(node("p","warn","PSA/BGS/CGC/TAG/BRG 공식 등급이 아닙니다. 등급 8·9·10 확률은 검증된 확률 모델 결과가 없으면 표시하지 않습니다."));
 deck.append(art,main);hero.append(deck);rootPanel.append(hero);
 const metrics=section("정밀 상태 분석","기존 촬영 엔진의 센터링·코너·엣지·표면 값을 그대로 표시합니다.");
 metrics.append(metricGrid(s));rootPanel.append(metrics);
 const grades=section("등급별 참고 시세","RAW · PSA 8 · PSA 9 · PSA 10. 완료된 실거래가 확인되지 않은 등급은 ‘자료 없음’으로 표시합니다.");
 const gradeCards=node("div","gradecards");["RAW","PSA 8","PSA 9","PSA 10"].forEach(label=>{
 const a=node("div","gradecard");a.append(node("strong","grade-label",label));
 const matches=gradeEvidence(label);
 if(!matches.length)a.append(node("p","unavailable",priceLoading?"근거 조회 중…":"검증된 동일판본 실거래 없음"));
 else {
   const latest=matches[matches.length-1];
   a.append(node("strong","grade-price","₩"+latest.price.toLocaleString("ko-KR")));
   a.append(node("p","hint",latest.date+" · 검증 거래 "+matches.length+"건 · 참고용"));
 }
 gradeCards.append(a);
 });grades.append(gradeCards);rootPanel.append(grades);
 const observation=section("동일 카드 후보의 저장 가격","참고·판매호가와 체결 실거래는 다릅니다. 자료일과 정확한 판본을 확인하세요.");
 if(priceLoading)observation.append(node("p","hint","등록된 거래 근거를 대조 중입니다…"));
 else if(priceFailed)observation.append(node("p","notice","시세 파일을 가져오지 못했습니다. 네트워크와 로컬 서버를 확인하세요."));
 else if(priceEvidence?.status==="single_candidate"){
   const reference=priceEvidence.reference;
   if(reference){
     priceRow(observation,"공개 참고자료",reference.display);
     priceRow(observation,"가격 유형",reference.kind);
     priceRow(observation,"자료일",reference.date);
     const age=Date.now()-Date.parse(reference.date+"T00:00:00Z");
     if(!Number.isFinite(age)||age>14*86400000)observation.append(node("p","warn","14일 이상 경과한 과거 가격입니다. 현재 시세로 사용하지 마세요."));
     const href=root.TCGCardDetail?.safeSourceUrl?.(reference.source)||"";
     if(href){const a=node("a","evidence-link","원문 가격 근거 ↗");a.href=href;a.target="_blank";a.rel="noopener noreferrer";observation.append(a);}
   }else observation.append(node("p","notice","동일 카드 후보는 있으나 자료일·가격출처가 검증되지 않았습니다."));
   if(!priceEvidence.variantConfirmed)observation.append(node("p","warn","세트·언어·인쇄판·상태의 완전 일치가 검증되지 않아 PSA 실거래가는 표시하지 않습니다."));
 }else if(priceEvidence?.status==="ambiguous")observation.append(node("p","notice","동일 이름·카드번호의 후보가 복수입니다. 자동 가격 연결을 중단했습니다."));
 else observation.append(node("p","notice","이 카드와 국가·번호가 일치하는 검증된 저장 시세가 없습니다."));
 rootPanel.append(observation);
 const market=section("가격 비교·최근 거래 내역","정확한 게임·카드명·카드번호·판매 지역이 모두 일치하는 경우에만 실거래를 연결합니다.");
 const act=node("div","actions");
 act.append(btn("카드 시세 상세 보기 ›",()=>void showMarket(gradeSnapshot())));
 act.append(btn("OCR 카드명·번호 확인",()=>{q("identityCardName")?.focus();q("identityStatus")?.scrollIntoView({block:"center",behavior:"smooth"});},"secondary"));
 market.append(act);
 market.append(node("p","notice","미확인 가격을 다른 카드·다른 언어판에서 가져와 채우지 않습니다."));
 const feedback=node("p","status","");feedback.dataset.tcgPhotoStatus="";feedback.setAttribute("role","status");market.append(feedback);
 rootPanel.append(market);
 const foot=node("p","foot","세대는 게임마다 의미가 다릅니다. 포켓몬은 세대, 다른 게임은 시리즈/탄/세트로 표기합니다. 카드 식별 미확정 시 시세와 투자수익률을 추정하지 않습니다.");rootPanel.append(foot);
}
function mountExtendedGames(){
 const host=q("simpleGradeV32");if(!host||host.querySelector(".tcg-photo-expanded"))return;
 const available=known.filter(g=>!g.grading);
 if(!available.length)return;
 const box=node("section","expanded");box.append(node("h3","section-title","확장 TCG 카드 사진·시세 조회"));
 box.append(node("p","hint","등록된 확장 게임은 사진을 저장하거나 시세자료를 조회할 수 있습니다. 카드 OCR·세대 판정·정밀 등급은 해당 게임의 검증 전까지 제공하지 않습니다."));
 const form=node("form","extended-form");
 const choose=node("select","entry");
 choose.setAttribute("aria-label","확장 카드게임 선택");
 available.forEach(game=>{const option=node("option","",game.label+" · "+game.state);option.value=game.id;choose.append(option);});
 const file=node("input","entry");
 file.type="file";file.accept="image/jpeg,image/png,image/webp";file.setAttribute("capture","environment");file.setAttribute("aria-label","카드 앞면 사진 촬영·선택");
 const name=node("input","entry");name.type="text";name.maxLength=120;name.placeholder="카드명";name.setAttribute("aria-label","확인한 카드명");
 const number=node("input","entry");number.type="text";number.maxLength=40;number.placeholder="카드번호";number.setAttribute("aria-label","확인한 카드번호");
 const region=node("select","entry");region.setAttribute("aria-label","실제 판매 국가");
 for(const [v,label] of [["UNKNOWN","판매 국가 미확인"],["KR","한국판"],["JP","일본판"],["EN","영어판 · 국가 미확인"]]){
   const option=node("option","",label);option.value=v;region.append(option);
 }
 const preview=node("img","extended-preview");preview.alt="선택한 확장 카드 사진";preview.hidden=true;
 const msg=node("p","status","사진은 이 화면에서만 표시하며 자동 학습이나 외부 업로드를 하지 않습니다.");msg.setAttribute("role","status");
 let requestToken=0;
 file.addEventListener("change",async()=>{
   const token=++requestToken;
   preview.hidden=true;preview.removeAttribute("src");
   const selected=file.files?.[0];
   if(!selected)return;
   if(selected.size<12||selected.size>12*1024*1024||!["image/jpeg","image/png","image/webp"].includes(selected.type)){
     file.value="";msg.textContent="JPEG/PNG/WebP 파일은 12MB 이하만 선택할 수 있습니다.";return;
   }
   try{
     const header=new Uint8Array(await selected.slice(0,12).arrayBuffer());
     const jpeg=header[0]===255&&header[1]===216&&header[2]===255;
     const png=[137,80,78,71,13,10,26,10].every((b,i)=>header[i]===b);
     const webp=[82,73,70,70].every((b,i)=>header[i]===b)
       &&[87,69,66,80].every((b,i)=>header[i+8]===b);
     const valid=(selected.type==="image/jpeg"&&jpeg)||(selected.type==="image/png"&&png)
       ||(selected.type==="image/webp"&&webp);
     if(!valid||typeof root.createImageBitmap!=="function")throw Error("unsupported-image");
     const bitmap=await root.createImageBitmap(selected);
     try{
       if(!bitmap.width||!bitmap.height||bitmap.width*bitmap.height>24000000)throw Error("large-image");
       const scale=Math.min(1,1080/Math.max(bitmap.width,bitmap.height));
       const canvas=d.createElement("canvas");
       canvas.width=Math.max(1,Math.round(bitmap.width*scale));
       canvas.height=Math.max(1,Math.round(bitmap.height*scale));
       const ctx=canvas.getContext("2d");
       if(!ctx)throw Error("canvas");
       ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);
       const safeRaster=canvas.toDataURL("image/png");
       if(token===requestToken){preview.src=safeRaster;preview.hidden=false;msg.textContent="안전한 PNG 미리보기 생성 완료 · 아직 카드번호·세대·등급은 확인되지 않았습니다.";}
     }finally{bitmap.close?.();}
   }catch(_){if(token===requestToken){file.value="";msg.textContent="이미지를 안전하게 해석하지 못했습니다. JPEG/PNG/WebP 사진을 다시 선택해 주세요.";}}
 });
 form.append(choose,file,preview,name,number,region);
 const open=btn("확인된 카드번호로 시세 조회",()=>{
  const game=available.find(g=>g.id===choose.value);
  if(!game){msg.textContent="등록 게임을 확인할 수 없습니다.";return;}
  if(!clean(name.value)||!clean(number.value)){msg.textContent="카드명·카드번호를 직접 확인하고 입력해야 합니다.";return;}
  if(!["KR","JP"].includes(region.value)){msg.textContent="지역 미확인 또는 영어판만으로는 시세 국가를 확정할 수 없습니다.";return;}
  if(!root.TCGCardDetail?.openFromPhoto){msg.textContent="시세 상세 모듈을 불러올 수 없습니다.";return;}
  msg.textContent="동일 카드·번호·지역의 검증된 시세를 확인하고 있습니다.";
  void root.TCGCardDetail.openFromPhoto({game:game.id,cardName:clean(name.value),cardNumber:clean(number.value),region:region.value})
    .then(exact=>{msg.textContent=exact?"동일 카드의 저장된 가격자료를 열었습니다.":"완전 일치 기록이 없어 후보 목록을 열었습니다. 가격을 확정하지 마세요.";})
    .catch(()=>{msg.textContent="시세자료 조회 실패: 저장자료나 네트워크를 확인해 주세요.";});
 },"action");
 form.append(open,msg);box.append(form);
 const gameRow=host.querySelector(".simple-game-grid");
 if(gameRow?.parentElement)gameRow.insertAdjacentElement("afterend",box);
 else host.append(box);
}
function attach(){
 const result=q("simpleGradeResult");if(!result||rootPanel)return;
 rootPanel=node("div","report");rootPanel.id="tcgPhotoResultV567";rootPanel.hidden=true;
 result.insertBefore(rootPanel,result.firstChild);
 const target=q("simpleGradeNumber");
 if(target&&root.MutationObserver){const obs=new root.MutationObserver(()=>render());obs.observe(target,{childList:true,characterData:true,subtree:true});}
 for(const id of ["identityCardName","identityCardNumber","identityRegion"]){const e=q(id);e?.addEventListener("input",render);e?.addEventListener("change",render);}
 const g=q("pokemonGenerationTitle");if(g&&root.MutationObserver){const obs=new root.MutationObserver(render);obs.observe(g,{childList:true,characterData:true,subtree:true});}
 // Scores and confidence may update without changing the integer grade.
 for(const id of ["scoreCenter","scoreCorner","scoreEdge","scoreSurface","simpleGradeConfidence"]){
   const item=q(id);
   if(item&&root.MutationObserver){const obs=new root.MutationObserver(render);obs.observe(item,{childList:true,characterData:true,subtree:true});}
 }
 const identityStatus=q("identityStatus");if(identityStatus&&root.MutationObserver){const obs=new root.MutationObserver(render);obs.observe(identityStatus,{childList:true,characterData:true,subtree:true});}
 const view=q("simpleGradeResult");
 if(view&&root.MutationObserver){const obs=new root.MutationObserver(()=>{if(view.style.display==="none")rootPanel.hidden=true;});obs.observe(view,{attributes:true,attributeFilter:["style"]});}
 void loadGames().then(mountExtendedGames);
}
if(d.readyState==="loading")d.addEventListener("DOMContentLoaded",attach,{once:true});else attach();
root.TCGPhotoResultV567=Object.freeze({version:"v567",snapshot:gradeSnapshot,strictMarketIdentity,refresh:render,eligibleGames:loadGames});
})(typeof window!=="undefined"?window:null);
