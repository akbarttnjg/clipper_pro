"""Regressions for hidden active jobs and inaccessible diagnostic logs."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from clipper.api_runtime import router
from clipper.runtime.manager import RuntimeManager


@pytest.fixture
def manager(tmp_path):
    return RuntimeManager(Path(__file__).resolve().parents[2],tmp_path/'runtime',autostart=False)


def client_for(manager):
    app=FastAPI();app.include_router(router(SimpleNamespace(runtime=manager)))
    return TestClient(app)


def test_old_running_job_survives_long_completed_history(manager):
    running=manager.enqueue('whisperx','install');assert manager.claim()==running['id']
    for _ in range(65):
        job=manager.enqueue('fonttools','probe');manager.update(job['id'],status='completed')
    jobs=manager.jobs()
    assert running['id'] in {j['id'] for j in jobs}
    assert len(jobs)==41
    assert len([j for j in jobs if j['status']=='completed'])==40


def test_old_queued_jobs_are_not_lost_to_history_limit(manager):
    queued=manager.enqueue('sam2','install')
    for _ in range(45):
        job=manager.enqueue('fonttools','probe');manager.update(job['id'],status='completed')
    assert queued['id'] in {j['id'] for j in manager.snapshot()['jobs']}


def test_cancel_queued_preserves_running_completed_and_partial_files(manager):
    running=manager.enqueue('whisperx','install');manager.claim()
    pending=[manager.enqueue(key,'install') for key in ('sam2','talknet','e5')]
    done=manager.enqueue('ffmpeg','install');manager.update(done['id'],status='completed')
    partial=manager.root/'generations'/pending[0]['id']/'weights.part'
    partial.parent.mkdir(parents=True);partial.write_bytes(b'partial-weight-bytes')
    result=manager.cancel_queued()
    assert result['canceled']==3
    assert set(result['job_ids'])=={j['id'] for j in pending}
    assert manager.job(running['id'])['status']=='running'
    assert manager.job(done['id'])['status']=='completed'
    assert partial.read_bytes()==b'partial-weight-bytes'
    assert all(manager.job(j['id'])['status']=='canceled' for j in pending)
    assert manager.cancel_queued()['canceled']==0
    assert manager.resume(pending[0]['id'])['options']==pending[0]['options']


def test_batch_cancel_api_is_separate_from_running_cancel(manager):
    running=manager.enqueue('whisperx','install');manager.claim()
    queued=manager.enqueue('sam2','install')
    with client_for(manager) as client:
        result=client.post('/runtime/jobs/cancel-queued')
        assert result.status_code==200 and result.json()['canceled']==1
        assert manager.job(running['id'])['status']=='running'
        assert manager.job(queued['id'])['status']=='canceled'
        assert client.post('/runtime/jobs/'+running['id']+'/cancel').json()['status']=='cancel_requested'


def test_log_keeps_more_than_old_3000_chars_and_redacts_credentials(manager,monkeypatch):
    monkeypatch.setenv('HF_TOKEN','private-token-regression-123')
    job=manager.enqueue('faster-whisper','install')
    log=manager.root/'logs'/(job['id']+'.log');log.parent.mkdir()
    contents='important-start\n'+'details\n'*1200+'private-token-regression-123\nimportant-end'
    log.write_text(contents,encoding='utf-8')
    with client_for(manager) as client:
        result=client.get('/runtime/jobs/'+job['id']+'/log').json()
        assert 'important-start' in result['text'] and 'important-end' in result['text']
        assert len(result['text'])>3000 and result['truncated'] is False
        assert 'private-token-regression-123' not in result['text']
        download=client.get('/runtime/jobs/'+job['id']+'/log/download')
        assert download.status_code==200
        assert download.text==result['text']
        assert 'attachment' in download.headers['content-disposition']


def test_large_log_tail_is_bounded_and_marked(manager):
    job=manager.enqueue('whisperx','install')
    log=manager.root/'logs'/(job['id']+'.log');log.parent.mkdir()
    log.write_text('not-in-tail\n'+'x'*120000+'\nlast-error',encoding='utf-8')
    with client_for(manager) as client:
        result=client.get('/runtime/jobs/'+job['id']+'/log').json()
        assert len(result['text'])==100000 and result['truncated'] is True
        assert 'not-in-tail' not in result['text'] and result['text'].endswith('last-error')
        assert client.get('/runtime/jobs/'+job['id']+'/log/download').text.startswith('[Bagian akhir log;')


def test_missing_log_is_readable_and_invalid_job_rejected(manager):
    job=manager.enqueue('sam2','install')
    with client_for(manager) as client:
        assert client.get('/runtime/jobs/'+job['id']+'/log').json()['text']=='Log belum tersedia'
        assert client.get('/runtime/jobs/'+job['id']+'/log/download').status_code==200
        assert client.get('/runtime/jobs/not-a-job/log/download').status_code==400
