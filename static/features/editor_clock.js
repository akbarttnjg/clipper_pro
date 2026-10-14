// The same half-open microsecond boundary policy as editor_contract.py.
const ticks=value=>Math.round(value*1e6);
const inside=(value,start,end)=>Math.max(ticks(start),Math.min(ticks(end)-1,ticks(value)))/1e6;
export function outputSource(spans,time){
 const row=spans.find(s=>s.start<=time&&time<s.end);if(!row)return null;
 const u=(time-row.start)/(row.end-row.start);
 const source=row.kind==='freeze'?row.source_start:row.reverse?row.source_end-u*(row.source_end-row.source_start):row.source_start+u*(row.source_end-row.source_start);
 return {row,source:inside(source,row.source_start,row.source_end)};
}
export function sourceOutput(spans,source){
 const row=spans.find(s=>s.source_start<=source&&source<s.source_end);if(!row)return null;
 const u=(source-row.source_start)/(row.source_end-row.source_start);
 const time=row.kind==='freeze'?row.start:row.start+(row.reverse?1-u:u)*(row.end-row.start);
 return {row,time:inside(time,row.start,row.end)};
}
