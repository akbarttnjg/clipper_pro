// Component administration lives alongside the creative workflow; drafts stay in place.
const labels={queued:'Antre',running:'Berjalan',cancel_requested:'Membatalkan',completed:'Selesai',failed:'Gagal',interrupted:'Terhenti',canceled:'Dibatalkan'};
const size=n=>n==null?'belum diukur':(n/1024**3).toFixed(1)+' GB';
function el(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node}

export async function mountRuntime(dialog,api,toast,sourcePath=''){
  dialog.replaceChildren();dialog.classList.add('runtime-dialog');
  const head=el('div',undefined,'runtime-head row spread');head.append(el('h2','Komponen & perangkat'));
  const headActions=el('div',undefined,'row'),content=el('div',undefined,'runtime-content');head.append(headActions);dialog.append(head,content);
  const close=el('button','Tutup');close.type='button';close.onclick=()=>dialog.close();
  content.append(el('p','Pasang komponen yang dibutuhkan secara bertahap. Versi dan bobot dikunci per lingkungan; data proyek tetap tersedia.','help'));
  const controls=el('div',undefined,'row'),summary=el('p',undefined,'help'),body=el('div'),jobs=el('section',undefined,'card runtime-queue');
  const pathLabel=el('label','Sumber untuk uji audio / video'),path=el('input');path.value=sourcePath||'';path.placeholder='Path video lokal, contoh C:\\Video\\sumber.mp4';pathLabel.append(path);
  const modelLabel=el('label','Bobot faster-whisper'),model=el('select');for(const id of ['small','medium']){const option=el('option',id);option.value=id;model.append(option)}modelLabel.append(model);
  const deviceLabel=el('label','Perangkat uji'),device=el('select');for(const [id,text] of [['cpu','CPU (awal)'],['cuda','CUDA (ukur & fallback CPU)']]){const option=el('option',text);option.value=id;device.append(option)}deviceLabel.append(device);
  controls.append(pathLabel,modelLabel,deviceLabel);content.append(controls,summary,jobs,body);
  let closed=false,polling=false,timer=null,lastSignature='',lastData=null,selectedLog=null,logRequest=0;
  const jobNodes=new Map();
  function button(parent,text,fn){const b=el('button',text);b.type='button';b.onclick=async()=>{if(b.disabled)return;b.dataset.busy='1';b.disabled=true;try{await fn();await refresh(true)}catch(e){toast(e.message,true)}finally{delete b.dataset.busy;b.disabled=false;if(lastData)syncActions(lastData)}};parent.append(b);return b}
  button(headActions,'Ke antrean',()=>{jobs.scrollIntoView({block:'start'});jobList.focus({preventScroll:true})});
  const cancelActive=button(headActions,'Batalkan proses aktif',async()=>{
    const active=lastData?.jobs.find(job=>job.status==='running');
    if(active){await api('/runtime/jobs/'+active.id+'/cancel',{});toast('Pembatalan proses diminta; unduhan parsial dipertahankan')}
  });cancelActive.classList.add('danger');cancelActive.disabled=true;
  const cancelQueued=button(headActions,'Batalkan antrean menunggu',async()=>{const result=await api('/runtime/jobs/cancel-queued',{});toast(result.canceled+' pekerjaan menunggu dibatalkan; berkas unduhan tetap disimpan')});cancelQueued.classList.add('danger');cancelQueued.disabled=true;
  headActions.append(close);
  async function queue(component,action){const options={model:model.value,device:device.value};if(action==='sample'&&path.value.trim())options.source=path.value.trim();await api('/runtime/jobs',{component,action,options});toast('Proses ditambahkan ke antrean komponen')}
  const top=el('div',undefined,'row');content.insertBefore(top,controls);
  button(top,'Kalibrasi perangkat',()=>queue('hardware','calibrate'));
  button(top,'Muat ulang status',()=>refresh(true));
  const reportLink=el('a','Unduh laporan perangkat','btn');reportLink.href='/api/studio/runtime/report';reportLink.download='';top.append(reportLink);
  const profileLabel=el('label','Profil worker'),profile=el('select');profileLabel.append(profile);top.append(profileLabel);
  button(top,'Gunakan profil',async()=>{const selected=await api('/runtime/profile',{name:profile.value});device.value=selected.device;toast('Profil worker '+profile.value+' dipilih')});
  const queueHead=el('div',undefined,'runtime-queue-head'),queueCount=el('p',undefined,'help');queueHead.append(el('h3','Antrean komponen'),queueCount);
  const filters=el('div',undefined,'row'),filterLabel=el('label','Tampilkan'),filter=el('select'),searchLabel=el('label','Cari komponen'),search=el('input');
  for(const [id,text] of [['all','Semua proses'],['active','Sedang berjalan'],['queued','Menunggu antrean'],['attention','Gagal / terhenti'],['history','Selesai / dibatalkan']]){const option=el('option',text);option.value=id;filter.append(option)}
  filter.value='all';filterLabel.append(filter);search.type='search';search.placeholder='Contoh: WhisperX';searchLabel.append(search);filters.append(filterLabel,searchLabel);queueHead.append(filters);
  const panes=el('div',undefined,'runtime-job-panes'),jobList=el('div',undefined,'runtime-job-list'),emptyJobs=el('p',undefined,'help');jobList.tabIndex=0;jobList.setAttribute('aria-label','Daftar proses komponen; dapat digulir');jobList.append(emptyJobs);
  const logPanel=el('section',undefined,'runtime-log-panel'),logHead=el('div',undefined,'row spread'),logTitle=el('strong','Log proses'),logNote=el('p',undefined,'help'),logActions=el('div',undefined,'row'),logText=el('pre',undefined,'runtime-log-text');logPanel.hidden=true;logText.tabIndex=0;logText.setAttribute('aria-label','Isi log; dapat digulir');logHead.append(logTitle);logPanel.append(logHead,logNote,logActions,logText);
  button(logActions,'Muat ulang log',()=>loadLog());
  button(logActions,'Salin log',async()=>{if(!navigator.clipboard?.writeText)throw new Error('Salin tidak tersedia. Gunakan Unduh log.');await navigator.clipboard.writeText(logText.textContent);toast('Log disalin')});
  const downloadLog=el('a','Unduh log','btn');downloadLog.download='';logActions.append(downloadLog);
  const closeLog=el('button','Tutup log');closeLog.type='button';closeLog.onclick=()=>{selectedLog=null;logRequest++;logPanel.hidden=true;panes.classList.remove('has-log')};logHead.append(closeLog);
  panes.append(jobList,logPanel);jobs.append(queueHead,panes);
  filter.onchange=()=>{if(lastData)renderJobs(lastData)};search.oninput=()=>{if(lastData)renderJobs(lastData)};
  async function loadLog(){
    if(!selectedLog||closed)return;
    const id=selectedLog,request=++logRequest;
    try{
      const result=await api('/runtime/jobs/'+id+'/log');if(closed||selectedLog!==id||request!==logRequest)return;
      const atBottom=logText.scrollHeight-logText.clientHeight-logText.scrollTop<24,position=logText.scrollTop;
      if(logText.textContent!==result.text){logText.textContent=result.text;logText.scrollTop=atBottom?logText.scrollHeight:position}
      logNote.textContent=result.truncated?'Menampilkan 100.000 byte terakhir; kredensial disembunyikan.':'Log diperbarui otomatis; kredensial disembunyikan.';
    }catch(e){if(!closed&&selectedLog===id&&request===logRequest)logNote.textContent='Log belum dapat dimuat: '+e.message}
  }
  async function openLog(job){
    selectedLog=job.id;logRequest++;logTitle.textContent='Log '+job.component;logText.textContent='Memuat log…';logText.scrollTop=0;
    downloadLog.href='/api/studio/runtime/jobs/'+job.id+'/log/download';logPanel.hidden=false;panes.classList.add('has-log');
    await loadLog();if(selectedLog===job.id){logPanel.scrollIntoView({block:'nearest'});logText.focus({preventScroll:true})}
  }
  function syncActions(data){
    const active=data.jobs.find(job=>['running','cancel_requested'].includes(job.status)),pending=data.jobs.filter(job=>job.status==='queued').length;
    cancelActive.textContent=active?(active.status==='cancel_requested'?'Membatalkan '+active.component:'Batalkan '+active.component):'Tidak ada proses aktif';
    cancelActive.disabled=!!cancelActive.dataset.busy||!active||active.status==='cancel_requested';
    cancelQueued.textContent='Batalkan antrean menunggu ('+pending+')';cancelQueued.disabled=!!cancelQueued.dataset.busy||pending===0;
    const activeComponents=new Set(data.jobs.filter(job=>['queued','running','cancel_requested'].includes(job.status)).map(job=>job.component));
    for(const record of jobNodes.values()){
      record.cancel.disabled=!!record.cancel.dataset.busy||record.job.status==='cancel_requested';
      record.resume.disabled=!!record.resume.dataset.busy||activeComponents.has(record.job.component);
      record.resume.title=activeComponents.has(record.job.component)?'Komponen ini masih memiliki percobaan lain yang aktif.':'';
    }
  }
  function renderComponents(data){
    const opened=new Set([...body.querySelectorAll('details[open]')].map(node=>node.dataset.component));body.replaceChildren();
    const hardware=el('section',undefined,'card');hardware.append(el('h3','Perangkat yang diukur'));
    if(!data.hardware)hardware.append(el('p','Belum dikalibrasi pada komputer ini. Profil menggunakan satu worker dan CPU sampai uji CUDA sendiri lulus.','help'));
    else{
      hardware.append(el('p',`${data.hardware.cpu_threads||'?'} thread CPU · RAM ${size(data.hardware.ram_bytes)} · ${data.hardware.os}`,'help'));
      for(const gpu of data.hardware.gpus||[])hardware.append(el('p',`${gpu.name} · VRAM ${(gpu.total_mb/1024).toFixed(1)} GB · driver ${gpu.driver}`));
      for(const b of data.hardware.benchmarks||[])hardware.append(el('p',`${b.codec}: ${b.passed?'lulus':'belum lulus'} · ${b.frames} frame · ${b.seconds}s`,b.passed?'help':'help runtime-error'));
      hardware.append(el('p',data.hardware.scope,'help'));
    }
    body.append(hardware);
    for(const item of data.components){
      const section=el('section',undefined,'card runtime-component'),row=el('div',undefined,'row spread');row.append(el('h3',item.name),el('span',item.status,'badge'+(item.test?.passed?'':' warn')));section.append(row,el('p',item.role,'help'));
      const actions=el('div',undefined,'row');
      button(actions,item.installed?'Pasang generasi baru':'Pasang / daftarkan',()=>queue(item.id,'install'));
      if(item.installed){
        button(actions,'Periksa runtime',()=>queue(item.id,'probe'));
        if(item.kind!=='docs')button(actions,item.id==='motion-canvas'?'Build contoh':'Uji sampel',()=>queue(item.id,'sample'));
        if(item.previous)button(actions,'Pulihkan generasi sebelumnya',()=>queue(item.id,'rollback'));
        if(item.id==='faster-whisper')button(actions,item.enabled?'Gunakan transcriber utama':'Aktifkan transcriber terisolasi',()=>api('/runtime/components/faster-whisper/enabled',{enabled:!item.enabled}));
      }
      section.append(actions);
      if(item.test?.detail)section.append(el('p',item.test.detail,'help'));
      if(item.test?.fallback)section.append(el('p','CUDA beralih ke CPU: '+item.test.fallback.reason,'help'));
      if(item.test?.duration_seconds!=null)section.append(el('p',`Uji terakhir: ${item.test.duration_seconds}s · ${item.test.device||'runtime'} · ${item.test.level}`,'help'));
      if(item.id==='faster-whisper'&&item.enabled)section.append(el('p','Dipakai hanya pada proyek yang memilih model sama dan transkripsi terisolasi. Pilihan model proyek tidak berubah.','help'));
      if(item.test?.artifacts?.length){const links=el('div',undefined,'row');for(const artifact of item.test.artifacts){const a=el('a','Buka '+artifact.split('/').pop(),'btn');a.href='/api/studio/runtime/components/'+item.id+'/artifact?'+new URLSearchParams({path:artifact});a.target='_blank';a.rel='noopener';links.append(a)}section.append(links)}
      const detail=el('details');detail.dataset.component=item.id;detail.open=opened.has(item.id);detail.append(el('summary','Versi, sumber, bobot & kebutuhan'));
      detail.append(el('p',`Perkiraan ruang: ${size(item.estimate_bytes)} · lingkungan ${item.group}`,'help'));
      detail.append(el('p',item.runtime+' · '+item.platforms.join(' / '),'help'));
      if(item.weight_source)detail.append(el('p','Sumber bobot: '+item.weight_source,'help'));
      if(item.note)detail.append(el('p',item.note,'help'));
      if(item.access)detail.append(el('p',`${item.access}: ${item.access_configured?'tersedia; akses belum diuji':'belum tersedia'}`,'help'));
      const link=el('a','Sumber resmi');link.href=item.source;link.target='_blank';link.rel='noopener';detail.append(link);
      const version=el('pre');version.textContent=JSON.stringify({rencana:item.requested_version,terpasang:item.version,bobot:item.weights,generasi:item.generation},null,2);detail.append(version);section.append(detail);body.append(section);
    }
    const stock=el('section',undefined,'card');stock.append(el('h3','Sumber B-roll'));
    for(const provider of data.stock)stock.append(el('p',provider.name+' · '+provider.status+' · uji akses belum dijalankan','help'));
    stock.append(el('p','Konektor baru belum dipakai otomatis oleh pipeline. Pexels yang sudah tersedia tetap mengikuti pengaturan proyek.','help'));body.append(stock);
  }
  function renderJobs(data){
    const position=jobList.scrollTop,ids=new Set(data.jobs.map(job=>job.id));
    for(const [id,record] of jobNodes)if(!ids.has(id)){record.node.remove();jobNodes.delete(id)}
    const priority={running:0,cancel_requested:0,failed:1,interrupted:1,queued:2,completed:3,canceled:3};
    const ordered=[...data.jobs].sort((a,b)=>(priority[a.status]??4)-(priority[b.status]??4)||(a.status==='queued'&&b.status==='queued'?a.created-b.created:b.created-a.created));
    let visible=0,cursor=emptyJobs.nextSibling;const query=search.value.trim().toLowerCase();
    for(const job of ordered){
      let record=jobNodes.get(job.id);
      if(!record){
        const node=el('div',undefined,'runtime-job'),title=el('strong'),meta=el('p',undefined,'help'),progress=el('progress'),message=el('p',undefined,'help'),actions=el('div',undefined,'row');node.dataset.jobId=job.id;progress.max=100;
        record={node,title,meta,progress,message,job};
        record.cancel=button(actions,'Batalkan',()=>api('/runtime/jobs/'+record.job.id+'/cancel',{}));
        record.resume=button(actions,'Lanjutkan rencana yang sama',()=>api('/runtime/jobs/'+record.job.id+'/resume',{}));
        button(actions,'Lihat log',()=>openLog(record.job));node.append(title,meta,progress,message,actions);jobNodes.set(job.id,record);
      }
      record.job=job;record.title.textContent=`${job.component} · ${job.action} · ${labels[job.status]||job.status}`;
      record.meta.textContent=[job.options?.model?'Model '+job.options.model:'',job.options?.device?.toUpperCase(),job.id.slice(-8)].filter(Boolean).join(' · ');
      record.progress.value=job.progress||0;record.message.textContent=job.message||job.error||'';
      record.cancel.hidden=!['queued','running','cancel_requested'].includes(job.status);record.resume.hidden=!['failed','interrupted','canceled'].includes(job.status);
      const matches=filter.value==='all'||filter.value==='active'&&['running','cancel_requested'].includes(job.status)||filter.value==='queued'&&job.status==='queued'||filter.value==='attention'&&['failed','interrupted'].includes(job.status)||filter.value==='history'&&['completed','canceled'].includes(job.status);
      const name=data.components.find(item=>item.id===job.component)?.name||'';
      record.node.hidden=!(matches&&(!query||(job.component+' '+name).toLowerCase().includes(query)));if(!record.node.hidden)visible++;
      if(record.node!==cursor)jobList.insertBefore(record.node,cursor);cursor=record.node.nextSibling;
    }
    emptyJobs.hidden=visible>0;emptyJobs.textContent=data.jobs.length?'Tidak ada proses yang cocok dengan filter.':'Belum ada proses komponen.';
    const pending=data.jobs.filter(job=>job.status==='queued').length,running=data.jobs.filter(job=>['running','cancel_requested'].includes(job.status)).length;
    queueCount.textContent=`${running} berjalan · ${pending} menunggu · ${visible} ditampilkan. Semua proses aktif dan 40 riwayat terakhir tersedia.`;
    jobList.scrollTop=position;syncActions(data);
    if(selectedLog){const selected=data.jobs.find(job=>job.id===selectedLog);if(selected)logTitle.textContent=`Log ${selected.component} · ${labels[selected.status]||selected.status}`}
  }
  async function refresh(force=false){
    if(polling||closed)return;polling=true;
    try{
      const data=await api('/runtime');if(closed)return;
      lastData=data;
      summary.textContent=`${data.counts.total} komponen · ${data.counts.installed} lingkungan tercatat · ${data.counts.sample_passed} lolos sampel · disk bebas ${size(data.free_bytes)}${data.gpu?.alive?' · GPU dipakai: '+data.gpu.purpose:''}`;
      const oldProfile=profile.value;profile.replaceChildren();for(const name of Object.keys(data.profiles||{})){const o=el('option',name);o.value=name;profile.append(o)}profile.value=oldProfile||data.selected_profile?.name||'balanced';
      renderJobs(data);
      const signature=JSON.stringify([data.components,data.hardware,data.stock]);if(force||signature!==lastSignature){renderComponents(data);lastSignature=signature}
      if(selectedLog)await loadLog();
    }finally{polling=false}
  }
  const cleanup=()=>{closed=true;logRequest++;clearInterval(timer);dialog.classList.remove('runtime-dialog');dialog.removeEventListener('close',cleanup)};
  dialog.addEventListener('close',cleanup);dialog.showModal();await refresh(true);if(!closed)timer=setInterval(()=>refresh().catch(e=>toast(e.message,true)),2500);
}
