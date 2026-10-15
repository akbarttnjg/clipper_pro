// Explicit M7 preflight before any export; no network publication on mount.
export function mountDelivery7(host,{project,api,onChange=()=>{},hasDrafts=()=>false}){
 const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
 const box=el('section');box.className='card';box.append(el('h2','M7 · Paket final dan proyek editor'));host.append(box);
 const note=el('p','Pilih isi paket, periksa kemampuan layer, lalu buat delivery. Final yang berubah perlu dirender ulang.');note.className='help';note.setAttribute('role','status');box.append(note);
 const controls=el('div');controls.className='fields';box.append(controls);const fields={};
 const select=(key,label,rows)=>{const l=el('label',label),n=el('select');n.setAttribute('aria-label',label);for(const [value,text]of rows){const o=el('option',text);o.value=value;n.append(o)}n.value=rows[0][0];l.append(n);controls.append(l);fields[key]=n;return n};
 const check=(key,label,value)=>{const l=el('label',label),n=el('input');l.className='check';n.type='checkbox';n.checked=value;n.setAttribute('aria-label',label);l.prepend(n);controls.append(l);fields[key]=n;return n};
 select('ratios','Rasio paket',[['both','9:16 + 16:9'],['portrait','9:16'],['landscape','16:9']]);
 const availableRatios=['portrait','landscape','square','feed','custom'].filter(v=>Object.values(project.clips||{}).some(c=>c.included!==false&&c.variants?.[v]));
 for(const v of availableRatios.filter(v=>!['portrait','landscape'].includes(v))){const o=el('option',({square:'1:1',feed:'4:5',custom:'Khusus M4'})[v]);o.value=v;fields.ratios.append(o)}
 if(availableRatios.length>2){const o=el('option','Semua rasio M4 yang tersedia');o.value='all';fields.ratios.append(o)}
 select('mode','Mode editor M7',[['hybrid','Hibrida · caption kandidat editable, master final aktif'],['native','Native dasar · hanya bila crop didukung'],['preserved','MP4 final · seluruh layer menyatu']]);
 select('profile','Profil MP4 delivery',[['reference','Salinan final yang direview'],['balanced','H.264 CPU · CRF 18'],['archive','H.264 CPU · CRF 16'],['compact','H.264 CPU · CRF 23']]);
 for(const [key,label]of [['capcut','CapCut 4.7.0'],['resolve','Resolve Free 18.6.6 · teks/font backlog'],['premiere','Premiere XML · video final'],['finalcut','Final Cut FCPXML · video final'],['otio','OTIO · video final']])check(key,label,true);
 for(const [key,label,value]of [['clean','Clean video tanpa caption',true],['alpha','Overlay caption alpha MOV (besar)',false],['stems','WAV master dan stem referensi',true],['merged','Gabungkan seluruh klip per rasio',true],['publish','Cover dan metadata publish kit',true]])check(key,label,value);
 const matrix=el('div');box.append(matrix);let preflight=null,epoch=0,disposed=false;const buttons=[];
 const choices=()=>({ratios:fields.ratios.value==='both'?['portrait','landscape']:fields.ratios.value==='all'?availableRatios:[fields.ratios.value],mode:fields.mode.value,profile:fields.profile.value,
  editors:['capcut','resolve','premiere','finalcut','otio'].filter(k=>fields[k].checked),clean:fields.clean.checked,alpha:fields.alpha.checked,stems:fields.stems.checked,merged:fields.merged.checked,publish:fields.publish.checked});
 const guard=()=>{if(hasDrafts())throw Error('Simpan atau buang draf sebelum membuat paket M7.');};
 const button=(text,action)=>{const n=el('button',text);n.type='button';box.append(n);buttons.push(n);n.onclick=async()=>{n.disabled=true;try{guard();await action()}catch(err){note.textContent=err.message}finally{n.disabled=false;if(n===create)n.disabled=!preflight?.ready}};return n};
 const inspect=button('Periksa paket dan kemampuan layer',async()=>{
  const generation=++epoch;const response=await api(`/projects/${project.project_id}/delivery7/preflight`,choices());if(disposed||generation!==epoch)return;preflight=response;matrix.replaceChildren();
  note.textContent=`${preflight.coverage} final · ${preflight.ready?'siap dipaketkan':'perlu diperbarui'}. Impor native belum diuji.`;
  for(const row of preflight.blockers||[])matrix.append(el('p',`${row.variant_id}: ${row.message}`));
  for(const row of preflight.capabilities||[]){const d=el('details');d.append(el('summary',`${row.clip_id} · ${row.variant_id}`));
   const table=el('table'),head=el('tr');for(const title of ['Editor / target','Layer','Status'])head.append(el('th',title));table.append(head);
   for(const cap of row.capabilities.filter(c=>choices().editors.includes(c.editor)))for(const [layer,status]of Object.entries(cap.layers)){
    const tr=el('tr');for(const text of [`${cap.editor} ${cap.target_version}`,layer,status])tr.append(el('td',text));table.append(tr)}d.append(table);matrix.append(d)}
  create.disabled=!preflight.ready;
 });
 const create=button('Buat paket M7',async()=>{
  if(!preflight?.ready)throw Error('Periksa paket dahulu.');
  await api(`/projects/${project.project_id}/jobs`,{kind:'delivery_m7',expected_revision:project.revision,options:choices()});
  note.textContent='Delivery M7 masuk antrean. Hasil tampil setelah seluruh pemeriksaan lulus.';await onChange();
 });create.disabled=true;
 for(const n of Object.values(fields))n.onchange=()=>{epoch++;if(n===fields.mode&&n.value==='preserved')for(const key of ['capcut','resolve','premiere','finalcut','otio'])fields[key].checked=false;preflight=null;create.disabled=true;note.textContent='Pilihan berubah. Periksa paket kembali.'};
 const packages=(project.exports||[]).filter(e=>e.version==='4.0.18-m7');
 for(const pkg of packages){const row=el('div');row.append(el('h3',`M7 · ${pkg.timelines} final · revisi ${pkg.input_revision}`));
  if(pkg.url){const a=el('a','Unduh paket M7');a.href=pkg.url;row.append(a)}
  const permission=el('select');permission.setAttribute('aria-label','Izin tautan review');for(const [value,label]of [['review','Review video'],['download','Review + unduh ZIP']]){const o=el('option',label);o.value=value;permission.append(o)}permission.value='review';row.append(permission);
  const expiry=el('input');expiry.type='number';expiry.min=15;expiry.max=10080;expiry.value=1440;expiry.setAttribute('aria-label','Masa berlaku review (menit)');row.append(expiry);
  const link=el('button','Buat tautan review lokal');link.type='button';link.onclick=async()=>{link.disabled=true;try{guard();const r=await api(`/projects/${project.project_id}/delivery7/reviews`,{
   expected_revision:project.revision,package_content_id:pkg.package_content_id,permission:permission.value,expires_minutes:Number(expiry.value)});
   const a=el('a','Buka review · berakhir '+new Date(r.expires*1000).toLocaleString('id-ID'));a.href=r.url+'/watch';a.target='_blank';a.rel='noopener noreferrer';row.append(a);
   const revoke=el('button','Cabut tautan ini');revoke.type='button';revoke.onclick=async()=>{try{await api(`/projects/${project.project_id}/delivery7/reviews/${r.id}/revoke`,{expected_revision:project.revision});a.remove();revoke.disabled=true;note.textContent='Tautan dicabut.'}catch(err){note.textContent=err.message}};row.append(revoke);
   note.textContent='Tautan mengikuti server lokal yang sedang berjalan; izin review membatasi endpoint, bukan penyalinan video.';
  }catch(err){note.textContent=err.message}finally{link.disabled=false}};row.append(link);box.append(row);
 }
 button('Kelola tautan review tersimpan',async()=>{const listing=await api(`/projects/${project.project_id}/delivery7/reviews`);if(disposed)return;for(const r of listing.reviews){const line=el('p',`${r.permission} · revisi ${r.input_revision} · berakhir ${new Date(r.expires*1000).toLocaleString('id-ID')} · ${r.revoked?'dicabut':r.expired?'kedaluwarsa':'aktif'}`);if(!r.revoked&&!r.expired){const revoke=el('button','Cabut '+r.id);revoke.type='button';revoke.onclick=async()=>{try{await api(`/projects/${project.project_id}/delivery7/reviews/${r.id}/revoke`,{expected_revision:project.revision});revoke.disabled=true;line.append(el('span',' · dicabut'))}catch(err){note.textContent=err.message}};line.append(revoke)}box.append(line)}});
 return {destroy(){disposed=true;epoch++;box.remove()}};
}
