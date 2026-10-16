// Behavioral DOM adapter. This is not native browser acceptance.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.value='';this.text='';this.disabled=false;this.type='';}
 set textContent(value){this.text=String(value);this.children=[];}get textContent(){return this.text+this.children.map(c=>c.textContent).join('');}
 append(...items){this.children.push(...items);for(const n of items)n.parent=this;}
 setAttribute(k,v){this.attributes[k]=v;}
 replaceChildren(...items){this.children=[];this.text='';this.append(...items);}
 remove(){this.removed=true;if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
 querySelector(selector){return walk(this).find(n=>selector==='[data-approval]'&&n.attributes['data-approval'])||null;}
}
const walk=e=>[e,...e.children.flatMap(walk)];
const context=vm.createContext({document:{createElement:tag=>new Element(tag)},crypto:require('node:crypto'),globalThis:null,Date});
context.globalThis=context;
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/features/distribution8.js'),'utf8').replace(/export /g,''),context);
const field=(host,label)=>walk(host).find(n=>n.attributes['aria-label']===label),button=(host,label)=>walk(host).find(n=>n.tagName==='button'&&n.textContent===label);
const project={project_id:'p1',revision:7,exports:[{version:'4.0.18-m7',package_content_id:'sha256:package',input_revision:6,coverage:[{clip_id:'c1',variant_id:'portrait',title:'<img onerror=evil> judul',output_content_id:'sha256:output'}]}]};
const account={id:'a1',platform:'tiktok',name:'Manual account',connection:'handoff',enabled:true,version:0,capabilities:{upload:false},data:{}};
const workspace={workspace:{name:'Lokal',version:0,settings:{timezone:'Asia/Jakarta',daily_jobs:50,daily_publish:10}},sessions:[]};
let dirty=false,wait=false,release=null,stored=[],writeCalls=[],calls=[];
const api=async(url,body)=>{calls.push({url,body});if(url.endsWith('/oauth/start'))return {id:'flow1',url:'https://accounts.google.com/authorize',expires:2000000000};
 const action=body.action,args=body.args;if(action==='status')return {role:'owner',worker:{online:false},vault:{ready:false,backend:'not_configured'}};
 if(action==='account.list')return {accounts:[account]};if(action==='workspace.get')return workspace;if(action==='publish.list')return {requests:stored};
 if(action==='publish.draft'){writeCalls.push(body);return {id:'publish1',version:0,request:{...args,project_revision:7,output_content_id:'sha256:output',schedule:{timezone:args.timezone,local:null}}};}
 if(action==='publish.preflight'){if(wait)await new Promise(r=>release=r);return {ready:true,blockers:[],warnings:['Hand-off menunggu unggahan manual.'],approval_hash:'frozen-hash',frozen:{title:'Tersimpan',privacy:'private'}};}
 if(action==='publish.approve'){writeCalls.push(body);return {id:'publish1',status:'queued'};}
 if(action==='analytics.get')return {rows:[{publish_id:'p',metric:'views',value:0,start_date:'2026-10-01',end_date:'2026-10-02',source:'operator_import'},{publish_id:'p',metric:'likes',value:null,reason:'not_supplied',start_date:'2026-10-01',end_date:'2026-10-02'}]};
 if(action==='record.list')return {records:[]};return {};
};
(async()=>{
 const host=new Element('div');const handle=context.mountM8(host,{project,api,hasDrafts:()=>dirty});await handle.ready;
 assert.equal(calls.length,4,'mount reads only four state queries');assert.equal(writeCalls.length,0);
 assert(host.textContent.includes('worker belum terlihat aktif'));assert(!walk(host).some(n=>n.tagName==='img'),'untrusted title remains text');
 assert(button(host,'Setujui draf ini dan antrekan').disabled);
 dirty=true;await button(host,'Buat draf publikasi').onclick();assert.equal(writeCalls.length,0);dirty=false;
 await button(host,'Buat draf publikasi').onclick();assert.equal(writeCalls.length,1);assert.equal(writeCalls[0].args.metadata.privacy,'private');assert.equal(writeCalls[0].args.expected_revision,7);assert.equal(writeCalls[0].args.mode,'handoff');
 await button(host,'Periksa draf tersimpan').onclick();let approve=button(host,'Setujui draf ini dan antrekan');assert(!approve.disabled);
 field(host,'Privacy tujuan').value='public';field(host,'Privacy tujuan').onchange();assert(approve.disabled,'changing any field revokes local approval gate');
 await approve.onclick();assert.equal(writeCalls.length,1);
 field(host,'Privacy tujuan').value='private';field(host,'Privacy tujuan').onchange();await button(host,'Buat draf publikasi').onclick();
 wait=true;const pending=button(host,'Periksa draf tersimpan').onclick();await Promise.resolve();field(host,'Judul publikasi').value='Berubah';field(host,'Judul publikasi').oninput();release();await pending;wait=false;
 assert(button(host,'Setujui draf ini dan antrekan').disabled,'late preflight cannot approve modified form');
 await button(host,'Buat draf publikasi').onclick();await button(host,'Periksa draf tersimpan').onclick();await button(host,'Setujui draf ini dan antrekan').onclick();
 assert.equal(writeCalls.at(-1).action,'publish.approve');assert.equal(writeCalls.at(-1).args.approval_hash,'frozen-hash');
 assert(button(host,'Setujui draf ini dan antrekan').disabled,'completed approval does not reenable a detached/unreviewed form');
 const before=calls.length;await button(host,'Akun').onclick();assert.equal(calls.length,before,'opening account tab does not connect OAuth');
 field(host,'Google Desktop client ID').value='fixture.apps.googleusercontent.com';field(host,'Google Desktop client secret').value='fixture-secret';field(host,'Nama profil YouTube').value='My channel';
 await button(host,'Mulai koneksi Google').onclick();assert(calls.at(-1).url.endsWith('/oauth/start'));assert.equal(field(host,'Google Desktop client secret').value,'');
 await button(host,'Analytics').onclick();await button(host,'Tampilkan metrik tersimpan').onclick();assert(host.textContent.includes('Belum tersedia'));assert(host.textContent.includes('operator_import'));
 await button(host,'Otomasi').onclick();assert(host.textContent.includes('Publish')||host.textContent.includes('Publikasi'));
 handle.destroy();assert.equal(host.children.length,0);
 console.log('M8 UI passed: read-only mount, draft guard, immutable request, explicit approval, stale-response invalidation, disabled-gate lifecycle, no implicit OAuth, password clearing, nullable metrics and destruction (DOM adapter).');
})().catch(error=>{console.error(error);process.exitCode=1;});
