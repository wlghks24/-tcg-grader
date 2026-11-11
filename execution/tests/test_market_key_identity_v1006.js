'use strict';
// Production JS exact-card market link fixtures, read-only and offline.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'..','..','grade_market_flow.js'),'utf8');
function section(start,end){
 const first=source.indexOf(start),last=source.indexOf(end,first+start.length);
 assert.ok(first>=0&&last>first,'missing production declaration: '+start);
 return source.slice(first,last);
}
let selected=[],direct='';
const ctx={el:id=>id==='econCard'?{options:selected}:id==='identityMarketKey'?{value:direct}:null};
vm.createContext(ctx);
vm.runInContext([
 section('const norm=s=>','const money='),
 section('function editionCode(','function editionLabel('),
 section('function marketKeyEdition(','function quoteTypeLabel('),
 section('function marketOptionMatches(','function applyIdentity('),
].join('\n'),ctx,{timeout:3000});
const find=(name,number,region)=>vm.runInContext(
 'findMarketKey('+[name,number,region].map(JSON.stringify).join(',')+')',ctx,{timeout:1000});
const item=(value,textContent)=>({value,textContent});
function list(items,confirmed=''){selected=items;direct=confirmed}
list([item('KR|Pikachu 112/100|HIT','Pikachu 112/100 · KR')]);
assert.equal(find('Pikachu','12/100','KR'),'');
assert.equal(find('Pikachu','112/100','KR'),selected[0].value);
list(selected,selected[0].value);
assert.equal(find('Pikachu','12/100','KR'),'','stale confirmed key must not bypass exact number');
assert.equal(find('Pikachu','','KR'),'','unknown card number: no automatic sale');
assert.equal(find('','112/100','KR'),'','name missing: no automatic sale');
assert.equal(find('Pikachu','112/100','UNKNOWN'),'','unknown edition');
assert.equal(find('Pikachu','112/100','JP'),'','wrong edition');
list([...selected,item('KR|Pikachu 12/100|HIT','Pikachu 12/100 · KR')]);
assert.equal(find('Pikachu','12/100','KR'),selected[1].value);
assert.equal(find('Pikachu','112/100','KR'),selected[0].value);
assert.equal(find('Pikachu','12/1000','KR'),'','denominator collision');
assert.equal(find('Pikachu','012/100','KR'),'','leading-zero collision');
list([...selected,item('KR|Pikachu V 12/100|HIT','Pikachu V 12/100 · KR')]);
assert.equal(find('Pikachu','12/100','KR'),'','same number multiple printings: hold');
list(selected,selected[1].value);
assert.equal(find('Pikachu','12/100','KR'),'','stale direct selection must not override multiple printings');
list([item('JP|블래키ex SAR [SV8a 217/187]|HIT','블래키ex · JP')]);
assert.equal(find('블래키ex','SV8a 217/187','JP'),selected[0].value);
assert.equal(find('블래키ex','SV8b 217/187','JP'),'','set mismatch');
list([item('KR|릴리에 SM1M 065/060|HIT','릴리에 Full Art 065/060 · KR')]);
assert.equal(find('릴리에','SM1M 065/060','KR'),selected[0].value);
assert.equal(find('릴리에','65/060','KR'),'','number truncation');
list([item('JP|창해의 칠걸 일본판 OP14-009|HIT','Trafalgar Law [Alternate Art] · JP')]);
assert.equal(find('Trafalgar Law','OP14-009','JP'),selected[0].value);
assert.equal(find('Trafalgar Law','009','JP'),'','set suffix collision');
// Run real production WYYYES quote matcher with optional metadata unavailable.
ctx.window={tcgIdentityGame:'pokemon'};
ctx.platformMarket={platform_quotes:{WYYYES:[]}};
vm.runInContext(section('function quoteScore(','function renderPlatformQuotes('),ctx,{timeout:3000});
const rawQuote={platform:'WYYYES',title:'Pikachu 025/165',card_name:'Pikachu',card_number:'025/165',card_region:'KR',game:'pokemon',price:18000};
function quote(row,name='Pikachu',number='025/165',region='KR'){
 ctx.quoteRow=row;ctx.quoteName=name;ctx.quoteNumber=number;ctx.quoteRegion=region;
 return vm.runInContext('quoteScore(quoteRow,quoteName,quoteNumber,quoteRegion)',ctx,{timeout:1000});
}
assert.ok(quote(rawQuote)>=25,'exact identity can match');
assert.ok(quote({...rawQuote,game:'Pokémon'})>=25,'supplier Pokémon label canonicalized');
ctx.window.tcgIdentityGame='onepiece';
assert.ok(quote({...rawQuote,game:'ONE PIECE'})>=25,'supplier ONE PIECE label canonicalized');
ctx.window.tcgIdentityGame='naruto';
assert.ok(quote({...rawQuote,game:'NARUTO'})>=25,'supplier NARUTO label canonicalized');
ctx.window.tcgIdentityGame='pokemon';
assert.equal(quote({...rawQuote,card_name:'Raichu'}),-999,'wrong name same number');
assert.equal(quote({...rawQuote,card_name:'Pikachu V'}),-999,'wrong variant');
assert.equal(quote({...rawQuote,card_name:''}),-999,'missing name');
assert.equal(quote({...rawQuote,game:'one_piece'}),-999,'wrong game');
assert.equal(quote({...rawQuote,game:''}),-999,'missing game');
assert.equal(quote({...rawQuote,card_region:'JP'}),-999,'wrong edition');
assert.equal(quote({...rawQuote,card_number:'125/165'}),-999,'wrong number');
assert.equal(quote({...rawQuote,card_number:''}),-999,'missing number');
assert.equal(quote(rawQuote,'Pikachu',''),-999,'request lacks number');
assert.equal(quote(rawQuote,'','025/165'),-999,'request lacks name');
assert.equal(quote({...rawQuote,price:0}),-999,'zero price');
assert.equal(quote({...rawQuote,price:Infinity}),-999,'non-finite price');
ctx.window.tcgIdentityGame='';
assert.equal(quote(rawQuote),-999,'unknown requested game');
ctx.window.tcgIdentityGame='pokemon';
ctx.platformMarket.platform_quotes.WYYYES=[{...rawQuote,card_name:'Raichu'},{...rawQuote,game:'one_piece'},rawQuote,{...rawQuote,card_number:'125/165'},{...rawQuote,price:0}];
const matched=vm.runInContext("matchingPlatformQuotes('Pikachu','025/165','KR')",ctx,{timeout:1000});
assert.equal(matched.length,1,'only exact quote survives');
assert.equal(matched[0].card_name,'Pikachu');
ctx.window.TCGCardMetadata={classify:()=>({}),bindPrice:()=>({safe:false})};
assert.equal(quote(rawQuote),-999,'metadata veto remains authoritative');
console.log('V1006 market-key and WYYYES full identity tests PASS');
