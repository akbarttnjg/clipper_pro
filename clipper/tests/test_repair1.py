"""Repair 1 regressions at real SQLite/FFmpeg and measured-model boundaries.

No ASR/CTC weights, browser renderers or native editor applications are run here.
"""
import copy
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import unittest
from dataclasses import replace
from unittest.mock import patch

from clipper.config import Config
from clipper import captions_pro, explanation5, media_context, projects, render, speech_jobs, stage3, studio_worker, transcript_correction, trim
from clipper.project_store import ProjectStore
from clipper.job_queue import JobQueue
from clipper.studio_service import StudioService
from clipper.typography import make_plan

ROOT=Path(__file__).resolve().parents[2]


def words():
    return [{'word':text,'word_id':i,'start':i*.6,'end':i*.6+.45}
            for i,text in enumerate(('kendalikan','ego','saat','trading'))]


class SpeechAndQueue(unittest.TestCase):
    def test_nested_unsorted_speech_is_not_trimmed(self):
        source=[{'word':'lanjut','start':3.,'end':4.}, {'word':'panjang','start':0.,'end':5.},
                {'word':'pendek','start':1.,'end':1.5}]
        before=copy.deepcopy(source)
        self.assertEqual(trim.keep_spans(source,0.,5.,Config(silence_max=1.2,silence_keep=.1)),[(0.,5.)])
        self.assertEqual(source,before)

    def test_real_silence_still_trimmed_inside_clip(self):
        spans=trim.keep_spans([{'start':.2,'end':1.},{'start':3.,'end':4.}],.5,3.5,Config(silence_max=1.2,silence_keep=.1))
        self.assertEqual(spans,[(.5,1.1),(2.9,3.5)])

    def test_old_queued_job_remains_visible_and_worker_checks_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue=JobQueue(ProjectStore(Path(tmp)/'studio.sqlite3'),tmp,autostart=False,recover=False)
            old=queue.enqueue('a','preview',{}, {'revision':'old'})
            for i in range(105):
                row=queue.enqueue('a','preview',{}, {'revision':i});queue.cancel(row['id'])
            other=queue.enqueue('b','preview',{}, {'revision':1})
            listed=queue.list('a')
            self.assertEqual(listed[0]['id'],old['id']);self.assertEqual(len(listed),101)
            self.assertNotIn(other['id'],[j['id'] for j in listed]);self.assertTrue(queue.has_queued())
            def claim_once():queue.stop_event.set();return None
            with patch.object(queue,'list',side_effect=AssertionError('Worker must not inspect history')),patch.object(queue,'claim',side_effect=claim_once) as claim:
                queue.run();claim.assert_called_once()

    def test_more_than_100_active_jobs_are_not_discarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue=JobQueue(ProjectStore(Path(tmp)/'studio.sqlite3'),tmp,autostart=False,recover=False)
            for i in range(110):queue.enqueue('a','preview',{}, {'revision':i})
            self.assertEqual(len(queue.list()),110)

    @unittest.skipUnless(importlib.util.find_spec('numpy'),'NumPy supplies real backend scalar types')
    def test_numpy_measurements_are_normalized_without_mutating_backend(self):
        import numpy as np
        original=[{'word':'Ketika','start':np.float64(0.),'end':np.float64(.52),'score':np.float64(.9)}]
        with self.assertRaisesRegex(ValueError,'Timing kata harus'):
            stage3.validate_alignment('Ketika',original,0.,.54,method='whisperx')
        normalized=speech_jobs.alignment_rows(original,0.)
        self.assertEqual(stage3.validate_alignment('Ketika',normalized,0.,.54,method='whisperx'),normalized)
        self.assertTrue(all(type(normalized[0][key]) is float for key in ('start','end','score')))
        self.assertEqual(type(original[0]['start']),np.float64)

    def test_invalid_measurements_still_rejected(self):
        base={'word':'aman','start':0.,'end':.5,'score':.9}
        for field,value in [('start',True),('score','0.9')]:
            with self.subTest(field=field),self.assertRaises(ValueError):speech_jobs.alignment_rows([{**base,field:value}],0.)
        for field,value in [('end',.6),('end',0.),('score',float('nan')),('score',0.)]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                stage3.validate_alignment('aman',speech_jobs.alignment_rows([{**base,field:value}],0.),0.,.54,method='whisperx')
        overlap=[base,{'word':'lagi','start':.4,'end':.54,'score':.9}]
        with self.assertRaises(ValueError):stage3.validate_alignment('aman lagi',speech_jobs.alignment_rows(overlap,0.),0.,.54,method='whisperx')

    def test_quoted_windows_style_copy_path_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,data in [('config.json','{"model_type":"wav2vec2"}'),('vocab.json','{}'),('preprocessor_config.json','{}'),('pytorch_model.bin','fixture')]:
                (root/name).write_text(data)
            self.assertEqual(speech_jobs.local_alignment_model('"'+tmp+'"'),str(root.resolve()))
            (root/'pytorch_model.bin').unlink()
            with self.assertRaisesRegex(ValueError,'Bobot'):speech_jobs.local_alignment_model(tmp)

    def fake_alignment(self,backend,candidates=True):
        wx=types.ModuleType('whisperx');nltk=types.ModuleType('nltk')
        wx.load_align_model=lambda **kwargs:('model',{})
        wx.align=lambda *args,**kwargs:{'word_segments':backend}
        source=[{'word_id':0,'word':'Ketika','start':0.,'end':.54,'manually_edited':candidates},
                {'word_id':1,'word':'saya','start':.54,'end':.82}]
        with patch.dict(sys.modules,{'whisperx':wx,'nltk':nltk}),patch.object(speech_jobs,'local_alignment_model',return_value='/fixture-model'),patch.object(speech_jobs,'_excerpt'):
            return speech_jobs._alignment('source',{'words':source,'language':'id','duration':2.},Config(),
                {'limit':12,'model_path':'/fixture-model','origin_word_ids':[]})

    @unittest.skipUnless(importlib.util.find_spec('numpy'),'NumPy supplies real backend scalar types')
    def test_alignment_adapter_accepts_real_scalar_types_and_produces_patch(self):
        import numpy as np
        result=self.fake_alignment([{'word':'Ketika','start':np.float64(0.),'end':np.float64(.52),'score':np.float64(.9)}])
        self.assertEqual(result['report']['aligned'],1);self.assertEqual(result['report']['attempted'],1)
        self.assertEqual(result['report']['errors'],[]);self.assertEqual(result['report']['status'],'aligned')
        self.assertEqual(result['patches'][0]['words'][0]['end'],.52)

    def test_alignment_failure_reports_measured_values_and_empty_patch(self):
        result=self.fake_alignment([{'word':'Ketika','start':0.,'end':.7,'score':.9}])
        self.assertEqual(result['patches'],[]);self.assertEqual(result['report']['status'],'failed')
        error=result['report']['errors'][0]
        self.assertEqual(error['diagnostic']['audio_end'],.54)
        self.assertEqual(error['diagnostic']['returned_words'][0]['end'],.7)
        json.dumps(result,allow_nan=False)

    def test_no_candidate_report_is_explicit(self):
        result=self.fake_alignment([],candidates=False)
        self.assertEqual(result['report']['attempted'],0);self.assertEqual(result['report']['status'],'skipped')
        self.assertEqual(result['patches'],[])


class CaptionsAndProjects(unittest.TestCase):
    def config(self,**kwargs):
        return Config(target_w=640,target_h=360,font_main='dm_sans',font_accent='dm_serif_italic',
                      caption_style='editorial',style_preset='legacy',fonts_dir=str(ROOT/'clipper/fonts'),**kwargs)

    def test_legacy_plan_freezes_color_motion_and_contrast(self):
        cfg=self.config();plan=make_plan(words(),cfg,['ego'])
        self.assertTrue(plan['contrast']);self.assertEqual(plan['template'],'editorial')
        emphasized=[word for phrase in plan['phrases'] for word in phrase['words'] if word['emphasis']]
        self.assertTrue(emphasized)
        self.assertTrue(all(w['color']==cfg.accent_hex and w['initial_color']==cfg.base_hex for w in emphasized))
        self.assertTrue(all(w['fade_seconds']>0 and w['color_transition']['duration']>0 for w in emphasized))

    def test_ass_obeys_saved_contrast_instead_of_later_config(self):
        cfg=self.config();plan=make_plan(words(),replace(cfg,caption_backdrop=False),['ego'])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'captions.ass';captions_pro.write_plan(plan,path,cfg)
            style=next(line for line in path.read_text().splitlines() if line.startswith('Style:'))
            self.assertEqual(style.split(',')[16:18],['0.0','0.0'])

    def test_backdrop_toggle_changes_real_libass_pixels(self):
        from clipper.ffmpeg_util import ass_filter
        cfg=self.config()
        with tempfile.TemporaryDirectory() as tmp:
            frames=[]
            for backdrop in (True,False):
                path=Path(tmp)/f'{backdrop}.ass'
                captions_pro.write_ass(words(),path,replace(cfg,caption_backdrop=backdrop),keywords=['ego'])
                frames.append(subprocess.check_output(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=gray:s=640x360:r=30:d=1',
                    '-vf',ass_filter(path,cfg),'-ss','0.3','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-threads','1','-']))
            self.assertEqual(len(frames[0]),640*360*3)
            self.assertGreater(sum(a!=b for a,b in zip(*frames)),100)

    def test_generated_motion_canvas_project_resolves_request_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=self.config(work_dir=tmp)
            def still(_image,target):Path(target).write_bytes(b'fixture')
            with patch.object(explanation5,'motion_runtime',return_value=None),patch('clipper.source_assets.still_video',side_effect=still):
                asset=explanation5.make_asset('Kendalikan ego saat trading',[0,1,2,3],cfg)
            project=Path(asset['editable_path']);self.assertTrue((project/'request.json').is_file())
            count=0
            for source in (project/'src').glob('*'):
                for match in re.finditer(r"from\s+['\"]([^'\"]*request\.json)['\"]",source.read_text()):
                    count+=1;self.assertTrue((source.parent/match.group(1)).is_file())
            self.assertEqual(count,2)
            self.assertEqual(json.loads((project/'request.json').read_text())['source_word_ids'],[0,1,2,3])

    def test_remotion_math_samples_legacy_colors_and_fades(self):
        plan=make_plan(words(),self.config(),['ego'])
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'plan.json';p.write_text(json.dumps(plan))
            code="""import fs from 'node:fs';import assert from 'node:assert/strict';
import {sampleAt} from './clipper/runtime/templates/remotion5/caption_math.mjs';
const plan=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
const p=plan.phrases.find(p=>p.words.some(w=>w.emphasis));const w=p.words.find(w=>w.emphasis);
assert.equal(sampleAt(w,0).opacity,0);
assert.equal(sampleAt(w,w.color_transition.start-.01).color,w.initial_color.toLowerCase());
assert.equal(sampleAt(w,w.color_transition.start+w.color_transition.duration+.01).color,w.color.toLowerCase());
assert.ok(sampleAt(w,w.phrase_duration-.01).opacity<1);
const v5={keyframes:[{t:0,scale:1,dx:0,dy:0,opacity:1,blur:0},{t:.1,scale:1.1,dx:2,dy:0,opacity:1,blur:0}]};
assert.equal(sampleAt(v5,.05).scale,1);assert.equal(sampleAt(v5,.1).scale,1.1);
"""
            subprocess.run(['node','--input-type=module','-e',code,str(p)],cwd=ROOT,check=True,capture_output=True)


class RealMedia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media=tempfile.TemporaryDirectory();base=Path(cls.media.name)
        cls.source=base/'source.mp4';cls.overlay=base/'overlay.webm';cls.mix=base/'mix.wav'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=1',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=1','-c:v','libx264','-threads','1','-c:a','aac','-shortest',str(cls.source)],check=True,capture_output=True)
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(cls.source),'-vn','-c:a','pcm_s16le',str(cls.mix)],check=True,capture_output=True)
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','color=c=red:s=320x180:r=30:d=1',
            '-c:v','libvpx-vp9','-threads','1',str(cls.overlay)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.media.cleanup()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)

    def config(self):
        return Config(target_w=320,target_h=180,use_nvenc=False,work_dir=str(self.base/'work'),
                      out_dir=str(self.base/'clips'),job_id='repair1',fonts_dir=str(ROOT/'clipper/fonts'))

    def plan(self):
        return {'version':2,'revision':0,'width':320,'height':180,'fps':30,'duration':1.,'duration_frames':30,
            'source':{'path':str(self.source),'width':320,'height':180,'fps':30,'duration':1.},
            'spans':[{'kind':'body','source_start':0.,'source_end':1.,'start':0.,'end':1.,'start_frame':0,'duration_frames':30}],
            'shots':[{'source_start':0.,'source_end':1.,'start':0.,'end':1.,'start_frame':0,'duration_frames':30,'rect':[0,0,320,180],
                      'mode':'fill','zoom_at':None,'position':'bottom','protected_source':[]}],
            'words':[],'display_words':[],'captions':{'version':5,'width':320,'height':180,'phrases':[]},'broll':[],
            'audio':{'mix':str(self.mix),'stems':{'voice':str(self.mix)},'music_original':'','music_db':-24.,'sfx_original':'','sfx_events':[]},
            'caption_renderer':{'engine':'remotion','path':str(self.overlay)},'render_config':{},'warnings':[],'title':'Fixture'}

    def mean_rgb(self,path):
        data=subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',str(path),'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','-threads','1','-'])
        return list(data[:3])

    def test_source_only_ignores_caption_and_insertions_but_final_keeps_them(self):
        cfg=self.config();plan=self.plan();final=self.base/'final.mp4'
        render.video(self.source,plan,cfg,None,final,self.mix)
        rgb=self.mean_rgb(final);self.assertGreater(rgb[0],200);self.assertLess(rgb[2],20)
        before=copy.deepcopy(plan)
        plan['broll']=[{'path':'/does-not-exist/insert.mp4'}]
        clean=self.base/'clean.mp4';render.video(self.source,plan,cfg,'/does-not-exist/captions.ass',clean,self.mix,mode='source_only')
        rgb=self.mean_rgb(clean);self.assertGreater(rgb[2],200);self.assertLess(rgb[0],20)
        self.assertNotIn('[captioned]',clean.with_suffix('.filter.txt').read_text())
        self.assertEqual(plan['caption_renderer'],before['caption_renderer']);self.assertEqual(len(plan['broll']),1)

    def test_hybrid_export_packs_genuinely_clean_video(self):
        cfg=self.config();plan=self.plan();final=self.base/'final.mp4'
        render.video(self.source,plan,cfg,None,final,self.mix)
        path=self.base/'edit-plan.json';path.write_text(json.dumps(plan))
        result={'plan_path':str(path),'revision':0,'absolute_file':str(final),'title':'Fixture','file':str(final),'length':1.,'width':320,'height':180}
        bundle=projects.export_bundle([result],cfg,mode='hybrid')
        clean=Path(bundle['folder'])/'Media/01-video-clean.mp4';rgb=self.mean_rgb(clean)
        self.assertGreater(rgb[2],200);self.assertLess(rgb[0],20)
        self.assertTrue(Path(bundle['zip']).is_file());self.assertEqual(bundle['export_mode'],'hybrid')

    def analyzer(self):
        svc=StudioService(self.base,Config(use_nvenc=False),autostart=False);doc=svc.create(self.source)
        state={'raw':[{'word':'treding','word_id':0,'start':.05,'end':.4,'probability':.95},
                      {'word':'tetap','word_id':1,'start':.45,'end':.8,'probability':.95}]}
        fake=types.ModuleType('clipper.pipeline')
        def analyze(_source,cfg,_progress):
            raw=copy.deepcopy(state['raw'])
            return transcript_correction.refine({'words':raw,'raw_words':raw,'heard_words':raw,'duration':1.,'language':'id'},cfg),[{'start':0.,'end':1.,'title':'Fixture','keywords':[],'warnings':[]}]
        fake.analyze=analyze
        info=media_context.inspect(self.source)
        def prepare(source,cfg,progress):
            return {'source_id':doc['source']['source_id'],'payload':{**info,'working_path':str(self.source),
                'audio_stream_id':doc['source']['source_id']+':audio:1','selected_audio_index':info['audio_tracks'][0]['index']}}
        return svc,doc,state,fake,prepare

    def run_analyze(self,svc,pid):
        studio_worker.execute(svc,svc.enqueue(pid,'analyze'))
        return svc.store.get(pid)

    def change(self,svc,doc,operations,cid=None):
        svc.changes({'project_id':doc['project_id'],'clip_id':cid,'expected_revision':doc['revision'],
                     'operation_id':'repair1-test-'+str(doc['revision']),'operations':operations})
        return svc.store.get(doc['project_id'])

    def test_reanalysis_versions_display_keeps_raw_and_reuses_identical_results(self):
        svc,doc,state,fake,prepare=self.analyzer();pid=doc['project_id']
        with patch.dict(sys.modules,{'clipper.pipeline':fake}),patch('clipper.pipeline',fake,create=True),patch.object(media_context,'prepare',side_effect=prepare),patch('clipper.editorial.release'):
            first=self.run_analyze(svc,pid);old=svc.store.transcript(first['transcript_id'])
            self.change(svc,first,[{'op':'analysis_settings','values':{'glossary':'Trading=treding'}}])
            second=self.run_analyze(svc,pid);new=svc.store.transcript(second['transcript_id'])
            self.assertNotEqual(first['transcript_id'],second['transcript_id']);self.assertEqual(new['words'][0]['word'],'Trading')
            self.assertEqual(old['raw_words'],new['raw_words']);self.assertEqual(old['raw_take_id'],new['raw_take_id'])
            evidence=svc.store.transcript(new['raw_take_id']);self.assertEqual(evidence['words'],evidence['raw_words'])
            third=self.run_analyze(svc,pid);self.assertEqual(second['transcript_id'],third['transcript_id'])
            self.assertEqual(second['transcript_revision'],third['transcript_revision'])
            self.assertEqual(svc.store.transcript(first['transcript_id']),old)

    def test_manual_clip_and_shared_corrections_survive_only_verified_lineage(self):
        svc,doc,state,fake,prepare=self.analyzer();pid=doc['project_id']
        with patch.dict(sys.modules,{'clipper.pipeline':fake}),patch('clipper.pipeline',fake,create=True),patch.object(media_context,'prepare',side_effect=prepare),patch('clipper.editorial.release'):
            doc=self.run_analyze(svc,pid);cid=next(iter(doc['clips']))
            def correction(doc,index,text,scope):
                return {'op':'correct_word','word_id':index,'after':text,'scope':scope,'transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision']}
            doc=self.change(svc,doc,[correction(doc,1,'Tetap','shared_utterance')])
            doc=self.change(svc,doc,[correction(doc,0,'TRADING','clip')],cid)
            doc=self.change(svc,doc,[{'op':'analysis_settings','values':{'glossary':'Trading=treding'}}])
            new=self.run_analyze(svc,pid)
            self.assertEqual([w['word'] for w in svc.transcript(new)['words']],['Trading','Tetap'])
            self.assertEqual([w['word'] for w in svc.transcript(new,cid)['words']],['TRADING','Tetap'])
            self.assertTrue(new['transcript_lineage']['manual_patches_preserved'])
            state['raw'][0]['word']='belajar';changed=self.run_analyze(svc,pid)
            self.assertFalse(changed['transcript_lineage']['manual_patches_preserved'])
            self.assertEqual([w['word'] for w in svc.transcript(changed)['words']],['belajar','tetap'])

    def test_failed_alignment_publishes_report_without_claiming_success(self):
        svc,doc,state,fake,prepare=self.analyzer();pid=doc['project_id']
        with patch.dict(sys.modules,{'clipper.pipeline':fake}),patch('clipper.pipeline',fake,create=True),patch.object(media_context,'prepare',side_effect=prepare),patch('clipper.editorial.release'):
            doc=self.run_analyze(svc,pid);revision=doc['transcript_revision']
            report={'aligned':0,'attempted':1,'status':'failed','device':'cpu','errors':[{'message':'Rejected timing'}]}
            with patch.object(speech_jobs,'alignment_runtime',return_value={'python':sys.executable,'model_path':'fixture'}),patch.object(speech_jobs,'run',return_value={'patches':[],'report':report}):
                job=svc.enqueue(pid,'alignment');studio_worker.execute(svc,job)
            final=svc.store.get(pid);job=svc.queue.get(job['id'])
            self.assertEqual(final['speech_reports']['alignment'],report)
            self.assertEqual(final['transcript_revision'],revision)
            self.assertIn('perlu diperiksa',job['message']);self.assertIn('0 frasa berhasil',job['message'])


if __name__=='__main__':unittest.main()
