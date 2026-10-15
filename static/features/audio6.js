import {localDrafts} from './draft_storage.js?v=4.0.17-m6';

// Exact string drafts remain owned by a tab until those strings are saved.
export async function mountAudio6(host,{project,clipId,variantId,api,onChange=()=>{},onDraftStatus=()=>{},isActive=()=>true}){
 let dead=false,corrupt=false,draft=null;const live=()=>!dead&&isActive();
 const key=`clipper-m6-fields|${project.project_id}|${clipId}|${variantId}`;
 const fields={},baseline={},status=document.createElement('p');status.setAttribute('role','status');
 const e=(tag,text)=>{const x=document.createElement(tag);if(text!==undefined)x.textContent=text;return x};
 const button=(parent,label,fn)=>{const x=e('button',label);x.type='button';x.onclick=async()=>{try{status.textContent='Memproses…';await fn();if(live()&&status.textContent==='Memproses…')status.textContent='Tersimpan / antrean siap.'}catch(error){if(live())status.textContent=error.message}};parent.append(x);return x};
 const section=(title,note)=>{const d=e('details');d.open=true;d.className='m6-group';d.append(e('summary',title));if(note)d.append(e('p',note));host.append(d);return d};
 const saveDraft=()=>{if(corrupt)return;const remaining={};for(const [k,f] of Object.entries(fields))if(f.read()!==baseline[k])remaining[k]=f.read();draft=Object.keys(remaining).length?{revision:draft?.revision??state.revision,fields:remaining}:null;if(draft)localDrafts.setItem(key,JSON.stringify(draft));else localDrafts.removeItem(key);onDraftStatus()};
 const request=ops=>({project_id:project.project_id,clip_id:clipId,variant_id:variantId,expected_revision:draft?.revision??state.revision,operation_id:crypto.randomUUID(),operations:ops});
 const consume=async(req,captured)=>{const result=await api('/changes',req);state.revision=result.revision??result.project?.revision??req.expected_revision+1;
  if('enabled' in captured)state.enabled=captured.enabled==='true';
  for(const [k,value] of Object.entries(captured))baseline[k]=value;
  let remaining={};if(live()){for(const [k,f] of Object.entries(fields))if(f.read()!==baseline[k])remaining[k]=f.read()}
  else{try{const saved=JSON.parse(localDrafts.getItem(key)||'null');if(saved?.fields){remaining={...saved.fields};for(const [k,value] of Object.entries(captured))if(remaining[k]===value)delete remaining[k]}}catch{return}}
  draft=Object.keys(remaining).length?{revision:state.revision,fields:remaining}:null;if(draft)localDrafts.setItem(key,JSON.stringify(draft));else localDrafts.removeItem(key);
  if(live()){onDraftStatus();await onChange()}
 };
 const state=await api(`/projects/${project.project_id}/audio6?`+new URLSearchParams({clip_id:clipId,variant_id:variantId}));
 if(!live())return {destroy(){dead=true},getDrafts(){return {}}};
 try{const raw=localDrafts.getItem(key);if(raw){draft=JSON.parse(raw);if(!draft||!Number.isInteger(draft.revision)||!draft.fields||Array.isArray(draft.fields)||Object.values(draft.fields).some(v=>typeof v!=='string'))throw Error('Format draf tidak valid')}}catch{corrupt=true;draft=null}
 host.replaceChildren();host.append(e('p',`M6 · Audio dan mix · revisi ${state.revision}. Setelan berlaku pada rasio aktif. Draf dan sumber asli tetap disimpan.`),status);
 if(corrupt)status.textContent='Draf rusak tetap disimpan. Unduh salinannya sebelum membuang atau memulihkannya.';
 const add=(parent,label,name,value,type='number',choices=null)=>{
  const labelNode=e('label',label);const input=e(choices?'select':type==='json'?'textarea':'input');
  if(!choices&&type!=='json')input.type=type==='boolean'?'checkbox':type;
  if(choices)for(const [v,t] of choices){const option=e('option',t);option.value=v;input.append(option)}
  input.setAttribute('aria-label',label);input.dataset.field=name;
  const serialize=v=>type==='boolean'?String(v):type==='json'?JSON.stringify(v,null,2):String(v);
  baseline[name]=serialize(value);const raw=draft?.fields?.[name]??baseline[name];if(type==='boolean')input.checked=raw==='true';else input.value=raw;
  fields[name]={node:input,type,read:()=>type==='boolean'?String(input.checked):input.value};input.oninput=()=>{saveDraft();toggle()};input.onchange=input.oninput;labelNode.append(input);parent.append(labelNode);return input;
 };
 let toggle=()=>{};
 const main=section('1 · Master dan normalisasi','Normalisasi diproses setelah semua track dan sensor digabung. Limiter memiliki sakelar tersendiri.');
 const enabled=add(main,'Aktifkan M6 pada rasio ini','enabled',state.enabled,'boolean');
 const normalize=add(main,'Normalisasi mix final','normalize',state.settings.normalize,'boolean');
 const target=add(main,'Target loudness (LUFS)','target_lufs',state.settings.target_lufs);
 const limiter=add(main,'Limiter puncak','limiter',state.settings.limiter,'boolean');
 const peak=add(main,'Batas true peak (dBTP)','peak_db',state.settings.peak_db);const targetNote=e('p');main.append(targetNote);
 add(main,'Gain suara sumber (dB)','source_gain_db',state.settings.source_gain_db);add(main,'Ekspor stem WAV','export_stems',state.settings.export_stems,'boolean');
 toggle=()=>{target.disabled=!normalize.checked;peak.disabled=!normalize.checked&&!limiter.checked;targetNote.textContent=normalize.checked?'Target LUFS dipakai pada mix final.':'Normalisasi nonaktif. Angka LUFS tersimpan untuk saat diaktifkan; angka itu tidak mengubah suara.'};toggle();
 const clean=section('2 · Bersihkan dan perbaiki suara','Bandingkan sebelum/sesudah. Noise reduction, enhancement dan pengurangan gema dapat memengaruhi ucapan pelan; penilaian dengar tetap diperlukan.');
 add(clean,'Denoise','denoise',state.settings.denoise,'text',[['off','Nonaktif'],['fft','FFT lokal'],['nlmeans','Non-local means lokal']]);add(clean,'Intensitas denoise (dB)','noise_reduction_db',state.settings.noise_reduction_db);
 add(clean,'Hum listrik','hum_hz',state.settings.hum_hz,'number',[['0','Nonaktif'],['50','50 Hz + harmonik'],['60','60 Hz + harmonik']]);
 add(clean,'Enhancement ucapan','enhancement',state.settings.enhancement,'boolean');add(clean,'Kurangi gema dengan WPE lokal','dereverb',state.settings.dereverb,'boolean');add(clean,'Intensitas pengurangan gema 0–1','dereverb_strength',state.settings.dereverb_strength);
 add(clean,'Band EQ (hz, gain_db, q)','eq_bands',state.settings.eq_bands,'json');
 add(clean,'Compressor ucapan','compressor',state.settings.compressor,'boolean');for(const [k,t] of [['compressor_threshold_db','Threshold compressor (dB)'],['compressor_ratio','Ratio compressor'],['compressor_attack_ms','Attack compressor (ms)'],['compressor_release_ms','Release compressor (ms)']])add(clean,t,k,state.settings[k]);
 add(clean,'Ubah pitch suara (semitone)','pitch_semitones',state.settings.pitch_semitones);
 const separation=section('3 · Pemisahan vokal dan musik','Pemisahan Demucs memerlukan runtime dan repo bobot lokal. Tidak ada unduhan model otomatis. Hasilnya estimasi, bukan rekaman ucapan asli yang sempurna.');
 add(separation,'Pemisahan stem','separation',state.settings.separation,'text',[['off','Nonaktif'],['demucs','Demucs lokal, CPU']]);add(separation,'Folder repo model lokal','model_directory',state.settings.model_directory,'text');add(separation,'Nama model lokal','model_name',state.settings.model_name,'text');add(separation,'Gain musik hasil pemisahan (dB)','separation_background_db',state.settings.separation_background_db);separation.append(e('p',state.model.status==='ready'?'Runtime dan bobot lokal terdeteksi; inference akan dicatat saat dijalankan.':state.model.reason));
 const music=section('4 · Musik, ducking dan SFX','Ducking mengikuti waktu ucapan efektif dan track narasi, termasuk kata pelan. SFX yang bertabrakan dengan angka/negasi memerlukan review.');
 add(music,'Ducking musik saat berbicara','ducking',state.settings.ducking,'boolean');for(const [k,t] of [['duck_db','Reduksi musik saat bicara (dB)'],['duck_attack_ms','Attack ducking (ms)'],['duck_release_ms','Release ducking (ms)']])add(music,t,k,state.settings[k]);add(music,'Aktifkan seluruh cue SFX','sfx_enabled',state.settings.sfx_enabled,'boolean');
 const trackHost=section('5 · Track tambahan','Musik, SFX, voiceover, reaction dan dubbing tetap terpisah dari transkrip sumber. Clock Output mengikuti hasil edit; clock Sumber mengikuti reverse/speed/reorder M1.');
 const cards=e('div');trackHost.append(cards);const numeric=new Set(['start','end','asset_start','gain_db','fade_in','fade_out','loop_crossfade','beat_bpm','beat_offset']);
 const rawRows=rows=>rows.map(row=>Object.fromEntries(Object.entries(row).map(([k,v])=>[k,numeric.has(k)?String(v):v])));
 const defaultRows=rawRows(state.tracks);baseline.tracks=JSON.stringify(defaultRows);let rows=defaultRows;
 try{if(draft?.fields?.tracks){rows=JSON.parse(draft.fields.tracks);if(!Array.isArray(rows)||rows.some(r=>!r||typeof r!=='object'))throw Error('Draf track rusak')}}catch{corrupt=true;status.textContent='Draf track rusak dipertahankan. Unduh salinan sebelum membuang.';rows=defaultRows}
 fields.tracks={type:'tracks',read:()=>JSON.stringify(rows)};
 function drawTracks(){cards.replaceChildren();for(const row of rows){const card=e('fieldset');card.append(e('legend',`${row.role} · ${row.id}`));
  const field=(key,label,type='text',options=null)=>{const wrap=e('label',label),node=e(options?'select':'input');if(options)for(const [v,t] of options){const option=e('option',t);option.value=v;node.append(option)}else node.type=type;
   node.setAttribute('aria-label',row.id+' · '+label);if(type==='checkbox')node.checked=!!row[key];else node.value=row[key]??'';
   node.oninput=()=>{row[key]=type==='checkbox'?node.checked:node.value;saveDraft()};node.onchange=node.oninput;wrap.append(node);card.append(wrap);return node};
  field('role','Peran','text',[['music','Musik'],['sfx','SFX'],['voiceover','Voiceover'],['reaction','Reaction'],['dubbing','Dubbing']]);field('asset_id','Aset lokal','text',[['','Pilih aset…'],...state.assets.map(a=>[a.id,`${a.name} · ${a.metadata.duration.toFixed(1)} dtk · ${a.permission}`])]);
  field('timebase','Clock','text',[['output','Output'],['source','Sumber']]);for(const [k,t] of [['start','Mulai (detik)'],['end','Selesai (detik)'],['asset_start','Mulai dalam aset (detik)'],['gain_db','Gain (dB)'],['fade_in','Fade masuk (detik)'],['fade_out','Fade keluar (detik)'],['loop_crossfade','Crossfade loop (detik)'],['beat_bpm','BPM (0 = tanpa beat)'],['beat_offset','Offset beat (detik)']])field(k,t,'number');
  for(const [k,t] of [['enabled','Track aktif'],['muted','Mute track'],['loop','Loop musik'],['beat_snap','Snap ke beat'],['reviewed','Cue/dubbing sudah saya tinjau'],['replace_source','Ganti suara sumber pada interval dubbing']])field(k,t,'checkbox');field('language','Bahasa dubbing');field('speaker_id','ID speaker dubbing');
  button(card,'Hapus track '+row.id,async()=>{rows=rows.filter(r=>r!==row);saveDraft();drawTracks()});cards.append(card)} }
 drawTracks();button(trackHost,'Tambah track',async()=>{rows.push({id:'track-'+crypto.randomUUID().slice(0,8),role:'music',asset_id:'',start:'0',end:String(Math.min(5,project.clips[clipId].end-project.clips[clipId].start)),asset_start:'0',gain_db:'-18',fade_in:'0.08',fade_out:'0.15',loop:false,loop_crossfade:'0.04',timebase:'output',beat_bpm:'0',beat_offset:'0',beat_snap:false,enabled:true,muted:false,language:'',speaker_id:'',reviewed:false,replace_source:false});saveDraft();drawTracks()});
 const library=section('6 · Aset musik dan audio lokal','Cari berdasarkan nama, mood/tag, koleksi dan metadata. Mesin tidak mencari atau mengunduh stock secara tersembunyi.');
 const plain=(label,type='text')=>{const wrap=e('label',label),input=e('input');input.type=type;input.setAttribute('aria-label',label);wrap.append(input);library.append(wrap);return input};
 const query=plain('Cari aset audio'),minDuration=plain('Durasi aset minimum (detik)','number'),maxDuration=plain('Durasi aset maksimum (detik)','number'),list=e('div');minDuration.value='0';maxDuration.value='86400';library.append(list);const showAssets=assets=>{list.replaceChildren();for(const a of assets){const row=e('p',`${a.name} · ${a.metadata.duration.toFixed(1)} detik · ${a.tags.join(', ')} · ${a.permission}`);if(a.url){const link=e('a','Dengar aset');link.href=a.url;link.target='_blank';row.append(link)}list.append(row)}};showAssets(state.assets);
 button(library,'Cari musik lokal',async()=>{if(!minDuration.value.trim()||!maxDuration.value.trim())throw Error('Isi rentang durasi aset');const result=await api('/audio6/assets?'+new URLSearchParams({q:query.value,min_seconds:minDuration.value,max_seconds:maxDuration.value}));if(live())showAssets(result.assets)});
 const assetPath=plain('Lokasi file audio'),assetName=plain('Nama aset'),origin=plain('Asal aset'),license=plain('Lisensi'),tags=plain('Mood/tag dipisahkan koma');const permission=e('select');permission.setAttribute('aria-label','Izin aset audio');for(const [v,t] of [['unknown','Belum ditinjau'],['user_owned','Milik sendiri'],['licensed','Berizin/lisensi']]){const option=e('option',t);option.value=v;permission.append(option)}library.append(permission);
 button(library,'Daftarkan aset audio',async()=>{await api('/audio6/assets',{path:assetPath.value,metadata:{name:assetName.value||'Audio lokal',origin:origin.value,license:license.value,permission:permission.value,tags:tags.value.split(',').map(x=>x.trim()).filter(Boolean)}});if(live())await onChange()});
 const cleanup=section('7 · Cleanup dan sambungan','Usulan tidak memotong apa pun sebelum ditinjau. Cleanup mengubah audio dan video bersama melalui timeline M1. Negasi/angka tidak dijadikan filler.');
 add(cleanup,'Microfade sambungan (ms)','smooth_ms',state.settings.smooth_ms);
 const selected=new Set();for(const p of state.cleanup.proposals||[]){const label=e('label',`${p.kind} · ${p.start.toFixed(2)}–${p.end.toFixed(2)} dtk sumber · ${p.reason}`),box=e('input');box.type='checkbox';box.setAttribute('aria-label','Pilih cleanup '+p.id);box.onchange=()=>box.checked?selected.add(p.id):selected.delete(p.id);label.append(box);cleanup.append(label)}
 const reviewed=e('input');reviewed.type='checkbox';reviewed.setAttribute('aria-label','Konteks cleanup sudah didengarkan');const approval=e('label','Saya sudah mendengar konteks dan menyetujui potongan terpilih');approval.append(reviewed);cleanup.append(approval);
 button(cleanup,'Terapkan cleanup yang ditinjau',async()=>{if(draft||corrupt)throw Error('Simpan/buang draf M6 dahulu');if(!reviewed.checked)throw Error('Dengarkan dan setujui konteks dahulu');await api('/changes',request([{op:'m6_cleanup',signature:state.cleanup.signature,proposal_ids:[...selected],reviewed:true}]));if(live())await onChange()});
 const review=section('8 · Dengar A/B, meter dan stem','Pemeriksaan teknis tidak menggantikan listening test ucapan asli. Hasil review lama tetap tersedia dan ditandai bila input berubah.');
 const queue=async seconds=>{if(draft||corrupt)throw Error('Simpan/buang draf M6 sebelum menjalankan audio');if(!state.enabled)throw Error('Aktifkan M6 dan simpan dahulu');await api(`/projects/${project.project_id}/jobs`,{kind:'audio_m6',clip_id:clipId,variant_id:variantId,expected_revision:state.revision,options:{seconds}});if(live())await onChange()};
 button(review,'Buat A/B 8 detik',()=>queue(8));button(review,'Buat audio lengkap dan stem',()=>queue(0));
 const result=state.review||{};if(result.master_url){review.append(e('p',result.stale?'Hasil A/B lama; input telah berubah.':'A/B sesuai snapshot tersimpan.'));const player=e('audio');player.controls=true;player.src=result.master_url;review.append(player);for(const [key,label] of [['before_url','Dengar sebelum'],['processed_url','Dengar sesudah cleanup'],['master_url','Dengar mix final']])if(result[key])button(review,label,async()=>{const t=player.currentTime||0;player.src=result[key];player.onloadedmetadata=()=>{player.currentTime=Math.min(t,Math.max(0,(player.duration||0)-.01));player.play?.().catch?.(()=>{})};player.load?.()});
  const meter=result.meter||{};review.append(e('p',`LUFS terukur: ${meter.integrated_lufs??'belum terukur'} · true peak: ${meter.true_peak_db??'belum terukur'} dBTP · clipping: ${meter.clipped_samples??'belum terukur'} · ${meter.status||''}`));for(const key of ['master_url','stem_archive_url','report_path_url'])if(result[key]){const link=e('a',key==='master_url'?'Unduh master WAV':key==='stem_archive_url'?'Unduh ZIP stem':'Unduh laporan audio');link.href=result[key];link.download='';review.append(link)} }
 if(state.final_audio?.meter_encoded){const m=state.final_audio.meter_encoded;review.append(e('p',`Audio MP4 ${state.final_audio.stale?'lama':'final'}: ${m.integrated_lufs??'belum terukur'} LUFS · ${m.true_peak_db??'belum terukur'} dBTP · sync ${m.sync?.status??'belum diukur'}`));if(state.final_audio.stem_archive_url){const link=e('a','Unduh stem dari render final');link.href=state.final_audio.stem_archive_url;review.append(link)}}
 const changes=()=>{if(corrupt)throw Error('Pulihkan/buang draf rusak dahulu');const captured={};for(const [k,f] of Object.entries(fields))if(f.read()!==baseline[k])captured[k]=f.read();const values={},ops=[];
  for(const [k,raw] of Object.entries(captured)){if(k==='enabled'||k==='tracks')continue;const type=fields[k].type;let value;if(type==='boolean')value=raw==='true';else if(type==='json')value=JSON.parse(raw);else if(type==='number'){if(!raw.trim()||!Number.isFinite(Number(raw)))throw Error('Angka belum lengkap: '+k);value=Number(raw)}else value=raw;if(k==='hum_hz')value=Number(raw);values[k]=value}
  if(Object.keys(values).length)ops.push({op:'m6_settings',values});if('tracks' in captured){const value=JSON.parse(captured.tracks).map(row=>Object.fromEntries(Object.entries(row).map(([k,v])=>{if(!numeric.has(k))return [k,v];if(String(v).trim()===''||!Number.isFinite(Number(v)))throw Error('Angka track belum lengkap: '+k);return [k,Number(v)]})));ops.push({op:'m6_tracks',values:value})}
  if('enabled' in captured)ops.push({op:'m6_enable',enabled:captured.enabled==='true'});return {captured,ops};
 };
 button(host,'Simpan perubahan M6',async()=>{const {captured,ops}=changes();if(!ops.length){status.textContent='Tidak ada perubahan';return}await consume(request(ops),captured)});
 button(host,'Lihat perubahan M6',async()=>{const {ops}=changes();if(!ops.length)throw Error('Tidak ada perubahan');const result=await api(`/projects/${project.project_id}/audio6/diff`,request(ops));if(live())status.textContent='Perubahan audio: '+JSON.stringify(result.effective_audio)});
 button(host,'Unduh salinan draf M6',async()=>{const a=e('a');a.href=URL.createObjectURL(new Blob([localDrafts.getItem(key)||'{}'],{type:'application/json'}));a.download='draf-M6.json';a.click();URL.revokeObjectURL(a.href)});
 button(host,'Muat revisi terbaru untuk draf M6',async()=>{const latest=await api(`/projects/${project.project_id}`);if(draft){draft.revision=latest.revision;localDrafts.setItem(key,JSON.stringify(draft))}if(live())status.textContent='Draf tetap ada; tinjau lalu simpan pada revisi terbaru.'});
 button(host,'Buang draf M6',async()=>{localDrafts.removeItem(key);draft=null;corrupt=false;if(live()){onDraftStatus();await onChange()}});
 return {getDrafts(){return draft?.fields||{}},destroy(){dead=true}};
}
