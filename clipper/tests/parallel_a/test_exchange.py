"""A exchange with actual C0 validators; B production storage remains simulated."""
import copy
from fractions import Fraction
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from clipper import analysis_adapter as adapter
from clipper.analysis_options import AnalysisConfig,DEPENDENCIES,AnalysisCancelled,checkpoint
from clipper.api_analysis import create_router
from clipper.correction_memory import propose_change


def transcript():
    text='trading forex hausd time frame tidak 1.250,50'
    return {'words':[dict(word_id=i,word=t,start=i*.4,end=i*.4+.35,probability=.3 if t=='hausd' else .95)
        for i,t in enumerate(text.split())],'duration':5}


def snapshot(tmp_path):
    return adapter.transcript_snapshot(transcript(),AnalysisConfig(work_dir=str(tmp_path)),source_id='fixture:source',
        transcript_id='asr-take-1',revision=3,input_fingerprint='fixture:input',audio_stream_id='audio:0')


def test_source_words_and_multiword_lineage_are_stable_and_revision_scoped(tmp_path):
    original=transcript();saved=copy.deepcopy(original);cfg=AnalysisConfig(work_dir=str(tmp_path))
    a=snapshot(tmp_path)
    assert original==saved and [w['word'] for w in a['payload']['heard_words']]==[w['word'] for w in original['words']]
    compound=next(t for t in a['payload']['display_tokens'] if t['text']=='timeframe')
    assert compound['origin_word_ids']==[3,4]
    assert any(t['text']=='tidak' for t in a['payload']['display_tokens']) and any(t['text']=='1.250,50' for t in a['payload']['display_tokens'])
    b=adapter.transcript_snapshot(original,cfg,source_id='fixture:source',transcript_id='asr-take-2',revision=3,input_fingerprint='new',audio_stream_id='audio:0')
    assert {t['token_id'] for t in a['payload']['display_tokens']}.isdisjoint(t['token_id'] for t in b['payload']['display_tokens'])
    partial=adapter.transcript_snapshot(original,cfg,source_id='fixture:source',transcript_id='asr-take-1',revision=3,input_fingerprint='p',audio_stream_id='audio:0',clip_span=[1.5,5])
    t=next(t for t in partial['payload']['display_tokens'] if t['text']=='timeframe')
    assert t['requires_alignment']
    with pytest.raises(ValueError,match='melintasi'):adapter.correction_proposal(partial,t['token_id'],'timeframe',expected_revision=19,expected_transcript_revision=3,operation_id='op-12345')


def test_manual_words_survive_fresh_refinement(tmp_path):
    tr=transcript();tr['raw_words']=copy.deepcopy(tr['words']);tr['words'][2].update(word='NamaManual',manually_edited=True)
    out=adapter.transcript_snapshot(tr,AnalysisConfig(work_dir=str(tmp_path)),source_id='fixture:source',transcript_id='t',revision=0,input_fingerprint='f',audio_stream_id='audio:0')
    assert out['payload']['heard_words'][2]['word']=='hausd'
    assert next(t for t in out['payload']['display_tokens'] if 2 in t['origin_word_ids'])['text']=='NamaManual'


def test_project_and_transcript_revisions_are_independent(tmp_path):
    snap=snapshot(tmp_path);token=snap['payload']['display_tokens'][0]
    result=adapter.correction_proposal(snap,token['token_id'],'Trading',expected_revision=29,
        expected_transcript_revision=3,operation_id='operation-29')
    assert result['expected_revision']==29 and result['operations'][0]['transcript_revision']==3
    with pytest.raises(ValueError,match='transkrip usang'):
        adapter.correction_proposal(snap,token['token_id'],'Trading',expected_revision=29,
            expected_transcript_revision=2,operation_id='operation-29')


def test_memory_operations_are_pure_and_can_rename_alias():
    rows=propose_change([],dict(op='alias_upsert',canonical='XAUUSD',alias='hausd',topic='finance'))
    before=copy.deepcopy(rows)
    renamed=propose_change(rows,dict(op='alias_upsert',id=rows[0]['id'],canonical='XAUUSD',alias='xausd',topic='finance',enabled=False))
    assert rows==before and len(renamed)==1 and renamed[0]['alias']=='xausd' and not renamed[0]['enabled']
    with pytest.raises(ValueError):propose_change(rows,dict(op='alias_upsert',canonical='untung',alias='tidak untung'))


def test_media_geometry_and_unknown_schema_are_blocked_without_mutating_input():
    context=adapter.envelope('MediaContext','fixture:source','input',coordinate_space='encoded_pixels',geometry_status='unavailable',display_size=[1080,1920])
    before=copy.deepcopy(context);result=adapter.scene_analysis({'shots':[]},context,input_fingerprint='analysis')
    assert result['state']=='blocked' and context==before
    with pytest.raises(ValueError):adapter.require_v1({**context,'schema_version':2})


def test_caption_exchange_uses_host_mapping_and_retains_all_origins(tmp_path):
    tr=snapshot(tmp_path);cfg=AnalysisConfig(work_dir=str(tmp_path),caption_style='clean')
    render_words=[{**t,'start':t['source_start'],'end':t['source_end']} for t in tr['payload']['display_tokens']]
    timeline=adapter.envelope('EditTimeline','fixture:source','input',revision=8,variant_id='vertical',fps={'numerator':30000,'denominator':1001})
    calls=[]
    def mapper(a,b,fps):
        calls.append((a,b));rate=Fraction(fps['numerator'],fps['denominator']);return round(a*rate),max(round(a*rate)+1,round(b*rate))
    plan=adapter.caption_plan(render_words,cfg,timeline,input_fingerprint='caption',frame_mapper=mapper)
    assert calls and plan['payload']['timeline_revision']==8 and plan['payload']['variant_id']=='vertical'
    assert {i for p in plan['payload']['phrases'] for i in p['origin_word_ids']}==set(range(7))
    assert {i for p in plan['payload']['phrases'] for i in p['token_references']}=={t['token_id'] for t in tr['payload']['display_tokens']}
    assert all(p['start_frame']<p['end_frame'] for p in plan['payload']['phrases'])


def test_c0_revision_service_owns_save_conflict_and_retry(tmp_path):
    revision=5;calls=[];acks={}
    def get_snapshot(target):return {'schema_version':1,'target':target,'revision':revision,'capabilities':{},'data':{}}
    def submit(request):
        nonlocal revision
        calls.append(copy.deepcopy(request));ident=request['operation_id']
        if ident in acks:return acks[ident]
        if request['expected_revision']!=revision:return {'status':'conflict','revision':revision,'conflicts':['token']}
        revision+=1;acks[ident]={'status':'ready','revision':revision};return acks[ident]
    app=FastAPI();app.include_router(create_router(dict(get_snapshot=get_snapshot,submit_changes=submit,run_stage=lambda r:{'status':'queued'})))
    client=TestClient(app);target=dict(project_id='project-stable',clip_id='clip-stable',variant_id='vertical')
    payload={**target,'expected_revision':5,'operation_id':'retry-0001','operations':[dict(op='correct_token',token_id='token-1',before='hausd',after='XAUUSD')]}
    first=client.post('/api/analysis/changes',json=payload);assert first.status_code==200 and first.json()['revision']==6
    assert client.post('/api/analysis/changes',json=payload).json()['revision']==6
    conflict=client.post('/api/analysis/changes',json={**payload,'operation_id':'other-tab-1'})
    assert conflict.status_code==409 and conflict.json()['conflicts']==['token']
    assert calls[0]['clip_id']=='clip-stable' and 'index' not in calls[0]
    missing={k:v for k,v in payload.items() if k!='expected_revision'}
    assert client.post('/api/analysis/changes',json=missing).status_code==400
    assert client.get('/api/analysis/snapshot',params=target).json()['revision']==6


def test_dependencies_include_budget_and_candidate_count_is_unbounded():
    assert 'asr_recheck_windows' in DEPENDENCIES['asr']
    assert 'asset_content_hashes' in DEPENDENCIES['asset_proposals']
    assert adapter.manual_candidate_policy(10001)['allowed']
    with pytest.raises(AnalysisCancelled):checkpoint(lambda:True)


def test_legacy_candidate_is_not_marked_as_new_automatic_ready():
    c=dict(start=0,end=40,title='Sesi lama',intelligence={'status':'ready'})
    out=adapter.candidate_set([c],{},source_id='fixture:source',input_fingerprint='x',legacy=True)
    assert out['payload']['candidates'][0]['status']=='stale' and out['payload']['candidates'][0]['origin']=='legacy'


def test_shared_c0_accepts_a_output_and_a_accepts_b_media(tmp_path):
    from clipper import contracts
    snap=snapshot(tmp_path)
    assert contracts.validate(snap) is snap and snap['state']=='ready'
    heard=snap['payload']['words'][2]
    assert heard['word']=='hausd' and heard['origin_word_ids']==[2]
    assert heard['source_id']=='fixture:source' and heard['transcript_id']=='asr-take-1'
    assert snap['payload']['words']==snap['payload']['heard_words']
    context=contracts.envelope('MediaContext','fixture:source',dict(coordinate_space='canonical_source_pixels',
        geometry_status='ready',display_size=[1920,1080]),'source-fingerprint')
    scene=adapter.scene_analysis({'shots':[]},context,input_fingerprint='scene-fingerprint')
    assert contracts.validate(scene)['state']=='empty'
    assets=adapter.asset_proposal_set({'scenes':[]},source_id='fixture:source',input_fingerprint='assets',cfg=AnalysisConfig(work_dir=str(tmp_path)))
    assert contracts.validate(assets)['payload']['proposals']==[]


def test_c0_analysis_host_mount_keeps_legacy_entrypoint_and_one_prefix():
    from clipper.api_analysis import AnalysisHost,mount
    host=AnalysisHost(snapshot=lambda target:{'schema_version':1,'target':target,'revision':1,'data':{}},
        submit_changes=lambda request:{'status':'ready','revision':2},
        get_words_page=lambda request:{'words':[]},run_stage=lambda request:{'status':'queued'})
    app=FastAPI();mount(app,host,create_router);client=TestClient(app)
    result=client.get('/api/analysis/snapshot',params=dict(project_id='p',clip_id='c',variant_id='v'))
    assert result.status_code==200 and result.json()['revision']==1
    assert client.get('/api/analysis/api/analysis/capabilities').status_code==404
