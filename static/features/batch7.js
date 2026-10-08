// One project selection, two independently composed ratios, one export bundle.
export function mountBatch7(host,{project,api,onChange=()=>{},hasDrafts=()=>false}){
 const e=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
 const box=e('section');box.className='card';box.append(e('h2','Seluruh klip · dua rasio'));
 const note=e('p');note.className='help';note.setAttribute('role','status');box.append(note);host.append(box);
 const state=project.batch||{},clips=Object.entries(project.clips||{});
 note.textContent=`${state.selected_clips||0} klip dipilih · ${state.timelines||0} hasil 9:16 dan 16:9. Render final yang masih sesuai akan digunakan kembali.`;
 const guard=()=>{if(hasDrafts())throw Error('Simpan atau buang draf sebelum menjalankan seluruh klip.');};
 for(const [cid,clip] of clips){
  const l=e('label',clip.title),c=e('input');l.className='check';c.type='checkbox';c.checked=clip.included!==false;
  c.setAttribute('aria-label','Sertakan '+clip.title);l.prepend(c);box.append(l);
  c.onchange=async()=>{const desired=c.checked;c.disabled=true;try{guard();await api('/changes',{
   project_id:project.project_id,expected_revision:project.revision,operation_id:crypto.randomUUID(),
   operations:[{op:'include_clip',clip_id:cid,included:desired}]});await onChange();
  }catch(err){c.checked=!desired;note.textContent=err.message}finally{c.disabled=false}};
 }
 const modes=e('select');modes.setAttribute('aria-label','Mode paket seluruh klip');
 for(const [id,label] of [['hybrid','Hibrida · teks dan audio terpisah'],['preserved','Tampilan terjaga · MP4 final'],['native','Native dasar · bila seluruh crop didukung']]){
  const o=e('option',label);o.value=id;modes.append(o);
 }modes.value='hybrid';box.append(modes);
 const add=(label,action,disabled=false)=>{const b=e('button',label);b.type='button';b.disabled=disabled;box.append(b);
  b.onclick=async()=>{b.disabled=true;try{guard();await action();await onChange()}catch(err){note.textContent=err.message}finally{b.disabled=disabled}};return b};
 const preset=e('select');preset.setAttribute('aria-label','Preset seluruh pilihan');
 for(const [id,label] of [['adaptif','Adaptif'],['rapi','Rapi'],['ekspresif','Ekspresif']]){const o=e('option',label);o.value=id;preset.append(o)}preset.value='adaptif';box.append(preset);
 box.append(e('p','Preset seluruh pilihan memakai DM Sans + DM Serif, outline gelap, dan gerak terbatas. Diterapkan ke kedua rasio; koreksi ucapan tetap tersimpan.'));
 add('Terapkan preset pada seluruh pilihan',()=>api('/changes',{project_id:project.project_id,expected_revision:project.revision,
   operation_id:crypto.randomUUID(),operations:[{op:'preset_batch',preset:preset.value}]}),!state.selected_clips);
 add('Render seluruh pilihan · 9:16 + 16:9',async()=>{const r=await api(`/projects/${project.project_id}/batch-render`,{expected_revision:project.revision});
   note.textContent=`${r.jobs.length} proses dalam antrean, ${r.skipped.length} final digunakan kembali.`},!state.selected_clips);
 add('Buat satu paket seluruh pilihan',()=>api(`/projects/${project.project_id}/jobs`,{
   kind:'export_project',expected_revision:project.revision,options:{mode:modes.value}}),!state.ready);
 if(state.blockers?.length){box.append(e('p','Final yang perlu dibuat atau diperbarui:'));for(const r of state.blockers.slice(0,12))
  box.append(e('p',`${r.title} · ${r.variant_id==='portrait'?'9:16':'16:9'} · ${r.message}`));
  if(state.blockers.length>12)box.append(e('p',`Dan ${state.blockers.length-12} hasil lainnya.`));}
}
