"""M8 recovery, tenant input, OAuth-loopback and asset portability regressions."""
import hashlib
import json
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
import httpx
import pytest
from PIL import Image
from clipper.m8_contract import AccessDenied, SCOPES, canonical
from clipper.m8_workspace import Actor
from .test_m8_contract import m8, account, draft, approved


def test_OAuth_PKCE_state_loopback_and_encrypted_tokens(m8):
    original=m8.transport.request;seen=[]
    def transport(method,url,**kwargs):
        if url=='https://oauth2.googleapis.com/token':
            seen.append(kwargs['data'])
            return httpx.Response(200,json={'access_token':'new-secret-oauth','refresh_token':'new-secret-refresh','expires_in':3600,'scope':' '.join(SCOPES.values())})
        return original(method,url,**kwargs)
    m8.transport.request=transport
    flow=m8.accounts.oauth_start(m8.test_actor,{'client_id':'fixture.apps.googleusercontent.com','client_secret':'fixture-secret','name':'OAuth fixture'})
    query=parse_qs(urlsplit(flow['url']).query)
    assert query['code_challenge_method']==['S256'] and query['redirect_uri']==[flow['redirect_uri']]
    bad=flow['redirect_uri']+'?'+urlencode({'code':'authored-code','state':'invalid'})
    with pytest.raises(urllib.error.HTTPError):urllib.request.urlopen(bad,timeout=3)
    assert not seen
    good=flow['redirect_uri']+'?'+urlencode({'code':'authored-code','state':query['state'][0]})
    with urllib.request.urlopen(good,timeout=3) as response:assert response.status==200
    result=m8.accounts.oauth_status(m8.test_actor,flow['id']);assert result['status']=='connected'
    assert len(seen)==1 and len(seen[0]['code_verifier'])>=43
    import base64
    challenge=base64.urlsafe_b64encode(hashlib.sha256(seen[0]['code_verifier'].encode()).digest()).decode().rstrip('=')
    assert challenge==query['code_challenge'][0]
    with m8.service.store.connect() as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM m8_accounts')]
        assert 'new-secret-oauth' not in canonical(rows) and 'new-secret-refresh' not in canonical(rows)


def test_durable_receipt_blocks_duplicate_after_explicit_SQLite_state_loss(m8):
    row=approved(m8)
    for _ in range(3):m8.worker.tick()
    with m8.db.transaction() as db:db.execute('DELETE FROM m8_publish')
    # A reconnected profile has a new local account ID but the same channel identity.
    with pytest.raises(ValueError,match='Receipt'):
        draft(m8)


def test_one_remaining_daily_slot_cannot_be_taken_twice(m8):
    m8.workspaces.configure(m8.test_actor,{'expected_version':0,'daily_publish':1})
    def reserve(reference):
        try:
            with m8.db.transaction() as db:m8.workspaces.reserve(db,m8.test_actor,'publish',reference)
            return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,['one','two']))
    assert sum(results)==1


def test_server_member_cannot_insert_new_host_paths_or_foreign_asset_ids(m8):
    token=m8.workspaces.issue_session(m8.test_actor,{'user_id':'edit','role':'editor'})
    actor=m8.workspaces.authenticate(token['token'])
    for operation in [{'op':'settings','values':{'music_path':'/private/other.wav'}},{'op':'settings','values':{'ollama_url':'http://169.254.169.254/'}},{'op':'m5_layer','asset_id':'asset-foreign'}]:
        with pytest.raises(AccessDenied):m8.scoped_inputs(actor,m8.test_pid,[operation])
    m8.scoped_inputs(actor,m8.test_pid,[{'op':'settings','values':{'caption_scale':1.2}}])


def test_asset_registry_and_actual_image_survive_restore(m8,tmp_path):
    path=tmp_path/'authored.png';Image.new('RGB',(8,8),(20,100,60)).save(path)
    asset=m8.service._assets5.register(path,{'name':'Owned logo','permission':'user_owned'})
    m8.service.store.mutate(m8.test_pid,0,'attach-owned-asset',{},lambda d:d.update(m8_test_asset_id=asset['id']))
    backup=m8.backups.create(m8.test_actor,{'project_id':m8.test_pid,'expected_revision':1})
    with m8.db.transaction() as db:db.execute('DELETE FROM assets5 WHERE id=?',(asset['id'],))
    restored=m8.backups.restore(m8.test_actor,{'file_id':backup['url'].rsplit('/',1)[-1]})
    result=m8.service._assets5.get(asset['id'])
    assert result['sha256']==asset['sha256'] and Path(result['path']).is_file()
    assert m8.service.store.get(restored['project_id'])['m8_test_asset_id']==asset['id']


def test_cross_project_rows_in_self_checksummed_backup_are_rejected(m8,tmp_path):
    backup=m8.backups.create(m8.test_actor,{'project_id':m8.test_pid,'expected_revision':0})
    source=m8.file(m8.test_actor,backup['url'].rsplit('/',1)[-1])
    with zipfile.ZipFile(source) as archive:files={n:archive.read(n) for n in archive.namelist()}
    snapshot=json.loads(files['snapshot.json']);snapshot['tables']['operations']=[{'project_id':'foreign-project','operation_id':'poison-id','request_hash':'bad','response':'{}'}]
    files['snapshot.json']=canonical(snapshot).encode();manifest=json.loads(files['manifest.json']);manifest['files']['snapshot.json']='sha256:'+hashlib.sha256(files['snapshot.json']).hexdigest();files['manifest.json']=canonical(manifest).encode()
    bad=tmp_path/'poison.zip'
    with zipfile.ZipFile(bad,'w') as archive:
        for n,b in files.items():archive.writestr(n,b)
    with pytest.raises(ValueError,match='luar proyek'):m8.backups.restore(m8.test_actor,{'path':str(bad)})
    with m8.service.store.connect() as db:assert not db.execute("SELECT 1 FROM operations WHERE project_id='foreign-project'").fetchone()


def test_full_publish_event_export_and_diagnosis_have_no_account_secret(m8):
    row=approved(m8)
    for _ in range(3):m8.worker.tick()
    m8.analytics.observe(m8.test_actor,{'publish_id':row['id'],'start_date':'2026-10-01','end_date':'2026-10-02','values':{'views':0}})
    report=m8.analytics.export(m8.test_actor)
    body=m8.file(m8.test_actor,report['json'].rsplit('/',1)[-1]).read_text()
    body+=canonical(m8.db.events('solo'))+canonical(m8.backups.diagnostics(m8.test_actor,{})['preview'])
    assert all(value not in body for value in ('secret-fixture-access','secret-fixture-refresh','secret-client','upload_id='))


def test_experiment_assignment_is_frozen_before_approval_not_causal_claim(m8):
    first=draft(m8,platform='tiktok',connected=False);second=draft(m8,platform='tiktok',connected=False)
    experiment=m8.analytics.experiment(m8.test_actor,{'name':'Font A/B','hypothesis':'Retention berbeda','variants':['A','B'],'mode':'randomized_assignment','primary_metric':'views','context':'Audience dan waktu dicatat terpisah'})
    result=m8.analytics.assign(m8.test_actor,{'id':experiment['id'],'expected_version':0,'unit_id':'story1','candidates':{'A':first['id'],'B':second['id']}})
    assert result['data']['assignments'][0]['publish_id'] in (first['id'],second['id']) and not result['data']['causal_effect_established']


def test_workflow_respects_revision_and_stops_at_existing_core_guard(m8):
    flow=m8.automation.save(m8.test_actor,{'name':'Authored workflow'})
    run=m8.automation.submit(m8.test_actor,{'workflow_id':flow['id'],'project_id':m8.test_pid,'expected_revision':0},'workflow-command-1')
    m8.service.store.mutate(m8.test_pid,0,'human-edit-before-autopilot',{},lambda d:d.update(name='User edit'))
    m8.automation.tick()
    result=next(r for r in m8.db.records('solo','automation_run') if r['id']==run['id'])
    assert result['data']['state']=='awaiting_review' and not m8.transport.calls
