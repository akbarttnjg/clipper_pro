// M8 controls submit explicit commands. Mount/refresh only reads account/project state.
const node8=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
const labels8={draft:'Draf',queued:'Menunggu jadwal',uploading:'Mengunggah',processing:'Diproses platform',scheduled_remote:'Terjadwal di YouTube',published:'Selesai di platform',handoff_ready:'Paket unggah manual siap',stale:'Revisi berubah',needs_reconcile:'Perlu rekonsiliasi',paused:'Dijeda',failed:'Gagal',canceled:'Dibatalkan',cancel_requested:'Memeriksa pembatalan',remote_mismatch:'Hasil remote berbeda',remote_change:'Memperbarui metadata'};

export function mountM8(host,{project=null,api,onChange=async()=>{},hasDrafts=()=>false,isActive=()=>true,download=null}){
 const root=node8('section');root.className='card m8-panel';host.append(root);
 const title=node8('h2','M8 · Distribusi dan workspace'),note=node8('p','Memuat status…'),nav=node8('div'),body=node8('div');
 note.setAttribute('role','status');nav.className='m8-tabs';root.append(title,note,nav,body);
 let disposed=false,epoch=0,state=null,accounts=[],requests=[],workspace=null,tab='publish',currentDraft=null,proof=null;
 const values={account:'',target:'',title:'',description:'',tags:'',privacy:'private',local_time:'',timezone:'Asia/Jakarta',mode:'handoff',remote_schedule:false};
 const alive=()=>!disposed&&isActive();
 const guard=()=>{if(!alive())throw Error('Panel sudah ditutup.');if(hasDrafts())throw Error('Simpan draf edit proyek sebelum menjalankan M8.');};
 const command=async(action,args={},write=false)=>{
  if(write)guard();const id=globalThis.crypto.randomUUID();
  return api('/m8/v1/command',{schema_version:1,command_id:id,action,args});
 };
 const field=(box,label,value='',type='text')=>{const wrap=node8('label'),caption=node8('span',label),input=node8(type==='textarea'?'textarea':'input');
  if(type!=='textarea')input.type=type;input.setAttribute('aria-label',label);if(type==='checkbox')input.checked=Boolean(value);else input.value=value??'';wrap.append(caption,input);box.append(wrap);return input};
 const choose=(box,label,options,value)=>{const wrap=node8('label'),input=node8('select');input.setAttribute('aria-label',label);for(const [id,text]of options){const o=node8('option',text);o.value=id;input.append(o)}input.value=value??options[0]?.[0]??'';wrap.append(node8('span',label),input);box.append(wrap);return input};
 const button=(box,text,action)=>{const b=node8('button',text);b.type='button';box.append(b);b.onclick=async()=>{if(b.disabled)return;b.disabled=true;try{await action()}catch(err){if(alive())note.textContent=err.message}finally{if(alive())b.disabled=Boolean(b.m8Locked)}};return b};
 const lock=(button,disabled)=>{button.m8Locked=disabled;button.disabled=disabled;};
 const section=(heading,help)=>{const s=node8('section');s.className='m8-section';s.append(node8('h3',heading));if(help)s.append(node8('p',help));body.append(s);return s};
 const link=(box,text,url)=>{if(!url)return;const a=node8('a',text);a.href=url;a.rel='noopener noreferrer';if(download)a.onclick=async event=>{event.preventDefault();try{await download(url)}catch(err){note.textContent=err.message}};box.append(a)};
 const describe=(box,value)=>{const pre=node8('pre',typeof value==='string'?value:JSON.stringify(value,null,2));pre.className='m8-receipt';box.append(pre);return pre};
 const canPublish=()=>['owner','publisher'].includes(state?.role);
 const canManage=()=>state?.role==='owner';
 const invalid=()=>{epoch++;currentDraft=null;proof=null;note.textContent='Metadata berubah. Buat draf lalu periksa isinya sebelum menyetujui.';const approval=body.querySelector?.('[data-approval]');if(approval)lock(approval,true);};
 async function load(){const generation=++epoch;try{
  const result=await Promise.all([command('status'),command('account.list'),command('publish.list',project?{project_id:project.project_id}:{}),command('workspace.get')]);
  if(!alive()||generation!==epoch)return;[state,{accounts},{requests},workspace]=result;
  values.timezone=values.timezone||workspace.workspace.settings.timezone;
  note.textContent=`${workspace.workspace.name} · ${state.role} · worker ${state.worker.online?'aktif':'belum terlihat aktif'}. Jadwal lokal berjalan selama host dan worker aktif.`;
  nav.replaceChildren();for(const [key,text]of [['publish','Publikasi'],['accounts','Akun'],['analytics','Analytics'],['automation','Otomasi'],['team','Workspace & bantuan']])button(nav,text,async()=>{tab=key;draw()});
  draw();
 }catch(err){if(alive())note.textContent=err.message}}
 function draw(){if(!alive())return;body.replaceChildren();
  if(tab==='publish')renderPublish();if(tab==='accounts')renderAccounts();if(tab==='analytics')renderAnalytics();if(tab==='automation')renderAutomation();if(tab==='team')renderTeam();
 }
 function renderPublish(){
  const intro=section('Siapkan publikasi','Pilih satu final M7 dan akun. Draf → periksa isi → setujui. Handoff menghasilkan ZIP untuk diunggah manual.');
  button(intro,'Perbarui status M8',load);
  if(!project){intro.append(node8('p','Pilih proyek untuk menyiapkan publikasi.'));renderRequests();return}
  if(!canPublish()){intro.append(node8('p','Role ini dapat meninjau data. Persetujuan/publikasi memerlukan publisher atau owner.'));renderRequests();return}
  const targets=[];for(const pkg of project.exports||[])if(pkg.version==='4.0.18-m7')for(const row of pkg.coverage||[])targets.push({package:pkg,row,key:pkg.package_content_id+'|'+row.clip_id+'|'+row.variant_id});
  if(!targets.length||!accounts.length){intro.append(node8('p',!targets.length?'Buat paket M7 dari final aktif dahulu.':'Tambahkan profil tujuan pada tab Akun.'));renderRequests();return}
  const form=node8('div');form.className='m8-form';intro.append(form);
  if(!targets.some(t=>t.key===values.target))values.target=targets.at(-1).key;
  if(!accounts.some(a=>a.id===values.account))values.account=accounts[0].id;
  const target=choose(form,'Final M7',targets.map(t=>[t.key,`${t.row.title} · ${t.row.variant_id} · paket revisi ${t.package.input_revision}`]),values.target);
  const account=choose(form,'Akun tujuan',accounts.map(a=>[a.id,`${a.platform} · ${a.name} · ${a.connection}`]),values.account);
  const mode=choose(form,'Cara mengirim',[['handoff','Paket unggah manual'],['youtube','YouTube API setelah koneksi diperiksa']],values.mode);
  const title=field(form,'Judul publikasi',values.title||targets.find(t=>t.key===values.target).row.title);
  const description=field(form,'Deskripsi atau caption',values.description,'textarea'),tags=field(form,'Tag, pisahkan dengan koma',values.tags);
  const privacy=choose(form,'Privacy tujuan',[['private','Private'],['unlisted','Unlisted'],['public','Public']],values.privacy);
  const local=field(form,'Jadwal lokal (kosong = segera)',values.local_time,'datetime-local'),timezone=field(form,'Zona waktu jadwal',values.timezone);
  const remote=field(form,'Simpan jadwal di YouTube (tujuan public)',values.remote_schedule,'checkbox');
  for(const [key,input]of Object.entries({target,account,title,description,tags,privacy,local_time:local,timezone,mode,remote_schedule:remote})){
   const save=()=>{values[key]=input.type==='checkbox'?input.checked:input.value;invalid()};
   input.oninput=save;input.onchange=save;
  }
  const receipt=node8('div');intro.append(receipt);
  button(intro,'Buat draf publikasi',async()=>{
   guard();const t=targets.find(t=>t.key===target.value),a=accounts.find(a=>a.id===account.value);if(!t||!a)throw Error('Pilih final dan akun.');
   if(mode.value==='youtube'&&!a.capabilities.upload)throw Error('Akun ini belum mempunyai izin API unggah. Hubungkan YouTube atau pilih handoff.');
   const generation=++epoch;const row=await command('publish.draft',{project_id:project.project_id,expected_revision:project.revision,package_content_id:t.package.package_content_id,
    clip_id:t.row.clip_id,variant_id:t.row.variant_id,account_id:a.id,mode:mode.value,metadata:{title:title.value,description:description.value,tags:tags.value.split(',').map(t=>t.trim()).filter(Boolean),privacy:privacy.value},
    local_time:local.value||null,timezone:timezone.value,remote_schedule:remote.checked},true);
   if(!alive()||generation!==epoch)return;currentDraft=row;proof=null;receipt.replaceChildren();describe(receipt,row.request);lock(inspect,false);lock(approve,true);note.textContent='Draf tersimpan. Periksa akun, file, privacy, waktu dan metadata di receipt.';
  });
  const inspect=button(intro,'Periksa draf tersimpan',async()=>{guard();if(!currentDraft)throw Error('Buat draf dahulu.');const generation=++epoch;
   const result=await command('publish.preflight',{id:currentDraft.id});if(!alive()||generation!==epoch)return;proof=result;receipt.replaceChildren();describe(receipt,result.frozen);for(const t of [...result.blockers,...result.warnings])receipt.append(node8('p',t));lock(approve,!result.ready);note.textContent=result.ready?'Draf siap disetujui. Tinjau receipt sebelum menekan persetujuan.':'Draf diblokir. Perbaiki hal yang ditampilkan.';
  });lock(inspect,true);
  const approve=button(intro,'Setujui draf ini dan antrekan',async()=>{guard();if(!currentDraft||!proof?.ready)throw Error('Periksa draf dahulu.');
   const row=await command('publish.approve',{id:currentDraft.id,expected_version:currentDraft.version,approval_hash:proof.approval_hash},true);
   currentDraft=null;proof=null;lock(approve,true);lock(inspect,true);note.textContent='Persetujuan tersimpan. Antrean: '+row.id;await load();
  });approve.setAttribute('data-approval','true');lock(approve,true);
  renderRequests();
 }
 function renderRequests(){const box=section('Antrean dan hasil','Status remote serta privacy aktual ditampilkan terpisah dari jadwal lokal.');
  if(!requests.length)box.append(node8('p','Belum ada permintaan publikasi.'));
  for(const r of requests){const item=node8('details');item.append(node8('summary',`${r.request.metadata.title} · ${r.request.platform} · ${labels8[r.status]||r.status}`));
   item.append(node8('p',`${r.request.variant_id} · revisi ${r.request.project_revision} · ${r.request.schedule.local||'Segera'} · ${r.request.schedule.timezone}`));
   if(r.remote?.privacy)item.append(node8('p','Privacy aktual: '+r.remote.privacy));if(r.remote?.id)link(item,'Buka video remote',r.remote.url);
   if(r.remote?.handoff_url)link(item,'Unduh paket unggah manual',r.remote.handoff_url.replace('/api/studio/files/','/api/studio/m8/v1/files/'));
   describe(item,{metadata:r.request.metadata,output_content_id:r.request.output_content_id,approval:r.approval,progress:r.progress,remote:r.remote});
   if(canPublish()){
    if(r.status==='draft')button(item,'Tinjau untuk persetujuan',async()=>{guard();const result=await command('publish.preflight',{id:r.id});if(!alive())return;const preview=node8('div');describe(preview,result.frozen);for(const reason of result.blockers)preview.append(node8('p',reason));item.append(preview);
     if(result.ready)button(preview,'Setujui isi yang ditampilkan',async()=>{await command('publish.approve',{id:r.id,expected_version:r.version,approval_hash:result.approval_hash},true);await load()});
    });
    if(['paused','needs_reconcile','failed'].includes(r.status))button(item,'Rekonsiliasi lalu lanjutkan',async()=>{await command('publish.retry',{id:r.id,expected_version:r.version},true);await load()});
    if(['draft','queued','stale','paused'].includes(r.status))button(item,'Batalkan antrean lokal',async()=>{const response=await command('publish.cancel',{id:r.id,expected_version:r.version},true);note.textContent=response.message||'Pembatalan tersimpan.';await load()});
    if(r.remote?.id){const label=field(item,'Saya ingin menjadikan video remote private dan membatalkan jadwalnya',false,'checkbox');button(item,'Ajukan pembatalan remote',async()=>{if(!label.checked)throw Error('Pilih pembatalan remote secara eksplisit.');await command('publish.cancel',{id:r.id,expected_version:r.version,remote_to_private:true},true);await load()})}
    if(r.status==='handoff_ready'){const id=field(item,'ID posting manual'),url=field(item,'URL posting manual'),privacy=choose(item,'Privacy posting manual',[['private','Private'],['unlisted','Unlisted'],['public','Public']],'private');
     button(item,'Catat hasil unggahan manual',async()=>{await command('publish.manual_receipt',{id:r.id,expected_version:r.version,remote_id:id.value,remote_url:url.value,privacy:privacy.value},true);await load()});}
   }
   box.append(item);
  }
 }
 function renderAccounts(){const box=section('Profil akun dan koneksi','YouTube API memakai OAuth Desktop milik Anda. TikTok, Instagram, Facebook, LinkedIn dan X tersedia melalui paket handoff.');
  for(const account of accounts){const row=node8('details');row.append(node8('summary',`${account.name} · ${account.platform} · ${account.enabled?'aktif':'nonaktif'} · ${account.connection}`));describe(row,account);
   if(canManage()){button(row,'Periksa koneksi akun',async()=>{const value=await command('account.probe',{id:account.id},true);note.textContent=value.ready?'Channel terverifikasi.':'Profil menggunakan handoff.'});button(row,'Putuskan koneksi akun',async()=>{await command('account.disconnect',{id:account.id,expected_version:account.version},true);await load()})}box.append(row)}
  if(!canManage())return;
  const manual=section('Tambahkan profil untuk unggah manual');const platform=choose(manual,'Platform profil',[['tiktok','TikTok'],['instagram','Instagram'],['facebook','Facebook'],['youtube','YouTube manual'],['linkedin','LinkedIn'],['x','X'],['other','Lainnya']],'tiktok'),name=field(manual,'Nama profil tujuan');
  button(manual,'Simpan profil handoff',async()=>{await command('account.save',{platform:platform.value,name:name.value},true);await load()});
  const google=section('Hubungkan YouTube','Siapkan OAuth client bertipe Desktop, aktifkan YouTube Data API dan Analytics API. Proses membuka halaman persetujuan Google; tidak langsung mengunggah video.');
  const client=field(google,'Google Desktop client ID'),secret=field(google,'Google Desktop client secret','','password'),profile=field(google,'Nama profil YouTube'),manage=field(google,'Minta izin mengubah metadata dan membatalkan jadwal remote',false,'checkbox');
  button(google,'Mulai koneksi Google',async()=>{guard();const value=await api('/m8/v1/oauth/start',{client_id:client.value,client_secret:secret.value,name:profile.value,manage_remote:manage.checked});secret.value='';if(!alive())return;
   const anchor=node8('a','Buka persetujuan Google');anchor.href=value.url;anchor.target='_blank';anchor.rel='noopener noreferrer';google.append(anchor);
   button(google,'Periksa hasil koneksi Google',async()=>{const result=await api('/m8/v1/oauth/'+value.id);note.textContent=result.status==='connected'?'Akun tersambung. Tekan Perbarui status untuk menampilkannya.':result.error||result.status;if(result.status==='connected')await load()});
  });
  google.append(node8('p',state.vault.ready?'Vault siap: '+state.vault.backend:'Vault belum dikonfigurasi pada host ini. Windows menggunakan DPAPI; panduan menjelaskan host lain.'));
 }
 function renderAnalytics(){const box=section('Analytics berdasarkan revisi','Data yang belum tersedia ditampilkan sebagai kosong. Uji A/B dan observasi beda audience/jadwal dicatat terpisah.');
  const dates=node8('div');dates.className='m8-form';box.append(dates);const start=field(dates,'Awal periode','','date'),end=field(dates,'Akhir periode','','date');
  for(const r of requests)if(r.remote?.id&&canPublish())button(box,'Ambil metrik: '+r.request.metadata.title,async()=>{await command('analytics.refresh',{publish_id:r.id,start_date:start.value,end_date:end.value},true);await renderData()});
  const report=node8('div');box.append(report);
  async function renderData(){const result=await command('analytics.get',project?{project_id:project.project_id}:{});if(!alive()||tab!=='analytics')return;report.replaceChildren();
   const table=node8('table'),head=node8('tr');for(const title of ['Post','Metrik','Nilai','Periode','Sumber / ketersediaan'])head.append(node8('th',title));table.append(head);
   for(const row of result.rows){const tr=node8('tr');for(const value of [row.publish_id,row.metric,row.value===null?'Belum tersedia':row.value,row.start_date+' – '+row.end_date,row.value===null?row.reason:row.source])tr.append(node8('td',String(value)));table.append(tr)}report.append(table);
   report.append(node8('p',result.rows.length?'Periode tetap terpisah; rata-rata per post hanya memakai data yang tersedia.':'Belum ada data platform atau impor metrik.'));report.append(node8('p','Prediksi drop-off: belum dikalibrasi.'));
  }
  button(box,'Tampilkan metrik tersimpan',renderData);
  button(box,'Ekspor laporan JSON dan CSV',async()=>{const value=await command('analytics.export',project?{project_id:project.project_id}:{},true);if(!alive())return;link(box,'Unduh JSON',value.json);link(box,'Unduh CSV',value.csv)});
  const imported=section('Impor pengukuran sendiri','Isi JSON dari laporan platform. Asal dicatat sebagai impor operator, terpisah dari data API.');
  const sample={publish_id:requests[0]?.id||'',start_date:'2026-10-01',end_date:'2026-10-02',values:{views:null,likes:null},provenance:'Nama file atau laporan platform'};
  const input=field(imported,'JSON metrik',JSON.stringify(sample,null,2),'textarea');button(imported,'Simpan metrik impor',async()=>{await command('analytics.observe',JSON.parse(input.value),true);await renderData()});
  if(project&&['owner','reviewer','publisher'].includes(state.role)){const comments=section('Komentar pada waktu sumber'),at=field(comments,'Detik pada sumber',0,'number'),text=field(comments,'Isi komentar','','textarea');button(comments,'Simpan komentar revisi ini',async()=>{await command('comment.save',{project_id:project.project_id,expected_revision:project.revision,source_time:Number(at.value),text:text.value},true);note.textContent='Komentar tersimpan dengan identitas sumber dan revisi.'})}
 }
 function renderAutomation(){const box=section('Workflow lokal','Alur analisis → seleksi → render → paket M7 memakai guard inti dan antrean GPU yang sama. Publikasi tetap menunggu persetujuan per file.');
  if(canManage()){const name=field(box,'Nama workflow'),folder=field(box,'Folder lokal yang dipantau (opsional)'),enabled=field(box,'Aktifkan pemantauan folder ini',false,'checkbox');
   button(box,'Simpan workflow',async()=>{await command('workflow.save',{name:name.value,folder:folder.value||null,enabled:enabled.checked},true);await listWorkflows()});}
  const listing=node8('div');box.append(listing);
  async function listWorkflows(){const result=await command('record.list',{kind:'workflow'});if(!alive()||tab!=='automation')return;listing.replaceChildren();
   for(const item of result.records){const row=node8('details');row.append(node8('summary',item.data.name+' · '+(item.data.enabled?'pemantauan aktif':'manual')));describe(row,item.data);
    if(project&&['owner','editor'].includes(state.role))button(row,'Jalankan pada proyek aktif',async()=>{await command('workflow.run',{workflow_id:item.id,project_id:project.project_id,expected_revision:project.revision},true);note.textContent='Workflow masuk antrean. Pemeriksaan mutu dan persetujuan tetap berlaku.'});listing.append(row)}
  }
  button(box,'Tampilkan workflow',listWorkflows);
  button(box,'Tampilkan proses workflow',async()=>{const result=await command('record.list',{kind:'automation_run',...(project?{project_id:project.project_id}:{})});if(alive())describe(listing,result.records)});
  if(canManage()){const webhook=section('Webhook dan CMS','Tujuan HTTPS harus ada di allowlist operator. Event ditandatangani, memiliki ID tetap, dan dapat terkirim ulang.');
   const url=field(webhook,'URL webhook HTTPS'),events=field(webhook,'Jenis event, pisahkan dengan koma','publish.published,publish.handoff_ready');
   button(webhook,'Simpan tujuan webhook',async()=>{const value=await command('webhook.save',{url:url.value,events:events.value.split(',').map(v=>v.trim()).filter(Boolean)},true);describe(webhook,value);button(webhook,'Buat kunci verifikasi webhook',async()=>{const key=await api('/m8/v1/webhooks/'+value.id+'/signing-key',{});if(alive())describe(webhook,key)})});
  }
 }
 function renderTeam(){const box=section('Workspace dan batas harian','Mode pribadi tetap dapat dipakai tanpa login. Sesi anggota hanya berlaku pada API M8 dengan scope workspace. SSO dan cloud sync belum dikonfigurasi.');describe(box,workspace);
  if(canManage()){
   const quota=node8('div');quota.className='m8-form';box.append(quota);const jobs=field(quota,'Batas job per hari',workspace.workspace.settings.daily_jobs,'number'),publish=field(quota,'Batas publikasi per hari',workspace.workspace.settings.daily_publish,'number');
   button(box,'Simpan batas harian',async()=>{await command('workspace.configure',{expected_version:workspace.workspace.version,daily_jobs:Number(jobs.value),daily_publish:Number(publish.value)},true);await load()});
   const members=section('Sesi anggota','Token ditampilkan sekali pada hasil pembuatan. Bagikan sendiri melalui jalur yang Anda pilih.');const user=field(members,'Identitas anggota'),role=choose(members,'Role anggota',[['reviewer','Reviewer'],['editor','Editor'],['publisher','Publisher'],['owner','Owner']],'reviewer'),hours=field(members,'Masa sesi (jam)',24,'number');
   button(members,'Buat sesi anggota',async()=>{guard();const value=await api('/m8/v1/sessions',{user_id:user.value,role:role.value,hours:Number(hours.value)});if(alive())describe(members,value)});
   for(const session of workspace.sessions||[])if(!session.revoked)button(members,'Cabut sesi '+session.user_id+' · '+session.id.slice(-6),async()=>{await command('session.revoke',{id:session.id},true);await load()});
   if(project){const backup=section('Backup proyek','Backup menyertakan snapshot, riwayat, transkrip dan bahan yang dirujuk. Pemulihan membuat proyek baru dalam workspace Anda; antrean publish dan credential tidak diputar ulang.');
    const source=field(backup,'Sertakan sumber video/audio',true,'checkbox');button(backup,'Buat backup revisi aktif',async()=>{const value=await command('backup.create',{project_id:project.project_id,expected_revision:project.revision,include_source:source.checked},true);if(alive())link(backup,'Unduh backup proyek',value.url)});
    const path=field(backup,'Path backup lokal untuk dipulihkan');button(backup,'Pulihkan sebagai proyek baru',async()=>{const value=await command('backup.restore',{path:path.value},true);describe(backup,value);await onChange()});
   }
  }
  const help=section('Bantuan dan diagnosis','Buat paket diagnosis untuk ditinjau sebelum Anda membagikannya. Isi tidak dikirim otomatis.');button(help,'Buat diagnosis tanpa media dan credential',async()=>{const value=await command('diagnostics.create',project?{project_id:project.project_id}:{},true);if(alive()){describe(help,value.preview);link(help,'Unduh diagnosis',value.url)}});
  button(help,'Tampilkan cakupan dan pekerjaan tertunda M8',async()=>{const value=await command('capabilities');if(alive())describe(help,value)});
  link(help,'Buka konsol API/workspace M8','/m8');
 }
 const ready=load();
 return {ready,destroy(){disposed=true;epoch++;root.remove();},refresh:load};
}
