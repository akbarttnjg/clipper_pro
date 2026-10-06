"""Current source context, final freshness and inactive proposal regressions."""
import copy
from dataclasses import replace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from clipper import intelligence
from clipper.intelligence import core
from clipper.studio_exchange import render_words
from clipper.dependency_cache import content_id
from clipper.tests.test_intelligence31 import example
from clipper.tests.test_studio4 import setup, request


def test_meaning_hints_survive_display_tokens_and_full_source_context(tmp_path):
    clip, words, _, _, cfg = example(tmp_path)
    words = words + [dict(word_id=999,word='Konteks',start=45.,end=45.5)]
    clip['intelligence']['signature']=core.signature(clip,words,cfg.audience)
    transcript=dict(words=words,raw_words=copy.deepcopy(words),duration=46.)
    document=dict(source=dict(source_id='source-a'),transcript_id='take-a',transcript_revision=0)
    tokens=render_words(transcript,document,clip,cfg)
    assert all(w['word_id'].startswith('tok-') for w in tokens)
    assert not any(w['start']>=45 for w in tokens)
    marked=intelligence.annotate_words(tokens,clip,cfg,context_words=words)
    assert [w['word'] for w in marked if w.get('meaning_emphasis')]==['Jangan','jualan','outcome']
    assert not any(w.get('meaning_emphasis') for w in tokens)
    assert all(w['source_word_ids']==w['origin_word_ids'] for w in marked)
    changed=copy.deepcopy(words);changed[-1]['word']='Konteks berubah'
    assert not any(w.get('meaning_emphasis') for w in intelligence.annotate_words(marked,clip,cfg,context_words=changed))
    assert not any(w.get('meaning_emphasis') for w in intelligence.annotate_words(marked,{**clip,'title':'Berubah'},cfg,context_words=words))
    assert not any(w.get('meaning_emphasis') for w in intelligence.annotate_words(marked,clip,replace(cfg,audience='finance'),context_words=words))


def test_invalid_token_origin_cannot_receive_meaning_hint(tmp_path):
    clip,words,_,_,cfg=example(tmp_path)
    token=next(w for w in words if w['word']=='Jangan')
    token={**token,'word_id':'tok-fake','source_word_ids':['missing']}
    assert not intelligence.annotate_words([token],clip,cfg,context_words=words)[0].get('meaning_emphasis')


def seed_final(svc,doc,cid,tmp_path):
    final=tmp_path/'final.mp4';final.write_bytes(b'validated-final')
    result=dict(absolute_file=str(final),output_content_id=content_id(final),
                dependency=svc.dependency(doc,cid,'portrait'),input_revision=doc['revision'])
    svc.store.mutate(doc['project_id'],doc['revision'],'test-final',{},
                     lambda d:d['clips'][cid]['variants']['portrait'].update(result=result))
    return svc.store.get(doc['project_id']),final


def test_final_readiness_tracks_inputs_instead_of_project_revision(setup,tmp_path):
    svc,doc,cid,_=setup
    assert svc.public(doc['project_id'])['clips'][cid]['variants']['portrait']['export_readiness']['status']=='missing'
    doc,final=seed_final(svc,doc,cid,tmp_path)
    svc.changes(request(doc,cid,[dict(op='rename',name='Nama baru')]))
    doc=svc.store.get(doc['project_id'])
    assert svc.export_readiness(doc,cid,'portrait',fresh=True)['status']=='ready'
    svc.changes(request(doc,cid,[dict(op='settings',values=dict(caption_scale=1.2))]))
    doc=svc.store.get(doc['project_id'])
    assert svc.public(doc['project_id'])['clips'][cid]['variants']['portrait']['export_readiness']['status']=='stale'
    with pytest.raises(ValueError,match='Render final revisi aktif'):
        svc.enqueue(doc['project_id'],'export',cid,'portrait',doc['revision'])
    assert not svc.queue.list(doc['project_id'])
    assert final.read_bytes()==b'validated-final'


def test_export_preflight_detects_missing_or_modified_final(setup,tmp_path):
    svc,doc,cid,_=setup;doc,final=seed_final(svc,doc,cid,tmp_path)
    final.write_bytes(b'modified-final')
    assert svc.export_readiness(doc,cid,'portrait',fresh=True)['status']=='changed'
    with pytest.raises(ValueError,match='berkas final berubah'):
        svc.enqueue(doc['project_id'],'export',cid,'portrait',doc['revision'])
    final.unlink()
    assert svc.export_readiness(doc,cid,'portrait',fresh=True)['status']=='missing'


def test_valid_export_can_enter_queue(setup,tmp_path):
    svc,doc,cid,_=setup;doc,_=seed_final(svc,doc,cid,tmp_path)
    job=svc.enqueue(doc['project_id'],'export',cid,'portrait',doc['revision'])
    assert job['status']=='queued'
    assert job['request']['dependency']==svc.dependency(doc,cid,'portrait')


def test_http_export_block_is_actionable_before_heavy_job(setup,tmp_path):
    from clipper.api_studio import create_router
    svc,doc,cid,_=setup
    app=FastAPI();app.include_router(create_router(svc));client=TestClient(app)
    response=client.post('/api/studio/projects/'+doc['project_id']+'/jobs',
                         json=dict(kind='export',clip_id=cid,variant_id='portrait',expected_revision=doc['revision']))
    assert response.status_code==400 and 'render final' in response.json()['detail']
    assert not svc.queue.list(doc['project_id'])


def test_unapplied_proposals_do_not_invalidate_final(setup,tmp_path):
    svc,doc,cid,_=setup
    variant=doc['clips'][cid]['variants']['portrait'];variant['settings']['broll_mode']='off'
    before=svc.dependency(doc,cid,'portrait')
    variant['recipe']={'notes':['Usulan tersedia'], 'scenes':[dict(id='proposal',enabled=True,source_start=3,source_end=6,
        asset=dict(path=str(tmp_path/'not-downloaded.mp4')))]}
    assert svc.dependency(doc,cid,'portrait')==before
    variant['settings']['broll_mode']='local';variant['recipe']['scenes'][0]['enabled']=False
    before=svc.dependency(doc,cid,'portrait')
    variant['recipe']['scenes'][0]['source_end']=8
    assert svc.dependency(doc,cid,'portrait')==before
    variant['recipe']['scenes'][0]['enabled']=True
    assert svc.dependency(doc,cid,'portrait')!=before
