"""Independent expected-behavior probes. Failures are reproduced audit findings.
Authored tones/geometry validate mechanics, never human-speech quality.
"""
import copy,json,sys,shutil,os
from pathlib import Path
from dataclasses import replace
import numpy as np
import pytest
REPO=Path(__file__).resolve().parents[2]
from clipper.tests._m4_fixture import make_studio,change
from clipper.tests.test_m6_media import tone,config,plan,asset
from clipper.audio6_dsp import decode
from clipper.audio6_contract import tracks
from clipper.audio6 import premix
from clipper.studio_worker import execute
from clipper.finishing5_service import assets
import tempfile
_EVID_TEMP=tempfile.TemporaryDirectory(prefix='clipper-m6-repairs-')
EVID=Path(_EVID_TEMP.name)
def evidence(name,data):
 (EVID/(name+'.json')).write_text(json.dumps(data,indent=2,ensure_ascii=False))
def document(s):return s.store.get(s.test_pid)
def queue(s):return execute(s,s.enqueue(s.test_pid,'audio_m6',s.test_cid,'portrait',document(s)['revision'],{'seconds':0}))
def register(s,path):return assets(s).register(str(path),{'name':'Authored audit asset','origin':'deterministic FFmpeg sine','license':'audit authored','permission':'user_owned','tags':['audit']})

@pytest.fixture
def svc(tmp_path):
 s=make_studio(tmp_path);yield s;s.queue.close()

def test_caption_mute_must_not_remove_source_speech_from_music_ducking(svc,tmp_path):
 a=register(svc,tone(tmp_path/'music.wav',900,4))
 change(svc,{'op':'m6_tracks','values':[{'id':'music','role':'music','asset_id':a['id'],'start':0.,'end':4.,'fade_in':0.,'fade_out':0.,'gain_db':-6}]})
 change(svc,{'op':'m6_settings','values':{'normalize':False,'limiter':False,'duck_db':-20}});change(svc,{'op':'m6_enable','enabled':True})
 normal=queue(svc);p1=json.loads(Path(normal['report_path']).read_text());m1=decode(p1['audio']['stems']['music'],seconds=4)
 change(svc,{'op':'track','track':'captions','values':{'mute':True}})
 muted=queue(svc);p2=json.loads(Path(muted['report_path']).read_text());m2=decode(p2['audio']['stems']['music'],seconds=4)
 rms=lambda a:float(np.sqrt(np.mean(a[24000:72000]**2)));shutil.copyfile(p1['audio']['stems']['music'],EVID/'caption-on-music.wav');shutil.copyfile(p2['audio']['stems']['music'],EVID/'caption-muted-music.wav');data={'caption_on_speech':p1['audio6']['speech_intervals'],'caption_muted_speech':p2['audio6']['speech_intervals'],'music_rms_on':rms(m1),'music_rms_muted':rms(m2),'source_before_identical':np.array_equal(decode(normal['before'],seconds=4),decode(muted['before'],seconds=4)),'source_still_audible_after_caption_mute':float(np.max(abs(decode(muted['before'],seconds=4)[24000:72000])))>0.01,'source_transcript_word_count':len(svc.transcript(document(svc))['words'])};evidence('caption-mute-ducking',data)
 assert data['music_rms_muted']<=data['music_rms_on']*1.05, data

def test_caption_mute_must_not_bypass_unreviewed_SFX_critical_word_guard(svc,tmp_path):
 from clipper.studio_service import identifier
 rows=[{'word_id':0,'word':'tidak','start':.2,'end':1.8},{'word_id':1,'word':'5 persen','start':2.2,'end':3.8}]
 take=svc.store.save_transcript(svc.test_pid,{'words':rows,'raw_words':rows,'duration':4.})
 svc.store.mutate(svc.test_pid,document(svc)['revision'],identifier('audit-critical'),{},lambda d:d.update(transcript_id=take,transcript_revision=d['transcript_revision']+1))
 a=register(svc,tone(tmp_path/'sfx.wav',1200,4));change(svc,{'op':'m6_tracks','values':[{'id':'sfx','role':'sfx','asset_id':a['id'],'start':.5,'end':1.1,'gain_db':-12.,'reviewed':False}]});change(svc,{'op':'m6_enable','enabled':True})
 with pytest.raises(ValueError,match='angka/negasi'):queue(svc)
 change(svc,{'op':'track','track':'captions','values':{'mute':True}})
 rejected=False
 try:r=queue(svc);p=json.loads(Path(r['report_path']).read_text());events=p['audio6']['sfx_events']
 except ValueError:rejected=True;events=[]
 evidence('caption-mute-sfx',{'rejected':rejected,'events':events,'source_words':rows})
 assert rejected,'Caption mute allowed unreviewed SFX over the unchanged negation audio'

def test_short_dubbing_asset_must_not_silently_replace_remaining_source_with_zeros(tmp_path):
 source=tone(tmp_path/'source.wav',250,6);dub=tone(tmp_path/'dub.wav',700,1);cfg=config(tmp_path)
 row=tracks([{'id':'dub','role':'dubbing','asset_id':'short','start':1.,'end':5.,'fade_in':0.,'fade_out':0.,'gain_db':0.,'language':'id','speaker_id':'S1','reviewed':True,'replace_source':True}])[0];row['asset']={**asset(dub),'metadata':{'duration':1.}};cfg.audio6['tracks']=[row];p=plan(cfg);rejected=False
 try:
  premix(source,p,cfg,tmp_path/'render');voice=decode(p['audio']['stems']['voice'],seconds=6);added=decode(next(v for k,v in p['audio']['stems'].items() if k.startswith('dubbing-')),seconds=6);lost=float(np.max(abs(voice[round(2.2*48000):round(4.8*48000)]+added[round(2.2*48000):round(4.8*48000)])))
 except ValueError:rejected=True;lost=None
 if not rejected:
  shutil.copyfile(p['audio']['stems']['voice'],EVID/'short-dubbing-source-muted.wav');shutil.copyfile(next(v for k,v in p['audio']['stems'].items() if k.startswith('dubbing-')),EVID/'short-dubbing-replacement.wav')
 evidence('short-dubbing',{'rejected':rejected,'source_interval':[1,5],'asset_duration':1,'peak_replacement_after_asset_ended':lost})
 assert rejected or lost>.001,'Three seconds of source speech replaced by padded digital silence without warning'

def test_source_loop_phase_must_follow_crossfade_shortened_period_after_trim(tmp_path):
 from clipper.audio6 import _track
 from clipper.audio6_dsp import loop,write
 rate=48000;t=np.arange(rate)/rate;x=np.column_stack((.1*np.sin(2*np.pi*(300*t+150*t*t)),.1*np.cos(2*np.pi*(400*t+100*t*t)))).astype(np.float32);path=write(tmp_path/'chirp.wav',x)
 base=tracks([{'id':'music','role':'music','asset_id':'a','start':0.,'end':4.,'timebase':'source','loop':True,'loop_crossfade':.2,'fade_in':0.,'fade_out':0.,'gain_db':0.}])[0]
 # Canonical source slice starts at source second 1, after the first overlap.
 row={**base,'event_id':'trimmed','asset':{'path':path,'metadata':{'duration':1.}},'original_asset_start':0.,'asset_start':.9,'asset_seconds':1.,'start':0.,'end':1.,'start_sample':0,'end_sample':rate,'reverse':False,'rate':1.}
 actual=decode(_track(row,{'duration':1.},tmp_path),seconds=1.)
 expected=loop(x,rate*2,.2)[round(.9*rate):round(1.9*rate)];write(EVID/'loop-cut-actual.wav',actual);write(EVID/'loop-cut-reference.wav',expected);error=float(np.sqrt(np.mean((actual-expected)**2)));evidence('loop-phase',{'rms_error_against_full_source_loop_slice':error,'expected_offset_seconds':.9,'loop_period_seconds':.8})
 assert error<1e-6,'Loop started at a different phase after a source cut'

def test_new_voiceover_must_not_modify_locked_music_through_ducking(svc,tmp_path):
 a=register(svc,tone(tmp_path/'extra.wav',700,4));change(svc,{'op':'m6_enable','enabled':True});change(svc,{'op':'track','track':'music','values':{'locked':True}})
 before=document(svc);rejected=False
 try:change(svc,{'op':'m6_tracks','values':[{'id':'extra','role':'voiceover','asset_id':a['id'],'start':1.8,'end':2.2,'fade_in':0.,'fade_out':0.}]})
 except ValueError:rejected=True
 evidence('music-lock-voiceover',{'rejected':rejected,'revision_before':before['revision'],'revision_after':document(svc)['revision'],'music_locked':True})
 assert rejected,'Narration intervals change music ducking despite music lock'

def test_separation_change_must_check_music_lock(svc):
 change(svc,{'op':'m6_enable','enabled':True});change(svc,{'op':'track','track':'music','values':{'locked':True}});rejected=False
 try:change(svc,{'op':'m6_settings','values':{'separation':'demucs'}})
 except ValueError:rejected=True
 evidence('music-lock-separation',{'rejected':rejected,'music_locked':True,'separation':svc.config(document(svc),svc.test_cid,'portrait').audio6['settings']['separation']})
 assert rejected,'Separation creates/replaces the residual music stem without honoring the music lock'

def test_audio_review_must_use_same_material_pause_policy_as_final_video(svc,monkeypatch):
 from clipper import pipeline,composition,ffmpeg_util
 from clipper.studio_exchange import render_words
 from clipper.studio_service import identifier
 rows=[{'word_id':0,'word':'awal','start':.2,'end':.6},{'word_id':1,'word':'akhir','start':3.3,'end':3.8}]
 take=svc.store.save_transcript(svc.test_pid,{'words':rows,'raw_words':rows,'duration':4.})
 svc.store.mutate(svc.test_pid,document(svc)['revision'],identifier('audit-material'),{},lambda d:d.update(transcript_id=take,transcript_revision=d['transcript_revision']+1))
 change(svc,{'op':'settings','values':{'source_kind':'auto','trim_silence':True,'preserve_material_pauses':True}});change(svc,{'op':'m6_enable','enabled':True})
 d=document(svc);cfg=svc.config(d,svc.test_cid,'portrait');clip={k:copy.deepcopy(v) for k,v in d['clips'][svc.test_cid].items() if k!='variants'};words=render_words(svc.transcript(d,svc.test_cid,'portrait'),d,clip,cfg)
 # Supplied controlled composition evidence triggers the documented auto pause
 # policy. This is a planning/integration probe, not a detector-quality test.
 def material(_source,p,_cfg,_info):p['shots']=[{'start':0.,'end':p['duration'],'has_material':True}]
 monkeypatch.setattr(composition,'analyze',material)
 _,final=pipeline.source_plan(d['source']['path'],words,clip,cfg,ffmpeg_util.probe(d['source']['path']),context_words=words)
 review=queue(svc);report=json.loads(Path(review['report_path']).read_text());evidence('review-final-clock',{'controlled_material_evidence':True,'final_duration':final['duration'],'review_duration':review['duration'],'final_spans':final['spans'],'review_spans':report['spans']})
 assert review['duration']==final['duration'],'Audio review exported a different timeline than final video under auto material pause protection'

def test_voiceover_music_lock_has_audible_consequence(svc,tmp_path):
 music=register(svc,tone(tmp_path/'bg.wav',900,4));narr=register(svc,tone(tmp_path/'narr.wav',700,4))
 base={'id':'music','role':'music','asset_id':music['id'],'start':0.,'end':4.,'fade_in':0.,'fade_out':0.}
 change(svc,{'op':'m6_tracks','values':[base]});change(svc,{'op':'m6_settings','values':{'duck_db':-20.,'duck_attack_ms':5.,'duck_release_ms':20.}});change(svc,{'op':'m6_enable','enabled':True})
 before=queue(svc);p1=json.loads(Path(before['report_path']).read_text());a=decode(p1['audio']['stems']['music'],seconds=4)
 change(svc,{'op':'track','track':'music','values':{'locked':True}})
 rejected=False
 try:change(svc,{'op':'m6_tracks','values':[base,{'id':'vo','role':'voiceover','asset_id':narr['id'],'start':1.9,'end':2.1,'fade_in':0.,'fade_out':0.}]})
 except ValueError:rejected=True
 if rejected:return
 after=queue(svc);p2=json.loads(Path(after['report_path']).read_text());b=decode(p2['audio']['stems']['music'],seconds=4)
 rms=lambda x:float(np.sqrt(np.mean(x[round(1.94*48000):round(2.06*48000)]**2)))
 evidence('music-lock-real-pcm',{'before_rms':rms(a),'after_rms':rms(b),'relative_gain_db':20*np.log10(rms(b)/rms(a)),'music_locked':True,'command_rejected':False})
 assert np.array_equal(a,b),'Locked music changed by 20 dB through added narration ducking'

def test_internal_speed_slices_must_not_reapply_track_fades_every_four_frames(tmp_path):
 from clipper.editor_contract import validate_segments,build_clock
 from clipper.audio6 import _track,_sum
 from clipper.audio6_plan import build
 audio=tone(tmp_path/'voiceover.wav',700,4)
 row=tracks([{'id':'vo','role':'voiceover','asset_id':'a','start':0.,'end':4.,'timebase':'source','fade_in':.08,'fade_out':.15,'gain_db':0.}])[0];row['asset']={**asset(audio),'metadata':{'duration':4.}}
 cfg=config(tmp_path);cfg.audio6['tracks']=[row]
 # A constant speed curve must be semantically identical to speed=1. It still
 # generates the canonical four-frame internal slices used by real ramps.
 clock=build_clock(validate_segments([{'id':'ramp','start':0.,'end':4.,'speed_curve':[{'offset':0.,'speed':1.},{'offset':4.,'speed':1.}]}],{'start':0,'end':4},{}),30)
 p={'duration':4.,'fps':30,'spans':[{'start':0.,'end':4.,'source_start':0.,'source_end':4.,'kind':'body'}],'words':[],'editor':{'clock':clock}}
 mapped=build(p,cfg);folder=tmp_path/'pieces';folder.mkdir();paths=[]
 for i,event in enumerate(mapped['events']):
  event.update(event_id='piece-'+str(i),original_asset_start=0.);paths.append(_track(event,p,folder))
 mixed=decode(_sum(paths,folder/'combined.wav',4),seconds=4)
 regular={**row,'event_id':'regular','original_asset_start':0.,'asset_start':0.,'asset_seconds':4.,'start_sample':0,'end_sample':192000,'rate':1.,'reverse':False};direct=decode(_track(regular,p,folder),seconds=4)
 x=mixed[round(.3*48000):round(3.7*48000)];y=direct[round(.3*48000):round(3.7*48000)];ratio=float(np.sqrt(np.mean(x*x))/np.sqrt(np.mean(y*y)));shutil.copyfile(folder/'combined.wav',EVID/'ramp-actual.wav');shutil.copyfile(folder/'regular-aligned.wav',EVID/'ramp-reference.wav');evidence('ramp-repeated-fades',{'internal_slices':len(mapped['events']),'output_duration':4.,'interior_rms_ratio':ratio,'relative_gain_db':float(20*np.log10(ratio)),'fade_in':.08,'fade_out':.15,'clock_curve':'1x to 1x; no semantic speed change'})
 assert ratio>.99,'Track fade was restarted at every internal clock slice, repeatedly attenuating continuous narration'

def test_historical_M0_M5_builder_must_not_mix_M6_core_without_M6_modules(tmp_path):
 import contextlib,io,subprocess,tarfile
 from tools import build_m0_m5_repair_release as builder
 pkg=tmp_path/'rebuilt-old-package'
 with contextlib.redirect_stdout(io.StringIO()):builder.build(pkg,'0'*40)
 from clipper.tests.frozen_release import _restore
 meta=json.loads((REPO/'docs/releases/m6_m5_base_provenance.json').read_text())
 target=_restore(tmp_path/'baseline',REPO/'docs/releases/m6_m5_base.zip',meta)
 for source in (pkg/'payload').rglob('*'):
  if source.is_file():dest=target/source.relative_to(pkg/'payload');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
 code="import sys;sys.path.insert(0,sys.argv[1]);from clipper.studio_service import StudioService;from clipper.config import Config;from pathlib import Path;r=Path(sys.argv[1]);s=StudioService(r,Config(work_dir=str(r/'work'),out_dir=str(r/'out')),autostart=False);s.config({'project_id':'audit','source':{},'clips':{}});s.queue.close()"
 q=subprocess.run([sys.executable,'-I','-c',code,str(target)],cwd=target,capture_output=True,text=True)
 evidence('historical-builder-mixed-release',{'manifest_version':json.loads((pkg/'manifest.json').read_text())['version'],'M6_module_in_payload':(pkg/'payload/clipper/audio6_service.py').exists(),'core_mentions_audio6': 'audio6_service' in (target/'clipper/studio_service.py').read_text(),'runtime_returncode':q.returncode,'runtime_stderr':q.stderr})
 assert q.returncode==0,q.stderr

def test_smooth_join_control_must_reach_actual_M1_cut_boundaries(svc):
 from clipper.studio_service import identifier
 rows=[{'word_id':0,'word':'awal','start':.2,'end':.5},{'word_id':1,'word':'akhir','start':2.5,'end':2.8}]
 take=svc.store.save_transcript(svc.test_pid,{'words':rows,'raw_words':rows,'duration':4.})
 svc.store.mutate(svc.test_pid,document(svc)['revision'],identifier('audit-cut'),{},lambda d:d.update(transcript_id=take,transcript_revision=d['transcript_revision']+1))
 change(svc,{'op':'editor_segments','segments':[{'id':'first','start':0.,'end':1.},{'id':'later','start':2.,'end':3.}]})
 change(svc,{'op':'m6_settings','values':{'smooth_ms':0.,'normalize':False,'limiter':False}});change(svc,{'op':'m6_enable','enabled':True});a=queue(svc);p1=json.loads(Path(a['report_path']).read_text());x=decode(a['processed'],seconds=2)
 change(svc,{'op':'m6_settings','values':{'smooth_ms':15.}});b=queue(svc);p2=json.loads(Path(b['report_path']).read_text());y=decode(b['processed'],seconds=2)
 evidence('smooth-M1-cut',{'output_duration':2.,'actual_M1_cut':1.,'source_spans_in_plan':p2['spans'],'M1_clock_slices':p2['editor']['clock']['slices'],'join_policy':p2['audio6_source']['join_policy'],'processed_PCM_identical_at_0_and_15ms':np.array_equal(x,y),'word_times':p2['words']})
 shutil.copyfile(a['processed'],EVID/'M1-cut-smooth-0ms.wav');shutil.copyfile(b['processed'],EVID/'M1-cut-smooth-15ms.wav')
 assert not np.array_equal(x,y),'Smooth control never reaches the actual M1 cut even though a speech gap covers the join'
