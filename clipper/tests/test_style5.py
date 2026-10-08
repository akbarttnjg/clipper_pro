"""Stage 5 behavior tests. Run with Python's standard-library unittest."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import wave
import struct
from clipper.config import Config,validate_overrides
from clipper.typography import make_plan,display_units
from clipper.style5 import readability,annotate_prosody
from clipper.captions_pro import write_plan
from clipper import caption_renderer


def words(text='Risiko bukan alasan untuk berhenti belajar. Modal Rp 5 juta tetap perlu dijaga.',step=.42):
    return [{'word':w,'word_id':i,'token_id':'t'+str(i),'start':i*step,'end':(i+1)*step} for i,w in enumerate(text.split())]


class Plans(unittest.TestCase):
    def config(self,**kwargs):return Config(style_preset='ekspresif',target_w=640,target_h=360,**kwargs)
    def test_repeat_preserves_saved_design(self):
        cfg=self.config();self.assertEqual(make_plan(words(),cfg),make_plan(words(),cfg))
    def test_seed_changes_design_without_changing_text(self):
        a=make_plan(words(),self.config(caption_seed=1));b=make_plan(words(),self.config(caption_seed=2))
        self.assertNotEqual([p['design'] for p in a['phrases']],[p['design'] for p in b['phrases']])
        self.assertEqual([w['text'] for p in a['phrases'] for w in p['words']],[w['text'] for p in b['phrases'] for w in p['words']])
    def test_preview_and_final_share_decisions(self):
        cfg=self.config();a=make_plan(words(),cfg);b=make_plan(words(),replace(cfg,target_w=1920,target_h=1080))
        self.assertEqual([p['phrase_id'] for p in a['phrases']],[p['phrase_id'] for p in b['phrases']])
        self.assertEqual([p['design'] for p in a['phrases']],[p['design'] for p in b['phrases']])
    def test_ratios_compose_independently(self):
        cfg=self.config();a=make_plan(words(),cfg);b=make_plan(words(),replace(cfg,target_w=360,target_h=640))
        self.assertNotEqual(a['phrases'][0]['panel'],b['phrases'][0]['panel'])
        self.assertEqual(a['phrases'][0]['phrase_id'],b['phrases'][0]['phrase_id'])
    def test_rapi_still_and_whole_phrase_visible(self):
        cfg=replace(self.config(),style_preset='rapi');p=make_plan(words(),cfg)
        self.assertTrue(all(w['motion']=='still' and w['keyframes'][0]['opacity']==1 for f in p['phrases'] for w in f['words']))
    def test_adaptive_quiets_board(self):
        cfg=replace(self.config(),style_preset='adaptif',source_kind='board');p=make_plan(words(),cfg)
        self.assertTrue(all(f['design']['quiet'] and f['design']['material'] for f in p['phrases']))
    def test_adaptive_quiets_dense_speech(self):
        p=make_plan(words(step=.15),replace(self.config(),style_preset='adaptif'))
        self.assertTrue(any(f['design']['quiet'] for f in p['phrases']))
    def test_material_anchor_quiets_auto_source(self):
        cfg=replace(self.config(),style_preset='adaptif');p=make_plan(words(),cfg,anchors=[{'start':0,'end':30,'position':'bottom','panel':[40,270,540,75],'protected':[],'has_material':True}])
        self.assertTrue(all(f['design']['material'] and f['design']['quiet'] for f in p['phrases']))
    def test_currency_lineage_survives_multiple_group_passes(self):
        original=words('Rp 5 juta aman');a=display_units(original);b=display_units(a)
        self.assertEqual(a,b);self.assertEqual(a[0]['word'],'Rp5 juta');self.assertEqual(a[0]['word_ids'],[0,1,2])
    def test_original_transcript_not_mutated(self):
        original=words();saved=copy.deepcopy(original);make_plan(original,self.config());self.assertEqual(original,saved)
    def test_negation_stays_with_keyword_phrase(self):
        p=make_plan(words('Ini bukan risiko besar.'),self.config(),keywords=['risiko besar'])
        emph=[w['text'] for f in p['phrases'] for w in f['words'] if w['emphasis']]
        self.assertIn('bukan',emph);self.assertIn('risiko',emph)
    def test_missing_ids_have_stable_identity(self):
        rows=words();[w.pop('word_id') for w in rows];self.assertEqual(make_plan(rows,self.config()),make_plan(rows,self.config()))
    def test_toggle_removes_color_emphasis(self):
        p=make_plan(words(),self.config(semantic_emphasis=False));self.assertTrue(all(not w['emphasis'] and w['color']=='#FFFFFF' for f in p['phrases'] for w in f['words']))
    def test_ass_uses_exact_saved_plan(self):
        cfg=self.config();p=make_plan(words(),cfg)
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'captions.ass';write_plan(p,file,cfg)
            self.assertEqual(p,json.loads(file.with_suffix('.caption-plan.json').read_text()))
            self.assertIn('Dialogue:',file.read_text())
    def test_legacy_still_supported(self):
        p=make_plan(words(),replace(self.config(),style_preset='legacy'));self.assertEqual(p['version'],4)
    def test_expressive_alignment_passes_production_qc(self):
        from clipper.caption_checks import inspect_caption_plan
        cfg=self.config();p=make_plan(words(),cfg)
        self.assertTrue(inspect_caption_plan(p,cfg,expected_words=words())['passed'])
    def test_explicit_alignment_overrides_preset_variation(self):
        from clipper.caption_checks import inspect_caption_plan
        cfg=self.config(caption_align='right');p=make_plan(words(),cfg)
        self.assertTrue(all(f['alignment']=='right' for f in p['phrases']))
        self.assertTrue(inspect_caption_plan(p,cfg)['passed'])
    def test_empty_transcript(self):self.assertEqual(make_plan([],self.config())['phrases'],[])


class Reading(unittest.TestCase):
    def setUp(self):self.cfg=Config(style_preset='rapi',target_w=640,target_h=360);self.plan=make_plan(words(),self.cfg)
    def codes(self,p=None,cfg=None):return {i['code'] for i in readability(p or self.plan,cfg or self.cfg)['issues']}
    def test_normal_phrase_passes(self):self.assertEqual(self.codes(),set())
    def test_reading_speed_detected(self):
        p=copy.deepcopy(self.plan);p['phrases'][0]['end']=p['phrases'][0]['start']+.1;self.assertIn('reading_speed',self.codes(p))
    def test_frame_overflow_detected(self):
        p=copy.deepcopy(self.plan);p['phrases'][0]['words'][0]['x']=-90;self.assertIn('frame_overflow',self.codes(p))
    def test_protected_collision_detected(self):
        p=copy.deepcopy(self.plan);p['phrases'][0]['protected']=[{'kind':'face','box':p['phrases'][0]['panel']}];self.assertIn('protected_collision',self.codes(p))
    def test_text_collision_detected(self):
        p=copy.deepcopy(self.plan);a,b=p['phrases'][0]['words'][:2];b['x']=a['x'];b['y']=a['y'];self.assertIn('word_collision',self.codes(p))
    def test_missing_outline_requires_review(self):self.assertIn('background_unknown',self.codes(cfg=replace(self.cfg,caption_backdrop=False)))
    def test_low_contrast_has_fix(self):
        p=copy.deepcopy(self.plan);p['phrases'][0]['words'][0]['color']='#101010';self.assertIn('contrast',self.codes(p));self.assertTrue(all(i['fix'] for i in readability(p,self.cfg)['issues']))
    def test_minimum_font_detected(self):
        p=copy.deepcopy(self.plan);p['phrases'][0]['words'][0]['size']=3;self.assertIn('small_text',self.codes(p))
    def test_motion_envelope_not_just_static_box(self):
        p=copy.deepcopy(self.plan);p['phrases'][0]['words'][0]['keyframes'][0]['dx']=900;self.assertIn('frame_overflow',self.codes(p))


class RuntimeAndSettings(unittest.TestCase):
    def test_valid_settings(self):
        actual=validate_overrides({'style_preset':'adaptif','caption_seed':31,'caption_renderer':'auto','illustration_mode':'labels','sfx_max':2,'sfx_gap_s':12,'semantic_emphasis':False})
        self.assertEqual(actual['caption_seed'],31);self.assertFalse(actual['semantic_emphasis'])
    def test_invalid_enum_rejected(self):
        for key in ('style_preset','caption_renderer','illustration_mode','broll_ranker','sfx_mode'):
            with self.assertRaises(ValueError):validate_overrides({key:'bad'})
    def test_seed_requires_integer(self):
        for value in (True,1.2,-1,'NaN','2.0'):
            with self.assertRaises((ValueError,TypeError)):validate_overrides({'caption_seed':value})
    def test_sfx_budget_rejected(self):
        for values in ({'sfx_max':7},{'sfx_gap_s':2},{'sfx_gap_s':'NaN'}):
            with self.assertRaises(ValueError):validate_overrides(values)
    def test_auto_falls_back_without_installing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=Config(caption_renderer='auto',visual_runtime_root=tmp);out=caption_renderer.render({'version':5},cfg,Path(tmp)/'output',2)
            self.assertEqual(out['engine'],'ass');self.assertEqual(out['status'],'fallback');self.assertFalse((Path(tmp)/'output').exists())
    def test_required_remotion_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):caption_renderer.render({'version':5},Config(caption_renderer='remotion',visual_runtime_root=tmp),tmp,2)
    def test_ass_needs_no_node(self):self.assertEqual(caption_renderer.render({'version':5},Config(),'/does-not-exist',2)['engine'],'ass')
    def test_prosody_rms_keeps_words_and_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'voice.wav'
            with wave.open(str(path),'wb') as f:
                f.setparams((1,2,8000,0,'NONE','not compressed'));f.writeframes(b''.join(struct.pack('<h',1000 if i<8000 else 12000) for i in range(16000)))
            original=[{'word':'bukan','word_id':1,'start':0.,'end':1.},{'word':'risiko','word_id':2,'start':1.,'end':2.}]
            actual=annotate_prosody(original,path);self.assertEqual([w['word'] for w in actual],['bukan','risiko']);self.assertEqual([w['word_id'] for w in actual],[1,2])
            self.assertEqual(actual[1]['prosody_method'],'pcm_rms_relative_to_clip_median')


if __name__=='__main__':unittest.main()
