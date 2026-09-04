(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.TCGVision=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';

  const ENGINE_VERSION='v160-grading-hierarchy-1-4-8';
  const MAX_PIXELS=16000000;
  const DEFAULT_CONFIG=Object.freeze({
    maskInset:.025,cornerRadius:.045,claheClipLimit:2,claheTiles:8,
    cannyLow:35,cannyHigh:105,houghVoteThreshold:18,minLineRatio:.24,maxLineGap:10,scratchContrastMin:30,
  });
  const GAME_PROFILES=Object.freeze({
    pokemon:Object.freeze({id:'pokemon',label:'포켓몬',textureAware:true,darkBorderAware:false,confidenceCap:96}),
    onepiece:Object.freeze({id:'onepiece',label:'원피스',textureAware:true,darkBorderAware:true,confidenceCap:96}),
    naruto:Object.freeze({id:'naruto',label:'나루토',textureAware:true,darkBorderAware:true,confidenceCap:84}),
  });
  const clamp=(value,low,high)=>Math.max(low,Math.min(high,value));
  const finite=value=>Number.isFinite(Number(value));
  function median(values){
    if(!values.length)return 0;
    const sorted=[...values].sort((a,b)=>a-b),middle=Math.floor(sorted.length/2);
    return sorted.length%2?sorted[middle]:(sorted[middle-1]+sorted[middle])/2;
  }
  function percentile(values,ratio){
    if(!values.length)return 0;
    const sorted=[...values].sort((a,b)=>a-b),position=clamp(ratio,0,1)*(sorted.length-1);
    const lower=Math.floor(position),upper=Math.ceil(position),weight=position-lower;
    return sorted[lower]*(1-weight)+sorted[upper]*weight;
  }
  function validateImage(image){
    const width=Number(image?.width),height=Number(image?.height),data=image?.data;
    if(!Number.isInteger(width)||!Number.isInteger(height)||width<8||height<8||width*height>MAX_PIXELS)throw new Error('VisionImageSizeError');
    if(!data||typeof data.length!=='number'||data.length!==width*height*4)throw new Error('VisionImageDataError');
    return {width,height,data};
  }
  function luminance(data,index){return .2126*data[index]+.7152*data[index+1]+.0722*data[index+2]}
  function colorDistance(data,index,color){
    const dr=data[index]-color[0],dg=data[index+1]-color[1],db=data[index+2]-color[2];
    return Math.sqrt(dr*dr+dg*dg+db*db);
  }
  function pixelIndex(width,x,y){return (y*width+x)*4}

  function analyzeQuality(input){
    const {width,height,data}=validateImage(input),step=Math.max(1,Math.floor(Math.min(width,height)/320));
    let count=0,sum=0,dark=0,bright=0,glare=0,lapSum=0,lap2=0,lapCount=0;
    const tiles=Array.from({length:16},()=>({sum:0,n:0}));
    for(let y=step;y<height-step;y+=step){
      for(let x=step;x<width-step;x+=step){
        const index=pixelIndex(width,x,y),value=luminance(data,index),mx=Math.max(data[index],data[index+1],data[index+2]),mn=Math.min(data[index],data[index+1],data[index+2]);
        count++;sum+=value;dark+=value<12?1:0;bright+=value>248?1:0;glare+=value>242&&mx-mn<18?1:0;
        const tile=tiles[Math.min(3,Math.floor(y/height*4))*4+Math.min(3,Math.floor(x/width*4))];tile.sum+=value;tile.n++;
        const lap=4*value-luminance(data,pixelIndex(width,x-step,y))-luminance(data,pixelIndex(width,x+step,y))-luminance(data,pixelIndex(width,x,y-step))-luminance(data,pixelIndex(width,x,y+step));
        lapSum+=lap;lap2+=lap*lap;lapCount++;
      }
    }
    const mean=sum/Math.max(1,count),lapMean=lapSum/Math.max(1,lapCount),sharpness=Math.max(0,lap2/Math.max(1,lapCount)-lapMean*lapMean);
    const darkRatio=dark/Math.max(1,count),brightRatio=bright/Math.max(1,count),glareRatio=glare/Math.max(1,count);
    const tileMeans=tiles.filter(tile=>tile.n).map(tile=>tile.sum/tile.n),illuminationRange=Math.max(...tileMeans)-Math.min(...tileMeans);
    const minDimension=Math.min(width,height),issues=[];
    let score=100;
    if(minDimension<480){issues.push('해상도 부족');score-=45}else if(minDimension<900){issues.push('미세결함용 해상도 낮음');score-=16}
    if(sharpness<25){issues.push('심한 흐림/초점 실패');score-=45}else if(sharpness<70){issues.push('초점 선명도 부족');score-=20}
    if(mean<45){issues.push('노출 부족');score-=30}else if(mean>220){issues.push('노출 과다');score-=28}
    if(darkRatio>.18){issues.push('검게 뭉개진 영역');score-=18}
    if(brightRatio>.12){issues.push('하얗게 날아간 영역');score-=20}
    if(glareRatio>.07){issues.push('강한 반사');score-=26}else if(glareRatio>.025){issues.push('부분 반사');score-=10}
    if(illuminationRange>105){issues.push('조명 불균일/그림자');score-=22}else if(illuminationRange>70){issues.push('조명 편차');score-=10}
    score=Math.round(clamp(score,0,100));
    return {
      score,measurable:score>=55&&minDimension>=480&&sharpness>=25&&glareRatio<.18,
      width,height,minDimension,mean:Math.round(mean*10)/10,sharpness:Math.round(sharpness*10)/10,
      darkRatio,brightRatio,glareRatio,illuminationRange:Math.round(illuminationRange*10)/10,issues:[...new Set(issues)]
    };
  }

  function cornerBackground(data,width,height){
    const values=[[],[],[]],sx=Math.max(2,Math.floor(width*.06)),sy=Math.max(2,Math.floor(height*.06)),step=Math.max(1,Math.floor(Math.min(width,height)/220));
    const regions=[[0,sx,0,sy],[width-sx,width,0,sy],[0,sx,height-sy,height],[width-sx,width,height-sy,height]];
    for(const [x0,x1,y0,y1] of regions)for(let y=y0;y<y1;y+=step)for(let x=x0;x<x1;x+=step){const index=pixelIndex(width,x,y);values[0].push(data[index]);values[1].push(data[index+1]);values[2].push(data[index+2])}
    return values.map(median);
  }
  function quantileBounds(points,width,height){
    const xs=points.map(point=>point[0]),ys=points.map(point=>point[1]);
    return {left:Math.round(percentile(xs,.015)),right:Math.round(percentile(xs,.985)),top:Math.round(percentile(ys,.015)),bottom:Math.round(percentile(ys,.985))};
  }
  function detectOuterBounds(input){
    const {width,height,data}=validateImage(input),background=cornerBackground(data,width,height),step=Math.max(1,Math.floor(Math.min(width,height)/420));
    const distances=[];
    for(let y=0;y<height;y+=step)for(let x=0;x<width;x+=step)distances.push(colorDistance(data,pixelIndex(width,x,y),background));
    const threshold=clamp(Math.max(26,percentile(distances,.62)*1.35),26,82),points=[];
    for(let y=0;y<height;y+=step)for(let x=0;x<width;x+=step)if(colorDistance(data,pixelIndex(width,x,y),background)>threshold)points.push([x,y]);
    const pointRatio=points.length/Math.max(1,Math.ceil(width/step)*Math.ceil(height/step));
    let bounds=points.length>80?quantileBounds(points,width,height):null,fallback=false;
    if(bounds){
      const bw=bounds.right-bounds.left,bh=bounds.bottom-bounds.top,coverage=bw*bh/(width*height),aspect=bw/Math.max(1,bh);
      if(coverage<.16||coverage>.94||aspect<.52||aspect>.92)bounds=null;
    }
    if(!bounds){fallback=true;bounds={left:Math.round(width*.02),right:Math.round(width*.98),top:Math.round(height*.02),bottom:Math.round(height*.98)}}
    const bw=bounds.right-bounds.left,bh=bounds.bottom-bounds.top,aspect=bw/Math.max(1,bh),expected=63/88,aspectError=Math.abs(aspect-expected)/expected;
    const rowExtents=[];
    if(!fallback){
      for(const ratio of [.12,.25,.75,.88]){
        const cy=Math.round(bounds.top+bh*ratio),band=[];
        for(const point of points)if(Math.abs(point[1]-cy)<=step*2)band.push(point[0]);
        if(band.length>5)rowExtents.push([percentile(band,.03),percentile(band,.97)]);
      }
    }
    let perspectiveSkew=0;
    if(rowExtents.length>=4){const widths=rowExtents.map(row=>row[1]-row[0]),centers=rowExtents.map(row=>(row[0]+row[1])/2);perspectiveSkew=Math.max((Math.max(...widths)-Math.min(...widths))/Math.max(1,median(widths)),(Math.max(...centers)-Math.min(...centers))/Math.max(1,bw))}
    const separation=percentile(distances,.85)-percentile(distances,.30);
    const confidence=Math.round(clamp((fallback?32:62)+Math.min(22,separation*.35)-aspectError*45-perspectiveSkew*80,5,98));
    return {...bounds,width:bw,height:bh,aspect,aspectError,perspectiveSkew,confidence,fallback,background,threshold,pointRatio};
  }

  function smooth(values,radius=2){
    const out=new Float32Array(values.length),prefix=new Float64Array(values.length+1);
    for(let i=0;i<values.length;i++)prefix[i+1]=prefix[i]+values[i];
    for(let i=0;i<values.length;i++){const left=Math.max(0,i-radius),right=Math.min(values.length,i+radius+1);out[i]=(prefix[right]-prefix[left])/(right-left)}
    return out;
  }
  function profileAt(data,width,height,bounds,axis,ratio){
    const length=axis==='x'?bounds.width:bounds.height,values=new Float32Array(length),cross=axis==='x'?bounds.height:bounds.width;
    const center=Math.round(ratio*(cross-1)),radius=2;
    for(let p=0;p<length;p++){
      let sum=0,n=0;
      for(let delta=-radius;delta<=radius;delta++){
        const q=clamp(center+delta,0,cross-1),x=axis==='x'?bounds.left+p:bounds.left+q,y=axis==='x'?bounds.top+q:bounds.top+p;
        if(x>=0&&x<width&&y>=0&&y<height){sum+=luminance(data,pixelIndex(width,x,y));n++}
      }
      values[p]=sum/Math.max(1,n);
    }
    return smooth(values,Math.max(1,Math.round(length/600)));
  }
  function peakCandidates(profile,start,end,scan){
    const peaks=[],gradients=new Float32Array(profile.length);
    for(let i=2;i<profile.length-2;i++)gradients[i]=Math.abs(profile[i+2]-profile[i-2])+.5*Math.abs(profile[i+1]-profile[i-1]);
    for(let i=Math.max(3,start);i<Math.min(profile.length-3,end);i++){
      const gradient=gradients[i];
      if(gradient>=gradients[i-1]&&gradient>=gradients[i+1]&&gradient>=4)peaks.push({position:i,strength:gradient,scan});
    }
    peaks.sort((a,b)=>b.strength-a.strength);return peaks.slice(0,32);
  }
  function clusterPeaks(peaks,tolerance,lineCount){
    const sorted=[...peaks].sort((a,b)=>a.position-b.position),clusters=[];
    for(const peak of sorted){let cluster=clusters.find(row=>Math.abs(row.center-peak.position)<=tolerance);if(!cluster){cluster={items:[],center:peak.position};clusters.push(cluster)}cluster.items.push(peak);cluster.center=median(cluster.items.map(item=>item.position))}
    return clusters.map(cluster=>{
      const scans=new Set(cluster.items.map(item=>item.scan)).size,positions=cluster.items.map(item=>item.position),strength=median(cluster.items.map(item=>item.strength));
      const spread=median(positions.map(value=>Math.abs(value-median(positions))));
      return {...cluster,support:scans/lineCount,scans,strength,spread,score:scans*12+Math.min(40,strength)-spread*2};
    }).sort((a,b)=>b.score-a.score);
  }
  function locateBoundary(input,bounds,axis,side){
    const {width,height,data}=validateImage(input),ratios=[.14,.23,.32,.41,.50,.59,.68,.77,.86],length=axis==='x'?bounds.width:bounds.height,peaks=[];
    const start=Math.round(length*(side==='near'?.008:.60)),end=Math.round(length*(side==='near'?.40:.992));
    ratios.forEach((ratio,scan)=>peaks.push(...peakCandidates(profileAt(data,width,height,bounds,axis,ratio),start,end,scan)));
    const clusters=clusterPeaks(peaks,Math.max(3,Math.round(length*.008)),ratios.length);
    const qualified=clusters.filter(row=>row.scans>=5&&row.strength>=6).map(row=>{
      const margin=(side==='near'?row.center:length-row.center)/Math.max(1,length);
      return {...row,margin,borderScore:row.support*42+Math.min(28,row.strength)-margin*520-row.spread*2};
    }).filter(row=>row.margin>=.012&&row.margin<=.36).sort((a,b)=>b.borderScore-a.borderScore);
    const best=qualified[0]||clusters[0];
    if(!best||best.scans<5||best.strength<6)return {valid:false,position:null,support:best?.support||0,strength:best?.strength||0,spread:best?.spread||999};
    return {valid:true,position:best.center,support:best.support,strength:best.strength,spread:best.spread};
  }
  function measureCentering(input,providedBounds,providedQuality){
    const quality=providedQuality||analyzeQuality(input),outer=providedBounds||detectOuterBounds(input);
    const left=locateBoundary(input,outer,'x','near'),right=locateBoundary(input,outer,'x','far'),top=locateBoundary(input,outer,'y','near'),bottom=locateBoundary(input,outer,'y','far');
    const valid=[left,right,top,bottom].every(row=>row.valid);
    if(!valid)return {valid:false,manualRequired:true,confidence:Math.round(Math.min(outer.confidence,quality.score)*.45),outer,boundaries:{left,right,top,bottom},reason:'반복되는 내부 보더 4면을 찾지 못했습니다.'};
    const widths={left:left.position,right:outer.width-right.position,top:top.position,bottom:outer.height-bottom.position};
    const horizontal=widths.left+widths.right,vertical=widths.top+widths.bottom;
    if(horizontal<=2||vertical<=2)return {valid:false,manualRequired:true,confidence:10,outer,boundaries:{left,right,top,bottom},reason:'보더 폭 계산값이 유효하지 않습니다.'};
    const lr=widths.left/horizontal*100,tb=widths.top/vertical*100;
    const plausible=Math.min(widths.left,widths.right)>outer.width*.012&&Math.max(widths.left,widths.right)<outer.width*.40&&Math.min(widths.top,widths.bottom)>outer.height*.012&&Math.max(widths.top,widths.bottom)<outer.height*.40;
    const support=median([left.support,right.support,top.support,bottom.support]),strength=median([left.strength,right.strength,top.strength,bottom.strength]);
    const spread=median([left.spread,right.spread,top.spread,bottom.spread]),consistency=clamp(1-spread/Math.max(4,Math.min(outer.width,outer.height)*.015),0,1);
    const confidence=Math.round(clamp(.30*outer.confidence+.25*quality.score+support*24+consistency*15+Math.min(8,strength/4)-(outer.perspectiveSkew>.08?20:0),5,99));
    return {valid:plausible&&confidence>=55&&outer.perspectiveSkew<=.16,manualRequired:!plausible||confidence<55||outer.perspectiveSkew>.16,confidence,outer,boundaries:{left,right,top,bottom},widths,lr,tb,worstLR:Math.max(lr,100-lr),worstTB:Math.max(tb,100-tb),worst:Math.min(lr,100-lr,tb,100-tb),reason:plausible?'내부 보더 반복 경계 검출':'내부 보더 위치가 비정상입니다.'};
  }

  function scratchGrid(input,bounds,config=DEFAULT_CONFIG){
    const {width,height,data}=validateImage(input),inset=config.maskInset;
    const left=Math.round(bounds.left+bounds.width*inset),right=Math.round(bounds.right-bounds.width*inset),top=Math.round(bounds.top+bounds.height*inset),bottom=Math.round(bounds.bottom-bounds.height*inset);
    const step=Math.max(1,Math.ceil(Math.max(right-left,bottom-top)/720)),gridWidth=Math.max(8,Math.floor((right-left)/step)),gridHeight=Math.max(8,Math.floor((bottom-top)/step));
    const values=new Float32Array(gridWidth*gridHeight),chroma=new Float32Array(gridWidth*gridHeight),mask=new Uint8Array(gridWidth*gridHeight),radius=Math.max(3,Math.round(Math.min(gridWidth,gridHeight)*config.cornerRadius));
    for(let gy=0;gy<gridHeight;gy++)for(let gx=0;gx<gridWidth;gx++){
      const x=clamp(left+gx*step,0,width-1),y=clamp(top+gy*step,0,height-1),index=pixelIndex(width,x,y),position=gy*gridWidth+gx;
      values[position]=luminance(data,index);chroma[position]=Math.max(data[index],data[index+1],data[index+2])-Math.min(data[index],data[index+1],data[index+2]);
      const cx=gx<radius?radius:gx>=gridWidth-radius?gridWidth-radius-1:gx,cy=gy<radius?radius:gy>=gridHeight-radius?gridHeight-radius-1:gy;
      if((gx-cx)*(gx-cx)+(gy-cy)*(gy-cy)<=radius*radius)mask[position]=1;
    }
    return {values,chroma,mask,width:gridWidth,height:gridHeight,step,left,top};
  }

  function clahe(values,width,height,mask,clipLimit=2,tileCount=8){
    const tiles=Math.max(2,Math.min(16,Math.round(tileCount))),maps=[];
    for(let ty=0;ty<tiles;ty++)for(let tx=0;tx<tiles;tx++){
      const x0=Math.floor(tx*width/tiles),x1=Math.floor((tx+1)*width/tiles),y0=Math.floor(ty*height/tiles),y1=Math.floor((ty+1)*height/tiles),hist=new Uint32Array(256);let count=0;
      for(let y=y0;y<y1;y++)for(let x=x0;x<x1;x++){const p=y*width+x;if(mask[p]){hist[clamp(Math.round(values[p]),0,255)]++;count++}}
      const limit=Math.max(1,Math.round(clipLimit*Math.max(1,count)/256));let excess=0;
      for(let i=0;i<256;i++)if(hist[i]>limit){excess+=hist[i]-limit;hist[i]=limit}
      const add=Math.floor(excess/256),remainder=excess%256;for(let i=0;i<256;i++)hist[i]+=add+(i<remainder?1:0);
      const map=new Uint8Array(256);let cumulative=0;for(let i=0;i<256;i++){cumulative+=hist[i];map[i]=Math.round(clamp(cumulative/Math.max(1,count)*255,0,255))}maps.push(map);
    }
    const out=new Float32Array(values.length);
    for(let y=0;y<height;y++)for(let x=0;x<width;x++){
      const p=y*width+x;if(!mask[p])continue;
      const fx=clamp((x+.5)*tiles/width-.5,0,tiles-1),fy=clamp((y+.5)*tiles/height-.5,0,tiles-1),x0=Math.floor(fx),x1=Math.min(tiles-1,x0+1),y0=Math.floor(fy),y1=Math.min(tiles-1,y0+1),wx=fx-x0,wy=fy-y0,v=clamp(Math.round(values[p]),0,255);
      const top=maps[y0*tiles+x0][v]*(1-wx)+maps[y0*tiles+x1][v]*wx,bottom=maps[y1*tiles+x0][v]*(1-wx)+maps[y1*tiles+x1][v]*wx;out[p]=top*(1-wy)+bottom*wy;
    }
    return out;
  }

  function cannyEdges(values,width,height,mask,low=35,high=105){
    const magnitude=new Float32Array(values.length),direction=new Uint8Array(values.length),suppressed=new Float32Array(values.length),edges=new Uint8Array(values.length),strong=[];
    const at=(x,y)=>values[y*width+x];
    for(let y=1;y<height-1;y++)for(let x=1;x<width-1;x++){
      const p=y*width+x;if(!mask[p])continue;
      const gx=-at(x-1,y-1)-2*at(x-1,y)-at(x-1,y+1)+at(x+1,y-1)+2*at(x+1,y)+at(x+1,y+1),gy=-at(x-1,y-1)-2*at(x,y-1)-at(x+1,y-1)+at(x-1,y+1)+2*at(x,y+1)+at(x+1,y+1);
      magnitude[p]=Math.hypot(gx,gy);let angle=(Math.atan2(gy,gx)*180/Math.PI+180)%180;direction[p]=angle<22.5||angle>=157.5?0:angle<67.5?1:angle<112.5?2:3;
    }
    for(let y=1;y<height-1;y++)for(let x=1;x<width-1;x++){
      const p=y*width+x;if(!mask[p])continue;const m=magnitude[p],d=direction[p];let a,b;
      if(d===0){a=magnitude[p-1];b=magnitude[p+1]}else if(d===1){a=magnitude[p-width+1];b=magnitude[p+width-1]}else if(d===2){a=magnitude[p-width];b=magnitude[p+width]}else{a=magnitude[p-width-1];b=magnitude[p+width+1]}
      if(m>=a&&m>=b)suppressed[p]=m;
    }
    for(let p=0;p<suppressed.length;p++)if(mask[p]&&suppressed[p]>=high){edges[p]=2;strong.push(p)}else if(mask[p]&&suppressed[p]>=low)edges[p]=1;
    while(strong.length){const p=strong.pop(),x=p%width,y=Math.floor(p/width);for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){const nx=x+dx,ny=y+dy;if(nx<0||nx>=width||ny<0||ny>=height)continue;const q=ny*width+nx;if(edges[q]===1){edges[q]=2;strong.push(q)}}}
    for(let p=0;p<edges.length;p++)edges[p]=edges[p]===2?1:0;
    return {edges,magnitude,direction,low,high};
  }

  function segmentEvidence(segment,values,chroma,width,height,config=DEFAULT_CONFIG){
    const samples=Math.max(8,Math.min(32,Math.round(segment.length/5))),contrasts=[],neutral=[];
    for(let i=0;i<samples;i++){
      const t=segment.start+(segment.end-segment.start)*(i+.5)/samples,x=Math.round(t*segment.dx+segment.rho*segment.nx),y=Math.round(t*segment.dy+segment.rho*segment.ny);
      if(x<3||x>=width-3||y<3||y>=height-3)continue;
      const a=values[Math.round(y+segment.ny*2)*width+Math.round(x+segment.nx*2)],b=values[Math.round(y-segment.ny*2)*width+Math.round(x-segment.nx*2)],p=y*width+x;
      const p1=Math.round(y+segment.ny)*width+Math.round(x+segment.nx),p2=Math.round(y-segment.ny)*width+Math.round(x-segment.nx);
      contrasts.push(Math.abs(a-b));neutral.push(Math.min(chroma[p],chroma[p1],chroma[p2])<32?1:0);
    }
    const mean=contrasts.reduce((a,b)=>a+b,0)/Math.max(1,contrasts.length),variance=contrasts.reduce((sum,value)=>sum+(value-mean)*(value-mean),0)/Math.max(1,contrasts.length),cv=Math.sqrt(variance)/Math.max(1,mean),neutralRatio=neutral.reduce((a,b)=>a+b,0)/Math.max(1,neutral.length);
    const contrastMin=clamp(Number(config.scratchContrastMin)||DEFAULT_CONFIG.scratchContrastMin,4,64);
    const neutralThinLine=neutralRatio>=.72&&segment.lengthRatio>=config.minLineRatio&&mean>=contrastMin*.60;
    return {contrastMean:mean,contrastCv:cv,neutralRatio,accepted:(mean>=contrastMin||neutralThinLine)&&cv<=1.2&&neutralRatio>=.42};
  }

  function probabilisticHoughSegments(canny,values,chroma,width,height,mask,config=DEFAULT_CONFIG){
    const angles=Array.from({length:18},(_,index)=>index*Math.PI/18),edgePoints=[];
    for(let p=0;p<canny.edges.length;p++)if(canny.edges[p]&&mask[p])edgePoints.push([p%width,Math.floor(p/width)]);
    const stride=Math.max(1,Math.ceil(edgePoints.length/24000)),segments=[],minimum=Math.max(7,Math.round(Math.max(width,height)*config.minLineRatio));
    angles.forEach((angle,angleIndex)=>{
      const dx=Math.cos(angle),dy=Math.sin(angle),nx=-dy,ny=dx,bins=new Map();
      for(let i=0;i<edgePoints.length;i+=stride){const [x,y]=edgePoints[i],rho=Math.round(x*nx+y*ny),t=x*dx+y*dy,row=bins.get(rho)||[];row.push(t);bins.set(rho,row)}
      const selected=[...bins.entries()].filter(([,points])=>points.length>=config.houghVoteThreshold).sort((a,b)=>b[1].length-a[1].length).slice(0,80);
      for(const [rho,points] of selected){points.sort((a,b)=>a-b);let start=points[0],previous=points[0];
        for(let i=1;i<=points.length;i++){const current=points[i];if(i<points.length&&current-previous<=config.maxLineGap){previous=current;continue}const length=previous-start;
          if(length>=minimum){const raw={angleIndex,angle,rho,start,end:previous,length,dx,dy,nx,ny,midX:((start+previous)/2*dx+rho*nx)/width,midY:((start+previous)/2*dy+rho*ny)/height,lengthRatio:length/Math.max(width,height)},evidence=segmentEvidence(raw,values,chroma,width,height,config);segments.push({...raw,...evidence})}
          start=current;previous=current;
        }
      }
    });
    const dedup=[];for(const segment of segments.sort((a,b)=>(Number(b.accepted)-Number(a.accepted))||b.length-a.length)){if(dedup.some(row=>row.angleIndex===segment.angleIndex&&Math.abs(row.rho-segment.rho)<=3&&Math.abs(row.start-segment.start)<=8&&Math.abs(row.end-segment.end)<=8))continue;dedup.push(segment);if(dedup.length>=120)break}
    return {segments:dedup,accepted:dedup.filter(row=>row.accepted),artworkRejected:dedup.filter(row=>!row.accepted).length,edgePoints:edgePoints.length};
  }

  function detectScratchCandidates(input,providedBounds,providedConfig={}){
    const config={...DEFAULT_CONFIG,...providedConfig},outer=providedBounds||detectOuterBounds(input),grid=scratchGrid(input,outer,config),enhanced=clahe(grid.values,grid.width,grid.height,grid.mask,config.claheClipLimit,config.claheTiles),canny=cannyEdges(enhanced,grid.width,grid.height,grid.mask,config.cannyLow,config.cannyHigh),hough=probabilisticHoughSegments(canny,enhanced,grid.chroma,grid.width,grid.height,grid.mask,config);
    const accepted=hough.accepted,weighted=accepted.reduce((sum,row)=>sum+row.lengthRatio*Math.min(1.5,row.contrastMean/18)*(1-Math.min(.65,row.contrastCv*.45)),0),maxRun=accepted.reduce((best,row)=>Math.max(best,row.length),0),risk=Math.round(clamp(weighted*46+Math.min(24,accepted.length*3),0,100));
    const compact=({angleIndex,rho,length,lengthRatio,midX,midY,contrastMean,contrastCv,neutralRatio})=>({angleIndex,rho,length,lengthRatio,midX,midY,contrastMean,contrastCv,neutralRatio});
    return {risk,candidatePixels:hough.edgePoints,candidateComponents:accepted.length,maxRun,density:hough.edgePoints/Math.max(1,grid.width*grid.height),thresholds:{low:config.cannyLow,high:config.cannyHigh},gridWidth:grid.width,gridHeight:grid.height,maskCoverage:grid.mask.reduce((a,b)=>a+b,0)/grid.mask.length,artworkRejected:hough.artworkRejected,segments:accepted.map(compact),rejectedSample:hough.segments.filter(row=>!row.accepted).slice(0,8).map(compact)};
  }

  function matchingSegments(a,b){
    let matches=0;for(const left of a.segments||[])if((b.segments||[]).some(right=>left.angleIndex===right.angleIndex&&Math.hypot(left.midX-right.midX,left.midY-right.midY)<=.13&&Math.abs(left.lengthRatio-right.lengthRatio)<=.22))matches++;
    return Math.min(matches,Math.min(a.segments?.length||0,b.segments?.length||0));
  }

  function analyzeSurface(baseInput,obliqueInput=null,baseBounds=null,providedConfig={}){
    const baseQuality=analyzeQuality(baseInput),baseOuter=baseBounds||detectOuterBounds(baseInput),base=detectScratchCandidates(baseInput,baseOuter,providedConfig);let oblique=null,obliqueQuality=null;
    if(obliqueInput){obliqueQuality=analyzeQuality(obliqueInput);oblique=detectScratchCandidates(obliqueInput,detectOuterBounds(obliqueInput),providedConfig)}
    const multiAngle=!!oblique,confirmed=multiAngle?matchingSegments(base,oblique):0,maxCandidate=multiAngle?Math.max(base.risk,oblique.risk):base.risk;
    const risk=Math.round(clamp(multiAngle?(confirmed?maxCandidate*.82+confirmed*5:maxCandidate*.15):maxCandidate*.58,0,100)),glare=(baseQuality.glareRatio+(obliqueQuality?.glareRatio||0)),qualityScore=multiAngle?Math.min(baseQuality.score,obliqueQuality.score):baseQuality.score;
    const confidence=Math.round(clamp((multiAngle?58:38)+qualityScore*.34+Math.min(16,confirmed*4)-glare*180,8,multiAngle?95:66));
    return {risk,scratchRisk:risk,confidence,multiAngle,confirmedSegments:confirmed,base,oblique,glareRisk:Math.round(clamp(glare*400,0,100)),quality:{base:baseQuality,oblique:obliqueQuality},requiresObliqueConfirmation:!multiAngle||(!confirmed&&maxCandidate>=15)};
  }

  function analyzeWhitening(input,providedBounds){
    const {width,height,data}=validateImage(input),outer=providedBounds||detectOuterBounds(input),band=Math.max(2,Math.round(Math.min(outer.width,outer.height)*.035)),cornerSpan=Math.max(band*2,Math.round(Math.min(outer.width,outer.height)*.13));
    let edgeCount=0,edgeWhite=0,cornerCount=0,cornerWhite=0;const sideReference=[];
    const pixel=(x,y)=>{const i=pixelIndex(width,clamp(x,0,width-1),clamp(y,0,height-1)),lum=luminance(data,i),chr=Math.max(data[i],data[i+1],data[i+2])-Math.min(data[i],data[i+1],data[i+2]);return {lum,chr}};
    const referenceDepth=Math.max(1,Math.round(band*.6));
    for(let t=0;t<=100;t++){const x=Math.round(outer.left+outer.width*t/100),y=Math.round(outer.top+outer.height*t/100);sideReference.push(pixel(x,outer.top+referenceDepth),pixel(x,outer.bottom-referenceDepth),pixel(outer.left+referenceDepth,y),pixel(outer.right-referenceDepth,y))}
    const refLum=median(sideReference.map(row=>row.lum)),refChroma=median(sideReference.map(row=>row.chr)),baselineWhite=refLum>=215&&refChroma<=25;
    function inspect(x,y,isCorner){const row=pixel(x,y),white=!baselineWhite&&refLum<225&&row.lum>=Math.max(175,refLum+28)&&row.chr<=Math.max(10,Math.min(36,refChroma*.72+10));edgeCount++;if(isCorner)cornerCount++;if(white){edgeWhite++;if(isCorner)cornerWhite++}}
    const step=Math.max(1,Math.round(Math.min(outer.width,outer.height)/420));
    for(let x=outer.left;x<=outer.right;x+=step)for(let d=0;d<band;d+=step){const corner=x-outer.left<cornerSpan||outer.right-x<cornerSpan;inspect(x,outer.top+d,corner);inspect(x,outer.bottom-d,corner)}
    for(let y=outer.top+cornerSpan;y<=outer.bottom-cornerSpan;y+=step)for(let d=0;d<band;d+=step){inspect(outer.left+d,y,false);inspect(outer.right-d,y,false)}
    const edgeRatio=edgeWhite/Math.max(1,edgeCount),cornerRatio=cornerWhite/Math.max(1,cornerCount),edgeRisk=Math.round(clamp(edgeRatio*1800,0,100)),cornerRisk=Math.round(clamp(cornerRatio*1500,0,100));
    return {edgeRisk,cornerRisk,risk:Math.max(edgeRisk,cornerRisk),edgeWhiteningPixels:edgeWhite,cornerWhiteningPixels:cornerWhite,edgeRatio,cornerRatio,baseline:{luminance:refLum,chroma:refChroma,naturallyWhite:baselineWhite}};
  }

  function gameProfile(value){
    const key=String(value||'').trim().toLowerCase().replace(/\s+/g,'');
    if(key==='pokemon'||key==='pokémon'||key==='포켓몬')return GAME_PROFILES.pokemon;
    if(key==='onepiece'||key==='원피스')return GAME_PROFILES.onepiece;
    if(key==='naruto'||key==='나루토')return GAME_PROFILES.naruto;
    return Object.freeze({id:'generic',label:'일반 TCG',textureAware:true,darkBorderAware:false,confidenceCap:82});
  }

  function quadrantId(x,y){return `${y<.5?'t':'b'}${x<.5?'l':'r'}`}
  function quadrantSegmentRisk(segments){
    const weighted=(segments||[]).reduce((sum,row)=>sum+row.lengthRatio*Math.min(1.5,row.contrastMean/30)*(1-Math.min(.65,row.contrastCv*.45)),0);
    return Math.round(clamp(weighted*50+Math.min(22,(segments||[]).length*3),0,100));
  }
  function quadrantWhitening(input,bounds,id){
    const {width,height,data}=validateImage(input),leftHalf=id.endsWith('l'),topHalf=id.startsWith('t'),mx=Math.round(bounds.left+bounds.width*.5),my=Math.round(bounds.top+bounds.height*.5);
    const x0=leftHalf?bounds.left:mx,x1=leftHalf?mx:bounds.right,y0=topHalf?bounds.top:my,y1=topHalf?my:bounds.bottom;
    const band=Math.max(2,Math.round(Math.min(bounds.width,bounds.height)*.035)),step=Math.max(1,Math.round(Math.min(bounds.width,bounds.height)/420)),reference=[];
    const sample=(x,y)=>{const p=pixelIndex(width,clamp(Math.round(x),0,width-1),clamp(Math.round(y),0,height-1)),lum=luminance(data,p),chr=Math.max(data[p],data[p+1],data[p+2])-Math.min(data[p],data[p+1],data[p+2]);return {lum,chr}};
    for(let x=x0;x<=x1;x+=step)reference.push(sample(x,topHalf?bounds.top+band:bounds.bottom-band));
    for(let y=y0;y<=y1;y+=step)reference.push(sample(leftHalf?bounds.left+band:bounds.right-band,y));
    const refLum=median(reference.map(row=>row.lum)),refChroma=median(reference.map(row=>row.chr)),natural=refLum>=215&&refChroma<=25;
    const cornerSpan=Math.max(band*2,Math.round(Math.min(bounds.width,bounds.height)*.13));
    let n=0,white=0,cornerN=0,cornerWhite=0;
    const inspect=(x,y,isCorner)=>{const row=sample(x,y),flag=!natural&&refLum<225&&row.lum>=Math.max(175,refLum+28)&&row.chr<=Math.max(10,Math.min(36,refChroma*.72+10));n++;if(isCorner)cornerN++;if(flag){white++;if(isCorner)cornerWhite++}};
    for(let x=x0;x<=x1;x+=step)for(let d=0;d<band;d+=step){const corner=leftHalf?x-x0<cornerSpan:x1-x<cornerSpan;inspect(x,topHalf?bounds.top+d:bounds.bottom-d,corner)}
    for(let y=y0;y<=y1;y+=step)for(let d=0;d<band;d+=step){const corner=topHalf?y-y0<cornerSpan:y1-y<cornerSpan;inspect(leftHalf?bounds.left+d:bounds.right-d,y,corner)}
    const ratio=white/Math.max(1,n),cornerRatio=cornerWhite/Math.max(1,cornerN),edgeRisk=Math.round(clamp(ratio*1700,0,100)),cornerRisk=Math.round(clamp(cornerRatio*1500,0,100));
    return {ratio,cornerRatio,whitePixels:white,cornerWhitePixels:cornerWhite,samplePixels:n,cornerSamplePixels:cornerN,risk:Math.max(edgeRisk,cornerRisk),edgeRisk,cornerRisk,naturallyWhite:natural};
  }
  function quadrantTextureRisk(input,bounds,id){
    const {width,height,data}=validateImage(input),leftHalf=id.endsWith('l'),topHalf=id.startsWith('t'),mx=Math.round(bounds.left+bounds.width*.5),my=Math.round(bounds.top+bounds.height*.5),pad=Math.max(3,Math.round(Math.min(bounds.width,bounds.height)*.035));
    const x0=(leftHalf?bounds.left:mx)+pad,x1=(leftHalf?mx:bounds.right)-pad,y0=(topHalf?bounds.top:my)+pad,y1=(topHalf?my:bounds.bottom)-pad,step=Math.max(1,Math.round(Math.min(bounds.width,bounds.height)/360));
    let total=0,samples=0,strong=0;for(let y=y0;y<y1-step;y+=step)for(let x=x0;x<x1-step;x+=step){const p=pixelIndex(width,x,y),px=pixelIndex(width,x+step,y),py=pixelIndex(width,x,y+step),delta=(Math.abs(luminance(data,p)-luminance(data,px))+Math.abs(luminance(data,p)-luminance(data,py)))/2;total+=delta;samples++;if(delta>=30)strong++}
    const mean=total/Math.max(1,samples),ratio=strong/Math.max(1,samples),risk=Math.round(clamp(Math.max(0,mean-9)*2.1+Math.max(0,ratio-.025)*180,0,100));return {risk,meanGradient:Math.round(mean*100)/100,strongDetailRatio:Math.round(ratio*10000)/10000,samples};
  }
  function quadrantMatches(baseSegments,obliqueSegments,id){
    let matches=0;for(const left of baseSegments||[]){if(quadrantId(left.midX,left.midY)!==id)continue;if((obliqueSegments||[]).some(right=>quadrantId(right.midX,right.midY)===id&&left.angleIndex===right.angleIndex&&Math.hypot(left.midX-right.midX,left.midY-right.midY)<=.13&&Math.abs(left.lengthRatio-right.lengthRatio)<=.22))matches++}return matches;
  }
  function analyzeFourQuadrants(baseInput,obliqueInput=null,providedBounds=null,providedConfig={},providedSurface=null){
    const profile=gameProfile(providedConfig.game),config={...DEFAULT_CONFIG,...providedConfig},bounds=providedBounds||detectOuterBounds(baseInput),quality=analyzeQuality(baseInput),surface=providedSurface||analyzeSurface(baseInput,obliqueInput,bounds,config),precisionConfig={...config,minLineRatio:Math.max(.10,config.minLineRatio*.50),houghVoteThreshold:Math.max(18,config.houghVoteThreshold),scratchContrastMin:Math.max(30,config.scratchContrastMin)},precisionBase=detectScratchCandidates(baseInput,bounds,precisionConfig),precisionOblique=obliqueInput?detectScratchCandidates(obliqueInput,detectOuterBounds(obliqueInput),precisionConfig):null,ids=['tl','tr','bl','br'],rows={};
    for(const id of ids){
      const baseSegments=(precisionBase.segments||[]).filter(row=>quadrantId(row.midX,row.midY)===id),obliqueSegments=(precisionOblique?.segments||[]).filter(row=>quadrantId(row.midX,row.midY)===id),confirmed=obliqueInput?quadrantMatches(baseSegments,obliqueSegments,id):0;
      const baseRisk=quadrantSegmentRisk(baseSegments),obliqueRisk=quadrantSegmentRisk(obliqueSegments),candidateRisk=obliqueInput?Math.max(baseRisk,obliqueRisk):baseRisk,scratchRisk=Math.round(clamp(obliqueInput?(confirmed?candidateRisk*.82+confirmed*5:candidateRisk*.15):candidateRisk*.58,0,100)),texture=quadrantTextureRisk(baseInput,bounds,id),surfaceRisk=Math.max(scratchRisk,texture.risk),whitening=quadrantWhitening(baseInput,bounds,id);
      const candidateSegments=baseSegments.length+obliqueSegments.length,obliqueStatus=!obliqueInput?'not_captured':confirmed?'confirmed':candidateSegments===0?'clear_both_angles':'angle_mismatch',risk=Math.round(clamp(Math.max(surfaceRisk,whitening.edgeRisk,whitening.cornerRisk),0,100)),confidence=Math.round(clamp((obliqueInput?58:40)+quality.score*.32+bounds.confidence*.18+Math.min(12,confirmed*4)-(profile.id==='naruto'?8:0),8,profile.confidenceCap));
      rows[id]={id,scratchRisk,surfaceRisk,edgeRisk:whitening.edgeRisk,cornerRisk:whitening.cornerRisk,whiteningRisk:whitening.risk,combinedRisk:risk,confidence,confirmedSegments:confirmed,candidateSegments,baseCandidateSegments:baseSegments.length,obliqueCandidateSegments:obliqueSegments.length,obliqueStatus,obliqueCrossChecked:Boolean(obliqueInput),texture,whitening};
    }
    const risks=ids.map(id=>rows[id].combinedRisk),surfaceRisks=ids.map(id=>rows[id].surfaceRisk),edgeRisks=ids.map(id=>rows[id].edgeRisk),cornerRisks=ids.map(id=>rows[id].cornerRisk),confidences=ids.map(id=>rows[id].confidence),worstRisk=Math.max(...risks),surfaceWorstRisk=Math.max(...surfaceRisks),edgeWorstRisk=Math.max(...edgeRisks),cornerWorstRisk=Math.max(...cornerRisks),meanRisk=risks.reduce((a,b)=>a+b,0)/4,imbalance=Math.max(...risks)-Math.min(...risks),confidence=Math.round(Math.min(...confidences));
    return {version:3,mode:'four-quadrant-oblique-crosscheck',gameProfile:profile.id,precisionConfig:{minLineRatio:precisionConfig.minLineRatio,houghVoteThreshold:precisionConfig.houghVoteThreshold,scratchContrastMin:precisionConfig.scratchContrastMin},quadrants:rows,worstQuadrant:ids.find(id=>rows[id].combinedRisk===worstRisk),worstRisk,surfaceWorstRisk,edgeWorstRisk,cornerWorstRisk,meanRisk:Math.round(meanRisk*10)/10,imbalance,confidence,obliqueCrossChecked:Boolean(obliqueInput),allQuadrantsMeasured:ids.every(id=>rows[id].confidence>=55),learningFeatures:{quadrantWorstRisk:worstRisk,quadrantSurfaceWorstRisk:surfaceWorstRisk,quadrantEdgeWorstRisk:edgeWorstRisk,quadrantCornerWorstRisk:cornerWorstRisk,quadrantMeanRisk:Math.round(meanRisk*10)/10,quadrantImbalance:imbalance,quadrantConfidence:confidence}};
  }

  function eightZoneId(x,y){
    const col=x<.5?0:1,row=clamp(Math.floor(y*4),0,3);
    return `r${row+1}${col===0?'l':'r'}`;
  }
  function eightZoneMeta(id){
    const match=/^r([1-4])([lr])$/.exec(String(id||''));
    if(!match)throw new Error('VisionZoneIdError');
    return {row:Number(match[1])-1,col:match[2]==='l'?0:1,rows:4,cols:2};
  }
  function regionTextureRisk(input,bounds,id){
    const {width,height,data}=validateImage(input),meta=eightZoneMeta(id),cellW=bounds.width/meta.cols,cellH=bounds.height/meta.rows,pad=Math.max(2,Math.round(Math.min(bounds.width,bounds.height)*.018));
    const x0=Math.round(bounds.left+meta.col*cellW)+pad,x1=Math.round(bounds.left+(meta.col+1)*cellW)-pad,y0=Math.round(bounds.top+meta.row*cellH)+pad,y1=Math.round(bounds.top+(meta.row+1)*cellH)-pad;
    const step=Math.max(1,Math.round(Math.min(bounds.width,bounds.height)/430));let total=0,samples=0,strong=0;
    for(let y=y0;y<y1-step;y+=step)for(let x=x0;x<x1-step;x+=step){const p=pixelIndex(width,x,y),px=pixelIndex(width,x+step,y),py=pixelIndex(width,x,y+step),delta=(Math.abs(luminance(data,p)-luminance(data,px))+Math.abs(luminance(data,p)-luminance(data,py)))/2;total+=delta;samples++;if(delta>=32)strong++}
    const mean=total/Math.max(1,samples),ratio=strong/Math.max(1,samples),raw=Math.max(0,mean-10)*1.8+Math.max(0,ratio-.03)*150,risk=Math.round(clamp(raw*.58,0,60));
    return {risk,meanGradient:Math.round(mean*100)/100,strongDetailRatio:Math.round(ratio*10000)/10000,samples};
  }
  function regionWhiteningRisk(input,bounds,id){
    const {width,height,data}=validateImage(input),meta=eightZoneMeta(id),cellW=bounds.width/meta.cols,cellH=bounds.height/meta.rows,x0=Math.round(bounds.left+meta.col*cellW),x1=Math.round(bounds.left+(meta.col+1)*cellW),y0=Math.round(bounds.top+meta.row*cellH),y1=Math.round(bounds.top+(meta.row+1)*cellH),band=Math.max(2,Math.round(Math.min(bounds.width,bounds.height)*.030)),step=Math.max(1,Math.round(Math.min(bounds.width,bounds.height)/440)),reference=[];
    const sample=(x,y)=>{const p=pixelIndex(width,clamp(Math.round(x),0,width-1),clamp(Math.round(y),0,height-1)),lum=luminance(data,p),chr=Math.max(data[p],data[p+1],data[p+2])-Math.min(data[p],data[p+1],data[p+2]);return {lum,chr}};
    const sideX=meta.col===0?bounds.left+band:bounds.right-band;
    for(let y=y0;y<=y1;y+=step)reference.push(sample(sideX,y));
    if(meta.row===0||meta.row===3){const sideY=meta.row===0?bounds.top+band:bounds.bottom-band;for(let x=x0;x<=x1;x+=step)reference.push(sample(x,sideY))}
    const refLum=median(reference.map(row=>row.lum)),refChroma=median(reference.map(row=>row.chr)),natural=refLum>=215&&refChroma<=25;let n=0,white=0,cornerN=0,cornerWhite=0;
    const cornerSpan=Math.max(band*2,Math.round(Math.min(bounds.width,bounds.height)*.105));
    const inspect=(x,y,isCorner)=>{const row=sample(x,y),flag=!natural&&refLum<225&&row.lum>=Math.max(175,refLum+28)&&row.chr<=Math.max(10,Math.min(36,refChroma*.72+10));n++;if(isCorner)cornerN++;if(flag){white++;if(isCorner)cornerWhite++}};
    for(let y=y0;y<=y1;y+=step)for(let d=0;d<band;d+=step){const atTopCorner=meta.row===0&&y-y0<cornerSpan,atBottomCorner=meta.row===3&&y1-y<cornerSpan;inspect(meta.col===0?bounds.left+d:bounds.right-d,y,atTopCorner||atBottomCorner)}
    if(meta.row===0||meta.row===3){for(let x=x0;x<=x1;x+=step)for(let d=0;d<band;d+=step){const atSideCorner=meta.col===0?x-x0<cornerSpan:x1-x<cornerSpan;inspect(x,meta.row===0?bounds.top+d:bounds.bottom-d,atSideCorner)}}
    const ratio=white/Math.max(1,n),cornerRatio=cornerWhite/Math.max(1,cornerN),edgeRisk=Math.round(clamp(ratio*1800,0,100)),cornerRisk=Math.round(clamp(cornerRatio*1600,0,100));
    return {risk:Math.max(edgeRisk,cornerRisk),edgeRisk,cornerRisk,ratio,cornerRatio,whitePixels:white,cornerWhitePixels:cornerWhite,samplePixels:n,naturallyWhite:natural};
  }
  function zoneMatches(baseSegments,obliqueSegments,id){
    let matches=0;for(const left of baseSegments||[]){if(eightZoneId(left.midX,left.midY)!==id)continue;if((obliqueSegments||[]).some(right=>eightZoneId(right.midX,right.midY)===id&&left.angleIndex===right.angleIndex&&Math.hypot(left.midX-right.midX,left.midY-right.midY)<=.10&&Math.abs(left.lengthRatio-right.lengthRatio)<=.18))matches++}return matches;
  }
  function analyzeEightZones(baseInput,obliqueInput=null,providedBounds=null,providedConfig={}){
    const profile=gameProfile(providedConfig.game),config={...DEFAULT_CONFIG,...providedConfig},bounds=providedBounds||detectOuterBounds(baseInput),quality=analyzeQuality(baseInput),precisionConfig={...config,minLineRatio:Math.max(.065,config.minLineRatio*.34),houghVoteThreshold:Math.max(16,config.houghVoteThreshold-1),scratchContrastMin:Math.max(30,config.scratchContrastMin)},base=detectScratchCandidates(baseInput,bounds,precisionConfig),oblique=obliqueInput?detectScratchCandidates(obliqueInput,detectOuterBounds(obliqueInput),precisionConfig):null,ids=['r1l','r1r','r2l','r2r','r3l','r3r','r4l','r4r'],zones={};
    for(const id of ids){
      const baseSegments=(base.segments||[]).filter(row=>eightZoneId(row.midX,row.midY)===id),obliqueSegments=(oblique?.segments||[]).filter(row=>eightZoneId(row.midX,row.midY)===id),confirmed=obliqueInput?zoneMatches(baseSegments,obliqueSegments,id):0,baseRisk=quadrantSegmentRisk(baseSegments),obliqueRisk=quadrantSegmentRisk(obliqueSegments),candidateRisk=obliqueInput?Math.max(baseRisk,obliqueRisk):baseRisk,scratchRisk=Math.round(clamp(obliqueInput?(confirmed?candidateRisk*.84+confirmed*5:candidateRisk*.14):candidateRisk*.56,0,100)),texture=regionTextureRisk(baseInput,bounds,id),whitening=regionWhiteningRisk(baseInput,bounds,id),surfaceRisk=Math.max(scratchRisk,texture.risk),combinedRisk=Math.round(clamp(Math.max(surfaceRisk,whitening.edgeRisk,whitening.cornerRisk),0,100)),candidateSegments=baseSegments.length+obliqueSegments.length,confidence=Math.round(clamp((obliqueInput?56:38)+quality.score*.30+bounds.confidence*.16+Math.min(14,confirmed*4)-(profile.id==='naruto'?8:0),8,profile.confidenceCap));
      zones[id]={id,...eightZoneMeta(id),scratchRisk,surfaceRisk,edgeRisk:whitening.edgeRisk,cornerRisk:whitening.cornerRisk,combinedRisk,confidence,confirmedSegments:confirmed,candidateSegments,baseCandidateSegments:baseSegments.length,obliqueCandidateSegments:obliqueSegments.length,obliqueCrossChecked:Boolean(obliqueInput),texture,whitening};
    }
    const risks=ids.map(id=>zones[id].combinedRisk),surfaceRisks=ids.map(id=>zones[id].surfaceRisk),edgeRisks=ids.map(id=>zones[id].edgeRisk),cornerRisks=ids.map(id=>zones[id].cornerRisk),confidences=ids.map(id=>zones[id].confidence),worstRisk=Math.max(...risks),surfaceWorstRisk=Math.max(...surfaceRisks),edgeWorstRisk=Math.max(...edgeRisks),cornerWorstRisk=Math.max(...cornerRisks),meanRisk=risks.reduce((a,b)=>a+b,0)/8,imbalance=Math.max(...risks)-Math.min(...risks),confidence=Math.round(Math.min(...confidences)),worstZone=ids.find(id=>zones[id].combinedRisk===worstRisk);
    return {version:1,mode:'eight-zone-precision-oblique-crosscheck',gameProfile:profile.id,zoneLayout:'4x2',zones,worstZone,worstRisk,surfaceWorstRisk,edgeWorstRisk,cornerWorstRisk,meanRisk:Math.round(meanRisk*10)/10,imbalance,confidence,obliqueCrossChecked:Boolean(obliqueInput),allZonesMeasured:ids.every(id=>zones[id].confidence>=50),learningFeatures:{eightZoneWorstRisk:worstRisk,eightZoneSurfaceWorstRisk:surfaceWorstRisk,eightZoneEdgeWorstRisk:edgeWorstRisk,eightZoneCornerWorstRisk:cornerWorstRisk,eightZoneMeanRisk:Math.round(meanRisk*10)/10,eightZoneImbalance:imbalance,eightZoneConfidence:confidence}};
  }
  function analyzeGradingHierarchy(baseInput,obliqueInput=null,providedBounds=null,providedConfig={}){
    const bounds=providedBounds||detectOuterBounds(baseInput),quality=analyzeQuality(baseInput),centering=measureCentering(baseInput,bounds,quality),surface=analyzeSurface(baseInput,obliqueInput,bounds,providedConfig),whitening=analyzeWhitening(baseInput,bounds),quadrants=analyzeFourQuadrants(baseInput,obliqueInput,bounds,providedConfig,surface),zones=analyzeEightZones(baseInput,obliqueInput,bounds,providedConfig),surfaceRisk=Math.max(surface.risk,quadrants.surfaceWorstRisk,zones.surfaceWorstRisk),edgeRisk=Math.max(whitening.edgeRisk,quadrants.edgeWorstRisk,zones.edgeWorstRisk),cornerRisk=Math.max(whitening.cornerRisk,quadrants.cornerWorstRisk,zones.cornerWorstRisk),defectRisk=Math.round(clamp(Math.max(surfaceRisk,edgeRisk*.90,cornerRisk*.95),0,100)),confidence=Math.round(clamp(Math.min(quality.score,centering.confidence||0,surface.confidence,quadrants.confidence,zones.confidence),0,99));
    return {version:1,mode:'grading-hierarchy-1-4-8',stageOrder:[1,2,3],stage1:{name:'full-card',quality,centering,surface,whitening},stage2:{name:'four-quadrant',...quadrants},stage3:{name:'eight-zone',...zones},surfaceRisk,edgeRisk,cornerRisk,defectRisk,confidence,allStagesMeasured:Boolean(quality.measurable&&centering.valid&&quadrants.allQuadrantsMeasured&&zones.allZonesMeasured),learningFeatures:{...quadrants.learningFeatures,...zones.learningFeatures,hierarchySurfaceRisk:surfaceRisk,hierarchyEdgeRisk:edgeRisk,hierarchyCornerRisk:cornerRisk,hierarchyDefectRisk:defectRisk,hierarchyConfidence:confidence}};
  }

  function imageElementData(image,maxDimension=1400){
    if(typeof document==='undefined'||!image)throw new Error('VisionBrowserCanvasUnavailable');
    const naturalWidth=Number(image.naturalWidth||image.width),naturalHeight=Number(image.naturalHeight||image.height);
    if(!finite(naturalWidth)||!finite(naturalHeight)||naturalWidth<8||naturalHeight<8)throw new Error('VisionImageSizeError');
    const scale=Math.min(1,maxDimension/Math.max(naturalWidth,naturalHeight)),canvas=document.createElement('canvas');
    canvas.width=Math.max(8,Math.round(naturalWidth*scale));canvas.height=Math.max(8,Math.round(naturalHeight*scale));
    const context=canvas.getContext('2d',{willReadFrequently:true});if(!context)throw new Error('VisionCanvasError');
    context.drawImage(image,0,0,canvas.width,canvas.height);const imageData=context.getImageData(0,0,canvas.width,canvas.height);
    return {width:imageData.width,height:imageData.height,data:imageData.data,canvas};
  }

  return Object.freeze({ENGINE_VERSION,DEFAULT_CONFIG,GAME_PROFILES,gameProfile,analyzeQuality,detectOuterBounds,measureCentering,detectScratchCandidates,analyzeSurface,analyzeWhitening,analyzeFourQuadrants,analyzeEightZones,analyzeGradingHierarchy,imageElementData});
});
