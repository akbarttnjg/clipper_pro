"""Real SQLite selection/queue/export and real FFmpeg diagram regression tests."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from clipper.config import Config
from clipper.studio_service import StudioService
from clipper.project_store import Conflict
from clipper.dependency_cache import content_id,fresh_scope
from clipper.storage import read_json,write_json
from clipper import batch7,explanation5


def words(text,start=5.,step=.4):
    return [{'word':t,'word_id':i,'start':start+i*step,'end':start+(i+1)*step} for i,t in enumerate(text.split())]


class Diagrams(unittest.TestCase):
    def test_ordinary_phrase_no_longer_becomes_a_duplicate_caption_card(self):
        rows=words('Belajar membuat keputusan secara konsisten perlu waktu.');saved=copy.deepcopy(rows)
        with tempfile.TemporaryDirectory() as tmp:
            result=explanation5.prepare(rows,{'start':0,'end':40},Config(illustration_mode='labels',work_dir=tmp))
            self.assertEqual(result['scenes'],[]);self.assertEqual(rows,saved);self.assertFalse((Path(tmp)/'explanations').exists())

    def test_contrast_preserves_negation_and_source_words(self):
        result=list(explanation5.structures(words('Ini bukan jalan pintas tetapi latihan yang konsisten.')))
        self.assertEqual(result[0]['labels'],['bukan jalan pintas','tetapi latihan yang konsisten.'])

    def test_complete_and_incomplete_numbered_lists(self):
        complete=words('Ada tiga langkah. Pertama menjaga modal. Kedua mengatur risiko. Ketiga mencatat hasil.')
        self.assertEqual(len(list(explanation5.structures(complete))),1)
        incomplete=words('Ada tiga langkah. Pertama menjaga modal. Kedua mengatur risiko.')
        self.assertEqual(list(explanation5.structures(incomplete)),[])

    def test_long_ambiguous_clause_skipped(self):
        self.assertEqual(list(explanation5.structures(words('Bukan sesuatu yang dapat kita lakukan tanpa memikirkan konsekuensi dalam jangka waktu panjang tetapi latihan.'))),[])

    def test_emotional_speaker_and_material_preserved(self):
        row=words('Bukan jalan pintas tetapi latihan konsisten.')
        for kind,intel in [('board',{}),('screen',{}),('auto',{'broll':'preserve_speaker'})]:
            result=explanation5.prepare(row,{'start':0,'end':40,'intelligence':intel},Config(source_kind=kind,illustration_mode='labels'))
            self.assertEqual(result['scenes'],[])

    def test_real_diagram_movie_svg_and_source_lineage(self):
        from clipper.ffmpeg_util import probe
        rows=words('Bukan jalan pintas tetapi latihan konsisten.')
        with tempfile.TemporaryDirectory() as tmp:
            result=explanation5.prepare(rows,{'start':0,'end':40},Config(illustration_mode='labels',work_dir=tmp,visual_runtime_root=tmp))
            self.assertEqual(len(result['scenes']),1)
            scene=result['scenes'][0];self.assertGreaterEqual(scene['source_start'],rows[-1]['end'])
            self.assertEqual(scene['asset']['origin']['source_word_ids'],list(range(len(rows))))
            info=probe(scene['asset']['path']);self.assertEqual((info['width'],info['height']),(1280,720));self.assertAlmostEqual(info['duration'],3.,places=2)
            svg=Path(scene['asset']['editable_path']).read_text();self.assertIn('Bukan jalan pintas',svg);self.assertNotIn('DARI UCAPAN SUMBER',svg)


class Batch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media=tempfile.TemporaryDirectory();cls.source=Path(cls.media.name)/'source.mp4';cls.finals={}
        for path,size,duration in [(cls.source,'320x180',6),(Path(cls.media.name)/'portrait.mp4','180x320',3),(Path(cls.media.name)/'landscape.mp4','320x180',3)]:
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i',f'color=s={size}:r=30:d={duration}',
                '-f','lavfi','-i',f'sine=frequency=260:duration={duration}','-c:v','libx264','-threads','1','-c:a','aac','-shortest',str(path)],capture_output=True,check=True)
        cls.finals={vid:Path(cls.media.name)/(vid+'.mp4') for vid in batch7.RATIOS}
    @classmethod
    def tearDownClass(cls):cls.media.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.svc=StudioService(self.temp.name,Config(use_nvenc=False),autostart=False)
        self.doc=self.svc.create(self.source);self.pid=self.doc['project_id']
        self.svc.store.save_transcript(self.pid,{'words':words('Pembahasan pertama dan pembahasan kedua.',start=0)},'batch-take')
        def initialize(d):
            d['transcript_id']='batch-take'
            self.svc.add_candidates(d,[{'title':'Cerita pertama','start':0,'end':3,'keywords':[]},{'title':'Cerita kedua','start':3,'end':6,'keywords':[]}])
        self.svc.store.mutate(self.pid,0,'initialize-batch',{},initialize)
        self.doc=self.svc.store.get(self.pid);self.cids=list(self.doc['clips'])
    def tearDown(self):self.temp.cleanup()
    def include(self,cid,value):
        doc=self.svc.store.get(self.pid)
        return self.svc.changes({'project_id':self.pid,'expected_revision':doc['revision'],'operation_id':f'include-{cid}-{value}',
            'operations':[{'op':'include_clip','clip_id':cid,'included':value}]})
    def seed_results(self):
        doc=self.svc.store.get(self.pid)
        def seed(d):
            for cid in self.cids:
                for vid,(w,h) in {'portrait':(180,320),'landscape':(320,180)}.items():
                    path=self.svc.work/f'{cid}-{vid}.json'
                    write_json(path,{'revision':0,'source':{'path':str(self.source)},'width':w,'height':h,'fps':30,'duration':3,
                        'captions':{'phrases':[]},'audio':{},'shots':[]})
                    d['clips'][cid]['variants'][vid]['result']={'absolute_file':str(self.finals[vid]),'file':self.finals[vid].name,
                        'title':d['clips'][cid]['title'],'revision':0,'width':w,'height':h,'length':3,'plan_path':str(path),
                        'dependency':self.svc.dependency(d,cid,vid),'output_content_id':content_id(self.finals[vid],fresh=True),
                        'plan_content_id':content_id(path,fresh=True)}
        self.svc.store.mutate(self.pid,doc['revision'],'seed-batch-results',{},seed)
        self.doc=self.svc.store.get(self.pid)
    def test_batch_queues_every_selected_clip_and_ratio_once(self):
        first=self.svc.enqueue_batch(self.pid,self.doc['revision']);second=self.svc.enqueue_batch(self.pid,self.doc['revision'])
        self.assertEqual(len(first['jobs']),4);self.assertEqual([j['id'] for j in first['jobs']],[j['id'] for j in second['jobs']])
        self.assertEqual({(j['target']['clip_id'],j['target']['variant_id']) for j in first['jobs']},{(c,v) for c in self.cids for v in batch7.RATIOS})
    def test_selection_does_not_invalidate_render_inputs(self):
        before=self.svc.dependency(self.doc,self.cids[0],'portrait');self.include(self.cids[0],False)
        current=self.svc.store.get(self.pid);self.assertEqual(before,self.svc.dependency(current,self.cids[0],'portrait'))
        self.assertEqual(len(self.svc.enqueue_batch(self.pid,current['revision'])['jobs']),2)
    def test_batch_preset_applies_both_ratios_only_to_included_clips(self):
        self.include(self.cids[1],False);doc=self.svc.store.get(self.pid)
        self.svc.changes({'project_id':self.pid,'expected_revision':doc['revision'],'operation_id':'batch-preset-test',
            'operations':[{'op':'preset_batch','preset':'adaptif'}]})
        current=self.svc.store.get(self.pid)
        for vid in batch7.RATIOS:
            selected=self.svc.config(current,self.cids[0],vid);other=self.svc.config(current,self.cids[1],vid)
            self.assertEqual((selected.style_preset,selected.font_main),('adaptif','dm_sans'));self.assertEqual(other.style_preset,'legacy')
    def test_invalid_and_stale_batches_enqueue_nothing(self):
        self.include(self.cids[0],False)
        with self.assertRaises(Conflict):self.svc.enqueue_batch(self.pid,self.doc['revision'])
        self.include(self.cids[1],False)
        with self.assertRaises(ValueError):self.svc.enqueue_batch(self.pid,self.svc.store.get(self.pid)['revision'])
        self.assertEqual(self.svc.queue.list(self.pid),[])
    def test_ready_render_reused_and_tampered_final_rejected(self):
        self.seed_results();self.assertEqual(len(self.svc.enqueue_batch(self.pid,self.doc['revision'])['skipped']),4)
        target=Path(self.temp.name)/'changed.mp4';target.write_bytes(b'not the final render')
        def tamper(d):d['clips'][self.cids[0]]['variants']['portrait']['result']['absolute_file']=str(target)
        self.svc.store.mutate(self.pid,self.doc['revision'],'tamper-final',{},tamper)
        current=self.svc.store.get(self.pid)
        with self.assertRaisesRegex(ValueError,'9:16'):self.svc.enqueue(self.pid,'export_project',expected_revision=current['revision'],options={'mode':'preserved'})
    def test_missing_ratio_blocks_project_package(self):
        with self.assertRaisesRegex(ValueError,'Paket seluruh klip belum lengkap'):self.svc.enqueue(self.pid,'export_project',expected_revision=self.doc['revision'])
        self.assertEqual(self.svc.queue.list(self.pid),[])
    def test_real_four_timeline_package_and_coverage(self):
        self.seed_results();job=self.svc.enqueue(self.pid,'export_project',expected_revision=self.doc['revision'],options={'mode':'preserved'})
        result=batch7.export_project(self.svc,job);manifest=read_json(Path(result['folder'])/'manifest.json')
        self.assertEqual(result['timelines'],4);self.assertEqual(len(manifest['coverage']),4)
        self.assertEqual({(r['clip_id'],r['variant_id']) for r in manifest['coverage']},{(c,v) for c in self.cids for v in batch7.RATIOS})
        for i,row in enumerate(manifest['coverage'],1):self.assertEqual(content_id(Path(result['folder'])/f'Media/{i:02}-final.mp4',fresh=True),row['output_content_id'])
        self.assertEqual(self.svc.queue.get(job['id'])['status'],'completed')
    def test_selection_change_while_export_queued_cannot_publish(self):
        self.seed_results();job=self.svc.enqueue(self.pid,'export_project',expected_revision=self.doc['revision'],options={'mode':'preserved'})
        self.include(self.cids[0],False)
        with self.assertRaisesRegex(ValueError,'Pilihan klip'):batch7.export_project(self.svc,job)
        self.assertEqual(self.svc.store.get(self.pid)['exports'],[])


class FreshHashes(unittest.TestCase):
    def test_scoped_fresh_reads_and_mutations_are_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source';path.write_bytes(b'first')
            with fresh_scope():
                a=content_id(path,fresh=True);self.assertEqual(a,content_id(path,fresh=True))
                path.write_bytes(b'other');self.assertNotEqual(a,content_id(path,fresh=True))
            path.write_bytes(b'third');self.assertNotEqual(a,content_id(path,fresh=True))


if __name__=='__main__':unittest.main()
