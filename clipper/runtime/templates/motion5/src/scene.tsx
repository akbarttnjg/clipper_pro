import {makeScene2D,Rect,Txt} from '@motion-canvas/2d';
import {createRef,all,waitFor} from '@motion-canvas/core';
import data from '../request.json';
export default makeScene2D(function* (view){
 view.fill('#11151b');const card=createRef<Rect>();
 view.add(<Rect ref={card} width={1120} height={400} radius={24} fill="#1d2937" opacity={0} y={25}>
  <Txt text="DARI UCAPAN SUMBER" y={-145} fontSize={25} fill="#a7b3c7" fontFamily="ClipperExplanation" />
  <Txt text={data.lines.join('\n')} y={0} fontSize={data.font_size} fill="#f6cf69" fontFamily="ClipperExplanation" textAlign="center" />
  <Txt text="KUTIPAN · TANPA DATA TAMBAHAN" y={145} fontSize={22} fill="#a7b3c7" fontFamily="ClipperExplanation" />
 </Rect>);
 yield* all(card().opacity(1,.18),card().position.y(0,.18));
 yield* waitFor(Math.max(0,data.duration-.36));yield* card().opacity(0,.18);
});
