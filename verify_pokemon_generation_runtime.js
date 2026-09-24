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
eq(r.generation,9,'reg H generation');eq(r.regulation_mark,'H','reg H mark');eq(r.confidence_level,'medium','reg H confidence');ok(/보조/.test(r.note),'regulation must be advisory');

r=api.infer({game:'pokemon',ocr_text:'REGULATION MARK J'});
eq(r.generation,9,'reg J generation');ok(/MEGA/.test(r.series),'reg J series should identify current MEGA era');

r=api.infer({game:'pokemon',card_number:'M5114'});
eq(r.generation,9,'MEGA generation');eq(r.series,'MEGA 시리즈','MEGA series');eq(r.expansion_code,'M5','MEGA set code');

r=api.infer({game:'pokemon',card_number:'PAL185/193'});
eq(r.generation,9,'English PAL generation');eq(r.expansion_code,'PAL','English PAL code');eq(r.set_region,'US','English PAL region');

r=api.infer({game:'pokemon',ocr_text:'MEG 060/132 Pikachu ex'});
eq(r.generation,9,'English MEGA generation');eq(r.series,'MEGA 시리즈','English MEGA series');eq(r.expansion_code,'MEG','English MEGA code');eq(r.set_region,'US','English MEGA region');

r=api.infer({game:'pokemon',ocr_text:'©2021 Pokémon'});
eq(r.generation,8,'year fallback generation');eq(r.confidence_level,'low','year fallback confidence');

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

eq(api.version,'v302','generation runtime version');
console.log('Pokémon generation runtime v302: PASS');
