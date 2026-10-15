"""Real PCM/FFmpeg integration. Authored fixtures are not human G6 acceptance."""
import copy,json,os,shutil,subprocess,zipfile
from pathlib import Path
from dataclasses import replace
import numpy as np
import pytest
from ..config import Config
from .. import editplan,pipeline,camera4_contract as camera
from ..audio6 import premix,finalize
from ..audio6_dsp import decode
from ..artifact_store import verify
from ..dependency_cache import content_id
from ..audio6_contract import tracks
from ._m4_fixture import video,controls,make_studio,change
from .test_m4_media import report_for
from .test_m5_contract import words

def tone(path,hz=250,seconds=6):
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i',f'sine=frequency={hz}:sample_rate=48000:duration={seconds}','-ac','2','-c:a','pcm_f32le',str(path)],check=True,capture_output=True)
    return Path(path)
def config(tmp_path,**settings):return Config(trim_silence=False,audio_normalize=False,audio6={'enabled':True,'settings':{'normalize':False,'limiter':False,'export_stems':True,**settings},'tracks':[]},work_dir=str(tmp_path))
def plan(cfg):
    p=editplan.build([{'word_id':0,'word':'tidak','start':1.,'end':2.},{'word_id':1,'word':'5 persen','start':4.,'end':5.}],{'start':0.,'end':6.,'title':'Authored audio'},cfg)
    p['display_words']=p['words'];p['captions']={'phrases':[],'censor_intervals':[]};return p
def render(source,cfg,folder):
    p=plan(cfg);mix=premix(source,p,cfg,folder);master=finalize(p,cfg,mix,folder);return p,master
def evidence(name,path,data):
    root=os.environ.get('CLIPPER_M6_EVIDENCE')
    if root:
        r=Path(root);r.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,r/(name+Path(path).suffix));(r/(name+'.json')).write_text(json.dumps(data,indent=2))
def asset(path):return {'id':'asset-authored','path':str(path),'metadata':{'duration':6.},'sha256':content_id(path).removeprefix('sha256:'),'permission':'user_owned','origin':'authored test tone','license':'authored fixture','attribution':'test author'}

def test_normalization_off_target_does_not_change_PCM_or_claim_an_active_target(tmp_path):
    source=tone(tmp_path/'source.wav');outputs=[]
    for target in (-16.,-24.):
        cfg=config(tmp_path,target_lufs=target);p,master=render(source,cfg,tmp_path/str(target));outputs.append(decode(master,seconds=6))
        assert p['audio6']['normalization']['status']=='off' and p['audio6']['meter_pcm']['target_lufs'] is None
        assert p['audio6']['meter_pcm']['stored_target_lufs']==target
    assert np.array_equal(*outputs)

def test_two_pass_normalization_changes_actual_full_mix_by_target_and_measures_final(tmp_path):
    source=tone(tmp_path/'source.wav');music=tone(tmp_path/'music.wav',700);levels=[]
    for target in (-16.,-22.):
        cfg=config(tmp_path,normalize=True,target_lufs=target,limiter=True,ducking=False)
        row=tracks([{'id':'music','role':'music','asset_id':'asset-authored','start':0.,'end':6.,'gain_db':-3.}])[0];row['asset']=asset(music);cfg.audio6['tracks']=[row]
        p,master=render(source,cfg,tmp_path/str(target));meter=p['audio6']['meter_pcm'];levels.append(meter['integrated_lufs'])
        assert abs(meter['integrated_lufs']-target)<.4;assert meter['clipped_samples']==0
        assert p['audio6']['normalization']['stage']=='after all music/SFX/voice/censor inputs'
        evidence('master-'+str(abs(target)),master,meter)
    assert abs((levels[0]-levels[1])-6)<.4

def test_final_limiter_prevents_clipping_after_large_gain_and_added_tracks(tmp_path):
    source=tone(tmp_path/'source.wav');cfg=config(tmp_path,source_gain_db=18,limiter=True,normalize=False,peak_db=-3.)
    p,master=render(source,cfg,tmp_path/'large');meter=p['audio6']['meter_pcm']
    assert p['audio6']['premix_meter']['input_tp']>meter['true_peak_db']
    assert meter['true_peak_db']<=-2.65 and meter['clipped_samples']==0 and meter['sync']['status']=='passed'

def test_music_ducking_follows_quiet_words_and_releases_in_gaps(tmp_path):
    source=tone(tmp_path/'voice.wav');music=tone(tmp_path/'music.wav',700);cfg=config(tmp_path,source_gain_db=-30,duck_db=-20,duck_attack_ms=40,duck_release_ms=100)
    row=tracks([{'id':'m','role':'music','asset_id':'asset-authored','start':0.,'end':6.,'gain_db':0.,'fade_in':0.,'fade_out':0.}])[0];row['asset']=asset(music);cfg.audio6['tracks']=[row]
    p=plan(cfg);premix(source,p,cfg,tmp_path/'duck');samples=decode(p['audio']['stems']['music'],seconds=6)[:,0]
    rms=lambda a,b:np.sqrt(np.mean(samples[round(a*48000):round(b*48000)]**2))
    assert .095<rms(1.2,1.8)/rms(2.8,3.2)<.105
    assert p['audio6']['ducking']['speech_intervals']==[[1.,2.],[4.,5.]]

def test_censor_is_sample_exact_and_exported_stems_do_not_restore_censored_source(tmp_path):
    source=tone(tmp_path/'source.wav');cfg=config(tmp_path);p=plan(cfg);a,b=.500123,.900456;p['captions']['censor_intervals']=[[a,b]]
    premix(source,p,cfg,tmp_path/'censor');before=decode(p['audio6_source']['processed'],seconds=6);voice=decode(p['audio']['stems']['voice'],seconds=6);left,right=round(a*48000),round(b*48000)
    assert np.array_equal(before[:left],voice[:left]) and np.array_equal(before[right:],voice[right:])
    assert np.max(abs(voice[left:right]))==0
    finalize(p,cfg,p['audio']['mix'],tmp_path/'censor')
    with zipfile.ZipFile(p['audio6']['stem_archive']) as z:
        assert z.testzip() is None;manifest=json.loads(z.read('manifest.json'));assert manifest['duration_samples']==288000
        z.extract('stems/voice.wav',tmp_path/'unpacked')
    exported=decode(tmp_path/'unpacked/stems/voice.wav',seconds=6);assert np.max(abs(exported[left:right]))==0

@pytest.mark.parametrize('size',[(360,640),(640,360)])
def test_actual_video_M4_M5_M6_keeps_source_freezes_audio_and_measures_encoded_AAC(tmp_path,size):
    source=video(tmp_path/'source.mp4');before=content_id(source,fresh=True);W,H=size
    cfg=Config(work_dir=str(tmp_path/'work'),out_dir=str(tmp_path/'out'),target_w=W,target_h=H,use_nvenc=False,visual_enabled=False,segmentation_enabled=False,align_selected_clips=False,audio_normalize=False,trim_silence=False,punch_zoom=False,
        audio6={'enabled':True,'settings':{'normalize':True},'tracks':[]},finishing5={'enabled':True,'style':{},'decorations':[]},caption_renderer='ass')
    clip={'start':0.,'end':4.,'title':'Authored M6 video','keywords':[],'_m4_camera':report_for(camera.controls(controls(),4.))}
    result=pipeline.render_clip(source,words(),clip,'m6',cfg);p=json.loads(Path(result['plan_path']).read_text());assert verify(result,fresh=True)
    assert content_id(source,fresh=True)==before and p['caption_checks']['passed']
    meter=p['audio6']['meter_encoded'];assert meter['sync']['status']=='passed' and meter['clipped_samples']==0
    assert abs(meter['integrated_lufs']+16)<1
    assert Path(p['audio6']['master']).is_relative_to(result['artifact_root'])
    assert Path(p['audio6']['stem_archive']).is_file();assert all(Path(x).is_relative_to(result['artifact_root']) for x in p['audio']['stems'].values())
    subprocess.run(['ffmpeg','-nostdin','-v','error','-i',result['absolute_file'],'-f','null','-'],check=True,capture_output=True)
    evidence(f'video-{W}x{H}',result['absolute_file'],meter)

@pytest.mark.parametrize('size',[(360,640),(640,360)])
def test_audio_only_source_audiogram_M5_M6_has_same_duration_and_final_meter(tmp_path,size):
    source=tone(tmp_path/'source.wav',seconds=4);W,H=size
    cfg=Config(work_dir=str(tmp_path/'work'),out_dir=str(tmp_path/'out'),target_w=W,target_h=H,use_nvenc=False,visual_enabled=False,segmentation_enabled=False,align_selected_clips=False,source_media_kind='audio',trim_silence=False,punch_zoom=False,
        audio6={'enabled':True,'settings':{'normalize':True},'tracks':[]},finishing5={'enabled':True,'style':{},'decorations':[]})
    result=pipeline.render_clip(source,words(),{'start':0,'end':4,'title':'Authored audiogram'},'m6-audio',cfg);p=json.loads(Path(result['plan_path']).read_text())
    assert verify(result,fresh=True) and p['source_kind']=='audio' and p['audio6']['meter_encoded']['sync']['status']=='passed'
    evidence(f'audiogram-{W}x{H}',result['absolute_file'],p['audio6']['meter_encoded'])

def test_actual_audio_job_publishes_AB_and_stems_without_ASR_or_replacing_final(tmp_path):
    from ..studio_worker import execute
    svc=make_studio(tmp_path)
    try:
        change(svc,{'op':'m6_enable','enabled':True});d=svc.store.get(svc.test_pid);before=copy.deepcopy(d['clips'][svc.test_cid]['variants']['portrait'].get('result'))
        job=svc.enqueue(svc.test_pid,'audio_m6',svc.test_cid,'portrait',d['revision'],{'seconds':2.});result=execute(svc,job)
        current=svc.store.get(svc.test_pid)['clips'][svc.test_cid]['variants']['portrait']
        assert current['audio6']['review']['master']==result['master'] and Path(result['stem_archive']).is_file()
        with zipfile.ZipFile(result['stem_archive']) as z:
            manifest=json.loads(z.read('manifest.json'));assert manifest['revision_context']['input_revision']==d['revision']
            assert manifest['revision_context']['variant_id']=='portrait' and manifest['revision_context']['dependency']==result['dependency']
            assert manifest['source_content_id'].startswith('sha256:')
        assert current.get('result')==before and result['duration']==2.
        assert verify(result,fresh=True)
    finally:svc.queue.close()

@pytest.mark.parametrize('settings',[
    {'denoise':'fft'},{'denoise':'nlmeans'},{'hum_hz':50},{'hum_hz':60},
    {'enhancement':True},{'eq_bands':[{'hz':250,'gain_db':-6,'q':1}]},
    {'compressor':True,'compressor_threshold_db':-30},
    {'pitch_semitones':3},{'dereverb':True,'dereverb_strength':.35}])
def test_actual_restoration_filter_paths_preserve_finite_samples_clock_and_original(tmp_path,settings):
    from ..audio6 import source_stem
    source=tone(tmp_path/'source.wav',seconds=1);before=content_id(source,fresh=True)
    cfg=config(tmp_path,**settings);p=plan(cfg);p['duration']=1.;p['spans']=[{'start':0.,'end':1.,'source_start':0.,'source_end':1.}];p['words']=[]
    out=source_stem(source,p,cfg,tmp_path/'restoration');samples=decode(out,seconds=1)
    assert samples.shape==(48000,2) and np.isfinite(samples).all() and content_id(source,fresh=True)==before
    assert Path(p['audio6_source']['before']).is_file() and not p['audio6_source']['normalization_applied']

def test_unavailable_separation_blocks_before_spawning_or_downloading(tmp_path,monkeypatch):
    from .. import audio6_models
    from ..audio6_contract import DEFAULTS
    source=tone(tmp_path/'source.wav',seconds=1)
    monkeypatch.setattr(audio6_models.importlib.util,'find_spec',lambda name:None)
    monkeypatch.setattr(audio6_models.subprocess,'run',lambda *a,**k:pytest.fail('No separation/download subprocess without local runtime'))
    with pytest.raises(ValueError,match='lokal'):audio6_models.separate(source,tmp_path/'separation',DEFAULTS)

def test_model_availability_requires_selected_model_and_all_bag_members(tmp_path,monkeypatch):
    from .. import audio6_models
    from ..audio6_contract import DEFAULTS
    pytest.importorskip('yaml')
    monkeypatch.setattr(audio6_models.importlib.util,'find_spec',lambda name:object())
    s={**DEFAULTS,'model_directory':str(tmp_path),'model_name':'htdemucs'}
    (tmp_path/'unrelated.th').write_bytes(b'not loaded')
    assert audio6_models.availability(s)['status']=='unavailable'
    (tmp_path/'htdemucs.yaml').write_text('models: [unrelated, missing]\n')
    assert audio6_models.availability(s)['status']=='unavailable'
    (tmp_path/'missing.th').write_bytes(b'not loaded')
    assert audio6_models.availability(s)['status']=='ready' and not audio6_models.availability(s)['actual_inference_performed']
    (tmp_path/'htdemucs.yaml').write_text('models: [broken')
    assert audio6_models.availability(s)['status']=='unavailable'

def test_reviewed_dubbing_replaces_only_source_interval_keeps_separate_stem_and_transcript(tmp_path):
    source=tone(tmp_path/'source.wav',250);dub=tone(tmp_path/'dub.wav',700);cfg=config(tmp_path)
    row=tracks([{'id':'dub','role':'dubbing','asset_id':'asset-authored','start':1.,'end':3.,'gain_db':0.,'language':'id','speaker_id':'S1','reviewed':True,'replace_source':True}])[0]
    row['asset']=asset(dub);cfg.audio6['tracks']=[row];p=plan(cfg);before=copy.deepcopy(p['words'])
    premix(source,p,cfg,tmp_path/'dub');voice=decode(p['audio']['stems']['voice'],seconds=6)
    extra=decode(next(v for k,v in p['audio']['stems'].items() if k.startswith('dubbing-')),seconds=6)
    assert np.max(abs(voice[48000:144000]))==0 and np.max(abs(voice[10000:20000]))>.01
    assert np.max(abs(extra[60000:130000]))>.01 and np.max(abs(extra[:48000]))==0
    assert p['words']==before and p['audio6']['events'][0]['language']=='id'

def test_M1_speed_reverse_freeze_and_M6_audio_job_use_same_output_clock(tmp_path):
    from ..studio_worker import execute
    svc=make_studio(tmp_path)
    try:
        change(svc,{'op':'editor_segments','segments':[{'id':'fast','start':2.,'end':4.,'speed':2.},{'id':'reverse','start':0.,'end':2.,'reverse':True},
            {'id':'freeze','start':2.,'end':2.1,'kind':'freeze','freeze_duration':.5}]})
        change(svc,{'op':'m6_settings','values':{'normalize':False,'limiter':False}});change(svc,{'op':'m6_enable','enabled':True})
        d=svc.store.get(svc.test_pid);job=svc.enqueue(svc.test_pid,'audio_m6',svc.test_cid,'portrait',d['revision'],{'seconds':0});result=execute(svc,job)
        samples=decode(result['master'],seconds=result['duration'])
        assert result['duration']==pytest.approx(3.5,abs=1/30) and samples.shape[0]==round(result['duration']*48000)
        assert np.max(abs(samples[-8000:]))<1e-6 and np.max(abs(samples[4800:40000]))>.01
        assert result['meter']['sync']['status']=='passed'
    finally:svc.queue.close()

def test_local_music_index_filters_by_mood_and_duration_without_network(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from ..api_studio import create_router
    svc=make_studio(tmp_path)
    try:
        audio=tone(tmp_path/'owned.wav',seconds=4);app=FastAPI();app.include_router(create_router(svc));client=TestClient(app)
        response=client.post('/api/studio/audio6/assets',json={'path':str(audio),'metadata':{'name':'Musik tenang','tags':['calm'],'permission':'user_owned','origin':'authored test tone','license':'owned'}})
        assert response.status_code==200,response.text
        rows=client.get('/api/studio/audio6/assets',params={'q':'calm','min_seconds':3,'max_seconds':5}).json()['assets']
        assert len(rows)==1 and rows[0]['origin']=='authored test tone' and rows[0]['permission']=='user_owned'
        assert client.get('/api/studio/audio6/assets',params={'min_seconds':5,'max_seconds':6}).json()['assets']==[]
    finally:svc.queue.close()
