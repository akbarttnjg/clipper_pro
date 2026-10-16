// Durable capture transport. MediaRecorder fragments are concatenated server-side.
// Local chunks remain until explicit deletion; upload acknowledgement is separate.
export class CaptureStore9 {
 constructor(indexedDB=globalThis.indexedDB){this.idb=indexedDB;this.ready=this.open();}
 open(){return new Promise((resolve,reject)=>{const r=this.idb.open('clipper-capture9',1);r.onupgradeneeded=()=>{const d=r.result;d.createObjectStore('chunks',{keyPath:'id'});d.createObjectStore('tracks',{keyPath:'id'});};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
 async operation(name,mode,action){const db=await this.ready;return new Promise((resolve,reject)=>{const tx=db.transaction(name,mode);let value;const request=action(tx.objectStore(name));request.onsuccess=()=>value=request.result;tx.oncomplete=()=>resolve(value);tx.onerror=()=>reject(tx.error||request.error);tx.onabort=()=>reject(tx.error||Error('Penyimpanan lokal dibatalkan'));});}
 put(name,value){return this.operation(name,'readwrite',s=>s.put(value));}
 all(name){return this.operation(name,'readonly',s=>s.getAll());}
 remove(name,id){return this.operation(name,'readwrite',s=>s.delete(id));}
 async clearRoom(room){for(const name of ['chunks','tracks'])for(const row of await this.all(name))if(row.room===room)await this.remove(name,row.id);}
}

export const digest9=async blob=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer())),n=>n.toString(16).padStart(2,'0')).join('');

export class Recorder9 {
 constructor({request,room,store=new CaptureStore9(),guest=false,onUpdate=()=>{},onFatal=()=>{},mediaDevices=globalThis.navigator?.mediaDevices,MediaRecorder=globalThis.MediaRecorder,clock=()=>performance.now()}){
  Object.assign(this,{request,room,store,guest,onUpdate,onFatal,mediaDevices,MediaRecorder,clock});this.active=[];this.streams=[];this.running=false;this.uploading=false;this.closed=false;this.bytes=0;this.pendingWrites=new Set();
 }
 path(suffix){return this.guest?'/m9/guest/'+encodeURIComponent(this.room)+suffix:'/m9/v1'+suffix;}
 async sync(){let best=null;for(let n=0;n<3;n++){const a=this.clock(),value=await this.request(this.path('/clock')),b=this.clock();const estimate={server:value.server_time,mid:(a+b)/2,uncertainty:(b-a)/2};if(!best||estimate.uncertainty<best.uncertainty)best=estimate;}this.timing=best;return best;}
 async start({microphone=true,screen=false,camera=false,micDevice='',cameraDevice='',systemAudio=false,consent=false}){
  if(this.running)throw Error('Rekaman sudah aktif.');if(!consent)throw Error('Persetujuan merekam diperlukan.');if(!microphone&&!screen&&!camera)throw Error('Pilih perangkat rekaman.');
  if(!this.mediaDevices||!this.MediaRecorder)throw Error('Browser belum mendukung capture; gunakan origin localhost/HTTPS dan periksa izin.');
  await this.store.ready;await this.sync();const inputs=[];
  try{
   if(microphone){const s=await this.mediaDevices.getUserMedia({audio:micDevice?{deviceId:{exact:micDevice}}:true,video:false});this.streams.push(s);inputs.push({kind:'microphone',stream:s});}
   if(screen){const s=await this.mediaDevices.getDisplayMedia({video:{width:{max:1920},height:{max:1080},frameRate:{max:30}},audio:systemAudio});this.streams.push(s);inputs.push({kind:'screen',stream:new MediaStream(s.getVideoTracks())});if(s.getAudioTracks().length)inputs.push({kind:'system_audio',stream:new MediaStream(s.getAudioTracks())});}
   if(camera){const s=await this.mediaDevices.getUserMedia({video:{...(cameraDevice?{deviceId:{exact:cameraDevice}}:{}),width:{ideal:1280,max:1920},height:{ideal:720,max:1080},frameRate:{max:30}},audio:false});this.streams.push(s);inputs.push({kind:'camera',stream:s});}
   for(const input of inputs){const audio=['microphone','system_audio'].includes(input.kind);const types=audio?['audio/webm;codecs=opus','audio/webm','audio/mp4']:['video/webm;codecs=vp8','video/webm','video/mp4'];const mime=types.find(t=>this.MediaRecorder.isTypeSupported(t));if(!mime)throw Error('Codec browser tidak didukung.');
    const mono=this.clock(),started=this.timing.server+(mono-this.timing.mid)/1000;const track=await this.request(this.path('/tracks'),{id:this.room,kind:input.kind,mime,started_at:started,clock_uncertainty_ms:this.timing.uncertainty,consent:true});
    const recorder=new this.MediaRecorder(input.stream,{mimeType:mime,...(audio?{audioBitsPerSecond:128000}:{videoBitsPerSecond:2500000})});const row={id:track.id,room:this.room,kind:input.kind,mime,seq:0,start:0,sealed:false,stopped:false,pending:Promise.resolve(),guest:this.guest};
    await this.store.put('tracks',{...row,pending:undefined});row.start=this.clock();
    recorder.ondataavailable=event=>{if(!event.data?.size)return;const elapsed=(this.clock()-row.start)/1000;const write=this.saveFragments(row,event.data,elapsed);this.pendingWrites.add(write);write.finally(()=>this.pendingWrites.delete(write)).catch(error=>this.fail(error,event.data));};
    recorder.onerror=event=>this.fail(event.error||Error('Perangkat rekaman gagal.'));recorder.onstop=()=>{row.stopped=true;};
    this.active.push({recorder,row,input});recorder.start(4000);
    for(const t of input.stream.getTracks())t.onended=()=>{if(this.running)this.stop().catch(e=>this.fail(e));};
   }
   this.running=true;this.timer=setInterval(()=>this.flush().catch(e=>this.onUpdate({error:e.message,localPreserved:true})),2000);this.onUpdate({running:true,tracks:this.active.map(a=>a.row.id)});
  }catch(error){for(const a of this.active)if(a.recorder.state!=='inactive')a.recorder.stop();for(const s of this.streams)for(const t of s.getTracks())t.stop();throw error;}
 }
 async saveFragments(row,blob,elapsed){
  // A delayed browser event may exceed transport limits. Byte splitting is safe
  // for later concatenation, and avoids assuming each fragment is playable.
  const chunks=[];for(let offset=0;offset<blob.size;offset+=8*1024*1024){const piece=blob.slice(offset,offset+8*1024*1024);const seq=row.seq++;chunks.push({piece,seq});}
  const operation=async()=>{for(const {piece,seq}of chunks){const checksum=await digest9(piece);await this.store.put('chunks',{id:row.id+':'+String(seq).padStart(6,'0'),room:this.room,track:row.id,seq,blob:piece,elapsed,sha256:checksum,uploaded:false});this.bytes+=piece.size;}
   await this.store.put('tracks',{id:row.id,room:this.room,kind:row.kind,mime:row.mime,seq:row.seq,stopped:row.stopped,sealed:false,guest:this.guest});this.onUpdate({localBytes:this.bytes,running:this.running});};
  row.pending=row.pending.then(operation);await row.pending;
 }
 async flush(){if(this.uploading)return;this.uploading=true;try{const rows=(await this.store.all('chunks')).filter(r=>r.room===this.room&&!r.uploaded).sort((a,b)=>a.track.localeCompare(b.track)||a.seq-b.seq);for(const row of rows){const path=this.guest?this.path('/tracks/'+row.track+'/chunks/'+row.seq):'/m9/v1/tracks/'+row.track+'/chunks/'+row.seq;
   await this.request(path,row.blob,{method:'PUT',headers:{'X-Chunk-SHA256':row.sha256,'X-Elapsed-Seconds':String(row.elapsed)}});row.uploaded=true;await this.store.put('chunks',row);this.onUpdate({uploaded:row.seq,track:row.track});}
  }finally{this.uploading=false;}}
 async stop(){if(this.stopping)return this.stopping;this.stopping=this.stopAll();return this.stopping;}
 async stopAll(){this.running=false;clearInterval(this.timer);for(const a of this.active)if(a.recorder.state!=='inactive')a.recorder.stop();
  const deadline=this.clock()+10000;while(this.active.some(a=>!a.row.stopped)){if(this.clock()>deadline)throw Error('Browser belum mengirim chunk terakhir; simpan halaman dan periksa cadangan lokal.');await new Promise(r=>setTimeout(r,30));}
  for(const s of this.streams)for(const t of s.getTracks())t.stop();await Promise.all([...this.pendingWrites]);
  for(const a of this.active)await this.store.put('tracks',{id:a.row.id,room:this.room,kind:a.row.kind,mime:a.row.mime,seq:a.row.seq,stopped:true,sealed:false,guest:this.guest});
  this.onUpdate({running:false,localPreserved:true});await this.resume();
 }
 async resume(){await this.flush();if(this.uploading)throw Error('Unggahan masih berjalan; tekan Pulihkan unggahan lagi setelah selesai.');
  const all=await this.store.all('chunks');for(const row of await this.store.all('tracks'))if(row.room===this.room&&row.stopped&&!row.sealed){const chunks=all.filter(c=>c.track===row.id);if(chunks.length!==row.seq||chunks.some(c=>!c.uploaded))throw Error('Masih ada chunk lokal yang belum diunggah.');
   const data={track_id:row.id,expected_chunks:row.seq};if(this.guest)await this.request(this.path('/seal'),data);else await this.request('/m8/v1/command',{schema_version:1,command_id:crypto.randomUUID(),action:'m9.record.seal',args:data});row.sealed=true;await this.store.put('tracks',row);}
  this.onUpdate({allUploaded:true,localPreserved:true});
 }
 async downloadLocal(){const rows=(await this.store.all('chunks')).filter(r=>r.room===this.room);const tracks=await this.store.all('tracks');return tracks.filter(t=>t.room===this.room).map(t=>({name:t.id+(t.mime.startsWith('audio/')?'.audio':'.video')+(t.mime.includes('mp4')?'.mp4':'.webm'),blob:new Blob(rows.filter(r=>r.track===t.id).sort((a,b)=>a.seq-b.seq).map(r=>r.blob),{type:t.mime}),track:t}));}
 fail(error,blob){this.onFatal(error,blob);if(this.running)this.stop().catch(e=>this.onUpdate({error:e.message,localPreserved:true}));}
 destroy(){clearInterval(this.timer);if(this.running)return this.stop();return Promise.resolve();}
}
