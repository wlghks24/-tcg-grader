'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('index.html','utf8'),elements=new Map();
function el(id){if(!elements.has(id))elements.set(id,{id,value:'ALL',dataset:{},innerHTML:'',textContent:'',hidden:false,selectedOptions:[]});return elements.get(id);}
const tabs=['releasePanel','promoPanel','purchasePanel'].map(topPanel=>({dataset:{topPanel},active:false,attrs:{},classList:{toggle(k,v){this.active=v}},setAttribute(k,v){this.attrs[k]=v}}));
const panels=tabs.map(t=>el(t.dataset.topPanel));
const c=vm.createContext({console,URL,Date,INFO_ARCHIVE_GRACE_DAYS:5,document:{getElementById:el,querySelectorAll:s=>s==='[data-top-panel]'?tabs:s==='.top-info-panel'?panels:[]},releaseData:{items:[]},promoData:{items:[]},supplementaryData:{items:[]},socialEventData:{items:[]}});
for(const name of ['escapeDisplayText','safeExternalUrl','localDateOnly','addLocalDays','releaseLifecycle','promoLifecycle','infoGameKey','trustedPromoOfficialUrl']){
 const line=html.split(/\r?\n/).find(x=>x.startsWith('function '+name+'('));assert.ok(line,name);vm.runInContext(line,c);
}
for(const name of ['releaseDayInfo','boxKbCountryMatches','updateInfoGameOptions','resetInfoFilters','selectInfoPanel','renderReleases','feedDisplayText','normalizedSupplementaryItems','normalizedSocialEventItems','renderPromos']){
 const match=html.match(new RegExp('^function '+name+'\\([^\\n]*\\)\\{[\\s\\S]*?^\\}','m'));assert.ok(match,name);vm.runInContext(match[0],c);
}
const run=s=>vm.runInContext(s,c),count=id=>(el(id).innerHTML.match(/<article\b/g)||[]).length;
assert.equal(run('infoGameKey("constructor")'),'constructor');assert.equal(run('infoGameKey({})'),'');
for(const id of ['releaseLifecycle','promoLifecycle'])el(id).value='ALL';
c.releaseData.items=Array.from({length:85},(_,i)=>({game:i%2?'Pokemon':'디지몬 카드',name:'release '+i,region:i%2?'KR':'GLOBAL',release_date:'2099-01-01',source:'https://www.pokemon-card.com/'}));
run('renderReleases()');assert.equal(count('releaseList'),40);assert.equal(el('releaseMore').hidden,false);assert.match(el('releaseGame').innerHTML,/디지몬 카드/);
el('releaseMore').dataset.limit='80';run('renderReleases()');assert.equal(count('releaseList'),80);
el('releaseGame').value='포켓몬 카드';el('releaseFilter').value='KR';run('renderReleases()');assert.equal(count('releaseList'),40);assert.equal(el('releaseMore').dataset.limit,'40');assert.match(el('releaseSummary').textContent,/조건 일치 42건/);
el('releaseGame').value='디지몬 카드';el('releaseFilter').value='GLOBAL';run('renderReleases()');assert.equal(count('releaseList'),40);assert.match(el('releaseSummary').textContent,/조건 일치 43건/);
// Reset only this panel; other-panel choices survive.
el('promoFilter').value='JP';run('resetInfoFilters("release")');assert.equal(el('releaseGame').value,'ALL');assert.equal(el('releaseLifecycle').value,'current');assert.equal(el('promoFilter').value,'JP');
c.promoData.items=Array.from({length:82},(_,i)=>({game:i%2?'디지몬 카드':'Pokemon',region:i%2?'ASIA':'KR',category:i%2?'collaboration':'promo',name_ko:'promo '+i,source:'https://www.pokemon-card.com/event/'+i,start_date:'2099-01-01',end_date:'2099-01-02',dates:['2099-01-01','2099-01-02']}));
el('promoFilter').value='ALL';run('renderPromos()');assert.equal(count('promoList'),40);assert.match(el('promoGame').innerHTML,/디지몬 카드/);
el('promoMore').dataset.limit='80';run('renderPromos()');assert.equal(count('promoList'),80);
el('promoGame').value='디지몬 카드';el('promoFilter').value='ASIA';el('promoType').value='collaboration';el('promoSourceGrade').value='confirmed';run('renderPromos()');assert.equal(count('promoList'),40);assert.match(el('promoSummary').textContent,/조건 일치 41건/);
el('promoType').value='movie';run('renderPromos()');assert.equal(count('promoList'),0);assert.equal(el('promoMore').hidden,true);
run('resetInfoFilters("promo")');assert.equal(el('promoFilter').value,'ALL');assert.equal(el('promoType').value,'ALL');assert.equal(el('promoLifecycle').value,'current');assert.equal(count('promoList'),40);
assert.equal(run('selectInfoPanel("promoPanel")'),true);assert.equal(el('promoPanel').hidden,false);assert.equal(el('releasePanel').hidden,true);assert.equal(tabs[1].attrs['aria-pressed'],'true');assert.equal(run('selectInfoPanel("missingPanel")'),false);assert.equal(el('promoPanel').hidden,false);
// The last actual event date controls archive state even if feed dates are reversed.
assert.equal(run('promoLifecycle({dates:["2099-01-01","2000-01-01"]})'),'current');
assert.equal(run('promoLifecycle({dates:["2000-02-01","2000-01-01"]})'),'archive');
c.socialEventData.items=[{game:'Pokemon',region:'KR',title:'No explicit event date',published_at:'2099-01-01',dates:[],source:'https://x.com/example/status/1'}];
assert.equal(run('normalizedSocialEventItems()[0].start_date'),null);
console.log('PASS: filter intersections, game/country coverage, paging, reset isolation, safe tab targets and event-date ordering');
