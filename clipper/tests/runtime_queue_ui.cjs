// Run the real panel against a small DOM adapter: no browser/model download.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.parentNode=null;this.dataset={};this.hidden=false;this.disabled=false;this.value='';this.scrollTop=0;this.clientHeight=100;this.text='';this.listeners={};this.classes=new Set();this.classList={add:(...s)=>s.forEach(x=>this.classes.add(x)),remove:(...s)=>s.forEach(x=>this.classes.delete(x))};}
  set className(s){this.classes=new Set(s.split(' '));} get className(){return [...this.classes].join(' ')}
  set textContent(s){this.text=String(s);this.replaceChildren();}get textContent(){return this.text+this.children.map(x=>x.textContent).join('')}
  get scrollHeight(){return this.tagName==='pre'?this.text.split('\n').length*20:this.children.length*160}
  get nextSibling(){if(!this.parentNode)return null;return this.parentNode.children[this.parentNode.children.indexOf(this)+1]||null}
  append(...nodes){for(const n of nodes)this.insertBefore(n,null)}
  insertBefore(n,before){n.remove();const i=before?this.children.indexOf(before):this.children.length;assert(i>=0);this.children.splice(i,0,n);n.parentNode=this}
  remove(){if(this.parentNode){const p=this.parentNode;p.children.splice(p.children.indexOf(this),1);this.parentNode=null}}
  replaceChildren(...nodes){for(const n of [...this.children])n.remove();this.append(...nodes)}
  setAttribute(k,v){this[k]=v}
  querySelectorAll(selector){return walk(this).filter(n=>selector==='details[open]'&&n.tagName==='details'&&n.open)}
  focus(){document.activeElement=this}scrollIntoView(){this.wasScrolled=true}
  addEventListener(k,fn){(this.listeners[k]??=[]).push(fn)}
  removeEventListener(k,fn){this.listeners[k]=(this.listeners[k]||[]).filter(x=>x!==fn)}
  showModal(){this.open=true}close(){this.open=false;for(const fn of this.listeners.close||[])fn()}
}
function walk(e){return e.children.flatMap(n=>[n,...walk(n)])}
const document={createElement:tag=>new Element(tag),activeElement:null};
const intervals=new Map();let nextTimer=0;
const context=vm.createContext({document,navigator:{clipboard:{writeText:async s=>{context.copied=s}}},URLSearchParams,Map,Set,JSON,console,setInterval:fn=>{intervals.set(++nextTimer,fn);return nextTimer},clearInterval:id=>intervals.delete(id)});
const source=fs.readFileSync(path.join(__dirname,'../../static/features/runtime.js'),'utf8').replace('export async function mountRuntime','async function mountRuntime');
vm.runInContext(source+'\nglobalThis.mountRuntime=mountRuntime;',context);
const synthetic=()=>({counts:{total:26,installed:0,sample_passed:0},free_bytes:1024**3,components:[],hardware:null,profiles:null,selected_profile:{name:'balanced'},stock:[],jobs:Array.from({length:30},(_,i)=>({id:'runtime-'+String(i).padStart(4,'0'),component:i===23?'whisperx':i===24?'faster-whisper':'component-'+i,action:'install',status:i===23?'running':i===24?'failed':i<22?'queued':'completed',created:30-i,progress:i===23?50:0,options:{model:'medium',device:'cuda'},message:'Test'}))});
let data=process.argv[2]?JSON.parse(fs.readFileSync(process.argv[2],'utf8')):synthetic();
const calls=[];let log='first-line\n'+'package details\n'.repeat(80),holdLog=null;
async function api(url,body){calls.push({url,body});if(url==='/runtime')return structuredClone(data);
  if(url.endsWith('/log')){if(holdLog)return holdLog;return {text:log,truncated:false}}
  if(url==='/runtime/jobs/cancel-queued'){let n=0;for(const j of data.jobs)if(j.status==='queued'){j.status='canceled';n++}return {canceled:n}}
  if(url.endsWith('/cancel')){const j=data.jobs.find(x=>url.includes(x.id));j.status=j.status==='queued'?'canceled':'cancel_requested';return j}
  throw Error('Unexpected request '+url);
}
const dialog=new Element('dialog'),toasts=[];
const nodes=cls=>walk(dialog).filter(n=>n.classes.has(cls));
const buttons=(parent,label)=>walk(parent).filter(n=>n.tagName==='button'&&n.textContent===label);
async function poll(){await [...intervals.values()][0]()}
(async()=>{
  await context.mountRuntime(dialog,api,(msg)=>toasts.push(msg));
  const running=data.jobs.find(j=>j.status==='running'),failed=data.jobs.find(j=>j.status==='failed');
  assert.equal(nodes('runtime-job').length,data.jobs.length,'every returned job is reachable');
  assert.equal(nodes('runtime-job')[0].dataset.jobId,running.id,'buried worker appears first');
  assert.equal(calls.filter(c=>c.body).length,0,'opening panel never cancels or enqueues');
  const record=nodes('runtime-job').find(n=>n.dataset.jobId===running.id),list=nodes('runtime-job-list')[0],scroll=nodes('runtime-content')[0];
  list.scrollTop=410;scroll.scrollTop=123;
  await buttons(record,'Lihat log')[0].onclick();
  const pre=nodes('runtime-log-text')[0];pre.scrollTop=160;
  log+='new package line\n';await poll();
  assert.equal(nodes('runtime-job').find(n=>n.dataset.jobId===running.id),record,'poll keeps buttons attached');
  assert.equal(nodes('runtime-log-text')[0],pre,'poll keeps log attached');
  assert.equal(list.scrollTop,410);assert.equal(scroll.scrollTop,123);assert.equal(pre.scrollTop,160);
  assert.equal(document.activeElement,pre,'poll keeps keyboard focus');
  assert(pre.textContent.endsWith('new package line\n'));
  assert.equal(nodes('runtime-log-panel')[0].hidden,false,'log stays open');
  const select=walk(dialog).find(n=>n.tagName==='select'&&n.children.some(o=>o.value==='attention'));
  select.value='attention';select.onchange();
  assert.deepEqual(nodes('runtime-job').filter(n=>!n.hidden).map(n=>n.dataset.jobId),[failed.id]);
  const search=walk(dialog).find(n=>n.type==='search');search.value='does-not-exist';search.oninput();assert.equal(nodes('runtime-job').filter(n=>!n.hidden).length,0);
  search.value='';search.oninput();select.value='all';select.onchange();
  await buttons(dialog,'Salin log')[0].onclick();assert.equal(context.copied,pre.textContent);
  assert(walk(dialog).some(n=>n.tagName==='a'&&n.href==='/api/studio/runtime/jobs/'+running.id+'/log/download'));
  const count=data.jobs.filter(j=>j.status==='queued').length;
  await buttons(dialog,'Batalkan antrean menunggu ('+count+')')[0].onclick();
  assert.equal(data.jobs.filter(j=>j.status==='queued').length,0);assert.equal(running.status,'running');
  await buttons(dialog,'Batalkan '+running.component)[0].onclick();assert.equal(running.status,'cancel_requested');
  assert(calls.some(c=>c.url==='/runtime/jobs/'+running.id+'/cancel'));
  let release;holdLog=new Promise(resolve=>{release=resolve});const pending=poll();
  await new Promise(resolve=>setImmediate(resolve));buttons(dialog,'Tutup log')[0].onclick();release({text:'late-result',truncated:false});await pending;
  assert.equal(nodes('runtime-log-panel')[0].hidden,true,'late log response cannot reopen panel');
  buttons(dialog,'Tutup')[0].onclick();assert.equal(intervals.size,0,'closing panel stops polling');
  console.log('PASS: full queue, active ordering, stable DOM/focus/scroll, log refresh/copy/download, filters, separate cancellations, late responses, cleanup.');
})().catch(e=>{console.error(e);process.exitCode=1});
