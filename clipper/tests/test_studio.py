"""Studio behavior gates: temporal integrity, review state, and editable exports."""
import copy
import json
from dataclasses import replace
from pathlib import Path
import pytest
from clipper.config import Config
from clipper import story, editplan
from clipper.storage import source_key, write_json


def words(text, step=1):
    return [{'word_id':i,'word':w,'start':i*step,'end':(i+1)*step-.05} for i,w in enumerate(text.split())]


def test_topic_boundaries_require_grounded_complete_ending():
    ws = words('Bagaimana menambah penghasilan? Belajar keahlian baru. Naikkan nilai pekerjaan. Pahami risikonya.')
    block = story.segments_from_words(ws)
    cfg = Config(min_clip_s=5,max_clip_s=20)
    raw = {'start_segment':0,'end_segment':3,'title':'Keahlian dan penghasilan','reason':'Cara konkret',
           'value':4,'opening':4,'closure':4,'complete':True,'ending_evidence':'Pahami risikonya.',
           'keywords':['keahlian','kaya raya'],'hook_quote':'Belajar keahlian baru'}
    result = story.ground([raw],block,ws,cfg,12)
    assert len(result)==1 and result[0]['keywords']==['keahlian']
    assert result[0]['start']==0 and result[0]['end']>=block[-1]['end']
    assert not story.ground([{**raw,'ending_evidence':'Dijamin kaya'}],block,ws,cfg,12)
    assert not story.ground([{**raw,'complete':False}],block,ws,cfg,12)
    assert not story.ground([{**raw,'start_segment':999}],block,ws,cfg,12)


def test_overlapping_windows_cover_boundary_topics():
    seg=[{'id':i,'start':i*10.,'end':i*10.+9,'text':'Konteks topik.'} for i in range(72)]
    blocks=list(story.windows(seg,Config()))
    assert set(s['id'] for b in blocks for s in b)==set(range(72))
    assert any(b[0]['start']<=190 and b[-1]['end']>=310 for b in blocks)


def test_cold_open_exact_quote_and_timeline_word_mapping():
    ws=words('Satu dua tiga empat lima enam risiko kehilangan uang itu nyata sekarang selesai.',.5)
    assert story.quote_span('risiko keuntungan pasti',ws,0,6.5) is None
    c={'start':0,'end':6.5,'title':'Uji','keywords':['risiko'],'cold_open_span':[4,5.5]}
    p=editplan.build(ws,c,Config(trim_silence=False))
    assert p['spans'][0]['kind']=='cold_open'
    assert p['duration_frames']==240
    assert p['spans'][1]['source_start']==0
    repeated=[w for w in p['words'] if w['word']=='uang']
    assert len(repeated)==2 and repeated[1]['start']>repeated[0]['start']
    assert all(0<=w['start']<w['end']<=p['duration']+.001 for w in p['words'])


def test_pause_cuts_preserve_words_and_breathing():
    ws=[{'word':'A','start':0,'end':1},{'word':'B','start':4,'end':5}]
    p=editplan.build(ws,{'start':0,'end':5.2,'title':'Uji'},Config(trim_silence=True))
    assert [w['word'] for w in p['words']]==['A','B']
    assert .45 <= p['words'][1]['start']-p['words'][0]['end'] <= .56
    assert p['duration']<5.2


def test_no_duplicate_topics_and_no_forced_ten_clips():
    ws=words('risiko investasi membutuhkan perencanaan ' * 20)
    c={'start':0,'end':40,'rubric':{'value':4,'opening':4,'closure':4}}
    assert len(story.distinct([c,{**c,'start':3,'end':42}],ws,Config(num_clips=10)))==1


def test_cache_invalidated_by_source_language_and_model(tmp_path):
    p=tmp_path/'source.mp4';p.write_bytes(b'first')
    cfg=Config()
    a=source_key(p,cfg)
    assert a==source_key(p,cfg)
    assert a!=source_key(p,replace(cfg,language='en'))
    assert a!=source_key(p,replace(cfg,whisper_model='small'))
    p.write_bytes(b'changed')
    assert a!=source_key(p,cfg)


def test_ollama_failure_is_not_a_viral_score(tmp_path,monkeypatch):
    ws=words('Isi pembicaraan lengkap. ' * 30)
    monkeypatch.setattr(story.editorial,'release',lambda c:None)
    def unavailable(*args):
        import requests
        raise requests.ConnectionError('offline')
    monkeypatch.setattr(story,'request',unavailable)
    result=story.select({'words':ws,'duration':90},Config(work_dir=str(tmp_path)))
    assert len(result)==1 and result[0]['selection_source']=='manual-required'
    assert result[0]['rubric']=={} and 'score' not in result[0]


def test_nvenc_real_size_probe_and_logged_cpu_retry(tmp_path,monkeypatch):
    from clipper import ffmpeg_util as f
    from types import SimpleNamespace
    calls=[]
    def run(cmd,**kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=1 if len(calls)==1 else 0,stderr=b'encoder error' if len(calls)==1 else b'')
    monkeypatch.setattr(f.subprocess,'run',run)
    command=['ffmpeg','-c:v','h264_nvenc',*f.encoder_args('h264_nvenc'),'out.mp4']
    codec, warnings=f.encode(command,'h264_nvenc',tmp_path/'render.log')
    assert codec=='libx264' and warnings
    assert 'h264_nvenc' not in calls[1] and '-crf' in calls[1]
    assert 'encoder error' in (tmp_path/'render.log').read_text()
    f.nvenc_diagnostic.cache_clear();f.nvenc_diagnostic()
    assert any('1280x720' in a for a in calls[-1])
    f.nvenc_diagnostic.cache_clear()


def test_editor_validation_is_transactional_and_exports_reject_stale(tmp_path,monkeypatch):
    import app
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app,'STATES',tmp_path)
    ws=words('Awal isi dan penutup.')
    cfg=Config(work_dir=str(tmp_path),job_id='studio-test')
    c={'start':0,'end':4,'title':'Uji','reason':'r','keywords':[],'revision':0}
    app.JOB_STATE['studio-test']={'cfg':cfg,'media':'source.mp4','transcript':{'words':ws,'duration':4},'scored':[c],'edits':{}}
    app.JOBS['studio-test']={'status':'review','clips':[{'index':0,'revision':0}]}
    client=TestClient(app.app)
    data={'start':0,'end':4,'words':ws,'keywords':['isi'],'cold_open_span':[3,8]}
    old=copy.deepcopy(app.JOB_STATE['studio-test'])
    assert client.post('/api/editor/studio-test/0',json=data).status_code==400
    assert app.JOB_STATE['studio-test']==old
    data['cold_open_span']=None
    assert client.post('/api/editor/studio-test/0',json=data).status_code==200
    assert client.post('/api/export/studio-test',json={'indices':[0]}).status_code==409
    app.JOB_STATE.pop('studio-test');app.JOBS.pop('studio-test');app.restore()
    assert app.JOB_STATE['studio-test']['scored'][0]['revision']==1
    assert app.JOB_STATE['studio-test']['edits'][0][1]['word']=='isi'


def test_cross_origin_local_path_write_rejected():
    import app
    from fastapi.testclient import TestClient
    c=TestClient(app.app)
    assert c.post('/api/local',json={'path':'anything'},headers={'Origin':'https://unrelated.example'}).status_code==403


def test_project_registration_preserves_existing_drafts(tmp_path):
    from clipper.project_install import install_capcut
    package=tmp_path/'package';draftroot=tmp_path/'drafts'
    package.mkdir();draftroot.mkdir()
    source=package/'CapCut'/'CLIPPER_ALL_TIMELINES';source.mkdir(parents=True)
    write_json(package/'manifest.json',{'created_root':str(package),'source_files':[],'capcut_status':'experimental-generated'})
    write_json(source/'draft_content.json',{'id':'x'})
    write_json(source/'draft_meta_info.json',{'draft_name':'test','draft_id':'x'})
    write_json(draftroot/'root_meta_info.json',{'all_draft_store':[{'draft_id':'existing','draft_name':'keep'}]})
    created,backup=install_capcut(package,draftroot,check_running=False)
    after=json.loads((draftroot/'root_meta_info.json').read_text())
    assert after['all_draft_store'][1]['draft_id']=='existing'
    assert backup.exists() and created[0].exists()
    assert json.loads(backup.read_text())['all_draft_store']==[{'draft_id':'existing','draft_name':'keep'}]


def test_pipeline_rejects_beyond_source_before_render(tmp_path,monkeypatch):
    from clipper import pipeline
    monkeypatch.setattr(pipeline.ffmpeg_util,'probe',lambda p:{'duration':4,'has_audio':True})
    with pytest.raises(ValueError,match='durasi sumber'):
        pipeline.render_clip('unused',[],{'start':0,'end':6,'title':'u'},'clip',Config(work_dir=str(tmp_path),out_dir=str(tmp_path)))
