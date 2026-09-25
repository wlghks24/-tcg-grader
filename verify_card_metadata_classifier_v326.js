const fs=require('fs'),vm=require('vm');vm.runInThisContext(fs.readFileSync('card_metadata_classifier_v326.js','utf8'));const a=globalThis.TCGCardMetadata;
function ok(v,m){if(!v)throw new Error(m)}
let c=a.classify({game:'pokemon',region:'US',card_name:'Pikachu ex SAR',card_number:'PAL 185/193'});ok(c.game==='pokemon'&&c.region==='US'&&c.set_code==='PAL'&&c.rarity==='SAR'&&c.generation===9,'pokemon metadata');
let p=a.bindPrice(c,{game:'pokemon',region:'JP',card_name:'Pikachu ex SAR',card_number:'PAL 185/193'});ok(!p.safe&&p.conflicts.includes('region'),'cross-edition price blocked');
p=a.bindPrice(c,{game:'pokemon',region:'US',card_name:'Pikachu ex SAR',card_number:'PAL 185/193'});ok(p.safe,'exact pokemon variant price');
c=a.classify({game:'onepiece',region:'JP',card_name:'Ace Manga Parallel SEC',card_number:'OP13-119'});ok(c.set_code==='OP-13'&&c.rarity==='SEC'&&c.variant==='manga_parallel'&&c.generation===null,'onepiece classification');
p=a.bindPrice(c,{game:'onepiece',region:'JP',card_name:'Ace SEC',card_number:'OP13-119'});ok(!p.safe&&p.conflicts.includes('variant'),'parallel/base price blocked');
c=a.classify({game:'naruto',region:'US',card_name:'Chakra Card Promo',card_number:'CP-001'});ok(c.set_code==='CP-001'&&c.variant==='promo'&&c.generation===null,'naruto classification');
c=a.classify({game:'pokemon',region:'US',card_name:'Mega card',card_number:'MEG 001'});ok(c.generation===null&&c.era==='MEGA','mega no invented generation');
c=a.classify({game:'pokemon',region:'UNKNOWN',card_name:'Pikachu',card_number:'025'});p=a.bindPrice(c,{game:'pokemon',region:'US',card_name:'Pikachu',card_number:'025'});ok(!p.safe,'unknown edition price blocked');
console.log('card metadata classifier v326: PASS');