/* V567: unified photo-result report; reads existing validated capture / identity DOM only. */
(function(root){
"use strict";
if(!root||!root.document)return;
const d=root.document;
const q=id=>d.getElementById(id);
const regionName={KR:"한국어판",JP:"일본어판",EN:"영어판",UNKNOWN:"판본 미확인"};
const core={pokemon:"포켓몬",onepiece:"원피스",naruto:"나루토"};
let rootPanel=null,lookupReady=false,known=[],lastGame="",fallback=null;
function clean(value,max=140){return String(value==null?"":value).normalize("NFKC").trim().slice(0,max);}
function node(tag,cls,txt){const e=d.createElement(tag);if(cls)e.className="tcg-photo-"+cls;if(txt!==undefined)e.textContent=String(txt);return e;}
function btn(label,run,cls="action"){const e=node("button",cls,label);e.type="button";e.addEventListener("click",run);return e;}
function line(parent,k,v){const row=node("div","pair");row.append(node("span","muted",k),node("strong","",v));parent.append(row);}
function activeGame(){const selected=d.querySelector("#simpleGradeV32 .simple-game.active[data-simple-game]")||d.querySelector(".simple-game.active[data-simple-game]");return clean(selected?.dataset.simpleGame,40)||"unknown";}
function gradeSnapshot(){
 const visible=q("simpleGradeResult")?.style.display!=="none";
 const n=Number(q("simpleGradeNumber")?.textContent);
 const game=activeGame();
 return {game,gameLabel:core[game]||"선택 게임 확인 필요",isVisible:visible&&Number.isInteger(n)&&n>=1&&n<=10,
  grade:visible&&Number.isInteger(n)&&n>=1&&n<=10?n:null,
  confidence:clean(q("simpleGradeConfidence")?.textContent,130),
  cardName:clean(q("identityCardName")?.value),cardNumber:clean(q("identityCardNumber")?.value,40),
  region:clean(q("identityRegion")?.value,12),
  generation:game==="pokemon"&&!q("simplePokemonGeneration")?.hidden?clean(q("pokemonGenerationTitle")?.textContent,100):"",
  generationMeta:game==="pokemon"&&!q("simplePokemonGeneration")?.hidden?clean(q("pokemonGenerationMeta")?.textContent,180):"",
  scores:Object.fromEntries(["Center","Corner","Edge","Surface"].map(k=>[k,parseInt(q("score"+k)?.textContent||"",10)]))
 };
}
function safeImage() {
 const p=q("autoFrontPreview"),f=q("fp");
 const source=p?.getAttribute("src")||f?.getAttribute("src")||"";
 if(!(source.startsWith("blob:")||source.startsWith("data:image/")))return "";
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
 try{const result=await api.openFromPhoto({game:s.game,region:s.region,cardName:s.cardName,cardNumber:s.cardNumber});if(!result)notify("동일 카드·번호·판본의 확인된 거래가가 없습니다. 상세 목록에서 다른 후보를 수동 확인할 수 있습니다.");}
 catch(_){notify("시세 상세 페이지를 열지 못했습니다. 인터넷과 저장자료를 확인해 주세요.");}
}
function render(){
 if(!rootPanel)return;
 const s=gradeSnapshot();
 if(!s.isVisible){rootPanel.hidden=true;return;}
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
 const score=node("div","score");score.append(node("span","muted","사진 기반 사전등급"),node("strong","rating",String(s.grade)+" / 10"));
 main.append(score,node("p","hint",s.confidence||"측정 신뢰도 정보 없음"));
 main.append(node("p","warn","PSA/BGS/CGC/TAG/BRG 공식 등급이 아닙니다. 등급 8·9·10 확률은 검증된 확률 모델 결과가 없으면 표시하지 않습니다."));
 deck.append(art,main);hero.append(deck);rootPanel.append(hero);
 const metrics=section("정밀 상태 분석","기존 촬영 엔진의 센터링·코너·엣지·표면 값을 그대로 표시합니다.");
 metrics.append(metricGrid(s));rootPanel.append(metrics);
 const grades=section("등급별 참고 시세","RAW · PSA 8 · PSA 9 · PSA 10. 완료된 실거래가 확인되지 않은 등급은 ‘자료 없음’으로 표시합니다.");
 const gradeCards=node("div","gradecards");["RAW","PSA 8","PSA 9","PSA 10"].forEach(label=>{
 const a=node("div","gradecard");a.append(node("strong","grade-label",label),node("p","unavailable","확인된 거래 자료 없음"));gradeCards.append(a);
 });grades.append(gradeCards);rootPanel.append(grades);
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
function attach(){
 const result=q("simpleGradeResult");if(!result||rootPanel)return;
 rootPanel=node("div","report");rootPanel.id="tcgPhotoResultV567";rootPanel.hidden=true;
 result.insertBefore(rootPanel,result.firstChild);
 const target=q("simpleGradeNumber");
 if(target&&root.MutationObserver){const obs=new root.MutationObserver(()=>render());obs.observe(target,{childList:true,characterData:true,subtree:true});}
 for(const id of ["identityCardName","identityCardNumber","identityRegion"]){const e=q(id);e?.addEventListener("input",render);e?.addEventListener("change",render);}
 const g=q("pokemonGenerationTitle");if(g&&root.MutationObserver){const obs=new root.MutationObserver(render);obs.observe(g,{childList:true,characterData:true,subtree:true});}
 const view=q("simpleGradeResult");
 if(view&&root.MutationObserver){const obs=new root.MutationObserver(()=>{if(view.style.display==="none")rootPanel.hidden=true;});obs.observe(view,{attributes:true,attributeFilter:["style"]});}
 void loadGames();
}
if(d.readyState==="loading")d.addEventListener("DOMContentLoaded",attach,{once:true});else attach();
root.TCGPhotoResultV567=Object.freeze({version:"v567",snapshot:gradeSnapshot,strictMarketIdentity,refresh:render,eligibleGames:loadGames});
})(typeof window!=="undefined"?window:null);
