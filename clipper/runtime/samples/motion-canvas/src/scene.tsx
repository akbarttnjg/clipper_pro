import {Circle, makeScene2D, Txt} from '@motion-canvas/2d';
import {all, createRef, waitFor} from '@motion-canvas/core';
export default makeScene2D(function* (view) {
  const circle = createRef<Circle>();
  view.fill('#14251e');
  view.add(<Circle ref={circle} size={20} fill="#a8cfb5" x={-200} />);
  view.add(<Txt text="Clipper · Tahap 2" fill="#edeee7" y={-120} fontSize={48} />);
  yield* all(circle().position.x(200, 1), circle().size(100, 1));
  yield* waitFor(1);
});
