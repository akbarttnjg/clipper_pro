'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),path=require('node:path');const auditRoot=process.env.CLIPPER_AUDIT_ROOT||path.resolve(__dirname,'../..'); const {loadModule}=require(path.join(auditRoot,'clipper/tests/ui_loader.cjs'));
class Node{constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this._text='';this.value='';this.checked=false;this.disabled=false;}append(...c){this.children.push(...c)}replaceChildren(...c){this.children=[];this.append(...c)}get textContent(){return this._text+this.children.map(n=>n.textContent).join(' ')}set textContent(v){this._text=String(v);this.children=[]}setAttribute(k,v){this.attrs[k]=v}click(){return this.onclick?.()}}
const all=n=>[n,...n.children.flatMap(all)];const st=m=>({getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,String(v)),removeItem:k=>m.delete(k),key:i=>[...m.keys()][i]??null,get length(){return m.size}});
function runtime(shared=new Map(),tab='A'){const c=vm.createContext({console,document:{createElement:t=>new Node(t)},window:{name:'clipper-m1:'+tab},localStorage:st(shared),sessionStorage:st(new Map()),crypto:require('node:crypto'),URL,URLSearchParams,Blob,JSON,Map,Set,Number,Math,structuredClone,setTimeout});const root=path.resolve(path.join(auditRoot,'clipper/tests'),'../../static/features');return {module:loadModule(root+'/finishing5.js',c),drafts:loadModule(root+'/draft_storage.js',c).localDrafts}}
const project={project_id:'p',revision:1,settings:{},clips:{c:{variants:{portrait:{},landscape:{}}}}};
function state(){const s={requests:[],fail:false,style:{font_main:'dm_sans',font_accent:'dm_serif_italic',base_hex:'#FFFFFF',accent_hex:'#F6CF69',stroke_hex:'#141821',shadow_hex:'#000000',glow_hex:'#F6CF69',stroke_px:1.8,shadow_px:2,glow_px:0,caption_backdrop:true,caption_align:'auto',caption_position:'auto',caption_scale:1,caption_seed:2026,caption_renderer:'ass',motion_intensity:'balanced',semantic_emphasis:true,accent_font:true,caption_template_policy:'auto',template_id:'editorial',granularity:'phrase',karaoke:false,emoji:false,emoji_map:[],speaker_color:false,speaker_labels:false,speaker_styles:[],fallback_fonts:['dejavu'],minimum_glyph_px:14,display_width_px:360,motion_budget:.03,censor_mode:'off',censor_terms:[],censor_approved:false,source_caption_mode:'avoid',source_captions:[],manual_panel:null,builder:null}};
s.snapshot=()=>({enabled:true,revision:1,style:structuredClone(s.style),origins:{},presets:[{id:'editorial',name:'Editorial'},{id:'social',name:'Sosial'}],templates:[{id:'editorial',name:'Editorial'}],fonts:[{id:'dm_sans',label:'DM Sans'},{id:'dm_serif_italic',label:'Serif'}],assets:[],kits:[],decorations:[],gallery:{items:[]}});
s.api=async(route,data)=>{s.requests.push({route,data});if(route.includes('?'))return s.snapshot();if(!data)return {...project,revision:2};if(s.fail)throw Error('409 konflik; draf dipertahankan');if(route.endsWith('/diff'))return {effective_style:{...s.style,font_main:'montserrat'}};return {status:'ready'}};return s}
const button=(h,t)=>{const n=all(h).find(n=>n.tag==='button'&&n.textContent===t);assert(n,'missing '+t);return n};const field=(h,t)=>{const n=all(h).find(n=>n.attrs['aria-label']===t);assert(n,'missing '+t);return n};const type=(n,v)=>{n.value=v;n.oninput?.()};async function mount(r=runtime(),s=state(),extra={}){const host=new Node('main');const handle=await r.module.mountFinishing5(host,{project,clipId:'c',variantId:'portrait',api:s.api,...extra});return {r,s,host,handle}}

(async()=>{
 const reports=[];
 for(const scenario of ['new-field','same-field','revert']){
  const r=runtime(),s=state();let resolve;const gate=new Promise(ok=>resolve=ok),api=s.api;
  s.api=async(route,data)=>{if(route==='/changes'){s.requests.push({route,data});await gate;return {revision:2}}return api(route,data)};
  const m=await mount(r,s);type(field(m.host,'Warna utama'),'#EEEEEE');
  const saving=button(m.host,'Simpan perubahan M5').onclick();await Promise.resolve();
  const label=scenario==='new-field'?'Budget gerak':'Warna utama',value=scenario==='new-field'?'0.040001':scenario==='same-field'?'#AABBCC':'#FFFFFF';
  type(field(m.host,label),value);resolve();await saving;
  const key='clipper-m5-fields|p|c|portrait',after=JSON.parse(r.drafts.getItem(key)),submitted=s.requests.find(x=>x.route==='/changes').data;
  const name=scenario==='new-field'?'motion_budget':'base_hex';assert.equal(after.fields[name],value);assert.equal(after.revision,2);
  assert.deepEqual(Object.keys(submitted.operations[0].values),['base_hex']);
  // Saving the remainder uses the advanced revision and exact preserved value.
  await button(m.host,'Simpan perubahan M5').onclick();assert.equal(s.requests.filter(x=>x.route==='/changes')[1].data.expected_revision,2);assert.equal(r.drafts.getItem(key),null);
  reports.push({scenario,after,submitted});m.handle.destroy();
 }
 const r=runtime(),s=state();let resolve;const gate=new Promise(ok=>resolve=ok),api=s.api;
 s.api=async(route,data)=>{if(route==='/changes'){await gate;return {revision:2}}return api(route,data)};
 const mounted=await mount(r,s);type(field(mounted.host,'Warna utama'),'#EEEEEE');const saving=button(mounted.host,'Simpan perubahan M5').onclick();await Promise.resolve();mounted.handle.destroy();
 const key='clipper-m5-fields|p|c|portrait';r.drafts.setItem(key,JSON.stringify({revision:1,fields:{base_hex:'#AABBCC',motion_budget:'0.050001'}}));resolve();await saving;
 assert.deepEqual(JSON.parse(r.drafts.getItem(key)),{revision:2,fields:{base_hex:'#AABBCC',motion_budget:'0.050001'}});
 reports.push({scenario:'remounted-panel',after:JSON.parse(r.drafts.getItem(key))});
 console.log(JSON.stringify(reports));console.log('PASS M5 pending-save: new field, same field, revert, and revision-aware retry');
})().catch(e=>{console.error(e);process.exitCode=1});
