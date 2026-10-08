import {makeScene2D,Rect,Txt} from '@motion-canvas/2d';
import {createRef,all,waitFor} from '@motion-canvas/core';
import data from '../request.json';
export default makeScene2D(function* (view){
 view.fill('#11151b');const card=createRef<Rect>();
 view.add(<Rect ref={card} opacity={0} y={25}>
  {(data.panels || [{lines:data.lines,font_size:data.font_size,y:360,height:400}]).map(panel =>
   <Rect width={1120} height={panel.height} radius={24} fill="#1d2937" y={panel.y-360}>
    <Txt text={panel.lines.join('\n')} fontSize={panel.font_size} fill={data.accent || '#f6cf69'} fontFamily="ClipperExplanation" textAlign="center" />
   </Rect>)}
 </Rect>);
 yield* all(card().opacity(1,.18),card().position.y(0,.18));
 yield* waitFor(Math.max(0,data.duration-.36));yield* card().opacity(0,.18);
});
