"""Real queue publication, stale/cancel guards and permission-bound HTTP review."""
import copy,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from clipper.studio_service import StudioService
from clipper.studio_worker import execute,StaleJob
from clipper.config import Config
from clipper.delivery7_contract import selection
from clipper.delivery7_review import Reviews
from clipper.api_delivery7 import router
from clipper.api_studio import guarded
from clipper.artifact_store import verify
from clipper.project_store import Conflict
from .test_m7_media import rendered,delivery

@pytest.fixture
def svc(tmp_path,rendered):
    _,source,results,cfg=rendered
    s=StudioService(tmp_path,Config(work_dir='work',out_dir='clips',use_nvenc=False,visual_enabled=False),autostart=False)
    d=s.create(source);pid=d['project_id'];take=s.store.save_transcript(pid,{'words':[],'raw_words':[],'duration':4.,'language':'id'})
    def seed(doc):
        doc['transcript_id']=take
        for cid in ('clip-0','clip-1'):
            doc['clips'][cid]={'clip_id':cid,'title':'Cerita '+cid,'start':0.,'end':4.,'revision':0,'included':True,
                'variants':{v:{'settings':{},'override_keys':[],'timeline_revision':0} for v in ('portrait','landscape')}}
        for result in results:
            cid=result['clip_id'];vid=result['variant_id'];r=copy.deepcopy(result);r['dependency']=s.dependency(doc,cid,vid);doc['clips'][cid]['variants'][vid]['result']=r
    s.store.mutate(pid,0,'seed-real-m7-renders',{},seed);s.test_pid=pid
    yield s
    s.queue.close()


def doc(s):return s.store.get(s.test_pid)
def minimal():return {'editors':[],'merged':False,'clean':False,'stems':False,'publish':False}

def attach(s,package):
    current=doc(s);s.store.mutate(s.test_pid,current['revision'],'attach-immutable-m7-package',{},lambda d:d['exports'].append(copy.deepcopy(package)))


def test_preflight_is_read_only_and_queue_deduplicates_exact_options(svc):
    before=doc(svc);p=selection(svc,before,require_ready=True,fresh=True);assert p['coverage']==4 and p['ready'];assert doc(svc)==before
    a=svc.enqueue(svc.test_pid,'delivery_m7',expected_revision=before['revision'],options=minimal())
    b=svc.enqueue(svc.test_pid,'delivery_m7',expected_revision=before['revision'],options=minimal())
    assert a['id']==b['id'] and a['request']['dependency']==selection(svc,before,minimal(),fresh=True)['dependency']
    with pytest.raises(Conflict):svc.enqueue(svc.test_pid,'delivery_m7',expected_revision=0,options=minimal())


def test_actual_job_seals_then_atomically_publishes_exact_coverage(svc):
    before=doc(svc);job=svc.enqueue(svc.test_pid,'delivery_m7',expected_revision=before['revision'],options=minimal());result=execute(svc,job)
    after=doc(svc);assert len(after['exports'])==1 and after['exports'][0]['package_content_id']==result['package_content_id']
    assert verify(result,fresh=True) and len(result['coverage'])==4 and after['revision']==before['revision']+1
    assert svc.queue.get(job['id'])['status']=='completed'

@pytest.mark.parametrize('fault',['selection_change','cancel','lease_change'])
def test_change_during_delivery_never_replaces_previous_export(svc,monkeypatch,fault):
    from clipper import delivery7
    d=doc(svc);prior={'zip':'prior-untouched.zip','package_content_id':'prior'}
    svc.store.mutate(svc.test_pid,d['revision'],'seed-previous-export',{},lambda d:d['exports'].append(prior));before=doc(svc)
    job=svc.enqueue(svc.test_pid,'delivery_m7',expected_revision=before['revision'],options=minimal())
    original=delivery7.build
    def interrupted(*args,before_seal,**kw):
        if fault=='selection_change':
            now=doc(svc);svc.store.mutate(svc.test_pid,now['revision'],'change-selection-during-delivery',{},lambda d:d['clips']['clip-1'].update(included=False))
        elif fault=='cancel':svc.queue.cancel(job['id'])
        else:
            with svc.store.connect() as db:db.execute("UPDATE jobs SET lease_token='different' WHERE id=?",(job['id'],))
        before_seal();return original(*args,before_seal=before_seal,**kw)
    monkeypatch.setattr(delivery7,'build',interrupted)
    with pytest.raises((StaleJob,ValueError)):execute(svc,job)
    assert doc(svc)['exports']==[prior]


def test_review_permission_expiry_revocation_hash_binding_and_no_token_storage(svc,delivery):
    attach(svc,delivery);clock=[10000.];reviews=Reviews(svc,clock=lambda:clock[0]);revision=doc(svc)['revision']
    row=reviews.create(svc.test_pid,{'expected_revision':revision,'package_content_id':delivery['package_content_id'],'permission':'review','expires_minutes':15})
    token=row['url'].rsplit('/',1)[-1];view=reviews.view(token);assert view['download_url'] is None and len(view['entries'])==4
    path=reviews.resolve(token,view['entries'][0]['id']);assert path.is_file()
    with pytest.raises(ValueError,match='unduhan ZIP'):reviews.resolve(token,'package')
    with svc.store.connect() as db:
        stored=dict(db.execute('SELECT * FROM reviews7 WHERE id=?',(row['id'],)).fetchone());assert token not in json.dumps(stored)
    clock[0]+=901
    with pytest.raises(ValueError,match='kedaluwarsa'):reviews.view(token)
    clock[0]=10000
    download=reviews.create(svc.test_pid,{'expected_revision':revision,'package_content_id':delivery['package_content_id'],'permission':'download','expires_minutes':15})
    other=download['url'].rsplit('/',1)[-1];assert reviews.resolve(other,'package')==Path(delivery['zip'])
    reviews.revoke(svc.test_pid,download['id'],revision)
    with pytest.raises(ValueError,match='tidak aktif'):reviews.view(other)
    assert reviews.listing(svc.test_pid)[1]['revoked'] or any(r['revoked'] for r in reviews.listing(svc.test_pid))


def test_HTTP_preflight_review_watch_download_and_revoke(svc,delivery):
    attach(svc,delivery);app=FastAPI();app.include_router(router(svc,guarded),prefix='/api/studio');client=TestClient(app);pid=svc.test_pid
    pre=client.post(f'/api/studio/projects/{pid}/delivery7/preflight',json=minimal());assert pre.status_code==200 and pre.json()['coverage']==4
    payload={'expected_revision':doc(svc)['revision'],'package_content_id':delivery['package_content_id'],'permission':'review','expires_minutes':15}
    response=client.post(f'/api/studio/projects/{pid}/delivery7/reviews',json=payload);assert response.status_code==200
    row=response.json();value=client.get(row['url']);assert value.status_code==200
    page=client.get(row['url']+'/watch');assert page.status_code==200 and '<video' in page.text and "default-src 'none'" in page.headers['content-security-policy']
    assert client.get(row['url']+'/files/package').status_code==400
    url=value.json()['entries'][0]['url'];r=client.get(url,headers={'Range':'bytes=0-127'});assert r.status_code==206 and len(r.content)==128
    assert client.get(row['url']+'/files/../../manifest.json').status_code in (400,404)
    response=client.post(f'/api/studio/projects/{pid}/delivery7/reviews/{row["id"]}/revoke',json={'expected_revision':doc(svc)['revision']});assert response.status_code==200
    assert client.get(url).status_code==400


def test_corrupt_reviewed_member_cannot_be_served(svc,delivery,tmp_path):
    # A separate copied immutable set lets this test inject corruption safely.
    import shutil
    from clipper.artifact_store import rebase
    original=Path(delivery['artifact_root']);target=tmp_path/original.name;shutil.copytree(original,target)
    package=rebase(copy.deepcopy(delivery),original,target);attach(svc,package);reviews=Reviews(svc)
    row=reviews.create(svc.test_pid,{'expected_revision':doc(svc)['revision'],'package_content_id':package['package_content_id'],'permission':'download','expires_minutes':15})
    token=row['url'].rsplit('/',1)[-1];view=reviews.view(token);path=reviews.resolve(token,view['entries'][0]['id']);path.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='hilang/berubah'):reviews.resolve(token,view['entries'][0]['id'])


def test_missing_M4_ratio_blocks_each_missing_timeline_explicitly(svc):
    state=selection(svc,doc(svc),{**minimal(),'ratios':['portrait','square']},fresh=True)
    assert not state['ready'] and len(state['targets'])==4
    assert sum(b['status']=='missing_variant' for b in state['blockers'])==2
    with pytest.raises(ValueError,match='Buat rasio square'):svc.enqueue(svc.test_pid,'delivery_m7',expected_revision=doc(svc)['revision'],options={**minimal(),'ratios':['portrait','square']})
