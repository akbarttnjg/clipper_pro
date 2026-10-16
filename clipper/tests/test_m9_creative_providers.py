"""Local HTTP/CLI protocol fixtures; these tests do NOT measure neural quality."""
import base64
import io
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import pytest
from PIL import Image
from clipper.m9_contract import sha
from clipper.m9_providers import local_url
from clipper.m8_contract import AccessDenied,canonical
from clipper.studio_worker import execute
from clipper.project_store import Conflict
from ._m4_fixture import make_studio


@pytest.fixture
def studio(tmp_path):
    service=make_studio(tmp_path)
    try:yield service
    finally:service.queue.close();service.integrations.close()


@pytest.fixture
def local_fixture():
    stream=io.BytesIO();Image.new('RGB',(64,64),(10,100,170)).save(stream,format='PNG')
    state={'calls':[],'busy':False,'fail_submit':False,'generated':{'text':'Catat biaya usaha dan simpan bukti transaksi.','references':[0],'operations':[]}}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            state['calls'].append(self.path)
            if self.path=='/system_stats':value={'devices':[{'vram_free':4*1024**3}]}
            elif self.path=='/object_info':value={c:{} for c in ('CheckpointLoaderSimple','CLIPTextEncode','EmptyLatentImage','KSampler','VAEDecode','SaveImage')}
            elif self.path=='/queue':value={'queue_running':[['1','fixture-prompt']] if state['busy'] else [],'queue_pending':[]}
            elif self.path.startswith('/history/'):value={'fixture-prompt':{'status':{'completed':True,'status_str':'success'},'outputs':{'9':{'images':[{'filename':'fixture.png','subfolder':'','type':'output'}]}}}}
            elif self.path.startswith('/view?'):
                self.send_response(200);self.end_headers();self.wfile.write(stream.getvalue());return
            else:self.send_response(404);self.end_headers();return
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps(value).encode())
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));state['calls'].append((self.path,body))
            if self.path=='/prompt' and state['fail_submit']:
                self.send_response(503);self.end_headers();return
            value={'prompt_id':'fixture-prompt'} if self.path=='/prompt' else {'response':json.dumps(state['generated']),'done_reason':'stop'}
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps(value).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(server.server_port),state
    finally:server.shutdown();server.server_close();thread.join(timeout=2)


def register_provider(studio,tmp_path,address):
    model=tmp_path/'authored-fixture.safetensors';model.write_bytes(b'NOT A MODEL - PROTOCOL FIXTURE ONLY')
    workflow={'1':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':model.name}},'2':{'class_type':'EmptyLatentImage','inputs':{'width':64,'height':64,'batch_size':1}},
        '3':{'class_type':'KSampler','inputs':{'seed':1,'steps':2}},'6':{'class_type':'CLIPTextEncode','inputs':{'text':'fixture'}},'9':{'class_type':'SaveImage','inputs':{'filename_prefix':'fixture'}}}
    path=tmp_path/'workflow.json';path.write_text(json.dumps(workflow));actor=studio.integrations.local_actor()
    item=studio.lab.providers.register(actor,{'name':'AUTHORED HTTP protocol fixture','url':address,'workflow_path':str(path),'model_path':str(model),
        'license':'Authored protocol fixture; NOT actual inference evidence','prompt_node':'6','seed_node':'3','memory_budget_mib':512})
    return studio.lab.providers.probe(actor,{'id':item['id']})


@pytest.mark.parametrize('url',['https://api.paid.example','http://localhost:8188','http://127.0.0.1.evil:8188','http://127.0.0.1/path','http://user:secret@127.0.0.1','http://169.254.169.254','file:///tmp/x'])
def test_provider_endpoint_is_explicit_numeric_loopback(url):
    with pytest.raises(ValueError):local_url(url)


def test_real_HTTP_creative_protocol_citations_coeditor_revision_and_bad_ops(studio,local_fixture):
    address,state=local_fixture;actor=studio.integrations.local_actor();pid=studio.test_pid
    doc=studio.store.get(pid);studio.store.mutate(pid,doc['revision'],'m9-ollama-fixture',{},lambda d:d['settings'].update(ollama_url=address,model='authored-protocol-fixture'))
    doc=studio.store.get(pid);lab=studio.lab
    job=lab.creative.generate(actor,{'project_id':pid,'expected_revision':doc['revision'],'mode':'summary','instruction':'Ringkas','language':'id'})
    result=execute(studio,job);item=lab.store.get(actor,result['item_id']);assert item['data']['references'][0]['word_ids']==[0,1]
    assert item['data']['synthetic'] and item['data']['source_quote'] is False and studio.store.get(pid)['revision']==doc['revision']
    state['generated']={'text':'Usulkan subtitle lebih besar.','references':[0],'operations':[{'op':'settings','values':{'caption_scale':1.1}}]}
    job=lab.creative.generate(actor,{'project_id':pid,'expected_revision':doc['revision'],'mode':'coeditor','instruction':'Perbesar subtitle','language':'id','clip_id':studio.test_cid})
    itemid=execute(studio,job)['item_id'];draft=lab.creative.propose(actor,{'id':itemid,'expected_revision':doc['revision'],'clip_id':studio.test_cid},'m9-coeditor-review')
    assert draft['id'] and draft['document']['clips'][studio.test_cid]['variants']['portrait']['settings']['caption_scale']==1.1 and studio.store.get(pid)['revision']==doc['revision']
    with pytest.raises(ValueError):lab.creative.valid_operations([{'op':'settings','values':{'music_path':'/private/file'}}])
    studio.store.mutate(pid,doc['revision'],'m9-stale-coeditor',{},lambda d:d.update(name='Changed'))
    with pytest.raises(Conflict):lab.creative.propose(actor,{'id':itemid,'expected_revision':doc['revision']+1,'clip_id':studio.test_cid},'m9-stale-proposal')


def test_real_HTTP_generation_protocol_and_failed_submission_holds_serial_queue(studio,tmp_path,local_fixture):
    address,state=local_fixture;actor=studio.integrations.local_actor();lab=studio.lab;provider=register_provider(studio,tmp_path,address)
    assert provider['data']['inference_acceptance']=='not_run'
    job=lab.providers.submit(actor,{'provider_id':provider['id'],'prompt':'Authored fixture only','seed':42,'reviewed':True});result=execute(studio,job)
    item=lab.store.get(actor,result['item_id']);assert item['data']['synthetic'] and item['data']['seed']==42
    assert not lab.dispatch(actor,'m9.status',{})['resource_holds']
    state['fail_submit']=True
    job=lab.providers.submit(actor,{'provider_id':provider['id'],'prompt':'Lost submission fixture','seed':43,'reviewed':True})
    with pytest.raises(ValueError):execute(studio,job)
    assert lab.dispatch(actor,'m9.status',{})['resource_holds']
    queued=studio.queue.enqueue(studio.test_pid,'waveform',{}, {'test':'blocked by unresolved external inference'})
    assert studio.queue.claim(queued['id']) is None
    with pytest.raises(ValueError,match='tidak diulang'):lab.dispatch(actor,'m9.job.resume',{'job_id':job['id']})
    state['busy']=True
    with pytest.raises(ValueError,match='masih bekerja'):lab.providers.reconcile(actor,{'job_id':job['id']})
    state['busy']=False;assert lab.providers.reconcile(actor,{'job_id':job['id']})['released']
    assert studio.queue.claim(queued['id'])['id']==queued['id']


@pytest.mark.skipif(os.name=='nt',reason='POSIX authored CLI fixture; Windows Piper actual runtime acceptance required')
def test_actual_Piper_CLI_transport_with_authored_tone_not_real_voice(studio,tmp_path):
    actor=studio.integrations.local_actor();lab=studio.lab
    executable=tmp_path/'piper-protocol-fixture'
    executable.write_text('#!'+sys.executable+'\nimport sys,wave,struct,math\na=sys.argv;out=a[a.index("--output_file")+1];text=sys.stdin.read()\nwith wave.open(out,"wb") as w:\n w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050);w.writeframes(b"".join(struct.pack("<h",int(500*math.sin(i*.1))) for i in range(22050)))\n')
    executable.chmod(0o700);model=tmp_path/'fixture.onnx';model.write_bytes(b'NOT A MODEL');config=tmp_path/'fixture.onnx.json';config.write_text('{"language":{"code":"id_ID"}}')
    voice=lab.providers.voice_register(actor,{'name':'AUTHORED tone CLI fixture','executable':str(executable),'model_path':str(model),'config_path':str(config),'language':'id_ID','license':'Authored transport fixture only','permission':'licensed'})
    script=lab.creative.save(actor,{'name':'Authored script','mode':'script','text':'Ini contoh tulisan.','language':'id','license':'Authored'})
    args={'id':script['id'],'expected_version':script['version'],'voice_id':voice['id'],'text_sha256':sha(script['data']['text'].encode()),'reviewed':True}
    with pytest.raises(ValueError):lab.providers.tts_submit(actor,{**args,'text_sha256':'0'*64})
    result=execute(studio,lab.providers.tts_submit(actor,args));project=studio.store.get(result['project_id'])
    assert project['source']['info']['kind']=='audio' and project['source']['lineage']['kind']=='synthetic_tts9'
    assert not project.get('transcript_id')
