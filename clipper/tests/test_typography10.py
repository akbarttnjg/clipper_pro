"""Regression cases from the 59.67s 4.0.9 audit, including late-clip defects."""
import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from clipper.config import Config
from clipper.typography import display_units,groups,make_plan
from clipper.caption_checks import inspect_caption_plan
from clipper import placement,visual4,segmentation,selected_alignment,semantic_rank


def words(text,start=0.,step=.45):
    return [dict(word=t,word_id=i,token_id='t'+str(i),start=start+i*step,end=start+(i+1)*step) for i,t in enumerate(text.split())]


class PhraseRegression(unittest.TestCase):
    def test_late_reduplication_preserves_all_original_ids_and_times(self):
        ws=words('akan terus -terusan kalian alamin',53.);original=copy.deepcopy(ws)
        merged=display_units(ws)
        self.assertEqual([w['word'] for w in merged],['akan','terus-terusan','kalian','alamin'])
        self.assertEqual(merged[1]['word_ids'],[1,2]);self.assertEqual(merged[1]['token_ids'],['t1','t2'])
        self.assertEqual((merged[1]['start'],merged[1]['end']),(ws[1]['start'],ws[2]['end']))
        self.assertEqual(ws,original)
        for W,H in ((1080,1920),(1920,1080)):
            p=make_plan(ws,Config(style_preset='ekspresif',target_w=W,target_h=H))
            self.assertIn('terus-terusan',[w['text'] for f in p['phrases'] for w in f['words']])
            self.assertEqual([i for f in p['phrases'] for w in f['words'] for i in w['word_ids']],list(range(5)))
    def test_three_part_hyphen_keeps_existing_dash(self):
        self.assertEqual(display_units(words('gara - gara kesentil'))[0]['word'],'gara-gara')
    def test_negative_number_is_not_attached_to_previous_word(self):
        self.assertEqual([w['word'] for w in display_units(words('rugi -5 persen'))],['rugi','-5 persen'])
    def test_hyphen_does_not_bridge_cuts_or_long_pauses(self):
        for field,value in [('part',2),('start',9.)]:
            ws=words('terus -terusan');ws[1][field]=value;ws[1]['end']=max(10.,ws[1]['end'])
            self.assertEqual(len(display_units(ws)),2)
    def test_short_middle_focus_does_not_force_three_lines(self):
        for W,H in ((1080,1920),(1920,1080)):
            cfg=Config(style_preset='ekspresif',target_w=W,target_h=H)
            p=make_plan(words('jadi hilang dan itu',50.),cfg,keywords=['hilang'])
            self.assertLessEqual(len({w['baseline'] for w in p['phrases'][0]['words']}),2)
            self.assertGreaterEqual(p['readability']['phrases'][0]['min_visible_lower_px'],14)
            self.assertTrue(inspect_caption_plan(p,cfg)['passed'])
    def test_all_fonts_in_a_row_share_true_baseline(self):
        cfg=Config(style_preset='ekspresif',caption_composition='editorial',target_w=1920,target_h=1080)
        p=make_plan(words('itu yang bahaya'),cfg)
        for phrase in p['phrases']:
            for w in phrase['words']:
                from clipper.typography import font
                a,d=font(cfg.fonts_dir,w['size'],w['font_id']).getmetrics()
                self.assertAlmostEqual(w['y']+(a-d)/2,w['baseline'],places=2)
    def test_auto_motion_has_blur_pop_and_all_four_directions(self):
        styles=set();directions=set()
        for seed in range(64):
            p=make_plan(words('mencoba memahami penjelasan ini'),Config(style_preset='ekspresif',caption_seed=seed))
            for f in p['phrases']:
                styles.add(f['design']['template'])
                if f['design']['template']=='slide':directions.add(f['design']['direction'])
        self.assertTrue({'magazine','narrative','blur','slide'}<=styles)
        self.assertEqual(directions,{'left','right','up','down'})
    def test_manual_blur_choice_survives_auto_composition(self):
        p=make_plan(words('Itu yang bahaya'),Config(style_preset='ekspresif',caption_template_policy='manual',caption_style='blur'))
        self.assertTrue(all(f['design']['template']=='blur' for f in p['phrases']))


class MeasuredPlacement(unittest.TestCase):
    def test_compact_phrase_fits_where_old_generic_panel_does_not(self):
        for W,H in ((1080,1920),(1920,1080)):
            cfg=Config(style_preset='ekspresif',target_w=W,target_h=H)
            bottom=.82 if H>W else .84
            boxes=[{'kind':'ocr','box':[0,0,W,H*.65]},{'kind':'ocr','box':[0,H*bottom,W,H*(1-bottom)]}]
            self.assertFalse(placement.choose_panel(boxes,W,H,cfg=cfg)[2])
            ws=words('tetap tenang')
            panel,pos,clear=placement.choose_panel(boxes,W,H,cfg=cfg,phrases=[ws])
            self.assertTrue(clear,(W,H,panel))
            anchor=dict(time=.5,start=0,end=2,panel=panel,position=pos,protected=boxes)
            p=make_plan(ws,cfg,anchors=[anchor]);self.assertTrue(inspect_caption_plan(p,cfg)['passed'])
    def test_cross_shot_conflict_reserves_only_phrase_interval(self):
        cfg=Config(style_preset='ekspresif',target_w=1920,target_h=1080)
        shot=dict(mode='fit',rect=[0,0,1920,1080],start=0.,end=10.,source_start=0.,source_end=10.,position='bottom',zoom_at=None,
                  protected_source=[{'kind':'material','box':[0,0,1920,640]}])
        other=copy.deepcopy(shot);other.update(start=10.,end=20.,source_start=10.,source_end=20.,protected_source=[{'kind':'material','box':[0,400,1920,680]}])
        plan={'shots':[shot,other],'words':words('tetap tenang',9.5,.65),'fps':30}
        placement.apply(plan,cfg);anchors=placement.caption_anchors(plan,cfg)
        bands=[s for s in plan['shots'] if s.get('image_height')]
        self.assertTrue(bands);self.assertTrue(all(s['start']>=9.5 and s['end']<=11.0 for s in bands))
        self.assertAlmostEqual(sum(s['end']-s['start'] for s in plan['shots']),20.)
        self.assertTrue(all(abs(s['source_start']-s['start'])<.0001 for s in plan['shots']))
        p=make_plan(plan['words'],cfg,anchors=anchors);self.assertTrue(inspect_caption_plan(p,cfg)['passed'])
        before=copy.deepcopy(plan['shots']);placement.caption_anchors(plan,cfg);self.assertEqual(plan['shots'],before)
    def test_manual_position_does_not_change_shots(self):
        cfg=Config(style_preset='ekspresif',caption_position='bottom')
        s=dict(mode='fit',rect=[0,0,1080,1920],start=0.,end=5.,source_start=0.,source_end=5.,position='bottom')
        p={'shots':[s],'words':words('tetap tenang')};placement.apply(p,cfg);placement.caption_anchors(p,cfg)
        self.assertNotIn('image_height',s);self.assertEqual(len(p['shots']),1)


class TimestampEvidence(unittest.TestCase):
    def test_mask_is_attached_only_to_matching_sample_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';source.write_bytes(b'fixture')
            shot={'source_start':0.,'source_end':2.,'area_samples':[{'time':.1},{'time':.9},{'time':1.8},{'categories':'stale'}]}
            plan={'shots':[shot]};cfg=Config(style_preset='adaptif',work_dir=tmp)
            response={'status':'ready','frames':[{'time':.1,'protected':[],'categories':'early'},{'time':1.8,'protected':[],'categories':'late'}]}
            with patch.object(visual4,'component_runtime',return_value={'generation':'fixture'}),patch.object(visual4,'backend',return_value=response) as backend:
                segmentation.enrich(source,plan,cfg)
            self.assertEqual(backend.call_args.args[1]['times'],[.1,.9,1.8])
            self.assertEqual(shot['area_samples'][0]['categories'],'early');self.assertEqual(shot['area_samples'][2]['categories'],'late')
            self.assertNotIn('categories',shot['area_samples'][1]);self.assertNotIn('categories',shot['area_samples'][3])


class LocalAlignment(unittest.TestCase):
    def test_studio_render_adapter_keeps_alignment_evidence(self):
        from clipper.studio_exchange import render_words
        ws=words('ucapan sumber benar');ws[1]['probability']=.4
        transcript={'words':ws,'raw_words':copy.deepcopy(ws),'duration':1.35,'language':'id'}
        doc={'source':{'source_id':'fixture'},'transcript_id':'take','transcript_revision':0}
        with tempfile.TemporaryDirectory() as tmp:
            rows=render_words(transcript,doc,{'start':0.,'end':1.35},Config(work_dir=tmp,transcript_correction=False))
        self.assertEqual(rows[1]['probability'],.4);self.assertTrue(selected_alignment.eligible(rows[1]))
        self.assertEqual(rows[1]['source_word_ids'],[1])
    def data(self):
        ws=words('ucapan sumber benar');ws[1]['probability']=.4
        p={'origin_word_ids':[1],'text':'sumber','words':[{'word':'sumber','start':.48,'end':.87,'score':.9}],
           'provenance':{'kind':'fixture'}}
        return ws,p,{'start':0.,'end':1.35}
    def test_verified_timing_applies_only_to_render_copy(self):
        ws,p,clip=self.data();before=copy.deepcopy(ws);out,n=selected_alignment.apply_patches(ws,[p],clip)
        self.assertEqual(n,1);self.assertEqual(out[1]['start'],.48);self.assertEqual(ws,before)
        self.assertEqual(out[1]['word_id'],1);self.assertEqual(out[1]['word'],'sumber')
    def test_manual_timing_cannot_be_overwritten(self):
        for field,value in [('timing_status','manual'),('alignment_method','manual')]:
            ws,p,clip=self.data();ws[1][field]=value
            out,n=selected_alignment.apply_patches(ws,[p],clip);self.assertEqual(n,0);self.assertEqual(out,ws)
    def test_unmeasured_or_cross_neighbor_alignment_is_rejected(self):
        for change in ({'score':0},{'start':0.1},{'word':'berubah'},{'end':1.2}):
            ws,p,clip=self.data();p['words'][0].update(change)
            out,n=selected_alignment.apply_patches(ws,[p],clip);self.assertEqual(n,0);self.assertEqual(out,ws)
    def test_words_outside_selected_clip_are_untouched(self):
        ws,p,clip=self.data();clip['start']=.5
        out,n=selected_alignment.apply_patches(ws,[p],clip);self.assertEqual(n,0)
    def test_unavailable_model_does_not_launch_worker(self):
        from clipper import speech_jobs
        ws,p,clip=self.data()
        with patch.object(speech_jobs,'alignment_runtime',side_effect=ValueError('model belum ada')),patch.object(speech_jobs,'run') as worker:
            out,report=selected_alignment.prepare('unused',ws,clip,Config())
        self.assertEqual(report['status'],'unavailable');self.assertEqual(out,ws);worker.assert_not_called()
    def test_disabled_alignment_has_no_runtime_lookup(self):
        from clipper import speech_jobs
        ws,p,clip=self.data()
        with patch.object(speech_jobs,'alignment_runtime') as runtime:
            _,report=selected_alignment.prepare('unused',ws,clip,Config(align_selected_clips=False))
        runtime.assert_not_called();self.assertEqual(report['status'],'disabled')


class E5Guardrails(unittest.TestCase):
    def candidates(self):return [(0,{'main_claim':'Tidak boleh rugi 5 persen'}),(1,{'main_claim':'Boleh rugi 5 persen'})]
    def test_missing_runtime_keeps_existing_semantic_path(self):
        with patch.object(visual4,'component_runtime',return_value=None),patch.object(visual4,'backend') as backend:
            pairs,report=semantic_rank.neighbors(self.candidates(),Config())
        self.assertEqual(pairs,[]);self.assertEqual(report['removed_by_embedding'],0);backend.assert_not_called()
    def test_high_similarity_is_only_a_comparison_proposal(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(visual4,'component_runtime',return_value={}),patch.object(visual4,'backend',return_value={'status':'ready','pairs':[{'a':0,'b':1,'score':.99}]}):
            # A ready generation must be truthy; no empty/unverified receipt.
            with patch.object(visual4,'component_runtime',return_value={'generation':'fixture'}):
                pairs,report=semantic_rank.neighbors(self.candidates(),Config(work_dir=tmp))
        self.assertEqual(pairs,[(0,1)]);self.assertEqual(report['removed_by_embedding'],0)
    def test_invalid_identity_or_score_rejected(self):
        for row in ({'a':0,'b':44,'score':.99},{'a':0,'b':1,'score':float('nan')}):
            with tempfile.TemporaryDirectory() as tmp,patch.object(visual4,'component_runtime',return_value={'generation':'fixture'}),patch.object(visual4,'backend',return_value={'status':'ready','pairs':[row]}):
                pairs,report=semantic_rank.neighbors(self.candidates(),Config(work_dir=tmp))
            self.assertEqual(pairs,[]);self.assertEqual(report['status'],'failed')


if __name__=='__main__':unittest.main()
