// Exercise the real UI module with a DOM adapter; this is not browser QA.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
class Element{constructor(tag){this.dataset={};this.tagName=tag;this.children=[];this.attributes={};this.value='';this.text=''}
 set textContent(v){this.text=String(v);this.children=[]}get textContent(){return this.text+this.children.map(c=>c.textContent).join('')}
 append(...items){this.children.push(...items)}setAttribute(k,v){this.attributes[k]=v}}
const storage=new Map(),context=vm.createContext({document:{createElement:t=>new Element(t)},crypto:require('node:crypto'),
 localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}});
const {loadModule,storageAdapter}=require('./ui_loader.cjs');
context.localStorage=storageAdapter(context.localStorage||{getItem:()=>null,setItem(){}});context.sessionStorage=storageAdapter(context.sessionStorage||{getItem:()=>null,setItem(){}});
Object.assign(context,loadModule(path.join(__dirname,'../../static/features/style5.js'),context));
const draftStorage=loadModule(path.join(__dirname,'../../static/features/draft_storage.js'),context).localDrafts;const hasDraft=k=>draftStorage.getItem(k)!==null;
const walk=e=>[e,...e.children.flatMap(walk)],field=(h,t)=>walk(h).find(n=>n.attributes['aria-label']===t),button=(h,t)=>walk(h).find(n=>n.tagName==='button'&&n.textContent===t);
const project={project_id:'p1',revision:5,clips:{c1:{variants:{portrait:{effective_settings:{style_preset:'legacy',caption_seed:2026,semantic_emphasis:true}},landscape:{effective_settings:{}}}}}};
let conflict=false,refresh=0;const calls=[];
const api=async(url,data)=>{calls.push({url,data});if(!data)return {...project,revision:6};if(conflict)throw Error('Konflik revisi');return {status:'queued'}};
function mount(id='portrait'){const host=new Element('div');const panel=context.mountStyle5(host,{project,clipId:'c1',variantId:id,api,onChange:()=>refresh++});return {host,panel}}
(async()=>{
 let {host,panel}=mount();assert.equal(calls.length,0,'opening controls runs no jobs or installers');
 field(host,'Preset tipografi').value='rapi';field(host,'Preset tipografi').onchange();
 let key='clipper5-style|p1|c1|portrait';assert(hasDraft(key));
 const before=calls.length;await button(host,'Periksa keterbacaan klip').onclick();assert.equal(calls.length,before,'dirty draft blocks checks');
 conflict=true;await button(host,'Simpan template dan animasi').onclick();assert(hasDraft(key),'conflict preserves draft');assert(host.textContent.includes('Konflik revisi'));
 conflict=false;await button(host,'Muat revisi terbaru untuk draf').onclick();await button(host,'Simpan template dan animasi').onclick();
 assert.equal(calls.at(-1).data.expected_revision,6);assert.equal(calls.at(-1).data.variant_id,'portrait');assert.equal(calls.at(-1).data.operations[0].values.font_main,'dm_sans');assert(!hasDraft(key));
 await button(host,'Periksa keterbacaan klip').onclick();assert.equal(calls.at(-1).data.kind,'style_review');panel.destroy();
 ({host,panel}=mount('landscape'));field(host,'Seed desain').value='7';field(host,'Seed desain').oninput();assert(hasDraft('clipper5-style|p1|c1|landscape'));panel.destroy();
 ({host,panel}=mount('landscape'));assert.equal(field(host,'Seed desain').value,7);await button(host,'Buang draf gaya').onclick();assert(!hasDraft('clipper5-style|p1|c1|landscape'));
 console.log('Stage 5 UI passed: explicit save, ratio scope, draft restoration, conflict preservation/rebase, curated pair, queued reading checks (DOM adapter).');
})().catch(e=>{console.error(e);process.exitCode=1});
