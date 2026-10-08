/* Stage 3 review: bounded pages, original audio, explicit fact approvals. */
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e};
const clock=n=>`${Math.floor(n/60)}:${(n%60).toFixed(2).padStart(5,'0')}`;
const input=(parent,label,value,type='text')=>{const l=node('label',label),e=node(type==='textarea'?'textarea':'input');if(type!=='textarea')e.type=type;e.value=value;e.setAttribute('aria-label',label);if(type==='number')e.step='.01';l.append(e);parent.append(l);return e};
const button=(parent,text,fn)=>{const b=node('button',text);b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn()}finally{b.disabled=false}};parent.append(b);return b};

export async function approveFactChanges(api,request){
 if(!request.operations.some(o=>['correct_word','correct_token'].includes(o.op)))return request;
 const review=await api('/correction-review',request),risks=review.reviews.filter(r=>r.requires_confirmation);
 if(!risks.length)return request;
 const approved=await new Promise(resolve=>{
  const dialog=node('dialog',undefined,'stage3-facts');dialog.append(node('h2','Periksa perubahan fakta'),node('p','Dengarkan sumber. Centang hanya bila perubahan angka, satuan, negasi atau syarat ini memang disengaja.'));
  const checks=[];for(const risk of risks){const box=node('section',undefined,'card');box.append(node('p','Sebelum: '+risk.before),node('p','Sesudah: '+risk.after),node('small',risk.categories.join(' · ')));const check=input(box,'Saya menyetujui perubahan fakta ini','','checkbox');checks.push(check);dialog.append(box)}
  let done=false;const finish=value=>{if(done)return;done=true;dialog.close();dialog.remove();resolve(value)};
  const save=button(dialog,'Setujui dan simpan',()=>finish(true));save.disabled=true;checks.forEach(c=>c.onchange=()=>save.disabled=!checks.every(c=>c.checked));
  button(dialog,'Kembali ke draf',()=>finish(false));dialog.addEventListener('cancel',e=>{e.preventDefault();finish(false)});dialog.addEventListener('close',()=>finish(false));document.body.append(dialog);dialog.showModal();
 });
 if(!approved)throw Error('Perubahan fakta belum disetujui. Draf tetap tersimpan.');
 const operations=request.operations.map(o=>({...o}));for(const risk of risks)operations[risk.operation_index].fact_confirmation=risk.confirmation_stamp;
 return {...request,operations};
}

export function mountTranscript3(root,{api,project,clipId=null,onChange=()=>{},onMessage=()=>{}}){
 let destroyed=false,generation=0,page=null,status=null,expected=project.revision,offset=0,rejectOffset=0,query='',whole=!clipId;
 const prefix=[project.project_id,clipId||'source'].join('|'),drafts=new Map();
 try{for(const pair of JSON.parse(localStorage.getItem('clipper-stage3-drafts')||'[]'))drafts.set(...pair)}catch{}
 const persist=()=>localStorage.setItem('clipper-stage3-drafts',JSON.stringify([...drafts]));
 const message=node('p','','help'),content=node('div');root.classList.add('transcript3');root.replaceChildren(message,content);
 const notice=text=>{if(!destroyed){message.textContent=text;onMessage(text)}};
 const action=(parent,text,fn)=>button(parent,text,async()=>{try{await fn()}catch(e){notice(e.message)}});
 function remember(key,e){e.oninput=()=>{if(!drafts.has(prefix+'|base'))drafts.set(prefix+'|base',expected);drafts.set(prefix+'|'+key,e.value);persist()}}
 function clear(key){drafts.delete(prefix+'|'+key);if(![...drafts.keys()].some(k=>k.startsWith(prefix+'|')&&k!==prefix+'|base'))drafts.delete(prefix+'|base');persist()}
 async function commit(operations,keys=[]){
  const correction=operations.every(o=>['correct_word','correct_token','align_words'].includes(o.op));
  const stamp=generation,request={project_id:project.project_id,clip_id:whole&&correction?null:clipId,variant_id:'portrait',expected_revision:drafts.get(prefix+'|base')??expected,operation_id:crypto.randomUUID(),operations};
  const approved=await approveFactChanges(api,request);if(destroyed||stamp!==generation)return;
  const result=await api('/changes',approved);if(destroyed||stamp!==generation)return;
  keys.forEach(clear);expected=result.revision;onChange(result);await refresh();
 }
 async function job(kind,options={}){const result=await api(`/projects/${project.project_id}/jobs`,{kind,clip_id:kind==='boundary_review'?clipId:whole?null:clipId,variant_id:'portrait',expected_revision:expected,options});notice(result.message||'Proses masuk antrean. Tutup panel untuk melihat status atau batalkan melalui antrean.');onChange(result)}
 async function refresh(){
  const stamp=++generation;notice('Memuat halaman transkrip dan laporan cerita…');
  try{
   const [words,report,latest]=await Promise.all([api(`/projects/${project.project_id}/words?`+new URLSearchParams({clip_id:whole?'':clipId||'',whole:String(whole),offset,limit:60,q:query})),api(`/projects/${project.project_id}/stage3?`+new URLSearchParams({clip_id:clipId||'',offset:rejectOffset,limit:30})),api(`/projects/${project.project_id}`)]);
   if(destroyed||stamp!==generation)return;
   if(words.revision!==report.revision||latest.revision!==report.revision)throw Error('Revisi berubah saat memuat. Tekan Muat revisi terbaru; draf tetap tersimpan.');
   project=latest;page=words;status=report;expected=report.revision;render();notice(`Tahap 3 · revisi ${expected} · ${words.total} kata dalam cakupan aktif`);
  }catch(e){if(!destroyed&&stamp===generation)notice(e.message)}
 }
 function render(){
  content.replaceChildren();const player=node('video');player.className='source-video';player.controls=true;player.preload='metadata';player.src=project.source.url||'';content.append(player);
  const oldDrafts=[...drafts].filter(([key])=>key.startsWith(prefix+'|word:')&&!key.startsWith(prefix+'|word:'+page.transcript_id+':'));
  if(oldDrafts.length){const saved=node('details');saved.append(node('summary','Draf dari transkrip sebelumnya ('+oldDrafts.length+')'),node('p','Draf ini tetap tersimpan. Salin setelah memeriksa ucapan sumber; draf lama tidak diterapkan otomatis pada transkrip baru.'));for(const [key,value] of oldDrafts.slice(0,100)){const f=input(saved,key,value);f.readOnly=true}content.append(saved)}
  let stop=null;player.ontimeupdate=()=>{if(stop!==null&&player.currentTime>=stop){player.pause();stop=null}};
  const listen=(a,b)=>{stop=b;const go=()=>{player.currentTime=a;player.play().catch(()=>{})};if(player.readyState)go();else player.addEventListener('loadedmetadata',go,{once:true})};
  const tools=node('div',undefined,'row');content.append(tools);
  action(tools,'Muat revisi terbaru',async()=>{drafts.delete(prefix+'|base');persist();await refresh()});
  if(clipId)action(tools,whole?'Tampilkan kata dalam klip':'Buka seluruh transkrip',async()=>{whole=!whole;offset=0;await refresh()});
  const search=input(tools,'Cari dalam transkrip',query);action(tools,'Cari',async()=>{query=search.value;offset=0;await refresh()});
  const speech=node('section',undefined,'card');speech.append(node('h3','Koreksi & timing'),node('p','Uji ulang ASR memeriksa rentang terarah. Koreksi otomatis mempertahankan fakta dan edit manual. Timing manual disimpan terpisah dari teks.','help'));content.append(speech);
  const asr=node('select');asr.setAttribute('aria-label','Model ASR lokal');const defaultModel=node('option','Gunakan model ASR pengaturan proyek');defaultModel.value='';asr.append(defaultModel);for(const m of status.asr_models||[]){const option=node('option',m.model+' · '+m.component+' · lokal');option.value=m.id;asr.append(option)}speech.append(asr);
  action(speech,'Uji ulang kata berkeyakinan rendah',()=>job('asr_recheck',{limit:12,model_ref:asr.value}));action(speech,'Terapkan kamus ke transkrip tersimpan',()=>job('correction'));
  const modelKey='model_path',model=input(speech,'Folder model alignment lokal (opsional)',drafts.get(prefix+'|'+modelKey)??project.settings.alignment_model_path??'');remember(modelKey,model);
  speech.append(node('p',status.alignment.message,'help'));action(speech,'Simpan folder model',()=>commit([{op:'analysis_settings',values:{alignment_model_path:model.value}}],[modelKey]));
  action(speech,'Selaraskan frasa yang dikoreksi pada CPU',()=>job('alignment',{limit:12,model_path:model.value}));
  const report=status.speech_reports||{};for(const [name,result] of Object.entries(report)){const detail=node('details');detail.append(node('summary',(name==='alignment'?'Alignment':'Uji ulang ASR')+' terakhir'));if(name==='alignment'){const count=Number(result.aligned)||0,errors=result.errors||[];detail.append(node('p',errors.length?`${count} frasa berhasil; ${errors.length} ditolak. Timing yang ditolak tidak diterapkan.`:count?`${count} frasa berhasil diselaraskan pada ${result.device||'CPU'}.`:'Tidak ada frasa diselaraskan. Hasil ini belum membuktikan model berhasil mengukur timing.','help'))}detail.append(node('pre',JSON.stringify(result,null,2),'history-diff'));speech.append(detail)}
  if(!page.transcript_id){content.append(node('p','Analisis sumber dahulu untuk membuat transkrip.'));return}
  const list=node('div',undefined,'stage3-word-list');content.append(list);const seen=new Set();
  for(const base of page.words){
   const ids=base.group_origin_word_ids||base.source_word_ids||[base.word_id],key='word:'+page.transcript_id+':'+JSON.stringify(ids);if(seen.has(key))continue;seen.add(key);
   const w=base.group_edit?{...base,word:base.group_text,start:base.group_start,end:base.group_end,aligned_words:base.group_aligned_words}:base;
   const article=node('article',undefined,'stage3-word');list.append(article);const top=node('div',undefined,'row');article.append(top);
   action(top,`${clock(w.start)}–${clock(w.end)} · Dengar`,()=>listen(Math.max(0,w.start-2),Math.min(project.source.info.duration,w.end+2)));
   article.append(node('small','ASR asli: '+w.heard+' · asal: '+ids.join(', '),'help'));
   const text=input(article,base.group_edit?'Frasa yang disetujui':'Teks tampilan',drafts.get(prefix+'|'+key)??w.word);text.maxLength=120;remember(key,text);
   const scope=node('select');scope.setAttribute('aria-label','Cakupan koreksi');for(const [id,label] of (clipId&&!whole?[['clip','Hanya klip ini'],['shared_utterance','Ucapan bersama']]:[['shared_utterance','Ucapan bersama seluruh klip']])){const o=node('option',label);o.value=id;scope.append(o)}article.append(scope);
   action(article,'Simpan teks',()=>commit([{op:'correct_word',word_id:base.word_id,before:w.word,after:text.value,scope:scope.value,transcript_id:page.transcript_id,transcript_revision:page.transcript_revision}],[key]));
   article.append(node('small',w.aligned_words?'Timing kata: '+(w.alignment_method||'manual'):(w.word.split(/\s+/).length>1?'Timing frasa; kata belum diselaraskan':w.correction||w.manually_edited||ids.length>1?'Timing rentang asal; teks koreksi belum diselaraskan':'Timing ASR asli'),'help'));
   const details=node('details');details.append(node('summary','Atur timing kata'));article.append(details);
   details.append(node('p','Simpan teks dahulu. Dengarkan sumber dan isi awal/akhir setiap kata. Rentang frasa tidak dibagi rata secara otomatis.','help'));
   const times=w.word.trim().split(/\s+/).map((word,index)=>{const r=node('div',undefined,'row');r.append(node('span',word));details.append(r);const existing=w.aligned_words?.[index],aKey=key+':'+index+':start',bKey=key+':'+index+':end';const a=input(r,'Mulai '+word,drafts.get(prefix+'|'+aKey)??existing?.start??'' ,'number'),b=input(r,'Akhir '+word,drafts.get(prefix+'|'+bKey)??existing?.end??'','number');remember(aKey,a);remember(bKey,b);return {word,a,b,aKey,bKey}});
   action(details,'Simpan timing manual',async()=>{if(text.value!==w.word)throw Error('Simpan koreksi teks dahulu, lalu beri timing pada frasa terbaru.');if(times.some(t=>!t.a.value||!t.b.value))throw Error('Isi awal dan akhir semua kata.');await commit([{op:'align_words',scope:scope.value,transcript_id:page.transcript_id,transcript_revision:page.transcript_revision,origin_word_ids:ids,text:w.word,words:times.map(t=>({word:t.word,start:Number(t.a.value),end:Number(t.b.value)}))}],times.flatMap(t=>[t.aKey,t.bKey]))});
   action(details,'Dengarkan ulang ASR bagian ini',()=>job('asr_recheck',{limit:1,origin_word_ids:ids,model_ref:asr.value}));
  }
  const pages=node('div',undefined,'row');content.append(pages);pages.append(node('span',`${page.offset+1}–${Math.min(page.offset+page.words.length,page.total)} / ${page.total}`));
  const previous=action(pages,'← Sebelumnya',async()=>{offset=Math.max(0,offset-60);await refresh()});previous.disabled=offset===0;
  const next=action(pages,'Berikutnya →',async()=>{offset=page.next_offset;await refresh()});next.disabled=page.next_offset===null;
  const coverage=node('section',undefined,'card');coverage.append(node('h3','Cakupan seluruh sumber'));content.append(coverage);
  if(status.coverage_stale)coverage.append(node('p','Transkrip berubah sejak pencarian terakhir. Jelajah lagi untuk memperbarui cakupan dan kandidat.','warning'));
  const cov=status.coverage;coverage.append(node('p',cov.speech_segments!==undefined?`${cov.reviewed_segments}/${cov.speech_segments} segmen transkrip diperiksa; ${cov.pending_segments} belum diperiksa.`:'Laporan cakupan lama; jalankan Jelajah seluruh sumber untuk laporan Tahap 3.'));
  coverage.append(node('p',cov.basis||'Cakupan didasarkan pada jendela transkrip, bukan seluruh frame video.','help'));action(coverage,'Jelajah seluruh sumber & cari cerita berbeda',()=>job('discovery'));
  for(const chapter of status.chapters||[]){const detail=node('details');detail.append(node('summary',`${clock(chapter.start)}–${clock(chapter.end)} · ${chapter.label}`),node('p',`${chapter.status} · ${chapter.candidate_count} kandidat · ${chapter.story_kinds.join(', ')||'belum ada jenis cerita'}`));action(detail,'Dengar bab ini',()=>listen(chapter.start,chapter.end));coverage.append(detail)}
  const boundaries=node('section',undefined,'card');boundaries.append(node('h3',clipId?'Batas klip & konteks':'Buat klip dari transkrip'));content.append(boundaries);
  const chosen=clipId?project.clips[clipId]:null,a=input(boundaries,'Mulai sumber',chosen?.start??0,'number'),b=input(boundaries,'Selesai sumber',chosen?.end??Math.min(60,project.source.info.duration),'number'),title=input(boundaries,'Judul',chosen?.title??'Klip pilihan saya');
  action(boundaries,'Dengar rentang',()=>listen(Number(a.value),Number(b.value)));
  action(boundaries,clipId?'Simpan batas manual':'Tambah klip manual',()=>commit([{op:clipId?'bounds':'manual_clip',start:Number(a.value),end:Number(b.value),title:title.value}]));
  if(status.boundary_pin)boundaries.append(node('p','Batas manual disimpan. Pemeriksaan AI memberi usulan tanpa mengganti batas ini.','help'));
  for(const [name,context] of Object.entries(status.boundary_context||{})){if(!context||typeof context!=='object')continue;boundaries.append(node('p',context.quote));action(boundaries,name==='before'?'Dengar pembuka & konteks':'Dengar penutup & konteks',()=>listen(context.start,context.end))}
  if(status.boundary_proposal){const p=status.boundary_proposal;boundaries.append(node('p',`Usulan AI: ${clock(p.start)}–${clock(p.end)} · ${p.evidence}`));action(boundaries,'Isi kolom dengan usulan AI',()=>{a.value=p.start;b.value=p.end})}
  if(clipId)action(boundaries,'Periksa konteks dengan AI lokal',()=>job('boundary_review'));
  const rejected=node('section',undefined,'card');rejected.append(node('h3',`Kandidat dilewati (${status.rejection_total})`),node('p','Pemulihan menyimpan klip manual baru. Alasan penolakan tetap tersedia; penilaian otomatis tidak dianggap sudah lolos.','help'));content.append(rejected);
  for(const r of status.rejections){const detail=node('details');detail.append(node('summary',(r.title||r.code)+' · '+r.code),node('p',r.detail||''));rejected.append(detail);
   if(Number.isFinite(r.start)&&Number.isFinite(r.end)){const x=input(detail,'Mulai kandidat',r.start,'number'),y=input(detail,'Selesai kandidat',r.end,'number');action(detail,'Dengar kandidat',()=>listen(Number(x.value),Number(y.value)));action(detail,status.restored[r.rejection_id]?'Tersimpan; pulihkan rentang lain':'Pulihkan dengan batas ini',()=>commit([{op:'restore_rejected',rejection_id:r.rejection_id,start:Number(x.value),end:Number(y.value)}]))}
  }
  const rejects=node('div',undefined,'row');rejected.append(rejects);const rp=action(rejects,'← Penolakan sebelumnya',async()=>{rejectOffset=Math.max(0,rejectOffset-30);await refresh()});rp.disabled=rejectOffset===0;const rn=action(rejects,'Penolakan berikutnya →',async()=>{rejectOffset=status.next_offset;await refresh()});rn.disabled=status.next_offset===null;
 }
 refresh();return {destroy(){destroyed=true;generation++;root.replaceChildren()},refresh};
}
