// Match frame-held ASS transforms; design choices are already saved in the plan.
export function sampleAt(word,t){
 const frames=word.keyframes||[];
 if(!frames.length){
  const fade=word.fade_seconds||0,duration=word.phrase_duration;
  const opacity=fade?Math.max(0,Math.min(1,t/fade,(duration-t)/fade)):1;
  const change=word.color_transition;
  const progress=change?Math.max(0,Math.min(1,(t-change.start)/change.duration)):1;
  const first=word.initial_color||word.color,last=word.color;
  let color=last;
  if(first&&last&&/^#[0-9a-f]{6}$/i.test(first)&&/^#[0-9a-f]{6}$/i.test(last)){
   color='#'+[1,3,5].map(i=>Math.round(parseInt(first.slice(i,i+2),16)*(1-progress)+parseInt(last.slice(i,i+2),16)*progress).toString(16).padStart(2,'0')).join('');
  }
  return {scale:1,dx:0,dy:0,opacity,blur:0,...(color?{color}:{})};
 }
 let sample=frames[0];for(const f of frames){if(f.t>t+1e-6)break;sample=f}return sample;
}
export function activePhrases(plan,t){return plan.phrases.filter(p=>p.start<=t+1e-6&&t<p.end-1e-6)}
