// Source-space visual controls; server revisions protect saved pins from reruns.
export function normalizedBox(a,b){
 const x=Math.max(0,Math.min(100,Math.min(a.x,b.x))),y=Math.max(0,Math.min(100,Math.min(a.y,b.y)));
 return [x,y,Math.min(100-x,Math.abs(a.x-b.x)),Math.min(100-y,Math.abs(a.y-b.y))].map(v=>Math.round(v*100)/100);
}
export function mountVisual4(host,{project,clipId,variantId,api,onChange=()=>{},onListen=()=>{}}){
 const clip=project.clips[clipId],variant=clip.variants[variantId],cfg=variant.effective_settings||{},report=variant.visual_report;
 const key=`clipper4-visual-draft|${project.project_id}|${clipId}|${variantId}`;
 let controls=structuredClone(variant.visual_controls||{}),draft,box=null,shot=report?.shots?.[0],destroyed=false;
 try{draft=JSON.parse(localStorage.getItem(key)||'null')}catch{}
 const e=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
 const note=e('p');note.className='help';host.append(note);
 const error=msg=>{note.textContent=msg;note.setAttribute('role','status')};
 const button=(parent,label,fn)=>{let n=e('button',label);n.type='button';n.onclick=async()=>{n.disabled=true;try{await fn()}catch(ex){error(ex.message)}finally{n.disabled=false}};parent.append(n);return n};
 const field=(parent,label,value,type='text')=>{let l=e('label',label),n=e('input');n.type=type;n.value=value;n.setAttribute('aria-label',label);l.append(n);parent.append(l);return n};
 const select=(parent,label,choices,value)=>{let l=e('label',label),n=e('select');n.setAttribute('aria-label',label);for(const [k,t] of choices){let o=e('option',t);o.value=k;n.append(o)}n.value=value;l.append(n);parent.append(l);return n};
 const time=t=>`${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,'0')}`;
 const changes=async (operations,consumeDraft=false)=>{await api('/changes',{project_id:project.project_id,clip_id:clipId,variant_id:variantId,
    expected_revision:consumeDraft?(draft?.revision??project.revision):project.revision,operation_id:crypto.randomUUID(),operations});
    if(consumeDraft){localStorage.removeItem(key);draft=null}if(!destroyed)await onChange()};
 const head=e('div');head.className='row';host.append(head);
 button(head,'Analisis visual klip',()=>api(`/projects/${project.project_id}/jobs`,{kind:'visual_review',clip_id:clipId,variant_id:variantId,expected_revision:project.revision}).then(onChange));
 if(report){
  note.textContent=`${report.summary?.sample_count||0} sampel · ${report.summary?.cache_reused?'cache dipakai':'analisis tersimpan'}${report.stale?' · perlu diperbarui':''}. ${report.summary?.note||''}`;
  const asd=report.summary?.active_speaker||{};host.append(e('p',`Pembicara aktif: ${{ready:'TalkNet dijalankan',unavailable:'bobot lokal belum siap',disabled:'dinonaktifkan',not_needed:'satu pembicara',failed:'worker gagal'}[asd.status]||'bukti belum cukup'}. ${asd.note||''}`));
  const seg=report.segmentation||{};host.append(e('p',`Area teks MediaPipe: ${{ready:`${seg.sampled_frames||0} frame sumber diproses pada CPU`,unavailable:'komponen opsional belum siap',disabled:'dinonaktifkan',failed:'inference gagal; memakai bukti lain'}[seg.status]||'belum diperiksa'}. ${seg.note||''}${seg.status==='ready'?' Pakaian polos boleh ditimpa; wajah, rambut, OCR dan objek yang dikenali dilindungi.':''}`));
 }
 const policies=e('div');policies.className='fields';host.append(policies);
 const active=select(policies,'Pembicara aktif',[['auto','Otomatis bila TalkNet siap'],['off','Pertahankan semua tamu']],cfg.visual_active_speaker||'auto');
 const vlm=select(policies,'Konfirmasi adegan meragukan',[['off','Geometri saja'],['auto','Model visual lokal yang siap'],['smolvlm','SmolVLM lokal'],['qwen3-vl','Qwen3 VL lokal']],cfg.visual_vlm||'off');
 button(policies,'Simpan analisis visual',()=>changes([{op:'settings',values:{visual_active_speaker:active.value,visual_vlm:vlm.value}}]));
 host.append(e('p','Gambar area pada frame sumber. Koreksi berlaku hanya pada rasio ini; transkrip dan sumber tetap tersedia.'));
 const viewer=e('div');viewer.className='visual4-viewer';host.append(viewer);const canvas=e('canvas');canvas.width=1000;canvas.height=Math.round(1000/(report?.source_size?.[0]/report?.source_size?.[1]||16/9));canvas.setAttribute('aria-label','Frame sumber untuk menandai area');viewer.append(canvas);
 const video=e('video');video.src=project.source.url||'';video.muted=true;video.preload='metadata';video.playsInline=true;video.hidden=true;host.append(video);
 const ctx=canvas.getContext('2d');let image=null;
 const paint=()=>{if(destroyed)return;ctx.clearRect(0,0,canvas.width,canvas.height);if(image)ctx.drawImage(image,0,0,canvas.width,canvas.height);
  const W=report?.source_size?.[0]||video.videoWidth||canvas.width,H=report?.source_size?.[1]||video.videoHeight||canvas.height;
  const rect=(b,color,percent=false)=>{ctx.strokeStyle=color;ctx.lineWidth=3;ctx.strokeRect(b[0]/(percent?100:W)*canvas.width,b[1]/(percent?100:H)*canvas.height,b[2]/(percent?100:W)*canvas.width,b[3]/(percent?100:H)*canvas.height)};
  for(const track of shot?.visual?.speaker?.tracks||[])rect(track.box,'#63d6c3');
  const t=video.currentTime||shot?.frame_time||clip.start;
  for(const area of controls.protected||[])if(area.start<=t&&t<area.end)rect(area.box,'#edbe65',true);
  for(const pin of controls.pins||[])if(pin.start<=t&&t<pin.end)rect(pin.box,'#8599fa',true);
  if(box?.length===4&&box.every(Number.isFinite))rect(box,'#ffffff',true);
 };
 const info=e('p');info.className='help';host.append(info);
 const selectShot=s=>{shot=s;info.textContent=s?.composition_reason||'Dengarkan sumber dan pilih waktu untuk menandai area.';if(s?.poster_url){let img=new Image();img.onload=()=>{if(!destroyed&&shot===s){image=img;paint()}};img.src=s.poster_url}else if(video.readyState)video.currentTime=s?.frame_time??clip.start};
 if(report?.shots?.length){const scenes=select(host,'Adegan sumber',report.shots.map((s,i)=>[String(i),`${time(s.source_start)}–${time(s.source_end)} · ${s.visual?.scene?.kind||s.mode}`]),'0');scenes.onchange=()=>selectShot(report.shots[Number(scenes.value)]);selectShot(shot)}
 video.onloadedmetadata=()=>{canvas.height=Math.round(canvas.width*video.videoHeight/video.videoWidth);video.currentTime=shot?.frame_time??clip.start};
 video.onseeked=()=>{if(!destroyed){image=video;paint()}};
 const seek=field(host,'Waktu frame pada sumber (detik)',shot?.frame_time??clip.start,'number');seek.step='.1';
 button(host,'Tampilkan frame ini',()=>{video.currentTime=Number(seek.value);image=video;paint()});button(host,'Dengarkan adegan',()=>onListen(shot?.source_start??clip.start));
 const form=e('div');form.className='fields';host.append(form);
 const kind=select(form,'Jenis area',[['crop','Kunci crop'],['speaker','Area pembicara'],['material','Area materi'],['manual','Lindungi dari subtitle']],draft?.kind||'crop');
 const start=field(form,'Area berlaku mulai (detik sumber)',draft?.start??shot?.source_start??clip.start,'number');
 const end=field(form,'Area berlaku sampai (detik sumber)',draft?.end??shot?.source_end??clip.end,'number');
 const coords=field(host,'Area x y lebar tinggi dalam persen',draft?.box?.join(', ')||'');
 const remember=()=>{draft={revision:draft?.revision??project.revision,kind:kind.value,start:Number(start.value),end:Number(end.value),box:coords.value.split(',').map(Number)};localStorage.setItem(key,JSON.stringify(draft));box=draft.box;paint()};
 for(const f of [kind,start,end,coords])f.onchange=remember;
 if(draft?.box){box=draft.box;error('Draf area dipulihkan; simpan untuk menerapkannya.');paint()}
 let dragging=null;
 const point=event=>{const r=canvas.getBoundingClientRect();return {x:Math.max(0,Math.min(100,(event.clientX-r.left)/r.width*100)),y:Math.max(0,Math.min(100,(event.clientY-r.top)/r.height*100))}};
 canvas.onpointerdown=event=>{dragging=point(event);canvas.setPointerCapture?.(event.pointerId)};
 canvas.onpointermove=event=>{if(dragging){box=normalizedBox(dragging,point(event));paint()}};
 canvas.onpointerup=event=>{if(!dragging)return;box=normalizedBox(dragging,point(event));dragging=null;coords.value=box.join(', ');remember()};
 canvas.onpointercancel=()=>{dragging=null};
 button(host,'Simpan area pada rasio ini',async()=>{remember();if(box.length!==4||box.some(n=>!Number.isFinite(n))||box[2]<1||box[3]<1)throw Error('Gambar area yang cukup besar terlebih dahulu');const area={id:crypto.randomUUID(),start:Number(start.value),end:Number(end.value),box,kind:kind.value};const target=kind.value==='manual'?'protected':'pins';await changes([{op:'visual_controls',values:{[target]:[...(controls[target]||[]),area]}}],true)});
 button(host,'Muat revisi terbaru untuk draf',async()=>{const latest=await api(`/projects/${project.project_id}`);if(destroyed)return;
  if(!latest.clips?.[clipId]?.variants?.[variantId])throw Error('Klip tidak tersedia pada revisi terbaru');
  project=latest;controls=structuredClone(latest.clips[clipId].variants[variantId].visual_controls||{});
  if(draft){draft.revision=latest.revision;localStorage.setItem(key,JSON.stringify(draft))}paint();error('Revisi terbaru dimuat. Draf tetap tersedia dan area baru akan ditambahkan ke koreksi terbaru.');});
 button(host,'Buang draf area',()=>{draft=null;box=null;coords.value='';localStorage.removeItem(key);paint();error('Draf area dibuang. Koreksi yang sudah disimpan tetap tersedia.');});
 const tracks=[...new Set((report?.shots||[]).flatMap(s=>(s.visual?.speaker?.tracks||[]).map(t=>t.track_id)))];
 const speaker=select(host,'Pembicara yang dipilih',[['auto','Otomatis / pertahankan bila ragu'],...tracks.map(t=>[t,t])],controls.speaker_track||'auto');
 button(host,'Simpan pilihan pembicara',()=>changes([{op:'visual_controls',values:{speaker_track:speaker.value}}]));
 const list=e('div');list.className='visual4-pins';host.append(list);
 for(const target of ['pins','protected'])for(const area of controls[target]||[]){let row=e('div');row.className='row';row.append(e('span',`${area.kind} · ${time(area.start)}–${time(area.end)} · ${area.box.join(', ')}%`));button(row,'Hapus area',()=>changes([{op:'visual_controls',values:{[target]:controls[target].filter(p=>p.id!==area.id)}}]));list.append(row)}
 const ocr=e('details');ocr.append(e('summary','Tulisan sumber dan koreksi OCR'));host.append(ocr);
 const texts=new Map((report?.shots||[]).flatMap(s=>s.visual?.ocr||[]).map(r=>[r.id,r]));
 for(const row of texts.values()){let value=field(ocr,`${Math.round(row.confidence*100)}% · ${row.confirmed_repeated?'berulang':'satu sampel'}`,controls.ocr_edits?.[row.id]??row.text);button(ocr,'Simpan koreksi tulisan',()=>changes([{op:'visual_controls',values:{ocr_edits:{...(controls.ocr_edits||{}),[row.id]:value.value}}}]))}
 if(!texts.size)ocr.append(e('p','Belum ada OCR berkeyakinan tinggi. Anda bisa menandai area materi secara manual.'));
 const sam=e('details');sam.append(e('summary','Mask SAM opsional'));host.append(sam);sam.append(e('p','Membutuhkan SAM lokal yang lulus uji. Pilih frame acuan atau propagasi maksimal enam detik pada 5 fps. Mask disimpan terpisah, belum dimasukkan ke video atau layer editor. Setelah menyimpan area mask, jalankan Analisis visual klip.'));
 const samMode=select(sam,'Rentang mask SAM',[['frame','Satu frame acuan'],['range','Propagasi rentang area']],controls.sam_span?'range':'frame');
 const mask=report?.shots?.find(s=>s.mask?.status==='ready')?.mask;
 const maskStatus=report?.shots?.find(s=>!['disabled','ready'].includes(s.mask?.status))?.mask;
 if(maskStatus)sam.append(e('p',`Status mask: ${maskStatus.status}. ${maskStatus.note||''}`));
 if(mask?.url){let img=e('img');img.src=mask.url;img.alt='Mask SAM frame acuan';img.className='visual4-mask';sam.append(img)}
 button(sam,'Simpan area mask',async()=>{remember();const t=Number(seek.value),span=samMode.value==='range'?[Number(start.value),Number(end.value)]:null;
  if(box.length!==4||box.some(n=>!Number.isFinite(n))||box[2]<1||box[3]<1)throw Error('Gambar area objek terlebih dahulu');
  if(span&&(!(span[1]>span[0])||span[1]-span[0]>6||t<span[0]||t>=span[1]))throw Error('Pilih rentang maksimal enam detik dan frame prompt di dalamnya');
  await changes([{op:'visual_controls',values:{sam_enabled:true,sam_box:box,sam_time:t,sam_span:span}}],true);});
 button(sam,'Matikan mask',()=>changes([{op:'visual_controls',values:{sam_enabled:false}}]));
 return {destroy(){destroyed=true;video.pause();video.removeAttribute('src');video.load?.();host.replaceChildren()}};
}
