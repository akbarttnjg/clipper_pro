// Exercise the actual Stage 3 component in a DOM adapter; no Chromium/model claim.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.listeners={};this.value='';this.checked=false;this.disabled=false;this.text='';this.classList={add:()=>{}};this.readyState=1;this.currentTime=0;}
 set textContent(v){this.text=String(v);this.children=[]}get textContent(){return this.text+this.children.map(c=>c.textContent).join('')}
 append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n)}}replaceChildren(...nodes){this.children=[];this.append(...nodes)}
 setAttribute(k,v){this.attributes[k]=v}addEventListener(k,fn){(this.listeners[k]??=[]).push(fn)}
 showModal(){this.open=true}close(){this.open=false;(this.listeners.close||[]).forEach(fn=>fn({}))}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this)}
 play(){this.paused=false;return Promise.resolve()}pause(){this.paused=true}
}
const body=new Element('body'),document={body,createElement:tag=>new Element(tag)};
const storage=new Map();const context=vm.createContext({document,console,URLSearchParams,crypto:require('node:crypto'),localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/features/transcript3.js'),'utf8').replace(/export /g,''),context);
const walk=e=>[e,...e.children.flatMap(walk)],btn=(root,label)=>walk(root).find(n=>n.tagName==='button'&&n.textContent===label),field=(root,label)=>walk(root).find(n=>n.attributes['aria-label']===label);
const flush=()=>new Promise(r=>setImmediate(r));
let project={project_id:'p',revision:1,settings:{},source:{url:'/source.mp4',info:{duration:120}},clips:{c:{start:0,end:20,title:'Cerita'}}};
let ws=[{word_id:0,word:'0,01',heard:'0,01',start:1,end:1.5},{word_id:1,word:'halo dunia',heard:'halo',start:2,end:3,source_word_ids:[1]}];
let report={revision:1,transcript_id:'take',transcript_revision:0,alignment:{message:'Model lokal belum dipilih'},coverage:{speech_segments:3,reviewed_segments:2,pending_segments:1},chapters:[],speech_reports:{},restored:{},rejection_total:1,next_offset:null,rejections:[{rejection_id:'r1',code:'incomplete',title:'Cerita cadangan',detail:'Penutup belum utuh',start:40,end:55}]};
const calls=[];let failSave=false,hold=false,release;
async function api(url,data){calls.push({url,data});if(url==='/correction-review')return {reviews:data.operations.filter(o=>o.op==='correct_word').map((o,i)=>({requires_confirmation:o.after==='0,1',before:'0,01',after:o.after,operation_index:i,categories:['angka'],confirmation_stamp:'bounded-approval'}))};
 if(url==='/changes'){
  if(failSave)throw Error('Konflik revisi; draf tetap tersimpan');
  const op=data.operations[0];if(op.op==='correct_word'){if(op.after==='0,1')assert.equal(op.fact_confirmation,'bounded-approval');ws.find(w=>w.word_id===op.word_id).word=op.after;report.transcript_revision++}
  if(op.op==='align_words'){const w=ws.find(w=>w.word_id===op.origin_word_ids[0]);w.aligned_words=op.words;w.alignment_method='manual';report.transcript_revision++}
  if(op.op==='restore_rejected'){report.restored.r1='restored';project.clips.restored={start:op.start,end:op.end,title:'Manual'}}
  project.revision++;report.revision=project.revision;return {revision:project.revision,status:'ready'};
 }
 if(url.includes('/jobs'))return {message:'Proses masuk antrean'};
 if(url.includes('/words?')){if(hold)await new Promise(r=>release=r);const q=new URLSearchParams(url.split('?')[1]);return {revision:project.revision,transcript_id:'take',transcript_revision:report.transcript_revision,offset:Number(q.get('offset')),total:10001,next_offset:Number(q.get('offset'))===0?60:null,words:structuredClone(ws)}}
 if(url.includes('/stage3?'))return structuredClone(report);
 if(url==='/projects/p')return structuredClone(project);
 throw Error('Unexpected '+url);
}
(async()=>{
 const root=new Element('div');body.append(root);const panel=context.mountTranscript3(root,{api,project});await flush();
 assert(calls.every(c=>!c.data),'opening review never starts installs, jobs or writes');
 assert(calls.some(c=>c.url.includes('limit=60')),'full transcript stays paged');
 assert.equal(walk(root).filter(n=>n.className==='stage3-word').length,2);
 let article=walk(root).find(n=>n.className==='stage3-word'),text=field(article,'Teks tampilan');text.value='0,1';text.oninput();
 let saving=btn(article,'Simpan teks').onclick();await flush();let facts=walk(body).find(n=>n.tagName==='dialog');assert(facts.open);assert(btn(facts,'Setujui dan simpan').disabled);
 await btn(facts,'Kembali ke draf').onclick();await saving;assert.equal(calls.filter(c=>c.url==='/changes').length,0);assert(storage.get('clipper-stage3-drafts').includes('0,1'));
 saving=btn(article,'Simpan teks').onclick();await flush();facts=walk(body).find(n=>n.tagName==='dialog');const check=walk(facts).find(n=>n.type==='checkbox');check.checked=true;check.onchange();assert(!btn(facts,'Setujui dan simpan').disabled);await btn(facts,'Setujui dan simpan').onclick();await saving;
 assert.equal(ws[0].word,'0,1');assert(!storage.get('clipper-stage3-drafts').includes('word:take:[0]'));
 article=walk(root).filter(n=>n.className==='stage3-word')[1];assert(article.textContent.includes('Timing frasa; kata belum diselaraskan'));
 await btn(article,'Simpan timing manual').onclick();assert(!calls.some(c=>c.data?.operations?.[0].op==='align_words'));
 for(const [label,value] of [['Mulai halo','2.0'],['Akhir halo','2.3'],['Mulai dunia','2.6'],['Akhir dunia','3.0']]){const f=field(article,label);f.value=value;f.oninput()}
 await btn(article,'Simpan timing manual').onclick();assert.equal(ws[1].aligned_words[1].start,2.6);
 const rejected=walk(root).find(n=>n.tagName==='details'&&n.textContent.includes('Cerita cadangan'));field(rejected,'Mulai kandidat').value='39.5';await btn(rejected,'Pulihkan dengan batas ini').onclick();
 assert.equal(project.clips.restored.start,39.5);assert(calls.some(c=>c.data?.operations?.[0].rejection_id==='r1'));
 article=walk(root).filter(n=>n.className==='stage3-word')[1];text=field(article,'Teks tampilan');text.value='halo sahabat';text.oninput();failSave=true;await btn(article,'Simpan teks').onclick();assert(storage.get('clipper-stage3-drafts').includes('halo sahabat'));failSave=false;
 const video=walk(root).find(n=>n.tagName==='video');await btn(article,'0:02.00–0:03.00 · Dengar').onclick();video.currentTime=5.1;video.ontimeupdate();assert(video.paused,'context playback stops at requested source end');
 hold=true;const pending=panel.refresh();await flush();panel.destroy();release();await pending;assert.equal(root.children.length,0,'late response cannot reopen destroyed panel');
 const other=new Element('div');body.append(other);hold=false;const scoped=context.mountTranscript3(other,{api,project,clipId:'c'});await flush();await btn(other,'Buka seluruh transkrip').onclick();assert(calls.at(-3).url.includes('clip_id=&whole=true'),'source view excludes clip-only overlays');scoped.destroy();
 console.log('Stage 3 UI: fact approval/cancel, paged source, measured timing, rejected restoration, conflict drafts, bounded playback, late-response guards passed (DOM adapter).');
})().catch(e=>{console.error(e);process.exitCode=1});
