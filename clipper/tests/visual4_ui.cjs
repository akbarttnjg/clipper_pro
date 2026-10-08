// Real module exercised with a DOM adapter. This does not claim browser rendering.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.value='';this.disabled=false;this.currentTime=0;this.readyState=1;this.videoWidth=640;this.videoHeight=360;this.text='';}
 set textContent(v){this.text=String(v);this.children=[]}get textContent(){return this.text+this.children.map(c=>c.textContent).join('')}
 append(...rows){for(const r of rows){r.parent=this;this.children.push(r)}}replaceChildren(...rows){this.children=[];this.append(...rows)}
 setAttribute(k,v){this.attributes[k]=v}removeAttribute(k){delete this.attributes[k]}
 getContext(){return {clearRect(){},drawImage(){},strokeRect(){}}}getBoundingClientRect(){return {left:0,top:0,width:100,height:100}}
 pause(){this.paused=true}load(){}setPointerCapture(){}
}
const document={createElement:t=>new Element(t)},storage=new Map();
class Image{set src(v){this.url=v;this.onload?.()}}
const context=vm.createContext({document,Image,console,structuredClone,crypto:require('node:crypto'),localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/features/visual4.js'),'utf8').replace(/export /g,''),context);
const plain=v=>JSON.parse(JSON.stringify(v)),walk=e=>[e,...e.children.flatMap(walk)],field=(r,t)=>walk(r).find(e=>e.attributes['aria-label']===t),button=(r,t)=>walk(r).find(e=>e.tagName==='button'&&e.textContent===t);
let project={project_id:'p1',revision:5,source:{url:'/source.mp4'},clips:{c1:{start:10,end:20,variants:{
 portrait:{effective_settings:{},visual_report:{source_size:[640,360],
  summary:{sample_count:20,active_speaker:{status:'unavailable'}},shots:[{
   source_start:10,source_end:20,frame_time:12,poster_url:'/frame.jpg',composition_reason:'Satu pembicara',
   visual:{speaker:{tracks:[{track_id:'face-0001',box:[100,50,50,60]}]},ocr:[]}
  }]}},landscape:{effective_settings:{}}
}}}};
const calls=[];let conflict=false,refresh=0,hold=null;
async function api(url,data){calls.push({url,data});if(hold)await hold;
 if(url==='/projects/p1')return structuredClone(project);
 if(url.includes('/jobs'))return {status:'queued'};
 if(url==='/changes'){
  if(conflict||data.expected_revision!==project.revision)throw Error('Konflik revisi');
  const v=project.clips[data.clip_id].variants[data.variant_id];for(const op of data.operations){
   if(op.op==='visual_controls')v.visual_controls={...(v.visual_controls||{}),...op.values};
   if(op.op==='settings')v.effective_settings={...v.effective_settings,...op.values};
  }project.revision++;return {revision:project.revision};
 }throw Error('Unexpected '+url);
}
const mount=(variantId='portrait')=>{let host=new Element('div'),panel=context.mountVisual4(host,{project:structuredClone(project),clipId:'c1',variantId,api,onChange:()=>{refresh++}});return {host,panel}};
const draw=h=>{const c=walk(h).find(n=>n.tagName==='canvas');c.onpointerdown({clientX:80,clientY:80,pointerId:1});c.onpointerup({clientX:10,clientY:20,pointerId:1})};
(async()=>{
 assert.deepEqual(plain(context.normalizedBox({x:80,y:90},{x:10,y:20})),[10,20,70,70]);
 assert.deepEqual(plain(context.normalizedBox({x:-10,y:-20},{x:110,y:120})),[0,0,100,100]);
 let {host,panel}=mount();assert.equal(calls.length,0,'opening panel performs no installs or jobs');
 assert(host.textContent.includes('bobot lokal belum siap'),'missing weights never show ready');
 draw(host);let key='clipper4-visual-draft|p1|c1|portrait';assert(storage.has(key));
 conflict=true;await button(host,'Simpan area pada rasio ini').onclick();assert(storage.has(key),'conflict preserves geometry draft');assert(host.textContent.includes('Konflik revisi'));
 project.revision++;project.clips.c1.variants.portrait.visual_controls={pins:[{id:'other-user',start:10,end:20,box:[0,0,30,40],kind:'crop'}]};conflict=false;
 await button(host,'Muat revisi terbaru untuk draf').onclick();await button(host,'Simpan area pada rasio ini').onclick();
 const request=calls.at(-1).data;assert.equal(request.expected_revision,6);assert.equal(request.variant_id,'portrait');assert.equal(request.operations[0].values.pins.length,2,'rebase preserves newest saved pins');
 assert.deepEqual(plain(request.operations[0].values.pins[1].box),[10,20,70,60]);assert(!storage.has(key));assert.equal(project.clips.c1.variants.landscape.visual_controls,undefined);
 panel.destroy();assert.equal(host.children.length,0);
 ({host,panel}=mount());draw(host);await button(host,'Simpan analisis visual').onclick();assert(storage.has(key),'unrelated settings never discard a drawn area');panel.destroy();
 ({host,panel}=mount());assert(host.textContent.includes('Draf area dipulihkan'));await button(host,'Buang draf area').onclick();assert(!storage.has(key));
 const canvas=walk(host).find(e=>e.tagName==='canvas');canvas.onpointerdown({clientX:20,clientY:20,pointerId:2});canvas.onpointercancel();canvas.onpointerup({clientX:90,clientY:90,pointerId:2});assert.equal(field(host,'Area x y lebar tinggi dalam persen').value,'');
 draw(host);field(host,'Rentang mask SAM').value='range';field(host,'Area berlaku mulai (detik sumber)').value='10';field(host,'Area berlaku sampai (detik sumber)').value='18';
 const count=calls.length;await button(host,'Simpan area mask').onclick();assert.equal(calls.length,count,'oversized SAM range stops before write');
 field(host,'Area berlaku sampai (detik sumber)').value='14';await button(host,'Simpan area mask').onclick();assert.equal(calls.at(-1).data.operations[0].values.sam_time,12);assert.deepEqual(plain(calls.at(-1).data.operations[0].values.sam_span),[10,14]);
 panel.destroy();({host,panel}=mount('landscape'));await button(host,'Analisis visual klip').onclick();assert.equal(calls.at(-1).data.variant_id,'landscape');assert.equal(calls.at(-1).data.kind,'visual_review');
 let release;hold=new Promise(r=>release=r);const old=refresh,pending=button(host,'Simpan pilihan pembicara').onclick();panel.destroy();release();await pending;assert.equal(refresh,old,'late save cannot reopen destroyed panel');hold=null;
 console.log('Stage 4 UI passed: source geometry, ratio scope, conflict draft, explicit rebase, preserved settings draft, SAM budget, queued analysis, destruction (DOM adapter).');
})().catch(e=>{console.error(e);process.exitCode=1});
