// Browser API adapter with real Blob/SHA256; NOT native device/browser acceptance.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
class MemoryStore{
 constructor(){this.rows={chunks:new Map(),tracks:new Map()};this.ready=Promise.resolve();}
 async put(name,value){this.rows[name].set(value.id,{...value});}
 async all(name){return [...this.rows[name].values()].map(v=>({...v}));}
 async remove(name,id){this.rows[name].delete(id);}
}
class Stream{constructor(tracks){this.tracks=tracks;}getTracks(){return this.tracks;}getVideoTracks(){return this.tracks.filter(t=>t.kind==='video');}getAudioTracks(){return this.tracks.filter(t=>t.kind==='audio');}}
const track=kind=>({kind,stopped:false,stop(){this.stopped=true;}});
class Recorder{static instances=[];static isTypeSupported(){return true;}constructor(stream,options){this.stream=stream;this.options=options;this.state='inactive';Recorder.instances.push(this);}start(timeslice){this.timeslice=timeslice;this.state='recording';}emit(blob){this.ondataavailable({data:blob});}stop(){this.state='inactive';queueMicrotask(()=>this.onstop());}}
let mono=1000,offline=false,sequence=0;const calls=[],streams=[],updates=[];
const request=async(url,body,extra={})=>{calls.push({url,body,extra});if(url.endsWith('/clock')){mono+=10;return {server_time:10000+(mono-1000)/1000};}if(url.endsWith('/tracks'))return {id:'track'+(++sequence)};if(extra.method==='PUT'){if(offline)throw Error('Offline authored fixture');return {durable:true};}return {};};
const devices={async getUserMedia(options){const s=new Stream([track(options.audio?'audio':'video')]);streams.push(s);return s;},async getDisplayMedia(){const s=new Stream([track('video'),track('audio')]);streams.push(s);return s;}};
const context=vm.createContext({crypto:require('node:crypto').webcrypto,Blob,MediaStream:Stream,performance:{now:()=>mono},setInterval:()=>1,clearInterval:()=>{},setTimeout,queueMicrotask,console});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/m9-recorder.js'),'utf8').replace(/export /g,''),context);
const Recorder9=vm.runInContext('Recorder9',context);
(async()=>{
 const store=new MemoryStore(),capture=new Recorder9({request,room:'room1',store,onUpdate:v=>updates.push(v),mediaDevices:devices,MediaRecorder:Recorder,clock:()=>mono});
 await assert.rejects(capture.start({consent:false}),/Persetujuan/);assert.equal(calls.length,0,'no permission/network activity before explicit consent');
 await capture.start({microphone:true,screen:true,camera:true,systemAudio:true,consent:true});assert.equal(capture.active.length,4);assert(capture.running);
 assert(Recorder.instances.every(r=>r.timeslice===4000));assert(capture.active.every(a=>a.row.id));
 mono+=4500;Recorder.instances[0].emit(new Blob(['authored audio fragment']));Recorder.instances[1].emit(new Blob([new Uint8Array(9*1024*1024)]));
 await Promise.all([...capture.pendingWrites]);const rows=await store.all('chunks');assert.equal(rows.length,3,'oversized browser chunk split by bytes without assuming playable boundaries');assert(rows.every(r=>r.sha256.length===64));assert.equal(rows[1].elapsed,rows[2].elapsed);
 offline=true;await assert.rejects(capture.flush(),/Offline/);assert((await store.all('chunks')).every(r=>!r.uploaded),'failed uploads retain durable local bytes');
 // Give the other tracks an actual fragment so a recovered seal is meaningful.
 Recorder.instances[2].emit(new Blob(['system audio']));Recorder.instances[3].emit(new Blob(['camera']));await Promise.all([...capture.pendingWrites]);
 await assert.rejects(capture.stop(),/Offline/);assert(!capture.running);assert(streams.every(s=>s.getTracks().every(t=>t.stopped)));
 const local=await capture.downloadLocal();assert.equal(local.length,4);assert.equal(local[0].blob.size,'authored audio fragment'.length);
 offline=false;const restarted=new Recorder9({request,room:'room1',store,mediaDevices:devices,MediaRecorder:Recorder,clock:()=>mono});await restarted.resume();
 assert((await store.all('chunks')).every(r=>r.uploaded));assert((await store.all('tracks')).every(t=>t.sealed));assert.equal((await store.all('chunks')).length,5,'acknowledged chunks are retained until explicit deletion');
 assert(calls.filter(c=>c.extra.method==='PUT').every(c=>c.extra.headers['X-Chunk-SHA256'].length===64));
 const other=new Recorder9({request,room:'guest-room',guest:true,store:new MemoryStore(),mediaDevices:devices,MediaRecorder:Recorder,clock:()=>mono});await other.sync();assert(calls.at(-1).url.startsWith('/m9/guest/guest-room/'));
 console.log('M9 recorder adapter passed: consent, separate tracks, monotonic timing, real SHA256, byte splitting, durable offline recovery, exact sealing, retained local backups and scoped guest path. Native hardware/browser acceptance remains pending.');
})().catch(e=>{console.error(e);process.exitCode=1;});
