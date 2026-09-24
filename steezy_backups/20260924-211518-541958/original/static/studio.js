'use strict';
const $ = id => document.getElementById(id);
const state = {job:null,index:null,data:null,editor:null,dirty:false,mode:'source',selected:new Set(),poll:null,draw:null,drag:null,loadedRevision:null,seen:new Set(),selectionToken:0,drawOld:''};
const optionIds = ['aspect','caption_style','layout','caption_position','caption_scale','accent_hex','punch_zoom','accent_font','title_card','cold_open','trim','music_db','sfx_db','framing_x','material_rect','speaker_rect','material_share'];
const active = new Set(['queued','analyzing','reviewing','rendering','previewing','exporting']);
const busy = () => active.has(state.data?.status);
function toast(text){$('toast').textContent=text;$('toast').classList.remove('hidden');clearTimeout(state.toastTimer);state.toastTimer=setTimeout(()=>$('toast').classList.add('hidden'),6000)}
function tc(t, precision=false){t=Math.max(0,Number(t)||0);const seconds=Math.floor(t);return [Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(x=>String(x).padStart(2,'0')).join(':')+(precision?'.'+String(Math.floor((t-seconds)*100+.001)).padStart(2,'0'):'')}
function seconds(value){const parts=String(value).trim().replace(',','.').split(':').map(Number);if(!String(value).trim()||parts.some(x=>!Number.isFinite(x)||x<0)||parts.length>3)throw Error('Gunakan waktu 00:18:36.92 atau detik 1116.92.');if(parts.length>1&&parts.slice(1).some(x=>x>=60))throw Error('Menit dan detik harus kurang dari 60.');return parts.reduce((n,x)=>n*60+x,0)}
function bounds(){return {start:seconds($('start').value),end:seconds($('end').value)}}
async function api(path, options={}){const r=await fetch(path,options);let data;try{data=await r.json()}catch{throw Error('Respons server tidak terbaca. Periksa terminal aplikasi.')}if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data}
const post=(path,data)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e}
function markDirty(){state.dirty=true;$('saveState').textContent='Koreksi belum disimpan'}
function options(){return Object.fromEntries(optionIds.map(id=>[id,$(id).type==='checkbox'?($(id).checked?'1':'0'):$(id).value]))}
async function history(){const jobs=await api('/api/jobs');$('history').replaceChildren();for(const j of jobs){const b=el('button',j.name);b.title=j.name;b.onclick=()=>loadJob(j.id);$('history').append(b)}}
function issues(c){return c.boundary_review?.issues||[]}
function paintCandidates(){
 const parent=$('candidates');const scroll=parent.scrollTop;parent.replaceChildren();const candidates=state.data?.candidates||[];$('count').textContent=candidates.length;
 for(const [i,c] of candidates.entries()){
  const card=el('div',undefined,'card'+(i===state.index?' active':''));card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-pressed',String(i===state.index));card.onclick=()=>selectClip(i);card.onkeydown=e=>{if(e.key==='Enter')selectClip(i)};
  const check=document.createElement('input');check.type='checkbox';check.checked=state.selected.has(i);check.setAttribute('aria-label','Pilih '+c.title);check.onclick=e=>e.stopPropagation();check.onchange=()=>{check.checked?state.selected.add(i):state.selected.delete(i);updateControls()};
  card.append(check,el('div',String(i+1).padStart(2,'0')+' · '+Math.round(c.end-c.start)+' dtk','meta'),el('h3',c.title),el('div',tc(c.start)+' → '+tc(c.end),'meta'),el('p',c.reason,'reason'));
  const warning=issues(c).length||c.boundary_review?.status==='needs_review';const result=state.data.clips?.find(r=>r.index===i&&r.revision===c.revision);
  card.append(el('div',result?'✓ Render tersimpan':warning?'Periksa batas pembahasan':c.boundary_review?.status==='checked'?'Konteks diperiksa · dengarkan hasilnya':'Kandidat · belum diperiksa','rubric'+(warning?' warn':'')));parent.append(card);
 }
 parent.scrollTop=scroll;
}
function updateControls(){
 const chosen=state.index!==null,selected=state.selected.size>0;document.body.classList.toggle('busy',!!busy());
 for(const id of ['saveEdit','preview','markIn','markOut','playBeginning','playEnding','playClip','context','reviewBoundary','drawMaterial','drawSpeaker'])$(id).disabled=!chosen||!!busy();
 $('render').disabled=!selected||!!busy();$('reviewAll').disabled=!state.data?.candidates?.length||!!busy();$('addClip').disabled=!state.data?.candidates?.length||!!busy();$('saveEdit').textContent=state.dirty?'Simpan koreksi •':'Simpan koreksi';$('render').textContent='Render '+(state.selected.size||'')+' pilihan';
 const result=state.data?.clips?.find(r=>r.index===state.index);$('resultTab').disabled=!result;$('download').classList.toggle('hidden',!result);
 if(result){$('download').href='/clips/'+encodeURIComponent(result.file);$('download').download=result.file}
 const exportReady=selected&&[...state.selected].every(i=>state.data?.clips?.some(r=>r.index===i&&r.revision===(state.data.candidates[i].revision||0)));
 $('export').disabled=!exportReady||!!busy();$('downloadBundle').classList.toggle('hidden',!state.data?.export);if(state.data?.export)$('downloadBundle').href='/api/download/'+state.job;
 const preview=state.data?.preview;$('previewTab').classList.toggle('hidden',!preview||preview.index!==state.index||preview.revision!==state.editor?.clip.revision);
 if(result&&state.editor&&result.revision!==state.editor.clip.revision&&!state.dirty)$('saveState').textContent='Koreksi tersimpan · render perlu diperbarui';
}
async function loadJob(id){
 if(state.dirty&&!confirm('Koreksi belum disimpan. Pindah proyek?'))return;
 try{clearTimeout(state.poll);state.job=id;state.index=null;state.editor=null;state.selected.clear();state.seen.clear();state.dirty=false;state.data=await api('/api/status/'+id);await refresh();if(state.data.candidates.length&&state.index===null)await selectClip(0);history().catch(()=>{})}catch(e){toast(e.message)}
}
async function refresh(){
 if(!state.job)return;const job=state.job;
 try{
  const oldStatus=state.data?.status;const data=await api('/api/status/'+job);if(job!==state.job)return;state.data=data;
  $('projectName').textContent=data.name||'Proyek lokal';$('message').textContent=data.message;$('progress').value=data.percent||0;$('elapsed').textContent=tc(data.elapsed);
  $('error').textContent=data.error||'';$('errorDetails').classList.toggle('hidden',!data.error);$('resume').classList.toggle('hidden',!['interrupted','error'].includes(data.status));
  $('timings').textContent=Object.entries(data.timings||{}).map(([k,v])=>({analyzing:'Analisis',reviewing:'Review AI',rendering:'Render',previewing:'Preview',exporting:'Ekspor'}[k]||k)+': '+tc(v)).join(' · ');
  for(const [i,c] of data.candidates.entries())if(!state.seen.has(i)){state.seen.add(i);if(!issues(c).length&&c.boundary_review?.status!=='needs_review'&&c.selection_source!=='manual-required')state.selected.add(i)}
  if(oldStatus==='reviewing'&&!busy()){for(const i of state.selected)if(issues(data.candidates[i]||{}).length)state.selected.delete(i);if(state.index!==null&&!state.dirty)await selectClip(state.index,true)}
  if(!state.dirty)$('saveState').textContent=busy()?'Sedang diproses':state.selected.size+' clip dipilih';paintCandidates();updateControls();
  if(state.index===null&&data.candidates.length)await selectClip(0,true);
 }catch(e){$('error').textContent=e.message;$('errorDetails').classList.remove('hidden')}
 clearTimeout(state.poll);state.poll=setTimeout(refresh,busy()?1400:6000);
}
async function selectClip(i,quiet=false){
 if(state.dirty&&!quiet&&!confirm('Koreksi belum disimpan. Pindah clip?'))return;
 try{
  const job=state.job,requestToken=++state.selectionToken;const editor=await api(`/api/editor/${job}/${i}`);if(job!==state.job||requestToken!==state.selectionToken)return;
  state.index=i;state.editor=editor;state.dirty=false;state.draw=null;$('viewer').classList.remove('drawing');
  const {clip:c,settings:s}=editor;$('title').value=c.title;$('start').value=tc(c.start,true);$('end').value=tc(c.end,true);$('keywords').value=(c.keywords||[]).join(', ');$('hookStart').value=c.cold_open_span?.[0]?.toFixed(2)||'';$('hookEnd').value=c.cold_open_span?.[1]?.toFixed(2)||'';
  for(const id of optionIds){let v=s[id];if(id==='aspect')v=s.target_w>s.target_h?'16:9':'9:16';if(id==='trim')v=s.trim_silence;if($(id).type==='checkbox')$(id).checked=!!v;else if(v!==undefined)$(id).value=v}
  $('audioInfo').textContent=(s.music_path?'Musik tersedia. ':'Belum ada musik. ')+(s.sfx_path?'Efek suara tersedia.':'Belum ada efek suara.');
  $('hookInfo').textContent=c.cold_open_span?'Kutipan pembuka sudah memiliki waktu sumber.':'Belum ada kutipan pembuka yang terverifikasi; judul tetap dapat tampil.';
  $('warnings').textContent=[...issues(c),...(c.warnings||[]).filter(x=>!x.startsWith('Batas topik dinilai'))].join(' ');
  showSource(c.start);paintWords();paintCandidates();updateControls();updateRange();
 }catch(e){toast(e.message)}
}
function updateRange(){try{const b=bounds();$('clipScrub').min=b.start;$('clipScrub').max=Math.max(b.start+.01,b.end);$('clipDuration').textContent=Math.max(0,b.end-b.start).toFixed(1)+' dtk';$('sourceNote').textContent=state.mode==='source'?'Sumber asli · hasil '+$('aspect').value+' · gunakan Preview untuk melihat komposisi.':'Hasil '+$('aspect').value+' · '+(state.mode==='preview'?'preview 12 detik':'render tersimpan');drawRegions()}catch{}}
function showSource(time){
 state.mode='source';const v=$('video'),url='/api/source/'+state.job;v.pause();
 const seek=()=>{if(time!==undefined)v.currentTime=Math.min(time,Number.isFinite(v.duration)?v.duration:time);drawRegions()};
 if(v.getAttribute('src')!==url){v.src=url;v.onloadedmetadata=seek}else seek();
 v.classList.remove('hidden');$('emptyViewer').classList.add('hidden');$('cropOverlay').classList.remove('hidden');updateRange();
}
function playAt(time){showSource(time);$('video').play().catch(()=>{})}
function paintWords(){
 const parent=$('words');parent.replaceChildren();parent.classList.toggle('editing',$('editWords').checked);if(!state.editor)return;let b;try{b=bounds()}catch{return}
 const keys=new Set($('keywords').value.toLowerCase().split(',').map(x=>x.trim()));let paragraph=el('p');parent.append(paragraph);
 state.editor.words.forEach((w,i)=>{
  const word=el('span',w.word,'word');word.dataset.i=i;word.title=tc(w.start,true)+'–'+tc(w.end,true);word.contentEditable=$('editWords').checked?'true':'false';word.classList.toggle('outside',w.end<=b.start||w.start>=b.end);word.classList.toggle('keyword',keys.has(w.word.toLowerCase().replace(/[.,!?]/g,'')));
  word.onclick=()=>{if(!$('editWords').checked){if(w.start<b.start||w.start>=b.end)$('clipOnly').checked=false;playAt(w.start)}};
  word.oninput=()=>{w.word=word.textContent.trim();markDirty()};paragraph.append(word,document.createTextNode(' '));
  const next=state.editor.words[i+1];if(next&&(/[.!?]$/.test(w.word)||next.start-w.end>.8)){paragraph=el('p');parent.append(paragraph)}
 });
}
async function save(){
 if(!state.editor)return;const hs=$('hookStart').value,he=$('hookEnd').value;
 const data={...bounds(),title:$('title').value,keywords:$('keywords').value.split(',').map(x=>x.trim()).filter(Boolean),words:state.editor.words,cold_open_span:hs!==''&&he!==''?[Number(hs),Number(he)]:null,settings:options()};
 const result=await post(`/api/editor/${state.job}/${state.index}`,data);state.editor.clip=result.clip||{...state.editor.clip,...data,revision:result.revision};state.dirty=false;
 $('start').value=tc(state.editor.clip.start,true);$('end').value=tc(state.editor.clip.end,true);$('warnings').textContent=issues(state.editor.clip).join(' ');updateRange();$('saveState').textContent='Koreksi tersimpan';await refresh();return result;
}
async function review(indices){try{if(state.dirty)await save();await post('/api/review-boundaries/'+state.job,{indices});await refresh()}catch(e){toast(e.message)}}
$('reviewBoundary').onclick=()=>review([state.index]);$('reviewAll').onclick=()=>review(state.data.candidates.map((_,i)=>i));
$('newProject').onclick=()=>$('newDialog').showModal();$('startProject').onclick=()=>$('newProject').click();$('closeDialog').onclick=()=>$('newDialog').close();$('toggleInspector').onclick=()=>document.body.classList.toggle('inspector-open');
$('selectAll').onclick=()=>{state.data?.candidates.forEach((_,i)=>state.selected.add(i));paintCandidates();updateControls()};$('selectNone').onclick=()=>{state.selected.clear();paintCandidates();updateControls()};
$('uploadForm').onsubmit=async e=>{e.preventDefault();$('uploadError').textContent='';$('analyze').disabled=true;$('analyze').textContent='Menyiapkan sumber…';try{const form=new FormData(e.target);form.set('trim','1');form.set('caption_style','editorial');let result;if($('localPath').value.trim()){const data=Object.fromEntries([...form].filter(([,v])=>typeof v==='string'));if(form.get('music')?.size||form.get('sfx')?.size)throw Error('Untuk mode path video, isi path musik/efek juga.');result=await post('/api/local',data)}else{if(!$('sourceFile').files.length)throw Error('Pilih video atau isi path lokal.');result=await api('/api/upload',{method:'POST',body:form})}$('newDialog').close();await loadJob(result.job)}catch(err){$('uploadError').textContent=err.message}finally{$('analyze').disabled=false;$('analyze').textContent='Analisis video'}};
$('audioForm').onsubmit=async e=>{e.preventDefault();try{if(!state.job)throw Error('Buka sesi dahulu.');if(state.dirty)await save();await api('/api/audio/'+state.job,{method:'POST',body:new FormData(e.target)});e.target.reset();await refresh();if(state.index!==null)await selectClip(state.index,true);toast('Audio sesi diperbarui. Render ulang clip yang ingin menggunakan audio baru.')}catch(err){toast(err.message)}};
$('saveEdit').onclick=()=>save().then(()=>toast('Koreksi disimpan.')).catch(e=>toast(e.message));
for(const id of ['title','start','end','keywords','hookStart','hookEnd',...optionIds])$(id).addEventListener('input',()=>{markDirty();updateControls();updateRange()});
$('editWords').onchange=paintWords;$('keywords').onchange=paintWords;$('start').onchange=paintWords;$('end').onchange=paintWords;
$('markIn').onclick=()=>{if(state.mode!=='source')return toast('Buka tab Sumber untuk menandai batas.');$('start').value=tc($('video').currentTime,true);markDirty();paintWords();updateRange()};
$('markOut').onclick=()=>{if(state.mode!=='source')return toast('Buka tab Sumber untuk menandai batas.');$('end').value=tc($('video').currentTime,true);markDirty();paintWords();updateRange()};
$('playClip').onclick=()=>{try{$('clipOnly').checked=true;playAt(bounds().start)}catch(e){toast(e.message)}};
$('playBeginning').onclick=()=>{try{$('clipOnly').checked=true;playAt(bounds().start)}catch(e){toast(e.message)}};
$('playEnding').onclick=()=>{try{$('clipOnly').checked=true;const b=bounds();playAt(Math.max(b.start,b.end-8))}catch(e){toast(e.message)}};
$('clipScrub').oninput=()=>{if(state.mode!=='source')showSource(Number($('clipScrub').value));else $('video').currentTime=Number($('clipScrub').value)};
$('sourceTab').onclick=()=>{if(state.editor)showSource(bounds().start)};
function showResult(result,mode){if(!result)return;state.mode=mode;state.draw=null;$('viewer').classList.remove('drawing');$('video').pause();$('video').onloadedmetadata=null;$('video').src='/clips/'+encodeURIComponent(result.file);$('cropOverlay').classList.add('hidden');updateRange()}
$('resultTab').onclick=()=>showResult(state.data.clips.find(x=>x.index===state.index),'result');$('previewTab').onclick=()=>showResult(state.data.preview,'preview');
$('video').ontimeupdate=()=>{
 const v=$('video');$('timecode').textContent=tc(v.currentTime);
 if(state.mode==='source'&&state.editor){try{const b=bounds();$('clipScrub').value=v.currentTime;if($('clipOnly').checked&&!v.paused&&v.currentTime>=b.end){v.pause();v.currentTime=b.end}}catch{}
 for(const n of $('words').querySelectorAll('.word')){const w=state.editor.words[Number(n.dataset.i)];n.classList.toggle('current',!!w&&w.start<=v.currentTime&&w.end>v.currentTime)}}
};
$('video').onplay=()=>{if(state.mode==='source'&&state.editor&&$('clipOnly').checked){try{const b=bounds();if($('video').currentTime<b.start||$('video').currentTime>=b.end)$('video').currentTime=b.start}catch{}}};
$('context').onclick=async()=>{try{if(state.dirty)await save();const b=bounds();const d=await api(`/api/editor/${state.job}/${state.index}?start=${Math.max(0,b.start-10)}&end=${b.end+10}`);state.editor.words=d.words;paintWords()}catch(e){toast(e.message)}};
$('render').onclick=async()=>{try{if(state.dirty)await save();await post('/api/render/'+state.job,{indices:[...state.selected]});await refresh()}catch(e){toast(e.message)}};
$('preview').onclick=async()=>{try{if(state.dirty)await save();await post(`/api/preview/${state.job}/${state.index}`,{});await refresh()}catch(e){toast(e.message)}};
$('export').onclick=async()=>{try{if(state.dirty)await save();await post('/api/export/'+state.job,{indices:[...state.selected]});await refresh()}catch(e){toast(e.message)}};
$('resume').onclick=()=>post('/api/resume/'+state.job,{}).then(refresh).catch(e=>toast(e.message));
$('addClip').onclick=async()=>{try{if(state.dirty)await save();const start=state.mode==='source'?$('video').currentTime:0;const r=await post('/api/add-clip/'+state.job,{start,end:Math.min(state.editor?.duration||60,start+90)});state.selected.add(r.index);await refresh();await selectClip(r.index)}catch(e){toast(e.message)}};
$('openSearch').onclick=()=>$('searchDialog').showModal();$('closeSearch').onclick=()=>$('searchDialog').close();
$('search').onclick=async()=>{try{if(!state.job)return;const d=await api('/api/transcript/'+state.job+'?q='+encodeURIComponent($('searchText').value));$('searchResults').replaceChildren();for(const w of d.words.slice(0,50)){const b=el('button',tc(w.start)+' '+w.word,'small');b.onclick=()=>{$('clipOnly').checked=false;showSource(w.start);$('searchDialog').close()};$('searchResults').append(b)}if(!d.words.length)$('searchResults').textContent='Kata tidak ditemukan.'}catch(e){toast(e.message)}};
// Source-region editing uses the actual displayed image, excluding letterbox bars.
function videoBox(){const canvas=$('cropOverlay'),v=$('video');const w=canvas.clientWidth,h=canvas.clientHeight;if(!w||!h||!v.videoWidth)return null;const scale=Math.min(w/v.videoWidth,h/v.videoHeight);return {x:(w-v.videoWidth*scale)/2,y:(h-v.videoHeight*scale)/2,w:v.videoWidth*scale,h:v.videoHeight*scale}}
function drawRegions(){const canvas=$('cropOverlay');if(state.mode!=='source'||!canvas.clientWidth)return;canvas.width=canvas.clientWidth;canvas.height=canvas.clientHeight;const ctx=canvas.getContext('2d'),b=videoBox();if(!ctx||!b)return;ctx.clearRect(0,0,canvas.width,canvas.height);ctx.font='bold 12px sans-serif';for(const [id,label,color] of [['material_rect','Materi','#f6cf69'],['speaker_rect','Pembicara','#8bdbc2']]){const values=$(id).value.split(',').map(Number);if(!$(id).value||values.length!==4||values.some(x=>!Number.isFinite(x)))continue;const [x,y,w,h]=values;ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=2;ctx.strokeRect(b.x+x*b.w/100,b.y+y*b.h/100,w*b.w/100,h*b.h/100);ctx.fillText(label,b.x+x*b.w/100+5,b.y+y*b.h/100+17)}}
function beginDraw(id){if(!state.editor)return;if(state.mode!=='source')showSource(bounds().start);$('video').pause();state.draw=id;state.drawOld=$(id).value;$('viewer').classList.add('drawing');toast('Tarik kotak pada gambar sumber. Esc untuk batal.')}
$('drawMaterial').onclick=()=>beginDraw('material_rect');$('drawSpeaker').onclick=()=>beginDraw('speaker_rect');
function point(e){const c=$('cropOverlay').getBoundingClientRect(),b=videoBox();if(!b)return null;return [Math.max(0,Math.min(100,(e.clientX-c.left-b.x)/b.w*100)),Math.max(0,Math.min(100,(e.clientY-c.top-b.y)/b.h*100))]}
$('cropOverlay').onpointerdown=e=>{if(!state.draw)return;state.drag=point(e);if(state.drag)$('cropOverlay').setPointerCapture(e.pointerId)};
$('cropOverlay').onpointermove=e=>{if(!state.drag)return;const p=point(e);if(!p)return;const [x,y]=state.drag;$ (state.draw).value=[Math.min(x,p[0]),Math.min(y,p[1]),Math.abs(p[0]-x),Math.abs(p[1]-y)].map(v=>v.toFixed(2)).join(',');drawRegions()};
$('cropOverlay').onpointerup=e=>{if(!state.drag)return;const vals=$(state.draw).value.split(',').map(Number);if(vals.length!==4||vals[2]<5||vals[3]<5){$(state.draw).value=state.drawOld;toast('Kotak terlalu kecil. Tandai area lebih besar.')}else{$('layout').value='stream';markDirty()}state.drag=null;state.draw=null;$('viewer').classList.remove('drawing');drawRegions();updateRange()};
$('resetRegions').onclick=()=>{$('material_rect').value='';$('speaker_rect').value='';markDirty();drawRegions()};
if(typeof ResizeObserver!=='undefined')new ResizeObserver(drawRegions).observe($('viewer'));
window.addEventListener('resize',drawRegions);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(state.draw)$(state.draw).value=state.drawOld;state.draw=null;state.drag=null;$('viewer').classList.remove('drawing');drawRegions()}if(/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)||e.target.isContentEditable||!state.editor)return;if(e.key.toLowerCase()==='i')$('markIn').click();if(e.key.toLowerCase()==='o')$('markOut').click()});
window.addEventListener('beforeunload',e=>{if(state.dirty){e.preventDefault();e.returnValue=''}});
history().catch(e=>toast(e.message));api('/api/health').then(d=>{$('hardware').textContent=d.render?.available===false?'Render perlu diperiksa':(d.nvenc.available?'NVENC siap · ':'CPU encoder · ')+d.model;$('hardware').title=d.render?.detail||d.nvenc.detail||'Filter, subtitle, dan encode diperiksa.'}).catch(e=>{$('hardware').textContent='Periksa CEK_PRO.cmd';$('hardware').title=e.message});
