"""M0 regressions: real SQLite/files/fonts and real FFmpeg negative media.

No neural accuracy, Windows GPU, or native editor acceptance is inferred.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from dataclasses import replace
import pytest
from clipper.config import Config
from clipper.project_store import JobLeaseLost
from clipper.studio_service import StudioService,identifier
from clipper import media_context,stage3
from clipper.dependency_cache import render_key,alignment_identity,content_id
from clipper.artifact_store import ArtifactSet,verify,recovery
from clipper.caption_checks import inspect_caption_plan
from clipper.caption_readability import clear_time
from clipper.subtitle_edit import clean
from clipper.benchmark import evaluate


@pytest.fixture
def service(tmp_path,monkeypatch):
    monkeypatch.setattr(media_context,'inspect',lambda path:{'duration':40.,'audio_tracks':[{'index':1}],'display_size':[640,360]})
    source=tmp_path/'source.mp4';source.write_bytes(b'controlled-source-identity')
    svc=StudioService(tmp_path,Config(work_dir='work',out_dir='clips',visual_enabled=False,align_selected_clips=False,use_nvenc=False),autostart=False)
    doc=svc.create(source)
    ws=[{'word_id':i,'word':text,'start':float(i),'end':i+.8,'probability':None} for i,text in enumerate(('Modal','bukan','5','persen'))]
    take=svc.store.save_transcript(doc['project_id'],{'words':ws,'raw_words':ws,'duration':40})
    def seed(d):
        d['transcript_id']=take
        svc.add_candidates(d,[{'start':0.,'end':35.,'title':'Fixture','keywords':[]}])
    svc.store.mutate(doc['project_id'],0,'seed-m0-01',{},seed)
    doc=svc.store.get(doc['project_id']);cid=next(iter(doc['clips']))
    yield svc,doc,cid,source
    svc.queue.close()


def edit(svc,doc,cid,operations,variant='portrait'):
    return svc.changes({'project_id':doc['project_id'],'clip_id':cid,'variant_id':variant,
                       'expected_revision':doc['revision'],'operation_id':identifier('edit'),'operations':operations})


def test_effective_dependency_ignores_selection_count_but_tracks_caption(service):
    svc,doc,cid,source=service
    before=svc.dependency(doc,cid,'portrait',fresh=True)
    inactive_policy=copy.deepcopy(doc);inactive_policy['settings']['allow_backend_fallback']=False
    assert svc.dependency(inactive_policy,cid,'portrait',fresh=True)==before
    edit(svc,doc,cid,[{'op':'settings','scope':'project','values':{'num_clips':7}}])
    doc=svc.store.get(doc['project_id'])
    assert svc.dependency(doc,cid,'portrait',fresh=True)==before
    edit(svc,doc,cid,[{'op':'settings','values':{'accent_hex':'#00FF00'}}])
    assert svc.dependency(svc.store.get(doc['project_id']),cid,'portrait',fresh=True)!=before


def test_model_bytes_nested_active_and_inactive(service,tmp_path):
    svc,doc,cid,source=service
    model=tmp_path/'model/nested';model.mkdir(parents=True);weight=model/'weights.bin';weight.write_bytes(b'AAAA')
    cfg=replace(svc.config(doc,cid,'portrait'),align_selected_clips=True,alignment_model_path=str(model.parent))
    clip={'start':0.,'end':4.};ws=svc.transcript(doc,cid)['words']
    before=render_key(source,ws,clip,cfg,fresh=True)
    stat=weight.stat();weight.write_bytes(b'BBBB');os.utime(weight,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert render_key(source,ws,clip,cfg,fresh=True)!=before
    inactive=replace(cfg,align_selected_clips=False)
    before=render_key(source,ws,clip,inactive,fresh=True)
    weight.write_bytes(b'CCCC')
    assert render_key(source,ws,clip,inactive,fresh=True)==before
    assert alignment_identity(inactive)==[]


def test_enqueue_freezes_snapshot_and_conflict_adds_no_job(service):
    svc,doc,cid,_=service
    job=svc.enqueue(doc['project_id'],'render',cid,expected_revision=doc['revision'])
    snapshot=copy.deepcopy(job['request']['snapshot'])
    edit(svc,doc,cid,[{'op':'settings','values':{'accent_hex':'#00FF00'}}])
    assert svc.queue.get(job['id'])['request']['snapshot']==snapshot
    count=len(svc.queue.list())
    with pytest.raises(ValueError):svc.enqueue(doc['project_id'],'render',cid,expected_revision=doc['revision'])
    assert len(svc.queue.list())==count


def test_named_asr_weights_invalidate_enqueue_identity(service,tmp_path,monkeypatch):
    from clipper import speech_jobs
    from clipper.dependency_cache import asr_identity
    svc,doc,cid,_=service
    root=tmp_path/'named-model';root.mkdir();weight=root/'model.bin';weight.write_bytes(b'AAAA')
    monkeypatch.setattr(speech_jobs,'_asr_model_path',lambda name:str(root))
    cfg=svc.config(doc);assert asr_identity(cfg,fresh=True)['status']=='verified'
    before=svc.dependency(doc,kind='analyze',fresh=True)
    strict=copy.deepcopy(doc);strict['settings']['allow_backend_fallback']=False
    assert svc.dependency(strict,kind='analyze',fresh=True)!=before
    stamp=weight.stat();weight.write_bytes(b'BBBB');os.utime(weight,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    assert svc.dependency(doc,kind='analyze',fresh=True)!=before


def test_unresolved_asr_identity_cannot_reuse_transcript_cache(tmp_path,monkeypatch):
    from clipper import pipeline,speech_jobs
    def unavailable(name):raise ValueError('controlled unavailable local model')
    monkeypatch.setattr(speech_jobs,'_asr_model_path',unavailable)
    monkeypatch.setattr(pipeline.ffmpeg_util,'ensure_ffmpeg',lambda:None)
    monkeypatch.setattr(pipeline.ffmpeg_util,'filter_file_args',lambda *a:[])
    monkeypatch.setattr(pipeline,'source_key',lambda *a:'unchanged-request-key')
    words=[{'word_id':0,'word':'Percakapan','start':0.,'end':1.,'probability':.8}]
    transcript={'words':words,'duration':1.,'text':'Percakapan','language':'id'};calls=[]
    monkeypatch.setattr(pipeline.transcribe,'transcribe',lambda *a:calls.append('inference') or copy.deepcopy(transcript))
    (tmp_path/'asr-cache.json').write_text(json.dumps({'key':'unchanged-request-key','transcript':transcript,'model_identity_verified':True}))
    result,_=pipeline.analyze('controlled-source',Config(work_dir=str(tmp_path),processing_mode='full',whisper_isolate=False))
    assert calls==['inference'] and not result['timings']['cache_reused']


@pytest.mark.parametrize('flag',[{'timing_status':'manual'},{'alignment_method':'manual'},{'timing_locked':True}])
def test_manual_timing_survives_cleanup_and_unknown_confidence(flag):
    original={'word_id':1,'word':'Modal','start':0.,'end':6.,'probability':None,**flag}
    before=copy.deepcopy(original)
    out,changes,warnings=clean([original])
    assert (out[0]['start'],out[0]['end'])==(0.,6.) and original==before
    assert any(w.get('confidence_status')=='unknown' for w in warnings)
    assert not any(c.get('reason')=='display_duration_capped' for c in changes)


def test_automatic_alignment_cannot_replace_manual_shared_or_local():
    manual={'transcript_id':'take','origin_word_ids':[1],'text':'Modal','method':'manual',
            'audio_start':0.,'audio_end':6.,'words':[{'word':'Modal','start':0.,'end':6.}]}
    auto={**manual,'method':'whisperx','words':[{'word':'Modal','start':0.,'end':1.,'score':.8}]}
    group={'manual':copy.deepcopy(manual)}
    assert stage3.store_alignment(group,auto) is False and group['manual']==manual
    doc={'transcript_id':'take','alignment_overrides':{'shared':{'manual':manual},'clips':{'c':{'auto':auto}}}}
    result=stage3.apply_alignments([{'word_id':1,'word':'Modal','start':0.,'end':6.}],doc,'c')
    assert result[0]['alignment_method']=='manual'
    assert stage3.expand_aligned(result)[0]['end']==6.


def test_empty_bounds_rejected_and_intersections_undo_together(service):
    svc,doc,cid,_=service
    for vid in ('portrait','landscape'):
        edit(svc,doc,cid,[{'op':'timeline','keep_spans':[[10.,20.],[25.,35.]]}],vid)
        doc=svc.store.get(doc['project_id'])
    before=copy.deepcopy(doc)
    with pytest.raises(ValueError,match='beririsan'):edit(svc,doc,cid,[{'op':'bounds','start':21.,'end':24.}])
    assert svc.store.get(doc['project_id'])==before
    response=edit(svc,doc,cid,[{'op':'bounds','start':15.,'end':30.}])
    current=svc.store.get(doc['project_id'])
    assert all(v['timeline']['keep_spans']==[[15.,20.],[25.,30.]] for v in current['clips'][cid]['variants'].values())
    svc.store.undo(doc['project_id'],current['revision'],'undo-m0-bounds',response['revision'])
    after=svc.store.get(doc['project_id'])
    assert after['clips'][cid]['start']==0. and all(v['timeline']==before['clips'][cid]['variants'][key]['timeline'] for key,v in after['clips'][cid]['variants'].items())


def test_cancel_claim_interleavings_never_hide_running_owner(service):
    svc,doc,cid,_=service
    from clipper.job_queue import JobQueue
    other=JobQueue(svc.store,svc.work,autostart=False,recover=False)
    for i in range(20):
        job=svc.queue.enqueue(doc['project_id'],'fixture',{}, {'iteration':i})
        barrier=threading.Barrier(2);claimed=[]
        def claim():barrier.wait();claimed.append(other.claim())
        def cancel():barrier.wait();svc.queue.cancel(job['id'])
        threads=[threading.Thread(target=claim),threading.Thread(target=cancel)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(10);assert not thread.is_alive()
        current=svc.queue.get(job['id'])
        if claimed[0]:
            assert current['status']=='cancel_requested' and current['owner']==other.owner
            other.update_owned(claimed[0],status='canceled')
        else:assert current['status']=='canceled' and current['owner'] is None


def test_guarded_commit_and_lease_fence(service):
    svc,doc,cid,_=service
    job=svc.enqueue(doc['project_id'],'render',cid,expected_revision=doc['revision']);job=svc.queue.claim()
    svc.queue.cancel(job['id'])
    with pytest.raises(JobLeaseLost):svc.store.mutate(doc['project_id'],doc['revision'],'publish-m0-cancel',{},lambda d:d.update(name='BAD'),job_guard=job)
    assert svc.store.get(doc['project_id'])==doc
    svc.queue.update_owned(job,status='canceled')
    retry=svc.queue.resume(job['id']);claimed=svc.queue.claim()
    with svc.store.connect() as db:db.execute('UPDATE jobs SET lease_expires=? WHERE id=?',(time.time()-1,claimed['id']))
    svc.queue.recover()
    with pytest.raises(JobLeaseLost):svc.queue.update_owned(claimed,status='completed')
    with pytest.raises(JobLeaseLost):svc.store.mutate(doc['project_id'],doc['revision'],'publish-m0-expired',{},lambda d:d.update(name='BAD'),job_guard=claimed)


def test_complete_job_and_project_pointer_commit_together(service):
    svc,doc,cid,_=service
    svc.enqueue(doc['project_id'],'render',cid,expected_revision=doc['revision']);job=svc.queue.claim()
    svc.store.mutate(doc['project_id'],doc['revision'],'publish-m0-success',{},lambda d:d.update(name='GOOD'),job_guard=job,job_result={'ok':True})
    assert svc.store.get(doc['project_id'])['name']=='GOOD'
    assert svc.queue.get(job['id'])['status']=='completed'
    assert svc.queue.cancel(job['id'])['status']=='completed'
    with pytest.raises(JobLeaseLost):svc.queue.update_owned(job,status='failed')
    with pytest.raises(JobLeaseLost):svc.queue.update_owned(job,result={'ok':False})


def test_prepared_plan_assets_survive_cleanup_of_original_work(tmp_path):
    from clipper.artifact_store import capture_plan_files
    work=tmp_path/'work';work.mkdir();plate=work/'plate.mp4';overlay=work/'captions.webm';asset=tmp_path/'selected-asset.mp4'
    for path in (plate,overlay,asset):path.write_bytes(b'controlled immutable asset '+path.name.encode())
    txn=ArtifactSet(tmp_path/'sets')
    plan=capture_plan_files(txn,{'broll':[{'path':str(plate),'asset':{'path':str(asset)}}],
                                 'caption_renderer':{'path':str(overlay)}},work)
    result=txn.seal()
    for path in (plate,overlay,asset):path.unlink()
    assert verify(result)
    assert Path(plan['broll'][0]['asset']['path']).is_file() and Path(plan['caption_renderer']['path']).is_file()


def test_failed_staging_and_crash_never_change_prior_set(tmp_path,monkeypatch):
    root=tmp_path/'sets';first=ArtifactSet(root)
    (first.staging/'video.mp4').write_bytes(b'OLD VALIDATED MEDIA')
    (first.staging/'edit-plan.json').write_text('{"revision":1}')
    old=first.seal();before={p.name:p.read_bytes() for p in first.final.iterdir()}
    failed=ArtifactSet(root);(failed.staging/'edit-plan.json').write_text('{"revision":2}')
    failed.abort(OSError('controlled disk full'))
    assert verify(old) and {p.name:p.read_bytes() for p in first.final.iterdir()}==before
    crashed=ArtifactSet(root);(crashed.staging/'video.mp4').write_bytes(b'UNPUBLISHED')
    assert any(r['set_id']==crashed.set_id and r['state']=='incomplete' for r in recovery(root))
    assert verify(old)
    (first.final/'edit-plan.json').write_text('{"revision":3}')
    assert not verify(old)


def caption():
    word={'word_id':1,'word_ids':[1],'token_ids':[1],'text':'Modal','x':160.,'y':90.,'width':40.,'size':20.,'baseline':0}
    return {'version':5,'phrases':[{'start':0.,'end':2.,'position':'bottom','alignment':'center','panel':[20.,40.,280.,120.],'words':[word]}]}


def test_duplicate_and_order_are_logical_not_membership():
    plan=caption();plan['phrases'].append(copy.deepcopy(plan['phrases'][0]))
    with pytest.raises(ValueError,match='duplikat'):inspect_caption_plan(plan,Config(target_w=320,target_h=180),[{'word_id':1,'word':'Modal'}])


def test_faint_caption_cannot_pass_readiness():
    plan=caption();word=plan['phrases'][0]['words'][0]
    word['keyframes']=[{'t':0.,'opacity':.1},{'t':2.,'opacity':.1}]
    result=inspect_caption_plan(plan,Config(target_w=320,target_h=180))
    assert result['geometry_passed'] and not result['passed'] and result['status']=='needs_review'
    assert result['clear_time_metrics'][0]['total_clear_seconds']==0


def test_clear_intervals_respect_renderer_interpolation():
    points=[(0,1),(.01,1),(1,0),(1.99,1),(2,1)]
    word={'keyframes':[{'t':t,'opacity':a} for t,a in points]}
    held=clear_time(word,2.,interpolation='hold');linear=clear_time(word,2.,interpolation='linear')
    assert held['total_clear_seconds']==pytest.approx(1.01) and held['longest_contiguous_clear']==1.
    assert linear['total_clear_seconds']==pytest.approx(.0596) and linear['longest_contiguous_clear']==pytest.approx(.0298)
    assert held['total_clear_seconds']<2
    plan=caption();plan['phrases'][0]['words'][0]['keyframes']=[{'t':0.,'opacity':1},{'t':.01,'opacity':0},{'t':1.99,'opacity':1},{'t':2.,'opacity':0}]
    assert not inspect_caption_plan(plan,Config(target_w=320,target_h=180))['passed']


@pytest.mark.parametrize('before,after',[('minus -5 persen','minus 5 persen'),('5 persen','5 rupiah'),('tidak naik 5%','naik 5%'),('Rp 5 juta','Rp 5'),('5%','5')])
def test_critical_metric_preserves_negation_sign_currency_unit(before,after):
    assert not evaluate({'text':before},{'text':after})['protected_tokens_exact']


def test_real_decode_rejects_wrong_fps_and_truncated_faststart(tmp_path):
    from clipper.qc import inspect
    path=tmp_path/'bad-rate.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','testsrc2=s=320x180:r=15:d=1',
                    '-f','lavfi','-i','sine=frequency=600:duration=1','-c:v','libx264','-threads','1','-c:a','aac','-movflags','+faststart','-shortest',str(path)],check=True)
    with pytest.raises(RuntimeError,match='FPS'):inspect(path,Config(target_w=320,target_h=180,output_fps=30),1.)
    report=json.loads(path.with_suffix('.qc.json').read_text())
    assert report['full_decode']=='passed' and not report['passed']
    truncated=tmp_path/'truncated.mp4';truncated.write_bytes(path.read_bytes()[:-1200])
    with pytest.raises((RuntimeError,subprocess.CalledProcessError)):inspect(truncated,Config(target_w=320,target_h=180,output_fps=15),1.)
