import {localDrafts} from './draft_storage.js?v=4.0.16.1';

const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n};
const split=value=>value.split(',').map(x=>x.trim()).filter(Boolean);
const clock=value=>`${Math.floor(value/60)}:${(value%60).toFixed(2).padStart(5,'0')}`;
const labels={claim:'Klaim utama cocok dengan sumber',caveats:'Syarat, risiko dan caveat tetap ada',conclusion:'Jawaban dan kesimpulan utuh',source_order:'Urutan segmen menjaga maksud sumber',critical_tokens:'Angka, satuan dan negasi sudah diperiksa',source_audio_visual:'Momen gambar dan suara sudah saya tinjau',duration_extension:'Saya menerima perluasan durasi ini',list_items:'Semua rincian daftar sudah saya periksa',speaker_identity:'Identitas speaker sudah saya cocokkan',opening_context:'Pembuka memiliki konteks yang cukup',weak_source_confidence:'Unit berkeyakinan lemah sudah saya dengarkan',financial_risk:'Asumsi dan risiko finansial tetap ada'};

export async function mountSelection(host,{api,project,beforeProcess=()=>{},onChange=()=>{},onOpenClip=()=>{},isActive=()=>true}){
 let alive=true,view=null,offset=0;const key=`clipper-m3-fields|${project.project_id}|source`;let draft={base_revision:project.revision,fields:{}};let corrupt=null;
 const raw=localDrafts.getItem(key);if(raw){try{const parsed=JSON.parse(raw);if(!parsed||!parsed.fields||typeof parsed.fields!=='object'||Array.isArray(parsed.fields)||!Number.isInteger(parsed.base_revision)||parsed.base_revision<0)throw Error('shape');draft=parsed}catch{corrupt=raw}}
 const live=()=>alive&&isActive();
 const initial=await api(`/projects/${project.project_id}/selection?offset=0&limit=25`);
 if(!live())return {destroy(){alive=false},getDrafts(){return draft.fields}};
 function persist(){if(corrupt!==null)throw Error('Draf rusak masih disimpan; unduh sebelum membuangnya.');localDrafts.setItem(key,JSON.stringify(draft))}
 function remember(name,value){draft.fields[name]=value;persist()}
 function clearPrefix(prefix){for(const k of Object.keys(draft.fields))if(k.startsWith(prefix))delete draft.fields[k];persist()}
 function field(parent,label,name,value='',type='text'){
  const wrap=node('label',undefined,'m3-field'),input=node(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;
  const stored=draft.fields[name]??value;if(type==='checkbox')input.checked=stored===true;else input.value=String(stored??'');
  wrap.append(node('span',label),input);parent.append(wrap);input.addEventListener(type==='checkbox'?'change':'input',()=>{try{remember(name,type==='checkbox'?input.checked:input.value)}catch(e){error.textContent=e.message}});return input;
 }
 function select(parent,label,name,choices,value){const wrap=node('label',undefined,'m3-field'),input=node('select');for(const [id,text] of choices){const option=node('option',text);option.value=id;input.append(option)}input.value=draft.fields[name]??value;wrap.append(node('span',label),input);parent.append(wrap);input.addEventListener('change',()=>{try{remember(name,input.value)}catch(e){error.textContent=e.message}});return input}
 const box=node('section',undefined,'card m3-panel');box.append(node('h2','M3 · Pilih cerita dan momen'),node('p','Cari ulang dari transkrip tersimpan. Dengarkan sumber dan terima kandidat sebelum membuat final.','help'));host.append(box);
 const error=node('p','', 'm3-error');error.setAttribute('role','alert');box.append(error);
 function action(parent,label,fn){const button=node('button',label);button.type='button';button.onclick=async()=>{if(!live())return;button.disabled=true;error.textContent='';try{if(corrupt!==null)throw Error('Draf rusak masih disimpan; unduh sebelum membuangnya.');await fn()}catch(e){if(live())error.textContent=e.message||String(e)}finally{button.disabled=false}};parent.append(button);return button}
 if(corrupt!==null){const warning=node('p','Draf M3 rusak; byte asli tetap tersedia.','m3-error');box.append(warning);const download=node('button','Unduh draf rusak');download.onclick=()=>{const link=node('a');link.href=URL.createObjectURL(new Blob([corrupt],{type:'application/json'}));link.download='draf-m3-rusak.json';link.click();URL.revokeObjectURL(link.href)};box.append(download);const discard=node('button','Buang draf rusak');discard.onclick=()=>{localDrafts.removeItem(key);corrupt=null;draft={base_revision:project.revision,fields:{}};warning.textContent='Draf rusak dibuang atas pilihan Anda.'};box.append(discard)}
 const form=node('div',undefined,'m3-fields');box.append(form);const previous=project.selection3?.requested_constraints||{};
 const query=field(form,'Instruksi / topik yang dicari','query',previous.query||'','textarea');
 const topics=field(form,'Topik berbeda, pisahkan koma','topics',(previous.topics||[]).join(', '));
 const count=field(form,'Jumlah rekomendasi (0 = semua yang memenuhi syarat)','count',previous.count??project.settings.num_clips??2,'number');
 const min=field(form,'Durasi minimum (detik)','min_seconds',previous.min_seconds??project.settings.min_clip_s??20,'number');
 const max=field(form,'Durasi maksimum (detik)','max_seconds',previous.max_seconds??project.settings.max_clip_s??120,'number');
 const start=field(form,'Cari mulai detik','start',previous.start??0,'number'),end=field(form,'Cari sampai detik','end',previous.end??project.source.info.duration,'number');
 const provider=select(form,'Pembuat proposal','provider',[['ollama','AI lokal yang sudah Anda pilih'],['rules','Aturan sumber · perlu penilaian manusia']],previous.provider||'ollama');
 const retrieval=select(form,'Pencarian','retrieval',[['auto','Otomatis · E5 jika tersedia'],['lexical','Teks dan kata sumber'],['e5','E5 lokal wajib tersedia']],previous.retrieval||'auto');
 const profile=select(form,'Profil sumber','profile',[['general','Umum'],['education','Edukasi'],['finance','Finansial'],['podcast','Podcast'],['gaming','Gaming'],['screen','Layar / demonstrasi']],previous.profile||'general');
 const scope=select(form,'Teks yang dicari','scope',[['display','Teks sumber yang disetujui'],['raw','Ucapan mentah tersimpan']],previous.scope||'display');
 const keywords=field(form,'Frasa wajib, pisahkan koma','keywords',(previous.keywords||[]).join(', '));const speakers=field(form,'Speaker yang dipilih, pisahkan koma','speakers',(previous.speakers||[]).join(', '));
 const signals=field(form,'Ukur petunjuk gambar dan suara','signals',previous.signals??true,'checkbox');
 const detail=node('details');detail.append(node('summary','Penanda, game dan model visual pilihan'));box.append(detail);
 const voice=field(detail,'Penanda suara, pisahkan koma','voice_markers',(previous.voice_markers||['clip that','klip itu','potong bagian ini']).join(', '));
 const game=field(detail,'Nama game untuk profil yang Anda tinjau','game_name',previous.game_name||''),hud=field(detail,'Tulisan HUD yang menandai momen, pisahkan koma','hud_terms',(previous.hud_terms||[]).join(', '));
 const vision=select(detail,'Pembacaan frame pilihan','visual_model',[['off','Frame bukti saja'],['smolvlm','SmolVLM lokal teruji'],['qwen3-vl','Qwen VL lokal teruji']],previous.visual_model||'off');
 detail.append(node('p','Profil game memerlukan contoh game Anda. Energi suara dan perubahan frame bukan bukti emosi atau kemenangan.','help'));
 const controls=node('div',undefined,'m3-actions');box.append(controls);
 action(controls,'Cari / cari ulang tanpa ASR ulang',async()=>{beforeProcess();const requested={query:query.value,topics:split(topics.value),count:Number(count.value),min_seconds:Number(min.value),max_seconds:Number(max.value),start:Number(start.value),end:Number(end.value),provider:provider.value,retrieval:retrieval.value,profile:profile.value,scope:scope.value,keywords:split(keywords.value),speakers:split(speakers.value),signals:signals.checked,voice_markers:split(voice.value),game_name:game.value,hud_terms:split(hud.value),visual_model:vision.value};const job=await api(`/projects/${project.project_id}/selection`,{expected_revision:draft.base_revision,constraints:requested});remember('queued_job_id',job.id);await onChange();if(live())status.textContent='Seleksi masuk antrean. Hasil lama tetap tersedia sampai hasil baru tersimpan.'});
 action(controls,'Bandingkan revisi terbaru',async()=>{const current=await api(`/projects/${project.project_id}/selection`);if(!live())return;comparison.textContent=`Draf memakai revisi ${draft.base_revision}; proyek terbaru revisi ${current.revision}. ${current.stale?'Teks atau timing berubah; lakukan seleksi ulang.':'Sumber hasil aktif belum berubah.'}`;view=current});
 action(controls,'Gunakan revisi terbaru untuk draf ini',async()=>{const current=await api(`/projects/${project.project_id}/selection`);if(!live())return;draft.base_revision=current.revision;persist();view=current;comparison.textContent='Draf tetap sama; basis revisi terbaru dipilih secara eksplisit.'});
 action(controls,'Muat hasil seleksi',()=>refresh());const comparison=node('p','', 'help');box.append(comparison);
 action(controls,'Gunakan rekomendasi yang diterima untuk render',async()=>{if(!view?.report.analysis_id)throw Error('Jalankan seleksi dahulu.');await api(`/projects/${project.project_id}/selection/render-set`,{expected_revision:view.revision,analysis_id:view.report.analysis_id,operation_id:crypto.randomUUID()});await onChange();if(live())await refresh()});
 const status=node('p','', 'help');status.setAttribute('role','status');box.append(status);
 const player=node(project.source.info.kind==='audio'?'audio':'video');player.controls=true;player.preload='metadata';player.className='m3-player';player.src=project.source.url||'';box.append(player);
 function seek(a,b=null){if(!live())return;const play=()=>{if(!live())return;player.currentTime=a;player.ontimeupdate=()=>{if(b!==null&&player.currentTime>=b){player.pause();player.ontimeupdate=null}};player.play().catch(()=>{})};if(player.readyState)play();else player.addEventListener('loadedmetadata',play,{once:true})}
 async function marker(){const current=view?.revision??project.revision;await api(`/projects/${project.project_id}/selection/marker`,{expected_revision:current,time:Number(player.currentTime||0),label:'Penanda saat review',operation_id:crypto.randomUUID()});await onChange();if(live())await refresh()}
 action(box,'Tandai momen saat ini (M)',marker);
 const keydown=event=>{if(event.key?.toLowerCase()!=='m'||event.ctrlKey||event.altKey||event.metaKey||event.repeat||!live())return;const tag=event.target?.tagName?.toLowerCase();if(['input','textarea','select'].includes(tag)||event.target?.isContentEditable)return;event.preventDefault();marker().catch(e=>{if(live())error.textContent=e.message})};document.addEventListener('keydown',keydown);
 const reportBox=node('div');box.append(reportBox);const candidates=node('div',undefined,'m3-candidates');box.append(candidates);
 const selected=new Map((Array.isArray(draft.fields.story_order)?draft.fields.story_order:[]).map(id=>[id,null]));const story=node('section',undefined,'m3-story');story.append(node('h3','Cerita dari beberapa segmen'),node('p','Centang kandidat dalam urutan yang diinginkan. Proposal gabungan tetap harus ditinjau dan diterima.','help'));box.append(story);
 const title=field(story,'Judul cerita gabungan','story_title','Cerita gabungan');
 action(story,'Review gabungan kandidat terpilih',async()=>{if(selected.size<2)throw Error('Pilih sedikitnya dua kandidat yang tidak bertumpang tindih.');await api(`/projects/${project.project_id}/selection/story`,{expected_revision:view.revision,analysis_id:view.report.analysis_id,candidate_ids:[...selected.keys()],title:title.value,operation_id:crypto.randomUUID()});await onChange();if(live())await refresh()});
 const pages=node('div',undefined,'m3-actions');box.append(pages);action(pages,'Kandidat sebelumnya',async()=>{offset=Math.max(0,offset-25);await refresh()});action(pages,'Kandidat berikutnya',async()=>{if(view?.next_offset===null)throw Error('Sudah di halaman terakhir.');offset=view?.next_offset??0;await refresh()});
 async function refresh(prefetched=null){const result=prefetched||await api(`/projects/${project.project_id}/selection?offset=${offset}&limit=25`);if(!live())return;view=result;if(result.source?.url&&player.getAttribute('src')!==result.source.url)player.src=result.source.url;reportBox.replaceChildren();candidates.replaceChildren();const report=result.report;
  if(!report.analysis_id){status.textContent='Belum ada seleksi M3. Anda dapat memulai dari transkrip tersimpan atau meninjau momen visual/audio tanpa transkrip.';return}
  status.textContent=`${result.total} kandidat · ${report.selection.recommended_ids.length} direkomendasikan · ${result.render_selection_count??0} klip dipilih untuk render · ${report.coverage.processed_chunks}/${report.coverage.chunks} jendela · ${report.index.provider==='e5'?'index E5':'index teks'}${report.index.cache_reused?' dipakai kembali':''}. ${report.score_label}`;
  if(result.stale)reportBox.append(node('p','Hasil seleksi usang. Teks, timing, atau speaker berubah; jalankan seleksi ulang sebelum menerima kandidat.','m3-error'));
  if(report.coverage.complete===false)reportBox.append(node('p','Sebagian rentang sumber belum berhasil dianalisis. Rekomendasi ini belum mewakili seluruh rentang; periksa kegagalan dan jalankan ulang.','m3-error'));
  for(const issue of (report.errors||[]).slice(0,8))reportBox.append(node('p','Proposal perlu diperiksa: '+issue.reason,'m3-error'));
  const signalReceipt=report.signals?.receipt||{};
  if(signalReceipt.gaming&&signalReceipt.gaming.ocr_status!=='ready')reportBox.append(node('p','Pembacaan HUD belum tersedia. Penanda game belum diperoleh dari model OCR.','help'));
  if((signalReceipt.model_results||[]).some(r=>r.model_result?.status!=='ready'))reportBox.append(node('p','Sebagian pembacaan frame oleh model visual belum tersedia; frame sumber tetap dapat ditinjau.','help'));
  if(report.selection.shortfall)reportBox.append(node('p',`Kurang ${report.selection.shortfall} dari jumlah diminta; mesin menjaga syarat dan tidak mengisi dengan cerita yang gagal.`,'help'));
  if(report.selection.topics_missing?.length)reportBox.append(node('p','Topik belum terwakili: '+report.selection.topics_missing.join(', '),'help'));
  for(const chapter of report.chapters||[]){const item=node('div',undefined,'m3-chapter');item.append(node('span',`${clock(chapter.start)} · ${chapter.summary}`));action(item,'Buka sumber bab',()=>seek(chapter.start,chapter.end));reportBox.append(item)}
  for(const c of result.candidates){const item=node('article',undefined,'m3-candidate');item.append(node('h3',c.title),node('p',`${c.duration.toFixed(2)} detik · ${c.recommended?'rekomendasi · ':''}${c.selection_status}`,'badge'),node('p',c.reason,'help'));
   const add=field(item,'Tambahkan ke susunan cerita',`story:${c.candidate_id}`,selected.has(c.candidate_id),'checkbox');add.addEventListener('change',()=>{if(add.checked)selected.set(c.candidate_id,c);else selected.delete(c.candidate_id);remember('story_order',[...selected.keys()])});
   c.source_spans.forEach((span,i)=>action(item,`Dengarkan segmen ${i+1} · ${clock(span.start)}–${clock(span.end)}`,()=>seek(span.start,span.end)));
   for(const role of ['claims','caveats','conclusion'])for(const evidence of c[role]||[]){item.append(node('blockquote',evidence.quote));action(item,`Buka ${role==='claims'?'klaim':role==='caveats'?'caveat':'penutup'} · ${clock(evidence.start)}`,()=>seek(evidence.start,evidence.end))}
   item.append(node('p','Keyakinan sumber: '+(c.confidence.status==='unknown'?'belum terukur untuk sebagian/seluruh unit':c.confidence.status)+'; akurasi makna belum diukur.','help'));
   for(const [name,score] of Object.entries(c.scores||{})){if(name==='model_proposal')continue;item.append(node('p',`${name}: ${score.value===null?'belum terukur':Number(score.value).toFixed(3)} · ${score.basis}`,'help'))}
   if(c.completeness.hard_blockers.length)item.append(node('p','Belum memenuhi syarat: '+c.completeness.hard_blockers.join(', '),'m3-error'));
   if(c.completeness.review_flags.length)item.append(node('p','Perlu diperiksa: '+c.completeness.review_flags.join(', '),'help'));
   for(const evidence of c.evidence||[]){const e=node('div',undefined,'m3-evidence');e.append(node('span',`${evidence.kind} · ${clock(evidence.time)}`));if(evidence.frame_url){const img=node('img');img.src=evidence.frame_url;img.alt='Frame sumber pada '+clock(evidence.time);img.loading='lazy';e.append(img)}action(e,'Buka momen',()=>seek(evidence.time));item.append(e)}
   const prefix=`review:${view.report.analysis_id}:${c.candidate_id}:`;const checks=(c.required_review||[]).map(name=>({name,input:field(item,labels[name]||name,prefix+name,false,'checkbox')}));const reason=field(item,'Alasan keputusan',prefix+'reason',c.human_decision?.reason||'','textarea');
   const decide=async status=>{const saved=await api(`/projects/${project.project_id}/selection/decision`,{expected_revision:view.revision,analysis_id:view.report.analysis_id,candidate_id:c.candidate_id,status,reviewed:checks.filter(r=>r.input.checked).map(r=>r.name),reason:reason.value,operation_id:crypto.randomUUID()});clearPrefix(prefix);draft.base_revision=saved.revision;persist();await onChange();if(live())await refresh()};
   const accept=action(item,'Terima kandidat',()=>decide('accepted'));accept.disabled=result.stale||c.completeness.hard_blockers.length>0;
   action(item,'Tolak kandidat',()=>decide('rejected'));action(item,'Simpan: perlu ditinjau',()=>decide('needs_review'));
   if(c.human_decision?.clip_id&&c.selection_status==='accepted')action(item,'Edit klip yang diterima',()=>onOpenClip(c.human_decision.clip_id));
   if(c.alternatives?.length)item.append(node('p',`${c.alternatives.length} alternatif serupa tetap tersedia; belum otomatis dirender.`,'help'));candidates.append(item);
  }
 }
 try{await refresh(initial)}catch(e){if(live())error.textContent=e.message}
 return {destroy(){alive=false;document.removeEventListener('keydown',keydown);player.pause();player.removeAttribute('src');player.load?.()},getDrafts(){return draft.fields}};
}
