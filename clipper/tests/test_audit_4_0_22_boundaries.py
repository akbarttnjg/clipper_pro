"""Adversarial boundaries and lifecycle round trips for the audit repairs."""
import ast
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
import pytest
from clipper.m8_contract import AccessDenied, canonical
from clipper.m8_workspace import Actor
from clipper.installation_lock import InstallationLease
from clipper.source_lineage import describe
from clipper.studio_worker import execute
from clipper.tests.test_audit_4_0_22 import studio, multi_source, frequency
from clipper.tests.test_m9_creative_providers import local_fixture
from tools import complete_installer as installer


def setup_creative(studio, address, mode='summary'):
    pid=studio.test_pid;doc=studio.store.get(pid)
    studio.store.mutate(pid,doc['revision'],'local-ollama',{},lambda d:d['settings'].update(ollama_url=address,model='authored-http-fixture'))
    doc=studio.store.get(pid)
    args={'project_id':pid,'expected_revision':doc['revision'],'mode':mode,'instruction':'Tinjau','language':'id'}
    if mode=='coeditor':args['clip_id']=studio.test_cid
    return studio.lab.creative.generate(studio.integrations.local_actor(),args)


@pytest.mark.parametrize('phase',['queued','response','draft_apply'])
def test_source_identity_rechecked_after_queue_HTTP_and_draft_review(studio,local_fixture,monkeypatch,phase):
    address,state=local_fixture
    if phase=='draft_apply':state['generated']={'text':'Tinjau subtitle.','references':[0],'operations':[{'op':'settings','values':{'caption_scale':1.1}}]}
    job=setup_creative(studio,address,'coeditor' if phase=='draft_apply' else 'summary')
    doc=studio.store.get(studio.test_pid);path=Path(doc['source']['path'])
    def change():
        with path.open('ab') as f:f.write(b'CHANGED-AFTER-REVIEW')
    if phase=='queued':
        change()
        with pytest.raises(ValueError,match='Sumber berubah'):execute(studio,job)
        assert not state['calls']
    elif phase=='response':
        import requests
        original=requests.Response.iter_content
        def changed(response,*args,**kwargs):
            yield from original(response,*args,**kwargs)
            change()
        monkeypatch.setattr(requests.Response,'iter_content',changed)
        with pytest.raises(ValueError,match='Sumber berubah'):execute(studio,job)
        assert not studio.lab.store.listing(studio.integrations.local_actor(),'creative')
    else:
        actor=studio.integrations.local_actor();item=execute(studio,job)['item_id']
        draft=studio.lab.creative.propose(actor,{'id':item,'expected_revision':doc['revision'],'clip_id':studio.test_cid},'audit-review')
        change()
        with pytest.raises(ValueError,match='Sumber berubah'):
            studio.integrations.command(actor,{'schema_version':1,'command_id':'audit-apply','action':'project.apply','args':{
                'project_id':studio.test_pid,'expected_revision':doc['revision'],'draft_id':draft['id']}})
        assert studio.store.get(studio.test_pid)['revision']==doc['revision']


def test_legacy_orphan_listing_stays_usable_and_scope_can_be_returned(studio):
    m8=studio.integrations;actor=m8.local_actor();pid=studio.test_pid;doc=studio.store.get(pid)
    item=studio.lab.creative.save(actor,{'name':'Legacy note','mode':'notes','text':'Keep this evidence.','language':'id','license':'Authored',
        'project_id':pid,'expected_revision':doc['revision']})
    destination=m8.workspaces.create(actor,{'name':'Legacy moved workspace'})
    with m8.db.transaction() as db:db.execute('UPDATE m8_projects SET workspace=?,version=1 WHERE project_id=?',(destination['id'],pid))
    assert studio.lab.store.listing(actor)==[]
    target=Actor(destination['id'],actor.user_id,local=True)
    result=m8.workspaces.organize(target,{'project_id':pid,'expected_version':1,'destination_workspace':actor.workspace})
    assert result['workspace']==actor.workspace
    assert studio.lab.store.get(actor,item['id'])['data']['text']=='Keep this evidence.'


@pytest.mark.parametrize('phase',['submit','queued','synthesizing'])
def test_project_bound_TTS_never_publishes_against_changed_source(studio,monkeypatch,phase):
    from clipper.m9_contract import sha
    import wave
    actor=studio.integrations.local_actor();lab=studio.lab;doc=studio.store.get(studio.test_pid)
    script=lab.creative.save(actor,{'name':'Reviewed narration','mode':'script','text':'Catat biaya usaha.','language':'id','license':'Authored',
        'project_id':studio.test_pid,'expected_revision':doc['revision']})
    voice=lab.store.create(actor,'voice',{'language':'id_ID','model_content_id':'sha256:fixture','license':'Authored fixture','permission':'licensed'})
    args={'id':script['id'],'expected_version':0,'voice_id':voice['id'],'text_sha256':sha(script['data']['text'].encode()),'reviewed':True}
    def change():
        with Path(doc['source']['path']).open('ab') as f:f.write(b'CHANGED-TTS-SOURCE')
    if phase=='submit':
        change()
        with pytest.raises(ValueError,match='Sumber berubah'):lab.providers.tts_submit(actor,args)
        return
    job=lab.providers.tts_submit(actor,args);before=len(studio.store.list())
    monkeypatch.setattr(lab.providers,'verify_voice',lambda voice:None)
    def synthesize(job,voice,text,out,limit):
        with wave.open(str(out),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(48000);w.writeframes(b'\0\0'*48000)
        change()
        return {}
    monkeypatch.setattr(lab.providers,'synthesize',synthesize)
    if phase=='queued':change()
    with pytest.raises(ValueError,match='Sumber berubah'):execute(studio,job)
    assert len(studio.store.list())==before


def test_member_can_use_approved_kit_but_cannot_apply_unapproved_saved_draft(studio):
    from clipper.finishing5_service import assets
    from clipper.editor_service import make_draft
    actor=studio.integrations.local_actor();m8=studio.integrations;pid=studio.test_pid;cid=studio.test_cid
    kit=assets(studio).save_kit({'name':'Approved brand','style':{'base_hex':'#FFFFFF'},'layers':[]})
    doc=studio.store.get(pid)
    studio.changes({'project_id':pid,'clip_id':cid,'expected_revision':doc['revision'],'operation_id':'approve-kit',
        'operations':[{'op':'m5_kit','kit_id':kit['id'],'kit_revision':0}]})
    session=m8.workspaces.issue_session(actor,{'user_id':'editor-audit','role':'editor','hours':1});member=m8.workspaces.authenticate(session['token'])
    doc=studio.store.get(pid)
    m8.scoped_inputs(member,pid,[{'op':'m5_kit','kit_id':kit['id'],'kit_revision':0}])
    other=assets(studio).save_kit({'name':'Private foreign brand','style':{'base_hex':'#111111'},'layers':[]})
    draft=make_draft(studio,{'project_id':pid,'clip_id':cid,'expected_revision':doc['revision'],'operation_id':'legacy-private-draft',
        'operations':[{'op':'m5_kit','kit_id':other['id'],'kit_revision':0}]})
    with pytest.raises(AccessDenied):m8.command(member,{'schema_version':1,'command_id':'apply-private-draft','action':'project.apply',
        'args':{'project_id':pid,'expected_revision':doc['revision'],'draft_id':draft['id']}})
    with pytest.raises(AccessDenied):m8.scoped_inputs(member,pid,[{'op':'settings','values':{'font_main':'font-private-unapproved'}}])


def test_selected_audio_remains_valid_for_next_analysis(studio,tmp_path):
    doc=multi_source(studio,tmp_path);lab=studio.lab;actor=studio.integrations.local_actor()
    snap=lab.effects.prepare(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision'],
        'recipe':{'operations':[{'kind':'color'}],'material_reviewed':True}})
    result=execute(studio,lab.enqueue(actor,'effects_m9',snap));derived=studio.store.get(result['project_id'])
    assert derived['settings']['audio_stream_index']==-1
    from clipper.media_context import prepare
    assert prepare(derived['source']['path'],studio.config(derived))['payload']['selected_audio_index']==1
    assert abs(frequency(derived['source']['path'])-700)<3


@pytest.mark.parametrize('sar,rotation,size',[('1/2',0,[160,180]),('1/1',90,[180,320]),('1/1',270,[180,320])])
def test_display_geometry_is_canonical_before_effect_coordinates(studio,tmp_path,sar,rotation,size):
    path=tmp_path/'geometry.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=320x180:r=30:d=1',
        '-f','lavfi','-i','sine=frequency=700:duration=1','-vf','setsar='+sar,'-c:v','libx264','-threads','2','-c:a','aac',str(path)],check=True,capture_output=True)
    if rotation:
        rotated=tmp_path/'rotated.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-display_rotation',str(rotation),'-i',str(path),'-c','copy',str(rotated)],check=True,capture_output=True)
        path=rotated
    doc=studio.store.get(studio.create(path)['project_id']);actor=studio.integrations.local_actor()
    assert doc['source']['info']['display_size']==size
    snapshot=studio.lab.effects.prepare(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision'],
        'recipe':{'operations':[{'kind':'blur','rect':[0,0,40,40],'ranges':[[0,.8]],'strength':3}],'material_reviewed':True}})
    result=execute(studio,studio.lab.enqueue(actor,'effects_m9',snapshot))
    assert studio.store.get(result['project_id'])['source']['info']['display_size']==size


def test_backup_records_evidence_without_replaying_capture_or_invites(studio,tmp_path):
    lab=studio.lab;m8=studio.integrations;actor=m8.local_actor();pid=studio.test_pid;doc=studio.store.get(pid)
    root=lab.root/'recordings'/'old-record';root.mkdir(parents=True)
    raw=root/'original.chunk';raw.write_bytes(b'isolated recording evidence')
    record=lab.store.create(actor,'recording',{'name':'Evidence','project_id':pid,'status':'ready','program_path':doc['source']['path']},'old-record')
    with m8.db.transaction() as db:
        db.execute('INSERT INTO m9_tracks VALUES(?,?,?,?,?,0,?)',('old-track',record['id'],'host','microphone','audio/webm',canonical({'status':'sealed'})))
        db.execute('INSERT INTO m9_chunks VALUES(?,?,?,?,?)',('old-track',0,'fixture-hash',raw.stat().st_size,'{}'))
        db.execute('INSERT INTO m9_invites VALUES(?,?,?,?,?,0)',('invite',record['id'],'guest','SECRET-HASH',99999999))
    backup=m8.backups.create(actor,{'project_id':pid,'expected_revision':doc['revision']});file_id=backup['url'].rsplit('/',1)[-1]
    with zipfile.ZipFile(m8.file(actor,file_id)) as z:
        body=z.read('snapshot.json');snap=json.loads(body)
        assert b'SECRET-HASH' not in body
        assert len(snap['m9_evidence'][record['id']]['tracks'])==1
        assert any(z.read(n)==raw.read_bytes() for n in z.namelist() if n.endswith('original.chunk'))
    restored=m8.backups.restore(actor,{'file_id':file_id})
    rows=[r for r in lab.store.listing(actor) if r['data'].get('project_id')==restored['project_id']]
    assert len(rows)==1 and rows[0]['kind']=='restored_evidence'
    with pytest.raises(ValueError,match='sebagai bukti'):lab.store.get(actor,rows[0]['id'],'edit')
    with studio.store.connect() as db:
        assert db.execute('SELECT count(*) FROM m9_invites').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM m9_tracks').fetchone()[0]==1


def test_backup_rejects_active_jobs_and_concurrent_M9_change(studio,monkeypatch):
    lab=studio.lab;m8=studio.integrations;actor=m8.local_actor();doc=studio.store.get(studio.test_pid)
    note=lab.creative.save(actor,{'name':'Note','mode':'notes','text':'Preserve','language':'id','license':'Authored',
        'project_id':studio.test_pid,'expected_revision':doc['revision']})
    job=lab.enqueue(actor,'creative_m9',{'project_id':studio.test_pid})
    with pytest.raises(ValueError,match='tugas M9'):m8.backups.create(actor,{'project_id':studio.test_pid,'expected_revision':doc['revision']})
    studio.queue.cancel(job['id'])
    original=zipfile.ZipFile.write
    def changed(archive,*args,**kwargs):
        result=original(archive,*args,**kwargs)
        with studio.store.connect() as db:db.execute('UPDATE m9_items SET version=version+1 WHERE id=?',(note['id'],))
        return result
    monkeypatch.setattr(zipfile.ZipFile,'write',changed)
    with pytest.raises(ValueError,match='Data M9 berubah'):m8.backups.create(actor,{'project_id':studio.test_pid,'expected_revision':doc['revision']})
    assert not list((studio.work/'m8-backups').rglob('Clipper_M8_Backup.zip'))


@pytest.mark.parametrize('table',['jobs','m2_imports'])
def test_installer_blocks_running_or_cancel_requested_tasks(tmp_path,table):
    import sqlite3
    path=tmp_path/'studio4.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE '+table+'(status TEXT)');db.execute('INSERT INTO '+table+" VALUES('cancel_requested')")
    with pytest.raises(ValueError,match='tugas inti'):installer.require_m8_stopped(path)


def test_OS_lease_excludes_installers_and_releases_after_process_exit(tmp_path):
    with InstallationLease(tmp_path):
        with InstallationLease(tmp_path):pass
        with pytest.raises(ValueError,match='sedang dipakai'):installer.InstallationLease(tmp_path,exclusive=True)
    script='from clipper.installation_lock import InstallationLease;import sys;lock=InstallationLease(sys.argv[1]);print("READY",flush=True);sys.stdin.read()'
    child=subprocess.Popen([sys.executable,'-c',script,str(tmp_path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        assert child.stdout.readline().strip()=='READY'
        with pytest.raises(ValueError):installer.InstallationLease(tmp_path,exclusive=True)
    finally:
        child.communicate('',timeout=10)
    with installer.InstallationLease(tmp_path,exclusive=True):pass


@pytest.mark.skipif(os.name=='nt',reason='Windows process enumeration needs Windows acceptance')
def test_first_upgrade_detects_uncooperative_legacy_Python_process(tmp_path):
    script='import sys;print("READY",flush=True);sys.stdin.read()'
    child=subprocess.Popen([sys.executable,'-c',script],cwd=tmp_path,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        assert child.stdout.readline().strip()=='READY'
        with pytest.raises(ValueError,match='server/worker'):installer.require_processes_stopped(tmp_path)
    finally:child.communicate('',timeout=10)
    installer.require_processes_stopped(tmp_path)


def test_standalone_installer_lease_has_same_implementation():
    import inspect
    assert ast.dump(ast.parse(inspect.getsource(InstallationLease)))==ast.dump(ast.parse(inspect.getsource(installer.InstallationLease)))


@pytest.mark.parametrize('lineage',[[],[{'project_id':'p','start':0,'end':1,'source_path':'source'}],
    {'kind':'effects9','parent_project_id':'p','source_range':[0,1]},
    {'kind':'synthetic_tts9','source':{'project_id':'p','source_content_id':'sha256:x'}},
    {'kind':'recording9'},{'kind':'dubbing9','parent_project_id':'p'},
    {'kind':'recording_cut9','source_project':'p','source_content_id':'sha256:x','range':[3,6]}])
def test_all_lineage_shapes_produce_typed_origins(lineage):
    result=describe({'lineage':lineage})
    assert isinstance(result['origins'],list) and isinstance(result['provenance'],dict)
    if isinstance(lineage,dict):assert all(r['url'] is None for r in result['origins'])
    if isinstance(lineage,dict) and lineage.get('kind')=='recording_cut9':
        assert result['origins'][0]['project_id']=='p' and result['origins'][0]['start']==3
