"""Real SQLite/FFmpeg checks for workspace policy and video comparisons."""
import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from dataclasses import asdict
from pathlib import Path
from clipper.config import Config
from clipper.studio_service import StudioService
from clipper.project_store import Conflict
from clipper.dependency_cache import content_id
from clipper.workflow6 import BRAND_FIELDS,brand_values,export_options,native_reasons
from clipper.evaluation6 import compare,artifact_pair,validate_record,quality_summary
from clipper.metrics6 import ResourceMeter
from clipper import studio_storage


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media=tempfile.TemporaryDirectory();cls.source=Path(cls.media.name)/'source.mp4'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','testsrc2=s=256x144:r=30:d=2',
            '-f','lavfi','-i','sine=frequency=300:duration=2','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(cls.source)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.media.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.svc=StudioService(self.root,Config(use_nvenc=False),autostart=False)
        self.doc=self.svc.create(self.source);self.pid=self.doc['project_id']
        self.svc.store.save_transcript(self.pid,{'words':[{'word_id':1,'word':'jangan','start':0.,'end':.5},{'word_id':2,'word':'berhenti','start':.5,'end':1.}]},'fixture')
        def initial(d):
            d['transcript_id']='fixture';self.svc.add_candidates(d,[{'title':'Uji','start':0.,'end':2.,'keywords':[]}])
        self.svc.store.mutate(self.pid,0,'initial-fixture',{},initial);self.cid=next(iter(self.svc.store.get(self.pid)['clips']))
    def tearDown(self):self.tmp.cleanup()
    def current(self):return self.svc.store.get(self.pid)
    def change(self,ops,variant='portrait'):
        return self.svc.changes({'project_id':self.pid,'clip_id':self.cid,'variant_id':variant,'expected_revision':self.current()['revision'],
            'operation_id':uuid.uuid4().hex,'operations':ops})
    def kit(self,values=None):return self.svc.workspace.save_kit({'name':'Kit uji','settings':values or {'accent_hex':'#12ABCD','font_main':'montserrat','motion_intensity':'calm','layout':'fit'}})
    def pair(self):
        ctx={'source_id':content_id(self.source),'variant_id':'landscape','duration':2.,'word_fingerprint':'same-words'}
        ids=[]
        for seed in (1,2):
            p=self.root/f'preview-{seed}.mp4';shutil.copyfile(self.source,p)
            ids.append(self.svc.store.artifact(self.pid,self.cid,'landscape','preview','k'+str(seed),{'absolute_file':str(p),
                'output_content_id':content_id(p),'evaluation_context':ctx,'evaluation_settings':{'style_preset':'ekspresif','accent_hex':'#12ABCD'}}))
        return {'baseline_id':ids[0],'candidate_id':ids[1],'category':'talking_head'},ids
    def evaluate(self):
        from clipper.studio_worker import execute
        opts,ids=self.pair();job=self.svc.enqueue(self.pid,'evaluation',self.cid,'landscape',self.current()['revision'],opts)
        return execute(self.svc,job)
    def test_brand_rejects_secrets_source_and_bad_fonts(self):
        for values in ({'pexels_key':'secret'},{'audio_stream_index':1},{'font_main':'unknown'},{'caption_scale':99},{'base_hex':'red'}):
            with self.subTest(values=values),self.assertRaises(ValueError):brand_values(values)
    def test_complete_active_brand_is_valid(self):
        values={k:v for k,v in asdict(Config()).items() if k in BRAND_FIELDS};self.assertEqual(brand_values(values),values)
    def test_brand_kit_persists_across_projects_and_restart(self):
        kit=self.kit();another=StudioService(self.root,Config(),autostart=False,recover=False)
        self.assertEqual(another.workspace.kit(kit['id'])['settings'],kit['settings'])
    def test_stale_brand_kit_update_is_rejected(self):
        kit=self.kit();self.svc.workspace.save_kit({**kit,'expected_revision':0,'name':'New'})
        with self.assertRaises(Conflict):self.svc.workspace.save_kit({**kit,'expected_revision':0})
    def test_project_brand_preserves_manual_color_crop_words_and_other_ratio(self):
        self.change([{'op':'settings','values':{'accent_hex':'#FF0000'}}])
        before=self.current();kit=self.kit()
        self.change([{'op':'brand_apply','kit_id':kit['id'],'kit_revision':0,'scope':'project'}]);after=self.current()
        self.assertEqual(self.svc.config(after,self.cid,'portrait').accent_hex,'#FF0000')
        self.assertEqual(self.svc.config(after,self.cid,'landscape').accent_hex,'#12ABCD')
        self.assertEqual(after['transcript_revision'],before['transcript_revision']);self.assertEqual(after['clip_corrections'],before['clip_corrections'])
        self.assertEqual(after['clips'][self.cid]['start'],before['clips'][self.cid]['start'])
    def test_variant_kit_does_not_change_other_ratio(self):
        kit=self.kit();self.change([{'op':'brand_apply','kit_id':kit['id'],'kit_revision':0}])
        self.assertEqual(self.svc.config(self.current(),self.cid,'landscape').accent_hex,Config().accent_hex)
    def test_brand_cannot_use_stale_kit_revision(self):
        kit=self.kit();before=self.current()
        with self.assertRaises(ValueError):self.change([{'op':'brand_apply','kit_id':kit['id'],'kit_revision':9}])
        self.assertEqual(before,self.current())
    def test_seed_change_and_undo_preserve_later_color_and_timeline(self):
        self.change([{'op':'settings','values':{'style_preset':'ekspresif'}},{'op':'timeline','keep_spans':[[0.,1.5]]}])
        old=self.current();alternative=self.change([{'op':'design_alternative'}])
        self.change([{'op':'settings','values':{'accent_hex':'#FF0000'}}])
        self.svc.store.undo(self.pid,self.current()['revision'],uuid.uuid4().hex,alternative['revision'])
        cfg=self.svc.config(self.current(),self.cid,'portrait');self.assertEqual(cfg.caption_seed,2026);self.assertEqual(cfg.accent_hex,'#FF0000')
        self.assertEqual(self.current()['clips'][self.cid]['variants']['portrait']['timeline'],old['clips'][self.cid]['variants']['portrait']['timeline'])
    def test_seed_requires_curated_preset(self):
        with self.assertRaises(ValueError):self.change([{'op':'design_alternative'}])
    def test_color_does_not_invalidate_source_jobs_or_asr_cache(self):
        from clipper.storage import source_key
        old=self.current();hashes={k:self.svc.dependency(old,kind=k) for k in ('analyze','discovery','correction','waveform','source_evidence')}
        asr=source_key(self.source,self.svc.config(old));render=self.svc.dependency(old,self.cid,'portrait')
        result=self.change([{'op':'settings','scope':'project','values':{'accent_hex':'#12ABCD'}}]);new=self.current()
        self.assertEqual(hashes,{k:self.svc.dependency(new,kind=k) for k in hashes})
        self.assertEqual(asr,source_key(self.source,self.svc.config(new)));self.assertNotEqual(render,self.svc.dependency(new,self.cid,'portrait'))
        self.assertEqual(result['impact'],['preview','render','export'])
    def test_language_invalidates_analysis(self):
        old=self.svc.dependency(self.current(),kind='analyze');self.change([{'op':'settings','scope':'project','values':{'language':'en'}}])
        self.assertNotEqual(old,self.svc.dependency(self.current(),kind='analyze'))
    def test_queue_cancel_resume_uses_new_dependency(self):
        job=self.svc.enqueue(self.pid,'preview',self.cid,'portrait',self.current()['revision']);self.svc.queue.cancel(job['id'])
        self.change([{'op':'settings','values':{'accent_hex':'#12ABCD'}}])
        new=self.svc.enqueue(self.pid,job['kind'],self.cid,'portrait',options=job['request']['options'])
        self.assertNotEqual(job['request']['dependency'],new['request']['dependency']);self.assertEqual(new['status'],'queued')
    def test_cache_protects_variant_music_final_and_evaluation_files(self):
        cache=self.svc.work/self.pid/'cache/previews';cache.mkdir(parents=True)
        paths={name:cache/(name+('.mp4' if name=='music' else '.bin')) for name in ('music','final','disposable')}
        for name,path in paths.items():path.write_bytes(name.encode())
        self.change([{'op':'settings','values':{'music_path':str(paths['music'])}}])
        self.svc.store.mutate(self.pid,self.current()['revision'],'seed-final-path',{},lambda d:d['clips'][self.cid]['variants']['portrait'].update(result={'absolute_file':str(paths['final'])}))
        self.svc.workspace.append('evaluations6',self.pid,{'baseline':{'path':str(paths['music'])},'candidate':{'path':str(paths['final'])}})
        listing=studio_storage.inventory(self.svc);byname={Path(e['path']).stem:e for e in listing['entries']}
        self.assertFalse(byname['music']['deletable']);self.assertFalse(byname['final']['deletable']);self.assertTrue(byname['disposable']['deletable'])
        studio_storage.cleanup(self.svc,[byname['disposable']['id']],listing['etag']);self.assertFalse(paths['disposable'].exists());self.assertTrue(paths['final'].exists())
    def test_cleanup_refuses_source_and_busy_jobs(self):
        listing=studio_storage.inventory(self.svc);source=next(e for e in listing['entries'] if e['category']=='source')
        with self.assertRaises(ValueError):studio_storage.cleanup(self.svc,[source['id']],listing['etag'])
        self.svc.enqueue(self.pid,'preview',self.cid,'portrait')
        with self.assertRaises(ValueError):studio_storage.cleanup(self.svc,[],listing['etag'])
    def test_native_layout_and_zoom_are_honest_gates(self):
        plan={'height':144,'shots':[{'mode':'fill','zoom_at':None}]};self.assertEqual(native_reasons(plan),[])
        for shot in ({'mode':'stream','zoom_at':None},{'mode':'fill','zoom_at':.5},{'mode':'fit','image_height':100,'zoom_at':None}):
            self.assertTrue(native_reasons({'height':144,'shots':[shot]}))
    def test_export_options_distinguish_preserved_and_hybrid(self):
        rows=export_options({});self.assertEqual([r['id'] for r in rows],['preserved','hybrid','native'])
        self.assertEqual(rows[0]['editable_layers'],[]);self.assertFalse(rows[2]['available'])
    def test_changed_final_plan_blocks_export_without_changing_mp4(self):
        path=self.root/'final-plan.json';path.write_text('{}')
        result={'absolute_file':str(self.source),'dependency':self.svc.dependency(self.current(),self.cid,'landscape'),
            'output_content_id':content_id(self.source),'plan_path':str(path),'plan_content_id':content_id(path)}
        self.svc.store.mutate(self.pid,self.current()['revision'],'seed-plan-integrity',{},lambda d:d['clips'][self.cid]['variants']['landscape'].update(result=result))
        self.assertEqual(self.svc.export_readiness(self.current(),self.cid,'landscape',fresh=True)['status'],'ready')
        path.write_text('{"changed":true}')
        self.assertEqual(self.svc.export_readiness(self.current(),self.cid,'landscape',fresh=True)['status'],'changed')
    def test_real_video_comparison_and_cpu_job(self):
        result=self.evaluate();self.assertEqual(result['ssim'],1.);self.assertTrue(result['psnr_infinite']);self.assertEqual(result['quality_status'],'human_review_required')
        self.assertEqual(len(self.svc.workspace.rows('evaluations6',self.pid)),1)
    def test_artifact_pair_rejects_other_source(self):
        opts,ids=self.pair()
        with self.svc.store.connect() as db:
            row=json.loads(db.execute('SELECT data FROM artifacts WHERE id=?',(ids[1],)).fetchone()[0]);row['evaluation_context']['source_id']='other';db.execute('UPDATE artifacts SET data=? WHERE id=?',(json.dumps(row),ids[1]))
        with self.assertRaises(ValueError):artifact_pair(self.svc,self.pid,opts)
    def test_artifact_pair_rejects_same_result_twice(self):
        opts,ids=self.pair();opts['candidate_id']=opts['baseline_id']
        with self.assertRaises(ValueError):artifact_pair(self.svc,self.pid,opts)
    def test_record_detects_modified_media(self):
        record=self.evaluate();Path(record['candidate']['path']).write_bytes(b'changed')
        with self.assertRaises(ValueError):validate_record(record)
    def test_feedback_does_not_change_default(self):
        record=self.evaluate();self.svc.workspace.feedback(self.pid,{'evaluation_id':record['id'],'choice':'candidate','note':'Review fixture only'})
        self.assertEqual(self.svc.workspace.preference()['source'],'built_in')
    def test_default_requires_human_win_and_explicit_promotion(self):
        record=self.evaluate();tie=self.svc.workspace.feedback(self.pid,{'evaluation_id':record['id'],'choice':'tie','note':'Same pixels'})
        with self.assertRaises(ValueError):self.svc.workspace.promote(self.pid,{'feedback_id':tie['id'],'expected_revision':0})
        win=self.svc.workspace.feedback(self.pid,{'evaluation_id':record['id'],'choice':'candidate','note':'Simulated human choice for policy test'})
        self.svc.workspace.promote(self.pid,{'feedback_id':win['id'],'expected_revision':0})
        before=self.current();new=self.svc.create(self.source)
        self.assertEqual(new['settings']['accent_hex'],'#12ABCD');self.assertEqual(self.current(),before)
    def test_unknown_measurements_remain_null(self):
        record=self.evaluate();f=self.svc.workspace.feedback(self.pid,{'evaluation_id':record['id'],'choice':'tie','note':'No manual counts yet'})
        self.assertIsNone(f['metrics']['manual_corrections']);self.assertIsNone(f['metrics']['unique_stories'])
    def test_evaluation_dataset_has_all_five_categories(self):
        q=quality_summary(self.svc,self.pid);self.assertEqual(len(q['categories']),5);self.assertTrue(all(c['comparisons']==0 for c in q['categories']))
    def test_native_matrix_starts_unverified_for_both_ratios(self):
        rows=self.svc.workspace.native_matrix(self.pid);self.assertEqual(len(rows),4);self.assertTrue(all(r['status']=='not_tested' for r in rows))
    def package(self):
        path=self.root/'package.zip';path.write_bytes(b'fixture package identity')
        p={'zip':str(path),'package_content_id':content_id(path),'clip_id':self.cid,'variant_id':'landscape','export_mode':'hybrid',
            'reference':{'width':256,'height':144,'length':2.},'editors':{'capcut':{'construction_status':'generated','structural_status':'passed'}}}
        self.svc.store.mutate(self.pid,self.current()['revision'],'seed-package',{},lambda d:d['exports'].append(p));return p
    def test_native_evidence_is_user_reported_and_bound_to_media(self):
        p=self.package();data={'package_content_id':p['package_content_id'],'editor':'capcut','version':'9.5.0','render_path':str(self.source),
            'note':'Fixture testing the evidence policy, not an actual editor import.',**{k:True for k in ('opened','text_edited','saved','rendered','compared')}}
        row=self.svc.workspace.native_evidence(self.pid,data);self.assertEqual(row['status'],'user_reported_passed')
        Path(p['zip']).write_bytes(b'new');matrix=self.svc.workspace.native_matrix(self.pid)
        self.assertEqual(next(r for r in matrix if r['package_content_id'])['status'],'stale')
    def test_native_evidence_rejects_wrong_version_or_unbuilt_editor(self):
        p=self.package()
        for editor,version in [('capcut','9.4.0'),('resolve','21')]:
            with self.assertRaises(ValueError):self.svc.workspace.native_evidence(self.pid,{'package_content_id':p['package_content_id'],'editor':editor,'version':version})
    def test_manifest_lists_protected_source_and_stage_dependencies(self):
        manifest=self.svc.workspace.manifest(self.pid);self.assertEqual(manifest['revision'],self.current()['revision'])
        self.assertFalse(next(f for f in manifest['files'] if f['category']=='source')['deletable']);self.assertIn('analyze',manifest['stages'])
    def test_resource_meter_reports_real_ram_or_missing_not_invented_zero(self):
        meter=ResourceMeter(os.getpid());meter.sample();report=meter.report()
        self.assertTrue(report['peak_ram_bytes'] is None or report['peak_ram_bytes']>0);self.assertEqual(report['samples'],1)


if __name__=='__main__':unittest.main(verbosity=2)
