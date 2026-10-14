import copy
from unittest.mock import patch
import pytest
from .. import camera4_service as camera
from ..studio_worker import execute,StaleJob
from ..project_store import Conflict
from ._m4_fixture import make_studio,controls,change

@pytest.fixture
def studio(tmp_path):
    service=make_studio(tmp_path);yield service;service.queue.close()

def doc(s):return s.store.get(s.test_pid)
def variant(s,vid='portrait'):return s.variant(doc(s),s.test_cid,vid)
def analyze(s,vid='portrait'):
    change(s,{'op':'m4_controls','values':controls()},vid);return execute(s,s.enqueue(s.test_pid,'camera_m4',s.test_cid,vid))
def accept(s,vid='portrait'):
    report=variant(s,vid)['camera4_report'];return change(s,{'op':'m4_decide','analysis_id':report['analysis_id'],'accepted':True,'reason':'Source geometry reviewed','reviewed':['speaker_identity','material_hud','motion_no_pan','safe_area','source_order']},vid)

def test_actual_source_shot_scan_queue_snapshot_and_review(studio):
    before=copy.deepcopy(studio.store.transcript(doc(studio)['transcript_id']));analyze(studio);report=variant(studio)['camera4_report'];assert len(report['shots'])==2;assert abs(report['shots'][0]['end']-2)<.08
    assert report['approved'] is False and not variant(studio)['camera4_enabled'];assert all(s['speaker']['selected'] is None for s in report['segments']);accept(studio);assert camera.renderable(studio,doc(studio),studio.test_cid,'portrait')['approved']
    snap=camera.snapshot(studio,studio.test_pid,studio.test_cid,'portrait');assert snap['report']['frames'][0]['url'].startswith('/api/studio/files/');assert studio.store.transcript(doc(studio)['transcript_id'])==before

def test_human_review_not_imputed_from_model_scores(studio):
    analyze(studio);report=variant(studio)['camera4_report']
    with pytest.raises(ValueError,match='Periksa'):change(studio,{'op':'m4_decide','analysis_id':report['analysis_id'],'accepted':True,'reason':'not checked','reviewed':[]})
    assert not variant(studio)['camera4_enabled']

def test_rejection_retains_report_and_feedback(studio):
    analyze(studio);accept(studio);report=variant(studio)['camera4_report'];change(studio,{'op':'m4_decide','analysis_id':report['analysis_id'],'accepted':False,'reason':'different framing wanted','reviewed':[]})
    assert not variant(studio)['camera4_enabled'] and len(variant(studio)['camera4_feedback'])==2

def test_settings_preserve_report_but_disable_approved_camera(studio):
    analyze(studio);accept(studio);old=copy.deepcopy(variant(studio)['camera4_report']);change(studio,{'op':'m4_controls','values':controls(background='blur')});assert variant(studio)['camera4_report']==old and not variant(studio)['camera4_enabled']

def test_style_reuses_camera_signature_but_clock_change_requires_review(studio):
    analyze(studio);accept(studio);before=camera.signature(studio,doc(studio),studio.test_cid,'portrait');change(studio,{'op':'settings','values':{'accent_hex':'#123456'}});assert camera.signature(studio,doc(studio),studio.test_cid,'portrait')==before
    change(studio,{'op':'editor_segments','segments':[{'id':'edited','start':0.,'end':3.}]})
    with pytest.raises(ValueError,match='clock'):camera.renderable(studio,doc(studio),studio.test_cid,'portrait')

def test_failed_or_canceled_new_analysis_preserves_report(studio):
    analyze(studio);previous=copy.deepcopy(variant(studio)['camera4_report']);job=studio.enqueue(studio.test_pid,'camera_m4',studio.test_cid,'portrait');studio.queue.cancel(job['id'])
    with pytest.raises(StaleJob):execute(studio,job)
    assert variant(studio)['camera4_report']==previous;job=studio.enqueue(studio.test_pid,'camera_m4',studio.test_cid,'portrait')
    with patch('clipper.camera4_observe.analyze',side_effect=ValueError('controlled bad decode')),pytest.raises(ValueError):execute(studio,job)
    assert variant(studio)['camera4_report']==previous

def test_copy_requires_review_on_destination(studio):
    analyze(studio);accept(studio);change(studio,{'op':'m4_copy','variant_ids':['landscape']});assert not variant(studio,'landscape')['camera4_enabled'] and not variant(studio,'landscape')['camera4_report']['approved'];assert variant(studio)['camera4_enabled']

@pytest.mark.parametrize('name,width,height',[('square',1080,1080),('feed',1080,1350),('custom',1440,960)])
def test_extra_ratios_share_source_clock(studio,name,width,height):
    change(studio,{'op':'m4_ratio','variant_id_new':name,'width':width,'height':height});cfg=studio.config(doc(studio),studio.test_cid,name);assert [cfg.target_w,cfg.target_h]==[width,height];assert camera.spans_for(studio,doc(studio),studio.test_cid,name)==camera.spans_for(studio,doc(studio),studio.test_cid,'portrait');assert len(doc(studio)['clips'][studio.test_cid]['variants'])==3

def test_CAS_idempotence_and_conflict(studio):
    current=doc(studio);op={'op':'m4_controls','values':controls()};a=change(studio,op,revision=current['revision'],operation='m4-repeat-1');b=change(studio,op,revision=current['revision'],operation='m4-repeat-1');assert a==b
    with pytest.raises(Conflict):change(studio,op,revision=current['revision'])

def test_changed_evidence_blocks_render(studio):
    analyze(studio);accept(studio);report=variant(studio)['camera4_report']
    from pathlib import Path
    Path(report['frames'][0]['path']).write_bytes(b'changed evidence')
    with pytest.raises(ValueError,match='Bukti frame'):camera.renderable(studio,doc(studio),studio.test_cid,'portrait')

def test_HTTP_revision_guard(studio):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from ..api_studio import create_router
    app=FastAPI();app.include_router(create_router(studio));client=TestClient(app);url='/api/studio/projects/'+studio.test_pid+'/camera4'
    assert client.get(url,params={'clip_id':studio.test_cid}).status_code==200
    result=client.post(url+'/changes',json={'clip_id':studio.test_cid,'expected_revision':0,'operation_id':'http-old-m4','operations':[{'op':'m4_disable'}]});assert result.status_code==409 and not variant(studio).get('camera4_enabled')


def test_legacy_manual_regions_survive_entry_to_M4(studio):
    change(studio,{'op':'visual_controls','values':{'pins':[{'id':'old-crop','start':0.,'end':4.,'kind':'crop','box':[0,0,100,100]}],'protected':[{'id':'old-text','start':0.,'end':4.,'kind':'manual','box':[10,10,20,20]}]}})
    settings=camera.effective_controls(studio,doc(studio),studio.test_cid,'portrait');assert {r['id'] for r in settings['regions']}=={'legacy-old-crop','legacy-old-text'}


def test_copy_does_not_relabel_old_source_analysis_as_current(studio):
    analyze(studio);change(studio,{'op':'m4_controls','values':controls(background='blur')});before=copy.deepcopy(variant(studio,'landscape'))
    with pytest.raises(ValueError,match='usang'):change(studio,{'op':'m4_copy','variant_ids':['landscape']})
    assert variant(studio,'landscape')==before
