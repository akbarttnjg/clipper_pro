"""Real media/process/fault checks. Synthetic transcript is not ASR evidence."""
import copy
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import threading
import time
import types
from dataclasses import replace
import pytest
from clipper.config import Config
from clipper.studio_service import StudioService,identifier
from clipper.studio_worker import execute
from clipper.artifact_store import verify,recovery


@pytest.fixture(scope='module')
def video(tmp_path_factory):
    path=tmp_path_factory.mktemp('m0-media')/'two-audio.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','testsrc2=s=640x360:r=30:d=2',
        '-f','lavfi','-i','sine=frequency=310:duration=2','-f','lavfi','-i','sine=frequency=910:duration=2',
        '-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-threads','1','-c:a','aac','-shortest',str(path)],check=True)
    return path


@pytest.fixture
def studio(tmp_path,video):
    cfg=Config(work_dir='work',out_dir='clips',visual_enabled=False,align_selected_clips=False,use_nvenc=False,
               style_preset='rapi',trim_silence=False,punch_zoom=False,caption_renderer='ass',broll_mode='off',illustration_mode='off')
    svc=StudioService(tmp_path,cfg,autostart=False);doc=svc.create(video)
    words=[{'word_id':i,'word':w,'start':i*.45,'end':i*.45+.4,'probability':None} for i,w in enumerate(('Modal','tetap','lima','persen'))]
    take=svc.store.save_transcript(doc['project_id'],{'words':words,'raw_words':words,'duration':2.})
    def seed(d):
        d['transcript_id']=take;svc.add_candidates(d,[{'title':'M0 synthetic media','start':0.,'end':2.,'keywords':[]}])
    svc.store.mutate(doc['project_id'],0,'synthetic-seed',{},seed)
    doc=svc.store.get(doc['project_id']);cid=next(iter(doc['clips']))
    yield svc,doc,cid
    svc.queue.close()

from clipper.tests._media_requirements import OPENCV_AVAILABLE, OPENCV_REASON


def request(svc,pid,cid,vid='portrait'):
    doc=svc.store.get(pid);return svc.enqueue(pid,'render',cid,vid,doc['revision'])


def tree_bytes(root):
    return {p.relative_to(root).as_posix():p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}


@pytest.mark.skipif(not OPENCV_AVAILABLE,reason=OPENCV_REASON)
def test_real_two_ratios_cache_publication_and_failed_retry(studio,monkeypatch):
    from clipper import pipeline
    svc,doc,cid=studio;pid=doc['project_id'];outputs=[]
    for vid,w,h in [('portrait',1080,1920),('landscape',1920,1080)]:
        job=request(svc,pid,cid,vid);result=execute(svc,job)
        assert svc.queue.get(job['id'])['status']=='completed' and verify(result)
        assert (result['width'],result['height'])==(w,h)
        assert result['qc']['passed'] and result['qc']['full_decode']=='passed'
        plan=json.loads(Path(result['plan_path']).read_text())
        assert plan['runtime_receipt']['actual_encoder']=='libx264' and plan['caption_checks']['passed']
        assert svc.export_readiness(svc.store.get(pid),cid,vid,fresh=True)['status']=='ready'
        outputs.append(result)
    if os.environ.get('M0_EVIDENCE_DIR'):
        evidence=Path(os.environ['M0_EVIDENCE_DIR']);evidence.mkdir(parents=True,exist_ok=True)
        for result in outputs:
            folder=evidence/result['variant_id'];folder.mkdir(exist_ok=True)
            shutil.copy2(result['absolute_file'],folder/'synthetic-render.mp4')
            for name in ('edit-plan.json','runtime-receipt.json','publication-receipt.json','exchange.json','manifest.json'):
                shutil.copy2(Path(result['artifact_root'])/name,folder/name)
            (folder/'result.json').write_text(json.dumps(result,indent=2))
    old=copy.deepcopy(outputs[0]);old_root=Path(old['artifact_root']);before=tree_bytes(old_root)
    current=svc.store.get(pid)
    svc.changes({'project_id':pid,'clip_id':cid,'variant_id':'portrait','expected_revision':current['revision'],
        'operation_id':identifier('selection'),'operations':[{'op':'settings','scope':'project','values':{'num_clips':7}}]})
    expected=svc.store.get(pid)['revision']
    def no_encode(*args,**kwargs):raise AssertionError('Pixel cache hit encoded again')
    with monkeypatch.context() as scoped:
        scoped.setattr(pipeline,'render_clip',no_encode);reused=execute(svc,request(svc,pid,cid))
    assert reused['cache_reused'] and reused['requested_revision']==expected
    assert reused['encode_provenance']==old['encode_provenance']
    assert reused['output_content_id']==old['output_content_id'] and reused['artifact_set_id']!=old['artifact_set_id']
    assert tree_bytes(old_root)==before and verify(old)
    plan=json.loads(Path(reused['plan_path']).read_text());exchange=json.loads(Path(reused['exchange_path']).read_text())
    assert plan['publication']['requested_revision']==expected and exchange['input_revision']==expected
    prior=svc.store.get(pid)['clips'][cid]['variants']['portrait']['result'];prior_bytes=tree_bytes(prior['artifact_root'])
    from clipper.artifact_store import ArtifactSet
    def fail_seal(self):raise OSError('controlled ENOSPC during publication seal')
    with monkeypatch.context() as scoped:
        scoped.setattr(ArtifactSet,'seal',fail_seal)
        with pytest.raises(OSError,match='ENOSPC'):execute(svc,request(svc,pid,cid))
    assert svc.store.get(pid)['clips'][cid]['variants']['portrait']['result']==prior
    assert svc.queue.list(pid)[0]['status']=='failed'
    assert tree_bytes(prior['artifact_root'])==prior_bytes and verify(prior)
    assert any(row['state']=='incomplete' for row in recovery(Path(prior['artifact_root']).parent))


def test_doctor_extracts_selected_second_audio_stream(video,tmp_path):
    from clipper.runtime.probe import excerpt
    import numpy as np
    data={'source':str(video),'audio_stream_index':2};_,values=excerpt(data,tmp_path)
    frequency=np.fft.rfftfreq(len(values),1/16000)[np.argmax(np.abs(np.fft.rfft(values)))]
    assert frequency==pytest.approx(910,abs=4) and data['_audio_receipt']['selected_audio_stream_index']==2
    with pytest.raises(ValueError,match='tersedia'):excerpt({'source':str(video),'audio_stream_index':88},tmp_path)


def test_missing_local_detector_never_downloads(tmp_path,monkeypatch):
    from clipper import crop
    import urllib.request
    def forbidden(*args,**kwargs):raise AssertionError('Hidden model network access')
    monkeypatch.setattr(urllib.request,'urlopen',forbidden);monkeypatch.setattr(urllib.request,'urlretrieve',forbidden)
    monkeypatch.setattr(crop,'_YUNET_PATH',tmp_path/'missing.onnx')
    assert crop._try_yunet(320,180) is None


def test_asr_local_only_and_required_backend_fail_closed(monkeypatch):
    from clipper import transcribe
    calls=[]
    class Model:
        def __init__(self,*args,**kwargs):
            calls.append(kwargs)
            if kwargs['device']=='cuda':raise RuntimeError('CUDA out of memory controlled fixture')
        def transcribe(self,*args,**kwargs):return iter([]),types.SimpleNamespace(duration=1.,language='id')
    monkeypatch.setitem(sys.modules,'faster_whisper',types.SimpleNamespace(WhisperModel=Model))
    # Explicit VAD double: this test measures fallback ownership, not neural VAD.
    from clipper import speech_m2
    monkeypatch.setattr(speech_m2,'vad_input',lambda *args:([0.]*16000,[0.,1.],{'provider':'test_double','gate_count':1}))
    cfg=Config(whisper_model='local-model',whisper_device='cuda',whisper_isolate=False,asr_second_pass=False)
    result=transcribe._run('controlled-audio',cfg)
    assert [c['device'] for c in calls]==['cuda','cpu'] and all(c['local_files_only'] for c in calls)
    assert result['runtime_receipt']['actual_device']=='cpu' and result['runtime_receipt']['fallback_reason']
    calls.clear()
    with pytest.raises(RuntimeError,match='CUDA'):transcribe._run('controlled-audio',replace(cfg,allow_backend_fallback=False))
    assert [c['device'] for c in calls]==['cuda']


def test_cancel_before_launch_starts_no_process(studio,monkeypatch):
    svc,doc,cid=studio;job=request(svc,doc['project_id'],cid);claimed=svc.queue.claim();svc.queue.cancel(job['id'])
    def forbidden(*args,**kwargs):raise AssertionError('Canceled launch started a process')
    monkeypatch.setattr(subprocess,'Popen',forbidden);svc.queue.run_claimed(claimed)
    assert svc.queue.get(job['id'])['status']=='canceled'


@pytest.mark.skipif(os.name=='nt',reason='POSIX process group fixture; Windows taskkill gate runs on target')
@pytest.mark.parametrize('ignore_sigterm',[False,True])
def test_running_cancel_terminates_worker_and_child(studio,tmp_path,monkeypatch,ignore_sigterm):
    from clipper.job_queue import process_birth
    svc,doc,cid=studio;job=request(svc,doc['project_id'],cid);claimed=svc.queue.claim()
    marker=tmp_path/'child.json';original_popen=subprocess.Popen;processes=[]
    child_code="import signal,time,os,sys,json; "+("signal.signal(signal.SIGTERM,signal.SIG_IGN); " if ignore_sigterm else '')+"open(sys.argv[1],'w').write(json.dumps({'child':os.getpid()})); time.sleep(90)"
    code="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',sys.argv[2],sys.argv[1]]); time.sleep(90)"
    def fixture_popen(args,**kwargs):
        if '-m' in args and 'clipper.studio_worker' in args:
            proc=original_popen([sys.executable,'-c',code,str(marker),child_code],**kwargs);processes.append(proc);return proc
        return original_popen(args,**kwargs)
    monkeypatch.setattr(subprocess,'Popen',fixture_popen)
    worker=threading.Thread(target=svc.queue.run_claimed,args=(claimed,));worker.start();deadline=time.monotonic()+10
    while not marker.exists() and time.monotonic()<deadline:time.sleep(.05)
    assert marker.exists();child=json.loads(marker.read_text())['child'];birth=process_birth(child)
    svc.queue.cancel(job['id']);worker.join(10)
    assert not worker.is_alive() and processes[0].poll() is not None
    if process_birth(child)==birth:
        stat=Path(f'/proc/{child}/stat');assert stat.exists() and stat.read_text().rsplit(')',1)[1].split()[0]=='Z'
    assert svc.queue.get(job['id'])['status']=='canceled' and svc.store.get(doc['project_id'])==doc
