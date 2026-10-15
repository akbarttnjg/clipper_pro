// DOM behavioral QA; this does not claim a native browser or editor import.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
class Element{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.value='';this.text='';this.disabled=false}
 set textContent(v){this.text=String(v);this.children=[]}get textContent(){return this.text+this.children.map(c=>c.textContent).join('')}
 append(...items){this.children.push(...items)}prepend(...items){this.children.unshift(...items)}setAttribute(k,v){this.attributes[k]=v}
 replaceChildren(...items){this.children=items}remove(){this.removed=true}}
const context=vm.createContext({document:{createElement:t=>new Element(t)},Date});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/features/delivery7.js'),'utf8').replace(/export /g,''),context);
const walk=e=>[e,...e.children.flatMap(walk)],button=(h,t)=>walk(h).find(n=>n.tagName==='button'&&n.textContent===t),field=(h,t)=>walk(h).find(n=>n.attributes['aria-label']===t);
let dirty=false,release=null,wait=false,refresh=0;const calls=[];
const state={coverage:4,ready:true,blockers:[],capabilities:[{clip_id:'c',variant_id:'portrait',capabilities:[{editor:'resolve',target_version:'18.6.6',layers:{caption_font_style:'backlog'}}]}]};
const api=async(url,data)=>{calls.push({url,data});if(url.endsWith('preflight')){if(wait)await new Promise(r=>release=r);return state}if(url.endsWith('/reviews'))return data?{id:'review1',url:'/review/token',expires:2000000000}:{reviews:[]};return {}};
const project={project_id:'p1',revision:7,exports:[{version:'4.0.18-m7',timelines:4,input_revision:6,package_content_id:'sha256:fixed',url:'/package.zip'}]};
const mount=()=>{const host=new Element('div');const handle=context.mountDelivery7(host,{project,api,onChange:()=>refresh++,hasDrafts:()=>dirty});return {host,handle}};
(async()=>{
 let {host,handle}=mount();assert.equal(calls.length,0,'mount has no export or review creation');let create=button(host,'Buat paket M7');assert(create.disabled);
 dirty=true;await button(host,'Periksa paket dan kemampuan layer').onclick();assert.equal(calls.length,0,'unsaved draft blocks work');dirty=false;
 await button(host,'Periksa paket dan kemampuan layer').onclick();assert(!create.disabled);assert(host.textContent.includes('backlog'));
 await create.onclick();assert.equal(calls.at(-1).data.kind,'delivery_m7');assert.equal(calls.at(-1).data.expected_revision,7);assert.equal(calls.at(-1).data.options.profile,'reference');assert.equal(refresh,1);
 field(host,'Profil MP4 delivery').value='compact';field(host,'Profil MP4 delivery').onchange();assert(create.disabled,'any choice change requires a new preflight');
 wait=true;const request=button(host,'Periksa paket dan kemampuan layer').onclick();await Promise.resolve();field(host,'Rasio paket').value='portrait';field(host,'Rasio paket').onchange();release();await request;assert(create.disabled,'late response must not approve changed choices');wait=false;
 field(host,'Mode editor M7').value='preserved';field(host,'Mode editor M7').onchange();assert(!field(host,'CapCut 4.7.0').checked);
 await button(host,'Periksa paket dan kemampuan layer').onclick();await create.onclick();assert.equal(calls.at(-1).data.options.editors.length,0);
 await button(host,'Buat tautan review lokal').onclick();assert.equal(calls.at(-1).data.permission,'review');assert.equal(calls.at(-1).data.expires_minutes,1440);
 assert.equal(calls.at(-1).data.package_content_id,'sha256:fixed');await button(host,'Cabut tautan ini').onclick();assert(calls.at(-1).url.endsWith('/review1/revoke'));
 await button(host,'Kelola tautan review tersimpan').onclick();assert(calls.at(-1).url.endsWith('/reviews')&&!calls.at(-1).data);
 handle.destroy();assert(walk(host).some(n=>n.removed));
 console.log('M7 UI passed: mount, draft guard, preflight gate, capability matrix, snapshot revision/options, stale response, preserved selection, review scope/expiry/hash, revocation and lifecycle (DOM adapter).');
})().catch(e=>{console.error(e);process.exitCode=1});
