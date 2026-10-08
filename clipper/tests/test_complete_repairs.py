"""Complete repair regressions: real fonts/SQLite/FFmpeg, controlled detectors.

Face/CTC models and native editor applications are not inferred from these tests.
"""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np
from clipper.config import Config,validate_overrides
from clipper import framing,story,boundaries,style5,render,editplan
from clipper.typography import make_plan

# Only geometry functions use this stub when OpenCV is absent on the QA host.
# A installed OpenCV package is used unchanged on the user's Windows machine.
try:
    import cv2
except ModuleNotFoundError:
    cv2=types.ModuleType('cv2')
    cv2.__spec__=importlib.util.spec_from_loader('cv2',loader=None)
    cv2.VideoCapture=lambda *_:types.SimpleNamespace(release=lambda:None)
    sys.modules['cv2']=cv2
from clipper import visual4,placement,composition


def words(text='Risiko bukan alasan untuk berhenti belajar.',step=.5):
    return [{'word':t,'word_id':i,'word_ids':[i],'token_id':'t'+str(i),'start':i*step,'end':(i+1)*step}
            for i,t in enumerate(text.split())]


def sample_rows(count=12,textures=20,panel=None):
    face=[280.,65.,80.,105.]
    return [{'t':i*.5,'faces':[face],'tracks':[{'track_id':'face-0001','box':face,'confidence':.94,'time':i*.5}],
        'hist':None,'area':[0,0,640,360],'panel':panel,'texts':[[j*22,300,15,7] for j in range(textures)],'ocr':[]} for i in range(count)]


class Framing(unittest.TestCase):
    def test_texture_does_not_turn_one_speaker_into_a_screen(self):
        self.assertEqual(visual4.classify(sample_rows())['kind'],'speaker')

    def test_dense_geometry_without_speaker_stays_conservative(self):
        rows=sample_rows()
        for r in rows:r['tracks']=[];r['faces']=[]
        self.assertEqual(visual4.classify(rows)['kind'],'screen')

    def test_manual_scene_choice_overrides_automatic_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kind in ('speaker','podcast','board','screen','chart'):
                cfg=Config(source_kind=kind,work_dir=tmp)
                result=visual4.describe('unused',sample_rows(panel=[0,0,300,360]),cfg,{'width':640,'height':360},{'status':'disabled'})
                self.assertEqual(result['scene']['kind'],kind)
                self.assertEqual(result['scene']['basis'],'manual')

    def test_single_speaker_portrait_fills_without_texture_forcing_band(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=Config(work_dir=tmp,target_w=360,target_h=640,ocr_enabled=False)
            plan=editplan.build(words(),{'start':0,'end':6,'title':'Framing','keywords':[]},replace(cfg,trim_silence=False))
            rows=sample_rows()
            with patch.object(visual4,'collect',return_value=(rows,{'key':'fixture'})),patch.object(visual4,'component_runtime',return_value=None),patch.object(cv2,'VideoCapture',return_value=types.SimpleNamespace(release=lambda:None)):
                composition.analyze('unused',plan,cfg,{'width':640,'height':360,'duration':6})
            self.assertTrue(all(s['mode']=='fill' for s in plan['shots']))
            self.assertTrue(all(not s.get('image_height') for s in plan['shots']))
            self.assertTrue(all(not any(b['kind']=='text' for b in s['protected_source']) for s in plan['shots']))
            self.assertTrue(all(s['geometry_diagnostics']['unconfirmed_regions']>0 for s in plan['shots']))

    def test_manual_regions_and_material_are_never_demoted_to_texture(self):
        self.assertTrue(framing.geometry_is_protected('speaker',True))
        self.assertTrue(framing.geometry_is_protected('unknown',False))
        self.assertFalse(framing.geometry_is_protected('podcast',False))

    def test_compaction_keeps_every_source_pixel_and_distinct_ocr_identity(self):
        items=[{'kind':'face','box':[10+i*.2,20,30,50]} for i in range(30)]
        items += [{'kind':'ocr','box':[10,20,30,50],'ocr_id':str(i)} for i in range(2)]
        before=copy.deepcopy(items);result=framing.compact_protected(items)
        self.assertEqual(len(result),3);self.assertEqual(items,before)
        for item in items:
            self.assertTrue(any(old['kind']==item['kind'] and placement.overlap(old['box'],item['box'])>=item['box'][2]*item['box'][3]-.001 for old in result))

    def test_adaptive_grid_finds_space_before_shrinking_source(self):
        W,H=1920,1080
        obstacles=[{'kind':'face','box':[700,60,450,660]}]
        selected,_,clear=placement.choose_panel(obstacles,W,H)
        self.assertTrue(clear);self.assertEqual(placement.overlap(selected,obstacles[0]['box']),0)

    def test_fallback_strip_keeps_speaker_crop_sized_for_display_area(self):
        cfg=Config(target_w=360,target_h=640)
        shot={'mode':'fill','rect':[220,0,202,360],'face':[280,65,80,105],
              'active_area':[0,0,640,360],'head_bounds':[280,65,80,105],'zoom_at':2.,'protected_source':[]}
        placement.reserve_band(shot,cfg)
        self.assertEqual(shot['mode'],'fill');self.assertIsNone(shot['zoom_at'])
        self.assertLess(abs(shot['rect'][2]/shot['rect'][3]-360/shot['image_height']),.01)
        viewport=placement.mappings(shot,360,640)[0][1][-1]
        self.assertEqual(viewport,[0,0,360,shot['image_height']])

    def test_zoom_cannot_clip_sampled_heads(self):
        self.assertFalse(framing.zoom_keeps_heads([{'kind':'face','box':[10,0,50,70]}],100,100,.08))
        self.assertTrue(framing.zoom_keeps_heads([{'kind':'face','box':[35,25,30,45]}],100,100,.08))

    def test_crop_bounds_and_source_are_preserved(self):
        area=[0,0,1920,1080];before=area.copy()
        for aspect in (9/16,16/9,1):
            rect=framing.crop_rect(area,[790,260,290,366],aspect)
            self.assertGreaterEqual(min(rect),0)
            self.assertLessEqual(rect[0]+rect[2],1920)
            self.assertLessEqual(rect[1]+rect[3],1080)
            self.assertEqual(rect[2]%2,0);self.assertEqual(rect[3]%2,0)
        self.assertEqual(area,before)


class Story(unittest.TestCase):
    def test_identical_footage_is_duplicate_despite_different_nested_claims(self):
        ws=words('Belajar mengelola risiko itu penting untuk menjaga modal kita.',step=2)
        a={'start':0,'end':20,'main_claim':'Belajar mengelola risiko itu penting','story_kind':'explanation'}
        b={**a,'main_claim':'mengelola risiko itu penting untuk menjaga modal','story_kind':'answer'}
        self.assertTrue(story.duplicate(a,b,ws))

    def test_different_spoken_numbers_are_preserved(self):
        ws=words('Modal Rp5 juta tetap dijaga. Modal Rp7 juta tetap dijaga.',step=1)
        a={'start':0,'end':5,'main_claim':'Modal Rp5 juta tetap dijaga.'}
        b={'start':5,'end':10,'main_claim':'Modal Rp7 juta tetap dijaga.'}
        self.assertFalse(story.duplicate(a,b,ws))

    def test_zero_count_limit_follows_unique_stories(self):
        ws=words('Belajar risiko menjaga modal penting sekali bagi kita.',step=2)
        a={'start':0,'end':16,'title':'A','rubric':{'value':5},'main_claim':'Belajar risiko menjaga modal penting'}
        b={**a,'title':'B','main_claim':'risiko menjaga modal penting sekali'}
        self.assertEqual(len(story.distinct([a,b],ws,Config(num_clips=0))),1)

    def test_unfinished_numbered_promise_requires_review(self):
        ws=words('Ada tiga cara. Pertama belajar. Kedua berlatih.',step=.6)
        self.assertTrue(any('penanda urutannya' in i for i in boundaries.audit({'start':0,'end':ws[-1]['end']},ws)))

    def test_complete_numbered_promise_not_flagged(self):
        ws=words('Ada tiga cara. Pertama belajar. Kedua berlatih. Ketiga evaluasi.',step=.6)
        self.assertFalse(any('penanda urutannya' in i for i in boundaries.audit({'start':0,'end':ws[-1]['end']},ws)))


class Typography(unittest.TestCase):
    def cfg(self,**kwargs):return Config(style_preset='adaptif',target_w=640,target_h=360,**kwargs)

    def test_incidental_source_text_does_not_quiet_or_shrink_material_free_scene(self):
        ws=words(step=.8)
        p=make_plan(ws,self.cfg(),anchors=[{'start':0,'end':10,'position':'left','panel':[30,200,560,150],
            'has_material':False,'protected':[{'kind':'text','box':[5,5,5,5]}]}])
        self.assertTrue(all(not x['design']['material'] and not x['design']['quiet'] for x in p['phrases']))

    def test_user_template_survives_expressive_preset(self):
        p=make_plan(words(step=.8),self.cfg(caption_template_policy='manual',caption_style='blur'))
        self.assertTrue(all(x['design']['template']=='blur' for x in p['phrases']))

    def test_measured_prominence_changes_actual_focus_size(self):
        ws=words('Risiko modal perlu dijaga.',step=.8)
        plain=make_plan(ws,self.cfg(),keywords=['risiko'])
        loud=make_plan([{**w,'prosody_prominence':1. if w['word']=='Risiko' else 0.} for w in ws],self.cfg(),keywords=['risiko'])
        a=[w for p in plain['phrases'] for w in p['words'] if w['text']=='Risiko'][0]
        b=[w for p in loud['phrases'] for w in p['words'] if w['text']=='Risiko'][0]
        self.assertGreater(b['size'],a['size'])

    def test_disabled_emphasis_removes_font_hierarchy_too(self):
        p=make_plan(words(),self.cfg(semantic_emphasis=False))
        self.assertTrue(all(w['font_id']=='dm_sans' and not w['emphasis'] for ph in p['phrases'] for w in ph['words']))

    def test_reading_hold_uses_real_gap_without_overlapping_next_phrase(self):
        ws=words('Risiko penting.',step=.1)+[{'word':'Lanjut.','word_id':9,'word_ids':[9],'start':2.,'end':3.}]
        p=make_plan(ws,replace(self.cfg(),style_preset='rapi'))
        first=p['phrases'][0]
        self.assertGreater(first['end'],.34)
        self.assertLessEqual(first['end'],p['phrases'][1]['start'])
        self.assertGreaterEqual(first['words'][0]['keyframes'][-1]['t'],first['end']-first['start']-.04)

    def test_negation_and_currency_stay_intact(self):
        p=make_plan(words('Bukan risiko besar. Modal Rp 5 juta aman.',step=.8),self.cfg(),keywords=['risiko besar'])
        tokens=[w for ph in p['phrases'] for w in ph['words']]
        self.assertTrue(any(w['text']=='bukan' or w['text']=='Bukan' for w in tokens if w['emphasis']))
        money=next(w for w in tokens if 'Rp5 juta' in w['text']);self.assertEqual(len(money['word_ids']),3)

    def test_new_settings_are_validated(self):
        self.assertEqual(validate_overrides({'caption_template_policy':'manual','source_kind':'chart'})['source_kind'],'chart')
        with self.assertRaises(ValueError):validate_overrides({'caption_template_policy':'unknown'})


class Audio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.source=cls.root/'source.wav'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=3',
            '-f','lavfi','-i','anullsrc=r=48000:cl=mono:d=3','-filter_complex','[0:a][1:a]concat=n=2:v=0:a=1[out]',
            '-map','[out]','-ar','48000',str(cls.source)],check=True,capture_output=True)
        cls.music=cls.root/'music.wav'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','sine=frequency=880:duration=6','-ar','48000',str(cls.music)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def plan(self):return {'fps':30,'duration':6.,'spans':[{'source_start':0.,'source_end':6.,'duration_frames':180,'kind':'body','end':6.}],
        'shots':[{'start':0.,'zoom_at':None}],'captions':{'phrases':[]}}

    def test_aspect_and_style_changes_reuse_voice_but_tampering_invalidates_it(self):
        cfg=Config(work_dir=str(self.root),audio_normalize=False)
        a=self.plan();one=render.voice_stem(self.source,a,cfg,self.root/'one')
        b=self.plan();two=render.voice_stem(self.source,b,replace(cfg,target_w=1920,target_h=1080,caption_style='blur'),self.root/'two')
        self.assertEqual(one,two);self.assertTrue(b['voice_cache']['reused'])
        Path(two).write_bytes(b'corrupt')
        c=self.plan();three=render.voice_stem(self.source,c,cfg,self.root/'three')
        self.assertEqual(one,three);self.assertFalse(c['voice_cache']['reused']);self.assertGreater(Path(three).stat().st_size,1000)

    def test_music_is_ducked_during_real_voice_and_master_has_expected_duration(self):
        cfg=Config(work_dir=str(self.root),audio_normalize=False,music_path=str(self.music),music_db=-16)
        p=self.plan();result=render.audio_stems(self.source,p,cfg,self.root/'mixed')
        raw=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',p['audio']['stems']['music'],'-f','f32le','-ac','1','-'],check=True,capture_output=True).stdout
        data=np.frombuffer(raw,dtype='<f4')
        rms=lambda a,b:float(np.sqrt(np.mean(data[int(a*48000):int(b*48000)]**2)))
        self.assertLess(rms(1.,2.),rms(4.,5.)*.9)
        duration=float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',result],check=True,capture_output=True,text=True).stdout)
        self.assertLess(abs(duration-6.),.01)


if __name__=='__main__':unittest.main()
