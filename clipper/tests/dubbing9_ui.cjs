// Behavioral DOM adapter only; no native browser or neural-quality claim.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
class Element{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.value='';this.checked=false;}append(...a){this.children.push(...a);}replaceChildren(...a){this.children=[...a];}set textContent(t){this.text=String(t);this.children=[];}get textContent(){return (this.text||'')+this.children.map(n=>n.textContent).join('');}}
const root=new Element('main'),walk=e=>[e,...e.children.flatMap(walk)],calls=[],previews=[];
const field=(p,label,value='',type='text')=>{const n=new Element('input');n.label=label;n.type=type;n.value=value;n.checked=type==='checkbox'&&Boolean(value);p.append(n);return n;};
const select=(p,label,items)=>{const n=field(p,label);return n;};
const button=(p,label,action)=>{const n=new Element('button');n.textContent=label;n.onclick=action;p.append(n);return n;};
const get=label=>walk(root).find(e=>e.label===label),click=label=>walk(root).find(e=>e.tagName==='button'&&e.textContent===label).onclick();
let doc={project_id:'p',revision:7,transcript_id:'take',transcript_revision:1,clips:{c:{start:0,end:4,title:'<img onerror=evil>'}},translation_tracks:{t:{approved:true,source_take:'take',source_revision:1,language:'en'},stale:{approved:true,source_take:'old',source_revision:0,language:'en'}}};
const plan={project_id:'p',input_revision:7,clip_id:'c',track_id:'t',voice_id:'v',audio_index:1,max_rate:1.15,plan_digest:'pin',language:'en',duration:4,glossary:'Andi',source_range:[0,4],cues:[{cue_id:'1',start:.2,end:1.7,source_text:'<script>source</script> 50',text:'Does not pay 50'}]};
let candidate={id:'candidate',version:0,kind:'dubbing',data:{status:'awaiting_listening',output:{content_id:'sha256:output'},plan,program_url:'program',original_url:'original',dubbed_url:'dubbed'}};
const command=async(action,args)=>{calls.push({action,args});if(action==='m9.list')return {items:[{id:'v',data:{name:'Authored fixture',language:'en_US'}}]};if(action==='m9.dub.plan')return structuredClone(plan);if(action==='m9.dub.submit'){if(args.reviewed_cue_ids.length!==1||!args.facts_reviewed||!args.rights_reviewed)throw Error('Review incomplete');return {id:'job'};}if(action==='m9.job.get')return {result:{item_id:'candidate'}};if(action==='m9.get')return structuredClone(candidate);if(action==='m9.dub.accept'){if(!args.listened||!args.timing_reviewed||!args.facts_reviewed)throw Error('Listen first');return {id:'accept-job'};}throw Error(action);};
const context=vm.createContext({document:{createElement:tag=>new Element(tag)},JSON,Number,Error});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/m9-dubbing.js'),'utf8').replace('export function','function'),context);
context.mountDubbing({box:(title,help)=>{const n=new Element('article');n.textContent=title+help;root.append(n);return n;},field,select,button,project:async()=>structuredClone(doc),command,
 showJob:(parent,id)=>{const n=new Element('p');n.textContent=id;parent.append(n);},describe:()=>{},preview:async(parent,label,url,type)=>previews.push({label,url,type})});
(async()=>{
 await assert.rejects(click('Buat kandidat dubbing'),/Muat pilihan/);
 await click('Muat klip, terjemahan dan suara');assert.equal(get('Track terjemahan disetujui').children.length,1);
 await click('Tampilkan rencana dan periksa setiap cue');assert(root.textContent.includes('<script>source</script> 50'));assert(!walk(root).some(n=>n.tagName==='script'));
 await assert.rejects(click('Buat kandidat dubbing'),/Review incomplete/);
 for(const n of walk(root))if(n.type==='checkbox')n.checked=true;
 await click('Buat kandidat dubbing');let request=calls.findLast(c=>c.action==='m9.dub.submit').args;
 assert.deepEqual(request.reviewed_cue_ids,['1']);assert.equal(request.plan_digest,'pin');
 get('Percepatan maksimum (1 sampai 1,25)').value='1.2';get('Percepatan maksimum (1 sampai 1,25)').onchange();
 await assert.rejects(click('Buat kandidat dubbing'),/rencana terbaru/);
 await click('Buka hasil tugas dubbing terakhir');assert.deepEqual(previews.map(p=>p.url),['program','original','dubbed']);
 await assert.rejects(click('Terima hasil ini dan buat proyek editor baru'),/Listen first/);
 for(const n of walk(root))if(n.type==='checkbox')n.checked=true;
 await click('Terima hasil ini dan buat proyek editor baru');request=calls.findLast(c=>c.action==='m9.dub.accept').args;
 assert.equal(request.output_content_id,'sha256:output');assert.equal(request.expected_version,0);
 await assert.rejects(click('Terima hasil ini dan buat proyek editor baru'),/Buka hasil A\/B/);
 doc={...doc,revision:8};await assert.rejects(click('Tampilkan rencana dan periksa setiap cue'),/Proyek\/revisi berubah/);
 console.log('M9 dubbing UI adapter passed: per-cue consent, safe text, stale plan invalidation, approved-track filtering, authenticated preview delegation, exact A/B output acceptance and repeat protection.');
})().catch(e=>{console.error(e);process.exitCode=1;});
