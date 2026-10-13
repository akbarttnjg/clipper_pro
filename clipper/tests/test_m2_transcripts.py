"""M2 tracks and editing: real SQLite/media; no model-inference claims."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import shutil

def require_ffmpeg():
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):raise unittest.SkipTest('FFmpeg/FFprobe required for real M2 media checks')
from ..config import Config
from ..studio_service import StudioService
from ..project_store import Conflict
from .. import transcript_tracks as t
from ..stage3 import approval_stamp

SRT='1\n00:00:00,500 --> 00:00:01,500\n[Andi] Tidak 5 persen\n\n2\n00:00:02,000 --> 00:00:03,000\nXAUUSD\n'


class TrackCase(unittest.TestCase):
    def parse(self,text=SRT,fmt='srt',**kw):return t.parse(text,fmt,'sha256:fixture',8,source_language='id',**kw)
    def test_srt_retains_one_cue_unit_and_no_word_confidence(self):
        d=self.parse();self.assertEqual(len(d['words']),2);self.assertEqual(d['words'][0]['word'],'Tidak 5 persen');self.assertIsNone(d['words'][0]['probability']);self.assertEqual(d['words'][0]['timing_status'],'cue_unaligned');self.assertFalse(d['runtime_receipt']['inference_performed'])
    def test_vtt_voice_and_cue_identity(self):
        d=self.parse('WEBVTT\n\nname\n00:00.500 --> 00:01.500\n<v Andi>Tidak 5 persen</v>\n','vtt');self.assertEqual(d['words'][0]['speaker_id'],'Andi');self.assertEqual(d['cues'][0]['cue_id'],'name')
    def test_roundtrip_srt_preserves_text_time_speaker(self):
        d=self.parse();again=self.parse(t.export_track(d,'srt'));self.assertEqual(d['cues'],again['cues'])
    def test_roundtrip_vtt_preserves_text_time_speaker(self):
        d=self.parse();again=self.parse(t.export_track(d,'vtt'),'vtt');self.assertEqual(d['cues'],again['cues'])
    def test_roundtrip_json_preserves_metadata_and_probability_null(self):
        d=self.parse();again=self.parse(t.export_track(d,'json',metadata={'revision':7,'chapters':[{'title':'Bab'}]}),'json');self.assertEqual(again['words'],d['words']);self.assertEqual(again['metadata']['revision'],7)
    def test_offset_checked_in_source_clock(self):
        d=self.parse(offset=.2);self.assertEqual(d['words'][0]['start'],.7);self.assertEqual(d['cues'][0]['start'],.7)
    def test_negative_offset_out_of_bounds_rejected(self):
        with self.assertRaises(ValueError):self.parse(offset=-1)
    def test_positive_offset_out_of_bounds_rejected(self):
        with self.assertRaises(ValueError):self.parse(offset=7)
    def test_bool_offset_not_number(self):
        with self.assertRaises(ValueError):self.parse(offset=True)
    def test_invalid_minute_rejected(self):
        with self.assertRaises(ValueError):self.parse(SRT.replace('00:00:00,500','00:60:00,500'))
    def test_missing_cue_time_rejected(self):
        with self.assertRaises(ValueError):self.parse('1\nTanpa timestamp')
    def test_reversed_cue_rejected(self):
        with self.assertRaises(ValueError):self.parse(SRT.replace('00:00:01,500','00:00:00,100'))
    def test_duplicate_cue_id_rejected(self):
        with self.assertRaises(ValueError):self.parse(SRT.replace('\n2\n','\n1\n'))
    def test_nan_duration_rejected(self):
        with self.assertRaises(ValueError):t.parse(SRT,'srt','a',float('nan'))
    def test_json_wrong_source_rejected(self):
        d=self.parse();d['source_id']='other'
        with self.assertRaises(ValueError):self.parse(t.export_track(d,'json'),'json')
    def test_json_wrong_timebase_rejected(self):
        d=json.loads(t.export_track(self.parse(),'json'));d['timebase']='output_seconds'
        with self.assertRaises(ValueError):self.parse(json.dumps(d),'json')
    def test_json_bool_confidence_rejected(self):
        d=self.parse();d['words'][0]['probability']=True
        with self.assertRaises(ValueError):self.parse(t.export_track(d,'json'),'json')
    def test_json_out_of_range_confidence_rejected(self):
        d=self.parse();d['words'][0]['probability']=1.1
        with self.assertRaises(ValueError):self.parse(t.export_track(d,'json'),'json')
    def test_empty_text_rejected(self):
        with self.assertRaises(ValueError):self.parse('')
    def test_import_language_mismatch_cannot_be_overridden(self):
        self.assertFalse(t.review_import(self.parse(),expected_language='en',language_checked=True,source_time_checked=True)['ready'])
    def test_import_unknown_language_not_fastpath(self):
        d=self.parse();d['language']='und';self.assertFalse(t.review_import(d,expected_language='id',language_checked=True,source_time_checked=True)['ready'])
    def test_import_requires_language_review(self):
        self.assertFalse(t.review_import(self.parse(),expected_language='id',source_time_checked=True)['ready'])
    def test_import_requires_source_time_review(self):
        self.assertFalse(t.review_import(self.parse(),expected_language='id',language_checked=True)['ready'])
    def test_import_review_ready_only_with_both_checks(self):
        self.assertTrue(t.review_import(self.parse(),expected_language='id',language_checked=True,source_time_checked=True)['ready'])
    def test_overlapping_cues_need_explicit_review(self):
        d=self.parse(SRT.replace('00:00:02,000','00:00:01,000'));self.assertFalse(t.review_import(d,expected_language='id',language_checked=True,source_time_checked=True)['ready']);self.assertTrue(t.review_import(d,expected_language='id',language_checked=True,source_time_checked=True,overlaps_checked=True)['ready'])
    def test_missing_confidence_is_not_zero_or_false_pass(self):
        row=t.critical_review(self.parse()['words'])[0];self.assertIsNone(row['probability']);self.assertIn('confidence_not_measured',row['reasons']);self.assertEqual(row['status'],'needs_listening')
    def test_critical_negation_number_unit_domain_name_flags(self):
        row=t.critical_review([{'word_id':1,'word':'Andi tidak 5 persen XAUUSD','start':0,'end':1,'probability':.5}],glossary='XAUUSD')[0]
        self.assertTrue({'low_asr_confidence','number','negation','unit','domain_term','candidate_name'}<=set(row['reasons']))
    def test_txt_export_speaker_and_source_time(self):
        out=t.export_track(self.parse(),'txt');self.assertIn('[00:00:00.500] [Andi]',out)


class M2Fixture(unittest.TestCase):
    __test__=False
    @classmethod
    def setUpClass(cls):
        require_ffmpeg()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'source.wav'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=8','-ar','48000',str(self.source)],check=True)
        self.service=StudioService(self.root,Config(work_dir='work',out_dir='clips'),autostart=False);self.doc=self.service.create(self.source)
        rows=[{'word_id':i,'word':v,'start':i+.1,'end':i+.7,'probability':p,'timing_status':'asr_estimated'} for i,(v,p) in enumerate([('Andi',None),('tidak',.95),('5',.6),('persen',.9),('XAUUSD',.95)])]
        self.take=self.service.store.save_transcript(self.doc['project_id'],{'words':rows,'raw_words':copy.deepcopy(rows),'language':'id','duration':8.,'source_id':self.doc['source']['source_id'],'runtime_receipt':{'provider':'fixture','inference_performed':False}})
        def setup(d):d.update(transcript_id=self.take,transcript_revision=1);self.service.add_candidates(d,[{'start':0.,'end':6.,'title':'Klip 1'},{'start':1.,'end':7.,'title':'Klip 2'}])
        self.service.store.mutate(self.doc['project_id'],0,'setup-m2-fixture',{},setup);self.refresh();self.cid=next(iter(self.doc['clips']))
    def tearDown(self):self.service.queue.close();self.tmp.cleanup()
    def refresh(self):self.doc=self.service.store.get(self.doc['project_id'])
    def command(self,op,*,cid=None,vid='portrait',expected=None):
        self.refresh();body={'project_id':self.doc['project_id'],'clip_id':self.cid if cid is None else cid,'variant_id':vid,'expected_revision':self.doc['revision'] if expected is None else expected,'operation_id':'operation-'+str(self.doc['revision'])+'-'+str(len(self.service.store.history(self.doc['project_id']))),'operations':[op]};result=self.service.changes(body);self.refresh();return result
    def text(self,wid,after,scope,vid='portrait'):
        self.refresh();before=next(w['word'] for w in self.service.transcript(self.doc,self.cid,vid)['words'] if wid in w.get('source_word_ids',[w['word_id']]))
        op={'op':'correct_phrase','scope':scope,'variant_id':vid,'origin_word_ids':[wid],'before':before,'after':after,'transcript_id':self.take,'transcript_revision':self.doc['transcript_revision']}
        op['fact_confirmation']=approval_stamp(self.take,self.doc['transcript_revision'],[wid],before,after)
        return self.command(op,vid=vid)
    def timing(self,wid,start,end,scope='clip'):
        return self.command({'op':'m2_timing','scope':scope,'origin_word_ids':[wid],'start':start,'end':end,'transcript_id':self.take,'transcript_revision':self.doc['transcript_revision']})
    def import_proposal(self,**kw):
        return self.service.transcripts.import_review(self.doc['project_id'],{'expected_revision':self.doc['revision'],'text':SRT,'format':'srt','language':'id','language_checked':True,'source_time_checked':True,**kw})
    def commit_import(self,p):return self.service.transcripts.commit_import(self.doc['project_id'],{'draft_id':p['draft_id'],'digest':p['digest'],'expected_revision':p['revision'],'operation_id':'import-approval-'+p['draft_id']})
    def translation(self):
        self.refresh();cues=t.cues_from_words(self.service.transcript(self.doc)['words']);rows=[{'cue_id':c['cue_id'],'text':'Andi does not sell 5 percent XAUUSD'} for c in cues]
        return self.service.transcripts.translation_review(self.doc['project_id'],{'expected_revision':self.doc['revision'],'target_language':'en','provider':'manual','cues':rows})
    def approve_translation(self,p,**kw):
        return self.service.transcripts.commit_translation(self.doc['project_id'],{'draft_id':p['draft_id'],'digest':p['digest'],'expected_revision':p['revision'],'operation_id':'translation-approve-'+p['draft_id'],'all_cues_reviewed':True,'critical_cue_ids':[c['cue_id'] for c in p['critical_cues']],**kw})


class ServiceCase(M2Fixture):
    __test__=True
    def test_audio_source_identity_is_original_file(self):self.assertEqual(self.doc['source']['info']['kind'],'audio');self.assertEqual(self.doc['source']['path'],str(self.source))
    def test_variant_text_overrides_clip_and_project_only_on_selected_ratio(self):
        self.text(4,'emas','project');self.text(4,'logam','clip');self.text(4,'instrumen','variant');self.assertEqual(self.service.transcript(self.doc,self.cid,'portrait')['words'][-1]['word'],'instrumen');self.assertEqual(self.service.transcript(self.doc,self.cid,'landscape')['words'][-1]['word'],'logam');self.assertEqual(self.service.transcript(self.doc)['words'][-1]['word'],'emas')
    def test_phrase_scope_projection_and_paged_search(self):
        self.text(4,'instrumen','phrase');page=self.service.page(self.doc['project_id'],self.cid,q='instrumen',variant_id='portrait');self.assertEqual(page['total'],1);self.assertEqual(self.service.page(self.doc['project_id'],self.cid,q='instrumen',variant_id='landscape')['total'],0)
    def test_manual_edit_leaves_heard_take_immutable(self):
        original=self.service.store.transcript(self.take);self.text(4,'emas','project');self.assertEqual(self.service.store.transcript(self.take),original)
    def test_fact_changing_negation_requires_stamp(self):
        with self.assertRaises(ValueError):self.command({'op':'correct_phrase','scope':'clip','origin_word_ids':[1],'before':'tidak','after':'selalu','transcript_id':self.take,'transcript_revision':1})
    def test_scoped_text_undo_restores_previous_projection(self):
        saved=self.text(4,'emas','variant');self.service.store.undo(self.doc['project_id'],saved['revision'],'undo-m2-text',saved['revision']);self.refresh();self.assertEqual(self.service.transcript(self.doc,self.cid,'portrait')['words'][-1]['word'],'XAUUSD')
    def test_manual_time_updates_page_and_render_projection(self):
        self.timing(4,4.2,4.8);page=self.service.page(self.doc['project_id'],self.cid);self.assertEqual(page['words'][-1]['start'],4.2)
        from ..studio_exchange import render_words
        rows=render_words(self.service.transcript(self.doc,self.cid,'portrait'),self.doc,self.doc['clips'][self.cid],self.service.config(self.doc,self.cid,'portrait'));self.assertEqual(rows[-1]['start'],4.2)
    def test_manual_time_variant_does_not_change_other_ratio(self):
        self.timing(4,4.2,4.8,'variant');self.assertEqual(self.service.transcript(self.doc,self.cid,'portrait')['words'][-1]['start'],4.2);self.assertEqual(self.service.transcript(self.doc,self.cid,'landscape')['words'][-1]['start'],4.1)
    def test_manual_time_rejects_overlap(self):
        with self.assertRaises(ValueError):self.timing(3,2.2,3.5)
    def test_manual_time_rejects_illegal_bounds(self):
        with self.assertRaises(ValueError):self.timing(4,4.2,9)
    def test_manual_time_rejects_boolean(self):
        with self.assertRaises(ValueError):self.timing(4,True,4.8)
    def test_manual_time_undo_keeps_raw_source_clock(self):
        saved=self.timing(4,4.2,4.8);self.service.store.undo(self.doc['project_id'],saved['revision'],'undo-m2-time',saved['revision']);self.refresh();self.assertEqual(self.service.transcript(self.doc,self.cid)['words'][-1]['start'],4.1)
    def test_stale_transcript_clock_raises_conflict_not_keyerror(self):
        with self.assertRaises(Conflict):self.command({'op':'m2_timing','scope':'clip','origin_word_ids':[4],'start':4.2,'end':4.8,'transcript_id':self.take,'transcript_revision':0})
    def test_manual_speaker_tracks_audio_identity_and_preserves_source(self):
        self.command({'op':'m2_speaker','origin_word_ids':[4],'speaker_id':'Andi','transcript_id':self.take,'transcript_revision':1});self.assertEqual(self.service.transcript(self.doc)['words'][-1]['speaker_id'],'Andi');self.assertNotIn('speaker_id',self.service.store.transcript(self.take)['words'][-1])
    def test_import_review_is_read_only(self):
        before=self.service.store.get(self.doc['project_id']);p=self.import_proposal();self.assertTrue(p['review']['ready']);self.assertEqual(self.service.store.get(self.doc['project_id']),before)
    def test_unchecked_import_cannot_commit(self):
        p=self.import_proposal(language_checked=False)
        with self.assertRaises(ValueError):self.commit_import(p)
    def test_import_commit_is_idempotent_and_keeps_old_take(self):
        p=self.import_proposal();a=self.commit_import(p);b=self.commit_import(p);self.assertEqual(a,b);self.assertEqual(len(self.service.store.transcript(self.take)['words']),5)
    def test_import_digest_tampering_rejected(self):
        p=self.import_proposal();p['digest']='x'
        with self.assertRaises(ValueError):self.commit_import(p)
    def test_import_commit_conflicts_with_new_revision(self):
        p=self.import_proposal();self.command({'op':'rename','name':'Baru'})
        with self.assertRaises(Conflict):self.commit_import(p)
    def test_source_change_rejected_before_import_review(self):
        with self.source.open('ab') as f:f.write(b'changed')
        with self.assertRaises(ValueError):self.import_proposal()
    def test_import_undo_restores_original_track_pointer(self):
        saved=self.commit_import(self.import_proposal());self.service.store.undo(self.doc['project_id'],saved['revision'],'undo-import-track',saved['revision']);self.refresh();self.assertEqual(self.doc['transcript_id'],self.take)
    def test_translation_separate_track_and_approved_only(self):
        p=self.translation();self.assertFalse(p['approved']);saved=self.approve_translation(p);self.refresh();self.assertEqual(self.doc['transcript_id'],self.take);self.assertTrue(self.doc['translation_tracks'][saved['track_id']]['approved'])
    def test_translation_all_cues_review_required(self):
        with self.assertRaises(ValueError):self.approve_translation(self.translation(),all_cues_reviewed=False)
    def test_translation_critical_facts_review_required(self):
        with self.assertRaises(ValueError):self.approve_translation(self.translation(),critical_cue_ids=[])
    def test_translation_numeric_change_rejected_before_proposal(self):
        from ..translation_m2 import validate
        with self.assertRaises(ValueError):validate([{'cue_id':'1','start':0.,'end':1.,'text':'5 persen'}],[{'cue_id':'1','text':'6 percent'}],'en')
    def test_translation_retiming_rejected(self):
        from ..translation_m2 import validate
        with self.assertRaises(ValueError):validate([{'cue_id':'1','start':0.,'end':1.,'text':'5 persen'}],[{'cue_id':'1','text':'5 percent','start':.5}],'en')
    def test_stale_translation_cannot_be_selected(self):
        p=self.translation();saved=self.approve_translation(p);self.refresh();self.timing(4,4.2,4.8)
        with self.assertRaises(ValueError):self.command({'op':'m2_track_display','mode':'bilingual','track_id':saved['track_id']})
    def test_approved_translation_display_propagates_to_render_words(self):
        saved=self.approve_translation(self.translation());self.refresh();self.command({'op':'m2_track_display','mode':'translation','track_id':saved['track_id']});from ..studio_exchange import render_words
        rows=render_words(self.service.transcript(self.doc,self.cid,'portrait'),self.doc,self.doc['clips'][self.cid],self.service.config(self.doc,self.cid,'portrait'));self.assertIn('does not',rows[0]['word'])
    def test_translation_export_roundtrip_preserves_source_origins(self):
        saved=self.approve_translation(self.translation());self.refresh();out=self.service.transcripts.export(self.doc['project_id'],{'expected_revision':self.doc['revision'],'format':'json','track_id':saved['track_id']});data=json.loads(self.service.file(out['url'].split('/')[-1]).read_text());self.assertEqual(data['words'][0]['source_word_ids'],[0,1,2,3,4]);again=t.parse(json.dumps(data),'json',self.doc['source']['source_id'],8,source_language='en');self.assertEqual(again['cues'],data['cues'])
    def test_four_exports_have_revision_chapter_and_source_clock(self):
        for fmt in ('txt','json','srt','vtt'):
            out=self.service.transcripts.export(self.doc['project_id'],{'expected_revision':self.doc['revision'],'format':fmt});self.assertTrue(self.service.file(out['url'].split('/')[-1]).is_file());meta=json.loads(self.service.file(out['provenance_url'].split('/')[-1]).read_text());self.assertEqual(meta['revision'],self.doc['revision']);self.assertEqual(len(meta['chapters']),2);self.assertEqual(meta['timebase'],'source_seconds')
    def test_api_stale_source_clock_returns_409_and_draft_remains_reviewable(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from ..api_studio import create_router
        app=FastAPI();app.include_router(create_router(self.service));client=TestClient(app)
        data={'project_id':self.doc['project_id'],'clip_id':self.cid,'expected_revision':self.doc['revision'],'operation_id':'api-stale-m2-clock','operations':[{'op':'m2_timing','origin_word_ids':[4],'start':4.2,'end':4.8,'transcript_id':self.take,'transcript_revision':0}]}
        self.assertEqual(client.post('/api/studio/changes',json=data).status_code,409);self.assertEqual(self.service.store.transcript(self.take)['words'][-1]['start'],4.1)
