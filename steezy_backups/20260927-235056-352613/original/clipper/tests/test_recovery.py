"""Regression cases from the failed render and incomplete candidate boundaries."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from clipper.config import Config, validate_overrides
from clipper import boundaries, story, ffmpeg_util as ff


def ws(text, step=.4):
    return [{'word': w, 'start': i*step, 'end': i*step+.35} for i,w in enumerate(text.split())]


def test_modern_filter_file_probe_prefers_actual_success(monkeypatch):
    calls=[]
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0,stderr=b'')
    monkeypatch.setattr(ff.subprocess,'run',run)
    ff.render_diagnostic.cache_clear()
    try:
        assert ff.filter_file_args('C:/video/graph.txt')==['-/filter_complex','C:/video/graph.txt']
        assert '-/filter_complex' in calls[0] and 'libx264' in calls[0]
    finally:
        ff.render_diagnostic.cache_clear()


def test_old_ffmpeg_probe_falls_back_only_on_option_error(monkeypatch):
    calls=[]
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1 if len(calls)==1 else 0,
            stderr=b"Unrecognized option '/filter_complex'" if len(calls)==1 else b'')
    monkeypatch.setattr(ff.subprocess,'run',run)
    ff.render_diagnostic.cache_clear()
    try:
        assert ff.filter_file_args('graph.txt')[0]=='-filter_complex_script'
        assert len(calls)==2
    finally:
        ff.render_diagnostic.cache_clear()


def test_argument_failure_is_not_retried_on_cpu(tmp_path,monkeypatch):
    calls=[]
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1,stderr=b"Unrecognized option 'filter_complex_script'.")
    monkeypatch.setattr(ff.subprocess,'run',run)
    with pytest.raises(RuntimeError,match='Unrecognized option'):
        ff.encode(['ffmpeg','-c:v','h264_nvenc','out.mp4'],'h264_nvenc',tmp_path/'render.log')
    assert len(calls)==1
    assert 'CPU RETRY' not in (tmp_path/'render.log').read_text()


def test_missing_ass_is_reported_before_long_analysis(tmp_path,monkeypatch):
    monkeypatch.setattr(ff.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stderr=b'No such filter: ass'))
    ff.render_diagnostic.cache_clear()
    try:
        with pytest.raises(RuntimeError,match='No such filter'):
            ff.filter_file_args('not-used')
    finally:
        ff.render_diagnostic.cache_clear()


@pytest.mark.parametrize('text,end',[
    ('Awal penjelasan. Uang pertama kalian dari gaji bulanan.',7),
    ('Ada empat cara. Yang keempat uang orang bisnis orang.',8),
    ('Beli kursus lalu setelah itu gue ngerti gue bikin konten.',8),
])
def test_partial_clauses_are_flagged_even_with_high_llm_score(text,end):
    words=ws(text)
    clip={'start':0,'end':words[end-1]['end']+.01,'rubric':{'closure':5},'reason':''}
    assert boundaries.annotate(clip,words)['boundary_review']['status']=='needs_review'


def test_grounding_padding_does_not_include_half_the_next_word():
    words=ws('Bagaimana caranya? Tingkatkan skill. Sesudah itu belajar lagi.')
    block=boundaries.segments_from_words(words)
    raw={'start_segment':0,'end_segment':1,'title':'Skill','reason':'Langkah belajar',
        'value':4,'opening':4,'closure':5,'complete':True,'ending_evidence':'Tingkatkan skill.',
        'keywords':['skill'],'hook_quote':''}
    result=story.ground([raw],block,words,Config(min_clip_s=1,max_clip_s=10),4)
    assert len(result)==1
    assert result[0]['end']<=words[4]['start']
    assert not boundaries.audit(result[0],words)


def test_unsupported_acronym_expansion_is_not_accepted_as_evidence():
    words=ws('Penghasilan dari gaji OMR dibahas di sini.')
    c={'start':0,'end':4,'reason':'OMR (Online Money Making)'}
    assert any('OMR' in x for x in boundaries.audit(c,words))


def test_context_review_does_not_switch_to_a_different_topic(tmp_path,monkeypatch):
    words=ws('Pertanyaan utama. Jawaban lengkap. Topik berbeda. Jawaban lain.')
    candidate={'start':0,'end':1.55,'title':'Utama','reason':'','revision':0}
    raw={'start_segment':2,'end_segment':3,'title':'Lain','reason':'Lain',
        'value':5,'opening':5,'closure':5,'complete':True,'ending_evidence':'Jawaban lain.',
        'keywords':[],'hook_quote':''}
    monkeypatch.setattr(story,'request',lambda *a:[raw])
    result=story.review_candidate(candidate,{'words':words,'duration':3.2},Config(work_dir=str(tmp_path),min_clip_s=.5,max_clip_s=4))
    assert result['start']==0 and result['title']=='Utama'
    assert result['boundary_review']['status']=='needs_review'


def test_successful_context_review_is_cached_and_preserves_previous_boundary(tmp_path,monkeypatch):
    words=ws('Bagaimana caranya? Tingkatkan skill. Sesudah itu belajar lagi.')
    candidate={'start':0,'end':1.4,'title':'Skill','reason':'','revision':0}
    raw={'start_segment':0,'end_segment':1,'title':'Belajar skill','reason':'Belajar',
        'value':5,'opening':5,'closure':5,'complete':True,'ending_evidence':'Tingkatkan skill.',
        'keywords':['skill'],'hook_quote':''}
    calls=[]
    def request(*a):
        calls.append(a);return [raw]
    monkeypatch.setattr(story,'request',request)
    cfg=Config(work_dir=str(tmp_path),min_clip_s=1,max_clip_s=4)
    result=story.review_candidate(candidate,{'words':words,'duration':4},cfg)
    assert result['revision']==1 and result['previous_boundary']['end']==1.4
    assert result['boundary_review']['status']=='checked'
    assert story.review_candidate(candidate,{'words':words,'duration':4},cfg)==result
    assert len(calls)==1


def test_manual_regions_are_bounded_and_clearable():
    assert validate_overrides({'material_rect':'40,10,55,85'})['material_rect']=='40,10,55,85'
    assert validate_overrides({'material_rect':''})['material_rect']==''
    for value in ('0,0,120,50','nan,0,50,50','1,2,3','0,0,0,0'):
        with pytest.raises(ValueError):
            validate_overrides({'material_rect':value})


def test_presentation_detector_finds_board_not_full_white_room():
    import numpy as np
    from clipper.composition import material_panel
    image=np.zeros((360,640,3),dtype=np.uint8)
    image[25:335,250:610]=245
    rect=material_panel(image)
    assert rect and abs(rect[0]-250)<10 and rect[2]>350
    assert material_panel(np.full_like(image,245)) is None


def test_render_batch_keeps_good_results_and_retries_only_failed(tmp_path,monkeypatch):
    import app
    from dataclasses import asdict
    cfg=Config(work_dir=str(tmp_path/'work'),out_dir=str(tmp_path),job_id='resume-test')
    clips=[{'start':0,'end':4,'title':str(i),'revision':0} for i in range(3)]
    monkeypatch.setattr(app,'STATES',tmp_path/'sessions')
    monkeypatch.setattr(app,'JOBS',{'resume-test':{'status':'review','clips':[]}})
    monkeypatch.setattr(app,'JOB_STATE',{'resume-test':{'cfg':cfg,'media':'source.mp4',
        'transcript':{'words':ws('Isi selesai.'),'duration':4},'scored':clips,'edits':{}}})
    monkeypatch.setattr(app.pipeline.ffmpeg_util,'filter_file_args',lambda p:[])
    calls=[]
    def render(media,words,clip,name,cfg,on_progress):
        calls.append(clip['title'])
        if clip['title']=='1' and calls.count('1')==1:raise RuntimeError('contoh gagal per clip')
        f=tmp_path/(clip['title']+'.mp4');f.write_bytes(b'complete')
        on_progress(50,'Encoding')
        return {'file':f.name,'revision':0,'render_version':'2.2.0'}
    monkeypatch.setattr(app.pipeline,'render_clip',render)
    app.worker('resume-test','rendering',[0,1,2])
    assert app.JOBS['resume-test']['status']=='error'
    assert [r['index'] for r in app.JOBS['resume-test']['clips']]==[0,2]
    app.worker('resume-test','rendering',[0,1,2])
    assert calls==['0','1','2','1']
    assert app.JOBS['resume-test']['status']=='done'
    assert len(app.JOBS['resume-test']['clips'])==3


def test_resume_uses_saved_candidates_without_analysis(tmp_path,monkeypatch):
    import app
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app,'STATES',tmp_path)
    monkeypatch.setattr(app,'JOBS',{'saved':{'status':'error','clips':[]}})
    monkeypatch.setattr(app,'JOB_STATE',{'saved':{'cfg':Config(),'scored':[{'title':'Utuh'}],'edits':{}}})
    monkeypatch.setattr(app,'enqueue',lambda *a:pytest.fail('Analysis must not run again'))
    r=TestClient(app.app).post('/api/resume/saved')
    assert r.status_code==200 and r.json()['status']=='review'
    assert r.json()['candidates'][0]['title']=='Utuh'
