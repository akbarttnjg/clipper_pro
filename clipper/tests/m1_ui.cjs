// Run the shipped state helpers and controller functions with a DOM adapter.
// This is behavioral UI coverage, not a Chromium or visual-render acceptance test.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');
class Storage{
 constructor(){this.data=new Map()}
 getItem(key){return this.data.get(key)??null}setItem(key,value){this.data.set(key,String(value))}
 removeItem(key){this.data.delete(key)}key(index){return [...this.data.keys()][index]??null}get length(){return this.data.size}
}
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.attributes={};this.text='';this.value='';this.disabled=false;this.classList={toggle(){},add(){},remove(){}}}
 set textContent(value){this.text=String(value);this.children=[]}get textContent(){return this.text+this.children.map(c=>c.textContent||'').join(' ')}
 append(...nodes){this.children.push(...nodes)}replaceChildren(...nodes){this.children=[...nodes]}setAttribute(key,value){this.attributes[key]=String(value)}
 querySelectorAll(tag){return this.children.flatMap(node=>[...(node.tagName===tag?[node]:[]),...node.querySelectorAll(tag)])}
}
const localStorage=new Storage(),sessionStorage=new Storage(),nodes=new Map([['#words',new Element('div')],['#draft-status',new Element('p')]]),preview=new Element('button');
let fetches=[];
const context=vm.createContext({localStorage,sessionStorage,console,URLSearchParams,JSON,Map,Set,crypto:require('node:crypto'),
 document:{createElement:tag=>new Element(tag),querySelector:q=>nodes.get(q),querySelectorAll:()=>[preview]},
 fetch:async(url,options)=>{fetches.push({url,options});return {ok:true,json:async()=>({status:'ready'})}},toast(){},listen(){},drawTimeline(){}});
const {loadModule}=require('./ui_loader.cjs');Object.assign(context,loadModule(path.join(root,'static/features/editor_state.js'),context));Object.assign(context,loadModule(path.join(root,'static/features/editor1.js'),context));
const {localDrafts,sessionDrafts}=loadModule(path.join(root,'static/features/draft_storage.js'),context);context.localStorage=localDrafts;context.sessionStorage=sessionDrafts;const helpers='';
const source=fs.readFileSync(path.join(root,'static/studio4.js'),'utf8');
const between=(start,end)=>source.slice(source.indexOf(start),source.indexOf(end,source.indexOf(start)));
vm.runInContext(helpers+'\nconst $=q=>document.querySelector(q);\n'+source.split('\n').find(line=>line.startsWith('const S='))+'\n'+
 between('const saveDrafts=','const time=')+'\n'+between('const time=','function toast(')+'\n'+between('function btn(','async function api(')+'\n'+
 between('async function api(','async function projects(')+'\n'+between('async function loadProject(','async function change(')+'\n'+
 between('async function renderWords(','function drawTimeline(')+'\n'+'globalThis.state=S;',context);
const S=context.state,pairs=(key,data)=>localDrafts.setItem(key,JSON.stringify(data));
const group=(name,fn)=>Promise.resolve().then(fn).then(()=>console.log('PASS '+name));
async function main(){
 let passed=0;
 await group('sparse settings and selected clip scope',()=>{
  const delta=context.settingsDelta({font:'main',scale:1,color:'#fff'},{font:'main',scale:1,color:'#000'});
  assert.equal(JSON.stringify(delta),JSON.stringify({color:'#fff'}));
  assert.equal(Object.keys(context.settingsDelta({accent_hex:'#f6cf69'},{accent_hex:'#F6CF69'})).length,0,'browser color case is not an edit');
  const project={clips:{a:{included:true,variants:{portrait:{},landscape:{}}},b:{included:false,variants:{portrait:{}}},c:{variants:{landscape:{}}}}};
  assert.equal(JSON.stringify(context.selectedStyleTargets(project,'portrait')),JSON.stringify([{clip_id:'a',variant_id:'portrait'}]));
  assert.equal(context.selectedStyleTargets(project,'portrait',true).length,3);
 });passed++;
 await group('all editor modules contribute project-scoped drafts',()=>{
  pairs('clipper4-drafts',[['p1|c|portrait|font','new'],['p1|c|portrait|__baseRevision',3],['p2|c|portrait|font','other']]);
  pairs('clipper-stage3-drafts',[['p1|c|word:take:1','modal'],['p1|c|base',3]]);
  sessionDrafts.setItem('clipper-analysis-drafts',JSON.stringify([['p1|c|portrait|asset:a:tags','metal'],['p1|c|portrait|base',3]]));
  localDrafts.setItem('clipper4-visual-fields|p1|c|portrait',JSON.stringify({revision:3,values:{visual_vlm:'auto'}}));
  localDrafts.setItem('clipper5-style|p1|c|landscape',JSON.stringify({revision:3,values:{caption_seed:7}}));
  assert.equal(context.projectDrafts('p1').length,5);assert.equal(context.projectDrafts('p2').length,1);
  assert.equal(context.projectDrafts('').length,0);
 });passed++;
 await group('malformed draft storage blocks silently losing edits',()=>{
  pairs('clipper4-drafts',{bad:true});assert(context.projectDrafts('p1').some(d=>d.error));
  localDrafts.setItem('clipper4-visual-fields|p1|c1|portrait','{invalid');assert(context.projectDrafts('p1').some(d=>d.error&&d.key==='clipper4-visual-fields|p1|c1|portrait'&&d.raw==='{invalid'));
  localStorage.data.clear();sessionStorage.data.clear();
 });passed++;
 S.doc={project_id:'p1',revision:3,clips:{c1:{},c2:{}}};S.clip='c1';S.variant='portrait';S.baseRevision=3;
 await group('controller tracks a draft, disables render, and clears exact reversion',()=>{
  context.dirty('font','accent','main');assert.equal(context.hasDrafts(),true);assert.equal(preview.disabled,true);
  assert.equal(S.dirty.get('p1|c1|portrait|__baseRevision'),3);
  context.dirty('font','main','main');assert.equal(context.hasDrafts(),false);assert.equal(S.dirty.size,0);assert.equal(preview.disabled,false);
 });passed++;
 await group('word edit revision comes from the returned word page',()=>{
  S.page={revision:7};context.dirty('word:take:1','modal','model');
  assert.equal(S.dirty.get('p1|c1|portrait|__baseRevision'),7);context.clearDraft('word:take:1');
 });passed++;
 await group('jobs, batch and analysis cannot enqueue with visual drafts',async()=>{
  localDrafts.setItem('clipper4-visual-fields|p1|c1|portrait',JSON.stringify({revision:3,values:{speaker_track:'track1'}}));
  const before=fetches.length;
  await assert.rejects(context.api('/projects/p1/jobs',{kind:'preview'}),/Simpan atau buang/);
  await assert.rejects(context.api('/projects/p1/batch-render',{}),/Simpan atau buang/);
  await assert.rejects(context.rawAnalysis('/stage',{stage_id:'asset_proposals'}),/Simpan atau buang/);
  assert.equal(fetches.length,before);
  await context.api('/jobs/job1/cancel',{});assert.equal(fetches.length,before+1,'cancel remains available with drafts');
  localStorage.data.clear();
 });passed++;
 await group('in-memory draft is protected even if browser storage is full',async()=>{
  S.analysis={getDrafts:()=>({token:'changed'})};await assert.rejects(context.api('/projects/p1/jobs',{}),/Simpan atau buang/);
  S.analysis=null;await context.api('/projects/p1/jobs',{});assert(fetches.at(-1).url.endsWith('/jobs'));
 });passed++;
 await group('draft from another project does not block current rendering',async()=>{
  pairs('clipper4-drafts',[['p2|c1|portrait|font','draft']]);await context.api('/projects/p1/jobs',{});localStorage.data.clear();
 });passed++;
 await group('evaluation options remain usable as explicit job inputs',async()=>{
  localDrafts.setItem('clipper6-evaluation|p1|c1|portrait',JSON.stringify({candidate:'artifact'}));
  assert.equal(context.projectDrafts('p1').length,1);assert.equal(context.hasDrafts(),false);
  await context.api('/projects/p1/jobs',{kind:'evaluation',options:{candidate_id:'artifact'}});localStorage.data.clear();
 });passed++;
 await group('late words cannot replace a newly selected clip',async()=>{
  const pending=[];context.fetch=(url,options)=>new Promise(resolve=>pending.push({url,resolve}));
  S.clip='c1';S.offset=0;S.query='';const old=context.renderWords();S.clip='c2';const current=context.renderWords();
  const response=(word,revision)=>({ok:true,json:async()=>({words:[{word_id:1,word,heard:'heard',start:0,end:1}],total:1,offset:0,next_offset:null,revision,transcript_id:'take',transcript_revision:1})});
  pending[1].resolve(response('NEW',4));await current;pending[0].resolve(response('OLD',3));await old;
  assert.equal(S.page.words[0].word,'NEW');assert(!nodes.get('#words').textContent.includes('OLD'));
  assert(pending[1].url.includes('clip_id=c2'));
 });passed++;
 await group('empty search reports zero and retains explicit search mode',async()=>{
  context.fetch=async(url)=>{assert(url.includes('search_mode=heard'));return {ok:true,json:async()=>({words:[],total:0,offset:0,next_offset:null,revision:4,transcript_id:'take',transcript_revision:1})}};
  S.searchMode='heard';await context.renderWords();assert(nodes.get('#words').textContent.includes('0–0 / 0'));
 });passed++;
 await group('late project fetch cannot switch the active project back',async()=>{
  const pending=[];context.fetch=url=>new Promise(resolve=>pending.push(resolve));context.show=async()=>{};context.projects=async()=>{};
  const old=context.loadProject('p1'),current=context.loadProject('p2');
  const response=id=>({ok:true,json:async()=>({project_id:id,revision:5,clips:{c2:{}}})});
  pending[1](response('p2'));await current;pending[0](response('p1'));await old;assert.equal(S.doc.project_id,'p2');
 });passed++;
 console.log(`M1 UI: ${passed} behavioral groups passed (DOM adapter).`);
}
main().catch(error=>{console.error(error);process.exitCode=1});
