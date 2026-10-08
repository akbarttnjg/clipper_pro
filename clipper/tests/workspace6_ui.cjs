// Real UI handlers under a DOM adapter. This is not a native browser test.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
class Element{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.value='';this.text='';this.checked=false}
 set textContent(v){this.text=String(v);this.children=[]}get textContent(){return this.text+this.children.map(c=>c.textContent).join('')}
 append(...items){this.children.push(...items)}setAttribute(k,v){this.attributes[k]=v}}
const storage=new Map(),context=vm.createContext({document:{createElement:t=>new Element(t)},crypto:require('node:crypto'),
 URLSearchParams,localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/features/workspace6.js'),'utf8').replace(/export /g,''),context);
const walk=e=>[e,...e.children.flatMap(walk)],field=(h,t)=>walk(h).find(n=>n.attributes['aria-label']===t),button=(h,t)=>walk(h).find(n=>n.tagName==='button'&&n.textContent===t);
const project={project_id:'p1',revision:4,exports:[],clips:{c1:{variants:{portrait:{effective_settings:{style_preset:'ekspresif',caption_seed:2026,accent_hex:'#FFFFFF',font_main:'dm_sans',font_accent:'dm_serif_italic',motion_intensity:'calm'}}}}}};
let calls=[],dirty=false,refresh=0,conflict=false;
const ws={evaluations:[],feedback:[],preference:{revision:0},native_matrix:[{editor:'capcut',target_version:'9.5.0',variant_id:'portrait',status:'not_tested'}]};
const api=async(url,data)=>{calls.push({url,data});if(data){if(conflict)throw Error('Konflik revisi');if(url==='/brand-kits')return {id:'kit-new',revision:0,name:data.name,settings:data.settings};return {status:'ready'}}
 if(url==='/brand-kits')return {kits:[],preference:{revision:0}};
 if(url.endsWith('/workspace'))return ws;if(url.includes('/artifacts'))return [];if(url.endsWith('/quality'))return {categories:[],jobs:[]};return {url:'/file'};};
(async()=>{
 let h=new Element('div');context.mountSteps6(h,{project:null,onNavigate:()=>{}});assert.equal(walk(h).filter(n=>n.tagName==='button').length,4);assert.equal(walk(h).filter(n=>n.tagName==='button'&&n.disabled).length,3);
 h=new Element('div');let panel=await context.mountBrand6(h,{project,clipId:'c1',variantId:'portrait',api,onChange:()=>refresh++,hasDrafts:()=>dirty});
 assert(calls.every(c=>!c.data),'opening brand panel makes no mutation');assert(button(h,'Terapkan brand kit').disabled);
 dirty=true;await button(h,'Simpan gaya aktif sebagai kit baru').onclick();assert(calls.every(c=>!c.data),'dirty style blocks applying/saving saved kit');
 dirty=false;await button(h,'Simpan gaya aktif sebagai kit baru').onclick();assert.equal(calls.at(-1).data.settings.font_main,'dm_sans');assert(!button(h,'Terapkan brand kit').disabled,'newly saved kit immediately becomes selectable');
 conflict=true;await button(h,'Terapkan brand kit').onclick();assert(h.textContent.includes('Konflik revisi'));assert.equal(refresh,0);
 conflict=false;await button(h,'Terapkan brand kit').onclick();let op=calls.at(-1).data;assert.equal(op.expected_revision,4);assert.equal(op.variant_id,'portrait');assert.equal(op.operations[0].scope,'variant');assert(!op.operations[0].replace_manual);
 await button(h,'Simpan alternatif seed').onclick();assert.equal(calls.at(-1).data.operations[0].op,'design_alternative');assert.equal(calls.at(-1).data.operations.length,1);panel.destroy();
 calls=[];h=new Element('div');panel=await context.mountEvaluation6(h,{project,clipId:'c1',variantId:'portrait',api,onChange:()=>refresh++});
 assert(calls.every(c=>!c.data),'opening evaluations is read-only');assert(button(h,'Ukur dua hasil tersimpan').disabled);assert(button(h,'Gunakan variasi terpilih untuk proyek baru').disabled);assert(button(h,'Simpan bukti impor').disabled);
 field(h,'Alasan: keterbacaan, cerita, efek dan audio').value='Review draft';field(h,'Alasan: keterbacaan, cerita, efek dan audio').oninput();assert(storage.has('clipper6-evaluation|p1|c1|portrait'));
 panel.destroy();h=new Element('div');panel=await context.mountEvaluation6(h,{project,clipId:'c1',variantId:'portrait',api,onChange:()=>{}});assert.equal(field(h,'Alasan: keterbacaan, cerita, efek dan audio').value,'Review draft');
 await button(h,'Buang draf evaluasi').onclick();assert.equal(Object.keys(panel.getDrafts()).length,0);assert(!storage.has('clipper6-evaluation|p1|c1|portrait'));panel.destroy();
 console.log('Workspace 6 DOM adapter passed: four steps, read-only opening, brand kit enablement, protected apply, revision conflicts, targeted alternative, evidence gates and persisted review drafts.');
})().catch(e=>{console.error(e);process.exitCode=1});
