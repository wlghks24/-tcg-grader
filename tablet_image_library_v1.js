/* Tablet TCG Card Images v1 — Android internal Pictures, 30-game registry-driven.
 * User-selected files only; no bulk scraping or public image redistribution. */
(() => {
  "use strict";
  const API = '/api/local-card-images';
  const ROOT_ID = 'tcgImageLibraryV1';
  const LIMIT = 5 * 1024 * 1024;
  const validGame = /^[a-z0-9][a-z0-9-]{0,63}$/;
  let registry = [];
  let photos = [];
  let visibleLimit = 60;
  const el = (tag, txt, klass) => {
    const n = document.createElement(tag);
    if (txt != null) n.textContent = String(txt);
    if (klass) n.className = klass;
    return n;
  };
  const btn = (txt) => { const b=el('button',txt);b.type='button';return b; };
  async function getJson(url) {
    const r = await fetch(url,{cache:'no-store',credentials:'same-origin'});
    if (!r.ok) throw Error('응답 오류 '+r.status);
    return r.json();
  }
  async function postJson(path, payload) {
    const r = await fetch(API + path,{
      method:'POST',credentials:'same-origin',cache:'no-store',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)
    });
    const data=await r.json().catch(()=>({}));
    if (!r.ok || !data.ok) throw Error(data.error||'저장소 요청 실패');
    return data;
  }
  function choose(select, entries) {
    select.replaceChildren();
    for(const [value,label] of entries) {const x=el('option',label);x.value=value;select.append(x);}
  }
  const style = el('style');
  style.textContent = `
  #${ROOT_ID}{margin:16px 0;background:#fff;border:1px solid #cbd5e1;border-radius:18px;padding:16px;color:#111827}
  #${ROOT_ID} h2{font-size:21px;margin:0 0 8px;color:#0f172a}
  #${ROOT_ID} .tcg-img-muted{font-size:13px;color:#475569;margin:5px 0 12px;line-height:1.6}
  #${ROOT_ID} .tcg-img-controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
  #${ROOT_ID} [hidden]{display:none!important}
  #${ROOT_ID} label{font-size:13px;font-weight:700;color:#334155;display:flex;flex-direction:column;gap:4px}
  #${ROOT_ID} input,#${ROOT_ID} select{padding:10px;border:1px solid #94a3b8;border-radius:9px;width:100%;min-width:0;font-size:15px;background:#fff;color:#111827}
  #${ROOT_ID} button{background:#164e63;color:white;border:0;border-radius:11px;padding:11px 14px;margin:7px 0 3px;min-height:44px;cursor:pointer}
  #${ROOT_ID} button.secondary{background:#475569}
  #${ROOT_ID} button:disabled{opacity:.48}
  #${ROOT_ID} .tcg-img-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;margin:12px 0}
  #${ROOT_ID} figure{padding:6px;margin:0;border:1px solid #e2e8f0;border-radius:12px;min-width:0}
  #${ROOT_ID} figure img{width:100%;height:158px;object-fit:contain;background:#f1f5f9;border-radius:7px}
  #${ROOT_ID} figcaption{font-size:12px;word-break:break-word;line-height:1.5}
  #${ROOT_ID} .tcg-manual-optional{border:1px solid #e2e8f0;background:#f8fafc;border-radius:12px;padding:9px 12px;margin:10px 0}
  #${ROOT_ID} .tcg-manual-optional summary{cursor:pointer;font-weight:700;color:#475569;font-size:13px;padding:4px}
  #${ROOT_ID} .tcg-img-footer{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
  #${ROOT_ID} [role=status]{font-size:13px;line-height:1.5;color:#0f172a;white-space:pre-wrap}
  @media(max-width:440px){#${ROOT_ID} .tcg-img-controls{grid-template-columns:1fr}}
  `;
  const app = document.querySelector('main.app') || document.body;
  const root=el('section',null);root.id=ROOT_ID;root.setAttribute('aria-label','태블릿 카드 이미지 보관함');
  root.append(el('h2','🖼️ 카드 이미지 보관함 · 전체 등록 게임'));
  root.append(el('p','등록된 게임의 한국판 · 일본판 · 미국판 · 중국판(간체/번체) 이미지를 태블릿 Pictures/TCG_Card_Images에 보관합니다. 저장된 사진은 인터넷 없이도 열람할 수 있습니다.','tcg-img-muted'));
  const form=el('form');
  const controls=el('div',null,'tcg-img-controls');
  const game=el('select'),country=el('select'),chineseType=el('select'),kind=el('select');
  const title=el('input');title.placeholder='카드명 / BOX명 / 카드번호';title.maxLength=130;title.required=true;
  const picker=el('input');picker.type='file';picker.accept='image/jpeg,image/png,image/webp';picker.required=true;
  const fields=[['게임 (전체 등록 목록)',game],['지역 (4종 전체)',country],['상품 구분',kind],['카드·상품명',title],['사진 선택 (JPG / PNG / WebP)',picker]];
  for(const [txt,node] of fields){const label=el('label',txt);label.append(node);controls.append(label);}
  choose(country,[['KR','한국판'],['JP','일본판'],['US','미국판'],['CN','중국판']]);
  choose(chineseType,[['CN-S','간체중국어 (중국 대륙)'],['CN-T','번체중국어 (대만·홍콩)']]);
  const chineseLabel=el('label','중국판 언어');chineseLabel.append(chineseType);controls.append(chineseLabel);
  const syncChinese=()=>{const isChinese=country.value==='CN';chineseLabel.hidden=!isChinese;chineseType.disabled=!isChinese;};
  country.addEventListener('change',syncChinese);syncChinese();
  const kindNames={CARD:'싱글카드',BOX:'BOX',PACK:'부스터팩',COLLECTION:'특별 컬렉션',PROMO:'프로모',DECK:'스타터덱',ACCESSORY:'액세서리',BUNDLE:'플레이매트·카드 세트',OTHER:'기타'};
  choose(kind,Object.entries(kindNames));
  form.append(controls);
  const save=el('button','선택한 사진 태블릿에 저장');save.type='submit';save.disabled=true;
  form.append(save);
  const status=el('p','게임 목록과 태블릿 저장소를 확인하는 중입니다.');status.setAttribute('role','status');
  form.append(status);
  // Automatic discovery is the default workflow. Manual upload stays available
  // only as an optional advanced fallback; never required to complete sync.
  const manualPanel=el('details');manualPanel.className='tcg-manual-optional';
  const manualLabel=el('summary','직접 사진 등록 (선택 기능)');
  manualPanel.append(manualLabel,form);
  root.append(manualPanel);

  const row=el('div',null,'tcg-img-footer');
  const total=el('strong','로컬 사진 0장');
  const refresh=btn('사진 목록 새로고침');refresh.className='secondary';
  const filter=el('select');filter.setAttribute('aria-label','게임별 이미지 필터');
  const countryFilter=el('select');countryFilter.setAttribute('aria-label','지역별 이미지 필터');
  const kindFilter=el('select');kindFilter.setAttribute('aria-label','상품 종류별 이미지 필터');
  choose(kindFilter,[['','전체 상품 종류'],...Object.entries(kindNames)]);
  choose(countryFilter,[['','4개 지역 전체'],['KR','한국판'],['JP','일본판'],['US','미국판'],['CN','중국판 (간체·번체)']]);
  row.append(total,filter,countryFilter,kindFilter,refresh);root.append(row);
  const images=el('div',null,'tcg-img-grid');root.append(images);
  const more=btn('사진 더 보기');more.hidden=true;root.append(more);
  more.addEventListener('click',()=>{visibleLimit+=60;render();});
  // v4.4: evidence reconciliation is automatic, not a manual control.
  const bridgeOutput=el('div','🔄 기존 카드·BOX 자료와 이미지 자동 교차검증 준비 중...','tcg-img-muted');
  bridgeOutput.id='tcgAutoCrossStatusV44';
  bridgeOutput.setAttribute('role','status');
  root.insertBefore(bridgeOutput,images);
  let crossInFlight=false;
  async function autoCross(){
    if(crossInFlight)return;
    crossInFlight=true;
    try{
      const [data,links]=await Promise.all([
        getJson(API+'/cross-status'),getJson(API+'/catalog-links')]);
      if(!data.ok||!data.summary||!links.ok||!links.summary)throw Error('교차분석 결과 형식 오류');
      const x=data.summary;
      const rawLinked=links.summary.auto_linked;
      const linked=Number.isSafeInteger(rawLinked)&&rawLinked>=0?rawLinked:null;
      bridgeOutput.replaceChildren();
      bridgeOutput.append(el('strong', linked===0?
        '⚠️ 자동 연결 0건 · 기존 사진은 안전하게 보관 중':
        linked===null?'⚠️ 연결 상태 확인 대기':
        '🔎 코드 일치 연결 '+linked+'건 · 실물판본/아트 검증 별도'));
      bridgeOutput.append(el('p',`수집 상품정보 ${x.catalog_records_analyzed}건 · 보관 이미지 ${x.local_files_present}장 · 상품→이미지 미연결 ${x.catalog_to_image_gaps}건 · 이미지→상품 미연결 ${x.image_to_catalog_gaps}건`));
      bridgeOutput.append(el('p','미연결 이미지도 사진 보관함에서 별도로 열람할 수 있습니다. 코드 일치는 실물·아트·시세 검증이 아닙니다. 이름이나 국가만 맞는 사진은 자동 연결하지 않습니다.','tcg-img-muted'));
    }catch(ex){
      bridgeOutput.textContent='⚠️ 자동 교차검증 연결 오류: '+ex.message+' · 기존 사진은 안전하게 보존됩니다.';
    }finally{crossInFlight=false;}
  }
  document.addEventListener("tcg-local-images-updated",autoCross);
  autoCross();
  setInterval(()=>{if(!document.hidden)autoCross();},90000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)autoCross();});
  // v4.6: Images are already reflected inside the existing card/BOX catalog.
  // Do not duplicate the whole photo gallery at the bottom of the app.
  // Keep an optional management UI (including safe delete) available on demand.
  const manager=el('details');manager.id='tcgImageManagementV46';
  manager.className='tcg-image-manager-v46';
  const managerSummary=el('summary','🗃️ 사진 보관함 관리 (필요할 때 펼치기)');
  manager.append(managerSummary,root);
  const boxArea=document.getElementById('box12section');
  const imageSurface=document.getElementById('tcgImageLibrarySurface');
  if(imageSurface)imageSurface.append(manager);
  else if(boxArea&&boxArea.parentNode)boxArea.before(manager);else app.prepend(manager);
  const quick=btn('🖼️ 태블릿 사진 보관함 확인');
  quick.id='tcgImageQuickAccessV9';
  quick.setAttribute('aria-controls','tcgImageManagementV46');
  quick.setAttribute('aria-expanded','false');
  quick.style.cssText='margin:10px 0;padding:11px 14px;min-height:44px;border-radius:10px;border:1px solid #94a3b8;background:#164e63;color:#fff;font-size:13px;cursor:pointer';
  manager.before(quick);
  quick.addEventListener('click',()=>{
    manager.open=!manager.open;
    quick.setAttribute('aria-expanded',String(manager.open));
    if(manager.open)manager.scrollIntoView({block:'nearest'});
  });
  manager.addEventListener('toggle',()=>quick.setAttribute('aria-expanded',String(manager.open)));
  style.textContent+=`
.tcg-image-manager-v46{margin:12px 0;border:1px solid #cbd5e1;border-radius:12px;background:#f8fafc;padding:8px 12px}
.tcg-image-manager-v46>summary{font-size:13px;font-weight:750;cursor:pointer;color:#475569;padding:8px}
.tcg-image-manager-v46 #${ROOT_ID}{margin:8px 0;padding:12px}
`;
  document.head.append(style);
  manager.addEventListener('toggle',()=>{if(manager.open)render();else images.replaceChildren();});
  function say(message){status.textContent=message;}
  function render(){
    images.replaceChildren();
    more.hidden=true;
    total.textContent=`태블릿 로컬 사진 ${photos.length.toLocaleString('ko-KR')}장`;
    managerSummary.textContent=`🗃️ 사진 보관함 관리 (${photos.length}장 · 필요할 때 펼치기)`;
    quick.textContent=`🖼️ 태블릿 사진 ${photos.length}장 확인 (시세 연결과 별도)`;
    if(!manager.open)return;
    const selected=filter.value;
    const selectedCountry=countryFilter.value;
    const selectedKind=kindFilter.value;
    const shown=photos.filter(x=>(!selected||x.game_id===selected)&&(!selectedKind||x.kind===selectedKind)&&(!selectedCountry||x.region===selectedCountry||(selectedCountry==='CN'&&(x.region==='CN-S'||x.region==='CN-T'))));
    total.textContent=`태블릿 로컬 사진 ${photos.length.toLocaleString('ko-KR')}장`;
    if(!shown.length){images.append(el('p','선택한 게임에 저장된 사진이 없습니다. 사진 선택으로 추가하세요.','tcg-img-muted'));return;}
    const lookup = new Map(registry.map(x=>[x.id,x.label_ko]));
    more.hidden=shown.length<=visibleLimit;
    for(const row of shown.slice(0,visibleLimit)){
      const fig=el('figure');
      const img=el('img');img.loading='lazy';img.alt=row.name||'보관 카드 사진';
      img.src=API+'/file/'+encodeURIComponent(row.id);img.referrerPolicy='no-referrer';
      img.addEventListener('error',()=>{img.removeAttribute('src');img.alt='사진을 읽지 못했습니다. 저장소 권한을 확인하세요.';});
      const regionName=({KR:'한국판',JP:'일본판',US:'미국판','CN-S':'중국판 간체','CN-T':'중국판 번체'})[row.region]||row.region;
      const caption=el('figcaption',(lookup.get(row.game_id)||row.game_id)+' · '+regionName+' · '+(kindNames[row.kind]||row.kind)+'\n'+row.name+(row.origin==='auto'&&row.provider?'\n자동수집: '+row.provider:''));
      const remove=btn('사진 삭제');remove.className='secondary';
      remove.setAttribute('aria-label',row.name+' 삭제');
      remove.addEventListener('click',async()=>{
        if(!window.confirm('이 사진을 태블릿에서도 삭제할까요? 되돌릴 수 없습니다.'))return;
        remove.disabled=true;
        try {await postJson('/delete',{id:row.id});await reload();say('사진을 태블릿에서 삭제했습니다.');}
        catch(ex){say('삭제 실패: '+ex.message);remove.disabled=false;}
      });
      const open=el('a','크게 보기');open.href=API+'/file/'+encodeURIComponent(row.id);open.target='_blank';open.rel='noopener';
      if(row.image_storage?.lossless===true)caption.textContent+='\n해상도 유지 · '+(row.image_storage.encoding==='webp-lossless'?'무손실 WebP':'원본 형식 유지');
      if(row.image_storage?.readability_review_required===true)caption.textContent+=' · 저해상도 확인 필요';
      fig.append(img,caption,open,remove);images.append(fig);
    }
  }
  async function reload(){
    const result=await getJson(API);
    if(!result.ok||!Array.isArray(result.items))throw Error('로컬 보관함 오류');
    photos=result.items;render();
    document.dispatchEvent(new Event("tcg-local-images-updated"));
    return result;
  }
  form.addEventListener('submit',async(event)=>{
    event.preventDefault();
    const f=picker.files && picker.files[0];
    if(!f){say('사진 파일을 선택하세요.');return;}
    if(!['image/jpeg','image/png','image/webp'].includes(f.type)||f.size>LIMIT||f.size<24){say('JPG/PNG/WebP, 5MB 이하의 사진만 가능합니다.');return;}
    if(!validGame.test(game.value)||!registry.some(x=>x.id===game.value)){say('게임을 다시 선택하세요.');return;}
    save.disabled=true;say('선택한 사진을 태블릿 저장소에 기록합니다.');
    try{
      const dataUri=await new Promise((resolve,reject)=>{const rd=new FileReader();rd.onload=()=>resolve(rd.result);rd.onerror=()=>reject(Error('사진을 읽을 수 없습니다.'));rd.readAsDataURL(f);});
      const region=country.value==='CN'?chineseType.value:country.value;
      await postJson('/save',{game_id:game.value,region,kind:kind.value,name:title.value,image_base64:dataUri});
      picker.value='';title.value='';
      await reload();say('사진이 태블릿 Pictures/TCG_Card_Images에 저장됐습니다.');
    }catch(ex){say('저장 실패: '+ex.message+' · Termux 저장소 권한 및 용량을 확인하세요.');}
    finally{save.disabled=false;}
  });
  refresh.addEventListener('click',()=>reload().then(()=>say('이미지 목록을 새로고침했습니다.')).catch(ex=>say('조회 실패: '+ex.message)));
  for(const select of [filter,countryFilter,kindFilter])select.addEventListener('change',()=>{visibleLimit=60;render();});
  function syncGame(value){
    const clean=v=>String(v||'').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
    const row=registry.find(x=>[x.id,x.canonical,x.label_ko].some(y=>y&&clean(y)===clean(value)));
    if(value==='ALL'||row){filter.value=row?row.id:'';visibleLimit=60;render();}
  }
  document.getElementById('analysisGame')?.addEventListener('change',event=>syncGame(event.target.value));
  document.addEventListener('click',event=>{const button=event.target.closest?.('.tcg-market-game');if(button)syncGame(button.dataset.game);});
  (async()=>{
    try {
      const result=await getJson('tcg_game_registry.json');
      if(result.schema_version!==1||!Array.isArray(result.games))throw Error('게임 목록 형식 오류');
      registry=result.games.filter(x=>x&&validGame.test(x.id)&&typeof x.label_ko==='string').slice(0,64);
      if(!registry.length)throw Error('게임 목록이 비어 있습니다.');
      choose(game,registry.map(x=>[x.id,x.label_ko+' · '+(x.state==='watch'?'관찰':'수집')]));
      choose(filter,[['','전체 게임'],...registry.map(x=>[x.id,x.label_ko])]);
      window.TCGLocalImageRegistry=Object.freeze(registry.map(x=>Object.freeze({id:x.id,canonical:x.canonical,label_ko:x.label_ko})));
      document.dispatchEvent(new Event('tcg-image-registry-loaded'));
      await reload();save.disabled=false;
      say('게임 '+registry.length+'종 로딩 완료 · 저장되는 사진은 태블릿 내부에만 보관됩니다.');
    }catch(ex){say('초기화 실패: '+ex.message+' · Termux 실행/저장소 권한을 확인하세요.');}
  })();
})();

/* v4.5: image-evidence items become first-class records inside the existing
   card-information and BOX/product lists. Not price/release facts. */
(() => {
  'use strict';
  const API='/api/local-card-images/catalog-links';
  const IDPAT=/^\/api\/local-card-images\/file\/[a-f0-9]{32}$/;
  const cardsId='countryAnalysisList', productsId='box12';
  const CARD_TYPES=new Set(['CARD','PROMO']);
  const PRODUCT_TYPES=new Set(['BOX','PACK','COLLECTION','DECK','ACCESSORY','BUNDLE','OTHER']);
  const types={CARD:'싱글카드',PROMO:'프로모',BOX:'밀봉 BOX',PACK:'부스터팩 (BOX 아님)',COLLECTION:'특별 컬렉션',DECK:'스타터덱',BUNDLE:'묶음상품',ACCESSORY:'액세서리',OTHER:'기타 상품'};
  const countries={KR:'한국어판',JP:'일본어판',US:'영어판','CN-S':'중국어 간체판','CN-T':'중국어 번체판'};
  const gameNames={pokemon:'Pokémon',onepiece:'ONE PIECE',naruto:'NARUTO',gundam:'GUNDAM',mtg:'Magic: The Gathering',yugioh:'Yu-Gi-Oh!',lorcana:'Disney Lorcana',swu:'Star Wars Unlimited',riftbound:'Riftbound'};
  const clean=v=>String(v||'').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
  const games=Object.fromEntries(Object.entries(gameNames).map(([id,n])=>[clean(n),id]));
  Object.assign(games,{pokemon:'pokemon',포켓몬:'pokemon',onepiece:'onepiece',원피스:'onepiece',gundam:'gundam',건담:'gundam',매직더개더링:'mtg',magic:'mtg',magicthegathering:'mtg',유희왕:'yugioh',y기:'yugioh',swu:'swu'});
  let data=[], matches=[], sourceCatalog=[], inFlight=false, mounted=false, lastSig='', cardLimit=60, productLimit=60;
  const el=(tag,cls,txt)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined)n.textContent=txt;return n;};
  const selected=id=>String(document.getElementById(id)?.value||'ALL');
  function selectedGame(v,id){
    if(v==='ALL')return true;
    return (games[clean(v)]||clean(v))===id;
  }
  function selectedCountry(v,region){return v==='ALL'||v===region||(v==='CN'&&region.startsWith('CN-'));}
  function evidence(row){
    if(!row||typeof row!=='object'||!IDPAT.test(row.image_url)||
       !/^[a-f0-9]{32}$/.test(String(row.id||''))||
       !/^[a-z0-9-]{2,64}$/.test(String(row.game_id||''))||
       !['KR','JP','US','CN-S','CN-T'].includes(row.region)||
       !(CARD_TYPES.has(row.kind)||PRODUCT_TYPES.has(row.kind)))return false;
    return true;
  }
  function content(row){
    const figure=el('div','tcg-v45-record');
    figure.dataset.tcgV45='true';figure.dataset.game=row.game_id;figure.dataset.region=row.region;figure.dataset.kind=row.kind;
    const img=el('img');img.loading='lazy';img.alt=String(row.name||'카드 상품 이미지').slice(0,135);
    img.src=row.image_url;img.referrerPolicy='no-referrer';
    img.addEventListener('error',()=>{img.removeAttribute('src');img.alt='로컬 사진 표시 오류';});
    const body=el('div','tcg-v45-body');
    body.append(el('strong',null,String(row.name||'상품명 미확인').slice(0,130)));
    body.append(el('small',null,`${gameNames[row.game_id]||row.game_id} · ${countries[row.region]} · ${types[row.kind]||row.kind}`));
    body.append(el('small',null,`이미지 출처: ${String(row.provider||'태블릿').slice(0,35)} · 시세·실물판본 미확인`));
    if(row.source_id)body.append(el('small',null,`출처 식별값: ${String(row.source_id).slice(0,80)}`));
    const metadata=row.card_metadata;
    if(metadata && typeof metadata==='object'){
      const fields=[['card_code','카드 코드'],['card_number','카드 번호'],['set_name','세트'],['set_code','세트 코드'],['language','언어'],['rarity','레어도'],['card_type','종류']];
      for(const [key,label] of fields)if(typeof metadata[key]==='string'&&metadata[key].trim())body.append(el('small',null,label+': '+metadata[key].slice(0,160)));
    }
    if(row.metadata_status==='MISSING_CARD_METADATA')body.append(el('small',null,'카드 상세정보 수집 대기 · 이미지 수집과 별도로 재확인합니다.'));
    if(row.identity_verification==='CODE_MATCH' && row.linked_to_existing_catalog===true){
      const metadata=row.metadata_evidence;
      if(metadata && typeof metadata.name==='string')body.append(el('small',null,'기존 정보 연결: '+metadata.name.slice(0,175)+' · 이미지 실물 검증 별도'));
    }
    figure.append(img,body);return figure;
  }
  // The original card/BOX collectors continue to own prices and verified dates.
  // A source-only row is supplementary evidence; it is NOT a verified card price.
  function sourceEvidence(row){
    return row && typeof row==='object' && /^[a-z0-9-]{2,64}$/.test(String(row.game_id||'')) &&
      ['KR','JP','US','CN-S','CN-T'].includes(row.region) &&
      (CARD_TYPES.has(row.kind)||PRODUCT_TYPES.has(row.kind)) &&
      ['releases','market'].includes(row.signal) &&
      /^https:\/\/[^\s/@#?]+(?:\/|$)/.test(String(row.source_url||'')) &&
      String(row.name||'').length>0 && String(row.name).length<=175;
  }
  function sourceCard(row){
    const figure=el('div','tcg-v45-record tcg-v46-source-record');
    figure.dataset.tcgV46='true';figure.dataset.kind=row.kind;
    const empty=el('div','tcg-v46-noimage','🔎 이미지 자동수집 대기');figure.append(empty);
    const body=el('div','tcg-v45-body');
    body.append(el('strong',null,row.name));
    body.append(el('small',null,`${gameNames[row.game_id]||row.game_id} · ${countries[row.region]} · ${types[row.kind]||row.kind}`));
    body.append(el('small',null,`${row.signal==='releases'?'기존 출시 수집자료':'기존 시세 수집자료'} · 사진 및 최신 정보 대조 중`));
    const link=el('a',null,'수집 근거 확인');link.rel='noopener noreferrer';link.target='_blank';link.href=row.source_url;
    body.append(link);figure.append(body);return figure;
  }
  function alreadyInLegacy(row){
    if(typeof COUNTRY_BOX_DATA==='undefined'||!Array.isArray(COUNTRY_BOX_DATA))return false;
    return COUNTRY_BOX_DATA.some(x=>x.country===row.region && selectedGame(String(x.game||''),row.game_id) &&
      [x.name,x.native,x.hitName].some(label=>clean(label)&&clean(label)===clean(row.name)));
  }
  function alreadyInPhotos(row){
    // A photo name or provider code substring is not a verified catalog link.
    // Do not hide an independently collected source observation until the
    // backend explicitly labels the image as linked to that catalog record.
    return data.some(p=>p.linked_to_existing_catalog===true&&p.game_id===row.game_id&&
      p.region===row.region&&p.kind===row.kind&&clean(p.name)===clean(row.name));
  }
  function sourceRows(allowed,country,game,query=''){
    return sourceCatalog.filter(x=>allowed.has(x.kind)&&selectedCountry(country,x.region)&&selectedGame(game,x.game_id)&&
      (!query||`${x.name} ${x.product_codes?.join(' ')||''} ${gameNames[x.game_id]||''}`.toLowerCase().includes(query))&&
      !alreadyInPhotos(x)&&!alreadyInLegacy(x));
  }
  function appendCards(){
    const host=document.getElementById(cardsId);if(!host)return 0;
    host.querySelectorAll('[data-tcg-v45="true"], [data-tcg-v46="true"]').forEach(n=>n.remove());
    const country=selected('analysisCountry'),asset=selected('analysisAsset'),game=selected('analysisGame'),query=String(document.getElementById('analysisQuery')?.value||'').toLowerCase().trim();
    if(asset==='BOX')return 0;
    const pool=data.filter(x=>CARD_TYPES.has(x.kind)&&selectedCountry(country,x.region)&&selectedGame(game,x.game_id)&&(!query||`${x.name} ${x.source_id} ${gameNames[x.game_id]||''}`.toLowerCase().includes(query)));
    for(const x of pool.slice(0,cardLimit))host.append(content(x));
    const discovery=sourceRows(CARD_TYPES,country,game,query);
    for(const x of discovery.slice(0,cardLimit))host.append(sourceCard(x));
    if(pool.length>cardLimit||discovery.length>cardLimit){
      const more=el('button','','이 게임의 카드 더 보기');more.type='button';more.dataset.tcgV45='true';
      more.addEventListener('click',()=>{cardLimit+=60;appendCards();});host.append(more);
    }
    const count=document.getElementById('analysisCount');
    if(count){
      const normal=count.textContent.split(' · 이미지 확보 ')[0];
      count.textContent=`${normal} · 이미지 확보 ${pool.length}건 · 기존 수집 보완 ${discovery.length}건`;
    }
    return pool.length;
  }
  function appendProducts(){
    const host=document.getElementById(productsId);if(!host)return 0;
    host.querySelectorAll('[data-tcg-v45="true"], [data-tcg-v46="true"]').forEach(n=>n.remove());
    const active=document.querySelector('.box-kb-country.active');
    const country=String(active?.dataset?.kbCountry||'ALL');
    const game=selected('boxKbGame');
    const pool=data.filter(x=>PRODUCT_TYPES.has(x.kind)&&selectedCountry(country,x.region)&&selectedGame(game,x.game_id));
    for(const x of pool.slice(0,productLimit))host.append(content(x));
    const discovery=sourceRows(PRODUCT_TYPES,country,game);
    for(const x of discovery.slice(0,productLimit))host.append(sourceCard(x));
    if(pool.length>productLimit||discovery.length>productLimit){
      const more=el('button','','상품 이미지 더 보기');more.type='button';more.dataset.tcgV45='true';
      more.addEventListener('click',()=>{productLimit+=60;appendProducts();});host.append(more);
    }
    const label=document.getElementById('boxKbCount');
    if(label){const normal=label.textContent.split(' · 추가 상품 사진 ')[0];label.textContent=`${normal} · 추가 상품 사진 ${pool.length}건 · 출시/시세 출처 보완 ${discovery.length}건`;}
    return pool.length;
  }
  function applyExactBoxPhotos(){
    // V6 candidate: ONLY server CODE_MATCH and unique same-game/region/BOX references.
    // Never assume display order equals COUNTRY_BOX_DATA order after asynchronous redraw.
    const host=document.getElementById(productsId);
    if(!host||!Array.isArray(matches)||typeof COUNTRY_BOX_DATA==='undefined'||!Array.isArray(COUNTRY_BOX_DATA))return 0;
    const safe=matches.filter(x=>x&&x.kind==='BOX'&&x.catalog_kind==='BOX'&&x.match==='CODE_MATCH'&&
      IDPAT.test(String(x.image_url||''))&&
      // The image must still exist in the server-provided local catalog, not only in a stale match.
      data.some(p=>p.image_url===x.image_url&&p.kind==='BOX'&&p.region===x.region&&p.game_id===x.game_id));
    const cards=[...host.querySelectorAll('.box-kb-card')];
    let linked=0;
    for(const row of COUNTRY_BOX_DATA){
      const active=document.querySelector('.box-kb-country.active');
      const region=String(active?.dataset?.kbCountry||'ALL');
      if(!selectedCountry(region,row.country)||!selectedGame(selected('boxKbGame'),games[clean(row.game)]||clean(row.game)))continue;
      const refs=safe.filter(x=>x.region===row.country&&selectedGame(row.game,x.game_id)&&
        clean(x.catalog_name)===clean(row.name));
      if(refs.length!==1)continue;
      // A name/native collision between editions or products must never take a photo by position.
      const catalogDuplicates=COUNTRY_BOX_DATA.filter(x=>x.country===row.country&&
        clean(x.game)===clean(row.game)&&
        clean(x.name)===clean(row.name));
      if(catalogDuplicates.length!==1)continue;
      const targets=cards.filter(card=>clean(card.querySelector('.box-kb-name')?.textContent)===clean(row.name)&&
        clean(card.querySelector('.box-kb-native')?.textContent)===clean(row.native));
      if(targets.length!==1)continue;
      const visual=targets[0].querySelector('.box-kb-image');
      if(!visual)continue;
      let img=visual.querySelector('img');
      if(!img){img=document.createElement('img');img.loading='lazy';img.decoding='async';visual.prepend(img);}
      const url=refs[0].image_url;
      if(img.getAttribute('src')!==url){
        img.addEventListener('error',()=>{
          img.removeAttribute('src');img.style.display='none';
          const fallback=visual.querySelector('.box-kb-fallback');if(fallback)fallback.style.display='block';
        },{once:true});
        img.src=url;
      }
      img.style.display='block';img.alt=row.name+' 로컬 상품 이미지 (코드 일치 · 이미지 실물 검증 별도)';
      img.referrerPolicy='no-referrer';
      visual.dataset.tcgLocalImage='code-match';
      const fallback=visual.querySelector('.box-kb-fallback');if(fallback)fallback.style.display='none';
      linked++;
    }
    return linked;
  }
  function render(){appendCards();appendProducts();applyExactBoxPhotos();}
  async function refresh(){
    if(inFlight)return;
    inFlight=true;
    try{
      const res=await fetch(API,{cache:'no-store',credentials:'same-origin'});
      if(!res.ok)throw Error(`HTTP ${res.status}`);
      const json=await res.json();
      if(!json.ok||json.version!==46||!Array.isArray(json.local_catalog)||!Array.isArray(json.source_catalog))throw Error('API schema');
      const records=json.local_catalog.filter(evidence).slice(0,2500);
      const sources=json.source_catalog.filter(sourceEvidence).slice(0,1500);
      const sig=JSON.stringify([records.map(r=>[r.id,r.name,r.region,r.kind,r.game_id,r.source_id,r.card_metadata,r.metadata_evidence,r.metadata_status]),json.catalog_matches||[],sources.map(x=>[x.game_id,x.region,x.kind,x.name,x.signal,x.source_url])]);
      data=records;matches=Array.isArray(json.catalog_matches)?json.catalog_matches:[];sourceCatalog=sources;
      if(sig!==lastSig||!mounted){lastSig=sig;render();mounted=true;}
    }catch(_){ /* Preserve UI when offline; next cycle retries. */ }
    finally{inFlight=false;}
  }
  function boot(){
    function updateGameRegistry(){
      const registry=window.TCGLocalImageRegistry;
      if(!Array.isArray(registry))return;
      for(const row of registry){
        if(!row||!/^[a-z0-9-]{2,64}$/.test(row.id))continue;
        for(const name of [row.id,row.canonical,row.label_ko])if(typeof name==='string'&&name)games[clean(name)]=row.id;
        if(typeof row.label_ko==='string')gameNames[row.id]=row.label_ko;
      }
      render();
    }
    document.addEventListener('tcg-image-registry-loaded',updateGameRegistry);
    updateGameRegistry();
    const style=el('style');style.textContent=`
      .tcg-v45-record{border:1px solid #cad5e5;border-radius:13px;background:#f8fbff;min-width:0;overflow:hidden;display:flex;flex-direction:column}
      .tcg-v45-record img{width:100%;height:190px;object-fit:contain;background:#edf3fb}
      .tcg-v45-body{padding:11px;overflow-wrap:anywhere;line-height:1.45}
      .tcg-v45-body strong{display:block;font-size:13px;margin-bottom:4px}
      .tcg-v45-body small{display:block;color:#475569;font-size:11px;margin-top:3px}
      #box12 .tcg-v45-record{margin:0}
      .tcg-v46-source-record .tcg-v46-noimage{height:110px;background:#edf2f8;color:#64748b;display:grid;place-items:center;font-size:12px}
      @media(max-width:480px){.tcg-v45-record img{height:150px}}
    `;document.head.append(style);
    // Existing legacy renderers replace their whole grid on every filter change.
    // Install event-level reattachment AFTER legacy synchronous handlers run.
    for(const id of ['analysisCountry','analysisAsset','analysisGame','analysisSort','analysisQuery','analysisSearchBtn','analysisClearBtn']){
      const ctl=document.getElementById(id);
      if(ctl)for(const ev of ['change','click','keydown'])ctl.addEventListener(ev,()=>{cardLimit=60;queueMicrotask(appendCards);});
    }
    document.getElementById('boxKbGame')?.addEventListener('change',()=>{productLimit=60;queueMicrotask(()=>{appendProducts();applyExactBoxPhotos();});});
    document.querySelectorAll('.box-kb-country').forEach(b=>b.addEventListener('click',()=>{productLimit=60;queueMicrotask(()=>{appendProducts();applyExactBoxPhotos();});}));
    const observerTargets=[document.getElementById(cardsId),document.getElementById(productsId)];
    // A legacy collector can re-render after asynchronously loading new prices.
    // A single coalesced pass reattaches evidence; no polling of DOM mutations.
    let queued=false;
    const observer=new MutationObserver(()=>{
      if(queued)return;
      if(observerTargets.every(x=>!x))return;
      const country=selected('analysisCountry'),asset=selected('analysisAsset'),game=selected('analysisGame');
      const search=String(document.getElementById('analysisQuery')?.value||'').toLowerCase().trim();
      const cardExpected=asset!=='BOX'&&(data.some(x=>CARD_TYPES.has(x.kind)&&selectedCountry(country,x.region)&&selectedGame(game,x.game_id)&&(!search||`${x.name} ${x.source_id}`.toLowerCase().includes(search)))||sourceRows(CARD_TYPES,country,game,search).length>0);
      const boxCountry=String(document.querySelector('.box-kb-country.active')?.dataset?.kbCountry||'ALL');
      const boxGame=selected('boxKbGame');
      const prodExpected=data.some(x=>PRODUCT_TYPES.has(x.kind)&&selectedCountry(boxCountry,x.region)&&selectedGame(boxGame,x.game_id))||sourceRows(PRODUCT_TYPES,boxCountry,boxGame).length>0;
      const detached=(cardExpected&&observerTargets[0]&&!observerTargets[0].querySelector('[data-tcg-v45="true"], [data-tcg-v46="true"]')) ||
                     (prodExpected&&observerTargets[1]&&!observerTargets[1].querySelector('[data-tcg-v45="true"], [data-tcg-v46="true"]'));
      if(!detached)return;
      queued=true;
      setTimeout(()=>{queued=false;render();},40);
    });
    for(const target of observerTargets)if(target)observer.observe(target,{childList:true});
    document.addEventListener("tcg-local-images-updated",refresh);
    refresh();setInterval(refresh,90000);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();

/* v4.7: private US-market opportunity research, no purchase action. */
(() => {
  'use strict';
  const base='/api/local-card-images/opportunities';
  const parent=document.getElementById('box12section') || document.querySelector('main.app') || document.body;
  if(document.getElementById('tcgProfitRadarV47'))return;
  const mk=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n;};
  const area=mk('section');area.id='tcgProfitRadarV47';area.setAttribute('aria-label','수익 후보 자동발굴');
  const css=mk('style');css.textContent=`
#tcgProfitRadarV47{background:#fff;border:1px solid #cbd5e1;border-radius:18px;padding:15px;margin:13px 0;color:#172337;box-shadow:0 3px 12px #0f172a0e}
#tcgProfitRadarV47 h2{font-size:19px;margin:0 0 6px}
#tcgProfitRadarV47 .radar-note{font-size:12px;color:#64748b;line-height:1.55;margin:6px 0}
#tcgProfitRadarV47 .radar-controls{display:grid;grid-template-columns:1fr 1fr auto;gap:7px;align-items:end}
#tcgProfitRadarV47 select{padding:11px 8px;border:1px solid #cbd5e1;border-radius:10px;background:white;min-width:0;width:100%;font-size:13px}
#tcgProfitRadarV47 button{background:#1d4ed8;border-radius:11px;font-size:12px;width:auto;padding:11px;margin:0;min-height:44px}
#tcgProfitRadarV47 details{margin-top:10px}#tcgProfitRadarV47 summary{cursor:pointer;font-weight:800;color:#1e40af;padding:8px}
#tcgProfitRadarV47 .radar-items{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:8px;margin-top:9px}
#tcgProfitRadarV47 article{border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc;padding:11px;min-width:0}
#tcgProfitRadarV47 article strong{display:block;font-size:14px;overflow-wrap:anywhere}
#tcgProfitRadarV47 .radar-meta{font-size:11px;color:#475569;margin-top:5px;line-height:1.6}
#tcgProfitRadarV47 .radar-value{font-weight:800;font-size:15px;margin:7px 0;color:#075985}
#tcgProfitRadarV47 a{font-size:12px;color:#1d4ed8}
@media(max-width:440px){#tcgProfitRadarV47 .radar-controls{grid-template-columns:1fr 1fr}#tcgProfitRadarV47 button{grid-column:1/-1;width:100%}}
`;document.head.append(css);
  area.append(mk('h2','💹 카드·BOX 수익 가능성 자동 탐색'));
  area.append(mk('p','30종 게임에서 무료 공개 상품·시리즈·시세 자료를 순차 수집합니다. 가격이 높거나 예상 가격차가 커도 실제 수익을 보장하지 않습니다.','radar-note'));
  const summary=mk('div','무료 시장 자료 수집 상태 확인 중…');summary.className='radar-note';summary.setAttribute('role','status');area.append(summary);
  const controls=mk('div');controls.className='radar-controls';
  const game=mk('select');game.setAttribute('aria-label','자동발굴 게임 필터');game.append(new Option('전체 게임',''));
  const kind=mk('select');kind.setAttribute('aria-label','자동발굴 상품 유형');
  [['','카드·BOX 전체'],['CARD','싱글카드'],['PROMO','프로모'],['BOX','BOX'],['PACK','팩'],['COLLECTION','컬렉션'],['DECK','덱'],['ACCESSORY','액세서리'],['BUNDLE','묶음 상품']].forEach(([id,label])=>kind.append(new Option(label,id)));
  const reload=mk('button','새로고침');reload.type='button';controls.append(game,kind,reload);area.append(controls);
  const details=mk('details');details.open=true;details.append(mk('summary','수집한 카드·상품 후보 보기'));
  const cards=mk('div');cards.className='radar-items';details.append(cards);area.append(details);
  area.append(mk('p','시장가격 ≠ 실제 체결가, 최저 호가 ≠ 확보 가능한 매입가. 수수료·배송·환율·세금·가품·재판 위험은 별도로 확인해야 합니다.','radar-note'));
  parent.before(area);
  let busy=false, lastKey='';
  async function update(){
    if(busy || document.hidden)return;
    busy=true;
    try{
      const query=new URLSearchParams({limit:'60'});if(game.value)query.set('game',game.value);if(kind.value)query.set('kind',kind.value);
      const response=await fetch(base+'?'+query.toString(),{cache:'no-store',credentials:'same-origin'});
      if(!response.ok)throw new Error('HTTP '+response.status);
      const data=await response.json();if(!data.ok||!data.summary||!Array.isArray(data.items))throw new Error('API 형식 오류');
      const s=data.summary;
      summary.textContent=`등록 게임 ${s.registered_games}종 · 시장 출처 연결 ${s.source_games_mapped||0}종 · 누적 상품 ${s.total}건 · 가격자료 ${s.with_market_price}건 · 현재 화면 후보 ${data.items.length}건`;
      if(data.last_run?.errors?.length)summary.textContent+=' · 일부 출처 오류 '+data.last_run.errors.length+'건';
      const sig=JSON.stringify(data.items.map(x=>[x.product_id,x.variant,x.market_price_usd,x.checked_at]));
      if(sig===lastKey)return;lastKey=sig;
      cards.replaceChildren();
      if(!data.items.length){cards.append(mk('p','수집 대기 중입니다. 서버 시작 약 90초 후 첫 실행되며, 이후 약 6시간 간격으로 다음 시리즈를 탐색합니다.'));return;}
      for(const x of data.items){
        const item=mk('article');const tag=mk('small',`${x.game_id} · ${x.kind} · 미국 거래시장 (인쇄판 미확인)`);tag.className='radar-meta';item.append(tag);
        item.append(mk('strong',x.name));
        const name=mk('div',`${x.series} · ${x.variant}${x.rarity?' · '+x.rarity:''}`);name.className='radar-meta';item.append(name);
        const v=mk('div',x.market_price_usd==null?'가격 미확인':`시장 기준 $${Number(x.market_price_usd).toFixed(2)}`);v.className='radar-value';item.append(v);
        if(x.hit_candidate)item.append(mk('div','⭐ 고가·희귀도 기반 HIT 조사 후보 (확정 아님)','radar-meta'));
        if(x.signal==='PRICE_GAP_REVIEW')item.append(mk('div','🔎 최저 호가·시장가 차이 추가 확인 필요 (순이익 아님)','radar-meta'));
        if(x.stale)item.append(mk('div','⚠️ 자료 갱신일 지남','radar-meta'));
        if(x.source_url){const a=mk('a','상품 출처 열기 ↗');a.href=x.source_url;a.target='_blank';a.rel='noopener noreferrer';item.append(a);}
        cards.append(item);
      }
    }catch(e){summary.textContent='시장 자료 확인 보류: '+e.message+' · 기존 카드·BOX 기능은 유지됩니다.';}
    finally{busy=false;}
  }
  game.addEventListener('change',update);kind.addEventListener('change',update);reload.addEventListener('click',update);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)update();});
  setInterval(update,180000);
  fetch('tcg_game_registry.json',{cache:'no-store'}).then(r=>r.json()).then(d=>{
    if(!Array.isArray(d.games))return;
    d.games.forEach(x=>{if(x&&/^[a-z0-9-]{1,64}$/.test(x.id||''))game.append(new Option(x.label_ko||x.id,x.id));});
  }).catch(()=>{});
  update();
})();

/* TCG v4.8: non-destructive launcher and automatic collector summary.
   Legacy nav, market, grading, purchases and image views remain available.
   Never infer a price, edition, actual profit, or inventory ownership. */
(() => {
  'use strict';
  const run=()=>{
    const main=document.querySelector('main.app');
    if(!main||document.getElementById('tcgUnifiedV48'))return;
    const node=(tag,text)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;return e;};
    const wrap=node('section');wrap.id='tcgUnifiedV48';wrap.setAttribute('aria-label','TCG 통합 바로가기');
    const css=node('style');css.textContent=`
#tcgUnifiedV48{position:relative;background:#fff;border:1px solid #dbe5f1;border-radius:20px;padding:13px;margin:8px 0 15px;box-shadow:0 7px 24px #0f172a0a;color:#0f172a}
#tcgUnifiedV48 h2{margin:3px 0;font-size:clamp(19px,3vw,24px);line-height:1.4}
#tcgUnifiedV48 .v48-sub{margin:2px 0 10px;font-size:12px;color:#52647b;line-height:1.55}
#tcgUnifiedV48 .v48-nav{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px}
#tcgUnifiedV48 .v48-nav button{width:100%;margin:0;background:#f3f6fc;border:1px solid #dae5f3;border-radius:12px;color:#18395e;min-height:51px;padding:8px 2px;font-size:clamp(11px,1.8vw,14px);font-weight:800;line-height:1.35;white-space:nowrap;touch-action:manipulation}
#tcgUnifiedV48 .v48-nav button:focus-visible{outline:3px solid #2563eb;outline-offset:1px}
#tcgUnifiedV48 .v48-nav button:first-child{background:#1d4ed8;color:#fff}
#tcgUnifiedV48 .v48-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin-top:11px}
#tcgUnifiedV48 .v48-stat{border:1px solid #e2e8f0;background:#f8fafc;border-radius:13px;padding:9px 7px;min-width:0}
#tcgUnifiedV48 .v48-stat strong{display:block;font-size:clamp(16px,2.5vw,22px);color:#1e40af;font-variant-numeric:tabular-nums}
#tcgUnifiedV48 .v48-stat span{display:block;color:#64748b;font-size:11px;line-height:1.5}
#tcgUnifiedV48 .v48-check{font-size:12px;line-height:1.55;color:#475569;padding-top:8px;margin:0}
#countryAnalysisList,#box12section,#tcgProfitRadarV47,#tcgImageManagementV46{scroll-margin-top:18px}
@media(max-width:400px){#tcgUnifiedV48{padding:11px}#tcgUnifiedV48 .v48-nav{gap:3px}#tcgUnifiedV48 .v48-nav button{font-size:10px;min-height:48px}#tcgUnifiedV48 .v48-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(prefers-reduced-motion:reduce){#tcgUnifiedV48 *{scroll-behavior:auto!important}}
`;document.head.append(css);
    wrap.append(node('h2','🎴 카드·BOX 통합 관리'));
    wrap.append(node('p','카드정보·밀봉상품·수집현황으로 바로 이동합니다. 기존 기능은 삭제하지 않습니다.','v48-sub'));
    const nav=node('div');nav.className='v48-nav';wrap.append(nav);
    const stats=node('div');stats.className='v48-stats';wrap.append(stats);
    const labels=[['게임','30'],['카드사진','–'],['상품사진','–'],['정확연결','–']];
    const valueEls=[];
    for(const [label,initial] of labels){const cell=node('div');cell.className='v48-stat';const strong=node('strong',initial);valueEls.push(strong);cell.append(strong,node('span',label));stats.append(cell);}
    const status=node('p','태블릿 자동수집 상태 확인 중…');status.className='v48-check';status.setAttribute('role','status');wrap.append(status);
    function go(element){if(!element){status.textContent='해당 기능을 아직 찾지 못했습니다. 기능목록에서 확인해 주세요.';return;}
      element.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth',block:'start'});
    }
    function openManaged(id){
      const link=document.querySelector('.feature-shortcut[href="#'+id+'"]');
      const controller=window.TCGFeatureCategoryNav;
      if(typeof controller?.openTarget==='function'&&controller.openTarget(id))return true;
      if(link&&typeof controller?.navigateShortcut==='function')return controller.navigateShortcut(link);
      if(link){link.click();return true;}
      const target=document.getElementById(id);
      if(target&&typeof controller?.showManagedTarget==='function')return controller.showManagedTarget(target);
      return false;
    }
    function backToFullView(){
      if(typeof window.TCGFeatureCategoryNav?.closeFeatureView==='function')window.TCGFeatureCategoryNav.closeFeatureView();
    }
    const destinations=[
      ['홈',()=>{backToFullView();go(document.querySelector('.home-launcher')||document.querySelector('.feature-category-nav')||main);}],
      ['카드정보',()=>{
        openManaged('v14section');
        for(const [id,val] of [['analysisAsset','HIT'],['analysisCountry','ALL'],['analysisGame','ALL']]){
          const s=document.getElementById(id);if(s&&[...s.options].some(o=>o.value===val)){s.value=val;s.dispatchEvent(new Event('change',{bubbles:true}));}}
        if(typeof window.renderCountryAnalysis==='function')window.renderCountryAnalysis();
        go(document.getElementById('v14section')||document.getElementById('countryAnalysisList'));}],
      ['BOX·상품',()=>{openManaged('box12section');go(document.getElementById('box12section'));}],
      ['자동수집',()=>{if(openManaged('tcgImageLibrarySurface')){const manager=document.getElementById('tcgImageManagementV46');if(manager)manager.open=true;go(manager||document.getElementById('tcgImageLibrarySurface'));}else status.textContent='이미지 수집 기능을 준비 중입니다. 기능목록에서 다시 확인해 주세요.';}],
      ['관리',()=>{if(openManaged('tcgImageLibrarySurface')){const d=document.getElementById('tcgImageManagementV46');if(d){d.open=true;go(d);}}else status.textContent='이미지 관리 기능을 준비 중입니다. 기능목록에서 다시 확인해 주세요.';}]
    ];
    for(const [label,cb] of destinations){const button=node('button',label);button.type='button';button.addEventListener('click',cb);nav.append(button);}
    main.insertBefore(wrap,main.firstElementChild);
    async function fetchData(path){const ctl=new AbortController();const tid=setTimeout(()=>ctl.abort(),8000);
      try{const resp=await fetch(path,{cache:'no-store',credentials:'same-origin',signal:ctl.signal});if(!resp.ok)throw Error(String(resp.status));return await resp.json();}finally{clearTimeout(tid);}}
    let busy=false;
    async function refresh(){if(busy||document.hidden)return;busy=true;
      try{const data=await fetchData('/api/local-card-images/catalog-links');if(!data.ok)throw Error('catalog API');
        const s=data.summary||{};valueEls[1].textContent=String(s.image_backed_card_records??'–');valueEls[2].textContent=String(s.image_backed_product_records??'–');valueEls[3].textContent=String(s.auto_linked??'–');
        status.textContent=`보관 이미지 ${s.local_all_photos??'–'}장 · 기존 카드·BOX 자료 ${s.catalog_records_scanned??'–'}건 · 검증된 정확 연결 ${s.auto_linked??0}건. 미연결 이미지는 별도 근거 항목으로 표시됩니다.`;
      }catch(e){status.textContent='수집현황 연결 확인 필요 · 기존 카드·BOX 목록은 유지됩니다.';}
      finally{busy=false;}}
    refresh();document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
    document.addEventListener('tcg-image-auto-update',refresh);setInterval(refresh,90000);
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',run,{once:true});else run();
})();
