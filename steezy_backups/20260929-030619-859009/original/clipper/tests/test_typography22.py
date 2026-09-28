"""Motion, numeric integrity, projection detection and batch styling regressions."""
import copy
from dataclasses import replace
from pathlib import Path
import json
import numpy as np
import pytest
from clipper.config import Config
from clipper.typography import display_units, make_plan, groups
from clipper.motion import IDS


def words(text, step=.32):
    return [{'word_id':i, 'word':s, 'start':i*step, 'end':(i+1)*step-.02}
            for i,s in enumerate(text.split())]


def test_number_units_preserve_value_timing_and_original():
    original = words('Modal Rp 2 ,5 juta naik 12 % setahun')
    saved = copy.deepcopy(original)
    units = display_units(original)
    assert [w['word'] for w in units] == ['Modal','Rp2,5 juta','naik','12%','setahun']
    assert units[1]['start'] == original[1]['start']
    assert units[1]['end'] == original[4]['end']
    assert units[1]['word_ids'] == [1,2,3,4]
    assert original == saved
    assert [w['word'] for w in display_units(words('Rp ini 2 ,5 juta'))] == ['Rp','ini','2,5 juta']
    assert display_units(words('2 juta 3 juta'))[1]['word'] == '3 juta'


def test_currency_does_not_merge_across_edits_or_long_gaps():
    ws=words('Rp 2')
    ws[0]['part']=0;ws[1]['part']=1
    assert len(display_units(ws))==2
    assert len(groups(ws,Config()))==2
    ws[1]['part']=0;ws[1]['start']=5;ws[1]['end']=6
    assert len(display_units(ws))==2


@pytest.mark.parametrize('style', IDS)
@pytest.mark.parametrize('dimensions', [(1080,1920),(1920,1080)])
def test_motion_reading_order_safe_frame_and_reveal(style, dimensions):
    cfg=Config(target_w=dimensions[0],target_h=dimensions[1],caption_style=style,
               motion_intensity='dynamic')
    ws=words('Mengapa investasi butuh kesabaran dan tujuan yang jelas? Modal Rp 2 ,5 juta.')
    plan=make_plan(ws,cfg,keywords=['kesabaran','tujuan'])
    texts=[w['text'] for p in plan['phrases'] for w in p['words']]
    assert texts==[w['word'] for w in display_units(ws)]
    for p in plan['phrases']:
        assert p['start']<p['end']
        for w in p['words']:
            ks=w['keyframes']
            assert ks[0]['opacity']==0 and ks[-1]['opacity']==0
            assert any(k['opacity']>.98 for k in ks)
            assert all(0<=k['opacity']<=1 for k in ks)
            assert [k['frame'] for k in ks]==sorted(set(k['frame'] for k in ks))
            for k in ks:
                if k['opacity']<=0:continue
                half=w['width']*k['scale']/2
                assert 0<w['x']+k['dx']-half<w['x']+k['dx']+half<cfg.target_w
                assert 0<w['y']+k['dy']-w['size']<w['y']+k['dy']+w['size']<cfg.target_h*.94


def test_anchors_choose_containing_shot_and_keep_text_in_band():
    cfg=Config(caption_style='narrative')
    anchor={'time':5,'start':0,'end':10,'position':'bottom','panel':[85,800,820,340]}
    p=make_plan(words('Isi yang penting untuk dipahami'),cfg,anchors=[anchor])
    assert p['phrases'][0]['panel']==anchor['panel']
    for w in p['phrases'][0]['words']:
        assert 800<w['y']<1140


def test_projection_recovers_fragmented_material_without_accepting_white_room():
    from clipper.composition import material_panel
    import cv2
    frame=np.full((360,640,3),38,np.uint8)
    frame[:,215:]=235
    for y in range(25,330,55):
        cv2.line(frame,(218,y),(635,y),(15,15,15),8)
    # A dark fade cuts off the bright mask near the bottom.
    for y in range(300,360):frame[y,215:]=max(70,235-(y-300)*3)
    box=material_panel(frame)
    assert box and 210<=box[0]<=225 and box[2]>400 and box[3]>300
    assert material_panel(np.full_like(frame,240)) is None
    assert material_panel(np.zeros_like(frame)) is None


def test_speaker_crop_keeps_headroom_in_short_panel():
    from clipper.composition import rectangle
    face=[170,226,62,81]
    x,y,w,h=rectangle([0,0,326,528],face,1080/730)
    assert y<=face[1]-face[3]*.60
    assert 0<=y and y+h<=528


def test_batch_style_preserves_analysis_and_blocks_busy_writes(tmp_path,monkeypatch):
    import app
    from fastapi.testclient import TestClient
    cfg=Config(work_dir=str(tmp_path),job_id='style-test')
    c={'start':0,'end':4,'title':'Topik','revision':0,'approved':True}
    st={'cfg':cfg,'media':'source.mp4','transcript':{'words':words('Isi lengkap.'),'duration':4},
        'scored':[copy.deepcopy(c),copy.deepcopy(c)],'edits':{},'clip_settings':{'1':{'layout':'fit'}}}
    job={'status':'review','clips':[],'export':{'zip':'old.zip'},'preview':{'index':1}}
    monkeypatch.setattr(app,'STATES',tmp_path/'sessions')
    monkeypatch.setattr(app,'JOBS',{'style-test':job});monkeypatch.setattr(app,'JOB_STATE',{'style-test':st})
    client=TestClient(app.app);before=copy.deepcopy(st)
    assert len(client.get('/api/templates').json())==5
    assert client.get('/api/template-preview/unknown').status_code==404
    data={'indices':[1],'settings':{'caption_style':'slide','motion_intensity':'calm','layout':'fill','aspect':'16:9'}}
    job['status']='rendering'
    assert client.post('/api/apply-template/style-test',json=data).status_code==409
    job['status']='review'
    assert client.post('/api/apply-template/style-test',json={**data,'indices':[1,99]}).status_code==400
    assert st==before
    assert client.post('/api/apply-template/style-test',json=data).status_code==200
    assert st['transcript']==before['transcript'] and st['edits']==before['edits']
    assert st['scored'][0]==c and st['scored'][1]=={**c,'revision':1}
    assert st['clip_settings']['1']=={'layout':'fit','caption_style':'slide','motion_intensity':'calm'}
    assert 'export' not in job and 'preview' not in job
    assert client.post('/api/export/style-test',json={'indices':[1]}).status_code==409


def test_relink_packaged_clean_media_checks_new_location(tmp_path):
    from clipper.project_install import relink
    folder=tmp_path/'moved';folder.mkdir();(folder/'Media').mkdir()
    (folder/'Media/clean.mp4').write_bytes(b'media')
    (folder/'manifest.json').write_text(json.dumps({'created_root':'/old/package','source_files':['/old/package/Media/clean.mp4']}))
    m=relink(folder)
    assert m['source_files']==[str(folder/'Media/clean.mp4')]


def test_failed_audio_render_keeps_completed_stem(tmp_path,monkeypatch):
    from clipper import render
    from types import SimpleNamespace
    target=tmp_path/'voice.wav';target.write_bytes(b'completed audio')
    def fail(command,**kwargs):
        Path(command[-1]).write_bytes(b'incomplete header')
        return SimpleNamespace(returncode=1,stderr=b'example encoder failure')
    monkeypatch.setattr(render.subprocess,'run',fail)
    with pytest.raises(RuntimeError,match='Audio FFmpeg gagal'):
        render.run_audio([],target,tmp_path/'audio.log')
    assert target.read_bytes()==b'completed audio'
    assert not (tmp_path/'voice.rendering.wav').exists()
