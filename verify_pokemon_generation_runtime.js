#!/usr/bin/env node
'use strict';
const fs=require('fs');
const vm=require('vm');

global.window={};
global.document={readyState:'loading',addEventListener() {},getElementById(){return null;}};
global.localStorage={getItem(){return null;},setItem(){}};
global.Option=function(){};

const source=fs.readFileSync('card_identity_recognition.js','utf8');
vm.runInThisContext(source,{filename:'card_identity_recognition.js'});
const api=global.window.TCGPokemonGeneration;
if(!api||typeof api.infer!=='function')throw new Error('generation API missing');
if(typeof api.inferRegion!=='function')throw new Error('edition inference API missing');

function eq(actual,expected,label){
  if(actual!==expected)throw new Error(`${label}: expected=${expected} actual=${actual}`);
}
function ok(value,label){if(!value)throw new Error(label)}

let r=api.infer({game:'pokemon',card_number:'SV8A217',ocr_text:'©2024'});
eq(r.generation,9,'SV generation');eq(r.series,'스칼렛&바이올렛','SV series');eq(r.expansion_code,'SV8A','SV code');eq(r.confidence_level,'high','SV confidence');

r=api.infer({game:'pokemon',card_number:'S12A260'});
eq(r.generation,8,'Sword Shield generation');eq(r.series,'소드&실드','Sword Shield series');eq(r.expansion_code,'S12A','Sword Shield code');

r=api.infer({game:'pokemon',card_number:'SM1M065/060'});
eq(r.generation,7,'SM generation');eq(r.series,'썬&문','SM series');eq(r.expansion_code,'SM1M','SM code');

r=api.infer({game:'pokemon',ocr_text:'REGULATION MARK H'});
eq(r.generation,null,'reg H must not invent generation');eq(r.regulation_mark,'H','reg H mark');eq(r.status,'context_only','reg H context status');eq(r.confidence_level,'context','reg H context confidence');ok(/세대 번호로 변환하지/.test(r.note),'regulation must remain context only');

r=api.infer({game:'pokemon',ocr_text:'REGULATION MARK J'});
eq(r.generation,null,'reg J must not invent generation');eq(r.status,'context_only','reg J context status');eq(r.regulation_mark,'J','reg J mark');ok(/레귤레이션 J/.test(r.series),'reg J remains regulation context');

r=api.infer({game:'pokemon',card_number:'M5114'});
eq(r.generation,null,'MEGA series must not invent generation');eq(r.series,'MEGA 시리즈','MEGA series');eq(r.expansion_code,'M5','MEGA set code');

r=api.infer({game:'pokemon',card_number:'PAL185/193'});
eq(r.generation,9,'English PAL generation');eq(r.expansion_code,'PAL','English PAL code');eq(r.set_region,'US','English PAL region');

r=api.infer({game:'pokemon',ocr_text:'MEG 060/132 Pikachu ex'});
eq(r.generation,null,'English MEGA must not invent generation');eq(r.series,'MEGA Evolution 시리즈','English MEGA series');eq(r.expansion_code,'MEG','English MEGA code');eq(r.set_region,'US','English MEGA region');

r=api.infer({game:'pokemon',ocr_text:'Mega Greninja ex CRI 22'});
eq(r.generation,null,'Chaos Rising must not invent generation');eq(r.series,'MEGA Evolution 시리즈','Chaos Rising series');eq(r.expansion_code,'CRI','Chaos Rising code');

r=api.infer({game:'pokemon',ocr_text:'Pitch Black PBL 79'});
eq(r.generation,null,'Pitch Black must not invent generation');eq(r.expansion_code,'PBL','Pitch Black code');

r=api.infer({game:'pokemon',ocr_text:'©2026 Pokémon',region:'US'});
eq(r.generation,null,'2026 year-only evidence must not invent generation');eq(r.generation_hint,null,'2026 transition era must not invent generation hint');eq(r.status,'context_only','2026 year-only context status');eq(r.confidence_level,'context','2026 year-only confidence');

r=api.infer({game:'pokemon',ocr_text:'©2021 Pokémon'});
eq(r.generation,null,'year-only evidence must not invent generation');eq(r.generation_hint,8,'year-only era hint');eq(r.status,'context_only','year-only context status');eq(r.confidence_level,'context','year-only context confidence');

r=api.infer({game:'pokemon',ocr_text:'©2004 Pokémon'});
eq(r.status,'legacy','legacy status');eq(r.generation,null,'legacy must not invent exact generation');

r=api.infer({game:'pokemon',ocr_text:'PIKACHU 25/102'});
eq(r.status,'unknown','unknown evidence status');eq(r.generation,null,'unknown must not invent generation');

r=api.infer({game:'onepiece',card_number:'OP13-007'});
eq(r.status,'not_applicable','non-pokemon status');eq(r.generation,null,'non-pokemon generation');

let region=api.inferRegion('포켓몬 카드 블래키 ex');eq(region.region,'KR','Hangul edition');ok(region.confidence>=0.9,'Hangul confidence');
region=api.inferRegion('ポケモンカード ミミッキュ');eq(region.region,'JP','Kana edition');ok(region.confidence>=0.9,'Kana confidence');
region=api.inferRegion('Pokémon TCG PAL 185/193');eq(region.region,'US','English set edition');ok(region.confidence>=0.9,'English set confidence');
region=api.inferRegion('Pikachu 25/102');eq(region.region,'UNKNOWN','generic Latin text must not invent edition');
region=api.inferRegion('2026 Japanese Pokémon card Pikachu');eq(region.region,'JP','embedded Japanese label');ok(region.basis.includes('explicit_region_label'),'embedded label basis');

region=api.inferRegion('포켓몬 카드 ポケモン カード');eq(region.region,'UNKNOWN','mixed strong scripts must not invent edition');eq(region.basis,'edition_evidence_conflict','mixed script basis');ok(region.conflict===true,'mixed script conflict flag');

r=api.infer({game:'pokemon',card_number:'PAL185/193',region:'JP'});
eq(r.status,'conflict','English set code vs Japanese edition must conflict');eq(r.generation,null,'edition conflict must not invent generation');

r=api.infer({game:'pokemon',card_number:'PAL185/193',region:'US',regulation_mark:'F'});
eq(r.status,'estimated','regulation context must not override exact set generation');eq(r.generation,9,'set code remains generation evidence');eq(r.context_evidence_count,1,'regulation recorded as context');

r=api.infer({game:'pokemon',card_number:'PAL185/193',region:'US',ocr_text:'©2020 Pokémon'});
eq(r.status,'conflict','set code vs impossible copyright year must conflict');eq(r.generation,null,'year conflict must fail closed');

r=api.infer({game:'pokemon',card_number:'PAL185/193',region:'US',regulation_mark:'H',ocr_text:'©2024 Pokémon'});
eq(r.generation,9,'set+year generation');eq(r.evidence_count,2,'only set and year count as generation evidence');eq(r.context_evidence_count,1,'regulation is context evidence');ok(r.basis.some(x=>x.includes('©/제작연도')),'year evidence retained');

eq(api.version,'v328','generation runtime version');
console.log('Pokémon generation runtime v328: PASS');
