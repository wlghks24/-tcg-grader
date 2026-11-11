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
const ctx={URL,el:id=>id==='econCard'?{options:selected}:id==='identityMarketKey'?{value:direct}:null};
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
const rawQuote={platform:'WYYYES',title:'Pikachu S8 SR 025/165 한국판 포켓몬 카드',
 card_name:'Pikachu',card_number:'025/165',card_region:'KR',game:'pokemon',price:18000,
 identity_verified:true,identity_binding_status:'VERIFIED_EXACT',
 identity_set_code:'S8',identity_printing:'SR',
 identity_source_url:'https://www.pokemon-card.com/card-search/details.php/card/12345',
 source_url:'https://wyyyes.com/category/pokemon-card/6502248',
 collected_at:new Date().toISOString()};
function quote(row,name='Pikachu',number='025/165',region='KR'){
 ctx.quoteRow=row;ctx.quoteName=name;ctx.quoteNumber=number;ctx.quoteRegion=region;
 return vm.runInContext('quoteScore(quoteRow,quoteName,quoteNumber,quoteRegion)',ctx,{timeout:1000});
}
assert.ok(quote(rawQuote)>=25,'exact identity can match');
assert.ok(quote({...rawQuote,game:'Pokémon'})>=25,'supplier Pokémon label canonicalized');
ctx.window.tcgIdentityGame='onepiece';
assert.ok(quote({...rawQuote,game:'ONE PIECE',
 identity_source_url:'https://en.onepiece-cardgame.com/cardlist/?series=569102'})>=25,
 'supplier ONE PIECE label canonicalized with matching official provenance');
ctx.window.tcgIdentityGame='naruto';
assert.equal(quote({...rawQuote,game:'NARUTO'}),-999,'Naruto quote has no reviewed official catalog host');
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
assert.equal(quote({...rawQuote,identity_verified:false}),-999,'unverified quote held');
assert.equal(quote({...rawQuote,identity_verified:null}),-999,'missing approval held');
assert.equal(quote({...rawQuote,identity_binding_status:'HOLD_UNVERIFIED'}),-999,'HOLD cannot show price');
assert.equal(quote({...rawQuote,identity_set_code:''}),-999,'missing reviewed set');
assert.equal(quote({...rawQuote,identity_printing:''}),-999,'missing reviewed printing');
assert.equal(quote({...rawQuote,identity_source_url:'https://pokemon-card.com.evil.invalid/card'}),-999,'official host lookalike');
assert.equal(quote({...rawQuote,identity_source_url:'https://www.pokemon-card.com@evil.invalid/card'}),-999,'official URL credentials spoof');
assert.equal(quote({...rawQuote,source_url:'https://wyyyes.com.evil.invalid/category/1'}),-999,'supplier URL lookalike');
assert.equal(quote({...rawQuote,source_url:'http://wyyyes.com/category/pokemon-card/1'}),-999,'supplier HTTP');
assert.equal(quote({...rawQuote,source_url:'https://wyyyes.com/not-a-product/1'}),-999,'non-product URL');
assert.equal(quote({...rawQuote,collected_at:'2020-01-01T00:00:00Z'}),-999,'stale offline quote');
assert.equal(quote({...rawQuote,collected_at:'2099-01-01T00:00:00Z'}),-999,'future timestamp');
assert.equal(quote({...rawQuote,collected_at:''}),-999,'no timestamp');
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
