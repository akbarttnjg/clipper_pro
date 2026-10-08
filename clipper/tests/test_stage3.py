"""Stage 3 acceptance at API/storage/worker boundaries, without model downloads."""
import copy
import json
import math
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from clipper import stage3, transcript_correction as correction, discovery, story, media_context, speech_jobs
from clipper.api_studio import create_router
from clipper.config import Config, validate_overrides
from clipper.studio_service import StudioService, identifier
from clipper.project_store import Conflict
from clipper.studio_exchange import render_words


def words(text):
    return [{'word_id': i, 'word': text, 'start': i*.6, 'end': i*.6+.5, 'probability': .94} for i, text in enumerate(text.split())]


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(media_context,'inspect',lambda _: {'duration':600.,'display_size':[640,360], 'audio_tracks':[{'index':1,'title':'Suara','language':'id'}]})
    source=tmp_path/'source.mp4';source.write_bytes(b'source-content-for-stage3')
    service=StudioService(tmp_path,Config(work_dir='work',out_dir='clips'),autostart=False)
    doc=service.create(source);ws=words('Jangan ubah nilai 0,01 lot jika risikonya belum jelas. Jawaban ini lengkap.')
    take=service.store.save_transcript(doc['project_id'],{'words':ws,'raw_words':ws,'heard_words':ws,'duration':600.,'language':'id'})
    def seed(d):
        d['transcript_id']=take;service.add_candidates(d,[{'start':0.,'end':8.,'title':'Utama','keywords':[]},{'start':1.,'end':8.,'title':'Kedua','keywords':[]}])
        d['discovery']={'analysis_revision':'test','round':1,'transcript_id':take,'transcript_revision':0,'rejections':[{'code':'incomplete','title':'Belum utuh','start':10.,'end':20.,'detail':'Penutup belum selesai.'}]}
    service.store.mutate(doc['project_id'],0,'initial-stage-three',{},seed)
    return service,service.store.get(doc['project_id'])


def request(doc,ops,cid=None):
    return {'project_id':doc['project_id'],'clip_id':cid,'variant_id':'portrait','expected_revision':doc['revision'], 'operation_id':identifier('operation'),'operations':ops}


def edit(doc,word_id,after,scope='shared_utterance'):
    return {'op':'correct_word','word_id':word_id,'after':after,'scope':scope,'transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision']}


@pytest.mark.parametrize('before,after',[
    ('0,01 lot','0,1 lot'),('10 kg','10 gram'),('tidak bisa','bisa'),('tidak tidak','tidak'),
    ('jika aman','aman'),('minimal dua','minimal tiga'),('tidak 2 lot','2 lot tidak'),('Rp 10','USD 10'),
])
def test_fact_changes_require_separate_approval(before,after):
    assert stage3.fact_review(before,after)['requires_confirmation']


def test_decimal_fragments_units_and_non_numeric_identifiers():
    assert not stage3.fact_review('0, 01 lot','0,01 lot')['requires_confirmation']
    assert not stage3.fact_review('10 kilogram','10 kg')['requires_confirmation']
    assert not stage3.fact_review('kata12','XAUUSD')['requires_confirmation']
    assert not stage3.fact_review('xau usd','XAUUSD')['requires_confirmation']


@pytest.mark.parametrize('text',['10 kg=10 gram','aman=tidak tidak aman','A=alias\nB=alias','tiga=dua'])
def test_glossary_cannot_silently_rewrite_facts_or_ambiguous_aliases(text):
    with pytest.raises(ValueError):correction.parse_glossary(text)


def test_numeric_edit_api_approval_is_bound_to_text_and_clock(project):
    svc,doc=project;app=FastAPI();app.include_router(create_router(svc));client=TestClient(app)
    payload=request(doc,[edit(doc,3,'0,1')])
    before=svc.store.transcript(doc['transcript_id'])
    assert client.post('/api/studio/changes',json=payload).status_code==400
    assert svc.store.get(doc['project_id'])==doc
    review=client.post('/api/studio/correction-review',json=payload).json()['reviews'][0]
    assert review['requires_confirmation']
    wrong=copy.deepcopy(payload);wrong['operations'][0].update(after='1',fact_confirmation=review['confirmation_stamp'])
    assert client.post('/api/studio/changes',json=wrong).status_code==400
    payload['operations'][0]['fact_confirmation']=review['confirmation_stamp']
    result=client.post('/api/studio/changes',json=payload);assert result.status_code==200
    assert client.post('/api/studio/changes',json=payload).json()==result.json()
    final=svc.store.get(doc['project_id']);assert svc.transcript(final)['words'][3]['word']=='0,1'
    assert next(iter(final['shared_corrections'].values()))['fact_approval']['before']=='0,01'
    assert svc.store.transcript(doc['transcript_id'])==before
    assert client.post('/api/studio/correction-review',json=wrong).status_code==409


def test_source_correction_preserves_clip_exception_and_undo(project):
    svc,doc=project;cid=list(doc['clips'])[0]
    svc.changes(request(doc,[edit(doc,1,'sesuaikan','clip')],cid));doc=svc.store.get(doc['project_id'])
    result=svc.changes(request(doc,[edit(doc,1,'ubahhlah')]))
    final=svc.store.get(doc['project_id']);assert svc.transcript(final)['words'][1]['word']=='ubahhlah'
    assert svc.transcript(final,cid)['words'][1]['word']=='sesuaikan'
    svc.store.undo(doc['project_id'],final['revision'],'undo-shared-text',result['revision'])
    final=svc.store.get(doc['project_id']);assert svc.transcript(final)['words'][1]['word']=='ubah'
    assert svc.transcript(final,cid)['words'][1]['word']=='sesuaikan'


def test_manual_phrase_timing_reaches_renderer_without_fabricated_spacing(project):
    svc,doc=project;cid=list(doc['clips'])[0]
    svc.changes(request(doc,[edit(doc,1,'ubah sekarang','clip')],cid));doc=svc.store.get(doc['project_id'])
    phrase=svc.transcript(doc,cid)['words'][1]
    assert stage3.expand_aligned([phrase])[0]['timing_status']=='phrase_span'
    aligned=[{'word':'ubah','start':.61,'end':.78},{'word':'sekarang','start':.86,'end':1.18}]
    op={'op':'align_words','scope':'clip','transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision'], 'origin_word_ids':[1],'text':phrase['word'],'words':aligned}
    old_dep=svc.dependency(doc,cid,'portrait');old_other=svc.dependency(doc,list(doc['clips'])[1],'landscape')
    saved=svc.changes(request(doc,[op],cid));doc=svc.store.get(doc['project_id'])
    assert svc.dependency(doc,cid,'portrait')!=old_dep
    transcript=svc.transcript(doc,cid);cfg=replace(svc.config(doc,cid,'portrait'),audio_stream_id='source:audio:1')
    rendered=render_words(transcript,doc,doc['clips'][cid],cfg);chosen=[w for w in rendered if w['source_word_ids']==[1]]
    assert [(w['word'],w['start'],w['end']) for w in chosen]==[('ubah',.61,.78),('sekarang',.86,1.18)]
    assert all(w['timing_status']=='manual' for w in chosen)
    assert len({w['word_id'] for w in chosen})==2
    assert correction.refine(transcript,cfg)['words'][1]['aligned_words']==aligned
    svc.store.undo(doc['project_id'],doc['revision'],'undo-measured-time',saved['revision'])
    assert not svc.transcript(svc.store.get(doc['project_id']),cid)['words'][1].get('aligned_words')


@pytest.mark.parametrize('bad',[
    [{'word':'ubah','start':math.nan,'end':1.}], [{'word':'ubah','start':1.,'end':.9}],
    [{'word':'ubah','start':-.1,'end':.3}], [{'word':'lain','start':.6,'end':1.}],
    [{'word':'ubah','start':.6,'end':1.2},{'word':'sekarang','start':1.,'end':1.4}],
])
def test_invalid_alignment_never_writes(bad):
    with pytest.raises(ValueError):stage3.validate_alignment('ubah',bad,0,2)


def test_ctc_partial_score_is_rejected():
    with pytest.raises(ValueError,match='skor'):stage3.validate_alignment('halo',[{'word':'halo','start':0.,'end':.2}],0,1,method='whisperx')


def test_text_change_invalidates_old_alignment_and_take_is_immutable(project):
    svc,doc=project;cid=list(doc['clips'])[0];immutable=svc.store.transcript(doc['transcript_id'])
    aligned={'op':'align_words','scope':'clip','transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision'], 'origin_word_ids':[1],'text':'ubah','words':[{'word':'ubah','start':.6,'end':.9}]}
    svc.changes(request(doc,[aligned],cid));doc=svc.store.get(doc['project_id'])
    svc.changes(request(doc,[edit(doc,1,'sesuaikan','clip')],cid));doc=svc.store.get(doc['project_id'])
    assert not svc.transcript(doc,cid)['words'][1].get('aligned_words')
    assert svc.store.transcript(doc['transcript_id'])==immutable


def test_rejected_restore_is_reviewable_persistent_and_undoable(project):
    svc,doc=project;row=svc.stage3_status(doc['project_id'])['rejections'][0]
    assert row['rejection_id']==svc.stage3_status(doc['project_id'])['rejections'][0]['rejection_id']
    operation={'op':'restore_rejected','rejection_id':row['rejection_id'],'start':9.,'end':22.}
    saved=svc.changes(request(doc,[operation]));final=svc.store.get(doc['project_id']);cid=final['restored_rejections'][row['rejection_id']]
    assert len(final['clips'])==3 and final['clips'][cid]['start']==9.
    assert final['clips'][cid]['boundary_pin']['end']==22.
    assert final['clips'][cid]['selection_source']=='manual'
    assert final['discovery']==doc['discovery']
    reopened=StudioService(svc.root,svc.base,autostart=False);assert reopened.store.get(doc['project_id'])['clips'][cid]['end']==22.
    svc.store.undo(doc['project_id'],final['revision'],'undo-rejected-clip',saved['revision']);assert svc.store.get(doc['project_id'])['clips']==doc['clips']


def test_rejection_from_old_transcript_is_not_restored(project):
    svc,doc=project;row=svc.stage3_status(doc['project_id'])['rejections'][0]
    svc.store.mutate(doc['project_id'],doc['revision'],'mark-report-stale',{},lambda d:d['discovery'].update(transcript_id='different-take'))
    doc=svc.store.get(doc['project_id'])
    with pytest.raises(ValueError,match='lama'):svc.changes(request(doc,[{'op':'restore_rejected','rejection_id':row['rejection_id']}]))


def test_temporal_overlap_does_not_delete_distinct_claims_or_facts():
    first={'start':0,'end':60,'main_claim':'Contoh pertama yang benar','story_kind':'example'}
    other={**first,'main_claim':'Jawaban lain yang lengkap'}
    assert not story.duplicate(first,other,[])
    assert not story.duplicate({'start':0,'end':60},{'start':0,'end':59.9,'main_claim':'tidak 10 gram'},words('10 kg'))


def test_coverage_exposes_pending_tail_and_excludes_silence():
    blocks=[[{'id':0,'start':0,'end':3,'text':'awal'}],[{'id':1,'start':90,'end':95,'text':'akhir'}]]
    coverage=discovery.coverage(blocks,{0},120)
    assert coverage['status']=='partial' and coverage['pending_segments']==1 and coverage['pending_ranges']==[[90,95]]
    complete=discovery.coverage(blocks,{0,1},120)
    assert complete['status']=='complete' and complete['speech_seconds']==8 and complete['source_seconds']==8
    chapters=stage3.chapter_plan([s for b in blocks for s in b],120,coverage_ranges=coverage['source_ranges'])
    assert chapters[-1]['status']=='pending' and chapters[-1]['label']=='akhir'


def test_semantic_reviewer_cannot_merge_different_units_or_conditions(tmp_path,monkeypatch):
    proposals=[{'start':0,'end':30,'title':'kg','main_claim':'Gunakan 10 kg jika aman','story_kind':'example'},
               {'start':60,'end':90,'title':'gram','main_claim':'Gunakan 10 gram jika aman','story_kind':'example'}]
    monkeypatch.setattr(discovery.requests,'post',lambda *a,**k:SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'response':json.dumps({'pairs':[{'keep':0,'duplicate':1,'reason':'topik sama'}]})}))
    removed,_=discovery.semantic_groups(proposals,Config(work_dir=str(tmp_path)))
    assert not removed


def test_asr_merge_keeps_numbers_negation_units_and_manual_edits():
    for before,after in [('0,01','0,1'),('tidak','bukan'),('lot','kg'),('jika','kalau')]:
        original=[{'word_id':0,'word':before,'start':0,'end':.4,'probability':.1}]
        newer=[{'word':after,'start':0,'end':.4,'probability':.99}]
        result,changes=correction.merge_recheck(original,newer);assert result==original and not changes
    original=[{'word_id':0,'word':'beris','start':0,'end':.4,'probability':.1,'manually_edited':True}]
    assert not correction.merge_recheck(original,[{'word':'bearish','start':0,'end':.4,'probability':.99}])[1]


def test_alignment_is_blocked_without_local_weights_and_never_enqueued(project):
    svc,doc=project
    with pytest.raises(ValueError,match='model alignment'):svc.enqueue(doc['project_id'],'alignment',expected_revision=doc['revision'])
    assert not svc.queue.list(doc['project_id'])
    status=svc.stage3_status(doc['project_id']);assert status['alignment']['manual_available']


def test_targeted_options_budgets_and_project_stage_scope(project):
    svc,doc=project;cid=list(doc['clips'])[0]
    with pytest.raises(ValueError):svc.enqueue(doc['project_id'],'asr_recheck',options={'limit':100})
    with pytest.raises(ValueError):speech_jobs.recheck_options({'origin_word_ids':[True]})
    job=svc.enqueue(doc['project_id'],'asr_recheck',cid,options={'limit':1,'origin_word_ids':[3]})
    assert job['request']['options']['limit']==1 and job['target']['clip_id']==cid
    job=svc.enqueue(doc['project_id'],'correction',cid);assert job['target']['clip_id'] is None


def test_stage3_defaults_keep_target_soft_and_no_fixed_quota():
    assert validate_overrides({'length':'auto'})=={'min_clip_s':20.,'max_clip_s':120.}
    assert Config().num_clips==0


def prepare_worker(svc,doc,monkeypatch):
    from clipper import editorial
    monkeypatch.setattr(editorial,'release',lambda cfg:None)
    monkeypatch.setattr(media_context,'prepare',lambda path,cfg,progress:{'source_id':doc['source']['source_id'],'input_fingerprint':'media-test',
        'payload':{'working_path':str(path),'audio_stream_id':'source:audio:1','duration':600.,'selected_audio_index':1,'audio_tracks':doc['source']['info']['audio_tracks']}})


def test_targeted_worker_preserves_raw_take_and_retargets_manual_patches(project,monkeypatch):
    from clipper.studio_worker import execute
    svc,doc=project;cid=list(doc['clips'])[0]
    svc.changes(request(doc,[edit(doc,1,'manual khusus','clip')],cid));doc=svc.store.get(doc['project_id'])
    old_take=doc['transcript_id'];old_raw=svc.store.transcript(old_take)['raw_words'];prepare_worker(svc,doc,monkeypatch)
    def recheck(kind,source,payload,cfg,options):
        assert payload['words'][1]['word']=='ubah' and payload['words'][1]['manually_edited']
        ws=copy.deepcopy(payload['words']);ws[9].update(word='Penjelasan',correction='audio_recheck',source_word_ids=[9])
        return {'words':ws,'changes':[{'word_id':9,'before':'Jawaban','after':'Penjelasan'}],'report':{'checked':1,'accepted':1,'errors':[],'device':'cpu'}}
    monkeypatch.setattr(speech_jobs,'run',recheck)
    job=svc.enqueue(doc['project_id'],'asr_recheck',expected_revision=doc['revision']);execute(svc,job)
    final=svc.store.get(doc['project_id']);assert final['transcript_id']!=old_take
    assert svc.transcript(final,cid)['words'][1]['word']=='manual khusus'
    assert svc.transcript(final)['words'][1]['word']=='ubah'
    assert svc.store.transcript(final['transcript_id'])['raw_words']==old_raw
    assert svc.store.transcript(old_take)['raw_words']==old_raw
    assert svc.transcript(final)['words'][9]['word']=='Penjelasan'
    assert svc.queue.get(job['id'])['status']=='completed'


@pytest.mark.parametrize('cancel',[False,True])
def test_speech_worker_never_publishes_after_cancel_or_input_change(project,monkeypatch,cancel):
    from clipper.studio_worker import execute,StaleJob
    svc,doc=project;prepare_worker(svc,doc,monkeypatch);old_take=doc['transcript_id']
    job=svc.enqueue(doc['project_id'],'asr_recheck',expected_revision=doc['revision'])
    def recheck(kind,source,payload,cfg,options):
        if cancel:svc.queue.update(job['id'],status='cancel_requested')
        else:svc.changes(request(svc.store.get(doc['project_id']),[edit(doc,2,'takaran')]))
        ws=copy.deepcopy(payload['words']);ws[9]['word']='Penjelasan'
        return {'words':ws,'changes':[{'word_id':9,'before':'Jawaban','after':'Penjelasan'}],'report':{'checked':1,'accepted':1,'errors':[]}}
    monkeypatch.setattr(speech_jobs,'run',recheck)
    with pytest.raises(StaleJob):execute(svc,job)
    assert svc.store.get(doc['project_id'])['transcript_id']==old_take
    assert svc.store.transcript(old_take)['words'][9]['word']=='Jawaban'


def test_manual_boundary_review_keeps_bounds_and_returns_proposal(tmp_path,monkeypatch):
    ws=words('Bagaimana caranya? Tingkatkan skill. Sesudah itu belajar lagi.')
    candidate={'start':0.,'end':2.,'title':'Skill','reason':'','revision':0,'boundary_pin':{'start':0.,'end':2.,'source':'manual'}}
    raw={'start_segment':0,'end_segment':1,'title':'Belajar skill','reason':'Belajar','value':5,'opening':5,'closure':5,'complete':True,
         'ending_evidence':'Tingkatkan skill.','keywords':[],'hook_quote':''}
    monkeypatch.setattr(story,'request',lambda *a,**k:[raw])
    result=story.review_candidate(candidate,{'words':ws,'duration':6.},Config(work_dir=str(tmp_path),min_clip_s=.5,max_clip_s=6))
    assert result['start']==candidate['start'] and result['end']==candidate['end'] and result['boundary_pin']==candidate['boundary_pin']
    assert result['boundary_proposal']['end']>candidate['end']


def test_local_asr_model_resolution_requires_cache_only(monkeypatch):
    calls=[]
    module=SimpleNamespace(download_model=lambda name,**kw:calls.append((name,kw)) or '/cached/weights')
    monkeypatch.setitem(sys.modules,'faster_whisper.utils',module)
    assert speech_jobs._asr_model_path('small')=='/cached/weights'
    assert calls==[('small',{'local_files_only':True})]


def test_backup_restore_relinks_alignment_take_and_keeps_source_evidence(project):
    from clipper import studio_storage
    svc,doc=project;cid=list(doc['clips'])[0]
    operation={'op':'align_words','scope':'clip','transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision'],
        'origin_word_ids':[1],'text':'ubah','words':[{'word':'ubah','start':.6,'end':.9}]}
    svc.changes(request(doc,[operation],cid));doc=svc.store.get(doc['project_id'])
    archive=studio_storage.backup(svc,doc['project_id'],True);restored=studio_storage.restore(svc,archive['file'])
    restored=svc.store.get(restored['project_id']);assert restored['transcript_id']!=doc['transcript_id']
    assert svc.transcript(restored,cid)['words'][1]['aligned_words']==operation['words']
    assert restored['discovery']['transcript_id']==restored['transcript_id']
    assert svc.transcript(doc,cid)['words'][1]['aligned_words']==operation['words']


@pytest.mark.parametrize('measured',[True,False])
def test_ctc_adapter_uses_local_cpu_no_interpolation_and_rejects_partial(tmp_path,monkeypatch,measured):
    model=tmp_path/'ctc';model.mkdir()
    for name,data in [('config.json',{'model_type':'wav2vec2'}),('vocab.json',{}),('preprocessor_config.json',{})]:
        (model/name).write_text(json.dumps(data))
    (model/'pytorch_model.bin').write_bytes(b'fixture-not-real-model')
    calls=[]
    def load(language_code,device,model_name):
        calls.append((language_code,device,model_name));return 'model',{'dictionary':{}}
    def align(segments,model,metadata,audio,**kw):
        assert kw['device']=='cpu' and kw['interpolate_method']=='ignore'
        rows=[{'word':'ubah','start':.1,'end':.25,'score':.9},{'word':'sekarang','start':.35,'end':.65,'score':.8}]
        if not measured:rows[1].pop('score')
        return {'word_segments':rows}
    monkeypatch.setitem(sys.modules,'nltk',SimpleNamespace(download=lambda *a,**k:pytest.fail('download not allowed')))
    monkeypatch.setitem(sys.modules,'whisperx',SimpleNamespace(load_align_model=load,align=align))
    monkeypatch.setattr(speech_jobs,'_excerpt',lambda *a:None)
    ws=words('awal ubah sesudah');ws[1].update(word='ubah sekarang',manually_edited=True)
    result=speech_jobs._alignment('source.mp4',{'words':ws,'duration':3.,'language':'id'},Config(),{'model_path':str(model),'origin_word_ids':[],'limit':1})
    assert calls==[('id','cpu',str(model.resolve()))]
    assert len(result['patches'])==(1 if measured else 0)
    assert bool(result['report']['errors']) is (not measured)
    if measured:assert result['patches'][0]['words'][1]['start']==.85


def test_ffmpeg_excerpt_preserves_requested_duration(tmp_path):
    import wave
    source=tmp_path/'source.wav';target=tmp_path/'excerpt.wav'
    with wave.open(str(source),'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000);audio.writeframes(b'\0\0'*16000)
    speech_jobs._excerpt(source,.2,.7,target)
    with wave.open(str(target)) as audio:
        assert audio.getframerate()==16000 and audio.getnchannels()==1 and audio.getnframes()==8000


def test_speech_child_is_offline_and_keeps_model_ref_in_owned_runtime(project,monkeypatch):
    svc,doc=project;captured=[]
    monkeypatch.setattr(speech_jobs,'available_asr_models',lambda:[{'id':'managed:sample','python':'existing-python','weights':'/local/model'}])
    def run(command,**kwargs):
        captured.append((command,kwargs));Path(command[-1]).write_text(json.dumps({'words':[],'changes':[],'report':{'checked':0}}))
        return SimpleNamespace(returncode=0,stderr='')
    monkeypatch.setattr(speech_jobs.subprocess,'run',run)
    result=speech_jobs.run('asr_recheck',doc['source']['path'],svc.store.transcript(doc['transcript_id']),Config(),{'limit':1,'model_ref':'managed:sample'})
    command,kwargs=captured[0];assert command[0]=='existing-python' and command[2]=='clipper.speech_jobs'
    assert kwargs['env']['HF_HUB_OFFLINE']=='1' and kwargs['env']['TRANSFORMERS_OFFLINE']=='1'
    assert result['report']['checked']==0


def test_memory_and_project_glossary_ambiguity_rolls_back(project):
    svc,doc=project
    svc.changes(request(doc,[{'op':'analysis_settings','values':{'glossary':'IstilahA=salahdengar'}}]));doc=svc.store.get(doc['project_id'])
    with pytest.raises(ValueError,match='ambigu'):svc.changes(request(doc,[{'op':'alias_upsert','canonical':'IstilahB','alias':'salahdengar','enabled':True,'topic':'general'}]))
    assert svc.store.get(doc['project_id'])==doc
