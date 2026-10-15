import copy
import math
import pytest
from dataclasses import replace
from ..config import Config
from ..audio6_contract import settings,tracks,effective
from ..audio6_plan import events,speech_intervals,build
from ..editor_contract import validate_segments,build_clock

def track(**values):
    return tracks([{'id':'music','role':'music','asset_id':'asset-test','start':0.,'end':4.,**values}])[0]

@pytest.mark.parametrize('value',[{'normalize':1},{'target_lufs':float('nan')},{'source_gain_db':float('inf')},{'gain_db':0},{'denoise':'automatic'},{'model_name':'../remote'},{'hum_hz':55},{'eq_bands':[{'hz':80,'gain_db':2}]},{'limiter':'false'},{'peak_db':0.},{'eq_bands':[{'hz':float('nan'),'gain_db':0,'q':1}]}])
def test_audio_schema_rejects_ambiguous_unsafe_or_nonfinite_controls(value):
    with pytest.raises(ValueError):settings(value)

def test_sparse_settings_do_not_clamp_other_fields_or_enable_normalization():
    cfg=Config(audio_normalize=False,audio_target_lufs=-18,audio6={'enabled':True,'settings':{'source_gain_db':3}})
    result=effective(cfg);assert result['source_gain_db']==3 and result['target_lufs']==-18 and not result['normalize']
    assert settings({'noise_reduction_db':8})=={'noise_reduction_db':8.}

@pytest.mark.parametrize('values',[{'end':0},{'id':'../track'},{'gain_db':True},{'timebase':'wall_time'},{'loop':True,'role':'sfx'},{'role':'dubbing'},{'replace_source':True},{'beat_snap':True},{'beat_snap':True,'beat_bpm':90,'timebase':'source'},{'fade_in':3,'fade_out':2}])
def test_track_contract_requires_exact_clock_review_and_valid_duration(values):
    with pytest.raises(ValueError):track(**values)

def test_dubbing_has_own_language_speaker_review_and_does_not_edit_source():
    row=track(role='dubbing',language='id',speaker_id='S1',reviewed=True,replace_source=True)
    assert row['role']=='dubbing' and row['speaker_id']=='S1'

def test_duplicate_track_identity_and_unknown_fields_are_rejected():
    row=track()
    with pytest.raises(ValueError):tracks([row,row])
    with pytest.raises(ValueError):track(secret_script='run()')

def test_beat_snap_records_requested_and_effective_start_without_duration_growth():
    row=track(start=.24,end=3.24,beat_snap=True,beat_bpm=120)
    actual=events({'duration':4,'spans':[]},row)[0]
    assert actual['requested_start']==.24 and actual['start']==0 and actual['end']==3
    assert actual['start_sample']==0 and actual['end_sample']==144000

def test_source_tracks_follow_reordered_reverse_speed_and_skip_freeze():
    clip={'start':0,'end':8};rows=validate_segments([
        {'id':'later','start':4,'end':8,'speed':2},
        {'id':'earlier','start':0,'end':4,'reverse':True},
        {'id':'frozen','start':2,'end':2.1,'kind':'freeze','freeze_duration':1}],clip,{})
    clock=build_clock(rows,30);plan={'duration':clock['duration'],'editor':{'clock':clock}}
    row=track(start=1,end=6,timebase='source');actual=events(plan,row)
    assert len(actual)==2
    assert actual[0]['start']==0 and actual[0]['end']==1 and actual[0]['rate']==2 and not actual[0]['reverse']
    assert actual[1]['start']==2 and actual[1]['end']==5 and actual[1]['reverse']
    assert all(a['end_sample']<=6*48000 for a in actual)

def test_speech_ducking_uses_output_times_not_nested_source_alignment():
    plan={'duration':2,'display_words':[{'word':'tidak','start':.2,'end':.8,'aligned_words':[{'word':'tidak','start':100.2,'end':100.8}]}]}
    assert speech_intervals(plan)==[[.2,.8]]

def test_disabled_sfx_and_muted_track_create_zero_events_and_no_asset_reference():
    row=track(role='sfx',gain_db=-25);p={'duration':4,'spans':[{'start':0,'end':4,'source_start':0,'source_end':4}],'words':[]}
    cfg=Config(audio6={'enabled':True,'settings':{'sfx_enabled':False},'tracks':[row]})
    assert build(p,cfg)['events']==[]
    cfg=replace(cfg,audio6={**cfg.audio6,'settings':{},'track_state':{'sfx':False}})
    assert build(p,cfg)['events']==[]

def test_unreviewed_SFX_on_negation_or_number_is_rejected():
    row=track(role='sfx');p={'duration':4,'spans':[{'start':0,'end':4,'source_start':0,'source_end':4}],'words':[{'word':'tidak 5 persen','start':1,'end':2}]}
    cfg=Config(audio6={'enabled':True,'settings':{},'tracks':[row]})
    with pytest.raises(ValueError,match='angka/negasi'):build(p,cfg)
    row['reviewed']=True;assert len(build(p,cfg)['events'])==1
