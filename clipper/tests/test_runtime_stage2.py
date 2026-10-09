"""Meaningful stage-2 failure/recovery tests; heavy models remain hardware tests."""
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import urllib.request
from unittest.mock import patch
import pytest
from clipper.runtime.catalog import CATALOG,get,stock_status
from clipper.runtime.download import fetch,Canceled
from clipper.runtime.state import read,write,digest,safe_path
from clipper.runtime.gpu import GPULease,owner
from clipper.runtime.manager import RuntimeManager,redact
from clipper.runtime import install,tasks,probe
from clipper.config import Config

REPO=Path(__file__).resolve().parents[2]


@pytest.fixture
def manager(tmp_path):return RuntimeManager(REPO,tmp_path/'runtime',autostart=False)


@pytest.fixture
def server():
    data=b'content-verified-model\n'*(180000);calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            offset=int(self.headers.get('Range','bytes=0-').split('=')[1].split('-')[0]);calls.append((self.path,offset))
            if self.path=='/ignore':offset=0
            if self.path=='/wrong':offset+=1
            if self.path=='/truncate':payload=data[:200]
            else:payload=data[offset:]
            self.send_response(206 if offset else 200)
            if offset:self.send_header('Content-Range',f'bytes {offset}-{len(data)-1}/{len(data)}')
            self.send_header('Content-Length',str(len(data)-offset if self.path=='/truncate' else len(payload)))
            self.send_header('ETag','"fixture-v1"');self.end_headers()
            try:self.wfile.write(payload)
            except (BrokenPipeError,ConnectionResetError):pass
            self.close_connection=True
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    yield SimpleNamespace(url=f'http://127.0.0.1:{http.server_port}',data=data,sha=hashlib.sha256(data).hexdigest(),calls=calls)
    http.shutdown();http.server_close();thread.join(timeout=2)


def partial(server,tmp_path):
    target=tmp_path/'model.bin';stop=[False]
    def progress(done,total):
        if done>=1024**2:stop[0]=True
    with pytest.raises(Canceled):fetch(server.url+'/model',target,server.sha,size=len(server.data),progress=progress,canceled=lambda:stop[0])
    assert not target.exists();assert target.with_name('model.bin.part').stat().st_size>=1024**2
    return target


def test_catalog_exact27_roles_and_official_sources():
    assert len(CATALOG)==27
    assert len({row['id'] for row in CATALOG})==27
    assert get('opus-skill')['repo']=='opus-pro/opus-skills'
    assert all(row['role'] and row['source'].startswith('https://') and not row['default_enabled'] for row in CATALOG)
    copy=get('talknet');copy['packages'].clear();assert get('talknet')['packages']


@pytest.mark.parametrize('key',['missing',None,[],{}])
def test_unknown_component_rejected(key):
    with pytest.raises(ValueError):get(key)


@pytest.mark.parametrize('path',['../outside','/outside','a/../../outside','C:/outside','a\\b'])
def test_unsafe_runtime_paths(tmp_path,path):
    with pytest.raises(ValueError):safe_path(tmp_path,path)


def test_symlink_escape(tmp_path):
    outside=tmp_path/'outside';outside.mkdir();root=tmp_path/'root';root.mkdir()
    (root/'link').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError):safe_path(root,'link/changed')


def test_download_resumes_exact_range_and_validates_hash(server,tmp_path):
    target=partial(server,tmp_path);offset=target.with_name('model.bin.part').stat().st_size
    fetch(server.url+'/model',target,server.sha,size=len(server.data))
    assert target.read_bytes()==server.data;assert server.calls[-1][1]==offset
    assert not target.with_name('model.bin.part.json').exists()


def test_cached_valid_download_makes_no_request(server,tmp_path):
    target=tmp_path/'model';target.write_bytes(server.data)
    fetch(server.url+'/model',target,server.sha,size=len(server.data))
    assert server.calls==[]


def test_corrupt_download_never_replaces_existing_file(server,tmp_path):
    target=tmp_path/'model';target.write_bytes(b'previous usable model')
    with pytest.raises(ValueError,match='Hash'):fetch(server.url+'/model',target,'0'*64,size=len(server.data))
    assert target.read_bytes()==b'previous usable model';assert not target.with_name('model.part').exists()


def test_interrupted_response_keeps_partial_data(server,tmp_path):
    target=tmp_path/'model'
    with pytest.raises(OSError,match='terputus'):fetch(server.url+'/truncate',target,server.sha,size=len(server.data))
    assert not target.exists();assert target.with_name('model.part').is_file()


def test_server_ignoring_range_restarts_cleanly(server,tmp_path):
    target=partial(server,tmp_path)
    # Same source identity, a server that changes its Range behavior.
    original=urllib.request.urlopen
    def ignore(request,timeout):
        request.remove_header('Range');request.remove_header('If-range');return original(request,timeout=timeout)
    fetch(server.url+'/model',target,server.sha,size=len(server.data),opener=ignore)
    assert target.read_bytes()==server.data


def test_wrong_range_never_publishes(server,tmp_path):
    target=partial(server,tmp_path)
    original=urllib.request.urlopen
    def wrong(request,timeout):
        response=original(request,timeout=timeout);response.headers.replace_header('Content-Range','bytes 7-10/20');return response
    with pytest.raises(ValueError,match='rentang'):fetch(server.url+'/model',target,server.sha,size=len(server.data),opener=wrong)
    assert not target.exists()


def test_completed_partial_recovers_without_416(server,tmp_path):
    target=tmp_path/'model';part=target.with_name('model.part');part.write_bytes(server.data)
    write(part.with_name('model.part.json'),dict(url_hash=hashlib.sha256((server.url+'/model').encode()).hexdigest(),hash=server.sha,algorithm='sha256'))
    fetch(server.url+'/model',target,server.sha,size=len(server.data))
    assert target.exists();assert server.calls==[]


def test_git_blob_hash_download(server,tmp_path):
    target=tmp_path/'source.py';sha=hashlib.sha1(('blob '+str(len(server.data))+'\0').encode()+server.data).hexdigest()
    fetch(server.url+'/model',target,sha,algorithm='git-sha1',size=len(server.data));assert digest(target,'git-sha1')==sha


def test_low_disk_rejected_before_network(server,tmp_path):
    with patch('clipper.runtime.download.shutil.disk_usage',return_value=SimpleNamespace(free=1)):
        with pytest.raises(OSError,match='disk'):fetch(server.url+'/model',tmp_path/'model',server.sha,size=len(server.data))
    assert server.calls==[]


def test_queue_duplicate_cancel_and_same_plan_resume(manager):
    job=manager.enqueue('sam2','install',{'device':'cpu'})
    with pytest.raises(ValueError,match='aktif'):manager.enqueue('sam2','probe')
    manager.cancel(job['id']);assert manager.job(job['id'])['status']=='canceled'
    resumed=manager.resume(job['id']);assert resumed['id']==job['id'];assert resumed['options']==job['options']
    assert manager.claim()==job['id'];assert manager.claim() is None


def test_invalid_source_cannot_create_job(manager,tmp_path):
    with pytest.raises(ValueError):manager.enqueue('faster-whisper','sample',{'source':str(tmp_path/'missing.mp4')})
    assert manager.jobs()==[]


def test_interrupted_worker_recovered_by_pid_birth(manager):
    job=manager.enqueue('sam2','install');manager.claim();manager.update(job['id'],pid=99999999,birth='dead')
    recovered=RuntimeManager(REPO,manager.root,autostart=False)
    assert recovered.job(job['id'])['status']=='interrupted'


def test_real_gpu_lease_serializes_two_processes(tmp_path):
    script='from clipper.runtime.gpu import GPULease; import pathlib,sys;\nwith GPULease(sys.argv[1],"second"):\n pathlib.Path(sys.argv[2]).write_text("entered")\n'
    signal=tmp_path/'entered'
    with GPULease(tmp_path,'first'):
        proc=subprocess.Popen([sys.executable,'-c',script,str(tmp_path),str(signal)],cwd=REPO)
        time.sleep(.4);assert proc.poll() is None;assert not signal.exists();assert owner(tmp_path)['purpose']=='first'
    proc.wait(timeout=8);assert proc.returncode==0;assert signal.read_text()=='entered';assert owner(tmp_path) is None


def test_same_process_threads_cannot_inherit_each_others_lease(tmp_path):
    entered=threading.Event()
    def second():
        with GPULease(tmp_path,'thread'):entered.set()
    with GPULease(tmp_path,'first'):
        thread=threading.Thread(target=second);thread.start();assert not entered.wait(.25)
    thread.join(timeout=3);assert entered.is_set()


def test_dead_gpu_owner_is_recovered(tmp_path):
    lease=GPULease(tmp_path,'recovery')
    with lease.connect() as db:db.execute('INSERT INTO lease VALUES(1,?,?,?,?,?)',('old',99999999,'dead','old',0))
    with lease:assert owner(tmp_path)['purpose']=='recovery'


def test_gpu_lease_canceled_while_waiting(tmp_path):
    with GPULease(tmp_path,'busy'):
        with pytest.raises(Canceled):
            with GPULease(tmp_path,'cancel',canceled=lambda:True):pass
        assert owner(tmp_path)['purpose']=='busy'


def generation(manager,key,name,content):
    directory=manager.root/'generations'/key/name;directory.mkdir(parents=True)
    asset=directory/'model.bin';asset.write_bytes(content)
    receipt=dict(component=key,installed=True,versions={'test':'1'},test={'passed':True,'level':'sample'},
                 artifacts=[dict(path='model.bin',hash=digest(asset),algorithm='sha256')])
    write(directory/'receipt.json',receipt);manager.activate(key,key+'/'+name,receipt);return directory


def test_environment_rollback_validates_backup_and_preserves_projects(manager,tmp_path):
    source=tmp_path/'project.json';source.write_text('manual corrections')
    previous=generation(manager,'sam2','one',b'one');generation(manager,'sam2','two',b'two')
    assert manager.active('sam2')['generation']=='sam2/two'
    manager.rollback('sam2');assert manager.active('sam2')['generation']=='sam2/one';assert source.read_text()=='manual corrections'
    manager.rollback('sam2');assert manager.active('sam2')['generation']=='sam2/two'


def test_tampered_previous_generation_cannot_be_activated(manager):
    previous=generation(manager,'sam2','one',b'one');generation(manager,'sam2','two',b'two');(previous/'model.bin').write_bytes(b'changed')
    with pytest.raises(ValueError,match='berubah'):manager.rollback('sam2')
    assert manager.active('sam2')['generation']=='sam2/two'


def test_new_generation_disables_production_activation(manager):
    generation(manager,'faster-whisper','one',b'one');manager.enable('faster-whisper',True)
    generation(manager,'faster-whisper','two',b'two');assert not read(manager.root/'components/faster-whisper/active.json')['enabled']


def test_activation_requires_real_sample_not_import(manager):
    folder=generation(manager,'faster-whisper','one',b'one');receipt=read(folder/'receipt.json');receipt['test']['level']='import';write(folder/'receipt.json',receipt)
    with pytest.raises(ValueError,match='sampel'):manager.enable('faster-whisper',True)


def test_import_recheck_preserves_verified_asr_sample(manager,monkeypatch):
    generation(manager,'faster-whisper','one',b'one');manager.enable('faster-whisper',True)
    job=manager.enqueue('faster-whisper','probe')
    monkeypatch.setattr(tasks,'probe_generation',lambda *args,**kwargs:dict(passed=True,level='import',detail='recheck'))
    tasks.execute(manager,job)
    assert manager.active('faster-whisper')['test']['level']=='sample'
    assert manager.active('faster-whisper')['diagnostic']['level']=='import'
    assert read(manager.root/'components/faster-whisper/active.json')['enabled']


def test_asr_fingerprint_changes_only_for_enabled_matching_environment(manager,monkeypatch):
    from clipper.analysis_adapter import asr_fingerprint
    cfg=Config(whisper_model='small');monkeypatch.setenv('CLIPPER_RUNTIME_DIR',str(manager.root))
    original=asr_fingerprint('source','audio',cfg)
    folder=generation(manager,'faster-whisper','one',b'one');(folder/'weights').mkdir();(folder/'weights/model.bin').write_bytes(b'weights');(folder/'installed-lock.txt').write_text('faster-whisper==1')
    py=install.interpreter(folder);py.parent.mkdir(parents=True);py.symlink_to(sys.executable)
    receipt=read(folder/'receipt.json');receipt.update(model_choice='small',weights={'commit':'pinned'});write(folder/'receipt.json',receipt)
    assert asr_fingerprint('source','audio',cfg)==original
    manager.enable('faster-whisper',True);assert asr_fingerprint('source','audio',cfg)!=original
    manager.enable('faster-whisper',False);assert asr_fingerprint('source','audio',cfg)==original


def test_receipt_import_is_never_counted_as_sample(manager):
    folder=generation(manager,'sam2','one',b'one');receipt=read(folder/'receipt.json');receipt['test']['level']='import';write(folder/'receipt.json',receipt)
    snapshot=manager.snapshot();assert snapshot['counts']['installed']==1;assert snapshot['counts']['sample_passed']==0
    assert next(r for r in snapshot['components'] if r['id']=='sam2')['status']=='impor diperiksa'


def test_secrets_are_redacted_and_stock_access_is_not_assumed(manager,monkeypatch):
    monkeypatch.setenv('OPUSCLIP_API_KEY','unique-secret-opus');monkeypatch.setenv('HF_TOKEN','unique-hf-secret')
    assert 'unique' not in redact('unique-secret-opus unique-hf-secret')
    value=json.dumps(manager.snapshot());assert 'unique-secret-opus' not in value;assert 'unique-hf-secret' not in value
    providers=stock_status({'PEXELS_API_KEY':'secret'});assert not any(p['network_tested'] for p in providers)


def test_hf_plan_pins_revision_and_checksums_without_remote_code():
    data={'sha':'commit123','siblings':[{'rfilename':'config.json','blobId':'a'*40,'size':9},
            {'rfilename':'model.safetensors','lfs':{'sha256':'b'*64,'size':20}},
            {'rfilename':'pytorch_model.bin','lfs':{'sha256':'c'*64,'size':20}},
            {'rfilename':'modeling_remote.py','blobId':'d'*40}]}
    with patch.object(install,'api',return_value=data):plan=install.model_plan('official/model')
    assert len(plan['files'])==2;assert all('/commit123/' in r['url'] for r in plan['files']);assert not any(r['path'].endswith('.py') for r in plan['files'])


def test_install_resume_uses_same_locked_plan(manager,tmp_path):
    directory=tmp_path/'generation';directory.mkdir();locked={'component':'sam2','packages':['torch==2.8.0'],'source':{'commit':'abc'}};write(directory/'plan.json',locked)
    with patch.object(install,'api',side_effect=AssertionError('network should not be called')):
        assert install.plan(manager,{'component':'sam2','options':{}},directory)==locked


def test_failed_install_probe_preserves_previous_environment(manager,monkeypatch):
    generation(manager,'ffmpeg','old',b'old');job=manager.enqueue('ffmpeg','install')
    monkeypatch.setattr(tasks,'probe_generation',lambda *args,**kwargs:dict(passed=False,detail='sample failure'))
    with pytest.raises(RuntimeError,match='belum diaktifkan'):install.install(manager,job)
    assert manager.active('ffmpeg')['generation']=='ffmpeg/old'


@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='FFmpeg absent')
@pytest.mark.parametrize('key',['ffmpeg','libass','fonttools','pycapcut'])
def test_real_available_component_samples(tmp_path,key):
    result=probe.infer(dict(component=key,directory=str(tmp_path/key),repo=str(REPO),sample=True,device='cpu'))
    assert result['passed'] and result['level']=='sample'
    for name in result['artifacts']:assert (tmp_path/key/name).is_file()


def test_managed_asr_respects_project_model_and_opt_in(manager,monkeypatch):
    from clipper.runtime.bridge import managed_asr
    folder=generation(manager,'faster-whisper','one',b'one');(folder/'weights').mkdir();(folder/'weights/model.bin').write_bytes(b'weights');(folder/'installed-lock.txt').write_text('faster-whisper==1')
    py=install.interpreter(folder);py.parent.mkdir(parents=True);py.symlink_to(sys.executable)
    receipt=read(folder/'receipt.json');receipt.update(model_choice='small',weights={'commit':'pinned'});write(folder/'receipt.json',receipt)
    monkeypatch.setenv('CLIPPER_RUNTIME_DIR',str(manager.root));assert managed_asr(Config(whisper_model='small')) is None
    manager.enable('faster-whisper',True)
    assert managed_asr(Config(whisper_model='medium')) is None
    assert managed_asr(Config(whisper_model='small'))['model_commit']=='pinned'


def test_runtime_api_queue_and_artifact_guard(manager,tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from clipper.api_runtime import router
    app=FastAPI();app.include_router(router(SimpleNamespace(runtime=manager)))
    with TestClient(app) as client:
        snapshot=client.get('/runtime').json();assert snapshot['counts']['total']==27
        response=client.post('/runtime/jobs',json={'component':'sam2','action':'install'});assert response.status_code==200
        assert client.post('/runtime/jobs',json={'component':'sam2','action':'install'}).status_code==400
        jid=response.json()['id'];assert client.post('/runtime/jobs/'+jid+'/cancel').json()['status']=='canceled'
        assert client.post('/runtime/jobs/'+jid+'/resume').json()['status']=='queued'
        assert client.get('/runtime/components/sam2/artifact?path=../../.env').status_code==404
        assert client.post('/runtime/components/sam2/enabled',json={'enabled':True}).status_code==400


def test_real_worker_queue_install_and_calibration(tmp_path):
    if not shutil.which('ffmpeg'):pytest.skip('FFmpeg absent')
    manager=RuntimeManager(REPO,tmp_path/'runtime',autostart=True)
    try:
        first=manager.enqueue('ffmpeg','install');second=manager.enqueue('hardware','calibrate')
        deadline=time.monotonic()+40
        while time.monotonic()<deadline and any(manager.job(j['id'])['status'] in ('queued','running') for j in (first,second)):time.sleep(.15)
        assert manager.job(first['id'])['status']=='completed',manager.job(first['id'])
        assert manager.job(second['id'])['status']=='completed',manager.job(second['id'])
        assert manager.active('ffmpeg')['test']['level']=='sample'
        hardware=read(manager.root/'hardware.json');assert hardware['benchmarks'][0]['passed']
        assert read(manager.root/'profiles.json')['balanced']['concurrency']==1
        assert read(manager.root/'profiles.json')['balanced']['device']=='cpu'
    finally:manager.close()
