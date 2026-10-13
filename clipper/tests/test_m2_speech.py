"""Backend protocol tests use explicit doubles; audiogram/clock tests use real FFmpeg."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from .test_m2_transcripts import M2Fixture
from ..config import Config
from .. import speech_m2,transcribe,pipeline,bilingual_m2


class SpeechCase(unittest.TestCase):
    def model(self,device_failure=False):
        calls=[]
        class Model:
            def __init__(self,*args,**kwargs):
                calls.append(('model',args,kwargs))
                if device_failure and kwargs['device']=='cuda':raise RuntimeError('controlled CUDA failure')
            def transcribe(self,*args,**kwargs):
                calls.append(('transcribe',args,kwargs));word=types.SimpleNamespace(word='tidak',start=.2,end=.7,probability=.8);seg=types.SimpleNamespace(text='tidak',start=.2,end=.7,words=[word]);return iter([seg]),types.SimpleNamespace(language='id',language_probability=.96,duration=1.)
        return Model,calls
    def exercise(self,device='cpu',fail=False,allow=True):
        model,calls=self.model(fail);cfg=Config(whisper_device=device,whisper_isolate=False,asr_second_pass=False,allow_backend_fallback=allow)
        # Explicit doubles validate one gate and receipt propagation, not neural quality.
        with patch.dict(sys.modules,{'faster_whisper':types.SimpleNamespace(WhisperModel=model)}),patch('clipper.speech_m2.vad_input',return_value=([0.]*16000,[.1,.9],{'provider':'test_double','gate_count':1})):
            result=transcribe._run('fixture',cfg)
        return result,calls
    def test_single_vad_gate_and_source_language_not_output_translation(self):
        result,calls=self.exercise();call=next(c for c in calls if c[0]=='transcribe');self.assertFalse(call[2]['vad_filter']);self.assertEqual(call[2]['clip_timestamps'],[.1,.9]);self.assertEqual(call[2]['task'],'transcribe');self.assertEqual(result['source_language'],'id');self.assertEqual(result['output_language'],'source');self.assertEqual(result['language_probability'],.96)
    def test_cpu_receipt_actual_compute_and_local_only(self):
        result,calls=self.exercise();self.assertEqual(result['runtime_receipt']['actual_device'],'cpu');self.assertEqual(result['runtime_receipt']['actual_compute_type'],'int8');self.assertTrue(calls[0][2]['local_files_only']);self.assertIn('peak_process_rss_bytes',result['runtime_receipt']['memory'])
    def test_cuda_failure_cpu_receipt_has_reason(self):
        result,calls=self.exercise('cuda',True);self.assertEqual(result['runtime_receipt']['actual_device'],'cpu');self.assertIn('controlled CUDA failure',result['runtime_receipt']['fallback_reason'])
    def test_cuda_required_failure_does_not_report_cpu_success(self):
        with self.assertRaises(RuntimeError):self.exercise('cuda',True,False)
    def test_no_vad_speech_means_no_asr_inference(self):
        model,calls=self.model()
        with patch.dict(sys.modules,{'faster_whisper':types.SimpleNamespace(WhisperModel=model)}),patch('clipper.speech_m2.vad_input',return_value=([0.]*16000,[],{'provider':'test_double','gate_count':1})):
            result=transcribe._run('fixture',Config(whisper_device='cpu',whisper_isolate=False))
        self.assertFalse(result['runtime_receipt']['inference_performed']);self.assertEqual(calls,[])
    def test_bad_backend_timestamps_rejected(self):
        for value in (True,float('nan'),-1.,2.):
            with self.assertRaises(ValueError):speech_m2.normalize({'words':[{'word':'bad','start':value,'end':1.}],'duration':1.,'language':'id'},Config())
    def test_bad_backend_probability_rejected(self):
        for value in (True,float('nan'),-.1,1.1):
            with self.assertRaises(ValueError):speech_m2.normalize({'words':[{'word':'bad','start':0.,'end':.5,'probability':value}],'duration':1.,'language':'id'},Config())
    def test_http_missing_endpoint_is_actionable(self):
        with patch.dict('os.environ',{'CLIPPER_ASR_ENDPOINT':''}):
            with self.assertRaisesRegex(ValueError,'CLIPPER_ASR_ENDPOINT'):speech_m2.http_asr('fixture',Config())
    def test_http_non_https_endpoint_rejected(self):
        with patch.dict('os.environ',{'CLIPPER_ASR_ENDPOINT':'http://public.example.invalid/asr'}):
            with self.assertRaises(ValueError):speech_m2.http_asr('fixture',Config())
    def test_language_matrix_does_not_claim_corpus_quality(self):
        rows=speech_m2.language_matrix(Config());self.assertEqual(len(rows),12);self.assertTrue(all(r['wer'] is None and r['measured_quality']=='not_tested' for r in rows))
    def test_unknown_local_model_support_is_not_verified(self):
        self.assertTrue(all(r['model_support']=='not_verified' for r in speech_m2.language_matrix(Config(whisper_model='/unknown/model'))))
    def test_english_only_model_does_not_claim_indonesian(self):
        rows=speech_m2.language_matrix(Config(whisper_model='small.en'));self.assertEqual(next(r for r in rows if r['language']=='id')['model_support'],'unsupported')
    def test_pauses_preserved_instead_of_automatic_cuts(self):
        data=speech_m2.pauses([{'start':1.,'end':2.},{'start':4.,'end':5.}],6.);self.assertEqual(data['pause_segments'],[{'start':0.,'end':1.,'policy':'preserve'},{'start':2.,'end':4.,'policy':'preserve'},{'start':5.,'end':6.,'policy':'preserve'}]);self.assertFalse(data['automatic_cutting'])
    def test_overlapping_speakers_are_ambiguous_not_face_identity(self):
        rows=speech_m2.assign_speakers([{'word_id':1,'word':'kata','start':0.,'end':1.}], [{'start':0.,'end':1.,'speaker_id':'A'},{'start':0.,'end':1.,'speaker_id':'B'}]);self.assertIsNone(rows[0]['speaker_id']);self.assertEqual(rows[0]['speaker_status'],'needs_review');self.assertEqual(set(rows[0]['overlapping_speakers']),{'A','B'})
    def test_dominant_audio_speaker_assignment(self):
        rows=speech_m2.assign_speakers([{'word_id':1,'word':'kata','start':0.,'end':1.}], [{'start':0.,'end':1.,'speaker_id':'A'}]);self.assertEqual(rows[0]['speaker_id'],'A');self.assertNotIn('face_id',rows[0])
    def test_weak_alignment_score_is_reviewable_not_certain(self):
        from .. import stage3
        row={'word_id':1,'word':'aman','start':0.,'end':1.,'probability':.9,'aligned_words':[{'word':'aman','start':.1,'end':.8,'score':.03}],'alignment_method':'whisperx'}
        word=stage3.expand_aligned([row])[0];self.assertEqual(word['timing_status'],'weak_alignment');self.assertEqual(word['alignment_confidence'],.03);self.assertEqual(word['probability'],.9);self.assertIn('timing_needs_review',speech_m2.critical_review([word])[0]['reasons'])
    def test_alternative_provider_language_name_is_normalized(self):
        result=speech_m2.normalize({'words':[{'word':'word','start':0.,'end':1.,'probability':None}],'duration':1.,'language':'english'},Config());self.assertEqual(result['source_language'],'en');self.assertEqual(result['reported_language'],'english');self.assertIsNone(result['words'][0]['probability'])
    def test_asr_cache_identity_changes_for_provider_and_vad(self):
        from ..storage import source_key
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'source';path.write_bytes(b'fixture');base=Config();key=source_key(path,base);self.assertNotEqual(key,source_key(path,replace(base,vad_policy='off')));self.assertNotEqual(key,source_key(path,replace(base,asr_provider='http')))


class AudioRenderCase(M2Fixture):
    __test__=True
    def render(self,vid='portrait',translation=False,bilingual=False):
        cfg=replace(self.service.config(self.doc,self.cid,vid),target_w=360 if vid=='portrait' else 640,target_h=640 if vid=='portrait' else 360,
            use_nvenc=False,audio_normalize=False,caption_style='clean',style_preset='legacy',align_selected_clips=False)
        clip=copy.deepcopy(self.doc['clips'][self.cid]);words=self.service.transcript(self.doc,self.cid,vid)['words']
        if translation or bilingual:
            proposal=self.translation();track=proposal['track']
            if bilingual:clip['_m2_translation']=track
            else:words=track['words']
        return pipeline.render_clip(self.source,words,clip,'audio-'+vid+str(translation)+str(bilingual),cfg)
    def test_real_audiogram_both_ratios_and_artifact_integrity(self):
        from ..artifact_store import verify
        for vid in ('portrait','landscape'):
            result=self.render(vid);self.assertTrue(result['qc']['passed']);self.assertTrue(verify(result));plan=json.loads(Path(result['plan_path']).read_text());self.assertEqual(plan['source_kind'],'audio');self.assertEqual(plan['visual_summary']['face_detection'],'not_applicable');self.assertEqual(plan['encoder'],'libx264')
    def test_bilingual_geometry_has_no_cross_track_collision_both_ratios(self):
        source=self.service.transcript(self.doc)['words'];track=self.translation()['track']
        for w,h in ((1080,1920),(1920,1080),(360,640),(640,360)):
            cfg=replace(self.service.config(self.doc),target_w=w,target_h=h,style_preset='legacy',caption_style='clean',caption_position='auto',caption_align='center');plan=bilingual_m2.make_plan(source,track['words'],cfg);checked=bilingual_m2.check(plan,cfg);self.assertTrue(checked['passed'],checked['issues'])
    def test_real_bilingual_audiogram_both_ratios(self):
        for vid in ('portrait','landscape'):
            result=self.render(vid,bilingual=True);plan=json.loads(Path(result['plan_path']).read_text());self.assertTrue(plan['captions']['bilingual']);self.assertTrue(plan['caption_checks']['passed']);self.assertTrue(result['qc']['passed'])
    def test_real_translation_only_audiogram_both_ratios(self):
        for vid in ('portrait','landscape'):
            result=self.render(vid,translation=True);plan=json.loads(Path(result['plan_path']).read_text());self.assertIn('does not',plan['words'][0]['word']);self.assertTrue(result['qc']['passed'])
    def test_audio_source_editor_clock_speed_reverse_freeze(self):
        from .. import editor_contract as ec
        from ..audio_project import edited_source
        rows=[{'id':'fast','start':0.,'end':2.,'speed':2.},{'id':'reverse','start':2.,'end':4.,'reverse':True},{'id':'hold','kind':'freeze','start':4.,'end':4.1,'freeze_duration':.5}]
        # Build segments through the validated editor command, not a fabricated clock.
        self.command({'op':'editor_segments','segments':rows});cfg=self.service.config(self.doc,self.cid,'portrait');clip=copy.deepcopy(self.doc['clips'][self.cid]);source,words,clip,cfg,receipt=edited_source(self.service,self.doc,self.cid,'portrait',self.source,self.service.transcript(self.doc)['words'],clip,cfg)
        from ..ffmpeg_util import probe
        self.assertAlmostEqual(probe(source)['duration'],receipt['clock']['duration'],delta=.03);self.assertEqual(receipt['source_layer'],'baked');self.assertTrue(any(s['reverse'] for s in receipt['clock']['slices']))
    def test_queued_translation_approval_after_publication_revision(self):
        from ..studio_worker import execute
        from .. import transcript_tracks
        def generate(cues,target,cfg):return ([{'cue_id':c['cue_id'],'text':'Andi does not sell 5 percent XAUUSD'} for c in cues],{'provider':'explicit_test_double','actual_model':'fixture-model','actual_device':'cpu','inference_performed':False})
        job=self.service.enqueue(self.doc['project_id'],'translation',options={'target_language':'en'})
        with patch('clipper.translation_m2.ollama',side_effect=generate):result=execute(self.service,job)
        self.refresh();self.assertEqual(result['approval_revision'],self.doc['revision']);saved=self.service.transcripts.commit_translation(self.doc['project_id'],{'draft_id':result['draft_id'],'digest':result['digest'],'expected_revision':result['approval_revision'],'operation_id':'queued-translation-approval','all_cues_reviewed':True,'critical_cue_ids':[c['cue_id'] for c in result['critical_cues']]});self.assertTrue(saved['track_id']);self.assertEqual(self.service.store.get(self.doc['project_id'])['transcript_id'],self.take)
    def test_audio_worker_waveform_and_preview_publish(self):
        from ..studio_worker import execute
        waveform=execute(self.service,self.service.enqueue(self.doc['project_id'],'waveform'));self.assertTrue(waveform)
        self.refresh();self.command({'op':'settings','scope':'project','values':{'use_nvenc':False,'align_selected_clips':False,'caption_style':'clean','style_preset':'legacy','audio_normalize':False}})
        job=self.service.enqueue(self.doc['project_id'],'preview',self.cid,'portrait');result=execute(self.service,job);self.assertTrue(result['qc']['passed']);self.assertTrue(Path(result['absolute_file']).is_file())
