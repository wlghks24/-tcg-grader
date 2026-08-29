(()=>{
'use strict';
const $=id=>document.getElementById(id);
const GAME_MAP={pokemon:'Pokémon',onepiece:'ONE PIECE',naruto:'NARUTO'};
let lastSig='';
function normRegion(v){return ['KR','JP','US'].includes(v)?v:'ALL'}
function gameValue(){return GAME_MAP[String(window.tcgIdentityGame||'').toLowerCase()]||'ALL'}
function setValue(id,value){const el=$(id);if(!el)return false;if([...el.options||[]].some(o=>o.value===value))el.value=value;else if(el.tagName!=='SELECT')el.value=value;return true}
function ensureStatus(){
 if($('market12AutoStatus'))return;
 const section=$('market12section');if(!section)return;
 const n=document.createElement('div');n.id='market12AutoStatus';n.className='market12-auto-status';n.innerHTML='<b>🤖 카드측정 자동연결</b><span>카드명·번호 인식 후 시장·게임·검색어를 자동 설정하고 시세를 조회합니다. BOX는 기존 수동검색을 사용합니다.</span>';
 const out=$('market12out');section.insertBefore(n,out||section.firstChild);
}
function run(force=false){
 ensureStatus();
 const name=String($('identityCardName')?.value||'').trim();
 const number=String($('identityCardNumber')?.value||'').trim();
 const region=normRegion($('identityRegion')?.value||'');
 const game=gameValue();
 if(!name&&!number)return;
 const query=[name,number].filter(Boolean).join(' ').trim();
 const sig=[query,region,game].join('|');
 if(!force&&sig===lastSig)return;
 lastSig=sig;
 setValue('market12',region);
 setValue('asset12','HIT');
 setValue('v12Game',game);
 if($('query12'))$('query12').value=query;
 const status=$('market12AutoStatus');
 if(status)status.dataset.state='active';
 // Keep other card-only search centers synchronized without forcing their manual searches.
 setValue('v13Asset','HIT');setValue('v13Game',game);
 if($('v13q'))$('v13q').value=query;
 setValue('analysisAsset','HIT');setValue('analysisGame',game);if($('analysisQuery'))$('analysisQuery').value=query;
 setValue('tradeAsset','HIT');setValue('tradeGame',game);if($('tradeQuery'))$('tradeQuery').value=query;
 // v12 is the primary pre-grade market lookup; execute it automatically.
 requestAnimationFrame(()=>$('search12')?.click());
}
function boot(){ensureStatus();setInterval(()=>run(false),500);['identityCardName','identityCardNumber','identityRegion'].forEach(id=>$(id)?.addEventListener('input',()=>run(true)));window.tcgAutoMarketCenter=Object.freeze({refresh:()=>run(true)})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
