"""Regression cases from the two audits; no model downloads in these tests."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from dataclasses import replace
from clipper.config import Config,validate_overrides
from clipper.typography import groups,make_plan,balanced_rows,protected_pair
from clipper.caption_director import focus,visible_cap
from clipper.style5 import readability
from clipper.explanation5 import structures
from clipper.text_area import choose,grid,output_quality
from clipper import placement
from clipper.dependency_cache import content_id,fresh_scope


def words(text,step=.42):
    return [{'word':t,'word_id':i,'start':i*step,'end':(i+1)*step} for i,t in enumerate(text.split())]


class CaptionDirection(unittest.TestCase):
    def cfg(self,**kwargs):return Config(style_preset='ekspresif',target_w=1920,target_h=1080,**kwargs)
    def test_collocations_survive_adversarial_phrase_lengths(self):
        for pair in ('hari ini','saat ini','makin memuncak','tanpa rencana','tidak gagal','stop loss','risk reward'):
            for lead in range(10):
                ws=words(('penjelasan '*lead)+pair+' tetap penting bagi kita hari ini',step=.18)
                parts=groups(ws,self.cfg())
                boundaries={p[-1]['word_id'] for p in parts[:-1]}
                self.assertNotIn(lead,boundaries,(pair,lead))
                self.assertEqual([w['word_id'] for p in parts for w in p],list(range(len(ws))))
    def test_protection_does_not_merge_different_source_parts(self):
        ws=words('hari ini');ws[0]['part']=1;ws[1]['part']=2
        self.assertEqual(len(groups(ws,self.cfg())),2)
    def test_protection_does_not_bridge_a_real_pause(self):
        ws=words('hari ini');ws[1].update(start=4.,end=4.5)
        self.assertEqual(len(groups(ws,self.cfg())),2)
    def test_row_wrapping_never_severs_short_governed_units(self):
        ws=words('kita trading tanpa rencana hari ini');rows=balanced_rows(ws,[90]*6,15,400,3,{2,3})
        self.assertIsNotNone(rows)
        ends={r[-1] for r in rows[:-1]}
        self.assertNotIn(2,ends);self.assertNotIn(4,ends)
    def test_keyword_list_does_not_hide_other_semantic_focus(self):
        for text,expected in (('Itu yang bahaya',{'bahaya'}),('Ketika emosinya makin memuncak',{'makin','memuncak'}),('ketika kita trading tanpa rencana',{'tanpa','rencana'})):
            ws=words(text);actual={ws[i]['word'] for i in focus(ws,['gagal','uang'])}
            self.assertEqual(actual,expected)
    def test_keyword_with_negation_keeps_whole_focus(self):
        ws=words('ini bukan risiko besar');self.assertEqual({ws[i]['word'] for i in focus(ws,['risiko besar'])},{'bukan','risiko','besar'})
    def test_spoken_discourse_boundary_does_not_attach_dan_hal_to_previous_clause(self):
        parts=groups(words('dapatnya banyak aja Dan hal itu yang bahaya'),self.cfg())
        self.assertTrue(any(p[0]['word']=='Dan' for p in parts))
    def test_negation_verb_and_object_receive_one_focus(self):
        ws=words('Gak punya plan');self.assertEqual({ws[i]['word'] for i in focus(ws,['plan'])},{'Gak','punya','plan'})
    def test_focus_composition_preserves_speech_order_and_ids(self):
        ws=words('ketika kita trading tanpa rencana');p=make_plan(ws,self.cfg(),['gagal'])
        self.assertEqual([w['text'] for f in p['phrases'] for w in f['words']],[w['word'] for w in ws])
        self.assertEqual([i for f in p['phrases'] for w in f['words'] for i in w['word_ids']],list(range(len(ws))))
        focused=[w for f in p['phrases'] for w in f['words'] if w['emphasis']]
        self.assertEqual([w['text'] for w in focused],['tanpa','rencana'])
        self.assertEqual(len({w['y'] for w in focused}),1)
    def test_both_ratios_have_same_phrase_and_first_reveal(self):
        ws=words('Ketika emosinya makin memuncak. Itu yang bahaya.');cfg=self.cfg()
        a=make_plan(ws,cfg,['gagal']);b=make_plan(ws,replace(cfg,target_w=1080,target_h=1920),['gagal'])
        self.assertEqual([p['phrase_id'] for p in a['phrases']],[p['phrase_id'] for p in b['phrases']])
        for plan in (a,b):
            for p in plan['phrases']:
                starts=[next(k['frame'] for k in w['keyframes'] if k['opacity']>.05) for w in p['words']]
                self.assertEqual(len(set(starts)),1)
    def test_landscape_phone_cap_height_meets_profile(self):
        cfg=self.cfg();p=make_plan(words('Itu yang bahaya.'),cfg)
        self.assertGreaterEqual(min(visible_cap(w,cfg.fonts_dir,360,1920) for f in p['phrases'] for w in f['words']),14)
    def test_old_76px_landscape_glyph_is_reported_small(self):
        cfg=self.cfg();p=make_plan(words('Itu yang bahaya.'),cfg)
        for f in p['phrases']:
            for w in f['words']:w['size']=76
        self.assertIn('small_text',{i['code'] for i in readability(p,cfg)['issues']})
    def test_portrait_area_ends_above_platform_caption(self):
        p=make_plan(words('ketika kita trading tanpa rencana'),replace(self.cfg(),target_w=1080,target_h=1920))
        for f in p['phrases']:self.assertLessEqual(f['panel'][1]+f['panel'][3],1920*.84)
    def test_manual_alignment_scale_and_template_are_respected(self):
        cfg=self.cfg(caption_align='right',caption_style='blur',caption_template_policy='manual',caption_scale=.7)
        a=make_plan(words('Itu yang bahaya.'),cfg);b=make_plan(words('Itu yang bahaya.'),replace(cfg,caption_scale=1.))
        self.assertTrue(all(f['alignment']=='right' and f['design']['template']=='blur' for f in a['phrases']))
        self.assertLess(a['phrases'][0]['words'][0]['size'],b['phrases'][0]['words'][0]['size'])
    def test_animation_envelopes_pass_real_font_qc(self):
        from clipper.caption_checks import inspect_caption_plan
        for W,H in ((1920,1080),(1080,1920),(640,360),(360,640)):
            cfg=replace(self.cfg(),target_w=W,target_h=H)
            for mode in ('auto','editorial','focus','quote'):
                plan=make_plan(words('Ketika emosinya makin memuncak. Itu yang bahaya.'),replace(cfg,caption_composition=mode),['gagal'])
                self.assertTrue(inspect_caption_plan(plan,cfg)['passed'],(W,H,mode))
    def test_new_settings_are_validated(self):
        self.assertEqual(validate_overrides({'caption_composition':'focus','segmentation_enabled':False}),{'caption_composition':'focus','segmentation_enabled':False})
        for values in ({'caption_composition':'broken'},{'segmentation_enabled':'true'}):
            with self.assertRaises(ValueError):validate_overrides(values)


class ListCompleteness(unittest.TestCase):
    def test_fifth_item_beyond_old_36_word_window_rejects_card(self):
        ws=words('Pertama modal. Kedua risiko. Ketiga catatan. Keempat evaluasi. '+('penjelasan '*30)+'Kelima disiplin.')
        self.assertFalse([s for s in structures(ws) if s['kind']=='list'])
    def test_last_item_caveat_is_not_silently_discarded(self):
        ws=words('Pertama modal. Kedua risiko. Tetapi jangan abaikan biaya.')
        self.assertFalse([s for s in structures(ws) if s['kind']=='list'])
    def test_complete_four_items_survive_verbatim(self):
        text='Pertama modal. Kedua risiko. Ketiga catatan. Keempat evaluasi.'
        s=list(structures(words(text)));self.assertEqual(s[0]['labels'],['Pertama modal.','Kedua risiko.','Ketiga catatan.','Keempat evaluasi.'])
    def test_explicit_conclusion_closes_complete_list(self):
        s=list(structures(words('Pertama modal. Kedua risiko. Kesimpulannya kendalikan emosi.')))
        self.assertEqual(len(s),1);self.assertEqual(s[0]['labels'],['Pertama modal.','Kedua risiko.'])
    def test_long_item_is_skipped_without_summarization(self):
        self.assertFalse(list(structures(words('Pertama kita perlu mencatat semua keputusan sebelum membeli aset baru. Kedua belajar.'))))


class AreaStability(unittest.TestCase):
    def shot(self):return {'mode':'fill','rect':[0,0,1920,1080],'source_start':0,'source_end':3,'start':0,'end':3,'protected_source':[{'kind':'face','box':[760,120,260,280]}],'zoom_at':None}
    def test_plain_shirt_below_face_is_an_eligible_large_panel(self):
        panel,_,clear=choose([{'kind':'face','box':[320,70,250,480]}],1080,1920)
        self.assertTrue(clear);self.assertGreater(panel[2],1080*.7);self.assertLessEqual(panel[1]+panel[3],1920*.84)
    def test_recognized_source_words_are_protected(self):
        boxes=[{'kind':'ocr','box':[80,580,1500,400]}];panel,_,clear=choose(boxes,1920,1080)
        self.assertTrue(clear);self.assertEqual(placement.overlap(panel,boxes[0]['box']),0)
    def test_minor_noise_keeps_previous_panel(self):
        preferred=[134.4,583.2,1612.8,324]
        panel,_,clear=choose([{'kind':'face','box':[760,120,260,280]}],1920,1080,preferred)
        self.assertTrue(clear);self.assertEqual(panel,preferred)
    def test_unsafe_previous_panel_is_abandoned(self):
        preferred=[134.4,583.2,1612.8,324];panel,_,clear=choose([{'kind':'face','box':[800,580,300,320]}],1920,1080,preferred)
        self.assertTrue(clear);self.assertNotEqual(panel,preferred)
    def test_stats_project_through_output_crop(self):
        import numpy as np
        sample=grid(np.full((180,320,3),127,dtype=np.uint8));s=self.shot();sample['source_size']=[1920,1080];s['area_samples']=[sample]
        tiles=output_quality(s,1080,1920)
        self.assertTrue(tiles);self.assertTrue(all(0<=t['luminance']<=1 and 0<=t['clutter']<=1 for t in tiles))
    def test_curated_stability_overrides_alternating_detector_proposals(self):
        cfg=Config(style_preset='adaptif',target_w=1920,target_h=1080);a=self.shot();b=self.shot();b.update(start=3,end=6,source_start=3,source_end=6,caption_panel=[1030,200,740,480])
        plan={'shots':[a,b]};placement.apply(plan,cfg)
        self.assertEqual(a['caption_panel'],b['caption_panel'])
    def test_phone_and_head_leave_plain_chest_available_in_both_ratios(self):
        for W,H in ((1080,1920),(1920,1080)):
            cfg=Config(style_preset='adaptif',target_w=W,target_h=H)
            s=self.shot();s['rect']=[628,0,608,1080] if H>W else [0,0,1920,1080]
            s['protected_source']+=[{'kind':'hair_face','box':[713,140,422,244]},{'kind':'accessory','box':[993,962,222,127]}]
            placement.place_shot(s,cfg)
            self.assertEqual(s['placement']['mode'],'empty_space',(W,H))
            self.assertIsNone(s.get('image_height'))


class OptionalSegmentation(unittest.TestCase):
    def test_missing_component_never_downloads_or_invokes_backend(self):
        from clipper import segmentation,visual4
        plan={'shots':[]};cfg=Config(style_preset='adaptif')
        with patch.object(visual4,'component_runtime',return_value=None),patch.object(visual4,'backend') as backend:
            result=segmentation.enrich('missing-source',plan,cfg)
        self.assertEqual(result['status'],'unavailable');backend.assert_not_called()
    def test_disabled_segmentation_has_no_runtime_lookup(self):
        from clipper import segmentation,visual4
        with patch.object(visual4,'component_runtime') as lookup:
            result=segmentation.enrich('missing-source',{'shots':[]},Config(style_preset='adaptif',segmentation_enabled=False))
        self.assertEqual(result['status'],'disabled');lookup.assert_not_called()
    def test_model_recipe_is_pinned_before_download(self):
        from clipper.runtime import install
        from clipper.segmentation import MODEL_SHA256,MODEL_BYTES
        with tempfile.TemporaryDirectory() as tmp,patch.object(install,'stable_package',side_effect=lambda p:p):
            recipe=install.plan(None,{'component':'mediapipe','options':{}},Path(tmp))
        entry=recipe['weights']['files'][0]
        self.assertEqual(entry['hash'],MODEL_SHA256);self.assertEqual(entry['algorithm'],'sha256');self.assertEqual(entry['size'],MODEL_BYTES)
        self.assertIn('/float32/1/',entry['url']);self.assertNotIn('/latest/',entry['url'])


class OperationalFixes(unittest.TestCase):
    def test_two_queue_owners_back_off_outside_resource_lock(self):
        from clipper.project_store import ProjectStore
        from clipper.job_queue import JobQueue
        with tempfile.TemporaryDirectory() as tmp:
            store=ProjectStore(Path(tmp)/'store.sqlite');lock=threading.Lock()
            a=JobQueue(store,tmp,autostart=False);b=JobQueue(store,tmp,lock,autostart=False,recover=False)
            first=a.enqueue('project','waveform',{}, {'value':1});a.claim();second=b.enqueue('project','waveform',{}, {'value':2})
            waits=[]
            def backoff(seconds):
                self.assertTrue(lock.acquire(blocking=False));lock.release();waits.append(seconds);b.stop_event.set()
            with patch.object(b.stop_event,'wait',side_effect=backoff):b.run()
            self.assertEqual(waits,[.5]);self.assertEqual(b.get(second['id'])['status'],'queued')
            a.update(first['id'],status='completed');b.stop_event.clear();self.assertEqual(b.claim()['id'],second['id'])
    def test_fresh_snapshot_deduplicates_only_unchanged_files_in_its_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source';path.write_bytes(b'first');original=Path.open;reads=[]
            def counted(p,*args,**kw):
                if p==path and args and args[0]=='rb':reads.append(p)
                return original(p,*args,**kw)
            with patch.object(Path,'open',counted):
                with fresh_scope():
                    a=content_id(path,fresh=True);self.assertEqual(content_id(path,fresh=True),a)
                    path.write_bytes(b'second');self.assertNotEqual(content_id(path,fresh=True),a)
                content_id(path,fresh=True)
            self.assertEqual(len(reads),3)
    def test_analysis_timers_separate_ocr_and_correction_from_asr(self):
        from clipper import pipeline
        from clipper import evidence,transcript_correction
        with tempfile.TemporaryDirectory() as tmp:
            cfg=Config(work_dir=tmp,processing_mode='full',source_content_id='test')
            transcript={'words':words('ucapan sumber'),'duration':3.,'correction_report':{}}
            ticks=iter(range(30))
            with patch.object(pipeline.ffmpeg_util,'ensure_ffmpeg'),patch.object(pipeline.ffmpeg_util,'filter_file_args'),patch.object(pipeline,'source_key',return_value='key'),patch.object(pipeline.transcribe,'transcribe',return_value=transcript),patch.object(evidence,'scan',return_value={}),patch.object(evidence,'suggestions',return_value=[]),patch.object(transcript_correction,'refine',side_effect=lambda t,c:t),patch.object(pipeline.time,'monotonic',side_effect=lambda:next(ticks)):
                result,_=pipeline.analyze('controlled-source',cfg)
            timing=result['timings'];self.assertEqual(timing['transcription_seconds'],1)
            self.assertEqual(timing['evidence_seconds'],1);self.assertEqual(timing['correction_seconds'],1)
            self.assertGreater(timing['analysis_total_seconds'],timing['transcription_seconds'])


class AggregateEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from clipper.tests import test_workflow6 as fixture
        cls.fixture=fixture.WorkspaceTests;cls.fixture.setUpClass()
    @classmethod
    def tearDownClass(cls):cls.fixture.tearDownClass()
    def setUp(self):
        self.base=self.fixture();self.base.setUp();self.svc=self.base.svc;self.pid=self.base.pid;self.cid=self.base.cid
        p=self.base.root/'aggregate.zip';p.write_bytes(b'aggregate fixture')
        self.package={'zip':str(p),'package_content_id':content_id(p),'variant_id':'both','export_mode':'hybrid',
            'coverage':[{'clip_id':cid,'variant_id':vid,'output_content_id':'final-'+cid+'-'+vid,
                        'reference':{'width':256 if vid=='landscape' else 144,'height':144 if vid=='landscape' else 256,'length':2.}}
                        for cid in (self.cid,'another-clip') for vid in ('portrait','landscape')],
            'editors':{e:{'construction_status':'generated','structural_status':'passed'} for e in ('capcut','resolve')}}
        d=self.svc.store.get(self.pid);self.svc.store.mutate(self.pid,d['revision'],'aggregate',{},lambda doc:doc.update(exports=[self.package]))
    def tearDown(self):self.base.tearDown()
    def data(self):return {'package_content_id':self.package['package_content_id'],'clip_id':self.cid,'variant_id':'landscape','editor':'capcut','version':'9.5.0','render_path':str(self.fixture.source),'note':'Fixture render dimensions match; native editor actions are user reported.',**{k:True for k in ('opened','text_edited','saved','rendered','compared')}}
    def test_all_four_timelines_have_separate_editor_rows(self):
        rows=self.svc.workspace.native_matrix(self.pid);self.assertEqual(len(rows),8)
        self.assertNotIn('both',{r['variant_id'] for r in rows})
    def test_evidence_on_one_timeline_does_not_certify_other_ratios_or_clips(self):
        row=self.svc.workspace.native_evidence(self.pid,self.data());self.assertEqual(row['clip_id'],self.cid)
        rows=self.svc.workspace.native_matrix(self.pid)
        self.assertEqual(sum(r['status']=='user_reported_passed' for r in rows),1)
    def test_wrong_ratio_rejected_against_frozen_reference(self):
        data=self.data();data['variant_id']='portrait'
        with self.assertRaisesRegex(ValueError,'resolusi'):self.svc.workspace.native_evidence(self.pid,data)
    def test_aggregate_requires_explicit_member(self):
        data=self.data();data.pop('clip_id');data.pop('variant_id')
        with self.assertRaisesRegex(ValueError,'klip dan rasio'):self.svc.workspace.native_evidence(self.pid,data)
    def test_uncovered_timeline_is_rejected(self):
        data=self.data();data['clip_id']='unknown'
        with self.assertRaises(ValueError):self.svc.workspace.native_evidence(self.pid,data)
    def test_legacy_aggregate_reference_requires_matching_current_final(self):
        from clipper.workflow6 import package_members
        p=copy.deepcopy(self.package);p['coverage'][0].pop('reference')
        member=package_members(p,self.svc.store.get(self.pid))[0]
        self.assertEqual(member['reference'],{})


if __name__=='__main__':unittest.main()
