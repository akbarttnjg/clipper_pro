// Workspace controls use saved revisions. Opening a panel performs read-only calls.
const LABELS6={talking_head:'Pembicara',chart:'Chart',board:'Papan',multispeaker:'Beberapa pembicara',graphics:'Sumber bergrafis'};
const STATUS6={not_tested:'Belum diuji',user_reported_passed:'Lolos menurut laporan pengguna',user_reported_issue:'Kendala dilaporkan pengguna',stale:'Bukti memakai berkas lama',evidence_missing:'Berkas bukti tidak tersedia'};
function e6(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e}
function p6(host,text){const p=e6('p',text);p.className='help';host.append(p);return p}
function select6(host,label,items,value){const l=e6('label',label),e=e6('select');e.setAttribute('aria-label',label);for(const [id,text] of items){const o=e6('option',text);o.value=id;e.append(o)}e.value=value??items[0]?.[0]??'';l.append(e);host.append(l);return e}
function input6(host,label,value='',type='text'){const l=e6('label',label),e=e6(type==='textarea'?'textarea':'input');if(type!=='textarea')e.type=type;e.setAttribute('aria-label',label);if(type==='checkbox')e.checked=!!value;else e.value=value;l.append(e);host.append(l);return e}
function button6(host,label,fn,status,alive){const b=e6('button',label);b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn()}catch(e){if(alive())status.textContent=e.message||String(e)}finally{if(alive())b.disabled=false}};host.append(b);return b}
function json6(host,value){const e=e6('pre',JSON.stringify(value,null,2));e.className='history-diff';host.append(e)}
const mb6=v=>v===null||v===undefined?'belum terukur':(v/1024**2).toFixed(1)+' MB';

export function mountSteps6(host,{project,onNavigate}){
 const row=e6('div');row.className='workspace6-steps';host.append(row);
 const stages=[['source','Sumber','Bahasa, track suara, dan kamus menentukan analisis.'],['story','Pilih klip','Dengarkan batas cerita; tinjau kandidat tertolak.'],['edit','Tata gaya','Simpan tiap rasio dan periksa keterbacaan sebelum render.'],['results','Periksa / ekspor','Tinjau final revisi aktif dan layer yang dapat diedit.']];
 for(const [id,label,help] of stages){const c=e6('section');c.append(e6('strong',label));p6(c,help);const b=e6('button','Buka '+label);b.type='button';b.disabled=!project&&id!=='source';b.onclick=()=>onNavigate(id);c.append(b);row.append(c)}
}

export async function mountBrand6(host,{project,clipId,variantId,api,onChange,hasDrafts=()=>false}){
 let disposed=false;const alive=()=>!disposed,status=p6(host,'Memuat brand kit…');
 const data=await api('/brand-kits');if(disposed)return {destroy(){},getDrafts(){return {}}};
 const variant=project.clips[clipId].variants[variantId],cfg=variant.effective_settings;
 status.textContent='Kit menyimpan font, warna, intensitas dan aturan layout. Kata, potongan, ilustrasi dan area manual tetap tersimpan.';
 const name=input6(host,'Nama brand kit','Gaya saya'),list=select6(host,'Brand kit tersimpan',data.kits.map(k=>[k.id,k.name+' · v'+k.revision]));
 const scope=select6(host,'Terapkan kit pada',[['variant','Klip dan rasio aktif'],['project','Semua klip dan kedua rasio']],'variant');
 const fields=['style_preset','font_main','font_accent','accent_hex','base_hex','caption_style','caption_position','caption_align','caption_scale','caption_backdrop','motion_intensity','layout','material_share','semantic_emphasis','safe_placement'];
 p6(host,`Gaya tersimpan: ${cfg.style_preset} · aksen ${cfg.accent_hex} · gerak ${cfg.motion_intensity}. Font ${cfg.font_main} / ${cfg.font_accent}.`);
 p6(host,'Pengaturan yang sudah Anda simpan manual dilindungi saat menerapkan kit. Simpan draf tata gaya sebelum memakai tombol ini.');
 const ready=()=>{if(hasDrafts())throw Error('Simpan atau buang draf aktif dahulu; kit memakai pengaturan yang sudah tersimpan.')};
 button6(host,'Simpan gaya aktif sebagai kit baru',async()=>{ready();const saved=await api('/brand-kits',{name:name.value,settings:Object.fromEntries(fields.filter(k=>cfg[k]!==undefined).map(k=>[k,cfg[k]]))});status.textContent='Kit '+saved.name+' tersimpan; belum diterapkan pada proyek.';const o=e6('option',saved.name+' · v'+saved.revision);o.value=saved.id;list.append(o);list.value=saved.id;data.kits.push(saved);apply.disabled=false},status,alive);
 const apply=button6(host,'Terapkan brand kit',async()=>{ready();const kit=data.kits.find(k=>k.id===list.value);if(!kit)throw Error('Simpan atau pilih kit dahulu.');await api('/changes',{project_id:project.project_id,clip_id:clipId,variant_id:variantId,expected_revision:project.revision,operation_id:crypto.randomUUID(),operations:[{op:'brand_apply',kit_id:kit.id,kit_revision:kit.revision,scope:scope.value}]});if(alive())await onChange()},status,alive);apply.disabled=!data.kits.length;
 list.onchange=()=>apply.disabled=!list.value;
 button6(host,'Simpan alternatif seed',async()=>{ready();await api('/changes',{project_id:project.project_id,clip_id:clipId,variant_id:variantId,expected_revision:project.revision,operation_id:crypto.randomUUID(),operations:[{op:'design_alternative'}]});if(alive())await onChange()},status,alive);
 p6(host,'Alternatif hanya mengganti variasi komposisi frasa. Buat preview klip ini untuk melihatnya; undo tersedia di Riwayat. Analisis sumber tidak dijalankan ulang.');
 return {destroy(){disposed=true},getDrafts(){return {}}};
}

export async function mountEvaluation6(host,{project,clipId,variantId,api,onChange}){
 let disposed=false;const alive=()=>!disposed,status=p6(host,'Memuat evaluasi dan bukti impor…'),pid=project.project_id;
 const [ws,artifacts,quality]=await Promise.all([api(`/projects/${pid}/workspace`),api(`/projects/${pid}/artifacts?`+new URLSearchParams({clip_id:clipId,variant_id:variantId})),api(`/projects/${pid}/quality`)]);
 if(disposed)return {destroy(){},getDrafts(){return {}}};
 status.textContent='Bandingkan sumber dan rentang cerita yang sama. SSIM/PSNR mengukur piksel; estetika, isi, dan audio dinilai melalui peninjauan.';
 const key=`clipper6-evaluation|${pid}|${clipId}|${variantId}`;let draft={};try{draft=JSON.parse(localStorage.getItem(key)||'{}')}catch{}
 const bind=(field,id)=>{if(id in draft){if(field.type==='checkbox')field.checked=draft[id];else field.value=draft[id]}const save=()=>{draft[id]=field.type==='checkbox'?field.checked:field.value;localStorage.setItem(key,JSON.stringify(draft))};field.oninput=save;field.onchange=save;return field};
 const clear=keys=>{for(const k of keys)delete draft[k];if(Object.keys(draft).length)localStorage.setItem(key,JSON.stringify(draft));else localStorage.removeItem(key)};
 const eligible=artifacts.filter(a=>a.data.evaluation_context);
 const options=eligible.map(a=>[a.id,`${a.kind} · revisi ${a.data.input_revision} · ${a.data.width}×${a.data.height}`]);
 const baseline=bind(select6(host,'Baseline tersimpan',options,options[1]?.[0]),'baseline'),candidate=bind(select6(host,'Variasi tersimpan',options,options[0]?.[0]),'candidate');
 const category=bind(select6(host,'Jenis sumber evaluasi',Object.entries(LABELS6),'talking_head'),'category');
 const compare=button6(host,'Ukur dua hasil tersimpan',async()=>{await api(`/projects/${pid}/jobs`,{kind:'evaluation',clip_id:clipId,variant_id:variantId,expected_revision:project.revision,options:{baseline_id:baseline.value,candidate_id:candidate.value,category:category.value}});if(alive())await onChange()},status,alive);compare.disabled=eligible.length<2;
 if(eligible.length<2)p6(host,'Buat dua preview atau final pada Tahap 6. Hasil Tahap 5 tetap dapat ditonton, tetapi belum mempunyai identitas pembanding yang lengkap.');
 const evaluations=ws.evaluations.filter(e=>e.context.variant_id===variantId),pick=bind(select6(host,'Perbandingan untuk dinilai',evaluations.map(e=>[e.id,`${LABELS6[e.category]} · SSIM ${e.ssim.toFixed(4)} · ${e.sampled_seconds}s`])),'evaluation');
 const choice=bind(select6(host,'Hasil peninjauan',[['tie','Setara / belum lebih baik'],['candidate','Variasi lebih baik'],['baseline','Baseline lebih baik']],'tie'),'choice'),note=bind(input6(host,'Alasan: keterbacaan, cerita, efek dan audio','','textarea'),'note');
 const quantities={};for(const [id,label] of [['manual_corrections','Jumlah koreksi manual'],['collisions','Benturan area penting'],['unique_stories','Cerita dengan isi berbeda']])quantities[id]=bind(input6(host,label,'','number'),id);
 p6(host,'Biarkan jumlah kosong jika belum diukur. Kandidat yang lebih banyak belum membuktikan cerita lebih beragam.');
 const feedback=button6(host,'Simpan penilaian manusia',async()=>{await api(`/projects/${pid}/feedback`,{evaluation_id:pick.value,choice:choice.value,note:note.value,...Object.fromEntries(Object.entries(quantities).map(([k,e])=>[k,e.value===''?null:Number(e.value)]))});clear(['evaluation','choice','note',...Object.keys(quantities)]);if(alive())await onChange()},status,alive);feedback.disabled=!evaluations.length;
 const wins=ws.feedback.filter(f=>f.choice==='candidate'),winner=select6(host,'Penilaian untuk preferensi baru',wins.map(f=>[f.id,f.note.slice(0,80)]));
 p6(host,'Preferensi baru hanya berlaku untuk proyek yang dibuat sesudahnya. Tombol ini memerlukan variasi yang Anda nilai lebih baik; kit atau eksperimen tidak mengubah default otomatis.');
 const promote=button6(host,'Gunakan variasi terpilih untuk proyek baru',async()=>{await api(`/projects/${pid}/preferences`,{feedback_id:winner.value,expected_revision:ws.preference.revision});if(alive())await onChange()},status,alive);promote.disabled=!wins.length;
 const evidence=e6('details');evidence.append(e6('summary','Bukti impor CapCut 9.5.0 / Resolve 21'));host.append(evidence);
 p6(evidence,'Buka paket, edit teks, simpan, render, dan bandingkan dengan Reference MP4. Centang langkah yang sudah dilakukan. Bukti dicatat sebagai laporan pengguna.');
 const table=e6('table'),head=e6('tr');for(const h of ['Editor','Rasio','Status'])head.append(e6('th',h));table.append(head);
 for(const r of ws.native_matrix){const tr=e6('tr');tr.append(e6('td',r.editor+' '+r.target_version),e6('td',r.variant_id==='portrait'?'9:16':'16:9'),e6('td',STATUS6[r.status]||r.status));table.append(tr)}evidence.append(table);
 const packages=(project.exports||[]).filter(p=>p.export_mode!=='preserved'&&p.package_content_id);
 const pack=bind(select6(evidence,'Paket yang diuji',packages.map(p=>[p.package_content_id,`${p.export_mode} · ${p.variant_id} · revisi ${p.input_revision}`])),'package'),editor=bind(select6(evidence,'Editor uji',[['capcut','CapCut'],['resolve','DaVinci Resolve']]),'editor');
 const version=bind(input6(evidence,'Versi editor','9.5.0'),'version'),render=bind(input6(evidence,'Lokasi MP4 render editor'),'render_path');
 const flags={};for(const [id,label] of [['opened','Paket berhasil dibuka'],['text_edited','Teks berhasil diedit'],['saved','Proyek berhasil disimpan'],['rendered','Render editor selesai'],['compared','Font, framing, efek dan audio dibandingkan']])flags[id]=bind(input6(evidence,label,false,'checkbox'),id);
 const nativeNote=bind(input6(evidence,'Catatan hasil impor','','textarea'),'native_note');
 const saveEvidence=button6(evidence,'Simpan bukti impor',async()=>{await api(`/projects/${pid}/native-evidence`,{package_content_id:pack.value,editor:editor.value,version:version.value,render_path:render.value,note:nativeNote.value,...Object.fromEntries(Object.entries(flags).map(([k,e])=>[k,e.checked]))});clear(['package','editor','version','render_path','native_note',...Object.keys(flags)]);if(alive())await onChange()},status,alive);saveEvidence.disabled=!packages.length;
 const resources=e6('details');resources.append(e6('summary','Cakupan evaluasi dan sumber daya'));host.append(resources);
 for(const c of quality.categories)p6(resources,`${LABELS6[c.category]}: ${c.comparisons} perbandingan · ${c.human_reviews} tinjauan manusia`);
 for(const j of quality.jobs.slice(0,10)){const r=j.resources;p6(resources,`${j.kind}: ${r?.wall_seconds??'—'} detik · RAM ${mb6(r?.peak_ram_bytes)} · VRAM ${mb6(r?.peak_vram_bytes)}`)}
 p6(resources,'RAM/VRAM adalah sampel, sehingga lonjakan singkat dapat terlewat. VRAM perangkat dapat dipakai aplikasi lain.');
 button6(resources,'Unduh manifest proyek',async()=>{const result=await api(`/projects/${pid}/manifest`);const a=e6('a','Unduh project-manifest.json');a.href=result.url;a.download='project-manifest.json';resources.append(a)},status,alive);
 button6(host,'Buang draf evaluasi',async()=>{clear(Object.keys(draft));status.textContent='Draf dibuang. Buka ulang panel untuk memuat nilai tersimpan.'},status,alive);
 return {destroy(){disposed=true},getDrafts(){return draft}};
}
