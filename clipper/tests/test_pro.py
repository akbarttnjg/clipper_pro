"""Regression gates for timestamps, grounded decisions, measured typography and UI API."""
import json
import math
from dataclasses import replace
from pathlib import Path
import pytest
from clipper.config import Config, validate_overrides
from clipper.typography import make_plan, emphasis_indices, valid_words
from clipper.score import _fallback, _ground, _clean, segments_from_words
from clipper.captions_pro import ts, write_ass
from clipper.trim import remap


def words(text, step=.45):
    return [{'word': w, 'start': i * step, 'end': (i + 1) * step, 'word_id': i} for i, w in enumerate(text.split())]


@pytest.mark.parametrize('dimensions,position', [((1920,1080),'left'),((1920,1080),'right'),((1080,1920),'bottom')])
@pytest.mark.parametrize('text', ['karena dengan penghasilan', 'PERTANGGUNGJAWABAN PENYELENGGARAAN PEMERINTAHAN', '8 dari 10 orang memahami risiko investasi.', 'WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW'])
def test_text_stays_inside_panels(dimensions, position, text):
    cfg=Config(target_w=dimensions[0],target_h=dimensions[1],caption_style='editorial')
    plan=make_plan(words(text),cfg,['penghasilan','risiko'],position)
    for phrase in plan['phrases']:
        x,y,w,h=phrase['panel']
        for item in phrase['words']:
            assert x-.01<=item['x']-item['width']/2
            assert item['x']+item['width']/2<=x+w+.01
            assert y<=item['y']<=y+h
            assert 0<=item['start']<phrase['end']


def test_indonesian_emphasis():
    w=words('karena dengan penghasilan')
    assert emphasis_indices(w)=={2}
    assert emphasis_indices(words('risiko biaya investasi'),['biaya'])=={1}


def test_timestamp_rounding():
    assert ts(59.999)=='0:01:00.00'
    assert ts(3599.999)=='1:00:00.00'


def test_partial_word_is_retained():
    result=remap([{'word':'investasi','start':1.,'end':1.5,'word_id':7}],[(1.2,2.)])
    assert result[0]['start']==0 and result[0]['word_id']==7
    assert result[0]['end']==pytest.approx(.3)


def test_invalid_times_filtered():
    assert valid_words([{'word':'bad','start':float('nan'),'end':1}])==[]
    assert _clean([{'start':0,'end':float('inf')}],100,Config())==[]


def test_fallback_respects_bounds_and_duplicates():
    w=words(' '.join('kata.' for _ in range(90)),step=.5)
    seg=segments_from_words(w)
    cfg=Config(min_clip_s=15,max_clip_s=30,num_clips=6)
    clips=_fallback(seg,45,cfg)
    assert clips
    assert len({(x['start'],x['end']) for x in clips})==len(clips)
    assert all(15<=c['end']-c['start']<=30 for c in clips)
    assert _fallback(segments_from_words(words('Sangat pendek.')),1, cfg)==[]


def test_llm_ids_and_keywords_are_grounded():
    seg=segments_from_words(words('Pahami risiko. Modal investasi.',step=1))
    cfg=Config(min_clip_s=2,max_clip_s=8)
    raw=[{'start_segment':0,'end_segment':1,'keywords':['risiko','uang palsu'],'title':'A','score':88}]
    c=_ground(raw,seg,cfg)[0]
    assert c['keywords']==['risiko'] and c['start']==0 and c['end']==4
    assert not _ground([{'start_segment':999,'end_segment':1000}],seg,cfg)


def test_ass_plan_consistency(tmp_path):
    cfg=Config(caption_style='editorial',target_w=1920,target_h=1080)
    target=tmp_path/'words.ass'
    write_ass(words('Pahami risiko sebelum investasi.'),str(target),cfg,keywords=['risiko'],position='right')
    data=json.loads(target.with_suffix('.caption-plan.json').read_text())
    ass=target.read_text()
    assert ass.count('Dialogue:')==4
    assert '\\t(' in ass and '\\pos(' in ass
    assert data['timebase']=='output_seconds'


def test_controls_allowed():
    o=validate_overrides({'aspect':'16:9','caption_style':'editorial','caption_position':'right','processing_mode':'full','language':'auto'})
    assert o['target_w']==1920 and o['processing_mode']=='full' and o['caption_position']=='right'


def test_paid_or_remote_endpoint_rejected():
    from clipper.editorial import local_url
    with pytest.raises(ValueError): local_url(Config(ollama_url='https://example.com'))
    with pytest.raises(ValueError): local_url(Config(model='example:cloud'))


def test_app_edit_and_regenerate(tmp_path,monkeypatch):
    import app
    from fastapi.testclient import TestClient
    cfg=Config(work_dir=str(tmp_path),job_id='testjob')
    original=words('karena dengan penghasilan',step=1)
    c={'start':0,'end':3,'title':'Test','reason':'Test','score':50,'keywords':[]}
    app.JOB_STATE['testjob']={'cfg':cfg,'media':'unused.mp4','transcript':{'words':original,'duration':3},'scored':[c],'edits':{}}
    app.JOBS['testjob']={'status':'done','clips':[{}]}
    client=TestClient(app.app)
    corrected=[{**w,'word':'pendapatan' if i==2 else w['word']} for i,w in enumerate(original)]
    r=client.post('/api/editor/testjob/0',json={'start':0,'end':3,'words':corrected,'keywords':['pendapatan']})
    assert r.status_code==200, r.text
    captured={}
    def render(media,ws,clip,name,cfg):
        captured.update(words=ws,cfg=cfg,clip=clip)
        return {'file':'test.mp4','width':cfg.target_w,'height':cfg.target_h,'length':3}
    monkeypatch.setattr(app.pipeline,'render_clip',render)
    r=client.post('/api/regenerate/testjob/0',data={'aspect':'16:9','caption_style':'editorial','caption_position':'right'})
    assert r.status_code==200,r.text
    assert captured['cfg'].target_w==1920 and captured['cfg'].caption_position=='right'
    assert captured['words'][-1]['word']=='pendapatan'
    r=client.post('/api/editor/testjob/0',json={'start':3,'end':2,'words':corrected})
    assert r.status_code==400


def test_full_mode_skips_ollama(tmp_path,monkeypatch):
    from clipper import pipeline
    cfg=Config(processing_mode='full',work_dir=str(tmp_path))
    monkeypatch.setattr(pipeline.transcribe,'transcribe',lambda p,c:{'words':words('Video utuh.'),'duration':1.,'text':'Video utuh.'})
    def forbidden(*args): raise AssertionError('Ollama must not be called')
    monkeypatch.setattr(pipeline.score,'score',forbidden)
    _, clips=pipeline.analyze('source.mp4',cfg)
    assert clips[0]['start']==0 and clips[0]['end']==1 and clips[0]['selection_source']=='full'


def test_offline_face_model_falls_back_once(tmp_path,monkeypatch):
    from clipper import crop
    calls=[]
    monkeypatch.setattr(crop,'_YUNET_PATH',tmp_path/'missing.onnx')
    monkeypatch.setattr(crop,'_YUNET_DOWNLOAD_FAILED',False)
    def offline(url,timeout):
        calls.append(timeout)
        raise TimeoutError('offline')
    monkeypatch.setattr(crop.urllib.request,'urlopen',offline)
    assert crop._try_yunet(640,360) is None
    assert crop._try_yunet(640,360) is None
    assert calls==[10]


def test_short_silent_audio_normalization(tmp_path):
    """Regression: a short silent clip used to send NaN samples to AAC."""
    import shutil,subprocess
    from clipper.ffmpeg_util import final_audio_args
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('ffmpeg/ffprobe not installed')
    source=tmp_path/'silence.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=s=64x64:d=1',
                    '-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','1',
                    '-c:v','libx264','-c:a','aac',str(source)],check=True,capture_output=True,timeout=15)
    r=subprocess.run(['ffmpeg','-v','error','-i',str(source),'-vn',
                      *final_audio_args(Config(audio_normalize=True),source),
                      '-c:a','aac','-f','null','-'],capture_output=True,text=True,timeout=15)
    assert r.returncode==0,r.stderr
