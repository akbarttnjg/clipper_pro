import React from 'react';
import {AbsoluteFill, Composition, interpolate, registerRoot, useCurrentFrame} from 'remotion';

const Sample: React.FC = () => {
  const frame = useCurrentFrame();
  return React.createElement(AbsoluteFill, {
    style: {backgroundColor: '#14251e', color: '#edeee7', fontFamily: 'sans-serif',
      alignItems: 'center', justifyContent: 'center', fontSize: 25,
      opacity: interpolate(frame, [0, 8], [0, 1], {extrapolateRight: 'clamp'})},
  }, 'Clipper Studio · Tahap 2');
};
const Root = () => React.createElement(Composition, {
  id: 'ClipperSample', component: Sample, durationInFrames: 24,
  fps: 24, width: 320, height: 180,
});
registerRoot(Root);
