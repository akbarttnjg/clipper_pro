"""Real project SQLite/CAS/history/queue tests; text reference is authored."""
import copy
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
import pytest
from ..studio_service import StudioService,identifier
from ..selection_service import signature,required_review,renderable,snapshot
from .. import selection_engine,selection_service,editor_contract as ec,batch7
from ..project_store import Conflict
from ..dependency_cache import content_id
from ..studio_worker import execute,StaleJob
from ._m3_fixture import reference,options,config,wav


@pytest.fixture
def studio(tmp_path):
    service=StudioService(tmp_path,config(tmp_path/'work'),autostart=False);source=wav(tmp_path/'source.wav')
    doc=service.create(source);pid=doc['project_id'];take=service.store.save_transcript(pid,reference(),'m3-authored-reference')
    def seed(d):d.update(transcript_id=take,transcript_revision=1)
    service.store.mutate(pid,0,'m3-seed-reference',{},seed)
    service.test_pid=pid
    yield service
    service.queue.close()


def document(service):return service.store.get(service.test_pid)


def put_report(service,**kw):
    doc=document(service);result=selection_engine.analyze(service.transcript(doc),options(**kw),service.config(doc),source_id=doc['source']['source_id'],take=doc['transcript_id'])
    result.update(source_signature=signature(service,doc),transcript_revision=doc['transcript_revision'])
    service.store.mutate(doc['project_id'],doc['revision'],identifier('m3-report'),{},lambda d:d.update(selection3=result))
    return document(service)


def proposed(doc):return next(c for c in doc['selection3']['candidates'] if not c['completeness']['hard_blockers'])


def change(service,op,revision=None,operation=None):
    doc=document(service)
    return service.changes({'project_id':doc['project_id'],'expected_revision':doc['revision'] if revision is None else revision,
        'operation_id':operation or identifier('m3-change'),'operations':[op]})


def decision(doc,candidate,status='accepted',**kw):
    return {'op':'m3_decide','analysis_id':doc['selection3']['analysis_id'],'candidate_id':candidate['candidate_id'],
        'status':status,'reason':'Diperiksa pada sumber' if status=='accepted' else 'Tidak sesuai kebutuhan',
        'reviewed':required_review(candidate),**kw}


def test_proposals_do_not_create_render_targets(studio):
    doc=put_report(studio);assert doc['clips']=={}
    with pytest.raises(ValueError,match='Pilih'):batch7.targets(doc)
    assert all(c['selection_status']!='accepted' for c in doc['selection3']['candidates'])


def test_accept_creates_two_ratio_clocks_and_preserves_model_scores(studio):
    doc=put_report(studio);c=proposed(doc);scores=copy.deepcopy(c['scores']);change(studio,decision(doc,c));saved=document(studio)
    clip=next(iter(saved['clips'].values()));assert clip['selection_status']=='accepted';assert clip['m3_source_signature']==signature(studio,saved)
    assert len(batch7.targets(saved))==2
    for variant in clip['variants'].values():
        clock=ec.build_clock(variant['editor']['segments'],30);assert clock['duration']==pytest.approx(c['duration'],abs=1/30)
    assert saved['selection3']['candidates'][0]['scores']==doc['selection3']['candidates'][0]['scores'];assert saved['m3_feedback'][0]['decision_basis']=='human_review'


def test_reject_retains_feedback_and_excludes_even_corrupt_included_flag(studio):
    doc=put_report(studio);c=proposed(doc);change(studio,decision(doc,c));doc=document(studio);change(studio,decision(doc,c,'rejected'));saved=document(studio)
    clip=next(iter(saved['clips'].values()));assert not clip['included'] and clip['selection_status']=='rejected';assert len(saved['m3_feedback'])==2
    clip['included']=True
    with pytest.raises(ValueError):batch7.targets(saved)
    with pytest.raises(ValueError,match='belum diterima'):renderable(studio,saved,clip)


def test_human_review_checks_are_required_and_not_filled_from_scores(studio):
    doc=put_report(studio);c=proposed(doc);before=copy.deepcopy(doc)
    with pytest.raises(ValueError,match='Periksa sumber'):change(studio,decision(doc,c,reviewed=[]))
    assert document(studio)==before


def test_rejection_requires_reason_and_preserves_candidate(studio):
    doc=put_report(studio);c=proposed(doc)
    with pytest.raises(ValueError,match='Penolakan'):change(studio,decision(doc,c,'rejected',reason=''))
    assert document(studio)['selection3']==doc['selection3']


def test_stale_revision_conflict_and_operation_replay_are_real(studio):
    doc=put_report(studio);c=proposed(doc);op=decision(doc,c);operation=identifier('m3-idempotent')
    first=change(studio,op,operation=operation);replayed=change(studio,op,revision=doc['revision'],operation=operation)
    assert first==replayed;assert len(document(studio)['m3_feedback'])==1
    with pytest.raises(Conflict):change(studio,op,revision=doc['revision'])


def test_source_signature_change_blocks_accept_without_overwriting_old_report(studio):
    doc=put_report(studio);c=proposed(doc)
    def mutate(d):d['manual_speakers']={'0':{'transcript_id':d['transcript_id'],'speaker_id':'different'}}
    studio.store.mutate(doc['project_id'],doc['revision'],identifier('speaker-edit'),{},mutate)
    with pytest.raises(ValueError,match='berubah'):change(studio,decision(doc,c))
    assert document(studio)['selection3']==doc['selection3']


def test_text_change_invalidates_accepted_final_and_preserves_history(studio):
    doc=put_report(studio);c=proposed(doc);change(studio,decision(doc,c));doc=document(studio)
    change(studio,{'op':'m2_speaker','transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision'],
        'origin_word_ids':[0],'speaker_id':'Speaker reviewed again'})
    saved=document(studio);clip=next(iter(saved['clips'].values()));assert clip['selection_status']=='needs_review' and not clip['included']
    with pytest.raises(ValueError):renderable(studio,saved,clip)
    assert saved['m3_feedback'][0]['status']=='accepted'


def test_raw_and_effective_search_have_separate_signatures(studio):
    doc=put_report(studio);before_raw=signature(studio,doc,'raw');before_display=signature(studio,doc,'display')
    patch={'transcript_id':doc['transcript_id'],'origin_word_ids':[1],'after':'Pisahkan rekening XAUUSD dari belanja pribadi.'}
    studio.store.mutate(doc['project_id'],doc['revision'],identifier('display-only'),{},lambda d:d['shared_corrections'].update({'test':patch}))
    saved=document(studio);assert signature(studio,saved,'raw')==before_raw;assert signature(studio,saved,'display')!=before_display


def test_manual_markers_use_source_time_and_are_idempotent(studio):
    doc=document(studio);op={'op':'m3_marker','time':4.123456,'label':'Momen penting'}
    change(studio,op);change(studio,op);saved=document(studio);assert len(saved['m3_markers'])==1
    assert saved['m3_markers'][0]['time']==4.123456 and saved['m3_markers'][0]['confidence'] is None


@pytest.mark.parametrize('time',[True,-1,49,float('nan')])
def test_outside_or_fake_marker_time_is_rejected(studio,time):
    with pytest.raises(ValueError):change(studio,{'op':'m3_marker','time':time})


def test_multisegment_story_reorders_shared_timeline_without_overwriting_raw_words(studio):
    doc=put_report(studio);heard=studio.store.transcript(doc['transcript_id'])
    change(studio,{'op':'m3_story','analysis_id':doc['selection3']['analysis_id'],'source_spans':[{'start':42.2,'end':47.8},{'start':6.2,'end':17.8}],
        'title':'Penutup dan pengingat'})
    doc=document(studio);c=next(c for c in doc['selection3']['candidates'] if c['candidate_id']==doc['last_m3_story_candidate'])
    change(studio,decision(doc,c));clip=next(iter(document(studio)['clips'].values()))
    for v in clip['variants'].values():
        clock=ec.build_clock(v['editor']['segments'],30)
        assert ec.output_to_source(clock,.5)['source_time']==pytest.approx(42.7,abs=.03)
        assert ec.output_to_source(clock,6.)['source_time']==pytest.approx(6.6,abs=.04)
    assert studio.store.transcript(doc['transcript_id'])==heard


def test_stale_analysis_identity_does_not_apply_new_story(studio):
    doc=put_report(studio)
    with pytest.raises(ValueError,match='berubah'):change(studio,{'op':'m3_story','analysis_id':'old','source_spans':[{'start':.2,'end':5.8}]})
    assert document(studio)['selection3']==doc['selection3']


def test_queued_selection_publishes_atomically_and_next_query_archives_history(studio):
    doc=document(studio);job=studio.enqueue(doc['project_id'],'selection_m3',expected_revision=doc['revision'],options=options(query='usaha'))
    result=execute(studio,job);assert result['asr_invoked'] is False;first=document(studio)['selection3'];assert studio.queue.get(job['id'])['status']=='completed'
    doc=document(studio);job=studio.enqueue(doc['project_id'],'selection_m3',expected_revision=doc['revision'],options=options(query='investasi'))
    execute(studio,job);saved=document(studio);assert saved['selection3_history']==[first];assert saved['selection3']['index']['cache_reused']


def test_canceled_new_selection_does_not_replace_previous_report(studio):
    doc=put_report(studio);previous=copy.deepcopy(doc['selection3']);job=studio.enqueue(doc['project_id'],'selection_m3',expected_revision=doc['revision'],options=options())
    claimed=studio.queue.claim(job['id']);studio.queue.cancel(job['id'])
    with pytest.raises(StaleJob):selection_service.execute(studio,claimed)
    assert document(studio)['selection3']==previous


def test_source_file_change_is_rejected_before_using_old_transcript(studio):
    doc=document(studio);path=Path(doc['source']['path']);path.write_bytes(path.read_bytes()+b'changed source')
    job=studio.enqueue(doc['project_id'],'selection_m3',expected_revision=doc['revision'],options=options())
    with pytest.raises(StaleJob,match='sumber berubah'):execute(studio,job)
    assert not document(studio).get('selection3')


def test_query_options_have_distinct_queue_dependencies_but_style_does_not(studio):
    doc=document(studio);dep=studio.dependency(doc,kind='selection_m3');job1=studio.enqueue(doc['project_id'],'selection_m3',options=options(query='uang'));job2=studio.enqueue(doc['project_id'],'selection_m3',options=options(query='risiko'))
    assert job1['request']['dependency']!=job2['request']['dependency']
    doc['settings']['accent_hex']='#123456';assert studio.dependency(doc,kind='selection_m3')==dep


def test_successful_analysis_queues_m3_after_save_despite_concurrent_style_edit(studio):
    """ASR is an explicit double; save/CAS/queue/media preparation are actual."""
    import sys,types
    doc=document(studio)
    studio.store.mutate(doc['project_id'],doc['revision'],identifier('auto-on'),{},lambda d:d['settings'].update(m3_auto_selection=True))
    doc=document(studio);job=studio.enqueue(doc['project_id'],'analyze',expected_revision=doc['revision'])
    fake=types.ModuleType('clipper.pipeline');fake.analyze=lambda *a,**k:(copy.deepcopy(reference()),[])
    enqueue=studio.enqueue
    def concurrent_enqueue(pid,kind,**kw):
        current=studio.store.get(pid)
        studio.store.mutate(pid,current['revision'],identifier('concurrent-style'),{},lambda d:d['settings'].update(accent_hex='#112233'))
        return enqueue(pid,kind,**kw)
    import clipper
    with patch.dict(sys.modules,{'clipper.pipeline':fake}),patch.object(clipper,'pipeline',fake,create=True),patch.object(studio,'enqueue',side_effect=concurrent_enqueue),patch('clipper.editorial.release'):
        result=execute(studio,job)
    saved=document(studio)
    assert saved['transcript_id']==result['transcript_id'] and saved['clips']=={}
    assert saved['settings']['accent_hex']=='#112233' and studio.queue.get(job['id'])['status']=='completed'
    queued=[j for j in studio.queue.list(saved['project_id']) if j['kind']=='selection_m3']
    assert len(queued)==1 and queued[0]['status']=='queued'
    assert queued[0]['request']['snapshot']['transcript_id']==saved['transcript_id']


def test_visual_audio_without_transcript_is_not_reported_as_asr_success(studio):
    doc=document(studio)
    studio.store.mutate(doc['project_id'],doc['revision'],identifier('no-transcript'),{},lambda d:d.update(transcript_id=None))
    doc=document(studio);job=studio.enqueue(doc['project_id'],'selection_m3',options=options(signals=True,frame_budget=0))
    execute(studio,job);saved=document(studio);take=studio.store.transcript(saved['transcript_id'])
    assert take['words']==[] and take['runtime_receipt']['inference_performed'] is False
    assert saved['selection3']['asr_invoked'] is False and snapshot(studio,doc['project_id'])['stale'] is False


def test_http_boundary_rejects_incomplete_approval_and_preserves_request_id(studio):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from ..api_studio import create_router
    doc=put_report(studio);c=proposed(doc);app=FastAPI();app.include_router(create_router(studio))
    with TestClient(app) as client:
        get=client.get('/api/studio/projects/'+doc['project_id']+'/selection');assert get.status_code==200
        request={'expected_revision':doc['revision'],'analysis_id':doc['selection3']['analysis_id'],'candidate_id':c['candidate_id'],
            'status':'accepted','reviewed':[],'operation_id':identifier('http-m3')}
        denied=client.post('/api/studio/projects/'+doc['project_id']+'/selection/decision',json=request);assert denied.status_code==400
        request['reviewed']=required_review(c);accepted=client.post('/api/studio/projects/'+doc['project_id']+'/selection/decision',json=request);assert accepted.status_code==200
        replay=client.post('/api/studio/projects/'+doc['project_id']+'/selection/decision',json=request);assert replay.json()==accepted.json()


def test_explicit_render_set_excludes_other_clips_without_deleting_edits(studio):
    doc=put_report(studio);c=proposed(doc);change(studio,decision(doc,c));doc=document(studio)
    change(studio,{'op':'manual_clip','start':0.,'end':8.,'title':'Klip manual yang tetap disimpan'})
    before=document(studio);manual=next(v for v in before['clips'].values() if v.get('created_from')!='M3')
    change(studio,{'op':'m3_select_set','analysis_id':before['selection3']['analysis_id'],'candidate_ids':[c['candidate_id']]})
    saved=document(studio);assert len(saved['clips'])==len(before['clips']);assert not saved['clips'][manual['clip_id']]['included']
    assert len(batch7.targets(saved))==2;assert saved['m3_selected_set']['shortfall']==1


def test_render_set_does_not_accept_proposals_implicitly(studio):
    doc=put_report(studio)
    with pytest.raises(ValueError,match='Terima'):change(studio,{'op':'m3_select_set','analysis_id':doc['selection3']['analysis_id']})
    assert document(studio)['clips']=={}
