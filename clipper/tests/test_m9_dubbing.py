"""Actual authored CLI/FFmpeg PCM evidence; never neural speech-quality proof."""
import copy
import json
import os
import sys
import threading
import time
import zipfile
from pathlib import Path
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from clipper.api_studio import create_router
from clipper.api_m8 import install_security
from clipper.dependency_cache import content_id
from clipper.m8_contract import AccessDenied, canonical
from clipper.m8_workspace import Actor
from clipper.m9_contract import sha
from clipper.m9_dubbing import pcm, srt_time
from clipper.project_store import Conflict, JobLeaseLost
from clipper.studio_worker import execute
from clipper.transcript_tracks import cues_from_words
from ._m4_fixture import make_studio


@pytest.fixture
def studio(tmp_path):
    service = make_studio(tmp_path)
    try: yield service
    finally: service.queue.close(); service.integrations.close()


def seed(service, tmp_path, seconds=.6, sleep_seconds=0):
    actor = service.integrations.local_actor(); pid = service.test_pid; doc = service.store.get(pid)
    words = [{'word_id':0,'word':'Andi tidak membayar 50 rupiah.','start':.2,'end':1.7,'speaker_id':'A','probability':None},
             {'word_id':1,'word':'Sari menyimpan 20 bukti.','start':2.2,'end':3.7,'speaker_id':'B','probability':None}]
    take = service.store.save_transcript(pid, {'words':words,'raw_words':words,'duration':4.,'language':'id'})
    def change(d): d.update(transcript_id=take,transcript_revision=2); d['settings']['glossary']='Andi, Sari, rupiah'
    service.store.mutate(pid,doc['revision'],'dubbing-authored-transcript',{},change);doc=service.store.get(pid)
    rows = [{'cue_id':c['cue_id'],'text':t} for c,t in zip(cues_from_words(words),['Andi does not pay 50 rupiah.','Sari saves 20 receipts.'])]
    draft = service.transcripts.translation_review(pid,{'expected_revision':doc['revision'],'target_language':'en','provider':'manual','cues':rows})
    result=service.transcripts.commit_translation(pid,{'expected_revision':doc['revision'],'draft_id':draft['draft_id'],'digest':draft['digest'],
        'operation_id':'approve-dubbing-fixture-translation','all_cues_reviewed':True,'critical_cue_ids':[c['cue_id'] for c in draft['critical_cues']]})
    executable=tmp_path/'authored-piper-transport'
    executable.write_text('#!'+sys.executable+'\nimport sys,wave,math,struct,json,time\nfrom pathlib import Path\na=sys.argv;t=sys.stdin.read();cfg=json.loads(Path(a[a.index("--config")+1]).read_text());d=cfg["fixture_seconds"];f=880 if "50" in t else 1320\nPath(a[a.index("--output_file")+1]+".started").write_text("authored CLI started")\ntime.sleep(cfg.get("sleep_seconds",0))\nwith wave.open(a[a.index("--output_file")+1],"wb") as w:\n w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b"".join(struct.pack("<h",int(6000*math.sin(2*math.pi*f*i/24000))) for i in range(round(d*24000))))\n')
    executable.chmod(0o700);model=tmp_path/'authored.onnx';model.write_bytes(b'NOT A NEURAL MODEL')
    config=tmp_path/'authored.onnx.json';config.write_text(json.dumps({'language':{'code':'en_US'},'fixture_seconds':seconds,'sleep_seconds':sleep_seconds}))
    voice=service.lab.providers.voice_register(actor,{'name':'Authored tone protocol fixture','executable':str(executable),'model_path':str(model),'config_path':str(config),
        'language':'en_US','license':'Authored CLI fixture; NOT voice quality evidence','permission':'own'})
    doc=service.store.get(pid)
    args={'project_id':pid,'expected_revision':doc['revision'],'clip_id':service.test_cid,'track_id':result['track_id'],'voice_id':voice['id']}
    return actor,args,voice


def reviewed(lab,actor,args):
    plan=lab.dubbing.plan(actor,args)
    return {**args,'plan_digest':plan['plan_digest'],'reviewed_cue_ids':[c['cue_id'] for c in plan['cues']],'facts_reviewed':True,'rights_reviewed':True}


def accepted(item):
    return {'id':item['id'],'expected_version':item['version'],'output_content_id':item['data']['output']['content_id'],
            'listened':True,'timing_reviewed':True,'facts_reviewed':True}


def candidate(service, tmp_path):
    actor,args,voice=seed(service,tmp_path);lab=service.lab
    result=execute(service,lab.dubbing.submit(actor,reviewed(lab,actor,args)))
    return actor,args,lab.store.get(actor,result['item_id'])


@pytest.mark.skipif(os.name=='nt',reason='POSIX authored executable; actual Windows Piper acceptance separate')
def test_actual_dubbing_PCM_clock_AB_archive_and_acceptance(studio,tmp_path):
    actor,args,voice=seed(studio,tmp_path);lab=studio.lab;before=studio.store.get(studio.test_pid);source=Path(before['source']['path']).read_bytes()
    plan=lab.dubbing.plan(actor,args);assert len(plan['cues'])==2 and plan['glossary']=='Andi, Sari, rupiah'
    result=execute(studio,lab.dubbing.submit(actor,reviewed(lab,actor,args)));item=lab.store.get(actor,result['item_id']);value=item['data']
    assert result['editor_project_created'] is False and value['status']=='awaiting_listening'
    assert len(studio.store.list())==1 and studio.store.get(studio.test_pid)==before
    samples=pcm(value['dubbed_path']);assert len(samples)==4*48000
    assert np.max(np.abs(samples[:round(.2*48000)]))==0
    assert np.max(np.abs(samples[round(1.7*48000):round(2.2*48000)]))==0
    for start,frequency in [(.2,880),(2.2,1320)]:
        segment=samples[round((start+.05)*48000):round((start+.45)*48000)].astype(float)
        peak=np.fft.rfftfreq(len(segment),1/48000)[np.argmax(np.abs(np.fft.rfft(segment)))];assert abs(peak-frequency)<5
    manifest=json.loads(Path(value['manifest_path']).read_text());assert all(c['truncated_samples']==0 for c in manifest['measurements'])
    assert manifest['plan']['speaker_policy']=='one_explicit_voice_for_all_cues'
    with zipfile.ZipFile(value['archive_path']) as z:
        assert z.testzip() is None and {'original.wav','dubbed.wav','translated-cues.srt','dubbing9.json'}<=set(z.namelist())
        for member in manifest['members']:assert 'sha256:'+sha(z.read(member['name']))==member['content_id']
        assert b'00:00:00,200 --> 00:00:01,700' in z.read('translated-cues.srt')
    public=lab.public_item(actor,item);assert public['data']['original_url'] and 'original_path' not in public['data']
    accept_job=lab.dubbing.accept(actor,accepted(item));new=execute(studio,accept_job);project=studio.store.get(new['project_id'])
    assert project['source']['lineage']['kind']=='synthetic_dubbing9' and not project.get('transcript_id')
    assert project['source']['lineage']['source']['project_id']==before['project_id']
    assert not project['settings']['punch_zoom'] and not project['settings']['cold_open']
    assert studio.store.get(before['project_id'])==before and Path(before['source']['path']).read_bytes()==source
    with pytest.raises(ValueError):lab.dubbing.accept(actor,accepted(item))


@pytest.mark.parametrize('bad',[
    {'facts_reviewed':False},{'rights_reviewed':False},{'reviewed_cue_ids':[]},{'reviewed_cue_ids':['1','1','2']},
    {'reviewed_cue_ids':[1,2]},{'plan_digest':'0'*64},{'max_rate':1.26},{'max_rate':float('nan')},{'shell':'x'},
])
def test_exact_review_rate_and_schema_before_enqueue(studio,tmp_path,bad):
    actor,args,_=seed(studio,tmp_path);data=reviewed(studio.lab,actor,args);data.update(bad)
    with pytest.raises(ValueError):studio.lab.dubbing.submit(actor,data)
    assert not studio.queue.list(studio.test_pid)


@pytest.mark.parametrize('fault',['unapproved','transcript','track_identity','language','partial_cue','source','voice_file','revision'])
def test_stale_or_unapproved_inputs_are_rejected(studio,tmp_path,fault):
    actor,args,voice=seed(studio,tmp_path);lab=studio.lab;data=reviewed(lab,actor,args);doc=studio.store.get(studio.test_pid)
    def change(d):
        track=d['translation_tracks'][args['track_id']]
        if fault=='unapproved':track['approved']=False
        if fault=='transcript':d['transcript_revision']+=1
        if fault=='partial_cue':d['clips'][args['clip_id']]['end']=1.
        if fault=='revision':d['name']='New revision'
    if fault in ('unapproved','transcript','partial_cue','revision'):
        studio.store.mutate(doc['project_id'],doc['revision'],'dubbing-change-'+fault,{},change)
        data['expected_revision']=studio.store.get(doc['project_id'])['revision']
    elif fault in ('track_identity','language'):
        track=studio.store.transcript(args['track_id']);track['source_id']='sha256:'+'0'*64 if fault=='track_identity' else track['source_id']
        if fault=='language':track['language']='id'
        with studio.store.connect() as db:db.execute('UPDATE transcripts SET metadata=? WHERE id=?',(canonical(track),args['track_id']))
    elif fault=='source':Path(doc['source']['path']).write_bytes(b'changed source')
    elif fault=='voice_file':Path(voice['data']['model_path']).write_bytes(b'changed model')
    with pytest.raises((ValueError,Conflict)):lab.dubbing.submit(actor,data)
    assert not studio.queue.list(studio.test_pid)


@pytest.mark.skipif(os.name=='nt',reason='POSIX CLI fixture')
@pytest.mark.parametrize('fault',['long','cancel','revision','voice_file','voice_version'])
def test_render_refuses_truncation_cancellation_and_midrun_changes(studio,tmp_path,monkeypatch,fault):
    actor,args,voice=seed(studio,tmp_path,seconds=3. if fault=='long' else .6);lab=studio.lab
    job=lab.dubbing.submit(actor,reviewed(lab,actor,args));original=lab.providers.synthesize;fired=[]
    def synth(*a,**kw):
        value=original(*a,**kw)
        if not fired:
            fired.append(True)
            if fault=='cancel':studio.queue.cancel(job['id'])
            elif fault=='revision':
                d=studio.store.get(studio.test_pid);studio.store.mutate(d['project_id'],d['revision'],'change-mid-dub',{},lambda x:x.update(name='Changed'))
            elif fault=='voice_file':Path(voice['data']['model_path']).write_bytes(b'changed model')
            elif fault=='voice_version':lab.store.change(actor,voice['id'],voice['version'],lambda v,db:v.update(name='New profile'))
        return value
    monkeypatch.setattr(lab.providers,'synthesize',synth)
    with pytest.raises((ValueError,Conflict,JobLeaseLost)):execute(studio,job)
    assert not lab.store.listing(actor,'dubbing') and len(studio.store.list())==1


@pytest.mark.skipif(os.name=='nt',reason='POSIX CLI fixture')
@pytest.mark.parametrize('fault',['unlistened','wrong_output','manifest','archive','media','revision','duplicate_accept'])
def test_candidate_acceptance_is_exact_and_rechecks_before_publication(studio,tmp_path,fault):
    actor,args,item=candidate(studio,tmp_path);lab=studio.lab;data=accepted(item)
    if fault=='unlistened':data['listened']=False
    if fault=='wrong_output':data['output_content_id']='sha256:'+'0'*64
    if fault=='revision':
        d=studio.store.get(studio.test_pid);studio.store.mutate(d['project_id'],d['revision'],'before-accept-change',{},lambda x:x.update(name='Changed'))
    if fault in ('unlistened','wrong_output','revision'):
        with pytest.raises((ValueError,Conflict)):lab.dubbing.accept(actor,data)
    else:
        first=lab.dubbing.accept(actor,data)
        if fault=='duplicate_accept':
            second=lab.dubbing.accept(actor,data);execute(studio,first)
            with pytest.raises((ValueError,Conflict)):execute(studio,second)
            assert len(studio.store.list())==2;return
        key={'manifest':'manifest_path','archive':'archive_path','media':'dubbed_path'}[fault]
        path=Path(item['data'][key]);path.write_bytes(path.read_bytes()+b'changed')
        with pytest.raises(ValueError):execute(studio,first)
    assert len(studio.store.list())==1


def test_HTTP_role_idempotence_and_workspace_scope(studio,tmp_path):
    actor,args,_=seed(studio,tmp_path);app=FastAPI();app.include_router(create_router(studio));install_security(app,studio)
    client=TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',50000));data=reviewed(studio.lab,actor,args)
    body={'schema_version':1,'command_id':'dubbing-http-reviewed-1','action':'m9.dub.submit','args':data}
    first=client.post('/api/studio/m8/v1/command',json=body);second=client.post('/api/studio/m8/v1/command',json=body)
    assert first.status_code==200 and first.json()['id']==second.json()['id'] and len(studio.queue.list(studio.test_pid))==1
    with studio.store.connect() as db:db.execute("INSERT INTO m8_members VALUES('solo','reviewer','reviewer')")
    reviewer=Actor('solo','reviewer',local=False)
    assert studio.integrations.command(reviewer,{'schema_version':1,'action':'m9.dub.plan','args':args})['plan_digest']
    with pytest.raises(AccessDenied):studio.integrations.command(reviewer,body)
    other=studio.integrations.workspaces.create(actor,{'name':'Other workspace'})
    foreign=studio.integrations.local_actor(other['id'])
    with pytest.raises(AccessDenied):studio.lab.dubbing.plan(foreign,args)


def test_srt_rounding_carries_seconds():
    assert srt_time(59.9996)=='00:01:00,000' and srt_time(3600.123)=='01:00:00,123'


@pytest.mark.parametrize('fault',['missing_cue','numbers','origin','time','overlap'])
def test_plan_revalidates_track_coverage_and_literal_evidence(studio,tmp_path,fault):
    actor,args,_=seed(studio,tmp_path);track=studio.store.transcript(args['track_id'])
    if fault=='missing_cue':track['cues'].pop()
    if fault=='numbers':track['cues'][0]['text']='Andi does not pay 500 rupiah.'
    if fault=='origin':track['cues'][0]['origin_word_ids']=[999]
    if fault=='time':track['cues'][0]['start']+=.05
    if fault=='overlap':track['cues'][1]['start']=1.
    with studio.store.connect() as db:db.execute('UPDATE transcripts SET metadata=? WHERE id=?',(canonical(track),args['track_id']))
    with pytest.raises(ValueError):studio.lab.dubbing.plan(actor,args)


@pytest.mark.skipif(os.name=='nt',reason='POSIX authored CLI fixture')
def test_atempo_fits_without_speech_tail_truncation(studio,tmp_path):
    actor,args,_=seed(studio,tmp_path,seconds=1.6);lab=studio.lab
    item=lab.store.get(actor,execute(studio,lab.dubbing.submit(actor,reviewed(lab,actor,args)))['item_id'])
    manifest=json.loads(Path(item['data']['manifest_path']).read_text())
    for row in manifest['measurements']:
        assert 1<row['atempo']<=1.15 and row['output_end_sample']<=row['slot_end_sample'] and row['truncated_samples']==0


@pytest.mark.skipif(os.name=='nt',reason='POSIX authored live CLI cancellation fixture')
def test_cancel_while_actual_piper_child_is_alive(studio,tmp_path):
    actor,args,_=seed(studio,tmp_path,sleep_seconds=60);lab=studio.lab
    job=lab.dubbing.submit(actor,reviewed(lab,actor,args));observed=[]
    def cancel_when_started():
        deadline=time.monotonic()+5
        marker=lab.root/'dubbing'/job['id']/'cue-000-raw.wav.started'
        while time.monotonic()<deadline:
            if marker.exists():observed.append(True);studio.queue.cancel(job['id']);return
            time.sleep(.02)
    thread=threading.Thread(target=cancel_when_started);thread.start();started=time.monotonic()
    try:
        with pytest.raises(JobLeaseLost):execute(studio,job)
    finally:thread.join(timeout=6)
    assert observed and time.monotonic()-started<6
    assert studio.queue.get(job['id'])['status']=='canceled' and not lab.store.listing(actor,'dubbing')
