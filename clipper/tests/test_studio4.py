"""Cross-boundary Studio 4 gates: concurrent tabs, lineage, cache and recovery."""
import copy
import json
import os
import zipfile
from pathlib import Path
from dataclasses import replace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from clipper.config import Config
from clipper.studio_service import StudioService,identifier,apply_corrections
from clipper.project_store import Conflict,ProjectStore
from clipper.dependency_cache import content_id
from clipper import studio_storage,media_context


@pytest.fixture
def setup(tmp_path,monkeypatch):
    info={'duration':6000.,'display_size':[640,360],'encoded_size':[640,360],
          'audio_tracks':[{'index':1,'title':'Suara','language':'id'}]}
    monkeypatch.setattr(media_context,'inspect',lambda path:info)
    source=tmp_path/'source.mp4';source.write_bytes(b'example-source-middle-contents')
    svc=StudioService(tmp_path,Config(work_dir='work',out_dir='clips',use_nvenc=False),autostart=False)
    doc=svc.create(source)
    words=[{'word_id':i,'word':f'kata{i}','start':i*.5,'end':i*.5+.4} for i in range(40)]
    take=svc.store.save_transcript(doc['project_id'],{'words':words,'raw_words':words,'duration':20})
    def change(d):
        d['transcript_id']=take
        svc.add_candidates(d,[{'title':'Cerita A','start':0.,'end':14.,'keywords':[]},
                              {'title':'Cerita B','start':5.,'end':19.,'keywords':[]}])
    svc.store.mutate(doc['project_id'],0,'seed-initial',{},change)
    doc=svc.store.get(doc['project_id']);cid=list(doc['clips'])[0]
    return svc,doc,cid,source


def request(doc,cid,operations,revision=None,vid='portrait'):
    return {'project_id':doc['project_id'],'clip_id':cid,'variant_id':vid,'operation_id':identifier('op'),
            'expected_revision':doc['revision'] if revision is None else revision,'operations':operations}


def test_two_tabs_idempotency_and_undo_preserve_newer_fields(setup):
    svc,doc,cid,_=setup
    first=request(doc,cid,[{'op':'settings','values':{'caption_scale':1.15}}]);r=svc.changes(first)
    assert svc.changes(first)==r
    with pytest.raises(Conflict):svc.changes(request(doc,cid,[{'op':'settings','values':{'caption_scale':.8}}]))
    current=svc.store.get(doc['project_id']);svc.changes(request(current,cid,[{'op':'settings','values':{'music_db':-30}}]))
    current=svc.store.get(doc['project_id']);svc.store.undo(doc['project_id'],current['revision'],'undo-an-edit',r['revision'])
    variant=svc.variant(svc.store.get(doc['project_id']),cid,'portrait')
    assert variant['settings'].get('caption_scale') is None and variant['settings']['music_db']==-30
    with pytest.raises(ValueError,match='berbeda'):svc.changes({**first,'operations':[{'op':'rename','name':'Different'}]})


def test_failed_transaction_is_all_or_nothing(setup):
    svc,doc,cid,_=setup
    with pytest.raises(ValueError):svc.changes(request(doc,cid,[{'op':'rename','name':'MUST ROLLBACK'},{'op':'bounds','start':-1,'end':4}]))
    assert svc.store.get(doc['project_id'])==doc


def test_shared_utterance_keeps_other_clip_manual_exception(setup):
    svc,doc,cid,_=setup;other=list(doc['clips'])[1]
    def correction(after,scope='clip'):
        return {'op':'correct_word','word_id':12,'after':after,'scope':scope,'transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision']}
    svc.changes(request(doc,other,[correction('manual exception')]))
    doc=svc.store.get(doc['project_id']);svc.changes(request(doc,cid,[correction('XAUUSD','shared_utterance')]))
    final=svc.store.get(doc['project_id'])
    assert svc.transcript(final,cid)['words'][12]['word']=='XAUUSD'
    assert svc.transcript(final,other)['words'][12]['word']=='manual exception'
    assert svc.store.transcript(doc['transcript_id'])['raw_words'][12]['word']=='kata12'


def test_paged_10001_word_edit_is_small_and_persistent(setup):
    svc,doc,cid,_=setup
    words=[{'word_id':i,'word':'kata','start':i*.5,'end':i*.5+.3} for i in range(10001)]
    take=svc.store.save_transcript(doc['project_id'],{'words':words,'duration':5001})
    svc.store.mutate(doc['project_id'],doc['revision'],'long-take-01',{},lambda d:d.update(transcript_id=take))
    page=svc.page(doc['project_id'],offset=10000,limit=500)
    assert len(page['words'])==1 and page['total']==10001 and page['next_offset'] is None
    assert len(json.dumps(svc.page(doc['project_id'],limit=100)))<40000
    doc=svc.store.get(doc['project_id']);svc.changes(request(doc,cid,[{'op':'correct_word','word_id':2,'after':'akurat','scope':'clip',
        'transcript_id':take,'transcript_revision':doc['transcript_revision']}]))
    with svc.store.connect() as db:
        op=db.execute('SELECT changes FROM history WHERE project_id=? ORDER BY revision DESC LIMIT 1',(doc['project_id'],)).fetchone()[0]
        assert len(op)<2000
    reopened=StudioService(svc.root,svc.base,autostart=False)
    assert reopened.page(doc['project_id'],cid)['words'][2]['word']=='akurat'


def test_variants_and_batch_preserve_manual_fields(setup):
    svc,doc,cid,_=setup;landscape=svc.dependency(doc,cid,'landscape')
    svc.changes(request(doc,cid,[{'op':'settings','values':{'caption_scale':.9,'layout':'fit'}}]))
    doc=svc.store.get(doc['project_id']);assert svc.dependency(doc,cid,'landscape')==landscape
    svc.changes(request(doc,cid,[{'op':'style','style_id':'energetic','targets':[{'clip_id':c,'variant_id':'portrait'} for c in doc['clips']]}]))
    final=svc.store.get(doc['project_id']);assert svc.variant(final,cid,'portrait')['settings']['layout']=='fit'
    assert svc.variant(final,list(final['clips'])[1],'portrait')['settings']['layout']=='fill'
    assert svc.variant(final,cid,'landscape')['settings']=={}


def test_middle_change_same_size_and_mtime_invalidates_source(setup):
    svc,doc,cid,source=setup;before=svc.dependency(doc,cid,'portrait');s=source.stat();data=bytearray(source.read_bytes());data[12]^=1;source.write_bytes(data);os.utime(source,ns=(s.st_atime_ns,s.st_mtime_ns))
    assert svc.dependency(doc,cid,'portrait',fresh=True)!=before
    with pytest.raises(ValueError,match='berbeda'):studio_storage.relink(svc,doc['project_id'],source,doc['revision'],'relink-other')


def test_broll_split_across_shots_keeps_full_duration_and_offsets(tmp_path):
    from clipper.illustration_schedule import attach
    asset=tmp_path/'broll.mp4';asset.write_bytes(b'asset')
    plan={'fps':30,'duration':20.,'warnings':[],'spans':[{'start':0,'end':20,'kind':'body'}],
        'shots':[{'source_start':0,'source_end':6,'start':0,'end':6},{'source_start':6,'source_end':20,'start':6,'end':20}]}
    recipe={'scenes':[{'id':'b1','source_start':5.,'source_end':8.,'enabled':True,'asset':{'path':str(asset),'duration':9.}}]}
    report=attach(plan,recipe,Config(broll_mode='local'))
    assert [(r['start'],r['end'],r['asset_start']) for r in plan['broll']]==[(5.,6.,0.),(6.,8.,1.)]
    assert sum(e['duration'] for e in plan['broll'])==3.
    assert len([r for r in report if r['status']=='scheduled'])==2
    recipe['scenes'][0]['enabled']=False;attach(plan,recipe,Config(broll_mode='local'))
    assert plan['broll']==[] and plan['broll_schedule'][0]['reason']=='Dinonaktifkan'


def test_cleanup_only_owned_cache_rejects_changed_listing(setup):
    svc,doc,cid,source=setup;pid=doc['project_id']
    preview=svc.work/pid/'cache/previews/key/output/test.mp4';preview.parent.mkdir(parents=True);preview.write_bytes(b'preview')
    final=Path(svc.base.out_dir)/pid/'video/final.mp4';final.parent.mkdir(parents=True);final.write_bytes(b'final')
    listing=studio_storage.inventory(svc)
    with pytest.raises(ValueError):studio_storage.cleanup(svc,[next(r['id'] for r in listing['entries'] if not r['deletable'])],listing['etag'])
    preview.write_bytes(b'new preview')
    with pytest.raises(Conflict):studio_storage.cleanup(svc,[next(r['id'] for r in listing['entries'] if r['deletable'])],listing['etag'])
    listing=studio_storage.inventory(svc);studio_storage.cleanup(svc,[r['id'] for r in listing['entries'] if r['deletable']],listing['etag'])
    assert not preview.exists() and final.read_bytes()==b'final' and source.exists()
    assert svc.store.transcript(doc['transcript_id'])['words']


def test_backup_restore_and_relink_keep_identity_without_overwriting(setup):
    svc,doc,cid,source=setup
    old=svc.store.get(doc['project_id']);package=studio_storage.backup(svc,doc['project_id'],True)
    restored=studio_storage.restore(svc,package['file'])
    assert restored['project_id']!=doc['project_id'] and svc.store.get(doc['project_id'])==old
    assert content_id(restored['source']['path'])==doc['source']['source_id']
    assert restored['transcript_id']!=doc['transcript_id']
    replacement=source.with_name('moved.mp4');replacement.write_bytes(source.read_bytes());source.unlink()
    studio_storage.relink(svc,doc['project_id'],replacement,doc['revision'],'relink-identical')
    assert svc.store.get(doc['project_id'])['transcript_id']==doc['transcript_id']


def test_backup_zip_slip_rejected(setup,tmp_path):
    svc,*_=setup;path=tmp_path/'bad.zip'
    with zipfile.ZipFile(path,'w') as z:z.writestr('../outside.txt','MUST NOT WRITE')
    with pytest.raises(ValueError,match='aman'):studio_storage.restore(svc,path)
    assert not (svc.work/'outside.txt').exists()


def test_source_inside_preview_tree_is_never_cleanup_target(setup):
    svc,doc,cid,source=setup
    nested=svc.work/doc['project_id']/'cache/previews/source.mp4'
    nested.parent.mkdir(parents=True);nested.write_bytes(source.read_bytes())
    def relocate(d):d['source']['path']=str(nested)
    svc.store.mutate(doc['project_id'],doc['revision'],'move-source-into-cache',{},relocate)
    listing=studio_storage.inventory(svc)
    entries=[r for r in listing['entries'] if r.get('path')==str(nested)]
    assert entries and not any(r['deletable'] for r in entries)
    ids=[r['id'] for r in listing['entries'] if r['deletable']]
    if ids:studio_storage.cleanup(svc,ids,listing['etag'])
    assert nested.read_bytes()==source.read_bytes()


def test_legacy_missing_media_keeps_project_and_transcript_for_relink(setup):
    svc,doc,cid,source=setup
    state={'media':str(source.with_name('missing.mp4')),'cfg':svc.base,
           'transcript':{'words':[{'word_id':0,'word':'XAUUSD','start':0,'end':1}],'duration':14},
           'scored':[{'title':'Proyek lama','start':0,'end':14}]}
    assert svc.migrate({'legacy-missing':state})==[]
    imported=svc.store.get('legacy-missing')
    assert imported['source']['requires_analysis'] and len(imported['clips'])==1
    assert svc.store.transcript(imported['transcript_id'])['words'][0]['word']=='XAUUSD'
    assert svc.migrate({'legacy-missing':state})==[]
    assert svc.store.get('legacy-missing')==imported


def test_queue_persists_recovers_and_deduplicates(setup):
    svc,doc,cid,_=setup
    one=svc.enqueue(doc['project_id'],'render',cid,'portrait',doc['revision']);two=svc.enqueue(doc['project_id'],'render',cid,'portrait',doc['revision'])
    assert one['id']==two['id']
    svc.queue.update(one['id'],status='running',pid=999999999,pid_birth='not-a-process')
    reopened=StudioService(svc.root,svc.base,autostart=False)
    assert reopened.queue.get(one['id'])['status']=='interrupted'
    resumed=reopened.queue.resume(one['id']);assert resumed['status']=='queued'
    reopened.queue.cancel(resumed['id']);assert reopened.queue.get(resumed['id'])['status']=='canceled'


def test_actual_http_revision_conflict_and_payload_boundary(setup):
    from clipper.api_studio import create_router
    svc,doc,cid,_=setup;app=FastAPI();app.include_router(create_router(svc));client=TestClient(app)
    edit=request(doc,cid,[{'op':'bounds','start':1,'end':12}])
    assert client.post('/api/studio/changes',json=edit).status_code==200
    stale=request(doc,cid,[{'op':'bounds','start':2,'end':11}])
    response=client.post('/api/studio/changes',json=stale)
    assert response.status_code==409 and response.json()['status']=='conflict'
    assert svc.store.get(doc['project_id'])['clips'][cid]['start']==1
    assert client.post('/api/studio/projects/'+doc['project_id']+'/jobs',json={'kind':'render','clip_id':cid}).status_code==400


def test_analysis_component_uses_real_studio_service(setup):
    from clipper.api_studio import create_router
    from clipper.api_analysis import create_router as analysis_router
    svc,doc,cid,_=setup;app=FastAPI();app.include_router(create_router(svc));app.include_router(analysis_router({'get_snapshot':svc.analysis_snapshot,'submit_changes':svc.changes,'run_stage':svc.run_stage}))
    client=TestClient(app);target={'project_id':doc['project_id'],'clip_id':cid,'variant_id':'portrait'}
    response=client.get('/api/analysis/snapshot',params=target);assert response.status_code==200
    snap=response.json()['data']['transcript'];token=snap['payload']['display_tokens'][0]
    from clipper.analysis_adapter import correction_proposal
    proposal=correction_proposal(snap,token['token_id'],'ucapan',expected_revision=doc['revision'],expected_transcript_revision=0,operation_id='test-a-service')
    assert client.post('/api/analysis/changes',json={**target,**proposal}).status_code==200
    assert svc.page(doc['project_id'],cid)['words'][0]['word']=='ucapan'


def test_benchmark_requires_reference_and_protects_negation():
    from clipper.benchmark import evaluate
    with pytest.raises(ValueError):evaluate({}, {'text':'contoh'})
    report=evaluate({'text':'XAUUSD tidak naik 10 poin','terms':['XAUUSD'],'clips':[{'start':0,'end':20}]},
        {'text':'XAUUSD naik 10 poin','clips':[{'start':0,'end':20},{'start':10,'end':25}]})
    assert report['protected_tokens_exact'] is False and report['status']=='needs_review'
    assert report['duplicate_seconds']==10 and report['story_coverage']==1
