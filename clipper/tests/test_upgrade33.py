"""Regression fixtures from failed 3.2 reviews and cross-shot subtitles."""
import copy
import json
from dataclasses import replace
from pathlib import Path
import cv2
import numpy as np
import pytest
from clipper import story, illustrations, typography, placement, composition, transcript_correction, library_paths
from clipper.config import Config
from clipper.tests.test_intelligence31 import example
from clipper.tests.test_upgrade32 import words, shot, app_fixture


def row(block):
    return dict(start_segment=0,end_segment=4,title='Jasa sesuai kemampuan',reason='Latihan keterampilan.',
        value=4,opening=4,closure=4,complete=True,ending_evidence=block[-1]['text'],hook_quote='',keywords=['skill'])


@pytest.mark.parametrize('ids',[(7,41),(58,94),(34,78),(0,True),(0,4.2)])
def test_bad_ids_never_poison_cache(tmp_path,monkeypatch,ids):
    c,ws,block,_,cfg=example(tmp_path);path=tmp_path/'reply.json';valid=row(block)
    bad={**valid,'start_segment':ids[0],'end_segment':ids[1]};calls=[]
    monkeypatch.setattr(story,'request',lambda *a,**kw:calls.append(kw) or [bad])
    out=story.validated_response(path,block,ws,cfg,c['end'])
    assert not out[0] and not path.exists() and len(calls)==2
    assert calls[-1]['feedback'][0]['code']=='segment_id'
    monkeypatch.setattr(story,'request',lambda *a,**kw:[valid])
    assert story.validated_response(path,block,ws,cfg,c['end'])[0]
    assert story.validated_response(path,block,ws,cfg,c['end'])[1]
    assert not story.validated_response(path,block,ws,cfg,c['end'],refresh=True)[1]


def test_forced_empty_review_invalidates_cache(tmp_path,monkeypatch):
    c,ws,block,_,cfg=example(tmp_path);path=tmp_path/'reply.json'
    monkeypatch.setattr(story,'request',lambda *a,**k:[row(block)])
    story.validated_response(path,block,ws,cfg,c['end']);assert path.exists()
    monkeypatch.setattr(story,'request',lambda *a,**k:[])
    assert not story.validated_response(path,block,ws,cfg,c['end'],refresh=True)[0]
    assert not path.exists()


@pytest.mark.parametrize('field,value,code',[('value',6,'score_range'),('closure',3.5,'score_range'),('complete',False,'incomplete'),('ending_evidence','semua pasti kaya','ending_quote')])
def test_ground_diagnostics(tmp_path,field,value,code):
    c,ws,block,_,cfg=example(tmp_path);errors=[]
    assert not story.ground([{**row(block),field:value}],block,ws,cfg,c['end'],errors)
    assert errors[0]['code']==code


def test_duration_repair_keeps_topic_grounded(tmp_path,monkeypatch):
    c,ws,block,_,cfg=example(tmp_path);cfg=replace(cfg,min_clip_s=30);calls=[]
    short={**row(block),'end_segment':1,'ending_evidence':block[1]['text']}
    def reply(*a,**kw):
        calls.append(kw);return [row(block) if kw.get('feedback') else short]
    monkeypatch.setattr(story,'request',reply)
    assert story.validated_response(tmp_path/'reply.json',block,ws,cfg,c['end'])[0]
    assert calls[-1]['feedback'][0]['code']=='duration'


def test_unverified_preserve_does_not_veto_broll(tmp_path,monkeypatch):
    c,ws,_,_,cfg=example(tmp_path);cfg=replace(cfg,broll_mode='local');c['intelligence']['status']='needs_review';c['intelligence']['broll']='preserve_speaker'
    calls=[]
    monkeypatch.setattr(illustrations.stock,'local_assets',lambda:[{'path':'local'}])
    monkeypatch.setattr(illustrations,'propose',lambda *a:calls.append(1) or [])
    monkeypatch.setattr(illustrations.editorial,'release',lambda *a:None)
    result=illustrations.prepare(ws,c,cfg)
    assert calls and result['status']=='empty'
    assert illustrations.prepare(ws,c,replace(cfg,source_kind='board'))['status']=='skipped'


@pytest.mark.parametrize('style',['editorial','clean','magazine','narrative','pop','slide','blur','impact'])
def test_phrase_not_split_at_two_frame_cut(style):
    cfg=Config(target_w=1920,target_h=1080,caption_style=style)
    ws=words('Ada materi yang menarik.',step=.4)
    anchors=[dict(time=.016,start=0,end=1/30,position='bottom',panel=None,protected=[]),dict(time=2,start=1/30,end=4,position='bottom',panel=None,protected=[])]
    groups=typography.scene_groups(ws,cfg,anchors)
    ids=[w['word_id'] for g in groups for w in g]
    assert ids==[w['word_id'] for w in ws]
    layout=typography.make_plan(ws,cfg,anchors=anchors)
    assert min(p['end']-p['start'] for p in layout['phrases'])>.2


def test_full_white_slide_requires_writing():
    frame=np.full((360,640,3),255,np.uint8)
    assert composition.material_panel(frame) is None
    for i in range(5):
        cv2.putText(frame,'MATERI TRADING',(30,45+i*55),cv2.FONT_HERSHEY_SIMPLEX,1.0,(0,0,0),2)
    rect=composition.material_panel(frame)
    assert rect and rect[2]*rect[3]>.8*640*360


def test_mixed_portrait_compositions_share_clear_phrase_panel():
    cfg=Config(target_w=1080,target_h=1920,caption_style='magazine')
    first=shot([{'kind':'material','box':[0,0,1920,1080]}]);first.update(start=0,end=.5)
    second=shot([{'kind':'material','box':[0,0,1920,1080]}]);second.update(start=.5,end=4,mode='stream',face_rect=[0,0,700,1080])
    plan={'shots':[first,second],'display_words':words('Ada materi yang penting.')}
    placement.apply(plan,cfg);anchors=placement.caption_anchors(plan,cfg)
    layout=typography.make_plan(plan['display_words'],cfg,anchors=anchors)
    from clipper.qc import inspect_caption_plan
    assert inspect_caption_plan(layout,cfg)['passed']
    assert first['caption_panel']==second['caption_panel']
    assert second['canvas_height']<cfg.target_h


def test_short_insert_does_not_shrink_entire_shot():
    cfg=Config(target_w=1920,target_h=1080)
    s={**shot(),'start':0,'end':60,'source_start':0,'source_end':60,'start_frame':0,'duration_frames':1800}
    p={'fps':30,'shots':[s],'words':[],'broll':[dict(start=20,end=23,duration=3)]}
    placement.protect_broll(p,cfg)
    assert len(p['shots'])==3 and sum(x['duration_frames'] for x in p['shots'])==1800
    assert not p['shots'][0].get('image_height') and not p['shots'][-1].get('image_height')
    assert p['shots'][1]['image_height']==p['broll'][0]['image_height']


def test_preview_keeps_insert_near_end_with_source_offset(tmp_path):
    asset=tmp_path/'a.mp4';asset.write_bytes(b'x')
    scene={'enabled':True,'source_start':9,'source_end':13,'asset':{'path':str(asset)}}
    p={'fps':30,'duration':12,'shots':[dict(start=0,end=12,source_start=10,source_end=22)],'spans':[dict(start=0,end=12,kind='body')],'warnings':[]}
    illustrations.attach(p,{'scenes':[scene]},Config(broll_mode='local',preview_seconds=12))
    assert len(p['broll'])==1 and p['broll'][0]['start']==0 and p['broll'][0]['asset_start']==1


def test_refresh_preserves_manual_words_numbers_and_raw(tmp_path):
    ws=words('Trading emas pair hausd tidak 100.');manual=copy.deepcopy(ws);manual[3]['word']='XAU khusus'
    t={'words':ws,'duration':4};new,edits=transcript_correction.refresh_saved(t,{0:manual},Config(audience='finance'))
    assert new['words'][3]['word']=='XAUUSD' and edits[0][3]['word']=='XAU khusus'
    assert new['raw_words']==ws and new['words'][-1]['word']=='100.'
    assert [(w['start'],w['end']) for w in new['words']]==[(w['start'],w['end']) for w in ws]


def test_legacy_preview_without_fingerprint():
    assert library_paths.LEGACY_PREVIEW.fullmatch('65905f865621-preview-8-r4-v22.mp4')
    assert not library_paths.LEGACY_PREVIEW.fullmatch('65905f865621-01-cerita-r4-v32.mp4')


def test_request_schema_restricts_segment_ids(tmp_path,monkeypatch):
    c,ws,block,_,cfg=example(tmp_path);seen={}
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'response':'{"clips": []}'}
    def post(url,**kw):seen.update(kw['json']);return Response()
    monkeypatch.setattr(story.requests,'post',post)
    story.request(block[2:],cfg,c)
    fields=seen['format']['properties']['clips']['items']['properties']
    assert fields['start_segment']['enum']==[2,3,4] and fields['value']['maximum']==5
    assert fields['intelligence']['properties']['payoff']['properties']['segment_id']['enum']==[2,3,4]
    assert 'START_SECONDS' in seen['prompt']


def test_refresh_endpoint_backs_up_without_asr(tmp_path,monkeypatch):
    app,client,ident,st,job=app_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(app,'enqueue',lambda job_id,action:app.worker(job_id,action))
    st['transcript']['words']=words('Trading emas pair hausd.');st['cfg']=replace(st['cfg'],audience='finance')
    assert client.post('/api/refresh-transcript/'+ident).status_code==200
    assert job['status']=='review' and st['transcript']['words'][-1]['word']=='XAUUSD.'
    assert st['scored'][0]['revision']==1 and st['scored'][0]['intelligence']['status']=='stale'
    assert list((Path(st['cfg'].work_dir)/'session-history').glob('*.json'))
    job['status']='rendering';assert client.post('/api/refresh-transcript/'+ident).status_code==409
