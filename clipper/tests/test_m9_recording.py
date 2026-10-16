"""Authored FFmpeg streams, durable receipts and real application boundaries.

This is not a native browser/device sync, real speech or remote network test.
"""
import copy
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from clipper.api_studio import create_router
from clipper.api_m8 import install_security
from clipper.m8_contract import AccessDenied
from clipper.studio_worker import execute
from clipper.dependency_cache import content_id
from ._m4_fixture import make_studio


@pytest.fixture
def studio(tmp_path):
    service=make_studio(tmp_path);clock=[10000.];service.integrations.db.clock=lambda:clock[0]
    service.test_clock=clock
    try:yield service
    finally:service.integrations.close();service.queue.close()


def make_recording(service,room=False):
    lab=service.lab;actor=lab.m8.local_actor();record=lab.recording.create(actor,{'name':'Capture authored','mode':'room' if room else 'local','consent':True})
    return lab,actor,record


def chunk_stream(lab,actor,record,kind,path,participant='host',offset=0):
    mime='audio/webm' if kind=='microphone' else 'video/webm'
    track=lab.recording.add_track(actor,{'id':record['id'],'kind':kind,'mime':mime,'started_at':record['data']['clock_origin']+offset,'clock_uncertainty_ms':5,'consent':True},participant)
    raw=path.read_bytes();pieces=[raw[:len(raw)//3],raw[len(raw)//3:2*len(raw)//3],raw[2*len(raw)//3:]]
    for seq,part in enumerate(pieces):lab.recording.chunk(actor,track['id'],seq,part,hashlib.sha256(part).hexdigest(),(seq+1)*1.3,participant)
    lab.recording.seal(actor,{'track_id':track['id'],'expected_chunks':len(pieces)},participant if participant!='host' else None)
    return lab.recording.track(actor,track['id'])


def capture_files(service,tmp_path):
    video=tmp_path/'capture-video.webm';audio=tmp_path/'capture-audio.webm';source=service.store.get(service.test_pid)['source']['path']
    subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-i',source,'-an','-c:v','libvpx','-threads','2',str(video)],check=True,capture_output=True)
    subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-i',source,'-vn','-c:a','libopus',str(audio)],check=True,capture_output=True)
    return video,audio


def test_durable_out_of_order_duplicate_conflict_and_restart(studio,tmp_path):
    lab,actor,record=make_recording(studio);track=lab.recording.add_track(actor,{'id':record['id'],'kind':'microphone','mime':'audio/webm','started_at':10000.,'consent':True})
    sha=lambda b:hashlib.sha256(b).hexdigest()
    assert lab.recording.chunk(actor,track['id'],1,b'chunk1',sha(b'chunk1'),2)['durable']
    with pytest.raises(ValueError,match='belum lengkap'):lab.recording.seal(actor,{'track_id':track['id'],'expected_chunks':2})
    lab.recording.chunk(actor,track['id'],0,b'chunk0',sha(b'chunk0'),1)
    assert lab.recording.chunk(actor,track['id'],0,b'chunk0',sha(b'chunk0'),1)['duplicate']
    with pytest.raises(ValueError):lab.recording.chunk(actor,track['id'],0,b'changed',sha(b'changed'),1)
    from clipper.studio_service import StudioService
    restarted=StudioService(studio.root,studio.base,autostart=False,recover=False)
    restarted.integrations.db.clock=lambda:10000.
    try:
        assert len(restarted.lab.recording.track(restarted.integrations.local_actor(),track['id'])['chunks'])==2
        restarted.lab.recording.seal(restarted.integrations.local_actor(),{'track_id':track['id'],'expected_chunks':2})
    finally:restarted.queue.close();restarted.integrations.close()
    with pytest.raises(ValueError,match='ditutup'):lab.recording.chunk(actor,track['id'],2,b'late',sha(b'late'),3)


def test_recover_prefix_is_explicit_and_host_only(studio):
    lab,actor,record=make_recording(studio,True);invite=lab.recording.invite(actor,{'id':record['id'],'name':'Guest'})
    token=invite['join_fragment'].split('token=')[1];g=lab.recording.guest(token,record['id']);track=lab.recording.add_track(g['actor'],{'id':record['id'],'kind':'microphone','mime':'audio/webm','started_at':10000.,'consent':True},g['participant'])
    for seq in (0,2):lab.recording.chunk(g['actor'],track['id'],seq,b'x'+bytes([seq]),hashlib.sha256(b'x'+bytes([seq])).hexdigest(),seq+1,g['participant'])
    with pytest.raises(AccessDenied):lab.recording.seal(g['actor'],{'track_id':track['id'],'expected_chunks':1,'recover_prefix':True},g['participant'])
    result=lab.recording.seal(actor,{'track_id':track['id'],'expected_chunks':1,'recover_prefix':True})
    assert result['data']['recovered_prefix'] and result['data']['expected_chunks']==1


def test_guest_capability_never_grants_workspace_or_foreign_tracks(studio):
    lab,actor,record=make_recording(studio,True);invite=lab.recording.invite(actor,{'id':record['id'],'name':'Guest'})
    token=invite['join_fragment'].split('token=')[1]
    app=FastAPI();app.include_router(create_router(studio));install_security(app,studio)
    client=TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',50000));headers={'Authorization':'Bearer '+token}
    base='/api/studio/m9/guest/'+record['id'];assert client.get(base+'/clock',headers=headers).status_code==200
    assert client.post('/api/studio/m8/v1/command',headers=headers,json={'schema_version':1,'action':'project.list','args':{}}).status_code==403
    host=lab.recording.add_track(actor,{'id':record['id'],'kind':'microphone','mime':'audio/webm','started_at':10000.,'consent':True})
    assert client.get(base+'/tracks/'+host['id'],headers=headers).status_code==403
    guest=client.post(base+'/tracks',headers=headers,json={'id':record['id'],'kind':'microphone','mime':'audio/webm','started_at':10000.,'consent':True});assert guest.status_code==200,guest.text
    raw=b'guest fixture';upload=client.put(base+'/tracks/'+guest.json()['id']+'/chunks/0',headers={**headers,'X-Chunk-SHA256':hashlib.sha256(raw).hexdigest(),'X-Elapsed-Seconds':'1'},content=raw);assert upload.json()['durable']
    assert client.get(base+'/clock',headers={**headers,'Origin':'https://foreign.test'}).status_code==403
    lab.recording.revoke(actor,{'id':record['id'],'participant':invite['participant']})
    assert client.get(base+'/clock',headers=headers).status_code==403
    with studio.store.connect() as db:
        for table,col in [('m9_invites','token_hash'),('m9_items','data'),('m8_events','data')]:assert token not in '\n'.join(str(r[col]) for r in db.execute('SELECT '+col+' FROM '+table))


def test_actual_capture_fragments_to_editor_podcast_and_exact_cut(studio,tmp_path):
    lab,actor,record=make_recording(studio);video,audio=capture_files(studio,tmp_path)
    visual=chunk_stream(lab,actor,record,'screen',video);microphone=chunk_stream(lab,actor,record,'microphone',audio)
    studio.test_clock[0]=10004.1;current=lab.store.get(actor,record['id'])
    finalized=lab.recording.finalize(actor,{'id':record['id'],'expected_version':current['version'],'primary_track':visual['id'],'sync_reviewed':True})
    job=studio.queue.get(finalized['data']['jobs'][-1]);result=execute(studio,job);assert studio.queue.get(job['id'])['status']=='completed'
    ready=lab.recording.view(actor,record['id']);assert ready['data']['status']=='ready'
    project=studio.store.get(result['project_id']);assert project['source']['lineage']['kind']=='recording9'
    assert project['source']['info']['duration']>=3.9 and len(project['source']['info']['audio_tracks'])==1
    with zipfile.ZipFile(ready['data']['archive_path']) as archive:
        assert archive.testzip() is None;manifest=json.loads(archive.read('recording9.json'));assert len(manifest['tracks'])==2
        assert all(t['artifact']['content_id'] for t in manifest['tracks'])
    podcast=lab.delivery.podcast(actor,{'project_id':project['project_id'],'expected_revision':project['revision'],'chapters':[{'start':0,'title':'Authored'}],'notes':'Catatan buatan pengujian'})
    packaged=execute(studio,podcast)
    with zipfile.ZipFile(packaged['archive_path']) as archive:assert 'episode.wav' in archive.namelist() and any(n.startswith('stem-') for n in archive.namelist())
    cut=lab.delivery.buffer(actor,{'id':record['id'],'start':1.,'end':3.,'name':'Potongan 2 detik'});derived=execute(studio,cut)
    assert abs(studio.store.get(derived['project_id'])['source']['info']['duration']-2)<.15
    assert content_id(project['source']['path'],fresh=True)==project['source']['source_id']
    import os,shutil
    if os.environ.get('CLIPPER_M9_EVIDENCE'):
        folder=Path(os.environ['CLIPPER_M9_EVIDENCE']);folder.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ready['data']['archive_path'],folder/'DEMO_BUATAN_M9_Rekaman.zip');shutil.copy2(packaged['archive_path'],folder/'DEMO_BUATAN_M9_Podcast.zip')
        (folder/'backend-e2e.json').write_text(json.dumps({'scope':'authored color/tone media; actual FFmpeg/SQLite/core editor integration; no native device/neural/live quality claim',
            'recording_program_content_id':project['source']['source_id'],'recording_manifest':json.loads(Path(ready['data']['manifest_path']).read_text()),
            'podcast_content_id':packaged['content_id'],'recording_cut_content_id':derived['content_id'],'external_posts_or_broadcasts':0},indent=2)+'\n')


def test_closed_room_rejects_new_track_and_unknown_sequences(studio):
    lab,actor,record=make_recording(studio);sha=lambda b:hashlib.sha256(b).hexdigest()
    with pytest.raises(ValueError):lab.recording.add_track(actor,{'id':record['id'],'kind':'screen','mime':'text/html','started_at':10000.,'consent':True})
    t=lab.recording.add_track(actor,{'id':record['id'],'kind':'microphone','mime':'audio/webm','started_at':10000.,'consent':True})
    with pytest.raises(ValueError):lab.recording.chunk(actor,t['id'],True,b'a',sha(b'a'),1)
    with pytest.raises(ValueError):lab.recording.chunk(actor,t['id'],0,b'a',sha(b'wrong'),1)
    lab.recording.chunk(actor,t['id'],1,b'b',sha(b'b'),2)
    with pytest.raises(ValueError,match='Jam chunk'):lab.recording.chunk(actor,t['id'],0,b'a',sha(b'a'),3)


def test_actual_supervised_recording_worker_without_existing_project(studio,tmp_path):
    import time
    lab,actor,record=make_recording(studio);video,audio=capture_files(studio,tmp_path)
    visual=chunk_stream(lab,actor,record,'screen',video);chunk_stream(lab,actor,record,'microphone',audio)
    studio.test_clock[0]=10004.1;row=lab.store.get(actor,record['id'])
    submitted=lab.recording.finalize(actor,{'id':row['id'],'expected_version':row['version'],'primary_track':visual['id'],'sync_reviewed':True})
    jobid=submitted['data']['jobs'][-1];studio.queue.autostart=True;studio.queue.start();deadline=time.monotonic()+35
    while time.monotonic()<deadline:
        job=studio.queue.get(jobid)
        if job['status'] not in ('queued','running','cancel_requested'):break
        time.sleep(.1)
    assert job['status']=='completed',job
    project=studio.store.get(job['result']['project_id'])
    assert Path(project['source']['path']).is_file() and project['settings']['out_dir']==studio.base.out_dir


def test_backstage_audio_excluded_until_explicit_stage_and_slides_panel(studio,tmp_path):
    import numpy as np
    lab,actor,record=make_recording(studio,True);video,audio=capture_files(studio,tmp_path)
    visual=chunk_stream(lab,actor,record,'screen',video);camera=chunk_stream(lab,actor,record,'camera',video);chunk_stream(lab,actor,record,'microphone',audio)
    invite=lab.recording.invite(actor,{'id':record['id'],'name':'Guest tone'});guest_file=tmp_path/'guest.webm'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=2000:sample_rate=48000:duration=4','-c:a','libopus',str(guest_file)],check=True,capture_output=True)
    chunk_stream(lab,actor,record,'microphone',guest_file,invite['participant'])
    studio.test_clock[0]=10001.;r=lab.store.get(actor,record['id']);lab.recording.stage(actor,{'id':r['id'],'expected_version':r['version'],'participant':invite['participant'],'onstage':True})
    studio.test_clock[0]=10002.;r=lab.store.get(actor,record['id']);lab.recording.stage(actor,{'id':r['id'],'expected_version':r['version'],'participant':invite['participant'],'onstage':False})
    studio.test_clock[0]=10004.1;r=lab.store.get(actor,record['id']);submitted=lab.recording.finalize(actor,{'id':r['id'],'expected_version':r['version'],'primary_track':visual['id'],'camera_track':camera['id'],'sync_reviewed':True})
    result=execute(studio,studio.queue.get(submitted['data']['jobs'][-1]));doc=studio.store.get(result['project_id']);assert doc['source']['info']['display_size']==[320,180]
    raw=subprocess.run(['ffmpeg','-v','error','-i',doc['source']['path'],'-vn','-ac','1','-ar','48000','-f','f32le','pipe:1'],check=True,capture_output=True).stdout
    samples=np.frombuffer(raw,dtype='<f4')
    def amplitude(a,b):
        values=samples[int(a*48000):int(b*48000)];time=np.arange(len(values))/48000
        return abs(np.sum(values*np.exp(-2j*np.pi*2000*time)))*2/len(values)
    assert amplitude(.2,.8)<.01 and amplitude(1.2,1.8)>.08 and amplitude(2.2,2.8)<.01
    manifest=json.loads(Path(result['manifest_path']).read_text());assert manifest['layout']['camera_track']==camera['id'] and manifest['layout']['preserve_slides']
