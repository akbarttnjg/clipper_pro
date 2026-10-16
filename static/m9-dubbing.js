// A/B and cue review UI. Native device and neural-voice acceptance are separate.
export function mountDubbing({box,field,select,button,project,command,showJob,describe,preview}){
 const b=box('Dubbing terjemahan yang ditinjau','Pilih klip sumber dan track terjemahan M2 yang sudah disetujui. Satu model suara dipakai untuk seluruh cue. Ini memakai rentang sumber sebelum potongan/efek editor. Latar audio diganti keheningan di antara cue; video tidak memakai lip-sync.');
 const clip=select(b,'Klip sumber',[]),track=select(b,'Track terjemahan disetujui',[]),voice=select(b,'Model suara Piper',[]),rate=field(b,'Percepatan maksimum (1 sampai 1,25)','1.15','number');
 rate.min='1';rate.max='1.25';rate.step='0.01';
 let loaded=null,plan=null,checks=[],candidate=null,lastJob=null;
 const review=document.createElement('div'),result=document.createElement('div');b.append(review,result);
 const facts=field(b,'Nama, angka, negasi, satuan dan glossary setiap cue sudah diperiksa',false,'checkbox');
 const rights=field(b,'Hak penggunaan materi, terjemahan dan model suara sudah diperiksa',false,'checkbox');
 function invalidate(){plan=null;checks=[];review.replaceChildren();facts.checked=false;rights.checked=false;}
 for(const n of [clip,track,voice,rate])n.onchange=invalidate;
 function options(node,rows){node.replaceChildren();for(const [id,label]of rows){const o=document.createElement('option');o.value=id;o.textContent=label;node.append(o);}node.value=rows[0]?.[0]||'';}
 function choice(){return JSON.stringify([clip.value,track.value,voice.value,Number(rate.value)]);}
 async function current(){const p=await project();if(!loaded||p.project_id!==loaded.project_id||p.revision!==loaded.revision){invalidate();throw Error('Proyek/revisi berubah. Muat pilihan kembali dan tinjau ulang.');}return p;}
 button(b,'Muat klip, terjemahan dan suara',async()=>{
  invalidate();loaded=await project();const items=(await command('m9.list',{kind:'voice'})).items;
  options(clip,Object.entries(loaded.clips||{}).map(([id,c])=>[id,(c.title||id)+' · '+c.start+'–'+c.end+' detik']));
  options(track,Object.entries(loaded.translation_tracks||{}).filter(([,t])=>t.approved&&t.source_take===loaded.transcript_id&&t.source_revision===loaded.transcript_revision).map(([id,t])=>[id,t.language+' · '+id]));
  options(voice,items.map(v=>[v.id,v.data.name+' · '+v.data.language]));
  if(!clip.value||!track.value||!voice.value)throw Error('Siapkan klip, terjemahan disetujui melalui M2, dan model Piper berlisensi melalui Model & kemampuan.');
 });
 button(b,'Tampilkan rencana dan periksa setiap cue',async()=>{
  const p=await current(),selected=choice();invalidate();
  const value=await command('m9.dub.plan',{project_id:p.project_id,expected_revision:p.revision,clip_id:clip.value,track_id:track.value,voice_id:voice.value,max_rate:Number(rate.value)});
  await current();if(choice()!==selected)throw Error('Pilihan berubah saat rencana dibaca. Buka rencana terbaru.');
  plan=value;review.replaceChildren();
  const header=document.createElement('p');header.textContent='Bahasa '+plan.language+' · '+plan.duration+' detik · satu suara · tanpa lip-sync. Glossary: '+(plan.glossary||'belum diisi');review.append(header);
  const table=document.createElement('table'),head=document.createElement('tr');
  for(const title of ['Cue / detik sumber','Ucapan sumber','Terjemahan']){const th=document.createElement('th');th.textContent=title;head.append(th);}table.append(head);
  for(const cue of plan.cues){const row=document.createElement('tr');for(const value of [cue.cue_id+' · '+cue.start+'–'+cue.end,cue.source_text,cue.text]){const td=document.createElement('td');td.textContent=value;row.append(td);}table.append(row);}
  review.append(table);checks=plan.cues.map(c=>({id:c.cue_id,input:field(review,'Cue '+c.cue_id+' sudah diperiksa terhadap sumber',false,'checkbox')}));
 });
 button(b,'Buat kandidat dubbing',async()=>{
  await current();if(!plan)throw Error('Buka dan periksa rencana terbaru dahulu.');
  const args={project_id:plan.project_id,expected_revision:plan.input_revision,clip_id:plan.clip_id,track_id:plan.track_id,voice_id:plan.voice_id,audio_index:plan.audio_index,max_rate:plan.max_rate,
   plan_digest:plan.plan_digest,reviewed_cue_ids:checks.filter(c=>c.input.checked).map(c=>c.id),facts_reviewed:facts.checked,rights_reviewed:rights.checked};
  const job=await command('m9.dub.submit',args);lastJob=job.id;showJob(result,job.id);
 });
 const item=field(b,'ID kandidat dubbing (bisa dibuka kembali nanti)');
 async function openCandidate(){
  candidate=null;const value=await command('m9.get',{id:item.value});
  if(value.kind!=='dubbing'||value.data.status!=='awaiting_listening')throw Error('Kandidat belum menunggu tinjauan dengar atau sudah diterima.');
  result.replaceChildren();
  await preview(result,'Video/audio kandidat sintetis',value.data.program_url,'program');
  await preview(result,'A — audio asli',value.data.original_url,'audio');
  await preview(result,'B — suara terjemahan sintetis',value.data.dubbed_url,'audio');
  describe(result,{output_content_id:value.data.output.content_id,plan_digest:value.data.plan.plan_digest,source_range:value.data.plan.source_range});candidate=value;
  listened.checked=false;timing.checked=false;pronunciation.checked=false;
 }
 button(b,'Buka hasil tugas dubbing terakhir',async()=>{if(!lastJob)throw Error('Belum ada tugas di tab ini. Isi ID kandidat untuk hasil lama.');const job=await command('m9.job.get',{job_id:lastJob});if(!job.result?.item_id)throw Error('Kandidat belum siap. Periksa status tugas.');item.value=job.result.item_id;await openCandidate();});
 button(b,'Buka kandidat A/B',openCandidate);
 item.onchange=()=>{candidate=null;listened.checked=false;timing.checked=false;pronunciation.checked=false;};
 const listened=field(b,'Saya telah mendengarkan A/B sampai selesai',false,'checkbox'),timing=field(b,'Jeda dan timing suara hasil sudah diperiksa',false,'checkbox'),pronunciation=field(b,'Pengucapan nama, angka, negasi dan istilah hasil sudah benar',false,'checkbox');
 button(b,'Terima hasil ini dan buat proyek editor baru',async()=>{
  if(!candidate||candidate.id!==item.value)throw Error('Buka hasil A/B kandidat ini dahulu.');
  const job=await command('m9.dub.accept',{id:candidate.id,expected_version:candidate.version,output_content_id:candidate.data.output.content_id,listened:listened.checked,timing_reviewed:timing.checked,facts_reviewed:pronunciation.checked});candidate=null;showJob(result,job.id);
 });
}
