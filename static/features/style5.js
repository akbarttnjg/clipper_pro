// Variant-scoped typography controls with revision-aware persistent drafts.
export function mountStyle5(host,{project,clipId,variantId,api,onChange=()=>{},onListen=()=>{}}){
 const variant=project.clips[clipId].variants[variantId],cfg=variant.effective_settings||{};
 const key=`clipper5-style|${project.project_id}|${clipId}|${variantId}`;
 let draft=null,destroyed=false;try{draft=JSON.parse(localStorage.getItem(key)||'null')}catch{}
 const e=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
 const note=e('p');note.className='help';note.setAttribute('role','status');host.append(note);
 const btn=(label,fn)=>{const b=e('button',label);b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn()}catch(err){note.textContent=err.message}finally{b.disabled=false}};host.append(b);return b};
 const fields={};
 const storeDraft=()=>{draft={revision:draft?.revision??project.revision,values:values()};localStorage.setItem(key,JSON.stringify(draft));note.textContent='Draf gaya belum disimpan.'};
 const select=(label,key,options,fallback)=>{const l=e('label',label),s=e('select');s.setAttribute('aria-label',label);for(const [id,name] of options){const o=e('option',name);o.value=id;s.append(o)}s.value=draft?.values?.[key]??cfg[key]??fallback;s.onchange=storeDraft;fields[key]=s;l.append(s);host.append(l);return s};
 select('Preset tipografi','style_preset',[['legacy','Gaya manual sebelumnya'],['rapi','Rapi · tenang dan terukur'],['ekspresif','Ekspresif · hierarki dan variasi'],['adaptif','Adaptif · mengikuti materi']],'legacy');
 select('Pilihan template','caption_template_policy',[['auto','Variasi mengikuti preset'],['manual','Kunci gaya teks yang dipilih']],'auto');
 select('Komposisi frasa','caption_composition',[['auto','Otomatis · editorial, fokus, kutipan'],['editorial','Editorial bersih'],['focus','Frasa fokus besar'],['quote','Kutipan tenang']],'auto');
 select('Pendukung area teks','segmentation_enabled',[['true','MediaPipe bila sudah siap'],['false','Tanpa segmentasi tambahan']],'true');
 select('Selaraskan frasa klip','align_selected_clips',[['true','Otomatis bila model lokal siap'],['false','Gunakan timing tersimpan']],'true');
 const label=e('label','Seed desain'),seed=e('input');seed.type='number';seed.min='0';seed.max='2147483647';seed.value=draft?.values?.caption_seed??cfg.caption_seed??2026;seed.setAttribute('aria-label','Seed desain');fields.caption_seed=seed;seed.oninput=storeDraft;label.append(seed);host.append(label);
 select('Renderer subtitle','caption_renderer',[['ass','Subtitle lokal'],['auto','Remotion bila siap'],['remotion','Wajib Remotion lokal']],'ass');
 select('Ilustrasi penjelas','illustration_mode',[['off','Nonaktif'],['labels','Diagram perbandingan atau daftar dari ucapan']],'off');
 select('Peringkat aset visual','broll_ranker',[['off','Metadata dan pemeriksaan visual'],['auto','SigLIP2 bila siap'],['siglip2','Wajib SigLIP2 lokal']],'auto');
 select('Penekanan makna','semantic_emphasis',[['true','Makna, angka utuh, dan negasi'],['false','Tanpa warna penekanan']],'true');
 const values=()=>Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,k==='caption_seed'?Number(v.value):['semantic_emphasis','segmentation_enabled','align_selected_clips'].includes(k)?v.value==='true':v.value]));
 btn('Simpan gaya Tahap 5',async()=>{const selected=values();
    if(selected.style_preset!=='legacy'&&selected.style_preset!==cfg.style_preset)Object.assign(selected,{font_main:'dm_sans',font_accent:'dm_serif_italic',caption_backdrop:true,motion_intensity:selected.style_preset==='rapi'?'calm':'balanced'});
    await api('/changes',{project_id:project.project_id,clip_id:clipId,variant_id:variantId,
    expected_revision:draft?.revision??project.revision,operation_id:crypto.randomUUID(),operations:[{op:'settings',values:selected}]});
    localStorage.removeItem(key);draft=null;if(!destroyed)await onChange()});
 btn('Buang draf gaya',async()=>{localStorage.removeItem(key);draft=null;if(!destroyed)await onChange()});
 btn('Muat revisi terbaru untuk draf',async()=>{if(!draft)return;const latest=await api(`/projects/${project.project_id}`);
   draft.revision=latest.revision;localStorage.setItem(key,JSON.stringify(draft));note.textContent='Draf tetap tersedia. Periksa pilihan Anda, lalu Simpan gaya untuk menerapkannya ke revisi terbaru.'});
 btn('Periksa keterbacaan klip',async()=>{if(draft)throw Error('Simpan draf gaya sebelum memeriksa keterbacaan.');await api(`/projects/${project.project_id}/jobs`,
   {kind:'style_review',clip_id:clipId,variant_id:variantId,expected_revision:project.revision});if(!destroyed)await onChange()});
 host.append(e('p','Seed yang sama mempertahankan pilihan susunan saat preview diulang. Tiap rasio mengukur tata letaknya sendiri. Remotion dan SigLIP2 memerlukan komponen lokal yang telah diuji.'));
 const report=variant.style_report;
 if(report?.selected_alignment){const a=report.selected_alignment;host.append(e('p','Alignment klip: '+({aligned:'timing terukur diterapkan',unavailable:'model lokal belum siap',no_candidates:'tidak ada frasa yang memerlukan pengukuran',disabled:'nonaktif',failed:'gagal; timing tersimpan digunakan',not_applied:'hasil belum memenuhi pemeriksaan'}[a.status]||a.status)+'. '+(a.reason||'')))}
 if(report?.renderer){const engine=report.renderer.engine==='remotion'?'Remotion':'Subtitle lokal';host.append(e('p','Render terakhir: '+engine+'. '+(report.renderer.reason||'')))}
 if(report)for(const asset of report.explanations||[]){const card=e('div');card.className='card';card.append(e('strong',asset.quote));
   card.append(e('p',asset.renderer==='motion-canvas'?'Motion Canvas berhasil merender aset.':'Kartu kutipan lokal · Motion Canvas '+(asset.motion_canvas?.status||'belum siap')+'.'));
   if(asset.preview_url){const video=e('video');video.src=asset.preview_url;video.controls=true;video.preload='metadata';video.setAttribute('aria-label','Preview kartu kutipan');card.append(video)}host.append(card)}
 if(draft)note.textContent='Draf gaya dipulihkan; simpan untuk menerapkannya.';
 else if(report)note.textContent=`${report.issue_count||0} masalah keterbacaan${report.stale?' · laporan perlu diperbarui':''}.`;
 if(report)for(const p of report.phrases||[]){
  if(!p.issues?.length)continue;
  const item=e('div');item.className='card';item.append(e('strong',p.text));
  for(const issue of p.issues)item.append(e('p',issue.message+' '+issue.fix));
  if(p.source_start!==undefined){const b=e('button','Dengarkan frasa');b.type='button';b.onclick=()=>onListen(p.source_start);item.append(b)}host.append(item);
 }
 return {destroy(){destroyed=true},getDrafts(){return draft?{[key]:draft}:{} }};
}
