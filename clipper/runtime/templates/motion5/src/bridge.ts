import {Renderer,Vector2} from '@motion-canvas/core';
import project from './project?project';
import data from '../request.json';
const face=new FontFace('ClipperExplanation',`url(${data.font_url})`);
await face.load();document.fonts.add(face);
const renderer=new Renderer(project);
const settings={name:'ClipperExplanation',size:new Vector2(1280,720),resolutionScale:1,colorSpace:'srgb' as const,
 background:'#11151b',range:[0,data.duration] as [number,number],fps:data.fps,exporter:{name:'@motion-canvas/core/image-sequence',options:{}}};
(window as any).clipperFrame=async(frame:number)=>{
 await renderer.renderFrame(settings,frame/data.fps);
 return renderer.stage.finalBuffer.toDataURL('image/png').split(',')[1];
};
(window as any).clipperReady=true;
