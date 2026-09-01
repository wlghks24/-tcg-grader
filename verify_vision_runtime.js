'use strict';
const assert=require('assert');
const vision=require('./grading_vision_engine.js');

function image(width=700,height=640,color=[25,28,32]){
  const data=new Uint8ClampedArray(width*height*4);
  for(let i=0;i<data.length;i+=4){data[i]=color[0];data[i+1]=color[1];data[i+2]=color[2];data[i+3]=255}
  return {width,height,data};
}
function setPixel(im,x,y,color){if(x<0||x>=im.width||y<0||y>=im.height)return;const i=(y*im.width+x)*4;im.data[i]=color[0];im.data[i+1]=color[1];im.data[i+2]=color[2];im.data[i+3]=255}
function fill(im,x0,y0,x1,y1,color,texture=0){
  for(let y=Math.max(0,y0);y<Math.min(im.height,y1);y++)for(let x=Math.max(0,x0);x<Math.min(im.width,x1);x++){
    const delta=texture?((x*17+y*31)%texture)-Math.floor(texture/2):0;
    setPixel(im,x,y,color.map(value=>Math.max(0,Math.min(255,value+delta))));
  }
}
function line(im,x0,y0,x1,y1,color,thickness=1){
  const steps=Math.max(Math.abs(x1-x0),Math.abs(y1-y0));
  for(let n=0;n<=steps;n++){const x=Math.round(x0+(x1-x0)*n/steps),y=Math.round(y0+(y1-y0)*n/steps);for(let d=-Math.floor(thickness/2);d<=Math.floor(thickness/2);d++)for(let e=-Math.floor(thickness/2);e<=Math.floor(thickness/2);e++)setPixel(im,x+d,y+e,color)}
}
function card({leftBorder=22,rightBorder=22,topBorder=25,bottomBorder=25,scratch=null,artwork=false,glare=false,outsideDust=false,whitening=false,whiteBorder=false,lowLight=false,borderless=false}={}){
  const im=image(),outer={left:200,top:50,right:500,bottom:470},base=whiteBorder?[228,230,232]:lowLight?[34,38,43]:[47,76,116],art=lowLight?[50,56,63]:[96,132,160];
  fill(im,outer.left,outer.top,outer.right,outer.bottom,base,7);
  if(borderless)fill(im,outer.left,outer.top,outer.right,outer.bottom,art,11);
  else fill(im,outer.left+leftBorder,outer.top+topBorder,outer.right-rightBorder,outer.bottom-bottomBorder,art,11);
  if(artwork){
    fill(im,260,125,450,190,[185,62,95],13);fill(im,235,230,330,360,[54,168,118],17);fill(im,350,215,465,390,[184,145,50],19);
    line(im,245,115,455,315,[35,86,175],8);line(im,245,385,455,205,[165,44,128],7);
    for(let y=405;y<435;y+=6)line(im,245,y,450,y,[235,210,65],3);
  }
  if(scratch){const color=scratch.dark?[10,11,12]:[246,246,244],thickness=scratch.thickness||1;
    if(scratch.kind==='horizontal')line(im,245,285,455,285,color,thickness);
    if(scratch.kind==='vertical')line(im,350,125,350,400,color,thickness);
    if(scratch.kind==='diagonal')line(im,250,130,445,365,color,thickness);
  }
  if(glare)fill(im,270,155,430,250,[252,252,250]);
  if(outsideDust){for(let n=0;n<90;n++){const x=35+(n*53)%130,y=20+(n*71)%570;fill(im,x,y,x+2,y+2,[245,245,245])}}
  if(whitening){fill(im,outer.left,outer.top,outer.left+24,outer.top+18,[244,244,241]);fill(im,outer.right-18,outer.bottom-28,outer.right,outer.bottom,[246,246,243])}
  return im;
}
function trapezoid(){
  const im=image(),top=55,bottom=500;
  for(let y=top;y<bottom;y++){const ratio=(y-top)/(bottom-top),half=105+ratio*65,center=350,left=Math.round(center-half),right=Math.round(center+half);for(let x=left;x<right;x++)setPixel(im,x,y,[198+(x+y)%7,201,204])}
  return im;
}

assert.strictEqual(vision.ENGINE_VERSION,'v158-four-quadrant-precision-learning');
assert.deepStrictEqual({low:vision.DEFAULT_CONFIG.cannyLow,high:vision.DEFAULT_CONFIG.cannyHigh},{low:35,high:105});

const clean=card({artwork:true}),quality=vision.analyzeQuality(clean),outer=vision.detectOuterBounds(clean),center=vision.measureCentering(clean,outer,quality);
assert(quality.measurable&&quality.score>=55,JSON.stringify(quality));
assert(!outer.fallback&&outer.confidence>=55,JSON.stringify(outer));
assert(center.valid&&center.confidence>=55,JSON.stringify(center));
assert(Math.abs(center.lr-50)<5&&Math.abs(center.tb-50)<5,JSON.stringify(center));
for(const game of ['pokemon','onepiece','naruto']){
  const quadrants=vision.analyzeFourQuadrants(clean,clean,outer,{game});
  assert.deepStrictEqual(Object.keys(quadrants.quadrants),['tl','tr','bl','br']);
  assert(quadrants.allQuadrantsMeasured&&quadrants.confidence>=55,JSON.stringify(quadrants));
  assert.strictEqual(quadrants.gameProfile,game);
}
const localScratch=card();line(localScratch,245,145,305,205,[246,246,244],2);
const localQuadrants=vision.analyzeFourQuadrants(localScratch,localScratch,null,{game:'pokemon'});
assert.strictEqual(localQuadrants.worstQuadrant,'tl',JSON.stringify(localQuadrants));
assert(localQuadrants.quadrants.tl.surfaceRisk>localQuadrants.quadrants.br.surfaceRisk,JSON.stringify(localQuadrants));

const off=card({leftBorder:14,rightBorder:34,topBorder:16,bottomBorder:36}),offCenter=vision.measureCentering(off);
assert(offCenter.valid,JSON.stringify(offCenter));
assert(offCenter.lr<38&&offCenter.tb<40,JSON.stringify(offCenter));

const plain=card(),cleanSurface=vision.analyzeSurface(clean,clean),plainSurface=vision.analyzeSurface(plain,plain);
const micro=vision.analyzeSurface(card({artwork:true,scratch:{kind:'horizontal',thickness:1}}),card({artwork:true,scratch:{kind:'horizontal',thickness:1}}));
const vertical=vision.analyzeSurface(card({scratch:{kind:'vertical',thickness:2}}),card({scratch:{kind:'vertical',thickness:2}}));
const diagonal=vision.analyzeSurface(card({scratch:{kind:'diagonal',thickness:2}}),card({scratch:{kind:'diagonal',thickness:2}}));
assert(cleanSurface.risk<25,JSON.stringify(cleanSurface));
assert(plainSurface.risk<20,JSON.stringify(plainSurface));
assert(micro.risk>=cleanSurface.risk+8,JSON.stringify({clean:cleanSurface.risk,micro:micro.risk,details:micro}));
assert(vertical.risk>=plainSurface.risk+12,JSON.stringify(vertical));
assert(diagonal.risk>=plainSurface.risk+10,JSON.stringify(diagonal));
assert(micro.confirmedSegments>0&&vertical.confirmedSegments>0&&diagonal.confirmedSegments>0);

const dust=vision.analyzeSurface(card({outsideDust:true}),card({outsideDust:true}));
assert(dust.risk<20,JSON.stringify(dust));
assert(dust.base.maskCoverage>.85&&dust.base.maskCoverage<1,JSON.stringify(dust.base));
const glareInput=card({glare:true}),glareSurface=vision.analyzeSurface(glareInput,card());
assert(vision.analyzeQuality(glareInput).issues.some(issue=>issue.includes('반사')||issue.includes('날아간')));
assert(glareSurface.risk<30,JSON.stringify(glareSurface));

const cleanBack=vision.analyzeWhitening(card()),damagedBack=vision.analyzeWhitening(card({whitening:true})),naturalWhite=vision.analyzeWhitening(card({whiteBorder:true}));
assert(cleanBack.risk<20,JSON.stringify(cleanBack));
assert(damagedBack.risk>=cleanBack.risk+20,JSON.stringify({cleanBack,damagedBack}));
assert(naturalWhite.baseline.naturallyWhite&&naturalWhite.risk<20,JSON.stringify(naturalWhite));

const presets=[[20,60],[35,105],[50,150],[65,195]],cases=[
  {input:clean,oblique:clean,defect:false},{input:plain,oblique:plain,defect:false},{input:card({outsideDust:true}),oblique:card({outsideDust:true}),defect:false},
  {input:card({artwork:true,scratch:{kind:'horizontal',thickness:1}}),oblique:card({artwork:true,scratch:{kind:'horizontal',thickness:1}}),defect:true},
  {input:card({scratch:{kind:'vertical',thickness:2}}),oblique:card({scratch:{kind:'vertical',thickness:2}}),defect:true},
  {input:card({scratch:{kind:'diagonal',thickness:2}}),oblique:card({scratch:{kind:'diagonal',thickness:2}}),defect:true},
];
const tuning=presets.map(([low,high])=>{let tp=0,tn=0,fp=0,fn=0;for(const row of cases){const result=vision.analyzeSurface(row.input,row.oblique,null,{cannyLow:low,cannyHigh:high}),pred=result.risk>=25;if(row.defect&&pred)tp++;else if(row.defect)fn++;else if(pred)fp++;else tn++}const f1=2*tp/Math.max(1,2*tp+fp+fn);return {low,high,tp,tn,fp,fn,f1}});
const selected=tuning.find(row=>row.low===vision.DEFAULT_CONFIG.cannyLow&&row.high===vision.DEFAULT_CONFIG.cannyHigh),best=Math.max(...tuning.map(row=>row.f1));
assert(selected.f1>=best-.001&&selected.fp===0&&selected.fn===0,JSON.stringify(tuning));

const blurred=image(700,640,[128,128,128]),blurQuality=vision.analyzeQuality(blurred);
assert(!blurQuality.measurable&&blurQuality.issues.some(issue=>issue.includes('흐림')));
assert(vision.analyzeQuality(card({lowLight:true})).score<quality.score);
assert(!vision.measureCentering(card({borderless:true})).valid);
const skewed=vision.detectOuterBounds(trapezoid());assert(skewed.perspectiveSkew>.08||skewed.confidence<55,JSON.stringify(skewed));
assert.throws(()=>vision.analyzeQuality({width:9,height:9,data:new Uint8Array(3)}),/VisionImageDataError/);
assert.throws(()=>vision.analyzeQuality({width:5000,height:5000,data:{length:100000000}}),/VisionImageSizeError/);

console.log('PASS: card mask + CLAHE + Canny hysteresis + Hough line evidence separated artwork/dust/glare from confirmed micro scratches; whitening and centering cross-tests passed; threshold tuning selected 35/105');
