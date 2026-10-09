// Real module behavior through a DOM adapter; native browser QA is separate.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
class Element{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.value='';this.text=''}
 set textContent(v){this.text=String(v);this.children=[]}get textContent(){return this.text+this.children.map(c=>c.textContent).join('')}
 append(...items){this.children.push(...items)}prepend(...items){this.children.unshift(...items)}setAttribute(k,v){this.attributes[k]=v}}
const context=vm.createContext({document:{createElement:t=>new Element(t)},crypto:require('node:crypto')});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/features/batch7.js'),'utf8').replace(/export /g,''),context);
const walk=e=>[e,...e.children.flatMap(walk)],button=(h,t)=>walk(h).find(n=>n.tagName==='button'&&n.textContent===t);
const project={project_id:'p1',revision:5,clips:{c1:{title:'Satu'},c2:{title:'Dua',included:false}},batch:{selected_clips:1,timelines:2,ready:false,blockers:[{title:'Satu',variant_id:'landscape',message:'Render dahulu'}]}};
let dirty=false,conflict=false,refresh=0;const calls=[];
const api=async(url,data)=>{calls.push({url,data});if(conflict)throw Error('Konflik revisi');return {jobs:[{}],skipped:[]}};
const mount=()=>{const host=new Element('div');context.mountBatch7(host,{project,api,onChange:()=>refresh++,hasDrafts:()=>dirty});return host};
(async()=>{
 let host=mount();assert.equal(calls.length,0);assert(button(host,'Buat satu paket seluruh pilihan').disabled,'missing ratio blocks aggregate export');
 dirty=true;await button(host,'Render seluruh pilihan · 9:16 + 16:9').onclick();assert.equal(calls.length,0,'dirty draft blocks batch');
 dirty=false;await button(host,'Render seluruh pilihan · 9:16 + 16:9').onclick();assert.equal(calls.at(-1).url,'/projects/p1/batch-render');assert.equal(calls.at(-1).data.expected_revision,5);
 const checkbox=walk(host).find(n=>n.attributes['aria-label']==='Sertakan Dua');checkbox.checked=true;conflict=true;await checkbox.onchange();assert.equal(checkbox.checked,false,'conflict restores saved inclusion');
 conflict=false;await button(host,'Terapkan preset pada seluruh pilihan').onclick();assert.equal(calls.at(-1).data.operations[0].op,'preset_batch');
 project.batch.ready=true;host=mount();await button(host,'Buat satu paket seluruh pilihan').onclick();assert.equal(calls.at(-1).data.kind,'export_project');assert.equal(calls.at(-1).data.options.mode,'hybrid');
 assert(refresh>=3);console.log('Batch UI passed: selection conflict, draft guard, missing-ratio gate, explicit preset, atomic batch endpoint and aggregate export (DOM adapter).');
})().catch(e=>{console.error(e);process.exitCode=1});
