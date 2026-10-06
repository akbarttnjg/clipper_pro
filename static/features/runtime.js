// Component administration lives alongside the creative workflow; drafts stay in place.
const labels={queued:'Antre',running:'Berjalan',cancel_requested:'Membatalkan',completed:'Selesai',failed:'Gagal',interrupted:'Terhenti',canceled:'Dibatalkan'};
const size=n=>n==null?'belum diukur':(n/1024**3).toFixed(1)+' GB';
function el(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node}

export async function mountRuntime(dialog,api,toast,sourcePath=''){
  dialog.replaceChildren();dialog.classList.add('runtime-dialog');
  const head=el('div',undefined,'row spread');head.append(el('h2','Komponen & perangkat'));
  const close=el('button','Tutup');close.onclick=()=>dialog.close();head.append(close);dialog.append(head);
  dialog.append(el('p','Pasang komponen yang dibutuhkan secara bertahap. Versi dan bobot dikunci per lingkungan; data proyek tetap tersedia.','help'));
  const controls=el('div',undefined,'row'),summary=el('p',undefined,'help'),body=el('div'),jobs=el('section',undefined,'card');
  const pathLabel=el('label','Sumber untuk uji audio / video'),path=el('input');path.value=sourcePath||'';path.placeholder='Path video lokal, contoh C:\\Video\\sumber.mp4';pathLabel.append(path);
  const modelLabel=el('label','Bobot faster-whisper'),model=el('select');for(const id of ['small','medium']){const option=el('option',id);option.value=id;model.append(option)}modelLabel.append(model);
  const deviceLabel=el('label','Perangkat uji'),device=el('select');for(const [id,text] of [['cpu','CPU (awal)'],['cuda','CUDA (ukur & fallback CPU)']]){const option=el('option',text);option.value=id;device.append(option)}deviceLabel.append(device);
  controls.append(pathLabel,modelLabel,deviceLabel);dialog.append(controls,summary,jobs,body);
  let closed=false,polling=false,timer=null,lastSignature='';const shownLogs=new Map();
  function button(parent,text,fn){const b=el('button',text);b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn();await refresh(true)}catch(e){toast(e.message,true)}finally{b.disabled=false}};parent.append(b);return b}
  async function queue(component,action){const options={model:model.value,device:device.value};if(action==='sample'&&path.value.trim())options.source=path.value.trim();await api('/runtime/jobs',{component,action,options});toast('Proses ditambahkan ke antrean komponen')}
  const top=el('div',undefined,'row');dialog.insertBefore(top,controls);
  button(top,'Kalibrasi perangkat',()=>queue('hardware','calibrate'));
  button(top,'Muat ulang status',()=>refresh(true));
  const reportLink=el('a','Unduh laporan perangkat','btn');reportLink.href='/api/studio/runtime/report';reportLink.download='';top.append(reportLink);
  const profileLabel=el('label','Profil worker'),profile=el('select');profileLabel.append(profile);top.append(profileLabel);
  button(top,'Gunakan profil',async()=>{const selected=await api('/runtime/profile',{name:profile.value});device.value=selected.device;toast('Profil worker '+profile.value+' dipilih')});
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
    jobs.replaceChildren(el('h3','Antrean komponen'));
    if(!data.jobs.length)jobs.append(el('p','Belum ada proses komponen.','help'));
    for(const job of data.jobs.slice(0,8)){
      const c=el('div',undefined,'runtime-job');c.append(el('strong',`${job.component} · ${job.action} · ${labels[job.status]||job.status}`));
      const progress=el('progress');progress.max=100;progress.value=job.progress||0;c.append(progress,el('p',job.message||'','help'));
      const r=el('div',undefined,'row');if(['queued','running','cancel_requested'].includes(job.status))button(r,'Batalkan',()=>api('/runtime/jobs/'+job.id+'/cancel',{}));
      if(['failed','interrupted','canceled'].includes(job.status))button(r,'Lanjutkan rencana yang sama',()=>api('/runtime/jobs/'+job.id+'/resume',{}));
      button(r,'Lihat log',async()=>{if(shownLogs.has(job.id))shownLogs.delete(job.id);else{const log=await api('/runtime/jobs/'+job.id+'/log');shownLogs.set(job.id,log.text)}});c.append(r);if(shownLogs.has(job.id))c.append(el('pre',shownLogs.get(job.id)));jobs.append(c);
    }
  }
  async function refresh(force=false){
    if(polling||closed)return;polling=true;
    try{
      const data=await api('/runtime');if(closed)return;
      summary.textContent=`${data.counts.total} komponen · ${data.counts.installed} lingkungan tercatat · ${data.counts.sample_passed} lolos sampel · disk bebas ${size(data.free_bytes)}${data.gpu?.alive?' · GPU dipakai: '+data.gpu.purpose:''}`;
      const oldProfile=profile.value;profile.replaceChildren();for(const name of Object.keys(data.profiles||{})){const o=el('option',name);o.value=name;profile.append(o)}profile.value=oldProfile||data.selected_profile?.name||'balanced';
      renderJobs(data);
      const signature=JSON.stringify([data.components,data.hardware,data.stock]);if(force||signature!==lastSignature){renderComponents(data);lastSignature=signature}
    }finally{polling=false}
  }
  const cleanup=()=>{closed=true;clearInterval(timer);dialog.classList.remove('runtime-dialog');dialog.removeEventListener('close',cleanup)};
  dialog.addEventListener('close',cleanup);dialog.showModal();await refresh(true);if(!closed)timer=setInterval(()=>refresh().catch(e=>toast(e.message,true)),2500);
}
