"""Stage 4 invariants: source identity, uncertainty, temporal safety and pins."""
import copy
import json
import math
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from clipper import visual4,composition,media_context
from clipper.config import Config,validate_overrides
from clipper.studio_service import StudioService,identifier
from clipper.project_store import Conflict
from clipper.api_studio import create_router


def samples(two=False, count=12):
    rows=[{'t':i*.5,'faces':[[50+i,40,55,70]]+([[240-i,42,60,75]] if two else []),
           'hist':np.ones((2,2),dtype=np.float32),'area':[0,0,360,240],'texts':[],'ocr':[]} for i in range(count)]
    return visual4.track_faces(rows)


def test_two_faces_keep_identity_despite_detection_order_and_size_changes():
    rows=samples(two=True)
    for i,r in enumerate(rows):r['faces']=list(reversed(r['faces'])) if i%2 else r['faces']
    rows=visual4.track_faces(rows)
    assert all([t['track_id'] for t in r['tracks']]==['face-0001','face-0002'] for r in rows)
    assert visual4.speaker(rows)['selected'] is None


def test_face_is_not_carried_across_a_cut_or_long_absence():
    rows=samples();rows[6]['cut']=True;visual4.track_faces(rows)
    assert rows[6]['tracks'][0]['track_id']!=rows[5]['tracks'][0]['track_id']
    rows=samples();rows[6]['t']=20;visual4.track_faces(rows)
    assert rows[6]['tracks'][0]['track_id']!=rows[5]['tracks'][0]['track_id']


def test_disappearing_face_never_becomes_a_confident_crop():
    rows=samples()
    for row in rows[4:]:row['tracks']=[]
    assert visual4.speaker(rows)['selected'] is None


def test_selected_manual_track_must_still_be_visible():
    rows=samples(two=True)
    assert visual4.speaker(rows,manual='face-0002')['selected']['track_id']=='face-0002'
    assert visual4.speaker(rows,manual='face-9999')['selected'] is None


@pytest.mark.parametrize('winner',[0,1])
def test_active_speaker_is_driven_by_aligned_audio_scores_not_face_area(winner):
    rows=samples(two=True)
    scores=[{'time':r['t'],'track_id':f['track_id'],'score':.92 if i==winner else .12} for r in rows for i,f in enumerate(r['tracks'])]
    selected=visual4.speaker(rows,{'status':'ready','scores':scores})
    assert selected['method']=='talknet'
    assert selected['selected']['track_id']==f'face-{winner+1:04d}'


def test_dense_scores_in_one_second_do_not_claim_whole_shot_coverage():
    rows=samples(two=True)
    scores=[{'time':t,'track_id':f'face-{i+1:04d}','score':.95 if i==0 else .1} for t in np.arange(0,1,.04) for i in range(2)]
    assert visual4.speaker(rows,{'status':'ready','scores':scores})['selected'] is None


def test_uncertain_or_equal_audio_scores_keep_both_guests():
    rows=samples(two=True)
    scores=[{'time':r['t'],'track_id':f['track_id'],'score':.72} for r in rows for f in r['tracks']]
    assert visual4.speaker(rows,{'status':'ready','scores':scores})['selected'] is None


def test_audio_switches_and_end_of_measurement_split_source_groups():
    rows=samples(two=True)
    scores=[{'time':r['t'],'track_id':f['track_id'],'score':.9 if (i==0)==(r['t']<3) else .1} for r in rows for i,f in enumerate(r['tracks'])]
    active={'status':'ready','scores':scores,'audio_windows':[{'start':0,'end':3},{'start':3,'end':5}]}
    groups,edges=visual4.split_groups([rows],[0,6],Config(),active)
    assert 3 in edges and 5 in edges
    assert visual4.speaker(groups[0],active)['selected']['track_id']=='face-0001'
    assert visual4.speaker(groups[1],active)['selected']['track_id']=='face-0002'
    assert visual4.speaker(groups[2],active)['selected'] is None


def test_repeated_ocr_uses_minimum_confidence_and_union_of_motion():
    rows=[{'t':0,'ocr':[{'text':'2 juta','box':[10,10,50,20],'confidence':.94}]},
          {'t':1,'ocr':[{'text':'2 JUTA','box':[15,12,50,20],'confidence':.83}]},
          {'t':1.5,'ocr':[{'text':'noise','box':[30,20,40,10],'confidence':.45}]}]
    result=visual4.merge_ocr(rows)
    assert len(result)==1 and result[0]['confirmed_repeated']
    assert result[0]['confidence']==.83 and result[0]['box']==[10,10,55,22]


def test_ocr_not_merged_across_different_text_or_a_long_gap():
    rows=[{'t':t,'ocr':[{'text':text,'box':[0,0,50,20],'confidence':.92}]} for t,text in [(0,'Rp 2 juta'),(1,'Rp 3 juta'),(20,'Rp 2 juta')]]
    assert len(visual4.merge_ocr(rows))==3


@pytest.mark.parametrize('box',[[0,0,101,2],[98,0,3,10],[0,0,0,10],[0,0,float('nan'),10]])
def test_visual_controls_reject_unsafe_coordinates(box):
    with pytest.raises(ValueError):visual4.validate_controls({'pins':[{'box':box}]},20)


@pytest.mark.parametrize('value',[{'pins':[{'box':[0,0,50,50],'start':10,'end':9}]},{'speaker_track':'../../other'},{'sam_enabled':'yes'},{'unknown':1}])
def test_visual_controls_reject_bad_ranges_and_unknown_fields(value):
    with pytest.raises(ValueError):visual4.validate_controls(value,20)


def test_pins_split_layout_at_exact_source_times():
    cfg=Config(visual_overrides=visual4.validate_controls({'pins':[{'start':1.25,'end':4.5,'box':[10,10,60,70]}]},6))
    _,boundaries=visual4.split_groups([samples()],[0,6],cfg,{'status':'disabled'})
    assert boundaries==[0,1.25,4.5,6]


def test_analysis_cache_is_shared_by_output_ratios_and_checks_source_content(tmp_path):
    path=tmp_path/'source';path.write_bytes(b'source1')
    cfg=Config(work_dir=str(tmp_path),ocr_enabled=False);plan={'spans':[{'source_start':0,'source_end':2}]};info={'duration':2,'width':360,'height':240}
    calls=[]
    def sampler(t):
        calls.append(t);return {'t':t,'faces':[],'hist':np.ones((2,2),dtype=np.float32),'area':[0,0,360,240],'texts':[]}
    _,a=visual4.collect(path,plan,cfg,info,sampler)
    _,b=visual4.collect(path,plan,replace(cfg,target_w=1920,target_h=1080),info,sampler)
    assert a['key']==b['key'] and b['cache_reused']
    assert calls[-1]>=1.9
    path.write_bytes(b'source2');_,c=visual4.collect(path,plan,cfg,info,sampler)
    assert a['key']!=c['key']


def test_optional_backend_requires_its_own_receipt_test_and_runtime(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPPER_RUNTIME_DIR',str(tmp_path))
    folder=tmp_path/'generations'/'one';folder.mkdir(parents=True)
    active=tmp_path/'components'/'talknet'/'active.json';active.parent.mkdir(parents=True);active.write_text(json.dumps({'generation':'one'}))
    (folder/'receipt.json').write_text(json.dumps({'installed':True,'test':{'passed':True,'level':'import'}}))
    assert visual4.component_runtime('talknet',Config()) is None
    assert visual4.backend('talknet',{},Config(),tmp_path)['status']=='unavailable'


def test_manual_subtitle_position_is_never_moved_by_safety_pass():
    cfg=Config(caption_position='left');plan={'words':[],'shots':[{'caption_panel':[1,2,3,4]}]}
    before=copy.deepcopy(plan);visual4.caption_envelopes(plan,cfg);assert plan==before


@pytest.mark.parametrize('kind,panel,faces,texts',[('board',[20,0,200,240],1,0),('podcast',None,2,0),('speaker',None,1,0),('screen',None,0,5),('unknown',None,0,0)])
def test_scene_kind_has_a_reason_and_confidence(kind,panel,faces,texts):
    group=[{'panel':panel,'tracks':[{}]*faces,'texts':[[]]*texts}]*3
    result=visual4.classify(group)
    assert result['kind']==kind and result['reason'] and 0<=result['confidence']<=1


@pytest.fixture
def project(tmp_path,monkeypatch):
    monkeypatch.setattr(media_context,'inspect',lambda _: {'duration':20.,'display_size':[640,360], 'audio_tracks':[{'index':1,'title':'Suara','language':'id'}]})
    source=tmp_path/'source.mp4';source.write_bytes(b'regression-source')
    service=StudioService(tmp_path,Config(),autostart=False)
    doc=service.create(source)
    ws=[{'word_id':i,'word':w,'start':i,'end':i+.8} for i,w in enumerate('Simpan area ini dengan benar'.split())]
    tid=service.store.save_transcript(doc['project_id'],{'words':ws,'raw_words':ws,'duration':20})
    def seed(d):d['transcript_id']=tid;service.add_candidates(d,[{'start':0,'end':10,'title':'Tes','keywords':[]}])
    service.store.mutate(doc['project_id'],0,'seed-visual4',{},seed);doc=service.store.get(doc['project_id'])
    return service,doc,next(iter(doc['clips']))


def test_saved_area_is_variant_scoped_and_survives_a_new_visual_report(project):
    service,doc,cid=project
    before=service.dependency(doc,cid,'portrait')
    request={'project_id':doc['project_id'],'clip_id':cid,'variant_id':'portrait','expected_revision':doc['revision'],'operation_id':identifier('op'),
             'operations':[{'op':'visual_controls','values':{'pins':[{'box':[10,5,70,90],'start':0,'end':10}]}}]}
    service.changes(request);saved=service.store.get(doc['project_id'])
    assert service.config(saved,cid,'portrait').visual_overrides['pins'][0]['box']==[10,5,70,90]
    assert service.config(saved,cid,'landscape').visual_overrides=={}
    assert service.dependency(saved,cid,'portrait')!=before
    pin=copy.deepcopy(saved['clips'][cid]['variants']['portrait']['visual_controls'])
    service.store.mutate(saved['project_id'],saved['revision'],'report-visual4',{},lambda d:d['clips'][cid]['variants']['portrait'].update(visual_report={'shots':[]}))
    assert service.store.get(doc['project_id'])['clips'][cid]['variants']['portrait']['visual_controls']==pin
    with pytest.raises(Conflict):service.changes({**request,'operation_id':identifier('stale')})


def test_visual_job_requires_a_clip_and_is_queued_without_asr(project):
    service,doc,cid=project
    with pytest.raises(ValueError):service.enqueue(doc['project_id'],'visual_review',None,expected_revision=doc['revision'])
    job=service.enqueue(doc['project_id'],'visual_review',cid,'portrait',doc['revision'])
    assert job['kind']=='visual_review' and job['status']=='queued'


def test_visual_control_failure_is_atomic(project):
    service,doc,cid=project
    with pytest.raises(ValueError):service.changes({'project_id':doc['project_id'],'clip_id':cid,'variant_id':'portrait','expected_revision':doc['revision'],
       'operation_id':identifier('bad'),'operations':[{'op':'visual_controls','values':{'speaker_track':'face-0001'}},{'op':'visual_controls','values':{'pins':[{'box':[90,90,40,40]}]}}]})
    assert service.store.get(doc['project_id'])['revision']==doc['revision']


def test_pyav_recipe_keeps_known_compatible_decoder():
    from clipper.runtime.catalog import get
    assert 'av==18.0.0' in get('faster-whisper')['packages']
    assert 'faster-whisper==1.2.1' in get('faster-whisper')['packages']


def test_optional_runtime_corrupt_metadata_never_stops_core_layout(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPPER_RUNTIME_DIR',str(tmp_path))
    p=tmp_path/'components/sam2/active.json';p.parent.mkdir(parents=True)
    for text in ['{broken',json.dumps({'generation':'../../outside'}),json.dumps(['bad'])]:
        p.write_text(text)
        assert visual4.component_runtime('sam2',Config()) is None
        assert visual4.runtime_signature()[0][1]=='invalid_metadata'


def test_ocr_corrections_follow_same_source_region_after_pin_splits(tmp_path,monkeypatch):
    source=tmp_path/'source.mp4';source.write_bytes(b'OCR fixture')
    monkeypatch.setattr(visual4,'backend',lambda *args:{'status':'unavailable'})
    cfg=Config(work_dir=str(tmp_path));plan={'spans':[{'source_start':0,'source_end':4}]};info={'width':640,'height':360,'duration':4}
    def frame(t):return {'t':t,'faces':[],'hist':np.ones((2,2),dtype=np.float32),'texts':[],'area':[0,0,640,360],
                         'ocr':[{'text':'Rp 2 juta','confidence':.91,'box':[100,40,130,30]}]}
    rows,_=visual4.collect(source,plan,cfg,info,frame)
    original=visual4.merge_ocr(rows)[0]['id'];cfg=replace(cfg,visual_overrides={'ocr_edits':{original:'Rp 2,5 juta'}})
    before=visual4.describe(source,rows[:4],cfg,info,{'status':'disabled'})
    after=visual4.describe(source,rows[4:],cfg,info,{'status':'disabled'})
    assert before['ocr'][0]['id']==after['ocr'][0]['id']==original
    assert before['ocr'][0]['text']==after['ocr'][0]['text']=='Rp 2,5 juta'


def test_visual_cache_reacts_to_new_source_evidence(tmp_path,monkeypatch):
    source=tmp_path/'source';source.write_bytes(b'fixture')
    cfg=Config(work_dir=str(tmp_path),ocr_enabled=False);info={'duration':1,'width':640,'height':360};plan={'spans':[{'source_start':0,'source_end':1}]}
    def frame(t):return {'t':t,'faces':[],'hist':None,'texts':[],'area':[0,0,640,360]}
    _,before=visual4.collect(source,plan,cfg,info,frame)
    (tmp_path/'source-evidence.json').write_text('{"frames": []}')
    _,after=visual4.collect(source,plan,cfg,info,frame)
    assert before['key']!=after['key'] and not after['cache_reused']


def test_pin_cannot_leak_past_its_exact_end_when_last_sample_is_near_boundary():
    rows=samples(count=4);cfg=Config(visual_overrides={'pins':[{'start':0,'end':1.75,'box':[0,0,50,80],'kind':'crop'}]})
    result=visual4.describe('unused',rows,cfg,{'width':360,'height':240},{'status':'disabled'},source_bounds=(1.75,2))
    assert result['pins']==[]


@pytest.mark.parametrize('controls',[{'sam_time':float('nan')},{'sam_time':20},{'sam_span':[0,7]},
    {'sam_span':[2,3],'sam_time':1},{'sam_span':[3,2]}])
def test_sam_prompts_and_budget_are_validated(controls):
    with pytest.raises(ValueError):visual4.validate_controls(controls,20)


def test_sam_uses_selected_source_shot_not_always_the_first(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(visual4,'backend',lambda key,r,*args:calls.append(r) or {'status':'ready'})
    monkeypatch.setattr(visual4.cv2,'VideoCapture',lambda *a:SimpleNamespace(set=lambda *a:None,read=lambda :(False,None),release=lambda :None))
    shots=[{'source_start':a,'source_end':b,'start':a,'end':b,'visual':{'frame_times':[a+.2]}} for a,b in [(0,4),(4,8)]]
    cfg=Config(work_dir=str(tmp_path),visual_overrides={'sam_enabled':True,'sam_time':5,'sam_span':[4,7],'sam_box':[10,10,50,70]})
    result=visual4.report({'shots':shots,'source':{'width':640,'height':360}},'source',cfg)
    assert result['shots'][0]['mask']['status']=='disabled'
    assert result['shots'][1]['mask']['status']=='ready'
    assert calls[0]['time']==5 and calls[0]['span']==[4,7] and calls[0]['box']==[64,36,320,252]


def test_visual_api_checks_revision_and_separates_variants(project):
    service,doc,cid=project;app=FastAPI();app.include_router(create_router(service));client=TestClient(app)
    request={'project_id':doc['project_id'],'clip_id':cid,'variant_id':'landscape','expected_revision':doc['revision'],
             'operation_id':identifier('api-pin'),'operations':[{'op':'visual_controls','values':{'protected':[{'start':1,'end':9,'box':[50,10,45,80]}]}}]}
    response=client.post('/api/studio/changes',json=request);assert response.status_code==200,response.text
    request['operation_id']=identifier('stale-pin');assert client.post('/api/studio/changes',json=request).status_code==409
    saved=service.store.get(doc['project_id'])
    assert service.variant(saved,cid,'portrait').get('visual_controls') is None
    assert service.variant(saved,cid,'landscape')['visual_controls']['protected'][0]['box']==[50,10,45,80]
    queued=client.post(f"/api/studio/projects/{doc['project_id']}/jobs",json={'kind':'visual_review','clip_id':cid,'variant_id':'landscape','expected_revision':saved['revision']})
    assert queued.status_code==200 and service.queue.list(doc['project_id'])[0]['kind']=='visual_review'


def test_sam_sequence_maps_source_times_and_saves_masks_without_neural_claim(tmp_path,monkeypatch):
    from clipper.visual_worker import sam_sequence
    from contextlib import nullcontext
    import sys
    # Predictor outputs are deliberate fixtures, not scores from actual weights.
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(inference_mode=nullcontext))
    monkeypatch.setattr(visual4.cv2,'VideoCapture',lambda *a:SimpleNamespace(set=lambda *a:None,
        read=lambda :(True,np.zeros((200,400,3),dtype=np.uint8)),release=lambda :None))
    class Logits:
        def __getitem__(self,index):return self
        def detach(self):return self
        def cpu(self):return self
        def numpy(self):return np.ones((1,200,400),dtype=np.float32)
    class Predictor:
        def init_state(self,video_path,**options):
            self.count=len(list(Path(video_path).glob('*.jpg')));return {}
        def add_new_points_or_box(self,state,frame_idx,obj_id,box):self.prompt=frame_idx;self.box=box.tolist()
        def propagate_in_video(self,state,start_frame_idx,reverse=False):
            for i in (range(start_frame_idx,-1,-1) if reverse else range(start_frame_idx,self.count)):
                yield i,[1],Logits()
    predictor=Predictor();r=sam_sequence({'source':'unused','source_content_id':'sha256:fixture','span':[10,11],'time':10.4,'box':[10,20,80,100]},predictor,tmp_path)
    assert r['scope']=='selected_range_sampled' and r['fps']==5 and len(r['frames'])==5
    assert predictor.prompt==2 and predictor.box==[10,20,90,120]
    assert r['frames'][0]['time']==10 and r['frames'][-1]['time']==10.8
    assert all(Path(p).is_file() for p in r['artifacts'])
    assert not list(tmp_path.glob('sam-frames-*'))


def test_renewed_calibration_refreshes_selected_profile_not_project_override(tmp_path,monkeypatch):
    from clipper.runtime import tasks
    from clipper.runtime.state import read,write
    from contextlib import nullcontext
    import subprocess
    runtime=tmp_path/'runtime';runtime.mkdir()
    write(runtime/'selected-profile.json',{'name':'balanced','device':'cpu'})
    manager=SimpleNamespace(root=runtime,update=lambda *a,**k:None,canceled=lambda _:False,
        active=lambda _: {'test':{'passed':True,'level':'sample','device':'cuda'}},snapshot=lambda :{'components':[]})
    monkeypatch.setattr(tasks,'GPULease',lambda *a,**k:nullcontext())
    monkeypatch.setattr(tasks,'GPUMonitor',lambda :SimpleNamespace(__enter__=lambda s:s,__exit__=lambda *a:None))
    class Monitor:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def result(self):return {}
    monkeypatch.setattr(tasks,'GPUMonitor',Monitor)
    monkeypatch.setattr(tasks,'gpu_snapshot',lambda :[])
    def encode(cmd,**options):Path(cmd[-1]).write_bytes(b'encoded-fixture');return subprocess.CompletedProcess(cmd,0,'','')
    monkeypatch.setattr(tasks.subprocess,'run',encode)
    tasks.calibrate(manager,{'id':'test'})
    assert read(runtime/'selected-profile.json')['device']=='cuda'
    assert read(runtime/'selected-profile.json')['batch_size']==1
    project_config=Config(whisper_device='cpu')
    assert project_config.whisper_device=='cpu'


def test_word_crossing_adjacent_body_spans_is_displayed_once():
    from clipper.editplan import build
    cfg=Config(trim_silence=False)
    words=[{'word_id':1,'word':'dengan','start':5.7,'end':6.19},{'word_id':2,'word':'stop','start':6.23,'end':6.72}]
    plan=build(words,{'start':0,'end':14,'title':'Tes','manual_keep_spans':[[0,6],[6,14]]},cfg)
    assert [w['word'] for w in plan['words']]==['dengan','stop']
    assert plan['words'][0]['start']==pytest.approx(5.7) and plan['words'][0]['end']==pytest.approx(6.19)
    assert len(plan['spans'])==2


def test_actual_repeated_utterances_are_not_deduplicated():
    from clipper.editplan import build
    words=[{'word_id':1,'word':'bisa','start':1,'end':2},{'word_id':2,'word':'bisa','start':2,'end':3}]
    plan=build(words,{'start':0,'end':4,'title':'Tes','manual_keep_spans':[[0,2],[2,4]]},Config(trim_silence=False))
    assert len(plan['words'])==2


def test_manual_speaker_id_is_not_reused_on_a_different_observation_set():
    cfg=Config(visual_overrides={'speaker_track':'face-0002','speaker_evidence':'a'*64})
    rows=samples(two=True);info={'width':360,'height':240}
    same=visual4.describe('unused',rows,cfg,info,{'status':'disabled'},observation_key='a'*64)
    changed=visual4.describe('unused',rows,cfg,info,{'status':'disabled'},observation_key='b'*64)
    assert same['speaker']['selected']['track_id']=='face-0002'
    assert changed['speaker']['selected'] is None and changed['speaker']['method']=='preserve_all'
