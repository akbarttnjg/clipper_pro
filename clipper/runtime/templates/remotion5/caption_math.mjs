// Match frame-held ASS transforms; design choices are already saved in the plan.
export function sampleAt(word,t){
 const frames=word.keyframes||[];
 if(!frames.length)return {scale:1,dx:0,dy:0,opacity:1,blur:0};
 let sample=frames[0];for(const f of frames){if(f.t>t+1e-6)break;sample=f}return sample;
}
export function activePhrases(plan,t){return plan.phrases.filter(p=>p.start<=t+1e-6&&t<p.end-1e-6)}
