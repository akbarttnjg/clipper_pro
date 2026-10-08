// Execute the real queue presentation and caption component with tiny UI stubs.
// This does not run a browser, Remotion renderer or font rasterizer.
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..');

async function main(){
 const main=fs.readFileSync(path.join(root,'static/studio4.js'),'utf8');
 const helper=main.slice(main.indexOf('function jobState('),main.indexOf('function renderJobs('));
 const renderer=main.split('\n').find(line=>line.startsWith('function renderJobs('));
 class Element{
  constructor(tag,text){this.tag=tag;this.text=text||'';this.children=[]}
  append(...children){this.children.push(...children)}
  replaceChildren(...children){this.children=[...children]}
  get textContent(){return this.text+this.children.map(child=>child.textContent||'').join(' ')}
 }
 const box=new Element('section');
 const jobs=[...Array.from({length:8},(_,i)=>({id:'active-'+i,kind:'preview',status:'queued',progress:0})),
  ...Array.from({length:110},(_,i)=>({id:'old-'+i,kind:'alignment',status:'completed',result:{aligned:0,attempted:1,errors:[{}]}}))];
 const context={S:{doc:{jobs}},$:()=>box,el:(tag,text)=>new Element(tag,text),
  row:parent=>{const row=new Element('div');parent.append(row);return row},btn:()=>{}};
 vm.runInNewContext(helper+renderer,context);
 const state=result=>context.jobState({kind:'alignment',status:'completed',result});
 assert.equal(state({aligned:0,attempted:0,errors:[]}),'tanpa kandidat');
 assert.equal(state({aligned:0,attempted:1,errors:[{}]}),'perlu diperiksa');
 assert.equal(state({aligned:1,attempted:2,errors:[{}]}),'sebagian berhasil');
 assert.equal(state({aligned:1,attempted:1,errors:[]}),'berhasil');
 context.renderJobs();
 assert.equal(box.children.length,1+8+6);
 assert.equal(box.children.filter(node=>node.textContent.includes('menunggu')).length,8);
 assert.equal(box.children.filter(node=>node.textContent.includes('perlu diperiksa')).length,6);

 const component=fs.readFileSync(path.join(root,'clipper/runtime/templates/remotion5/index.jsx'),'utf8');
 const syntax=spawnSync(process.execPath,['--input-type=module','--check'],{input:component,encoding:'utf8'});
 assert.equal(syntax.status,0,syntax.stderr);
 const {sampleAt,activePhrases}=await import(path.join(root,'clipper/runtime/templates/remotion5/caption_math.mjs'));
 let registered,frame=8;
 const react={createElement:(tag,props,...children)=>({tag,props,children})};
 const scene={React:react,Composition:'Composition',sampleAt,activePhrases,useCurrentFrame:()=>frame,
  useVideoConfig:()=>({fps:30}),useEffect:()=>{},useState:init=>[init()],delayRender:()=>1,
  continueRender:()=>{},registerRoot:root=>{registered=root}};
 vm.runInNewContext(component.replace(/^import .*;\s*$/gm,''),scene);
 const plan={width:640,height:360,contrast:true,contrast_style:{outline:2,shadow:2.5,outline_opacity:.68,shadow_opacity:.56},
  phrases:[{start:0,end:2,words:[{text:'ego',font_id:'dm_sans',size:32,baseline:300,x:320,y:280,
   color:'#FFD152',initial_color:'#FFFFFF',fade_seconds:.065,phrase_duration:2,color_transition:{start:.6,duration:.12}}]}]};
 const composition=registered();
 assert.equal(composition.tag,'Composition');
 const svg=composition.props.component({plan,fonts:{}});
 assert.equal(svg.tag,'svg');assert.equal(svg.props.width,640);
 const text=svg.children[0][0].children[0];
 assert.equal(text.children[0],'ego');assert.equal(text.props.fill,'#ffffff');assert.equal(text.props.strokeWidth,2);
 frame=30;
 const spoken=composition.props.component({plan,fonts:{}}).children[0][0].children[0];
 assert.equal(spoken.props.fill,'#ffd152');
 console.log('Repair 1 UI: active queue, alignment outcomes, legacy color/fade and valid Remotion entry passed.');
}
main().catch(error=>{console.error(error);process.exitCode=1});
