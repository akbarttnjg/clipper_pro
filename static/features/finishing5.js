import {localDrafts} from './draft_storage.js?v=4.0.17-m6';
// Each tab owns string drafts; only changed fields are submitted to the engine.
export async function mountFinishing5(host,{project,clipId,variantId,api,onChange=()=>{},isActive=()=>true,onDraftStatus=()=>{}}){
 let destroyed=false,preview=null,corrupt=false,draft=null;
 host.classList?.add('m5-panel');
 const key=`clipper-m5-fields|${project.project_id}|${clipId}|${variantId}`;
 const e=(tag,value)=>{const n=document.createElement(tag);if(value!==undefined)n.textContent=value;return n};
 const status=e('p');status.className='help';status.setAttribute('role','status');host.append(status);
 const live=()=>!destroyed&&isActive();
 const state=await api(`/projects/${project.project_id}/finishing5?`+new URLSearchParams({clip_id:clipId,variant_id:variantId}));
 if(!live())return {destroy(){},getDrafts(){return {}}};
 try{const raw=localDrafts.getItem(key);draft=raw?JSON.parse(raw):null;if(draft&&(!draft.fields||typeof draft.fields!=='object'||Array.isArray(draft.fields)))throw Error('Draf tidak valid')}catch{corrupt=true}
 const fields={},baseline=state.style;
 const button=(box,label,fn)=>{const n=e('button',label);n.type='button';n.onclick=async()=>{n.disabled=true;try{await fn()}catch(err){if(live())status.textContent=err.message}finally{if(live())n.disabled=false}};box.append(n);return n};
 const section=(label,help)=>{const box=e('details'),title=e('summary',label);box.append(title,e('p',help));host.append(box);return box};
 const saveDraft=()=>{if(corrupt){status.textContent='Draf rusak tetap disimpan. Unduh salinannya lalu buang draf sebelum mengedit.';return}
  const changed={};for(const [k,{node}] of Object.entries(fields)){if(node.value!==node.dataset.baseline)changed[k]=node.value}
  preview=null;draft=Object.keys(changed).length?{revision:draft?.revision??state.revision,fields:changed}:null;
  if(draft)localDrafts.setItem(key,JSON.stringify(draft));else localDrafts.removeItem(key);status.textContent=draft?'Draf belum disimpan.':'Semua kolom sesuai nilai tersimpan.';onDraftStatus();
 };
 const field=(box,label,k,type='text',options=null)=>{
  const l=e('label',label),n=e(options?'select':type==='json'?'textarea':'input');n.setAttribute('aria-label',label);n.dataset.settingKey=k;
  if(options)for(const [id,name] of options){const o=e('option',name);o.value=String(id);n.append(o)}
  else if(type!=='json')n.type=type==='boolean'?'text':type;
  const rawInitial=type==='json'?JSON.stringify(baseline[k]??null,null,2):String(baseline[k]??'');const initial=type==='color'?rawInitial.toLowerCase():rawInitial;n.dataset.baseline=initial;n.value=draft?.fields?.[k]??initial;n.oninput=saveDraft;n.onchange=saveDraft;
  fields[k]={node:n,type};const origin=e('small','Asal: '+(state.origins[k]||'inherited'));l.append(n,origin);box.append(l);
  button(l,'Reset '+label,async()=>{clean();await change([{op:'m5_reset',keys:[k]}]);});return n;
 };
 const values=()=>{const out={};for(const [k,{node,type}] of Object.entries(fields)){
  if(node.value===node.dataset.baseline)continue;
  if(type==='number'){if(node.value.trim()===''||!Number.isFinite(Number(node.value)))throw Error('Angka '+k+' belum valid');out[k]=Number(node.value)}
  else if(type==='boolean')out[k]=node.value==='true';else if(type==='json'){try{out[k]=JSON.parse(node.value)}catch{throw Error('Data '+k+' belum valid; draf tetap tersimpan')}}else out[k]=node.value;
 }return out};
 const clean=()=>{if(draft||corrupt)throw Error('Simpan atau buang draf M5 dahulu.')};
 const request=ops=>({project_id:project.project_id,clip_id:clipId,variant_id:variantId,expected_revision:state.revision,operation_id:crypto.randomUUID(),operations:ops});
 const change=async ops=>{await api('/changes',request(ops));if(live())await onChange()};
 const bool=(box,label,k)=>field(box,label,k,'boolean',[['false','Nonaktif'],['true','Aktif']]);
 const download=(name,value)=>{const a=e('a');const url=URL.createObjectURL(new Blob([value],{type:'application/json'}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
 host.append(e('p',state.enabled?'M5 aktif pada rasio ini.':'M5 belum aktif; pengaturan proyek sebelumnya tetap digunakan.'));
 button(host,state.enabled?'Nonaktifkan M5 pada rasio ini':'Aktifkan M5 pada rasio ini',async()=>{clean();await change([{op:'m5_enable',enabled:!state.enabled}])});
 const a=section('1 · Preset dan template','Tinjau font, warna, posisi, dan gerak sebelum menerapkan. Override manual tetap dipertahankan.');
 const preset=e('select');preset.setAttribute('aria-label','Preset M5');for(const p of state.presets){const o=e('option',p.name);o.value=p.id;preset.append(o)}a.append(preset);
 const replace=e('input');replace.type='checkbox';replace.setAttribute('aria-label','Ganti override manual');const replaceLabel=e('label','Ganti override manual yang terlihat pada diff');replaceLabel.append(replace);a.append(replaceLabel);const diff=e('div');a.append(diff);
 preset.onchange=()=>{preview=null;diff.replaceChildren()};replace.onchange=()=>{preview=null;diff.replaceChildren()};
 button(a,'Lihat perubahan preset',async()=>{clean();const op={op:'m5_preset',preset_id:preset.value,replace_manual:replace.checked};const result=await api(`/projects/${project.project_id}/finishing5/diff`,request([op]));if(!live())return;preview=op;diff.replaceChildren();
  for(const [k,v] of Object.entries(result.effective_style||{}))if(JSON.stringify(v)!==JSON.stringify(baseline[k]))diff.append(e('p',`${k}: ${JSON.stringify(baseline[k])} → ${JSON.stringify(v)}`));
  if(!diff.children.length)diff.append(e('p','Tidak ada nilai efektif yang berubah. Override manual tetap berlaku.'));
 });
 button(a,'Terapkan preset yang ditinjau',async()=>{clean();if(!preview)throw Error('Lihat perubahan preset dahulu');await change([preview])});
 field(a,'Kebijakan template','caption_template_policy','text',[['auto','Mengikuti peran kalimat'],['manual','Kunci pilihan template']]);
 field(a,'Template','template_id','text',[...state.templates.map(t=>[t.id,t.name]),['custom','Template buatan saya']]);
 field(a,'Renderer','caption_renderer','text',[['ass','ASS lokal'],['raster','Raster lokal · CPU'],['auto','Otomatis · ASS untuk M5'],['remotion','Remotion · belum terbukti untuk M5']]);
 const b=section('2 · Font utama, aksen, dan fallback','Pemeriksaan glyph memakai file font sebenarnya. Font impor memerlukan asal dan izin penggunaan.');
 const fonts=state.fonts.map(f=>[f.id,f.label]);field(b,'Font utama M5','font_main','text',fonts);field(b,'Font aksen M5','font_accent','text',fonts);field(b,'Font fallback (daftar ID)','fallback_fonts','json');bool(b,'Gunakan font aksen','accent_font');
 const c=section('3 · Warna dan paint','Satu warna yang diubah menyimpan satu override. Ukuran paint memakai referensi sisi pendek 1080 px.');
 for(const [k,l] of [['base_hex','Warna utama'],['accent_hex','Warna aksen'],['stroke_hex','Warna stroke'],['shadow_hex','Warna shadow'],['glow_hex','Warna glow']])field(c,l,k,'color');
 for(const [k,l] of [['stroke_px','Stroke'],['shadow_px','Shadow'],['glow_px','Glow']])field(c,l,k,'number');bool(c,'Lindungi kontras','caption_backdrop');
 const d=section('4 · Ruang, posisi, dan layar kecil','Area manual berupa persen output [x,y,lebar,tinggi]. Kosongkan dengan null untuk mengikuti posisi. Wajah dan materi tetap dilindungi.');
 field(d,'Posisi M5','caption_position','text',[['auto','Ruang kosong otomatis'],['left','Kiri'],['right','Kanan'],['bottom','Bawah']]);field(d,'Perataan M5','caption_align','text',[['auto','Mengikuti posisi'],['left','Kiri'],['center','Tengah'],['right','Kanan']]);
 field(d,'Area caption manual','manual_panel','json');field(d,'Skala caption','caption_scale','number');field(d,'Minimum glyph pada ponsel','minimum_glyph_px','number');field(d,'Lebar layar simulasi','display_width_px','number');
 const f=section('5 · Makna, timing, dan aksesibilitas','Negasi, angka, dan satuan tetap berada dalam frasa utuh. Dua bahasa dipilih melalui panel transkrip M2.');
 field(f,'Granularitas','granularity','text',[['phrase','Frasa'],['word','Kata / unit makna']]);bool(f,'Penekanan semantik','semantic_emphasis');bool(f,'Karaoke M5','karaoke');bool(f,'Emoji M5','emoji');field(f,'Peta keyword dan ikon','emoji_map','json');bool(f,'Warna speaker','speaker_color');bool(f,'Label speaker','speaker_labels');field(f,'Identitas speaker yang disetujui','speaker_styles','json');
 field(f,'Sensor kata','censor_mode','text',[['off','Nonaktif'],['mask','Mask teks'],['bleep_mask','Mask dan bleep audio']]);field(f,'Kamus sensor','censor_terms','json');bool(f,'Kamus sensor sudah saya tinjau','censor_approved');
 const g=section('6 · Gerak dan builder','Gerak dibatasi supaya hold kontinu dan ukuran glyph tetap terbaca. Builder tidak menjalankan kode.');
 field(g,'Intensitas gerak M5','motion_intensity','text',[['calm','Tenang'],['balanced','Seimbang'],['dynamic','Dinamis']]);field(g,'Budget gerak','motion_budget','number');field(g,'Seed M5','caption_seed','number');field(g,'Template builder','builder','json');g.append(e('p','Contoh builder: {"id":"saya","name":"Gaya saya","motion":"rise","accent_ratio":1.12,"max_rows":2,"line_gap":0.23,"roles":["narration"]}'));
 const h=section('7 · Subtitle bawaan sumber','Tandai area yang terlihat di output dan interval waktu sumber. Hindari, tutup, atau rekonstruksi membutuhkan area yang sudah ditinjau.');
 field(h,'Penanganan subtitle sumber','source_caption_mode','text',[['avoid','Hindari area'],['cover','Tutup area'],['reconstruct','Tutup lalu susun caption baru']]);field(h,'Area subtitle sumber yang disetujui','source_captions','json');
 if(state.source_caption_detection){h.append(e('p',state.source_caption_detection.reason||'Usulan dari sampel OCR M4 perlu diperiksa pada video.'));
  for(const proposal of state.source_caption_detection.proposals||[])h.append(e('p',`${proposal.start.toFixed(2)}–${proposal.end.toFixed(2)} detik sumber · area output ${proposal.rect.map(n=>n.toFixed(1)).join(', ')}% · ${proposal.observations} sampel · ${(proposal.texts||[]).join(' / ')} · belum disetujui`));
  if(state.source_caption_detection.proposals?.length)button(h,'Saya tinjau dan gunakan usulan area subtitle',async()=>{const rows=state.source_caption_detection.proposals.map(r=>({rect:r.rect,start:r.start,end:r.end,provenance:r.provenance,approved:true}));fields.source_captions.node.value=JSON.stringify(rows,null,2);saveDraft()});}
 const i=section('8 · Brand, aset, dan layer','Kit menyimpan versi, template policy, font, layer, kamus, asal/lisensi dan digest aset. Waktu layer memakai sumber asli.');
 const location=e('input');location.setAttribute('aria-label','Lokasi aset lokal');const name=e('input');name.setAttribute('aria-label','Nama aset');const license=e('input');license.setAttribute('aria-label','Lisensi dan asal aset');const permission=e('select');permission.setAttribute('aria-label','Izin penggunaan');for(const [id,label] of [['unknown','Belum diisi'],['user_owned','Milik saya'],['licensed','Memiliki lisensi']]){const o=e('option',label);o.value=id;permission.append(o)}
 for(const [label,input] of [['Lokasi font/gambar/video lokal',location],['Nama aset',name],['Lisensi dan asal',license],['Izin penggunaan',permission]]){const l=e('label',label);l.append(input);i.append(l)}
 button(i,'Import aset lokal',async()=>{clean();await api('/finishing5/assets',{path:location.value,metadata:{name:name.value||undefined,permission:permission.value,license:license.value,origin:license.value||'local import'}});if(live())await onChange()});
 const search=e('input');search.setAttribute('aria-label','Cari aset');const listing=e('div');i.append(search,listing);const showAssets=rows=>{listing.replaceChildren();for(const r of rows)listing.append(e('p',`${r.id} · ${r.name} · ${r.kind} · ${r.permission} · ${(r.tags||[]).join(', ')}`))};showAssets(state.assets);
 for(const asset of state.assets){if(asset.url){const link=e('a','Buka aset '+asset.name);link.href=asset.url;link.target='_blank';link.rel='noopener';i.append(link)}}
 for(const asset of state.assets)button(i,'Ubah izin / lisensi '+asset.name,async()=>{clean();await api('/finishing5/assets/metadata',{asset_id:asset.id,expected_revision:asset.metadata_revision||0,values:{permission:permission.value,license:license.value,origin:license.value||asset.origin}});if(live())await onChange()});
 button(i,'Cari di koleksi aset',async()=>{const r=await api('/finishing5/assets?'+new URLSearchParams({q:search.value}));if(live())showAssets(r.assets)});
 field(i,'Layer logo, kartu, diagram, B-roll','decorations','json');fields.decorations.node.dataset.baseline=JSON.stringify(state.decorations,null,2);fields.decorations.node.value=draft?.fields?.decorations??fields.decorations.node.dataset.baseline;
 i.append(e('p','Contoh layer: {"id":"logo1","kind":"logo","asset_id":"ID_ASET","start":0,"end":3,"rect":[5,5,12,12],"opacity":0.8,"anchor":"top_right","transition":"fade","transition_s":0.2}. Daftar layer memakai [ ... ].'));
 const kitName=e('input');kitName.setAttribute('aria-label','Nama kit baru');i.append(kitName);
 button(i,'Simpan gaya tersimpan sebagai kit',async()=>{clean();await api('/finishing5/kits',{name:kitName.value,style:state.style,layers:state.decorations});if(live())await onChange()});
 for(const kit of state.kits){const card=e('div');card.className='card';card.append(e('strong',`${kit.name} · revisi ${kit.revision}`));i.append(card);let reviewed=null;const scope=e('select');for(const [value,label] of [['variant','Rasio aktif'],['project','Seluruh rasio/klip yang dipilih']]){const option=e('option',label);option.value=value;scope.append(option)}scope.value='variant';scope.onchange=()=>{reviewed=null};card.append(scope);
  button(card,'Tinjau kit '+kit.name,async()=>{clean();reviewed={op:'m5_kit',kit_id:kit.id,kit_revision:kit.revision,include_layers:true,scope:scope.value};const result=await api(`/projects/${project.project_id}/finishing5/diff`,request([reviewed]));if(live()){card.append(e('pre',JSON.stringify(result.effective_style,null,2)));card.append(e('p',`Layer yang diterapkan: ${(kit.layers||[]).map(r=>r.kind+' '+r.id+' '+r.start+'–'+r.end+' detik').join('; ')||'tidak ada'}. Cakupan: ${scope.value}.`),e('pre',JSON.stringify({layers:kit.layers,license:kit.license,asset_digests:kit.asset_digests},null,2)))}});
  button(card,'Terapkan kit '+kit.name,async()=>{clean();if(!reviewed)throw Error('Tinjau kit dahulu');await change([reviewed])});
  button(card,'Unduh kit '+kit.name,async()=>{const result=await api('/finishing5/kits/export',{project_id:project.project_id,kit_id:kit.id});if(live()){const a=e('a');a.href=result.url;a.download=kit.name+'.zip';a.click()}});
  if(kit.glossary?.length)button(card,'Terapkan kamus '+kit.name+' ke sumber',async()=>{clean();const previous=project.settings?.glossary||'';const terms=kit.glossary.map(r=>`${r.preferred} = ${r.heard}`).join('\n');await change([{op:'settings',scope:'project',values:{glossary:[previous,terms].filter(Boolean).join('\n')}}])});
 }
 const pack=e('input');pack.setAttribute('aria-label','Lokasi ZIP kit');i.append(pack);button(i,'Import kit portable',async()=>{clean();await api('/finishing5/kits/import',{path:pack.value});if(live())await onChange()});
 const j=section('9 · Galeri video, cover, dan pemeriksaan','Galeri merender potongan video Anda dengan font dan renderer aktif. Cover memakai frame hasil rasio ini.');
 const job=async(kind,options={})=>{clean();await api(`/projects/${project.project_id}/jobs`,{kind,clip_id:clipId,variant_id:variantId,expected_revision:state.revision,options});if(live())await onChange()};
 button(j,'Buat galeri 6 template · 5 detik',()=>job('gallery_m5',{seconds:5}));
 for(const r of state.gallery.items||[]){const card=e('div');card.className='card';card.append(e('strong',r.template_id+(r.stale?' · perlu diperbarui':'')));if(r.url){const v=e('video');v.controls=true;v.preload='metadata';v.src=r.url;card.append(v)}j.append(card)}
 const time=e('input');time.type='number';time.value=String(state.cover?.options?.time??0);time.setAttribute('aria-label','Waktu frame cover');const title=e('input');title.setAttribute('aria-label','Teks cover');title.value=state.cover?.options?.text||'';j.append(e('label','Waktu pada hasil (detik)'),time,e('label','Teks cover opsional'),title);
 const coverRect=e('input');coverRect.value=JSON.stringify(state.cover?.options?.rect||[7,9,80,40]);coverRect.setAttribute('aria-label','Area desain cover');const coverColor=e('input');coverColor.type='color';coverColor.value=state.cover?.options?.color||'#FFFFFF';coverColor.setAttribute('aria-label','Warna teks cover');j.append(e('label','Area desain cover (persen)'),coverRect,e('label','Warna teks cover'),coverColor);
 button(j,'Buat cover dari frame hasil',()=>job('cover_m5',{time:Number(time.value),text:title.value,rect:JSON.parse(coverRect.value),color:coverColor.value}));
 if(state.cover?.url){const image=e('img');image.src=state.cover.url;image.alt='Cover klip rasio aktif';j.append(image);const link=e('a','Unduh cover');link.href=state.cover.url;link.download='cover.png';j.append(link)}
 button(j,'Periksa caption dan hold',()=>job('style_review'));
 const report=project.clips[clipId].variants[variantId].style_report;
 if(report){j.append(e('p',`${report.stale?'Laporan lama · ':''}${report.issue_count||0} catatan pengukuran. Penilaian estetika dan makna pada video asli tetap terpisah.`));
  if(report.raster_qc){const raster=report.raster_qc;j.append(e('p',`Sampel kontras final: ${raster.contrast_ratio==null?'belum terukur':raster.contrast_ratio.toFixed(2)+':1'} · ${raster.decoded_frames||0} frame · ${raster.status}. Ini pengukuran sampel paint; latar bergerak tetap perlu ditinjau.`));}
  for(const phrase of report.phrases||[])j.append(e('p',`${phrase.text} · ${phrase.characters_per_second??'?'} karakter/detik · hold ${Math.min(...(phrase.clear_time_metrics||[]).map(r=>r.longest_contiguous_clear)).toFixed(2)} detik`));}
 button(host,'Simpan perubahan M5',async()=>{if(corrupt)throw Error('Pulihkan/buang draf rusak dahulu');const changed=values();const ops=[];if('decorations' in changed){ops.push({op:'m5_layers',values:changed.decorations});delete changed.decorations}if(Object.keys(changed).length)ops.unshift({op:'m5_style',values:changed});if(!ops.length){status.textContent='Tidak ada perubahan';return}const captured=Object.fromEntries(Object.entries(fields).filter(([k,{node}])=>node.value!==node.dataset.baseline).map(([k,{node}])=>[k,node.value]));const req=request(ops);req.expected_revision=draft?.revision??state.revision;const result=await api('/changes',req);
  // Advance saved baselines, consuming only exact captured strings. Edits made
  // while the request was pending remain owned by this tab and revision.
  state.revision=result.revision??result.project?.revision??(req.expected_revision+1);
  for(const [k,value] of Object.entries(captured))fields[k].node.dataset.baseline=value;
  const remaining={};
  if(live()){for(const [k,{node}] of Object.entries(fields))if(node.value!==node.dataset.baseline)remaining[k]=node.value;}
  else {try{const stored=JSON.parse(localDrafts.getItem(key)||'null');if(stored){if(!stored.fields||typeof stored.fields!=='object'||Array.isArray(stored.fields))return;Object.assign(remaining,stored.fields);for(const [k,value] of Object.entries(captured))if(remaining[k]===value)delete remaining[k];}}catch{return}}
  draft=Object.keys(remaining).length?{revision:state.revision,fields:remaining}:null;
  if(draft)localDrafts.setItem(key,JSON.stringify(draft));else localDrafts.removeItem(key);
 if(live()){onDraftStatus();await onChange()}});
 button(host,'Unduh salinan draf M5',async()=>download('draf-M5.json',localDrafts.getItem(key)||'{}'));
 button(host,'Buang draf M5',async()=>{localDrafts.removeItem(key);draft=null;corrupt=false;if(live()){onDraftStatus();await onChange()}});
 button(host,'Muat revisi terbaru untuk draf M5',async()=>{if(corrupt)throw Error('Draf rusak perlu dipulihkan dahulu');const latest=await api(`/projects/${project.project_id}`);if(draft){draft.revision=latest.revision;localDrafts.setItem(key,JSON.stringify(draft))}if(live())status.textContent='Draf dipertahankan. Tinjau kembali nilainya sebelum menyimpan.'});
 status.textContent=corrupt?'Draf M5 tidak dapat dibaca; salinan aslinya tetap disimpan.':draft?'Draf M5 dipulihkan; belum diterapkan.':'Nilai yang ditampilkan adalah nilai efektif rasio ini.';
 return {destroy(){destroyed=true},getDrafts(){return draft||corrupt?{[key]:draft||{corrupt:true}}:{}}};
}
