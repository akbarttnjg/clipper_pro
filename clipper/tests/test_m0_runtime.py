"""Real supervisor and recovery plus explicitly controlled backend-failure receipts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import types
from contextlib import nullcontext
import pytest
from clipper.job_queue import process_birth
from clipper.project_store import JobLeaseLost
from clipper.runtime.manager import RuntimeManager
from clipper.runtime import probe,tasks
from clipper.runtime.state import read,write
from .test_m0_integration import video,studio,request


def test_real_supervised_worker_publishes_and_records_resources(studio):
    svc,doc,cid=studio;job=request(svc,doc['project_id'],cid);svc.queue.autostart=True;svc.queue.start()
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        result=svc.queue.get(job['id'])
        if result['status'] not in ('queued','running','cancel_requested'):break
        time.sleep(.1)
    svc.queue.close();result=svc.queue.get(job['id'])
    assert result['status']=='completed',result.get('error')
    assert result['result']['qc']['full_decode']=='passed' and result['result']['resource_metrics']['samples']>0


@pytest.mark.skipif(os.name=='nt',reason='POSIX real stale-owner tree fixture')
def test_expired_live_owner_keeps_serial_slot_until_exit(studio):
    svc,doc,cid=studio;job=request(svc,doc['project_id'],cid);claimed=svc.queue.claim()
    proc=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)'],start_new_session=True)
    try:
        svc.queue.update_owned(claimed,pid=proc.pid,pid_birth=process_birth(proc.pid))
        with svc.store.connect() as db:db.execute('UPDATE jobs SET lease_expires=? WHERE id=?',(time.time()-1,claimed['id']))
        svc.queue.recover();assert svc.queue.get(claimed['id'])['status']=='cancel_requested'
        assert svc.queue.claim() is None
        with pytest.raises(JobLeaseLost):svc.queue.update_owned(claimed,status='completed')
        proc.wait(5);svc.queue.recover()
        assert svc.queue.get(claimed['id'])['status']=='interrupted'
        assert svc.store.get(doc['project_id'])==doc
    finally:
        if proc.poll() is None:proc.kill();proc.wait(5)


def test_runtime_options_accept_selected_stream_and_strict_device(tmp_path,video):
    manager=RuntimeManager(Path(__file__).resolve().parents[2],tmp_path/'runtime',autostart=False)
    job=manager.enqueue('faster-whisper','sample',{'source':str(video),'audio_stream_index':2,'required':True})
    assert job['options']['audio_stream_index']==2 and job['options']['required']
    for bad in ({'audio_stream_index':True},{'required':'yes'},{'audio_stream_index':-2}):
        with pytest.raises(ValueError):manager.enqueue('silero-vad','sample',bad)


def test_empty_asr_sample_cannot_be_a_pass(video,tmp_path,monkeypatch):
    class Model:
        def __init__(self,*args,**kwargs):assert kwargs['local_files_only']
        def transcribe(self,*args,**kwargs):return iter([]),types.SimpleNamespace(language='id')
    monkeypatch.setitem(sys.modules,'faster_whisper',types.SimpleNamespace(WhisperModel=Model))
    with pytest.raises(ValueError,match='belum menghasilkan kata'):
        probe.infer({'component':'faster-whisper','directory':str(tmp_path),'repo':str(Path(__file__).resolve().parents[2]),
                     'sample':True,'source':str(video),'audio_stream_index':2,'device':'cpu'})


def test_required_cuda_preflight_cannot_report_cpu_pass(tmp_path,monkeypatch):
    manager=RuntimeManager(Path(__file__).resolve().parents[2],tmp_path/'runtime',autostart=False)
    directory=tmp_path/'generation';py=directory/'env/bin/python';py.parent.mkdir(parents=True);py.symlink_to(sys.executable)
    monkeypatch.setattr(tasks,'gpu_snapshot',lambda:[])
    job={'component':'faster-whisper','id':'fixture','options':{'device':'cuda','required':True}}
    with pytest.raises(ValueError,match='diwajibkan'):tasks.probe_generation(manager,job,directory,{},sample=True)


def test_required_backend_cannot_pass_when_worker_reports_another_device(tmp_path,monkeypatch):
    manager=RuntimeManager(Path(__file__).resolve().parents[2],tmp_path/'runtime',autostart=False)
    directory=tmp_path/'generation';py=directory/'env/bin/python';py.parent.mkdir(parents=True);py.symlink_to(sys.executable)
    monkeypatch.setattr(tasks,'gpu_snapshot',lambda:[{'index':0}])
    monkeypatch.setattr(tasks,'GPULease',lambda *a,**kw:nullcontext())
    class Monitor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def result(self):return {'scope':'controlled_fixture'}
    monkeypatch.setattr(tasks,'GPUMonitor',Monitor)
    def controlled_run(args,*a,**kwargs):write(args[-1],{'passed':True,'level':'sample','device':'cpu','detail':'controlled worker CPU result'})
    monkeypatch.setattr(tasks,'run',controlled_run)
    result=tasks.probe_generation(manager,{'component':'faster-whisper','id':'fixture','options':{'device':'cuda','required':True}},directory,{},sample=True)
    assert not result['passed'] and result['requested_device']=='cuda' and result['actual_device']=='cpu'
