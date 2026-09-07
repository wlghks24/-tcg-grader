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
eq(r.generation,9,'reg H generation');eq(r.regulation_mark,'H','reg H mark');eq(r.confidence_level,'medium','reg H confidence');

r=api.infer({game:'pokemon',ocr_text:'REGULATION MARK J'});
eq(r.generation,9,'reg J generation');ok(/MEGA/.test(r.series),'reg J series should identify current MEGA era');

r=api.infer({game:'pokemon',card_number:'M5114'});
eq(r.generation,9,'MEGA generation');eq(r.series,'MEGA 시리즈','MEGA series');eq(r.expansion_code,'M5','MEGA set code');

r=api.infer({game:'pokemon',ocr_text:'©2021 Pokémon'});
eq(r.generation,8,'year fallback generation');eq(r.confidence_level,'low','year fallback confidence');

r=api.infer({game:'pokemon',ocr_text:'©2004 Pokémon'});
eq(r.status,'legacy','legacy status');eq(r.generation,null,'legacy must not invent exact generation');

r=api.infer({game:'pokemon',ocr_text:'PIKACHU 25/102'});
eq(r.status,'unknown','unknown evidence status');eq(r.generation,null,'unknown must not invent generation');

r=api.infer({game:'onepiece',card_number:'OP13-007'});
eq(r.status,'not_applicable','non-pokemon status');eq(r.generation,null,'non-pokemon generation');

console.log('Pokémon generation runtime v207: PASS');
