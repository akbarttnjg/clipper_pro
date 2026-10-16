"""Positive regressions for the nine confirmed 4.0.21 audit findings."""
from pathlib import Path
import hashlib, json, os, shutil, socket, time
import pytest
from clipper.tests._m4_fixture import make_studio
from clipper.tests.test_m9_creative_providers import local_fixture
from clipper.studio_worker import execute
from clipper.m8_contract import AccessDenied
from clipper.m8_workspace import Actor
from clipper.dependency_cache import content_id
from tools import complete_installer as installer

@pytest.fixture
def studio(tmp_path):
    service=make_studio(tmp_path)
    try: yield service
    finally: service.queue.close();service.integrations.close()


def test_A01_creative_rejects_source_file_changed_without_revision(studio,local_fixture):
    address,state=local_fixture;actor=studio.integrations.local_actor();pid=studio.test_pid
    doc=studio.store.get(pid)
    studio.store.mutate(pid,doc['revision'],'audit-ollama',{},lambda d:d['settings'].update(ollama_url=address,model='audit-http-fixture'))
    doc=studio.store.get(pid);source=Path(doc['source']['path']);old_id=doc['source']['source_id']
    # Legal MP4 trailing data changes exact source identity without changing project revision.
    with source.open('ab') as f:f.write(b'AUDIT-SOURCE-CHANGED')
    actual=content_id(source,fresh=True);assert actual!=old_id
    with pytest.raises(ValueError,match='Sumber berubah'):
        studio.lab.creative.generate(actor,{'project_id':pid,'expected_revision':doc['revision'],'mode':'summary','instruction':'Ringkas','language':'id'})
    assert studio.queue.list(pid)==[]


def test_A02_transfer_with_creative_is_atomic_and_rejected(studio):
    m8=studio.integrations;actor=m8.local_actor();doc=studio.store.get(studio.test_pid)
    item=studio.lab.creative.save(actor,{'name':'Audit notes','mode':'notes','text':'Catatan yang ditinjau.','language':'id','license':'Authored', 'project_id':doc['project_id'],'expected_revision':doc['revision']})
    destination=m8.workspaces.create(actor,{'name':'Destination audit'})
    with pytest.raises(ValueError,match='data M9'):
        m8.workspaces.organize(actor,{'project_id':doc['project_id'],'expected_version':0,'destination_workspace':destination['id']})
    assert studio.lab.store.get(actor,item['id'])['data']['text']=='Catatan yang ditinjau.'
    assert len(studio.lab.dispatch(actor,'m9.list',{})['items'])==1


def test_A03_preflight_rejects_claimed_core_job(studio,tmp_path):
    # Full release preflight against a clean source copy, real SQLite job and unexpired lease.
    repo=Path(installer.__file__).resolve().parents[1]
    if os.environ.get('CLIPPER_AUDIT_PACKAGE'):
        package=Path(os.environ['CLIPPER_AUDIT_PACKAGE'])
    else:
        from tools.build_audit_22_release import build
        package=tmp_path/'repair-package';build(package,'2'*40)
    from clipper.tests.test_m8_installer import restore_m7
    target=restore_m7(tmp_path/'machine')
    database=target/'work/studio4.sqlite3';database.parent.mkdir(exist_ok=True)
    job=studio.queue.enqueue(studio.test_pid,'waveform',{}, {'audit':'live core job'})
    claimed=studio.queue.claim(job['id']);assert claimed['lease_expires']>time.time()
    with studio.store.connect() as src:
        import sqlite3
        with sqlite3.connect(database) as dst:src.backup(dst)
    try:
        sock=socket.create_connection(('127.0.0.1',8765),timeout=.1);sock.close()
    except OSError:pass
    else:pytest.skip('port 8765 occupied: cannot isolate missing core job guard')
    with pytest.raises(ValueError,match='tugas inti'):
        installer.preflight(target,package,runtime=False,stopped=True)


def frequency(path):
    import subprocess, numpy as np
    raw=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-ar','4000','-ac','1','-f','f32le','pipe:1'],check=True,capture_output=True).stdout
    x=np.frombuffer(raw,dtype='<f4');return round(float(np.argmax(abs(np.fft.rfft(x)))*4000/len(x)),2)


def multi_source(studio,tmp_path):
    import subprocess
    path=tmp_path/'two-audios.mkv'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=s=320x180:r=30:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-f','lavfi','-i','sine=frequency=700:duration=2','-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-threads','2','-c:a','pcm_s16le',str(path)],check=True,capture_output=True)
    return studio.store.get(studio.create(path,{'audio_stream_index':2})['project_id'])


def test_A04_M9_derivative_supports_M2_source_origins_endpoint(studio):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from clipper.api_studio import create_router
    from clipper.api_m8 import install_security
    lab=studio.lab;actor=studio.integrations.local_actor();doc=studio.store.get(studio.test_pid)
    snap=lab.effects.prepare(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision'],'recipe':{'operations':[{'kind':'color'}],'material_reviewed':True},'end':1.})
    result=execute(studio,lab.enqueue(actor,'effects_m9',snap));pid=result['project_id']
    app=FastAPI();app.include_router(create_router(studio));install_security(app,studio)
    with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',1234)) as client:
        response=client.get('/api/studio/projects/'+pid+'/source-origins')
    assert response.status_code==200
    data=response.json();assert data['kind']=='effects9' and data['origins'][0]['project_id']==doc['project_id']
    assert data['origins'][0]['url'] is None
    assert isinstance(studio.transcripts.snapshot(pid)['source_lineage'],list)


def test_A05_effects_preserves_selected_audio(studio,tmp_path):
    doc=multi_source(studio,tmp_path);lab=studio.lab;actor=studio.integrations.local_actor()
    snap=lab.effects.prepare(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision'],'recipe':{'operations':[{'kind':'color'}],'material_reviewed':True}})
    result=execute(studio,lab.enqueue(actor,'effects_m9',snap));out=studio.store.get(result['project_id'])['source']['path']
    observed=frequency(out);assert abs(observed-700)<3 and doc['settings']['audio_stream_index']==2


def test_N01_assembly_CORRECTLY_preserves_selected_audio(studio,tmp_path):
    from clipper.source_assembly import assemble
    doc=multi_source(studio,tmp_path)
    result=assemble(studio,{'segments':[{'project_id':doc['project_id'],'revision':doc['revision'],'start':0,'end':2}]},tmp_path/'assembly')
    observed=frequency(result['path']);assert abs(observed-700)<3 and doc['settings']['audio_stream_index']==2


def test_A07_project_backup_roundtrips_attached_M9_creative(studio):
    import zipfile
    m8=studio.integrations;actor=m8.local_actor();doc=studio.store.get(studio.test_pid)
    item=studio.lab.creative.save(actor,{'name':'Only script','mode':'notes','text':'Catatan unik proyek.','language':'id','license':'Authored','project_id':doc['project_id'],'expected_revision':doc['revision']})
    backup=m8.backups.create(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision']})
    file_id=backup['url'].rsplit('/',1)[-1]
    with zipfile.ZipFile(m8.file(actor,file_id)) as z:
        snapshot=json.loads(z.read('snapshot.json'));assert len(snapshot['m9_items'])==1
        assert item['data']['text'] in z.read('snapshot.json').decode()
        assert json.loads(z.read('manifest.json'))['schema_version']==2
    restored=m8.backups.restore(actor,{'file_id':file_id})
    attached=[r for r in studio.lab.store.listing(actor,'creative') if r['data'].get('project_id')==restored['project_id']]
    assert len(attached)==1 and attached[0]['data']['text']==item['data']['text']
    assert attached[0]['data']['project_id']==restored['project_id']
    assert attached[0]['data']['source']['project_id']==restored['project_id']
    assert attached[0]['id']!=item['id'] and attached[0]['data']['status']=='requires_review'


def test_A08_effects_preserves_anamorphic_display_geometry(studio,tmp_path):
    import subprocess
    path=tmp_path/'wide-pixels.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=s=320x180:r=30:d=1','-f','lavfi','-i','sine=frequency=700:duration=1','-vf','setsar=2','-c:v','libx264','-threads','2','-c:a','aac',str(path)],check=True,capture_output=True)
    doc=studio.store.get(studio.create(path)['project_id']);lab=studio.lab;actor=studio.integrations.local_actor()
    assert doc['source']['info']['display_size']==[640,180]
    snap=lab.effects.prepare(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision'],'recipe':{'operations':[{'kind':'color'}],'material_reviewed':True}})
    result=execute(studio,lab.enqueue(actor,'effects_m9',snap));derived=studio.store.get(result['project_id'])
    assert derived['source']['info']['display_size']==[640,180]


def test_A09_member_cannot_expand_unapproved_foreign_brand_kit(studio,tmp_path):
    import copy
    from PIL import Image
    from clipper.finishing5_service import assets
    m8=studio.integrations;owner=m8.local_actor();private_doc=studio.store.get(studio.test_pid)
    path=tmp_path/'private-logo.png';Image.new('RGBA',(20,20),(255,0,0,255)).save(path)
    registry=assets(studio);asset=registry.register(path,{'name':'PRIVATE_OTHER_WORKSPACE_LOGO','permission':'user_owned','license':'Authored audit fixture','text':'Private customer identity'})
    layer={'id':'private-logo','kind':'logo','start':0.,'end':2.,'rect':[0,0,20,20],'asset_id':asset['id']}
    kit=registry.save_kit({'name':'PRIVATE_BRAND_IN_SOLO','style':{'base_hex':'#FFFFFF'},'layers':[layer]})
    # Bind the private kit to a project in solo, not to the destination project.
    studio.changes({'project_id':studio.test_pid,'clip_id':studio.test_cid,'variant_id':'portrait','expected_revision':private_doc['revision'],'operation_id':'audit-bind-private-kit','operations':[{'op':'m5_kit','kit_id':kit['id'],'kit_revision':0}]})
    destination=m8.workspaces.create(owner,{'name':'Other workspace'})
    doc=studio.create(private_doc['source']['path']);pid=doc['project_id']
    studio.store.mutate(pid,doc['revision'],'audit-seed-other-clip',{},lambda d:d.update(clips=copy.deepcopy(private_doc['clips'])))
    m8.workspaces.organize(owner,{'project_id':pid,'expected_version':0,'destination_workspace':destination['id']})
    dest_owner=Actor(destination['id'],owner.user_id,local=True)
    session=m8.workspaces.issue_session(dest_owner,{'user_id':'untrusted-editor','role':'editor','hours':1});member=m8.workspaces.authenticate(session['token'])
    with pytest.raises(AccessDenied):m8.workspaces.require(member,'read',studio.test_pid)
    doc=studio.store.get(pid);assert kit['id'] not in json.dumps(doc) and asset['id'] not in json.dumps(doc)
    with pytest.raises(AccessDenied):m8.scoped_inputs(member,pid,[{'op':'m5_layers','values':[layer]}])
    request={'schema_version':1,'command_id':'audit-expand-private-brand','action':'project.propose','args':{'project_id':pid,'clip_id':studio.test_cid,'variant_id':'portrait','expected_revision':doc['revision'],'operations':[{'op':'m5_kit','kit_id':kit['id'],'kit_revision':0}]}}
    with pytest.raises(AccessDenied,match='Aset belum'):
        m8.command(member,request)
    assert kit['id'] not in json.dumps(studio.store.get(pid))


def test_A10_requirement_entries_have_clean_target_and_acceptance():
    root=Path(installer.__file__).resolve().parents[1];bad=['IN02','TR01','EX01','RC09']
    for milestone in ('M1','M2'):
        rows={r['id']:r for r in json.loads((root/f'docs/{milestone}_REQUIREMENTS.json').read_text())['requirements']}
        assert all(row['target'].strip() and row['acceptance'].strip() for row in rows.values())
        for rid in bad:
            if rid in rows:assert 'Uji penerimaan.' not in rows[rid]['target'] and 'Baseline:' not in rows[rid]['target']
