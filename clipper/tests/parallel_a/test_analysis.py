"""Step 1 contracts: source integrity, discovery novelty, geometry and asset evidence."""
import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import pytest
from clipper.analysis_options import AnalysisConfig as Config
from clipper import transcript_correction as correction
from clipper import correction_memory, evidence, discovery, story, stock, asset_review
from clipper.storage import read_json, write_json, source_key
from clipper.typography import make_plan, groups, optical_factor, font, emphasis_indices
from clipper.caption_checks import inspect_caption_plan
from clipper.tests.test_upgrade32 import words


def test_memory_is_explicit_scoped_disableable_and_protects_values(tmp_path):
    cfg=Config(work_dir=str(tmp_path),audience='finance')
    rows=correction_memory.save(cfg,'XAUUSD','hausd','finance')
    assert correction_memory.glossary(cfg)=='XAUUSD=hausd'
    assert not correction_memory.glossary(replace(cfg,audience='students'))
    correction_memory.save(cfg,'XAUUSD','hausd','finance',False)
    assert not correction_memory.glossary(cfg)
    with pytest.raises(ValueError):correction_memory.save(cfg,'untung','tidak untung')
    with pytest.raises(ValueError):correction_memory.save(cfg,'25','20')
    assert len(correction_memory.remove(cfg,rows[0]['id']))==0


def test_domain_aliases_are_not_general_rewrites(tmp_path):
    cfg=Config(work_dir=str(tmp_path))
    original=words('nama jona ada di sana')
    assert correction.correct_words(original,cfg)[0]==original
    finance=words('trading forex hausd sedang beris pada time frame daily')
    result,changes=correction.correct_words(finance,cfg)
    text=' '.join(w['word'] for w in result)
    assert 'XAUUSD' in text and 'bearish' in text and 'timeframe' in text
    assert changes and finance[2]['word']=='hausd'


def test_audio_phrase_merge_preserves_source_ids_timing_and_manual(tmp_path):
    original=words('time frame');original[0]['probability']=.3;original[1]['probability']=.45
    heard=[dict(word='timeframe',start=original[0]['start'],end=original[-1]['end'],probability=.96)]
    merged,changes=correction.merge_recheck(original,heard)
    assert len(merged)==1 and merged[0]['source_word_ids']==[0,1]
    assert merged[0]['end']==original[1]['end'] and changes[0]['evidence']['new_probability']==.96
    original[0]['manually_edited']=True
    assert correction.merge_recheck(original,heard)[0]==original


@pytest.mark.parametrize('text,heard',[('tidak rugi','rugi'),('20 pip','25 pip')])
def test_audio_cannot_remove_negation_or_change_number(text,heard):
    source=words(text);replacement=words(heard)
    for w in source:w['probability']=.2
    for w in replacement:w['probability']=.99
    assert correction.merge_recheck(source,replacement)[0]==source


def test_suspicious_high_confidence_and_cache_budget(tmp_path):
    ws=words('trading hausd');ws[1]['probability']=.99
    assert correction.recheck_ranges(ws,20,12)
    p=tmp_path/'source.mp4';p.write_bytes(b'fixture')
    cfg=Config(work_dir=str(tmp_path))
    from clipper.analysis_adapter import asr_fingerprint
    assert asr_fingerprint('sha256:source','audio:0',cfg)!=asr_fingerprint('sha256:source','audio:0',replace(cfg,asr_recheck_windows=24))
    correction_memory.save(cfg,'NamaProduk','nama prodak')
    assert correction_memory.signature(cfg)


def test_ocr_suggestions_never_modify_transcript_or_invent_numbers(tmp_path):
    ws=words('hausd 1250 tidak');saved=copy.deepcopy(ws)
    frames={'frames':[dict(time=1,width=1920,height=1080,texts=[dict(text='XAUUSD 1350',confidence=.95,box=[10,10,300,80])])]}
    suggestions=evidence.suggestions(ws,frames)
    assert suggestions and suggestions[0]['suggestions']==['XAUUSD'] and ws==saved
    assert all(x['word_id']==0 for x in suggestions)
    cfg=Config(work_dir=str(tmp_path));ws[0]['manually_edited']=True
    assert not any(x['evidence']=='ocr' for x in correction.review_queue(ws,cfg,suggestions))


def test_phrase_guard_and_semantic_fallback_include_negation():
    ws=words('pilih trading dengan stop loss tidak pasti untung sekarang',step=.25)
    for phrase in groups(ws,Config()):
        assert phrase[-1]['word'] not in ('stop','tidak')
    assert emphasis_indices(words('tidak untung'),['untung'])=={0,1}
    assert emphasis_indices(words('jaga stop loss selalu'),['stop loss'])=={1,2}


@pytest.mark.parametrize('family',['dm_sans','dm_serif','dm_serif_italic','bebas','montserrat','dejavu','dejavu_serif'])
def test_optical_size_uses_visible_height(family):
    from clipper.font_catalog import FONTS
    cfg=Config();size=round(100*optical_factor(cfg.fonts_dir,family))
    bbox=font(cfg.fonts_dir,size,family).getbbox('H');ref=font(cfg.fonts_dir,100,'dm_sans').getbbox('H')
    assert abs((bbox[3]-bbox[1])-(ref[3]-ref[1]))<=3


@pytest.mark.parametrize('size',[(1080,1920),(1920,1080)])
@pytest.mark.parametrize('style',['magazine','narrative','editorial','clean','slide'])
def test_entire_motion_stays_inside_caption_panel(size,style):
    cfg=Config(target_w=size[0],target_h=size[1],caption_style=style,motion_intensity='dynamic')
    plan=make_plan(words('Trading XAUUSD tidak pasti untung kelola risiko dengan disiplin',step=.35),cfg,keywords=['tidak pasti untung'])
    assert inspect_caption_plan(plan,cfg,expected_words=True)['passed']
    bad=copy.deepcopy(plan);bad['phrases'][0]['words'][0]['y']=-200
    with pytest.raises(ValueError,match='batas|area'):inspect_caption_plan(bad,cfg)
    with pytest.raises(ValueError,match='kosong'):inspect_caption_plan({'phrases':[]},cfg,expected_words=True)


def test_ocr_boxes_use_source_coordinate_space_and_do_not_cross_old_slides():
    ev={'frames':[dict(time=3,width=1920,height=1080,texts=[dict(box=[200,100,900,600],confidence=.95)])]}
    assert evidence.protected_boxes(ev,2,4,1920,1080)==[[200,100,900,600]]
    assert not evidence.protected_boxes(ev,5,7,1920,1080)
    assert not evidence.protected_boxes(ev,2,4,1080,1920)


def test_discovery_again_has_new_objective_and_keeps_history(tmp_path,monkeypatch):
    from clipper.tests.test_intelligence31 import example
    from clipper.tests.test_upgrade33 import row
    clip,ws,block,_,cfg=example(tmp_path);cfg=replace(cfg,search_depth='balanced',topic_review=False)
    calls=[]
    monkeypatch.setattr(story,'segments_from_words',lambda w:block)
    monkeypatch.setattr(story,'windows',lambda s,c:[block])
    monkeypatch.setattr(story,'request',lambda b,c,candidate=None,**kw:calls.append(kw) or [row(block)])
    monkeypatch.setattr(story.editorial,'release',lambda c:None)
    transcript={'words':ws,'duration':clip['end']}
    first=story.select(transcript,cfg);before=len(calls)
    story.select(transcript,cfg,existing=first)
    assert len(calls)>before and calls[-1]['focus']
    history=discovery.history(cfg)
    assert len(history)==2 and history[0]['objective']!=history[1]['objective']
    assert history[1]['existing_candidates']==1 and history[1]['new_candidates']==0
    assert history[0]['analysis_revision']==history[1]['analysis_revision']


def test_multiple_scales_cover_late_source_and_visual_cue():
    seg=[dict(id=i,start=i*10,end=i*10+9,text='Isi lengkap.') for i in range(150)]
    cfg=Config(discovery_extra_windows=8)
    blocks=discovery.extra_windows(seg,cfg,[],[dict(time=600,kind='slide_or_scene_change',strength=1)],1)
    assert any(b[-1]['end']>1300 for b,k in blocks)
    assert any(k=='slide_or_scene_change' for b,k in blocks)
    assert len({round(b[-1]['end']-b[0]['start']) for b,k in blocks})>1


def test_different_grounded_claims_can_share_context():
    a=dict(start=0,end=40,main_claim='Angka penting untuk mengukur biaya')
    b=dict(start=12,end=50,main_claim='Contoh penghematan waktu dalam operasional')
    assert not story.duplicate(a,b,words('Isi bersama untuk konteks yang sama'))


def test_semantic_comparison_can_detect_paraphrase_but_retains_new_story_type(tmp_path,monkeypatch):
    cfg=Config(work_dir=str(tmp_path));calls=[]
    class Reply:
        def raise_for_status(self):pass
        def json(self):return {'response':json.dumps({'pairs':[{'keep':0,'duplicate':1,'reason':'Keduanya menjelaskan latihan meningkatkan keterampilan.'}]})}
    monkeypatch.setattr(discovery.requests,'post',lambda *a,**kw:calls.append(kw) or Reply())
    a=dict(start=0,end=30,title='Latihan',story_kind='explanation',main_claim='Latihan rutin meningkatkan kemampuan kerja')
    b=dict(start=60,end=90,title='Belajar',story_kind='explanation',main_claim='Keterampilan membaik melalui praktik setiap hari')
    removed,report=discovery.semantic_groups([a,b],cfg)
    assert removed=={1} and report[0]['source']=='local_semantic_review' and calls
    b['story_kind']='example'
    assert discovery.semantic_groups([a,b],cfg)[0]==set()


def test_malformed_stock_cache_is_repaired_not_reused_forever(tmp_path,monkeypatch):
    cfg=Config();monkeypatch.setattr(stock,'CACHE',tmp_path);monkeypatch.setattr(story.editorial,'release',lambda c:None)
    assets=[dict(id='a',title='Person typing keyboard')]
    rows=[dict(index=0,title='Person typing keyboard',tags='',description='')]
    key=hashlib.sha256(json.dumps([rows,'typing','typing work',cfg.model,'relevance-3.1'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    path=tmp_path/'relevance'/(key+'.json');write_json(path,{'index':55,'reason':'wrong','metadata_quote':'invented'})
    calls=[]
    class Reply:
        def raise_for_status(self):pass
        def json(self):return {'response':json.dumps(dict(index=0,reason='Aktivitas sesuai',metadata_quote='typing keyboard'))}
    monkeypatch.setattr(stock.requests,'post',lambda *a,**kw:calls.append(kw) or Reply())
    assert stock.choose(assets,'typing','typing work',cfg)[0]['id']=='a'
    assert len(calls)==1 and read_json(path)['index']==0
    assert stock.choose(assets,'typing','typing work',cfg)[0] and len(calls)==1


def test_local_query_variants_and_metadata_edit(tmp_path,monkeypatch):
    monkeypatch.setattr(stock,'SETTINGS',tmp_path/'settings.json');p=tmp_path/'collection';p.mkdir();(p/'asset.mp4').write_bytes(b'fixture')
    write_json(stock.SETTINGS,{'local_dir':str(p)})
    asset=stock.local_assets()[0]
    stock.save_local_metadata(asset['id'],{'tags':'mengetik typing keyboard','author':'Pemilik','license_url':'https://example.org/license'})
    assert 'keyboard' in stock.local_assets()[0]['tags']
    variants=stock.query_variants('typing laptop','mengetik laptop')
    assert len(variants)>=2 and any('working' in s for s in variants)
    with pytest.raises(ValueError):stock.save_local_metadata('missing',{})


def test_visual_review_sends_actual_frames_and_validates_response(tmp_path,monkeypatch):
    import numpy as np
    p=tmp_path/'asset.mp4';p.write_bytes(b'fixture')
    frame=np.zeros((120,200,3),dtype=np.uint8);frame[:,100:]=255
    monkeypatch.setattr(asset_review,'samples',lambda p:[frame]*3)
    calls=[]
    class Reply:
        def raise_for_status(self):pass
        def json(self):return {'response':json.dumps(dict(relevant=True,watermark=False,description='Tangan mengetik keyboard.',reason='Sesuai aktivitas bekerja.'))}
    monkeypatch.setattr(asset_review.requests,'post',lambda *a,**kw:calls.append(kw['json']) or Reply())
    cfg=Config(work_dir=str(tmp_path),vision_model='fixture-vision',vision_policy='required')
    result=asset_review.verify({'path':str(p)},'typing','latihan mengetik',cfg)
    assert result['visual_verified'] and result['sample_count']==3 and len(calls[0]['images'])==3
    assert calls[-1]['keep_alive']==0
    assert asset_review.verify({'path':str(p)},'typing','latihan mengetik',cfg)['cached']
    review_path=next((tmp_path/'visual-reviews').glob('*.json'))
    write_json(review_path,{'status':'verified'})
    assert not asset_review.verify({'path':str(p)},'typing','latihan mengetik',cfg)['cached']
    assert len([c for c in calls if 'images' in c])==2
    unavailable=asset_review.verify({'path':str(p)},'typing','latihan mengetik',replace(cfg,vision_model=''))
    assert not unavailable['accept'] and not unavailable['visual_verified']


def test_content_fingerprint_detects_same_name_size_and_timestamp_replacement(tmp_path):
    import os
    from clipper.illustration_catalog import cached_assets_valid,recipe_path
    p=tmp_path/'asset.mp4';p.write_bytes(b'first');stat=p.stat()
    fingerprint=asset_review.identity(p)[-1]
    recipe={'scenes':[{'asset':{'path':str(p),'content_fingerprint':fingerprint}}]}
    assert cached_assets_valid(recipe)
    p.write_bytes(b'other');os.utime(p,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert asset_review.identity(p)[-1]!=fingerprint and not cached_assets_valid(recipe)
    cfg=Config(work_dir=str(tmp_path));clip={'start':0,'end':40}
    assert recipe_path([],clip,cfg,input_fingerprint='source-old')!=recipe_path([],clip,cfg,input_fingerprint='source-new')


def test_next_candidate_is_checked_after_visual_rejection(tmp_path,monkeypatch):
    assets=[dict(id='bad',provider='local',title='typing keyboard',tags='typing'),
            dict(id='good',provider='local',title='typing keyboard',tags='typing')]
    checked=[]
    monkeypatch.setattr(stock,'local_assets',lambda:assets)
    monkeypatch.setattr(stock,'choose',lambda rows,*args:(rows[0],[]))
    monkeypatch.setattr(stock,'download',lambda item:dict(item))
    def verify(item,*args):
        checked.append(item['id'])
        return dict(accept=item['id']=='good',visual_verified=True,reason='fixture frame review')
    monkeypatch.setattr(asset_review,'verify',verify)
    result,notes=stock.find('typing keyboard','mengetik',online=False,cfg=Config(work_dir=str(tmp_path)))
    assert result['id']=='good' and checked==['bad','good'] and notes


def test_caption_qc_detects_one_missing_phrase_even_if_others_exist():
    cfg=Config();ws=words('Trading XAUUSD tidak pasti untung kelola risiko dengan disiplin setiap hari',step=.5)
    plan=make_plan(ws,cfg);assert len(plan['phrases'])>1
    plan['phrases'].pop()
    with pytest.raises(ValueError,match='tidak ada'):inspect_caption_plan(plan,cfg,expected_words=ws)

