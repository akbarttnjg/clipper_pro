import copy
from pathlib import Path
import subprocess
from unittest.mock import patch
import pytest
from ..selection_signals import voice_markers,audio_events,sample_frames,collect
from ..selection_contract import constraints
from ._m3_fixture import reference,config


def test_voice_marker_uses_actual_cue_time_without_invented_subword_offsets():
    data=reference(['Saat ini saya berkata clip that untuk penanda.'])
    result=voice_markers(data['words'],['clip that'],'source')
    assert result[0]['time']==.2 and result[0]['end']==5.8;assert result[0]['resolution'].startswith('source_units')


def test_voice_marker_can_cross_separate_words_and_does_not_match_substring():
    words=[{'word_id':1,'word':'clip','start':2.,'end':2.4},{'word_id':2,'word':'that','start':2.5,'end':3.}]
    assert voice_markers(words,['clip that'],'source')[0]['word_ids']==[1,2]
    assert voice_markers([{'word_id':1,'word':'clipping that','start':0,'end':1}],['clip that'],'source')==[]


def test_actual_selected_audio_energy_event_is_not_emotion_inference(tmp_path):
    source=tmp_path/'energy.wav';subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
        '-i','sine=frequency=440:duration=6','-af',"volume=0.1:enable='lt(t,3)',volume=4:enable='gte(t,3)'",str(source)],check=True,capture_output=True)
    events,receipt=audio_events(source,0,0,6)
    assert events and any(2<=e['time']<=4 for e in events);assert all(e['emotion'] is None for e in events)
    assert receipt['measured_seconds']==6 and receipt['emotion_inference']=='not_performed'


def test_audio_decode_failure_is_not_reported_as_zero_energy(tmp_path):
    bad=tmp_path/'bad.wav';bad.write_bytes(b'not an audio file')
    with pytest.raises(ValueError,match='gagal'):audio_events(bad,0,0,4)


def test_real_frames_keep_hash_source_clock_and_unknown_object_labels(tmp_path):
    video=tmp_path/'frames.mp4';subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','color=c=red:s=160x90:r=15:d=2',
        '-f','lavfi','-i','color=c=blue:s=160x90:r=15:d=2','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0','-c:v','libx264','-threads','1',str(video)],check=True,capture_output=True)
    rows,events=sample_frames(video,[.5,2.5],tmp_path/'frames','source')
    assert all(Path(r['path']).is_file() and len(r['sha256'])==64 for r in rows);assert rows[0]['time']==.5
    assert rows[1]['pixel_change']>.18;assert events[0]['kind']=='sampled_visual_change';assert rows[0]['objects']==[] and rows[0]['model'] is None


def test_audio_only_source_never_calls_face_or_frame_detector(tmp_path):
    from ._m3_fixture import wav
    source=wav(tmp_path/'source.wav',seconds=6);request=constraints({'provider':'rules','retrieval':'lexical','min_seconds':1,'max_seconds':6},6)
    with patch('clipper.selection_signals.sample_frames',side_effect=AssertionError('No video invented')):result=collect(source,'source',request,[],config(tmp_path),kind='audio')
    assert result['frames']==[];assert result['receipt']['objects']=='not_inferred'


def test_query_change_reuses_measured_audio_and_frames(tmp_path):
    from ._m3_fixture import wav
    source=wav(tmp_path/'source.wav',seconds=6);cfg=config(tmp_path);request=constraints({'provider':'rules','retrieval':'lexical','min_seconds':1,'max_seconds':6},6)
    first=collect(source,'source',request,[],cfg,kind='audio');request['query']='topik berbeda';second=collect(source,'source',request,[],cfg,kind='audio')
    assert not first['cache_reused'] and second['cache_reused']


def test_disabled_signal_scan_still_preserves_transcript_voice_marker(tmp_path):
    request=constraints({'signals':False,'min_seconds':1,'max_seconds':6},6);data=reference(['clip that.'])
    result=collect('unused','source',request,data['words'],config(tmp_path),kind='audio')
    assert result['status']=='disabled' and result['events'][0]['kind']=='voice_marker'
