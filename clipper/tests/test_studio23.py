"""2.3 regressions: display integrity, real fonts, presets and preview recovery."""
import copy
from dataclasses import replace
from pathlib import Path
import json
import pytest
from clipper.config import Config
from clipper.font_catalog import FONTS, measured
from clipper.looks import LOOKS
from clipper.subtitle_edit import clean
from clipper.typography import make_plan
from clipper.captions_pro import write_ass


def words(text):
    return [{'word_id':i, 'word':s, 'start':i*.4, 'end':i*.4+.35, 'part':'body'} for i,s in enumerate(text.split())]


def test_cleanup_preserves_qualifiers_numbers_audio_timing_and_original():
    original=words('eee nah nah mungkin tidak naik 2 ,5 juta ya ya jangan')
    before=copy.deepcopy(original)
    shown, changes, warnings=clean(original)
    assert [w['word'] for w in shown]==['nah','mungkin','tidak','naik','2',',5','juta','ya','ya','jangan']
    assert original==before and len(changes)==2 and len(warnings)==1
    for w in shown:
        assert w==before[w['word_id']]
    assert clean(original, 'verbatim')[0]==original
    assert clean(words('hmm emm'))[0]==words('hmm emm')
    separated=words('nah nah');separated[1]['part']='cold_open'
    assert len(clean(separated)[0])==2


@pytest.mark.parametrize('look',LOOKS,ids=lambda t:t['id'])
def test_paired_fonts_are_real_measured_and_emitted_in_ass(look,tmp_path):
    cfg=replace(Config(title_card=False),**look['settings'])
    src=words('Pahami risiko sebelum mengambil keputusan')
    path=tmp_path/'test.ass'
    write_ass(src,path,cfg,keywords=['risiko'])
    plan=json.loads(path.with_suffix('.caption-plan.json').read_text())
    placed=[w for p in plan['phrases'] for w in p['words']]
    assert {w['font_id'] for w in placed}=={cfg.font_main,cfg.font_accent}
    for w in placed:
        f=FONTS[w['font_id']]
        assert w['file']==f['file'] and w['family']==f['family'] and w['style']==f['style']
        assert measured(cfg.fonts_dir,w['font_id'],w['size']).getname()[0]==f['family']
        assert '\\fn'+f['family'] in path.read_text()
        assert w['width']==pytest.approx(measured(cfg.fonts_dir,w['font_id'],w['size']).getlength(w['text']))
    assert src==words('Pahami risiko sebelum mengambil keputusan')


def test_no_emphasis_for_generic_longest_word():
    p=make_plan(words('berarti lu butuh berapa sebenarnya'),Config())
    assert not any(w['emphasis'] for ph in p['phrases'] for w in ph['words'])


def test_manual_position_wins_and_auto_can_use_reserved_band():
    cfg=Config(target_w=1920,target_h=1080,caption_position='left')
    anchor={'start':0,'end':10,'time':5,'position':'bottom','panel':[230,800,1460,250]}
    for safe in (True,False):
        p=make_plan(words('Pahami risiko investasi'),replace(cfg,safe_placement=safe),anchors=[anchor])['phrases'][0]
        assert p['position']=='left' and p['panel']!=anchor['panel']
    p=make_plan(words('Pahami risiko investasi'),replace(cfg,caption_position='auto'),anchors=[anchor])['phrases'][0]
    assert p['position']=='bottom' and p['panel']==anchor['panel']


@pytest.fixture
def api_state(tmp_path,monkeypatch):
    import app
    from fastapi.testclient import TestClient
    cfg=Config(work_dir=str(tmp_path),out_dir=str(tmp_path),job_id='v23')
    ws=words('eee mungkin tidak naik 2 ,5 juta')
    st={'cfg':cfg,'media':'source.mp4','transcript':{'words':ws,'duration':40},
        'scored':[{'start':0,'end':30,'title':'Contoh','revision':0}], 'edits':{},'clip_settings':{}}
    job={'status':'review','clips':[]}
    monkeypatch.setattr(app,'STATES',tmp_path/'sessions')
    monkeypatch.setattr(app,'PRESETS_FILE',tmp_path/'presets.json')
    monkeypatch.setattr(app,'JOBS',{'v23':job});monkeypatch.setattr(app,'JOB_STATE',{'v23':st})
    return app,TestClient(app.app),st,job


def test_presets_persist_without_timeline_changes_and_reject_bad_settings(api_state):
    app,client,st,job=api_state
    before=copy.deepcopy(st)
    settings={**LOOKS[0]['settings'],'caption_scale':10,'layout':'fill','target_w':3}
    r=client.post('/api/style-presets',json={'name':'Kanal saya','settings':settings})
    assert r.status_code==200,r.text
    p=r.json();assert p['settings']['caption_scale']==1.3
    assert 'layout' not in p['settings'] and 'target_w' not in p['settings']
    assert client.get('/api/style-presets').json()==[p] and st==before
    assert json.loads(app.PRESETS_FILE.read_text())==[p]
    bad=client.post('/api/style-presets',json={'name':'x','settings':{'caption_style':'narrative','font_main':'missing','font_accent':'x'}})
    assert bad.status_code==400 and client.get('/api/style-presets').json()==[p]
    client.delete('/api/style-presets/'+p['id'])
    assert client.get('/api/style-presets').json()==[]


def test_canonical_settings_and_cleanup_report_do_not_rewrite_original(api_state):
    app,client,st,job=api_state
    original=copy.deepcopy(st['transcript'])
    data={'start':0,'end':30,'words':st['transcript']['words'],'settings':{'caption_scale':10,'font_main':'montserrat','font_accent':'bebas'}}
    r=client.post('/api/editor/v23/0',json=data)
    assert r.status_code==200 and r.json()['settings']['caption_scale']==1.3
    assert r.json()['settings']['font_main']=='montserrat'
    assert 'pexels_key' not in r.json()['settings']
    result=client.get('/api/subtitle-review/v23/0').json()
    assert len(result['changes'])==1 and result['display'][0]['word']=='mungkin'
    assert st['transcript']==original
    app.persist('v23');app.JOB_STATE.clear();app.JOBS.clear();app.restore()
    assert app.JOB_STATE['v23']['clip_settings']['0']['font_accent']=='bebas'


def test_preview_from_cursor_reuses_transcript_and_never_changes_clip(api_state,monkeypatch):
    app,client,st,job=api_state
    old=copy.deepcopy(st['scored'])
    captured={}
    monkeypatch.setattr(app,'enqueue',lambda *a:None)
    assert client.post('/api/preview/v23/0',json={'source_start':99}).status_code==400
    assert 'preview_source_start' not in job
    assert client.post('/api/preview/v23/0',json={'source_start':15}).status_code==200
    def render(media,ws,c,name,cfg,progress):
        captured.update(clip=c,cfg=cfg,words=ws)
        return {'file':name+'.mp4','revision':0,'render_version':'2.3.1','length':12}
    monkeypatch.setattr(app.pipeline,'render_clip',render)
    app.worker('v23','previewing',[0])
    assert st['scored']==old and captured['clip']['start']==15
    assert captured['cfg'].preview_seconds==12 and not captured['cfg'].cold_open
    assert not captured['cfg'].title_card
    assert captured['words']==st['transcript']['words']
    assert job['preview']['source_start']==15
    job['status']='rendering'
    assert client.post('/api/preview/v23/0',json={'source_start':10}).status_code==409


def test_v22_session_gets_new_defaults_without_analysis(api_state):
    app,client,st,job=api_state
    app.persist('v23')
    path=app.STATES/'v23.json';data=json.loads(path.read_text())
    for key in ('font_main','font_accent','caption_cleanup','caption_backdrop','safe_placement'):
        data['state']['cfg'].pop(key,None)
    path.write_text(json.dumps(data))
    app.JOB_STATE.clear();app.JOBS.clear();app.restore()
    assert len(app.JOB_STATE['v23']['scored'])==1
    assert app.JOB_STATE['v23']['cfg'].font_main=='dm_sans'


def test_native_fusion_retains_actual_font_and_style(tmp_path):
    from clipper.projects import fusion_comp
    cfg=Config()
    p=make_plan(words('Pahami risiko'),cfg,keywords=['risiko'])
    plan={'fps':30,'width':1080,'height':1920,'style':{'base':'#FFFFFF','accent':'#F6D582'}}
    dst=tmp_path/'words.comp';fusion_comp(p['phrases'][0],plan,dst)
    text=dst.read_text()
    assert 'DM Sans' in text and 'SemiBold' in text
    assert 'DM Serif Display' in text and 'Italic' in text
