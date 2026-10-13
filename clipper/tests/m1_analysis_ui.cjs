// Real analysis component, simulated revision service, no browser or inference.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
class Element{
 constructor(tag){this.dataset={};this.tagName=tag;this.children=[];this.text='';this.value='';this.classList={add(){},remove(){}};this.attributes={}}
 append(...nodes){this.children.push(...nodes)}replaceChildren(...nodes){this.children=[...nodes]}
 set textContent(value){this.text=String(value);this.children=[]}get textContent(){return this.text+this.children.map(n=>n.textContent||'').join(' ')}
 setAttribute(k,v){this.attributes[k]=v}get options(){return this.children}focus(){}
}
const store=new Map(),context=vm.createContext({document:{createElement:t=>new Element(t)},crypto:require('node:crypto'),
 sessionStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)}});
const {loadModule,storageAdapter}=require('./ui_loader.cjs');
context.localStorage=storageAdapter(context.localStorage||{getItem:()=>null,setItem(){}});context.sessionStorage=storageAdapter(context.sessionStorage||{getItem:()=>null,setItem(){}});
Object.assign(context,loadModule(path.join(__dirname,'../../static/features/analysis.js'),context));
const draftStorage=loadModule(path.join(__dirname,'../../static/features/draft_storage.js'),context).sessionDrafts;const hasDraft=k=>draftStorage.getItem(k)!==null;
const walk=e=>[e,...e.children.flatMap(walk)],field=(host,label)=>walk(host).find(e=>e.tagName==='label'&&e.text===label)?.children[0],button=(host,label)=>walk(host).find(e=>e.tagName==='button'&&e.text===label);
const target={project_id:'p1',clip_id:'c1',variant_id:'portrait'};let revision=5,conflict=false;const changes=[];
function snapshot(){return {schema_version:1,target,revision,capabilities:{correction:true,aliases:true,asset_changes:true},data:{aliases:[],
 transcript:{schema_version:1,kind:'TranscriptSnapshot',source_id:'source',payload:{transcript_id:'take',revision:1,
  heard_words:[{word_id:0,word:'model'}],display_tokens:[{token_id:'token',origin_word_ids:[0],text:'model',source_start:0,source_end:1}],
  review_queue:[{token_id:'token',start:0,end:1,text:'model',suggestions:[],reason:'controlled'}]}},
 asset_proposals:{schema_version:1,kind:'AssetProposalSet',source_id:'source',payload:{proposals:[{asset_id:'a',proposal_id:'proposal',
  visual_intent:'fixture',reason:'fixture',source_start:0,source_end:1,tags:'original',rights:{permission_status:'user_supplied',attribution:'owner'}}]}}}}}
const api={get_snapshot:async()=>snapshot(),submit_changes:async request=>{changes.push(request);if(conflict||request.expected_revision!==revision)return {status:'conflict',revision};return {status:'ready',revision:++revision}},run_stage:async()=>({status:'queued'})};
async function main(){
 let host=new Element('div'),panel=context.mountAnalysis(host,{api,target,revision:5});await panel.refresh();
 const canonical=field(host,'Ejaan benar'),alias=field(host,'Alias salah dengar');canonical.value='modal';canonical.oninput();alias.value='model';alias.oninput();
 assert.equal(Object.keys(panel.getDrafts()).length,2);assert.equal(new Map(JSON.parse(draftStorage.getItem('clipper-analysis-drafts'))).get('p1|c1|portrait|base'),5);
 conflict=true;await button(host,'Simpan alias').onclick();assert.equal(Object.keys(panel.getDrafts()).length,2);
 revision=6;await panel.refresh();conflict=false;await button(host,'Simpan alias').onclick();assert.equal(changes.at(-1).expected_revision,5,'refresh does not silently rebase a pending edit');assert.equal(Object.keys(panel.getDrafts()).length,2);
 // Reset the simulated server to verify explicit rebase and consumption.
 revision=8;canonical.value='capital';canonical.oninput();await button(host,'Muat revisi terbaru').onclick();
 await button(host,'Simpan alias').onclick();assert.equal(changes.at(-1).expected_revision,8);
 assert.equal(Object.keys(panel.getDrafts()).length,0);assert.equal(changes.at(-1).operations[0].canonical,'capital');
 const tags=field(host,'Tag lokal (Indonesia / Inggris)');tags.value='metal';tags.oninput();assert.equal(Object.keys(panel.getDrafts()).length,1);
 await button(host,'Simpan metadata').onclick();assert.equal(changes.at(-1).operations[0].tags,'metal');assert.equal(Object.keys(panel.getDrafts()).length,0);
 const text=field(host,'Ejaan yang Anda setujui');text.value='modal';text.oninput();assert.equal(Object.keys(panel.getDrafts()).length,1);
 text.value='model';text.oninput();assert.equal(Object.keys(panel.getDrafts()).length,0,'reverting text clears its draft');
 panel.destroy();assert.equal(host.children.length,0);
 console.log('M1 analysis UI: alias/metadata drafts, conflict retention, explicit rebase, consumption and exact reversion passed (DOM adapter).');
}
main().catch(error=>{console.error(error);process.exitCode=1});
