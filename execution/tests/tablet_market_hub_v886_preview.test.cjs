'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.resolve(__dirname,'../tablet_market_hub_v886_preview.html'),'utf8');

class Element {
  constructor(id='') {
    this.id=id;this.value='ALL';this.style={};this.dataset={};this.children=[];
    this.listeners={};this.attributes={};this.hidden=false;this.textContent='';
    const classes=new Set(id==='page-home'?['active']:[]);
    this.classList={contains:x=>classes.has(x),toggle:(x,on)=>{if(on)classes.add(x);else classes.delete(x)}};
  }
  addEventListener(name,listener){this.listeners[name]=listener}
  setAttribute(k,v){this.attributes[k]=String(v)}
  removeAttribute(k){delete this.attributes[k]}
  append(...children){this.children.push(...children)}
  replaceChildren(...children){this.children=children}
  dispatch(name){const fn=this.listeners[name];assert.equal(typeof fn,'function',this.id+':'+name);fn({preventDefault(){},target:this})}
}
function boot() {
  const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]),els=new Map(ids.map(x=>[x,new Element(x)]));
  for(const x of ['marketGame','marketRegion','marketKind'])els.get(x).value='ALL';
  els.get('homeQuery').value='';els.get('marketQuery').value='';
  const pages=['home','market','scanner','news','portfolio'].map(x=>els.get('page-'+x));
  const dock=pages.map(p=>{const e=new Element();e.dataset.page=p.id.slice(5);return e});
  const document={
    getElementById:x=>els.get(x)||null,
    createElement:t=>{const e=new Element();e.tag=t;return e},
    createTextNode:value=>({textContent:String(value)}),
    addEventListener(name,fn){this.listeners[name]=fn},
    listeners:{},
    querySelectorAll:sel=>sel==='.page'?pages:sel==='.dock button'?dock:sel==='#homeGames button'?els.get('homeGames').children:[],
  };
  const prices={entries:{
    'KR|계승되는 의지|BOX':{game:'ONE PIECE',display:'₩50,000',source_date:'2026-10-31'},
    'CN-S|英雄|BOX':{game:'Pokémon',display:'¥100',source_date:'2026-10-30'},
    'CN-T|英雄|BOX':{game:'Pokémon',display:'NT$200',source_date:'2026-10-30'},
    'JP|受け継がれる意志|BOX':{game:'ONE PIECE',display:'¥9,000',source_date:'2026-10-28'}
  }};
  const watch={items:[
    {region:'KR',game:'ONE PIECE',asset:'BOX',name:'계승되는 의지',native:'계승되는 의지',product_code:'OPK-13'},
    {region:'JP',game:'ONE PIECE',asset:'BOX',name:'受け継がれる意志',native:'受け継がれる意志',product_code:'OP-13'},
    {region:'CN-S',game:'Pokémon',asset:'BOX',name:'英雄',product_code:'CN001'},
    {region:'CN-T',game:'Pokémon',asset:'BOX',name:'英雄',product_code:'TW001'}
  ]};
  const data={'market_prices.json':prices,'market_watch.json':watch,
    'catalog_image_manifest.json':{items:{}},'releases.json':{items:[]},
    '/api/local-card-images/cross-status':{summary:{auto_linked:0,local_all_photos:0,catalog_records_scanned:4}}};
  const context={document,URL,AbortController,setTimeout,clearTimeout,
    fetch:async url=>({ok:Object.prototype.hasOwnProperty.call(data,url),status:404,
      json:async()=>data[url]})};
  context.window=context;context.scrollTo=()=>{};
  vm.createContext(context);
  const match=html.match(/<script>([\s\S]*?)<\/script>/g);
  assert.equal(match.length,1,'single script keeps original CSP structure');
  vm.runInContext(match[0].slice('<script>'.length,-'</script>'.length),context,{timeout:1500});
  return {els,document,context};
}
async function loaded(){
  const app=boot();
  for(let i=0;i<60 && app.els.get('apiDot').style.background!=='#32d39a';i++)
    await new Promise(resolve=>setTimeout(resolve,5));
  assert.equal(app.els.get('apiDot').style.background,'#32d39a','local fixture data loaded');
  return app;
}
test('navigation targets are accurate; game pill flows through market dock',async()=>{
  const {els,context,document}=await loaded();
  assert.match(html,/<button class="tile orange" data-page="market"[^>]*>[\s\S]*?카드 시세확인/);
  const buttons=els.get('homeGames').children;
  assert.equal(buttons.length,4);
  buttons.find(b=>b.dataset.game==='ONE PIECE').dispatch('click');
  assert.equal(els.get('marketGame').value,'ONE PIECE');
  const action={dataset:{page:'market'}};
  document.listeners.click({target:{closest:()=>action}});
  assert.equal(els.get('page-market').classList.contains('active'),true);
  assert.equal(els.get('marketItems').children.length,2,'only two One Piece boxes');
  context.TCGReferenceHubV881.go('home');
  assert.equal(els.get('page-home').classList.contains('active'),true);
});
test('China unified select returns two editions without collapsing them',async()=>{
  const {els}=await loaded();
  assert.match(html,/<option value="CN">중국판 전체<\/option>/);
  els.get('marketGame').value='Pokémon';els.get('marketGame').dispatch('change');
  els.get('marketRegion').value='CN';els.get('marketRegion').dispatch('change');
  assert.equal(els.get('marketItems').children.length,2);
  els.get('marketRegion').value='CN-S';els.get('marketRegion').dispatch('change');
  assert.equal(els.get('marketItems').children.length,1);
  els.get('marketRegion').value='CN-T';els.get('marketRegion').dispatch('change');
  assert.equal(els.get('marketItems').children.length,1);
});
test('product-code and multilingual tokens drive real result list',async()=>{
  const {els,context}=await loaded();
  els.get('marketQuery').value='원피스 한국판 OPK-13';
  context.TCGReferenceHubV881.go('market');
  assert.equal(els.get('marketItems').children.length,1);
  els.get('marketQuery').value='포켓몬 중국판';
  els.get('marketSearch').dispatch('submit');
  assert.equal(els.get('marketItems').children.length,2);
});
