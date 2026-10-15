"""Actual local backend flow: reviewed transcript → M5/M6 render → M7 → review.

Only the source and transcript are authored fixtures. Media jobs, ArtifactSets,
SQLite publication, export writers and HTTP range access execute without doubles.
"""
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from clipper.studio_worker import execute
from clipper.artifact_store import verify
from clipper.api_studio import create_router
from clipper.dependency_cache import content_id
from ._m4_fixture import make_studio,change


def test_actual_render_publication_M6_M7_and_review_share_exact_revision(tmp_path):
    svc=make_studio(tmp_path)
    try:
        pid,cid=svc.test_pid,svc.test_cid;initial=svc.store.get(pid);source_id=content_id(initial['source']['path'],fresh=True)
        transcript=svc.store.transcript(initial['transcript_id']);transcript['language']='id'
        take=svc.store.save_transcript(pid,transcript)
        svc.store.mutate(pid,initial['revision'],'declare-authored-fixture-language',{},lambda d:d.update(transcript_id=take))
        change(svc,{'op':'m4_ratio','variant_id_new':'custom','width':320,'height':180})
        change(svc,{'op':'m5_enable','enabled':True},vid='custom');change(svc,{'op':'m6_enable','enabled':True},vid='custom')
        before=svc.store.get(pid);render=svc.enqueue(pid,'render',cid,'custom',before['revision']);result=execute(svc,render)
        assert verify(result,fresh=True) and svc.queue.get(render['id'])['status']=='completed'
        plan=json.loads(Path(result['plan_path']).read_text());sidecars=json.loads((Path(result['artifact_root'])/'Sidecars/transcript.json').read_text())
        assert sidecars['language']=='id' and sidecars['reference']['requested_revision']==result['requested_revision']
        assert sidecars['reference']['output_content_id']==result['output_content_id']
        assert sidecars['publication']['requested_revision']==plan['publication']['requested_revision']
        now=svc.store.get(pid);job=svc.enqueue(pid,'delivery_m7',expected_revision=now['revision'],options={'ratios':['custom'],'editors':['capcut','resolve'],'alpha':True})
        package=execute(svc,job);assert verify(package,fresh=True) and len(package['coverage'])==1
        main=json.loads(Path(package['delivery_manifest_path']).read_text());assert main['coverage'][0]['reviewed_output_content_id']==result['output_content_id']
        assert main['merged'][0]['qc']['frames']==plan['duration_frames']
        assert content_id(svc.store.get(pid)['source']['path'],fresh=True)==source_id
        app=FastAPI();app.include_router(create_router(svc));client=TestClient(app)
        response=client.post(f'/api/studio/projects/{pid}/delivery7/reviews',json={'expected_revision':svc.store.get(pid)['revision'],
            'package_content_id':package['package_content_id'],'permission':'download','expires_minutes':15})
        assert response.status_code==200,response.text
        review=client.get(response.json()['url']);assert review.status_code==200
        assert review.json()['entries'][0]['content_id']==result['output_content_id']
        stream=client.get(review.json()['entries'][0]['url'],headers={'Range':'bytes=0-255'});assert stream.status_code==206 and len(stream.content)==256
        import os,shutil
        if os.environ.get('CLIPPER_M7_EVIDENCE'):
            folder=Path(os.environ['CLIPPER_M7_EVIDENCE']);folder.mkdir(parents=True,exist_ok=True)
            shutil.copy2(package['zip'],folder/'DEMO_BUATAN_M7_Delivery.zip')
            summary={'scope':'authored color/tone/manual transcript; no ASR/model/native editor quality claim',
                'source_content_id':source_id,'render_content_id':result['output_content_id'],
                'render_revision':result['requested_revision'],'delivery_revision':package['input_revision'],
                'delivery_content_id':package['package_content_id'],'actual_frames':main['merged'][0]['qc']['frames'],
                'expected_frames':plan['duration_frames'],'sidecar_language':sidecars['language'],
                'source_unchanged':True,'artifact_sets_verified':True,'review_range_access':stream.status_code,
                'editors':main['editors'],'native_editor_status':'not_tested'}
            (folder/'backend-e2e.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    finally:svc.queue.close()
