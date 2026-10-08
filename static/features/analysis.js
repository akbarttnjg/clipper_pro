/* A-owned review component. Host B injects services and owns project revisions. */
export function mountAnalysis(root,{api,target,revision,onChange=()=>{},onListen=()=>{},onPreview=null}){
 if(!root||!api?.get_snapshot||!api?.submit_changes||!api?.run_stage)throw Error('Container dan layanan C0 diperlukan');
 let current={...target},expected=revision,snapshot=null,generation=0,destroyed=false;
 const drafts=new Map(),requests=new Map();
 try{for(const [k,v] of JSON.parse(sessionStorage.getItem('clipper-analysis-drafts')||'[]'))drafts.set(k,v)}catch{}
 const persistDrafts=()=>sessionStorage.setItem('clipper-analysis-drafts',JSON.stringify([...drafts]));
 const key=t=>[t.project_id,t.clip_id,t.variant_id].join('|');
 const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n};
 const time=n=>Number.isFinite(n)?`${Math.floor(n/60)}:${String(Math.floor(n%60)).padStart(2,'0')}`:'—';
 root.classList.add('analysis-panel');
 const message=node('p','','analysis-message');message.setAttribute('role','status');
 const content=node('div'),reload=node('button','Muat revisi terbaru');reload.type='button';reload.onclick=()=>refresh();root.replaceChildren(message,reload,content);
 function notice(text){if(!destroyed)message.textContent=text}
 function button(parent,text,handler,disabled=false){const b=node('button',text);b.type='button';b.disabled=disabled;b.onclick=()=>Promise.resolve(handler()).catch(e=>notice(e.message));parent.append(b);return b}
 function section(title,help){const s=node('section',undefined,'analysis-section');s.append(node('h3',title),node('p',help,'analysis-help'));content.append(s);return s}
 function input(parent,label,value='',type='text'){const l=node('label',label),e=node('input');e.type=type;if(type==='checkbox')e.checked=!!value;else e.value=value;l.append(e);parent.append(l);return e}
 function select(parent,label,choices,value){const l=node('label',label),e=node('select');for(const [id,text] of choices){const o=node('option',text);o.value=id;e.append(o)}e.value=value;l.append(e);parent.append(l);return e}
 function valid(stamp,t){return !destroyed&&stamp===generation&&key(t)===key(current)}
 async function refresh(){
  const stamp=++generation,t={...current},minimum=expected;
  content.inert=true;notice('Memuat bukti dan saran…');
  try{const result=await api.get_snapshot(t);
   if(!valid(stamp,t))return;
   if(result.schema_version!==1)throw Error('Snapshot versi ini belum didukung; data asli tidak diubah.');
   if(key(result.target)!==key(t))throw Error('Respons berasal dari target berbeda; panel tidak diperbarui.');
   if(!Number.isInteger(result.revision)||result.revision<minimum)throw Error('Respons lama diabaikan. Muat snapshot terbaru.');
   snapshot=result;expected=result.revision;render();content.inert=false;notice(`Revisi ${expected} · ${t.clip_id} / ${t.variant_id}`);
  }catch(e){if(valid(stamp,t))notice(e.message)}
 }
 async function commit(operations,draftKey){
  const stamp=generation,t={...current},payloadKey=JSON.stringify([t,expected,operations]);
  const operation_id=requests.get(payloadKey)||globalThis.crypto.randomUUID();requests.set(payloadKey,operation_id);
  const response=await api.submit_changes({...t,expected_revision:expected,operation_id,operations});
  if(!valid(stamp,t))return;
  if(response.status==='conflict'){notice('Ada perubahan dari tab lain. Draf Anda dipertahankan; muat revisi terbaru sebelum mencoba lagi.');return}
  if(response.status!=='ready'||!Number.isInteger(response.revision))throw Error(response.message||'Perubahan belum tersimpan. Draf Anda tetap tersedia.');
  if(draftKey){drafts.delete(draftKey);persistDrafts()}requests.delete(payloadKey);expected=response.revision;
  onChange({...t,revision:expected,operation_id});await refresh();
 }
 async function stage(stage_id){
  const stamp=generation,t={...current};const response=await api.run_stage({...t,expected_revision:expected,stage_id});
  if(valid(stamp,t))notice(response.message||'Tahap dimasukkan ke antrean proyek.');
 }
 function render(){
  content.replaceChildren();const data=snapshot.data||{},caps=snapshot.capabilities||{};
  const unpack=(value,kind)=>{if(!value)return null;if(value.schema_version!==1||value.kind!==kind||!value.payload)throw Error('Data analisis belum cocok dengan versi aplikasi. Muat ulang setelah integrasi diperbarui.');return {...value.payload,source_id:value.source_id}};
  const transcript=unpack(data.transcript,'TranscriptSnapshot');
  const review=section('Kata yang perlu didengar','Saran OCR adalah bukti tulisan, bukan kepastian ucapan. Dengarkan konteks sebelum menyimpan ejaan yang Anda setujui.');
  if(!transcript){review.append(node('p','Transkrip analisis belum tersedia.'));}
  else{
   const compare=node('details');compare.append(node('summary','Hasil transkripsi asli dan teks tampilan'));
   compare.append(node('p',(transcript.heard_words||[]).map(w=>w.word).join(' ')),node('hr'),node('p',(transcript.display_tokens||[]).map(t=>t.text).join(' ')));review.append(compare);
   if(!transcript.review_queue?.length)review.append(node('p','Tidak ada kata yang ditandai dalam snapshot ini.'));
   for(const row of transcript.review_queue||[]){
    const token=transcript.display_tokens.find(t=>t.token_id===row.token_id);if(!token)continue;
    const card=node('article',undefined,'analysis-card');review.append(card);card.append(node('h4',`${time(row.start)} · ${row.text}`),node('p',row.reason));
    button(card,'Dengarkan konteks',()=>onListen({...current,revision:expected,source_start:row.listen_start??Math.max(0,row.start-2),source_end:row.listen_end??row.end+2}));
    if(row.ocr){card.append(node('p',`Slide: “${row.ocr.text}” · keyakinan OCR ${Math.round(row.ocr.confidence*100)}%`));button(card,'Lihat materi',()=>onListen({...current,revision:expected,source_start:row.ocr.time,source_end:row.ocr.time,paused:true}))}
    const draftKey=key(current)+'|'+token.token_id;
    const text=input(card,'Ejaan yang Anda setujui',drafts.get(draftKey)??row.suggestions?.[0]??token.text);text.maxLength=120;text.oninput=()=>{drafts.set(draftKey,text.value);persistDrafts()};
    const scope=select(card,'Cakupan',[['clip','Clip ini'],['shared_utterance','Ucapan yang sama pada clip terkait']],'clip');
    if(!caps.shared_utterance){scope.options[1].disabled=true;scope.title='Koreksi lintas klip belum tersedia pada proyek ini'}
    button(card,'Simpan koreksi',()=>commit([{op:'correct_token',scope:scope.value,source_id:transcript.source_id,transcript_id:transcript.transcript_id,
     transcript_revision:transcript.revision,token_id:token.token_id,origin_word_ids:token.origin_word_ids,before:token.text,after:text.value,
     provenance:{kind:'user_approval',source_start:token.source_start,source_end:token.source_end}}],draftKey),!caps.correction||token.requires_alignment);
    if(token.requires_alignment)card.append(node('p','Frasa melintasi batas clip; perlu penyelarasan sebelum diterapkan.'));
   }
  }
  const aliases=section('Memori ejaan proyek','Tambahkan hanya alias yang sudah Anda dengarkan dan setujui. Menonaktifkan memori tidak menghapus koreksi manual.');
  const form=node('div',undefined,'analysis-card');aliases.append(form);let editId=null;
  const canonical=input(form,'Ejaan benar'),alias=input(form,'Alias salah dengar');
  const topic=select(form,'Topik',[['*','Semua topik proyek'],['finance','Keuangan'],['general','Umum'],['creators','Kreator'],['business','Bisnis'],['students','Pelajar']],'*');
  button(form,'Simpan alias',()=>commit([{op:'alias_upsert',id:editId,canonical:canonical.value,alias:alias.value,topic:topic.value,enabled:true}]),!caps.aliases);
  for(const row of data.aliases||[]){const card=node('div',undefined,'analysis-card');aliases.append(card);card.append(node('strong',`${row.alias} → ${row.canonical} · ${row.topic}`));
   const enabled=input(card,'Aktif',row.enabled,'checkbox');enabled.disabled=!caps.aliases;enabled.onchange=()=>commit([{op:'alias_upsert',...row,enabled:enabled.checked}]).catch(e=>notice(e.message));
   button(card,'Edit',()=>{editId=row.id;canonical.value=row.canonical;alias.value=row.alias;topic.value=row.topic;canonical.focus()},!caps.aliases);
   button(card,'Hapus alias',()=>commit([{op:'alias_remove',id:row.id}]),!caps.aliases);
  }
  button(aliases,'Terapkan memori ke analisis',()=>stage('correction'),!caps.correction);
  const coverage=section('Cakupan dan alasan kandidat dilewati','Jendela transkrip yang diperiksa dibedakan dari frame sampel. Jumlah clip tidak dipaksakan.');
  const report=data.discovery;
  if(report){coverage.append(node('p',`${report.processed_windows}/${report.windows} jendela utama · ${report.new_candidates} kandidat dalam analisis · revisi ${report.analysis_revision}`),node('p',report.objective));
   for(const [a,b] of report.coverage?.source_ranges||[])coverage.append(node('span',`${time(a)}–${time(b)} `));
   for(const r of report.rejections||[]){const details=node('details');details.append(node('summary',`${r.title||r.code}: ${r.code}`),node('p',r.detail));
    if(Number.isFinite(r.start)&&Number.isFinite(r.end)){button(details,'Dengar bagian ini',()=>onListen({...current,revision:expected,source_start:r.start,source_end:r.end}));button(details,'Tinjau batas',()=>onChange({...current,revision:expected,action:'review_rejected_candidate',candidate:r}))}coverage.append(details)}
  }else coverage.append(node('p','Belum ada laporan pencarian pada revisi ini. Data sesi lama tidak dihitung sebagai analisis baru.'));
  button(coverage,'Cari pembahasan tambahan',()=>stage('discovery'),!caps.discovery);
  const context=data.boundary_context;
  if(context)for(const [name,label] of [['before','Sekitar pembuka'],['after','Sekitar penutup']]){coverage.append(node('p',context[name].quote));button(coverage,label,()=>onListen({...current,revision:expected,source_start:context[name].start,source_end:context[name].end}))}
  button(coverage,'Periksa konteks dengan AI lokal',()=>stage('boundary_review'),!caps.discovery);
  const assets=section('Usulan ilustrasi','Tinjau ilustrasi sebelum digunakan. Ilustrasi yang sudah diunduh belum tentu dipakai dalam hasil video.');
  button(assets,'Siapkan ilustrasi',()=>stage('asset_proposals'),!caps.assets);
  for(const proposal of unpack(data.asset_proposals,'AssetProposalSet')?.proposals||[]){
   const card=node('article',undefined,'analysis-card');assets.append(card);card.append(node('h4',proposal.visual_intent),node('p',proposal.reason));
   const status=node('p',proposal.availability==='missing'?'Berkas hilang':'Pratinjau belum tersedia. Siapkan ilustrasi untuk memuatnya.');card.append(status);
   if(proposal.preview_url){const video=node('video');video.controls=true;video.muted=true;video.playsInline=true;video.preload='metadata';video.poster=proposal.poster_url||'';
    const retry=button(card,'Coba muat lagi',()=>{video.src=proposal.preview_url;video.load();status.textContent='Memuat ulang…'});retry.hidden=true;
    video.onloadedmetadata=()=>{status.textContent=`Aset ${Number.isFinite(proposal.duration)?proposal.duration.toFixed(1):'—'} dtk · usulan ${(proposal.source_end-proposal.source_start).toFixed(1)} dtk`;retry.hidden=true};
    video.onerror=()=>{status.textContent='Preview gagal dimuat. Coba lagi atau siapkan ulang aset.';retry.hidden=false};video.src=proposal.preview_url;card.append(video);status.textContent='Memuat preview…';
   }else if(proposal.poster_url){const image=node('img');image.src=proposal.poster_url;image.alt=proposal.visual_intent;card.append(image)}
   const metadata=proposal.metadata_status==='ready'?'Keterangan cocok':'Keterangan belum lengkap';const visualStatus=proposal.visual_status==='ready'?'Gambar sudah diperiksa':proposal.visual_status==='blocked'?'Gambar tidak cocok':'Gambar belum diverifikasi';const usage=proposal.usage_status==='not_scheduled'?'Belum dipasang':proposal.usage_status==='scheduled'?'Sudah dijadwalkan':'Status pemakaian perlu diperiksa';card.append(node('p',`${metadata} · ${visualStatus} · ${usage}`));
   const visual=proposal.visual_evidence||{};if(visual.reason)card.append(node('p',`${visual.reason} · ${visual.sample_count} sampel · ${visual.seconds}s${visual.cached?' · cache':''}`));
   if(proposal.visual_rank)card.append(node('p',`SigLIP2 · ${proposal.visual_rank.sample_count} sampel · skor relatif ${proposal.visual_rank.score}. Peringkat ini perlu pemeriksaan visual.`));
   card.append(node('p',proposal.rights?.attribution||'Asal/izin belum dilengkapi.'));
   const enabled=input(card,'Izinkan usulan ini',proposal.enabled,'checkbox');enabled.disabled=!caps.asset_changes;enabled.onchange=()=>commit([{op:'asset_enabled',proposal_id:proposal.proposal_id,enabled:enabled.checked}]).catch(e=>notice(e.message));
   if(proposal.editable_url){const a=node('a','Unduh SVG editable');a.href=proposal.editable_url;a.download='diagram.svg';card.append(a)}
   if(proposal.rights?.permission_status==='user_supplied'){
    const tags=input(card,'Tag lokal (Indonesia / Inggris)',proposal.tags||''),credit=input(card,'Asal / izin / kredit',proposal.rights?.attribution||'');
    button(card,'Simpan metadata',()=>commit([{op:'asset_metadata',asset_id:proposal.asset_id,tags:tags.value,attribution:credit.value}]),!caps.asset_changes);
   }
  }
  const preview=section('Ukuran ponsel','Periksa pratinjau dari perubahan terbaru. Kata kecil, waktu baca, wajah, dan materi perlu diperiksa pada ukuran ini.');
  const media=data.caption_preview;
  if(media?.url&&media.revision===expected){const video=node('video');video.className='analysis-phone';video.controls=true;video.src=media.url;video.playsInline=true;preview.append(video)}
  else preview.append(node('p','Preview revisi aktif belum tersedia.'));
  if(onPreview)button(preview,'Buat preview revisi aktif',()=>onPreview({...current,revision:expected}));
 }
 refresh();
 return {refresh,update(next){generation++;snapshot=null;content.replaceChildren();current={...next.target};expected=next.revision;return refresh()},
         getDrafts(){return Object.fromEntries(drafts)},destroy(){destroyed=true;generation++;root.replaceChildren();root.classList.remove('analysis-panel')}};
}
