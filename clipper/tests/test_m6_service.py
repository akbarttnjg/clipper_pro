import copy,json
from pathlib import Path
import pytest
from ._m4_fixture import make_studio,change
from ..audio6_service import snapshot
from ..project_store import Conflict

@pytest.fixture
def svc(tmp_path):
    s=make_studio(tmp_path)
    yield s
    s.queue.close()
def doc(s):return s.store.get(s.test_pid)
def cfg(s,vid='portrait'):return s.config(doc(s),s.test_cid,vid)

def test_M6_is_explicit_opt_in_and_disabling_preserves_saved_settings(svc):
    before=cfg(svc);assert before.audio6 is None
    change(svc,{'op':'m6_settings','values':{'source_gain_db':4}});assert cfg(svc).audio6 is None
    change(svc,{'op':'m6_enable','enabled':True});assert cfg(svc).audio6['settings']['source_gain_db']==4
    change(svc,{'op':'m6_enable','enabled':False});assert cfg(svc).audio6 is None and cfg(svc).audio_normalize==before.audio_normalize
    change(svc,{'op':'m6_enable','enabled':True});assert cfg(svc).audio6['settings']['source_gain_db']==4

def test_M6_settings_are_scoped_and_do_not_rewrite_heard_transcript(svc):
    heard=copy.deepcopy(svc.transcript(doc(svc)))
    change(svc,{'op':'m6_settings','values':{'target_lufs':-20}});change(svc,{'op':'m6_enable','enabled':True})
    assert cfg(svc).audio_target_lufs==-20 and cfg(svc,'landscape').audio6 is None
    assert svc.transcript(doc(svc))==heard

def test_M6_revision_conflict_and_field_reset_keep_other_manual_values(svc):
    old=doc(svc)['revision'];change(svc,{'op':'m6_settings','values':{'source_gain_db':4,'normalize':False}})
    with pytest.raises(Conflict):change(svc,{'op':'m6_enable','enabled':True},revision=old)
    change(svc,{'op':'m6_reset','keys':['source_gain_db']});change(svc,{'op':'m6_enable','enabled':True})
    assert cfg(svc).audio6['settings']['source_gain_db']==0 and not cfg(svc).audio_normalize

@pytest.mark.parametrize('owner',['voice','music','sfx'])
def test_master_normalization_cannot_bypass_any_audio_track_lock(svc,owner):
    change(svc,{'op':'m6_enable','enabled':True});change(svc,{'op':'track','track':owner,'values':{'locked':True}});before=doc(svc)
    with pytest.raises(ValueError,match='terkunci'):change(svc,{'op':'m6_settings','values':{'normalize':True}})
    assert doc(svc)==before

def test_project_apply_checks_locked_second_ratio_before_first_mutation(svc):
    change(svc,{'op':'track','track':'voice','values':{'locked':True}},vid='landscape');before=doc(svc)
    with pytest.raises(ValueError,match='terkunci'):change(svc,{'op':'m6_enable','enabled':True,'scope':'project'})
    assert doc(svc)==before

def test_ducking_can_change_with_voice_locked_but_not_music_locked(svc):
    change(svc,{'op':'m6_enable','enabled':True});change(svc,{'op':'track','track':'voice','values':{'locked':True}})
    change(svc,{'op':'m6_settings','values':{'duck_db':-22}})
    change(svc,{'op':'track','track':'music','values':{'locked':True}})
    with pytest.raises(ValueError,match='terkunci'):change(svc,{'op':'m6_settings','values':{'duck_db':-18}})

def test_snapshot_is_read_only_and_missing_models_are_not_claimed_available(svc):
    before=doc(svc);view=snapshot(svc,svc.test_pid,svc.test_cid,'portrait')
    assert doc(svc)==before;assert view['model']['status']=='unavailable' and not view['model']['actual_inference_performed']
    assert not view['normalization_target_active'] and view['gate_g6']=='pending_real_speech_listening'

def test_job_requires_saved_M6_and_invalid_options_are_rejected(svc):
    with pytest.raises(ValueError,match='Aktifkan'):svc.enqueue(svc.test_pid,'audio_m6',svc.test_cid,'portrait',doc(svc)['revision'])
    change(svc,{'op':'m6_enable','enabled':True})
    with pytest.raises(ValueError):svc.enqueue(svc.test_pid,'audio_m6',svc.test_cid,'portrait',doc(svc)['revision'],{'download_models':True})

def test_HTTP_audio_snapshot_diff_and_queue_routes(svc):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from ..api_studio import create_router
    app=FastAPI();app.include_router(create_router(svc));client=TestClient(app)
    before=doc(svc);base=f'/api/studio/projects/{svc.test_pid}/audio6'
    response=client.get(base,params={'clip_id':svc.test_cid,'variant_id':'portrait'});assert response.status_code==200
    response=client.post(base+'/diff',json={'clip_id':svc.test_cid,'variant_id':'portrait','expected_revision':before['revision'],'operation_id':'m6-http-diff','operations':[{'op':'m6_settings','values':{'source_gain_db':3}},{'op':'m6_enable','enabled':True}]})
    assert response.status_code==200 and response.json()['effective_audio']['source_gain_db']==3;assert doc(svc)==before
