'use strict';
const $ = id => document.getElementById(id);
const state = {job:null,index:null,data:null,editor:null,dirty:false,mode:'source',selected:new Set(),poll:null,draw:null,drag:null,loadedRevision:null,seen:new Set(),selectionToken:0,drawOld:''};
const optionIds = ['aspect','caption_style','motion_intensity','layout','caption_position','caption_align','caption_scale','accent_hex','punch_zoom','accent_font','cold_open','trim','music_db','sfx_db','framing_x','material_rect','speaker_rect','material_share','font_main','font_accent','caption_cleanup','caption_punctuation','transcript_correction','glossary','caption_backdrop','safe_placement','source_kind','audience','broll_mode','broll_provider','broll_max','preserve_material_pauses'];
const active = new Set(['queued','analyzing','reviewing','rendering','previewing','exporting','illustrating','automatic','discovering']);
const busy = () => active.has(state.data?.status);
function toast(text){$('toast').textContent=text;$('toast').classList.remove('hidden');clearTimeout(state.toastTimer);state.toastTimer=setTimeout(()=>$('toast').classList.add('hidden'),6000)}
function tc(t, precision=false){t=Math.max(0,Number(t)||0);const seconds=Math.floor(t);return [Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(x=>String(x).padStart(2,'0')).join(':')+(precision?'.'+String(Math.floor((t-seconds)*100+.001)).padStart(2,'0'):'')}
function seconds(value){const parts=String(value).trim().replace(',','.').split(':').map(Number);if(!String(value).trim()||parts.some(x=>!Number.isFinite(x)||x<0)||parts.length>3)throw Error('Gunakan waktu 00:18:36.92 atau detik 1116.92.');if(parts.length>1&&parts.slice(1).some(x=>x>=60))throw Error('Menit dan detik harus kurang dari 60.');return parts.reduce((n,x)=>n*60+x,0)}
function bounds(){return {start:seconds($('start').value),end:seconds($('end').value)}}
async function api(path, options={}){const r=await fetch(path,options);let data;try{data=await r.json()}catch{throw Error('Respons server tidak terbaca. Periksa terminal aplikasi.')}if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data}
const post=(path,data)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e}
function markDirty(){state.dirty=true;$('saveState').textContent='Koreksi belum disimpan';updateControls()}
function options(){return Object.fromEntries(optionIds.map(id=>[id,id==='caption_scale'?Number($(id).value)/100:$(id).type==='checkbox'?($(id).checked?'1':'0'):$(id).value]))}
function setOptions(s){for(const id of optionIds){let v=s[id];if(id==='aspect'&&s.target_w)v=s.target_w>s.target_h?'16:9':'9:16';if(id==='trim')v=s.trim_silence;if(v===undefined)continue;if(id==='caption_scale')v=Math.round(v*100);if($(id).type==='checkbox')$(id).checked=v===true||v===1||v==='1';else $(id).value=v}updateFontSample()}
function updatePlacementHint(){const manual=$('caption_position').value!=='auto';$('safe_placement').disabled=manual||state.index===null||!!busy();$('placementHint').textContent=manual?'Posisi manual terkunci. Ganti template tetap mempertahankan posisi ini.':'Posisi mengikuti adegan. Aktifkan ruang teks untuk menghindari materi atau pembicara.'}
function updateFontSample(){for(const [role,id] of [['main','fontSampleMain'],['accent','fontSampleAccent']]){const fontId=$('font_'+(role==='accent'&&!$('accent_font').checked?'main':role)).value;$(id).style.fontFamily='preview_'+fontId;$(id).style.fontStyle='normal';$(id).style.fontWeight='normal'}$('fontSampleAccent').style.color=$('accent_hex').value;$('sizeLabel').textContent=$('caption_scale').value+'%';$('font_accent').disabled=!$('accent_font').checked||busy()}

async function history(){const jobs=await api('/api/jobs');$('history').replaceChildren();for(const j of jobs){const b=el('button',j.name);b.title=j.name;b.onclick=()=>loadJob(j.id);$('history').append(b)}}
function issues(c){return [...new Set([...(c.boundary_review?.issues||[]),...(c.intelligence?.issues||[])])]}
function paintIntelligence(c){
 const box=$('intelligenceReview');box.replaceChildren();const d=c.intelligence;
 box.append(el('h3','Alasan cerita ini dipilih'));
 if(!d){box.append(el('p','Sesi ini belum mempunyai pemeriksaan cerita 3.1. Klik Periksa AI; transkripsi lama tetap dipakai.','tiny'));return}
 const label={ready:'Lolos pemeriksaan AI',needs_review:'Perlu review',stale:'Keputusan perlu diperbarui'}[d.status]||'Belum diperiksa';
 box.append(el('strong',label),el('p',d.summary||'Pembuka dan jawaban belum diverifikasi.','tiny'));
 for(const [key,name] of [['opening','Pembuka'],['development','Isi'],['payoff','Jawaban / penutup']]){
  const e=d.evidence?.[key];if(!e)continue;const b=el('button',name+' · '+tc(e.source_start),'quiet small');
  b.onclick=()=>playAt(e.source_start);box.append(b,el('p','“'+e.quote+'”','evidence-quote'));
 }
 box.append(el('p','B-roll: '+(d.broll==='contextual'?'Ilustrasi bila relevan. ':'Pertahankan pembicara. ')+(d.broll_reason||''),'tiny'));
 box.append(el('p',d.hook?'Kutipan pembuka: '+d.hook.quote:'Hook memakai pembukaan asli.','tiny'));
 if(d.issues?.length){const list=el('ul');for(const issue of d.issues)list.append(el('li',issue));box.append(list)}
 box.append(el('p','Pemeriksaan AI membantu seleksi; hasil ini bukan prediksi FYP.','tiny'));
}
function paintCandidates(){
 const parent=$('candidates');const scroll=parent.scrollTop;parent.replaceChildren();const candidates=state.data?.candidates||[];$('count').textContent=candidates.length;
 for(const [i,c] of candidates.entries()){
  const card=el('div',undefined,'card'+(i===state.index?' active':''));card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-pressed',String(i===state.index));card.onclick=()=>selectClip(i);card.onkeydown=e=>{if(e.key==='Enter')selectClip(i)};
  const check=document.createElement('input');check.type='checkbox';check.checked=state.selected.has(i);check.setAttribute('aria-label','Pilih '+c.title);check.onclick=e=>e.stopPropagation();check.onchange=()=>{check.checked?state.selected.add(i):state.selected.delete(i);updateControls()};
  card.append(check,el('div',String(i+1).padStart(2,'0')+' · '+Math.round(c.end-c.start)+' dtk','meta'),el('h3',c.title),el('div',tc(c.start)+' → '+tc(c.end),'meta'),el('p',c.reason,'reason'));
  const warning=issues(c).length||c.boundary_review?.status==='needs_review';const result=state.data.clips?.find(r=>r.index===i&&r.revision===c.revision&&r.render_version==='3.2');
  card.append(el('div',result?'✓ Render tersimpan':warning?'Periksa batas pembahasan':c.intelligence?.status==='ready'?'Cerita lolos pemeriksaan AI':c.boundary_review?.status==='checked'?'Konteks diperiksa · dengarkan hasilnya':'Kandidat · belum diperiksa','rubric'+(warning?' warn':'')));parent.append(card);
 }
 parent.scrollTop=scroll;
}
function updateControls(){
 const chosen=state.index!==null,selected=state.selected.size>0;document.body.classList.toggle('busy',!!busy());
 for(const id of ['saveEdit','preview','markIn','markOut','playBeginning','playEnding','playClip','context','reviewBoundary','drawMaterial','drawSpeaker','openTemplates','savePreset','reviewCleanup','usePreset','prepareBroll'])$(id).disabled=!chosen||!!busy();
 $('applyLook').disabled=!chosen||!selected||!!busy();$('render').disabled=!selected||!!busy();$('autoRun').disabled=!selected||!!busy();$('reviewAll').disabled=!state.data?.candidates?.length||!!busy();$('discoverMore').disabled=!state.data?.candidates?.length||!!busy();$('addClip').disabled=!state.data?.candidates?.length||!!busy();$('saveEdit').textContent=state.dirty?'Simpan koreksi •':'Simpan koreksi';$('render').textContent='Render '+(state.selected.size||'')+' pilihan';
 for(const id of optionIds)$(id).disabled=!chosen||!!busy();if(chosen)updateFontSample();updatePlacementHint();
 const result=state.data?.clips?.find(r=>r.index===state.index);$('resultTab').disabled=!result;$('download').classList.toggle('hidden',!result);
 $('resultTab').textContent=result&&(state.dirty||result.revision!==state.editor?.clip.revision||result.render_version!=='3.2')?'Hasil sebelumnya':'Hasil';
 $('downloadCredits').classList.toggle('hidden',!result?.broll_count);if(result?.broll_count)$('downloadCredits').href=result.credits_url||'/clips/'+encodeURIComponent(result.file.replace(/\.mp4$/,'.credits.txt'));
 $('downloadAss').classList.toggle('hidden',!result||result.render_version!=='3.2');
 if(result){$('downloadAss').href=result.ass_url||'/clips/'+encodeURIComponent(result.file.replace(/\.mp4$/,'.ass'));$('downloadAss').download=result.file.replace(/\.mp4$/,'.ass');$('download').href=result.url||'/clips/'+encodeURIComponent(result.file);$('download').download=result.file}
 const exportReady=!state.dirty&&selected&&[...state.selected].every(i=>state.data?.clips?.some(r=>r.index===i&&r.revision===(state.data.candidates[i].revision||0)&&r.render_version==='3.2'));
 $('export').disabled=!exportReady||!!busy();$('downloadBundle').classList.toggle('hidden',!state.data?.export);if(state.data?.export)$('downloadBundle').href='/api/download/'+state.job;
 const preview=state.data?.preview;$('previewTab').classList.toggle('hidden',!preview||preview.index!==state.index||preview.revision!==state.editor?.clip.revision||preview.render_version!=='3.2');$('previewTab').textContent=state.dirty?'Preview sebelumnya':'Preview';
 if(result&&state.editor&&result.revision!==state.editor.clip.revision&&!state.dirty)$('saveState').textContent='Koreksi tersimpan · render perlu diperbarui';
}
async function loadJob(id){
 if(state.dirty&&!confirm('Koreksi belum disimpan. Pindah proyek?'))return;
 try{clearTimeout(state.poll);state.job=id;state.index=null;state.editor=null;state.selected.clear();state.seen.clear();state.dirty=false;state.data=await api('/api/status/'+id);await refresh();if(state.data.candidates.length&&state.index===null)await selectClip(0);history().catch(()=>{})}catch(e){toast(e.message)}
}
async function refresh(){
 if(!state.job)return;const job=state.job;
 try{
  const oldStatus=state.data?.status,oldPreview=state.data?.preview?.file,oldResult=state.data?.clips?.find(r=>r.index===state.index)?.file;const data=await api('/api/status/'+job);if(job!==state.job)return;state.data=data;
  $('projectName').textContent=data.name||'Proyek lokal';$('message').textContent=data.message;$('progress').value=data.percent||0;$('elapsed').textContent=tc(data.elapsed);
  const report=data.selection_report||{};$('searchCoverage').textContent=report.windows?`${report.processed_windows}/${report.windows} jendela diperiksa · ${report.candidate_pool||0} kandidat unik · ${report.automatic_ready||0} lolos otomatis${report.coverage_complete?'':' · jelajah belum lengkap'}`:'Jumlah clip mengikuti isi yang layak.';$('error').textContent=data.error||'';$('errorDetails').classList.toggle('hidden',!data.error);$('resume').classList.toggle('hidden',!['interrupted','error'].includes(data.status));
  $('timings').textContent=Object.entries(data.timings||{}).map(([k,v])=>({analyzing:'Analisis',reviewing:'Review AI',rendering:'Render',previewing:'Preview',exporting:'Ekspor',illustrating:'Ilustrasi',automatic:'Otomatis'}[k]||k)+': '+tc(v)).join(' · ');
  for(const [i,c] of data.candidates.entries())if(!state.seen.has(i)){state.seen.add(i);if(!issues(c).length&&c.boundary_review?.status!=='needs_review'&&c.selection_source!=='manual-required')state.selected.add(i)}
  if(!busy()){
   if(oldStatus==='reviewing')for(const i of state.selected)if(issues(data.candidates[i]||{}).length)state.selected.delete(i);
   const changed=state.index!==null&&data.candidates[state.index]?.revision!==state.editor?.clip.revision;
   if(state.index!==null&&!state.dirty&&(changed||oldStatus==='reviewing'||oldStatus==='illustrating'))await selectClip(state.index,true);
   else if(oldResult!==data.clips?.find(r=>r.index===state.index)?.file)await loadIllustrations();
  }
  if(!state.dirty)$('saveState').textContent=busy()?'Sedang diproses':state.selected.size+' clip dipilih';paintCandidates();updateControls();
  if(state.index===null&&data.candidates.length)await selectClip(0,true);
  if(oldPreview!==data.preview?.file&&!busy()&&data.preview?.index===state.index&&!state.dirty)showResult(data.preview,'preview');
 }catch(e){$('error').textContent=e.message;$('errorDetails').classList.remove('hidden')}
 clearTimeout(state.poll);state.poll=setTimeout(refresh,busy()?1400:6000);
}
async function selectClip(i,quiet=false){
 if(state.dirty&&!quiet&&!confirm('Koreksi belum disimpan. Pindah clip?'))return;
 try{
  const job=state.job,requestToken=++state.selectionToken;const editor=await api(`/api/editor/${job}/${i}`);if(job!==state.job||requestToken!==state.selectionToken)return;
  state.index=i;state.editor=editor;state.dirty=false;state.draw=null;$('viewer').classList.remove('drawing');
  const {clip:c,settings:s}=editor;$('title').value=c.title;$('start').value=tc(c.start,true);$('end').value=tc(c.end,true);$('keywords').value=(c.keywords||[]).join(', ');$('hookStart').value=c.cold_open_span?.[0]?.toFixed(2)||'';$('hookEnd').value=c.cold_open_span?.[1]?.toFixed(2)||'';
  setOptions(s);$('clipScope').textContent=String(i+1).padStart(2,'0')+' · '+c.title;
  $('audioInfo').textContent=(s.music_path?'Musik tersedia. ':'Belum ada musik. ')+(s.sfx_path?'Efek suara tersedia.':'Belum ada efek suara.');
  $('hookInfo').textContent=c.cold_open_span?'Kutipan pembuka sudah memiliki waktu sumber.':'Belum ada kutipan pembuka yang terverifikasi; video dimulai dari awal clip.';
  $('warnings').textContent=[...issues(c),...(c.warnings||[]).filter(x=>!x.startsWith('Batas topik dinilai'))].join(' ');
  paintIntelligence(c);showSource(c.start);paintWords();paintCandidates();updateControls();updateRange();loadIllustrations();
 }catch(e){toast(e.message)}
}
function updateRange(){try{const b=bounds();$('clipScrub').min=b.start;$('clipScrub').max=Math.max(b.start+.01,b.end);$('clipDuration').textContent=Math.max(0,b.end-b.start).toFixed(1)+' dtk';$('sourceNote').textContent=state.mode==='source'?'Sumber asli · hasil '+$('aspect').value+' · gunakan Preview untuk melihat komposisi.':'Hasil '+$('aspect').value+' · '+(state.mode==='preview'?'preview '+Number(state.data?.preview?.length||0).toFixed(1)+' detik':'render tersimpan');drawRegions()}catch{}}
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
  const word=el('span',w.word,'word');word.dataset.i=i;word.title=tc(w.start,true)+'–'+tc(w.end,true);word.contentEditable=$('editWords').checked?'true':'false';word.classList.toggle('uncertain',w.probability<.5&&!w.correction&&!w.manually_edited);word.classList.toggle('corrected',!!w.correction);if(w.raw_word)word.title+=' · sebelumnya: '+w.raw_word;if(w.probability<.5&&!w.correction)word.title+=' · dengarkan kata ini';word.classList.toggle('outside',w.end<=b.start||w.start>=b.end);word.classList.toggle('keyword',keys.has(w.word.toLowerCase().replace(/[.,!?]/g,'')));
  word.onclick=()=>{if(!$('editWords').checked){if(w.start<b.start||w.start>=b.end)$('clipOnly').checked=false;playAt(w.start)}};
  word.oninput=()=>{w.word=word.textContent.trim();w.manually_edited=true;markDirty()};paragraph.append(word,document.createTextNode(' '));
  const next=state.editor.words[i+1];if(next&&(/[.!?]$/.test(w.word)||next.start-w.end>.8)){paragraph=el('p');parent.append(paragraph)}
 });
}
async function save(){
 if(!state.editor)return;const hs=$('hookStart').value,he=$('hookEnd').value;
 const data={...bounds(),title:$('title').value,keywords:$('keywords').value.split(',').map(x=>x.trim()).filter(Boolean),words:state.editor.words,cold_open_span:hs!==''&&he!==''?[Number(hs),Number(he)]:null,settings:options()};
 const result=await post(`/api/editor/${state.job}/${state.index}`,data);state.editor.clip=result.clip||{...state.editor.clip,...data,revision:result.revision};state.dirty=false;if(result.settings){state.editor.settings=result.settings;setOptions(result.settings)}
 $('start').value=tc(state.editor.clip.start,true);$('end').value=tc(state.editor.clip.end,true);$('warnings').textContent=issues(state.editor.clip).join(' ');updateRange();$('saveState').textContent='Koreksi tersimpan';await refresh();return result;
}
async function review(indices){try{if(state.dirty)await save();await post('/api/review-boundaries/'+state.job,{indices});await refresh()}catch(e){toast(e.message)}}
$('autoRun').onclick=async()=>{try{if(state.dirty)await save();await post('/api/automatic/'+state.job,{indices:[...state.selected]});await refresh()}catch(e){toast(e.message)}};
$('reviewBoundary').onclick=()=>review([state.index]);$('reviewAll').onclick=()=>review(state.data.candidates.map((_,i)=>i));
$('newProject').onclick=()=>$('newDialog').showModal();$('startProject').onclick=()=>$('newProject').click();$('closeDialog').onclick=()=>$('newDialog').close();$('toggleInspector').onclick=()=>document.body.classList.toggle('inspector-open');
$('selectAll').onclick=()=>{state.data?.candidates.forEach((_,i)=>state.selected.add(i));paintCandidates();updateControls()};$('selectNone').onclick=()=>{state.selected.clear();paintCandidates();updateControls()};
$('uploadForm').onsubmit=async e=>{e.preventDefault();$('uploadError').textContent='';$('analyze').disabled=true;$('analyze').textContent='Menyiapkan sumber…';try{const form=new FormData(e.target);form.set('trim','1');let result;if($('localPath').value.trim()){const data=Object.fromEntries([...form].filter(([,v])=>typeof v==='string'));if(form.get('music')?.size||form.get('sfx')?.size)throw Error('Untuk mode path video, isi path musik/efek juga.');result=await post('/api/local',data)}else{if(!$('sourceFile').files.length)throw Error('Pilih video atau isi path lokal.');result=await api('/api/upload',{method:'POST',body:form})}$('newDialog').close();await loadJob(result.job)}catch(err){$('uploadError').textContent=err.message}finally{$('analyze').disabled=false;$('analyze').textContent='Mulai proses'}};
$('audioForm').onsubmit=async e=>{e.preventDefault();try{if(!state.job)throw Error('Buka sesi dahulu.');if(state.dirty)await save();await api('/api/audio/'+state.job,{method:'POST',body:new FormData(e.target)});e.target.reset();await refresh();if(state.index!==null)await selectClip(state.index,true);toast('Audio sesi diperbarui. Render ulang clip yang ingin menggunakan audio baru.')}catch(err){toast(err.message)}};
$('saveEdit').onclick=()=>save().then(()=>toast('Koreksi disimpan.')).catch(e=>toast(e.message));
for(const id of ['title','start','end','keywords','hookStart','hookEnd',...optionIds])$(id).addEventListener('input',()=>{markDirty();updateControls();updateRange();updateFontSample()});
$('editWords').onchange=paintWords;$('keywords').onchange=paintWords;$('start').onchange=paintWords;$('end').onchange=paintWords;
$('markIn').onclick=()=>{if(state.mode!=='source')return toast('Buka tab Sumber untuk menandai batas.');$('start').value=tc($('video').currentTime,true);markDirty();paintWords();updateRange()};
$('markOut').onclick=()=>{if(state.mode!=='source')return toast('Buka tab Sumber untuk menandai batas.');$('end').value=tc($('video').currentTime,true);markDirty();paintWords();updateRange()};
$('playClip').onclick=()=>{try{$('clipOnly').checked=true;playAt(bounds().start)}catch(e){toast(e.message)}};
$('playBeginning').onclick=()=>{try{$('clipOnly').checked=true;playAt(bounds().start)}catch(e){toast(e.message)}};
$('playEnding').onclick=()=>{try{$('clipOnly').checked=true;const b=bounds();playAt(Math.max(b.start,b.end-8))}catch(e){toast(e.message)}};
$('clipScrub').oninput=()=>{if(state.mode!=='source')showSource(Number($('clipScrub').value));else $('video').currentTime=Number($('clipScrub').value)};
$('sourceTab').onclick=()=>{if(state.editor)showSource(bounds().start)};
function showResult(result,mode){if(!result)return;state.mode=mode;state.draw=null;$('viewer').classList.remove('drawing');$('video').pause();$('video').onloadedmetadata=null;$('video').src=result.url||'/clips/'+encodeURIComponent(result.file);$('cropOverlay').classList.add('hidden');updateRange()}
$('resultTab').onclick=()=>showResult(state.data.clips.find(x=>x.index===state.index),'result');$('previewTab').onclick=()=>showResult(state.data.preview,'preview');
$('video').ontimeupdate=()=>{
 const v=$('video');$('timecode').textContent=tc(v.currentTime);
 if(state.mode==='source'&&state.editor){try{const b=bounds();$('clipScrub').value=v.currentTime;if($('clipOnly').checked&&!v.paused&&v.currentTime>=b.end){v.pause();v.currentTime=b.end}}catch{}
 for(const n of $('words').querySelectorAll('.word')){const w=state.editor.words[Number(n.dataset.i)];n.classList.toggle('current',!!w&&w.start<=v.currentTime&&w.end>v.currentTime)}}
};
$('video').onplay=()=>{if(state.mode==='source'&&state.editor&&$('clipOnly').checked){try{const b=bounds();if($('video').currentTime<b.start||$('video').currentTime>=b.end)$('video').currentTime=b.start}catch{}}};
$('context').onclick=async()=>{try{if(state.dirty)await save();const b=bounds();const d=await api(`/api/editor/${state.job}/${state.index}?start=${Math.max(0,b.start-10)}&end=${b.end+10}`);state.editor.words=d.words;paintWords()}catch(e){toast(e.message)}};
$('render').onclick=async()=>{try{if(state.dirty)await save();await post('/api/render/'+state.job,{indices:[...state.selected]});await refresh()}catch(e){toast(e.message)}};
$('preview').onclick=async()=>{try{let cursor=state.mode==='source'?$('video').currentTime:(state.data?.preview?.index===state.index?state.data.preview.source_start:bounds().start);if(state.dirty)await save();const b=bounds();cursor=cursor>=b.end-.5?Math.max(b.start,b.end-12):Math.max(b.start,cursor);await post(`/api/preview/${state.job}/${state.index}`,{source_start:cursor});await refresh()}catch(e){toast(e.message)}};
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
initFonts().then(history).catch(e=>toast(e.message));api('/api/health').then(d=>{$('hardware').textContent=d.render?.available===false?'Render perlu diperiksa':(d.nvenc.available?'NVENC siap · ':'CPU encoder · ')+d.model;$('hardware').title=d.render?.detail||d.nvenc.detail||'Filter, subtitle, dan encode diperiksa.'}).catch(e=>{$('hardware').textContent='Periksa CEK_PRO.cmd';$('hardware').title=e.message});

// Rendered previews use the same ASS typography engine as the final MP4.
$('openTemplates').onclick=async()=>{
 try{const templates=await api('/api/templates');$('templateGrid').replaceChildren();
 for(const t of templates){const card=el('article',undefined,'template-card');card.dataset.selected=String(Object.entries(t.settings).every(([k,v])=>String(options()[k])===String(typeof v==='boolean'?(v?'1':'0'):v)));
 const video=el('video');video.src=t.preview;video.poster=t.poster;video.muted=true;video.loop=true;video.playsInline=true;video.controls=true;video.preload='none';video.setAttribute('aria-label','Contoh '+t.name);video.onclick=e=>e.stopPropagation();
 const pick=el('button','Gunakan template','template-pick');pick.setAttribute('aria-label','Gunakan '+t.name);pick.setAttribute('aria-pressed',card.dataset.selected);card.append(video,el('h2',t.name),el('p',t.description),pick);
 pick.onclick=()=>{setOptions(t.settings);markDirty();$('templateDialog').close();toast(t.name+' dipilih. Preview untuk melihat hasilnya.');};$('templateGrid').append(card);
 }$('templateDialog').showModal();
 }catch(e){toast(e.message)}
};
$('closeTemplates').onclick=()=>$('templateDialog').close();
$('templateDialog').addEventListener('close',()=>{$('templateGrid').querySelectorAll('video').forEach(v=>v.pause())});
$('applyLook').onclick=async()=>{try{if(state.dirty)await save();const settings=options();const r=await post('/api/apply-template/'+state.job,{indices:[...state.selected],settings});await refresh();await selectClip(state.index,true);toast('Gaya diterapkan ke '+r.count+' clip. Render ulang saat siap.')}catch(e){toast(e.message)}};

async function initFonts(){const fonts=await api('/api/fonts');const sheet=document.createElement('style');sheet.textContent=fonts.map(f=>`@font-face{font-family:preview_${f.id};src:url('${f.url}') format('truetype');font-display:swap}`).join('\n');document.head.append(sheet);for(const id of ['font_main','font_accent']){for(const f of fonts){const opt=el('option',f.label);opt.value=f.id;$(id).append(opt)}}$('font_main').value='dm_sans';$('font_accent').value='dm_serif_italic';updateFontSample();await loadPresets()}
async function loadPresets(){state.userPresets=await api('/api/style-presets');$('userPreset').replaceChildren(el('option','Pilih preset tersimpan'));$('userPreset').firstChild.value='';for(const p of state.userPresets){const o=el('option',p.name);o.value=p.id;$('userPreset').append(o)}}
$('savePreset').onclick=async()=>{try{const p=await post('/api/style-presets',{name:$('presetName').value,settings:options()});await loadPresets();$('userPreset').value=p.id;$('presetName').value='';toast('Preset tersimpan di komputer.')}catch(e){toast(e.message)}};
$('usePreset').onclick=()=>{const p=state.userPresets?.find(p=>p.id===$('userPreset').value);if(!p)return toast('Pilih preset dahulu.');setOptions(p.settings);markDirty();toast(p.name+' digunakan untuk clip aktif.')};
$('deletePreset').onclick=async()=>{const id=$('userPreset').value;if(!id)return;try{await api('/api/style-presets/'+id,{method:'DELETE'});await loadPresets();toast('Preset dihapus; gaya pada clip tidak berubah.')}catch(e){toast(e.message)}};
const panelHelp={styleTab:'Pilih font, ukuran, warna, dan gerak untuk clip aktif. Posisi teks diatur pada Visual.',frameTab:'Otomatis mencari ruang kosong di tiap adegan. Jika penuh, gambar diberi ruang subtitle. Posisi manual mengunci pilihan Anda.',storyTab:'Ubah kata, nama clip, serta awal dan akhir pembahasan. Koreksi subtitle tidak mengubah suara sumber.',audioTab:'Musik dan efek berlaku untuk sesi; volume di bawah berlaku untuk clip aktif.'};
const tabButtons=[...document.querySelectorAll('.inspector-tabs button')];
function choosePanel(button){$('editHelp').textContent=panelHelp[button.id]||'';for(const b of tabButtons){const chosen=b===button;b.setAttribute('aria-selected',String(chosen));b.tabIndex=chosen?0:-1;$(b.dataset.panel).classList.toggle('hidden',!chosen)}document.querySelector('.inspector-body').scrollTop=0}
for(const [i,b] of tabButtons.entries()){b.setAttribute('aria-controls',b.dataset.panel);b.tabIndex=i? -1:0;b.onclick=()=>choosePanel(b);b.onkeydown=e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();const next=tabButtons[(i+(e.key==='ArrowRight'?1:3))%4];choosePanel(next);next.focus()}}
$('reviewCleanup').onclick=async()=>{try{if(state.dirty)await save();const r=await api(`/api/subtitle-review/${state.job}/${state.index}`);$('cleanupOriginal').textContent=r.original.map(w=>w.word).join(' ');$('cleanupDisplay').textContent=r.display.map(w=>w.word).join(' ');$('cleanupStats').textContent=r.changes.length+' penyesuaian tampilan; '+r.warnings.length+' bagian perlu diperiksa.';$('cleanupWarnings').replaceChildren();for(const w of r.changes.filter(x=>x.before&&x.after)){$('cleanupWarnings').append(el('p',tc(w.start)+' · '+w.before+' → '+w.after,'tiny'))}for(const w of r.warnings){const b=el('button',tc(w.start)+' · '+w.text+' — '+w.reason,'quiet small');b.onclick=()=>{$('cleanupDialog').close();playAt(w.start)};$('cleanupWarnings').append(b)}$('cleanupDialog').showModal()}catch(e){toast(e.message)}};
$('closeCleanup').onclick=()=>$('cleanupDialog').close();

// Contextual stock controls: credentials never returned to this page.
async function openStock(){try{const d=await api('/api/stock-settings');$('stockFolder').value=d.local_dir;for(const n of ['Pexels','Pixabay','Coverr']){$('key'+n).value='';$('clear'+n).checked=false}$('stockSummary').textContent=d.local_count+' video lokal · '+d.providers.map(p=>p.id+': '+(p.configured?'key tersimpan':'belum diisi')).join(' · ');$('stockError').textContent='';$('stockDialog').showModal()}catch(e){toast(e.message)}}
$('openStock').onclick=openStock;$('stockShortcut').onclick=openStock;$('closeStock').onclick=()=>$('stockDialog').close();
$('stockForm').onsubmit=async e=>{e.preventDefault();const data={local_dir:$('stockFolder').value,clear:[]};for(const n of ['Pexels','Pixabay','Coverr']){data[n.toLowerCase()]=$('key'+n).value;if($('clear'+n).checked)data.clear.push(n.toLowerCase())}try{await post('/api/stock-settings',data);$('stockDialog').close();toast('Koleksi dan API tersimpan. Pilih mode ilustrasi pada tab Visual.')}catch(err){$('stockError').textContent=err.message}};
$('prepareBroll').onclick=async()=>{try{if($('broll_mode').value==='off')return toast('Pilih Koleksi lokal atau Otomatis terlebih dahulu.');if(state.dirty)await save();await post('/api/prepare-illustrations/'+state.job,{indices:[state.index]});await refresh()}catch(e){toast(e.message)}};
async function loadIllustrations(){if(state.index===null)return;const job=state.job,index=state.index;try{const data=await api(`/api/illustrations/${job}/${index}`);if(job!==state.job||index!==state.index)return;$('brollStatus').textContent=(data.scenes.length?data.scenes.length+' sisipan tersedia. ':'')+(data.notes||[]).join(' ');$('brollScenes').replaceChildren();for(const item of data.scenes){const card=el('article',undefined,'broll-card');const toggle=el('input');toggle.type='checkbox';toggle.checked=item.enabled;toggle.setAttribute('aria-label','Gunakan '+item.query);const label=el('label',tc(item.source_start)+' · '+item.query);label.prepend(toggle);const v=el('video');v.src=item.preview;v.controls=true;v.muted=true;v.preload='none';card.append(label,v,el('p',item.reason,'tiny'),el('p',item.quote,'tiny muted'));const credit=el('a',item.asset.author+' / '+item.asset.provider,'tiny');if(/^https:\/\//.test(item.asset.page_url)){credit.href=item.asset.page_url;credit.target='_blank';credit.rel='noreferrer'}card.append(credit);toggle.onchange=async()=>{try{if(state.dirty)await save();await post(`/api/illustrations/${job}/${index}`,{id:item.id,enabled:toggle.checked});await refresh();await selectClip(index,true)}catch(e){toggle.checked=!toggle.checked;toast(e.message)}};$('brollScenes').append(card)}}catch(e){$('brollStatus').textContent=e.message}}

// Storage operations are server guarded while any video task is queued or active.
function byteSize(n){return n>=1024**3?(n/1024**3).toFixed(2)+' GB':(n/1024**2).toFixed(1)+' MB'}
async function refreshStorage(){const d=await api('/api/storage');$('cacheSize').textContent=byteSize(d.bytes)+' · '+d.files+' file sementara';$('outputFolder').textContent=d.output_folder;$('clearCache').disabled=d.busy||!d.files;$('organizeOutputs').disabled=d.busy;if(d.busy)$('storageMessage').textContent='Tunggu proses video selesai sebelum merapikan penyimpanan.'}
$('openStorage').onclick=async()=>{try{$('storageMessage').textContent='';$('storageDialog').showModal();await refreshStorage()}catch(e){$('storageMessage').textContent=e.message}};
$('closeStorage').onclick=()=>$('storageDialog').close();
$('clearCache').onclick=async()=>{try{$('clearCache').disabled=true;const d=await post('/api/storage/clear-cache',{});$('storageMessage').textContent=byteSize(d.freed_bytes)+' dibersihkan. Hasil final dan koreksi tetap tersimpan.'+(d.skipped_files?.length?' '+d.skipped_files.length+' file masih terkunci; tutup pemutar lalu ulangi.':'');if(state.mode==='preview'&&state.editor)showSource(bounds().start);await refreshStorage();await refresh()}catch(e){$('storageMessage').textContent=e.message}};
$('organizeOutputs').onclick=async()=>{try{$('organizeOutputs').disabled=true;const d=await post('/api/storage/organize',{});$('storageMessage').textContent=d.moved_files+' file dirapikan ke folder proyek.';await refreshStorage();await refresh()}catch(e){$('storageMessage').textContent=e.message}};
$('discoverMore').onclick=async()=>{try{if(state.dirty)await save();await post('/api/discover/'+state.job,{});await refresh()}catch(e){toast(e.message)}};
const controlHelp={preview:'Render contoh 12 detik mulai dari posisi video saat ini. Simpan koreksi otomatis terlebih dahulu.',saveEdit:'Simpan kata, batas, dan pengaturan untuk clip aktif.',autoRun:'Periksa cerita pada clip yang dicentang, lalu render hanya yang lolos dan buat paket editor.',render:'Render clip yang dicentang menggunakan koreksi tersimpan.',export:'Buat paket editable dari render terbaru: video tanpa teks, subtitle, audio, dan timeline editor.',reviewBoundary:'Periksa pembuka dan penutup clip aktif dengan konteks sumber. Tidak mengulang Whisper.',discoverMore:'Jelajah sumber yang tersimpan untuk mencari cerita tambahan; jumlah hasil tidak dipaksakan.',caption_style:'Pilih bagaimana teks masuk. Font dan posisi bisa diatur terpisah.',caption_position:'Otomatis mencari area aman. Kiri, kanan, dan bawah mengunci posisi manual.',caption_scale:'Ukuran dasar teks. Mesin mengecilkan frasa panjang agar tetap muat.',caption_punctuation:'Minimal hanya menyembunyikan tanda baca tepi kata; angka dan persentase dipertahankan.',glossary:'Kamus ejaan. Contoh: XAUUSD = hausd | xausd. Koreksi manual tidak ditimpa.',safe_placement:'Deteksi wajah dan pola tulisan pada beberapa frame. Area penuh mendapat jalur subtitle terpisah.',broll_mode:'Ilustrasi hanya dipakai bila relevan; AI boleh memilih tanpa sisipan.'};
for(const [id,help] of Object.entries(controlHelp)){const node=$(id);node.title=help;node.addEventListener('focus',()=>{$('editHelp').textContent=help});node.addEventListener('mouseenter',()=>{$('editHelp').textContent=help})}
