import React,{useEffect,useState} from 'react';
import {registerRoot,Composition,useCurrentFrame,useVideoConfig,delayRender,continueRender} from 'remotion';
import {sampleAt,activePhrases} from './caption_math.mjs';

const Captions=({plan,fonts})=>{
 const frame=useCurrentFrame(),{fps}=useVideoConfig(),t=frame/fps;
 const [handle]=useState(()=>delayRender('Bundled caption fonts'));
 useEffect(()=>{
  let live=true;
  Promise.all(Object.entries(fonts).map(async([key,url])=>{
   const font=new FontFace('Clipper-'+key,`url(${url})`);
   await font.load();document.fonts.add(font);
  })).then(()=>{if(live)continueRender(handle)});
  return()=>{live=false};
 },[fonts,handle]);

 const nodes=activePhrases(plan,t).flatMap(phrase=>phrase.words.map((word,index)=>{
  const sample=sampleAt(word,t-phrase.start),contrast=plan.contrast_style;
  const filters=[
   sample.blur?`blur(${sample.blur}px)`:null,
   plan.contrast&&contrast?.shadow?`drop-shadow(${contrast.shadow}px ${contrast.shadow}px 0 rgba(0,0,0,${contrast.shadow_opacity}))`:null,
  ].filter(Boolean).join(' ');
  return React.createElement('g',{
   key:phrase.start+'-'+index,opacity:sample.opacity,
   transform:`translate(${word.x+sample.dx} ${word.y+sample.dy}) scale(${sample.scale})`,
  },React.createElement('text',{
   x:0,y:word.baseline-word.y,textAnchor:'middle',fontFamily:'Clipper-'+word.font_id,fontSize:word.size,
   fontWeight:word.bold?700:400,fontStyle:word.italic?'italic':'normal',fill:sample.color||word.color||'#FFFFFF',
   stroke:plan.contrast?(contrast?.outline_color||'#15110D'):'none',strokeOpacity:contrast?.outline_opacity??1,
   strokeWidth:plan.contrast?(contrast?.outline??Math.min(plan.width,plan.height)/1080*2.2):0,
   paintOrder:'stroke',style:{filter:filters||'none',whiteSpace:'pre'},
  },word.text));
 }));
 return React.createElement('svg',{
  xmlns:'http://www.w3.org/2000/svg',width:plan.width,height:plan.height,style:{background:'transparent'},
 },nodes);
};

const Root=()=>React.createElement(Composition,{
 id:'ClipperCaptions',component:Captions,durationInFrames:30,fps:30,width:320,height:180,
 defaultProps:{plan:{width:320,height:180,phrases:[]},fonts:{},duration_frames:30,fps:30},
 calculateMetadata:({props})=>({durationInFrames:props.duration_frames,fps:props.fps,width:props.plan.width,height:props.plan.height}),
});
registerRoot(Root);
