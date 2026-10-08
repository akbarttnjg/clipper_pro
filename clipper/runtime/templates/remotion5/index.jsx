import React,{useEffect,useState} from 'react';
import {registerRoot,Composition,useCurrentFrame,useVideoConfig,delayRender,continueRender} from 'remotion';
import {sampleAt,activePhrases} from './caption_math.mjs';
const Captions=({plan,fonts})=>{
 const frame=useCurrentFrame(),{fps}=useVideoConfig(),t=frame/fps;
 const [handle]=useState(()=>delayRender('Bundled caption fonts'));
 useEffect(()=>{let live=true;Promise.all(Object.entries(fonts).map(async([key,url])=>{
   const font=new FontFace('Clipper-'+key,`url(${url})`);await font.load();document.fonts.add(font);
 })).then(()=>{if(live)continueRender(handle)});return()=>{live=false}},[fonts,handle]);
 return <svg xmlns="http://www.w3.org/2000/svg" width={plan.width} height={plan.height} style={{background:'transparent'}}>
  {activePhrases(plan,t).flatMap(p=>p.words.map((w,i)=>{const a=sampleAt(w,t-p.start);
   return <g key={p.start+'-'+i} opacity={a.opacity} transform={`translate(${w.x+a.dx} ${w.y+a.dy}) scale(${a.scale})`}>
    <text x="0" y={w.baseline-w.y} textAnchor="middle" fontFamily={'Clipper-'+w.font_id} fontSize={w.size}
     fontWeight={w.bold?700:400} fontStyle={w.italic?'italic':'normal'} fill={w.color||'#FFFFFF'}
     stroke={plan.contrast?'#15110D':'none'} strokeWidth={plan.contrast?Math.min(plan.width,plan.height)/1080*2.2:0}
     paintOrder="stroke" style={{filter:a.blur?`blur(${a.blur}px)`:'none',whiteSpace:'pre'}}>{w.text}</text>
   </g>;}))}
 </svg>;
const Root=()=> <Composition id="ClipperCaptions" component={Captions} durationInFrames={30} fps={30} width={320} height={180}
 defaultProps={{plan:{width:320,height:180,phrases:[]},fonts:{},duration_frames:30,fps:30}}
 calculateMetadata={({props})=>({durationInFrames:props.duration_frames,fps:props.fps,width:props.plan.width,height:props.plan.height})}/>;
registerRoot(Root);
