"""Regression contracts for the thirteen confirmed M0–M2 audit findings.

Real FFmpeg, SQLite and synthetic signals. No speech-model quality claims.
"""
import copy
import json
import sqlite3
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from clipper import editor_contract as ec, editor_media, media_context, transcript_tracks as tracks
from clipper.config import Config
from clipper.dependency_cache import content_id
from clipper.editplan import validate_source_words
from clipper.project_store import JobLeaseLost
from clipper.tests.test_m2_transcripts import M2Fixture, SRT, require_ffmpeg
from clipper.tests.test_editor_m1 import studio, edit, document, first


def ffmpeg(args):
    require_ffmpeg()
    subprocess.run(['ffmpeg','-v','error','-nostdin','-y',*map(str,args)],check=True,capture_output=True)


@pytest.mark.parametrize('origin',[0,5,105])
def test_matroska_origin_is_not_content_duration(tmp_path,origin):
    source=tmp_path/'clock.mkv'
    ffmpeg(['-f','lavfi','-i','testsrc2=s=160x90:r=30:d=2','-f','lavfi','-i','sine=frequency=650:duration=2',
            '-c:v','libx264','-threads','2','-c:a','pcm_s16le','-output_ts_offset',origin,source])
    info=media_context.inspect(source)
    assert info['duration']==pytest.approx(2,abs=.04)
    assert info['video_start_time']==pytest.approx(origin,abs=.001)
    cfg=Config(work_dir=str(tmp_path/'work'),out_dir=str(tmp_path/'out'),use_nvenc=False)
    context=media_context.prepare(source,cfg)
    assert context['payload']['duration']==pytest.approx(2,abs=.04)


@pytest.mark.parametrize('field,value',[('text','Selalu 50 persen'),('start',.6),('end',1.6),('speaker_id','Budi'),('origin_word_ids',[999])])
def test_json_cue_cannot_disagree_with_canonical_words(field,value):
    original=tracks.parse(SRT,'srt','source',8,source_language='id')
    incoming=json.loads(tracks.export_track(original,'json'))
    incoming['cues'][0][field]=value
    with pytest.raises(ValueError):tracks.parse(json.dumps(incoming),'json','source',8,source_language='id')


def test_effective_cues_split_speakers_without_mutating_original():
    take={'words':[{'word_id':1,'word':'Tidak','start':0,'end':.5,'speaker_id':'A'},
                   {'word_id':2,'word':'5 persen','start':.5,'end':1.,'speaker_id':'A'}],
          'cues':[{'cue_id':'original','text':'Tidak 5 persen','start':0,'end':1.,'speaker_id':'A','origin_word_ids':[1,2]}]}
    frozen=copy.deepcopy(take)
    projected=copy.deepcopy(take);projected['words'][1]['speaker_id']='B'
    cues=tracks.effective_cues(projected)
    assert [r['speaker_id'] for r in cues]==['A','B']
    assert all(r['parent_cue_id']=='original' for r in cues)
    assert take==frozen
    assert tracks.effective_cues(take)[0]['cue_id']=='original'


@pytest.mark.parametrize('word',[{'word':'lost','start':2.1,'end':2.5},
                                 {'word':'lost','start':.1,'end':.5,'aligned_words':[{'word':'lost','start':3,'end':4}]}])
def test_out_of_source_timing_is_rejected_before_word_clipping(word):
    with pytest.raises(ValueError):validate_source_words([word],2)


@pytest.mark.parametrize('op,track',[({'op':'inherit_field','keys':['accent_hex']},'captions'),
    ({'op':'settings','values':{'layout':'fit'}},'video'),({'op':'settings','values':{'sfx_db':-24.}},'sfx'),
    ({'op':'settings','values':{'audio_normalize':False}},'voice'),
    ({'op':'settings','values':{'music_db':-28.,'sfx_db':-24.}},'sfx'),
    ({'op':'reset_overrides','keys':['layout']},'video'),
    ({'op':'profile','profile_id':'education'},'video')])
def test_track_lock_owns_each_changed_field(studio,op,track):
    edit(studio,[{'op':'track','track':track,'values':{'locked':True}}])
    before=document(studio)
    with pytest.raises(ValueError,match='terkunci'):edit(studio,[op])
    assert document(studio)==before


def test_project_settings_check_other_ratio_lock_and_allow_unrelated_fields(studio):
    edit(studio,[{'op':'track','track':'sfx','values':{'locked':True}}],vid='landscape')
    with pytest.raises(ValueError,match='terkunci'):edit(studio,[{'op':'settings','scope':'project','values':{'sfx_db':-28.}}])
    edit(studio,[{'op':'settings','scope':'project','values':{'music_db':-28.}}])


@pytest.mark.parametrize('source',[1.,1.000001,1.5,2.,2.999999])
def test_reverse_mapping_stays_in_its_half_open_slice(source):
    rows=ec.validate_segments([{'id':'reverse','start':1,'end':3,'reverse':True},{'id':'next','start':0,'end':1}],{'start':0,'end':4})
    clock=ec.build_clock(rows,30)
    mapped=ec.source_to_output(clock,source)[0]
    back=ec.output_to_source(clock,mapped)
    assert 0<=mapped<2 and back['segment_id']=='reverse'
    assert back['source_time']==pytest.approx(source,abs=1.1e-6)
    assert ec.output_to_source(clock,0)['source_time']==2.999999


def test_offset_changes_cached_camera_pixels(studio,tmp_path):
    source=Path(document(studio)['source']['path']);camera=tmp_path/'camera.mp4';cid=first(studio)
    ffmpeg(['-f','lavfi','-i','color=c=green:s=160x96:r=30:d=4','-f','lavfi','-i','sine=frequency=600:duration=4',
            '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',source])
    ffmpeg(['-f','lavfi','-i','color=c=red:s=160x96:r=30:d=2','-f','lavfi','-i','color=c=blue:s=160x96:r=30:d=2',
            '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-c:v','libx264','-pix_fmt','yuv420p',camera])
    def register(offset):edit(studio,[{'op':'camera_register','path':str(camera),'offset_seconds':offset,'confirm_manual_offset':True}])
    register(0)
    cam=next(iter(document(studio)['editor_cameras']))
    edit(studio,[{'op':'editor_segments','segments':[{'id':'shot','start':0,'end':1,'camera_id':cam}]}])
    def prepare():
        doc=document(studio);return editor_media.prepare(studio,doc,cid,'portrait',str(source),studio.transcript(doc,cid)['words'],dict(doc['clips'][cid]),studio.config(doc,cid,'portrait'))
    def rgb(p):return subprocess.run(['ffmpeg','-v','error','-i',str(p),'-frames:v','1','-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','pipe:1'],check=True,capture_output=True).stdout[:3]
    one=prepare();register(2);two=prepare()
    assert one[0]!=two[0] and not two[4]['reused']
    assert rgb(one[0])[0]>240 and rgb(two[0])[2]>240
    assert prepare()[4]['reused']


class RepairsServiceCase(M2Fixture):
    __test__=True

    def test_json_import_rejection_leaves_track_and_revision_untouched(self):
        take=tracks.parse(SRT,'srt',self.doc['source']['source_id'],8,source_language='id')
        incoming=json.loads(tracks.export_track(take,'json'));incoming['cues'][0]['text']='Selalu 50 persen'
        before=copy.deepcopy(self.doc)
        with self.assertRaises(ValueError):self.import_proposal(text=json.dumps(incoming),format='json')
        self.assertEqual(self.service.store.get(self.doc['project_id']),before)

    def test_whole_source_export_uses_effective_speaker_and_preserves_take(self):
        self.commit_import(self.import_proposal());self.refresh();original=self.service.store.transcript(self.doc['transcript_id'])
        self.service.store.mutate(self.doc['project_id'],self.doc['revision'],'speaker-result-double',{},
            lambda d:d.update(diarization={'transcript_id':d['transcript_id'],'segments':[{'start':0.,'end':8.,'speaker_id':'SPEAKER_00'}],
                                          'runtime_receipt':{'provider':'labelled_result_double','inference_performed':False}}))
        self.refresh();result=self.service.transcripts.export(self.doc['project_id'],{'expected_revision':self.doc['revision'],'format':'json'})
        data=json.loads(self.service.file(result['url'].split('/')[-1]).read_text())
        self.assertEqual(data['cues'][0]['speaker_id'],'SPEAKER_00')
        self.assertEqual(data['cues'][0]['cue_id'],original['cues'][0]['cue_id'])
        self.assertEqual(self.service.store.transcript(self.doc['transcript_id']),original)

    def test_project_timing_cannot_overlap_a_narrower_override(self):
        self.timing(3,2.8,3.8,'variant');self.refresh();before=copy.deepcopy(self.doc)
        with self.assertRaises(ValueError):self.command({'op':'m2_timing','scope':'project','origin_word_ids':[2],'start':2.1,'end':2.9,
            'transcript_id':self.take,'transcript_revision':self.doc['transcript_revision']},vid='landscape')
        self.assertEqual(self.service.store.get(self.doc['project_id']),before)
        self.timing(2,2.1,2.7,'project')

    def test_assembly_rebases_nested_alignment_and_render_keeps_all_words(self):
        self.command({'op':'align_words','scope':'shared_utterance','origin_word_ids':[4],'text':'XAUUSD',
            'words':[{'word':'XAUUSD','start':4.2,'end':4.6}],'transcript_id':self.take,'transcript_revision':self.doc['transcript_revision']})
        self.refresh();batch=self.service.imports.submit({'items':[{'kind':'assembly','segments':[{'project_id':self.doc['project_id'],
            'revision':self.doc['revision'],'start':3.,'end':5.}]}],'operation_id':'repair-aligned-assembly'})
        result=self.service.imports.process(batch['items'][0]['id']);derived=self.service.store.get(result['project_id']);take=self.service.transcript(derived)
        from clipper.stage3 import expand_aligned
        word=next(w for w in expand_aligned(take['words']) if w['word']=='XAUUSD')
        self.assertAlmostEqual(word['start'],1.2);self.assertAlmostEqual(word['end'],1.6)
        self.service.add_candidates(derived,[{'start':0.,'end':2.,'title':'Derived'}]);cid=next(iter(derived['clips']))
        from clipper.studio_exchange import render_words
        rows=render_words(take,derived,derived['clips'][cid],self.service.config(derived,cid,'portrait'))
        from clipper import pipeline
        cfg=replace(self.service.config(derived,cid,'portrait'),target_w=360,target_h=640,use_nvenc=False,audio_normalize=False,
                    caption_style='clean',style_preset='legacy',align_selected_clips=False)
        final=pipeline.render_clip(result['path'],rows,derived['clips'][cid],'repair-alignment',cfg)
        plan=json.loads(Path(final['plan_path']).read_text())
        self.assertIn('XAUUSD',[w['word'] for w in plan['words']]);self.assertTrue(final['qc']['passed'])

    def submit(self,assembly=False):
        item={'kind':'assembly','segments':[{'project_id':self.doc['project_id'],'revision':self.doc['revision'],'start':3.,'end':5.}]} if assembly else {'kind':'local','path':str(self.source)}
        return self.service.imports.submit({'items':[item],'operation_id':'repair-atomic-'+str(assembly)})['items'][0]['id']

    def counts(self):
        with self.service.store.connect() as db:return tuple(db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('projects','transcripts','words'))

    def fault_resume(self,assembly):
        iid=self.submit(assembly);before=self.counts()
        with self.service.store.connect() as db:db.execute("CREATE TRIGGER repair_fault BEFORE UPDATE OF status ON m2_imports WHEN NEW.status='completed' BEGIN SELECT RAISE(ABORT,'repair controlled commit fault'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.service.imports.process(iid)
        self.assertEqual(self.counts(),before);self.assertEqual(self.service.imports.get(iid)['status'],'failed')
        with self.service.store.connect() as db:db.execute('DROP TRIGGER repair_fault')
        self.service.imports.resume(iid);result=self.service.imports.process(iid)
        self.assertEqual(self.counts()[0],before[0]+1);self.assertEqual(self.service.imports.get(iid)['result']['project_id'],result['project_id'])
        if assembly:self.assertEqual(self.counts()[1],before[1]+1)
        doc=self.service.store.get(result['project_id']);again=self.service.store.create_import(doc,iid,'expired-lease',result)
        self.assertEqual(again['project_id'],result['project_id']);self.assertEqual(self.counts()[0],before[0]+1)

    def test_local_commit_fault_rolls_back_before_resume(self):self.fault_resume(False)
    def test_assembly_commit_fault_rolls_back_project_take_and_words(self):self.fault_resume(True)

    def test_cancel_before_publication_has_no_late_project(self):
        iid=self.submit();before=self.counts();create=self.service.create
        def canceled(*args,**kw):
            self.assertEqual(self.service.imports.cancel(iid)['status'],'canceled')
            return create(*args,**kw)
        with patch.object(self.service,'create',side_effect=canceled):
            with self.assertRaises(JobLeaseLost):self.service.imports.process(iid)
        self.assertEqual(self.counts(),before);self.assertEqual(self.service.imports.get(iid)['status'],'canceled')
        self.service.imports.resume(iid);self.service.imports.process(iid)
        self.assertEqual(self.counts()[0],before[0]+1)

    def test_cancel_after_commit_reports_completed_and_keeps_one_project(self):
        iid=self.submit();before=self.counts();result=self.service.imports.process(iid)
        self.assertEqual(self.service.imports.cancel(iid)['status'],'completed')
        self.assertEqual(self.counts()[0],before[0]+1)
        self.assertEqual(self.service.imports.get(iid)['result']['project_id'],result['project_id'])


def test_frozen_aud06_fullhd_render_keeps_original_ids_and_qc(tmp_path):
    import zipfile,hashlib
    from clipper.studio_service import StudioService
    from clipper.studio_worker import execute
    from clipper.caption_checks import inspect_caption_plan
    root=Path(__file__).resolve().parents[2]
    meta=json.loads((root/'docs/releases/m0_m2_aud06_provenance.json').read_text())
    archive=root/'docs/releases/m0_m2_aud06_fixture.zip'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==meta['sha256']
    with zipfile.ZipFile(archive) as z:
        for name in ('case/work/studio4.sqlite3','source/two-audio.mp4'):
            p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name))
    dest=tmp_path/'case';source=tmp_path/'source/two-audio.mp4'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==meta['source_sha256']
    oldroot='/tmp/pytest-of-root/pytest-3/test_m1_advanced_speed_full_pi6'
    oldsource='/tmp/pytest-of-root/pytest-3/m0-media0/two-audio.mp4'
    def relocate(v):
        if isinstance(v,str):return v.replace(oldroot,str(dest)).replace(oldsource,str(source))
        if isinstance(v,dict):return {k:relocate(x) for k,x in v.items()}
        if isinstance(v,list):return [relocate(x) for x in v]
        return v
    with sqlite3.connect(dest/'work/studio4.sqlite3') as db:
        for pid,raw in db.execute('SELECT id,document FROM projects').fetchall():
            db.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(relocate(json.loads(raw))),pid))
    service=StudioService(dest,Config(work_dir='work',out_dir='clips'),autostart=False,recover=False)
    try:
        pid=meta['project_id'];cid=meta['clip_id'];before=service.store.get(pid)
        assert before['revision']==2 and service.config(before,cid,'landscape').caption_seed==2026
        job=service.enqueue(pid,'render',cid,'landscape');result=execute(service,job)
        assert result['qc']['passed'] and result['qc']['full_decode']=='passed'
        assert result['qc']['caption_layout']['geometry_passed']
        assert result['width']==1920 and result['height']==1080
        plan=json.loads(Path(result['plan_path']).read_text())
        caption=plan['captions'];cfg=service.config(before,cid,'landscape')
        # A deliberately displaced glyph must still fail the unchanged QC gate.
        broken=copy.deepcopy(caption);broken['phrases'][0]['words'][0]['x']=-100
        with pytest.raises(ValueError):inspect_caption_plan(broken,cfg)
        assert service.store.get(pid)['transcript_id']==before['transcript_id']
    finally:service.queue.close()


def test_json_alignment_offset_uses_the_same_source_clock():
    value={'schema_version':1,'words':[{'word_id':'unit','word':'XAUUSD','start':1.,'end':2.,
                                      'aligned_words':[{'word':'XAUUSD','start':1.2,'end':1.6}]}]}
    parsed=tracks.parse(json.dumps(value),'json','source',8,offset=.3)
    assert parsed['words'][0]['aligned_words'][0]['start']==pytest.approx(1.5)
    assert parsed['words'][0]['aligned_words'][0]['end']==pytest.approx(1.9)
    value['words'][0]['aligned_words'][0]['end']=9
    with pytest.raises(ValueError):tracks.parse(json.dumps(value),'json','source',8)
