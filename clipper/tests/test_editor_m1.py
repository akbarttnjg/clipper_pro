"""M1 contracts tested through actual SQLite, HTTP boundary and FFmpeg.

Synthetic media is deliberate; it does not stand in for the user's Windows/GPU
or a native CapCut import. Tests assert effects and failure recovery, not counts.
"""
import copy
import json
import math
import shutil
import subprocess
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from clipper import editor_contract as ec, editor_service as editor
from clipper.config import Config
from clipper.dependency_cache import content_id
from clipper.project_store import Conflict
from clipper.studio_service import StudioService, identifier


@pytest.fixture
def studio(tmp_path):
    svc=StudioService(tmp_path,Config(work_dir='work',out_dir='clips',visual_enabled=False,
        align_selected_clips=False,use_nvenc=False),autostart=False)
    source=tmp_path/'source.mp4';source.write_bytes(b'contract fixture, not decoded as video')
    svc.store.create({'name':'M1 full','settings':asdict(svc.base),
        'source':{'path':str(source),'source_id':content_id(source),'info':{'duration':20.,'audio_tracks':[{'index':1}],'display_size':[320,180]}},
        'clips':{},'aliases':[],'shared_corrections':{},'clip_corrections':{},'transcript_revision':0,'exports':[]},'editor-case')
    words=[{'word_id':i,'word':text,'start':float(i),'end':i+.8,'probability':None} for i,text in enumerate(['model','tidak','5','persen','Andi','CAFÉ','literal_%','utuh'])]
    take=svc.store.save_transcript('editor-case',{'words':words,'raw_words':words,'duration':20.})
    def seed(doc):
        doc['transcript_id']=take
        svc.add_candidates(doc,[{'start':0.,'end':10.,'title':'A','keywords':[]},{'start':1.,'end':11.,'title':'B','keywords':[]}])
    svc.store.mutate('editor-case',0,'seed-full-01',{},seed)
    yield svc
    svc.queue.close()


def document(svc):return svc.store.get('editor-case')
def first(svc):return next(iter(document(svc)['clips']))
def request(svc,ops,cid=None,vid='portrait',revision=None):
    return {'project_id':'editor-case','clip_id':cid or first(svc),'variant_id':vid,
        'expected_revision':document(svc)['revision'] if revision is None else revision,'operation_id':identifier('full-m1'),'operations':ops}
def edit(svc,ops,**kwargs):return svc.changes(request(svc,ops,**kwargs))
def segments(start=0,end=4,**extra):
    return ec.validate_segments([{'id':'body','start':start,'end':end,**extra}],{'start':0.,'end':10.})


@pytest.mark.parametrize('fps',[15,24,25,30,60])
@pytest.mark.parametrize('speed',[.25,.5,.8,1.,1.5,2.,4.])
def test_clock_frame_grid_and_source_output_inverse(fps,speed):
    rows=segments(speed=speed);clock=ec.build_clock(rows,fps)
    assert clock['duration_frames']==round(4/speed*fps)
    for source in (.1,1.,2.,3.9):
        output=ec.source_to_output(clock,source)[0]
        assert ec.output_to_source(clock,output)['source_time']==pytest.approx(source,abs=1e-6)
    assert ec.output_to_source(clock,clock['duration']) is None
    assert ec.source_to_output(clock,4.)==[]


@pytest.mark.parametrize('bad',[True,False,0,.1,5,float('nan'),float('inf'),{'numerator':1,'denominator':0},{'numerator':True,'denominator':1}])
def test_invalid_speed_is_rejected(bad):
    with pytest.raises((ValueError,TypeError)):segments(speed=bad)


def test_reverse_freeze_reorder_remap_preserves_origin_and_alignment():
    rows=ec.validate_segments([{'id':'r','start':1,'end':3,'reverse':True},{'id':'freeze','start':0,'end':.1,'kind':'freeze','freeze_duration':1},
        {'id':'again','start':1,'end':3}],{'start':0,'end':4})
    clock=ec.build_clock(rows,30)
    words=[{'word_id':7,'word':'dua kata','start':1.,'end':3.,'source_word_ids':[7,8],
        'aligned_words':[{'word':'dua','start':1.,'end':2.},{'word':'kata','start':2.,'end':3.}]}]
    before=copy.deepcopy(words);mapped=ec.remap_words(words,clock,[7])
    assert words==before
    assert len(mapped)==2 and len({w['word_id'] for w in mapped})==2
    assert mapped[0]['caption_hidden'] and mapped[1]['caption_hidden']
    assert mapped[1]['start']==3 and mapped[1]['end']==5
    assert mapped[1]['aligned_words'][0]['start']==3
    assert ec.output_to_source(clock,0)['source_time']<3
    assert ec.output_to_source(clock,2.5)['source_time']==0


def test_ramp_has_same_clock_for_audio_captions_and_ratios():
    rows=segments(speed_curve=[{'offset':0,'speed':.5},{'offset':4,'speed':2.}])
    clock=ec.build_clock(rows,30)
    assert len(clock['slices'])>2
    assert all(a['output_end_frame']==b['output_start_frame'] for a,b in zip(clock['slices'],clock['slices'][1:]))
    words=[{'word_id':1,'word':'utuh','start':0,'end':4,'aligned_words':[{'word':'utuh','start':0,'end':4}]}]
    mapped=ec.remap_words(words,clock)
    assert len(mapped)==1
    assert mapped[0]['end']==pytest.approx(clock['duration'])
    assert len(mapped[0]['aligned_words'])==1
    assert mapped[0]['aligned_words'][0]['end']==pytest.approx(clock['duration'])


@pytest.mark.parametrize('easing',ec.EASINGS)
@pytest.mark.parametrize('attribute',['scale','x','y','opacity'])
def test_curve_easing_and_limits(easing,attribute):
    lo,hi=ec.CURVE_ATTRIBUTES[attribute]
    rows=ec.validate_curve(attribute,[{'time':0,'value':lo,'easing':easing},{'time':2,'value':hi}],3)
    assert ec.sample_curve(rows,-1,0)==lo
    assert ec.sample_curve(rows,ec.tick(2),0)==hi
    assert lo<=ec.sample_curve(rows,ec.tick(1),0)<=hi
    assert 'nan' not in ec.ffmpeg_curve(rows,0)


@pytest.mark.parametrize('points',[[{'time':0,'value':1},{'time':0,'value':2}],
    [{'time':4,'value':1}],[{'time':-1,'value':1}],[{'time':0,'value':float('nan')}],
    [{'time':0,'value':True}],[{'time':0,'value':1,'easing':'execute(code)'}]])
def test_curve_rejects_invalid_data(points):
    with pytest.raises((ValueError,TypeError)):ec.validate_curve('scale',points,3)


def test_diff_is_read_only_and_uses_real_validators(studio):
    before=document(studio);cid=first(studio)
    result=studio.changes(request(studio,[{'op':'profile','profile_id':'education'}]),preview_only=True)
    assert result['status']=='preview' and result['changes']
    assert document(studio)==before
    assert len(studio.store.history('editor-case'))==1
    with pytest.raises(ValueError):studio.changes(request(studio,[{'op':'editor_segments','segments':[]}]),preview_only=True)
    assert document(studio)==before


@pytest.mark.parametrize('profile',ec.PROFILES)
def test_profiles_are_effective_and_retain_manual_fields(studio,profile):
    edit(studio,[{'op':'settings','values':{'accent_hex':'#00FF00'}}])
    edit(studio,[{'op':'profile','profile_id':profile}])
    doc=document(studio);cid=first(studio);variant=doc['clips'][cid]['variants']['portrait']
    assert studio.config(doc,cid,'portrait').accent_hex=='#00FF00'
    assert variant['override_keys']==['accent_hex']
    assert editor.state(studio,doc,cid,'portrait')['fields']['accent_hex']['manual']
    if profile=='education':
        cfg=studio.config(doc,cid,'portrait')
        assert not cfg.cold_open and not cfg.title_card and not cfg.punch_zoom and cfg.caption_position=='left'


def test_sparse_override_parent_reset_brand_and_profile(studio):
    cid=first(studio)
    edit(studio,[{'op':'profile','profile_id':'education'}])
    kit=studio.workspace.save_kit({'name':'M1 kit','settings':{'accent_hex':'#AAEE00','caption_template_policy':'manual','font_main':'montserrat','motion_intensity':'calm'}})
    edit(studio,[{'op':'brand_apply','kit_id':kit['id'],'kit_revision':kit['revision']}])
    edit(studio,[{'op':'settings','values':{'accent_hex':'#00FF00'}}])
    before=asdict(studio.config(document(studio),cid,'portrait'))
    edit(studio,[{'op':'inherit_field','keys':['accent_hex']}])
    after=asdict(studio.config(document(studio),cid,'portrait'))
    assert after['accent_hex']=='#AAEE00'
    assert {k for k in before if before[k]!=after[k]}=={'accent_hex'}
    state=editor.state(studio,document(studio),cid,'portrait')
    assert state['fields']['accent_hex']['origin']['scope']=='brand'
    assert state['fields']['caption_template_policy']['value']=='manual'


def test_copy_color_does_not_copy_other_attributes_or_excluded_clip(studio):
    cid=first(studio);other=list(document(studio)['clips'])[1]
    edit(studio,[{'op':'settings','values':{'accent_hex':'#00FF00','font_main':'montserrat'}}])
    doc=document(studio);clipboard=editor.copy_attributes(studio,doc,cid,'portrait',list(editor.ATTRIBUTE_GROUPS['warna']))
    before=asdict(studio.config(doc,cid,'landscape'))
    edit(studio,[{'op':'paste_attributes','clipboard':clipboard,'keys':['accent_hex'],'preserve_manual':False,
        'targets':[{'clip_id':cid,'variant_id':'landscape'}]}])
    after=asdict(studio.config(document(studio),cid,'landscape'))
    assert {k for k in before if before[k]!=after[k]}=={'accent_hex'}
    edit(studio,[{'op':'include_clip','clip_id':other,'included':False}])
    with pytest.raises(ValueError):edit(studio,[{'op':'paste_attributes','clipboard':clipboard,'keys':['accent_hex'],
        'targets':[{'clip_id':other,'variant_id':'landscape'}]}])


def test_temporal_edit_shared_ratios_split_reorder_undo_redo(studio):
    cid=first(studio);original=document(studio)
    result=edit(studio,[{'op':'editor_segments','segments':[{'id':'one','start':0,'end':4},{'id':'two','start':6,'end':8}]}])
    doc=document(studio)
    assert doc['clips'][cid]['variants']['portrait']['editor']['segments']==doc['clips'][cid]['variants']['landscape']['editor']['segments']
    assert editor.state(studio,doc,cid,'portrait')['clock']['digest']==editor.state(studio,doc,cid,'landscape')['clock']['digest']
    edit(studio,[{'op':'segment_edit','segment_id':'one','action':'split','source_time':2.}])
    rows=document(studio)['clips'][cid]['variants']['portrait']['editor']['segments']
    assert len(rows)==3
    edit(studio,[{'op':'segment_edit','action':'reorder','order':[r['id'] for r in reversed(rows)]}])
    revision=document(studio)['revision'];undone=studio.store.undo('editor-case',revision,identifier('undo'),revision)
    assert document(studio)['clips'][cid]['variants']['portrait']['editor']['segments']==rows
    studio.store.redo('editor-case',undone['revision'],identifier('redo'),undone['revision'])
    assert document(studio)['clips'][cid]['variants']['portrait']['editor']['segments']==list(reversed(rows))
    assert studio.store.transcript(document(studio)['transcript_id'])['raw_words'][1]['word']=='tidak'


def test_cut_speech_and_hide_caption_are_distinct(studio):
    doc=document(studio);cid=first(studio);take=doc['transcript_id']
    edit(studio,[{'op':'caption_visibility','origin_word_ids':[1],'hidden':True,'transcript_id':take}])
    state=editor.state(studio,document(studio),cid,'portrait')
    assert state['clock']['duration']==10 and state['hidden_caption_word_ids']==[1]
    edit(studio,[{'op':'cut_speech','origin_word_ids':[1],'transcript_id':take,'transcript_revision':doc['transcript_revision']}])
    state=editor.state(studio,document(studio),cid,'portrait')
    assert state['clock']['duration']==pytest.approx(9.2)
    assert studio.store.transcript(take)['raw_words'][1]['word']=='tidak'


def test_track_lock_rejects_edits_and_solo_disables_other_tracks(studio):
    edit(studio,[{'op':'track','track':'captions','values':{'locked':True}}])
    before=document(studio)
    with pytest.raises(ValueError):edit(studio,[{'op':'settings','values':{'accent_hex':'#00FF00'}}])
    assert document(studio)==before
    edit(studio,[{'op':'track','track':'captions','values':{'locked':False,'solo':True}}])
    tracks=editor.state(studio,document(studio),first(studio),'portrait')['tracks']
    assert tracks['captions']['enabled'] and not tracks['voice']['enabled'] and not tracks['video']['enabled']


def test_draft_snapshot_immutable_commit_idempotence_and_conflict(studio):
    original=document(studio);req=request(studio,[{'op':'settings','values':{'accent_hex':'#00FF00'}}])
    draft=editor.make_draft(studio,req)
    assert document(studio)==original
    assert draft['document']['clips'][first(studio)]['variants']['portrait']['settings']['accent_hex']=='#00FF00'
    operation=identifier('commit')
    saved=editor.commit_draft(studio,'editor-case',draft['id'],original['revision'],operation)
    with pytest.raises(Conflict):editor.commit_draft(studio,'editor-case',draft['id'],original['revision'],identifier('wrong'))
    # Regular command replay returns the original response without another revision.
    assert studio.changes({**req,'operation_id':operation})==saved
    assert document(studio)['revision']==saved['revision']


def test_disjoint_draft_rebase_and_overlapping_conflict(studio):
    draft=editor.make_draft(studio,request(studio,[{'op':'rename','name':'Draft title'}]))
    edit(studio,[{'op':'settings','values':{'accent_hex':'#00FF00'}}])
    editor.commit_draft(studio,'editor-case',draft['id'],document(studio)['revision'],identifier('rebase'),rebase=True)
    assert document(studio)['name']=='Draft title'
    draft=editor.make_draft(studio,request(studio,[{'op':'rename','name':'Second title'}]))
    edit(studio,[{'op':'rename','name':'Other tab'}])
    with pytest.raises(Conflict) as exc:editor.commit_draft(studio,'editor-case',draft['id'],document(studio)['revision'],identifier('collision'),rebase=True)
    assert ['name'] in exc.value.paths
    assert document(studio)['name']=='Other tab'


def test_history_snapshot_actor_and_comments_revision(studio):
    original=document(studio)
    edit(studio,[{'op':'editor_comment','text':'Periksa angka','source_tick':ec.tick(2)}])
    doc=document(studio);comment=next(iter(doc['editor_comments']))
    assert studio.store.revision_document('editor-case',original['revision'])['name']==original['name']
    assert studio.store.history('editor-case')[0]['actor']=='pengguna_lokal'
    edit(studio,[{'op':'rename','name':'Next revision'}])
    with pytest.raises(ValueError):edit(studio,[{'op':'editor_comment','action':'resolve','comment_id':comment}])
    edit(studio,[{'op':'editor_comment','action':'resolve','comment_id':comment,'review_stale':True}])
    assert document(studio)['editor_comments'][comment]['resolved']


def test_replace_proposal_effective_scope_and_fact_review(studio):
    doc=document(studio);cid=first(studio)
    edit(studio,[{'op':'correct_word','word_id':0,'after':'modal','scope':'clip','transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision']}])
    doc=document(studio)
    proposal=editor.replace_proposal(studio,doc,{'query':'modal','replacement':'kapital','scope':'clip','clip_id':cid})
    assert proposal['count']==1 and not proposal['audio_changed']
    assert editor.replace_proposal(studio,doc,{'query':'model','replacement':'kapital','scope':'clip','clip_id':cid})['count']==0
    risk=editor.replace_proposal(studio,doc,{'query':'5','replacement':'6','scope':'clip','clip_id':cid})
    assert risk['reviews'][0]['requires_confirmation']
    with pytest.raises(ValueError):edit(studio,risk['operations'])


def test_legacy_draft_registry_includes_camera_audio_style_word_and_bounds(studio):
    from clipper.editor_drafts import request as adapter
    doc=document(studio);cid=first(studio);base='editor-case|'+cid+'|portrait|'
    stores={'clipper4-drafts':[[base+'__baseRevision',doc['revision']],[base+'word:0','modal'],[base+'music_db','-30'],[base+'bound-end','9']],
        'clipper5-style|editor-case|'+cid+'|portrait':{'revision':doc['revision'],'values':{'style_preset':'rapi'}},
        'clipper4-visual-fields|editor-case|'+cid+'|portrait':{'revision':doc['revision'],'values':{'visual_active_speaker':'off'}}}
    req=adapter(studio,doc,{'stores':stores,'operation_id':identifier('registry')})
    assert len(req['operations'])==5
    result=studio.changes(req,preview_only=True)
    cfg=studio.config(result['document'],cid,'portrait')
    assert cfg.music_db==-30 and cfg.visual_active_speaker=='off' and cfg.style_preset=='rapi'
    assert result['document']['clips'][cid]['end']==9
    assert document(studio)==doc


def test_real_http_diff_snapshot_and_invalid_revision(studio):
    fastapi=pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from clipper.api_studio import create_router
    app=fastapi.FastAPI();app.include_router(create_router(studio));client=TestClient(app)
    req=request(studio,[{'op':'settings','values':{'accent_hex':'#00FF00'}}]);before=document(studio)
    response=client.post('/api/studio/editor/diff',json=req)
    assert response.status_code==200 and response.json()['changes']
    assert document(studio)==before
    snap=client.post('/api/studio/editor/drafts',json=req)
    assert snap.status_code==200
    response=client.get('/api/studio/editor/projects/editor-case',params={'clip_id':first(studio)})
    assert response.status_code==200 and len(response.json()['aliases'])==10 and response.json()['aliases']['M5 · Caption, brand dan finishing']==['Tampilan','M5 · Caption, brand dan finishing']
    stale=client.post('/api/studio/editor/diff',json={**req,'expected_revision':0})
    assert stale.status_code==409 and document(studio)==before


@pytest.fixture
def media_studio(studio):
    if not shutil.which('ffmpeg'):pytest.skip('Actual FFmpeg unavailable')
    source=Path(document(studio)['source']['path'])
    subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','testsrc2=s=320x180:r=30:d=4',
        '-f','lavfi','-i','sine=frequency=730:sample_rate=48000:duration=4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True)
    def update(doc):
        doc['source']['source_id']=content_id(source,fresh=True)
        for clip in doc['clips'].values():clip.update(start=0.,end=4.)
    studio.store.mutate('editor-case',document(studio)['revision'],identifier('media'),{},update)
    return studio


@pytest.mark.parametrize('mode',['speed','reverse','freeze','ramp','mute','curve'])
def test_actual_ffmpeg_edit_proxy_decode_audio_duration_and_reuse(media_studio,mode):
    from clipper.editor_media import prepare
    from clipper.ffmpeg_util import probe
    svc=media_studio;cid=first(svc)
    rows=[{'id':'a','start':0.,'end':2.},{'id':'b','start':2.,'end':4.}]
    if mode=='speed':rows[0]['speed']=2.
    if mode=='reverse':rows[0]['reverse']=True
    if mode=='freeze':rows[0].update(kind='freeze',freeze_duration=.5)
    if mode=='ramp':rows[0]['speed_curve']=[{'offset':0,'speed':.5},{'offset':2,'speed':2.}]
    edit(svc,[{'op':'editor_segments','segments':rows}])
    if mode=='mute':edit(svc,[{'op':'track','track':'voice','values':{'mute':True}}])
    if mode=='curve':edit(svc,[{'op':'keyframes','attribute':'scale','points':[{'time':0,'value':1.,'easing':'ease_in_out'},{'time':4,'value':1.2}]}])
    doc=document(svc);clip={k:v for k,v in doc['clips'][cid].items() if k!='variants'};clip['_broll_recipe']={'scenes':[]}
    words=svc.transcript(doc,cid)['words'];cfg=svc.config(doc,cid,'portrait');source=doc['source']['path']
    path,display,edited,cfg2,receipt=prepare(svc,doc,cid,'portrait',source,words,clip,cfg)
    actual=probe(path)
    assert actual['has_audio'] and actual['width']==320
    assert actual['duration']==pytest.approx(receipt['clock']['duration'],abs=.07)
    subprocess.run(['ffmpeg','-v','error','-nostdin','-i',path,'-f','null','-'],check=True,capture_output=True)
    assert words==svc.transcript(doc,cid)['words']
    assert all(0<=w['start']<w['end']<=receipt['clock']['duration']+.001 for w in display)
    if mode=='mute':
        output=subprocess.run(['ffmpeg','-v','info','-i',path,'-af','volumedetect','-f','null','-'],capture_output=True,text=True,check=True)
        assert 'mean_volume: -91' in output.stderr
    second=prepare(svc,doc,cid,'landscape',source,words,clip,svc.config(doc,cid,'landscape'))
    assert second[-1]['clock']['digest']==receipt['clock']['digest']
    if mode not in ('curve','mute'):assert second[-1]['reused']
    assert Path(source).is_file()


def test_actual_filmstrip_and_manual_camera_validation(media_studio):
    from clipper.editor_media import filmstrip
    svc=media_studio;cid=first(svc);doc=document(svc)
    frames=filmstrip(svc,doc,cid,'portrait',3)
    assert len(frames['frames'])==3
    assert all(svc.file(row['url'].rsplit('/',1)[-1]).is_file() for row in frames['frames'])
    with pytest.raises(ValueError):edit(svc,[{'op':'camera_register','path':doc['source']['path']}])
    edit(svc,[{'op':'camera_register','path':doc['source']['path'],'offset_seconds':0.,'confirm_manual_offset':True}])
    camera=next(iter(document(svc)['editor_cameras'].values()))
    assert not camera['sync']['measured']


def test_correlation_measures_known_offset_and_rejects_silence():
    import numpy as np
    from clipper.editor_media import _correlate
    rng=np.random.default_rng(120)
    voice=rng.normal(0,.1,8000);search=np.r_[np.zeros(1000),voice,np.zeros(2000)]
    result=_correlate(voice,search)
    assert result['offset_samples']==1000 and result['score']>.99
    assert _correlate(np.zeros(8000),search) is None


def test_phrase_search_count_scope_replace_and_raw_transcript_unchanged(studio):
    doc=document(studio);cid=first(studio);raw=studio.store.transcript(doc['transcript_id'])['raw_words']
    page=studio.page('editor-case',cid,q='model tidak',limit=1)
    assert page['total']==1 and page['words'][0]['match_origin_word_ids']==[0,1]
    assert page['words'][0]['match_phrase']=='model tidak' and page['revision']==doc['revision']
    proposal=editor.replace_proposal(studio,doc,{'clip_id':cid,'scope':'clip','query':'model tidak','replacement':'modal tidak'})
    assert proposal['count']==1 and proposal['operations'][0]['origin_word_ids']==[0,1]
    edit(studio,proposal['operations'])
    assert studio.page('editor-case',cid,q='modal tidak')['total']==1
    assert studio.page('editor-case',cid,q='model tidak')['total']==0
    assert studio.page('editor-case',cid,q='model tidak',search_mode='heard')['total']==1
    assert studio.page('editor-case',cid,q='modal tidak',whole=True)['total']==0
    assert studio.store.transcript(doc['transcript_id'])['raw_words']==raw


def test_phrase_unicode_literal_and_nonoverlapping_occurrences():
    from clipper.editor_search import phrase_groups
    words=[{'word_id':1,'word':'Straße CAFÉ'},{'word_id':2,'word':'literal_%'},{'word_id':3,'word':'literal_%'}]
    assert phrase_groups(words,'STRASSE café')[0]['origin_word_ids']==[1]
    rows=phrase_groups(words,'literal_%',replacement='kutipan')
    assert len(rows)==2 and all(r['after']=='kutipan' for r in rows)
    assert phrase_groups(words,"' OR 1=1 --")==[]


def test_protected_name_requires_explicit_review(studio):
    doc=document(studio);cid=first(studio)
    proposal=editor.replace_proposal(studio,doc,{'clip_id':cid,'scope':'clip','query':'Andi','replacement':'Budi'})
    assert proposal['reviews'][0]['requires_confirmation']
    assert 'nama_atau_istilah_kritis' in proposal['reviews'][0]['categories']
    with pytest.raises(ValueError):edit(studio,proposal['operations'])
    proposal['operations'][0]['fact_confirmation']=proposal['reviews'][0]['confirmation_stamp']
    edit(studio,proposal['operations'])
    assert studio.page('editor-case',cid,q='Budi')['total']==1


def test_disjoint_fields_rebase_merges_manual_flags(studio):
    draft=editor.make_draft(studio,request(studio,[{'op':'settings','values':{'font_main':'montserrat'}}]))
    edit(studio,[{'op':'settings','values':{'accent_hex':'#00FF00'}}])
    saved=editor.commit_draft(studio,'editor-case',draft['id'],document(studio)['revision'],identifier('field-rebase'),rebase=True)
    variant=document(studio)['clips'][first(studio)]['variants']['portrait']
    assert variant['override_keys']==['accent_hex','font_main'] and variant['settings']['accent_hex']=='#00FF00'


def test_track_lock_and_unused_camera_do_not_invalidate_render_inputs(studio):
    cid=first(studio);before=studio.dependency(document(studio),cid,'portrait')
    edit(studio,[{'op':'track','track':'captions','values':{'locked':True}}])
    assert studio.dependency(document(studio),cid,'portrait')==before
    edit(studio,[{'op':'track','track':'voice','values':{'mute':True}}])
    assert studio.dependency(document(studio),cid,'portrait')!=before


def test_http_draft_preview_freezes_snapshot_and_publication_never_replaces_final(studio):
    fastapi=pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from clipper.api_studio import create_router
    from clipper.project_store import JobLeaseLost
    app=fastapi.FastAPI();app.include_router(create_router(studio));client=TestClient(app)
    before=document(studio);cid=first(studio)
    draft=editor.make_draft(studio,request(studio,[{'op':'settings','values':{'accent_hex':'#00FF00'}}]))
    response=client.post('/api/studio/editor/projects/editor-case/drafts/'+draft['id']+'/preview',
        json={'expected_revision':before['revision'],'clip_id':cid,'variant_id':'portrait'})
    assert response.status_code==200
    queued=studio.queue.get(response.json()['id'])
    assert queued['request']['snapshot']['clips'][cid]['variants']['portrait']['settings']['accent_hex']=='#00FF00'
    assert document(studio)==before
    claimed=studio.queue.claim(queued['id'])
    result={'kind':'preview','fingerprint':'protocol-fixture','draft_id':draft['id'],'is_draft':True}
    studio.store.publish_editor_draft('editor-case',{**claimed,'clip_id':cid,'variant_id':'portrait'},result)
    assert studio.queue.get(queued['id'])['status']=='completed'
    assert document(studio)==before
    assert studio.store.artifacts('editor-case')[0]['kind']=='preview_draft'
    with pytest.raises(JobLeaseLost):studio.store.publish_editor_draft('editor-case',{**claimed,'clip_id':cid,'variant_id':'portrait'},result)


def test_render_summary_exact_request_and_stale_summary_guard(studio):
    doc=document(studio);cid=first(studio);targets=[{'clip_id':cid,'variant_id':'portrait'}]
    summary=editor.render_summary(studio,doc,targets)
    job=studio.enqueue('editor-case','render',cid,'portrait',doc['revision'],{'summary_digest':summary['digest']})
    assert job['request']['render_summary']==summary
    row=summary['targets'][0]
    assert row['cost']['amount'] is None and row['audio_normalize']==studio.config(doc,cid,'portrait').audio_normalize
    edit(studio,[{'op':'settings','values':{'accent_hex':'#00FF00'}}])
    with pytest.raises(Conflict):studio.enqueue('editor-case','render',cid,'portrait',document(studio)['revision'],{'summary_digest':summary['digest']})


def test_brand_json_round_trip_policy_font_motion_and_checksum(studio):
    fastapi=pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from clipper.api_studio import create_router
    app=fastapi.FastAPI();app.include_router(create_router(studio));client=TestClient(app)
    kit=studio.workspace.save_kit({'name':'Portable values','settings':{'caption_template_policy':'manual','font_main':'montserrat',
        'font_accent':'dm_serif_italic','motion_intensity':'calm','accent_hex':'#00FF00'}})
    data=client.get('/api/studio/editor/brand-kits/'+kit['id']+'/export').json()
    imported=client.post('/api/studio/editor/brand-kits/import',json=data)
    assert imported.status_code==200 and imported.json()['kit']['settings']==kit['settings']
    data['settings']['caption_template_policy']='auto'
    count=len(studio.workspace.kits())
    assert client.post('/api/studio/editor/brand-kits/import',json=data).status_code==400
    assert len(studio.workspace.kits())==count


@pytest.mark.parametrize('op',[{'op':'editor_segments','segments':[{'start':0,'end':1,'camera_id':{}}]},
    {'op':'editor_segments','segments':[{'start':0,'end':1,'speed_curve':[3,4]}]},
    {'op':'keyframes','attribute':'scale','points':[None]}, {'op':'track','track':'voice','values':{'mute':1}}])
def test_http_invalid_editor_payload_is_400_without_write(studio,op):
    fastapi=pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from clipper.api_studio import create_router
    app=fastapi.FastAPI();app.include_router(create_router(studio));client=TestClient(app);before=document(studio)
    response=client.post('/api/studio/changes',json=request(studio,[op]))
    assert response.status_code==400 and document(studio)==before


def test_source_proxy_is_frozen_inside_the_immutable_artifact_set(tmp_path):
    from clipper.artifact_store import ArtifactSet,capture_plan_files
    source=tmp_path/'cache'/'edited.mp4';source.parent.mkdir();source.write_bytes(b'controlled proxy asset bytes')
    txn=ArtifactSet(tmp_path/'sets')
    plan={'source':{'path':str(source)},'editor':{'advanced_source_layer':'baked'}}
    frozen=capture_plan_files(txn,plan,tmp_path/'attempt')
    assert Path(frozen['source']['path']).is_relative_to(txn.final)
    metadata=txn.seal();member=Path(frozen['source']['path'])
    assert member.read_bytes()==b'controlled proxy asset bytes'
    source.write_bytes(b'cache changed after publication')
    assert member.read_bytes()==b'controlled proxy asset bytes'
