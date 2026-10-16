"""Fast unit/state fixtures. These bytes are not a media-QC or live API claim."""
import base64
import copy
import io
import json
import hashlib
import zipfile
from pathlib import Path
import httpx
import pytest
from clipper.config import Config
from clipper.studio_service import StudioService
from clipper.artifact_store import ArtifactSet
from clipper.dependency_cache import content_id
from clipper.m8 import M8
from clipper.m8_contract import AccessDenied, Busy, SCOPES, canonical, schedule
from clipper.m8_workspace import Actor
from clipper.m8_youtube import NetworkFailure, session_uri
from clipper.project_store import Conflict


class ProtocolFixture:
    def __init__(self):
        self.initializations = 0;self.sends = 0;self.offset = 0;self.complete = False
        self.lose_final_response = False;self.privacy = 'private';self.processing = 'succeeded';self.publish_at = None
        self.calls = [];self.title = 'Contoh';self.description = '';self.tags = []
    def request(self, method, url, **kw):
        self.calls.append((method, url))
        if url.endswith('/channels'):
            return httpx.Response(200, json={'items': [{'id': 'channel_fixture', 'snippet': {'title': 'Channel authored'}}]})
        if method == 'POST' and '/upload/' in url:
            self.initializations += 1
            self.publish_at = kw['json']['status'].get('publishAt')
            self.title = kw['json']['snippet']['title'];self.description = kw['json']['snippet']['description'];self.tags = kw['json']['snippet']['tags']
            return httpx.Response(200, headers={'Location': 'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=fixture'})
        if method == 'PUT' and '/upload/' in url:
            content = kw.get('content', b'')
            if content:
                self.sends += 1;self.offset += len(content);self.complete = True
                if self.lose_final_response:
                    self.lose_final_response = False
                    raise NetworkFailure('Koneksi terputus')
            if self.complete:
                return httpx.Response(201, json={'id': 'video_fixture'})
            return httpx.Response(308, headers={'Range': 'bytes=0-'+str(self.offset-1)} if self.offset else {})
        if method == 'PUT' and url.endswith('/videos'):
            if 'snippet' in kw['json']:
                self.title = kw['json']['snippet']['title'];self.description = kw['json']['snippet']['description'];self.tags = kw['json']['snippet']['tags']
            else:
                self.privacy = 'private';self.publish_at = None
            return httpx.Response(200, json={})
        if method == 'GET' and url.endswith('/videos'):
            status = {'privacyStatus': self.privacy, 'uploadStatus': 'processed'}
            if self.publish_at:
                status['publishAt'] = self.publish_at
            return httpx.Response(200, json={'items': [{'id': 'video_fixture', 'status': status, 'processingDetails': {'processingStatus': self.processing},
                'snippet': {'title': self.title, 'description': self.description, 'tags': self.tags, 'categoryId': '22'}, 'statistics': {'viewCount': '12'}}]})
        if 'youtubeanalytics' in url:
            return httpx.Response(200, json={'columnHeaders': [{'name': 'views'}, {'name': 'estimatedMinutesWatched'}], 'rows': [[12, 3.5]]})
        raise AssertionError('Unexpected fixture request: '+method+' '+url)


@pytest.fixture
def m8(tmp_path, monkeypatch):
    monkeypatch.setenv('CLIPPER_M8_VAULT_KEY', base64.b64encode(bytes(range(32))).decode())
    service = StudioService(tmp_path, Config(work_dir='work', out_dir='clips', use_nvenc=False), autostart=False)
    clock = [1800000000.]
    engine = M8(service, clock=lambda: clock[0], transport=ProtocolFixture(), server_mode=False)
    service.__dict__['integrations'] = engine
    engine.test_clock = clock
    engine.test_actor = engine.local_actor()
    source = service.work/'authored.bin';source.write_bytes(b'authored protocol fixture, not decoded media')
    txn = ArtifactSet(service.work/'authored-delivery')
    folder = txn.staging/'Package';(folder/'Clips/c-portrait/Sidecars').mkdir(parents=True)
    final = folder/'Clips/c-portrait/final.mp4';final.write_bytes(b'authored protocol fixture for queue ownership only')
    side = folder/'Clips/c-portrait/Sidecars/captions.srt';side.write_text('1\n00:00:00,000 --> 00:00:01,000\nContoh\n')
    output = content_id(final, fresh=True)
    row = {'clip_id': 'c', 'variant_id': 'portrait', 'file': 'Clips/c-portrait/final.mp4', 'key': 'c-portrait', 'title': 'Contoh', 'duration': 1., 'output_content_id': output, 'reviewed_output_content_id': output}
    manifest = {'coverage': [row], 'files': [{'path': 'Clips/c-portrait/Sidecars/captions.srt', 'content_id': content_id(side, fresh=True), 'role': 'subtitle_transcript_same_revision'}]}
    (folder/'delivery.json').write_text(canonical(manifest))
    archive = txn.staging/'delivery.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.write(final, 'final.mp4')
    sealed = txn.seal()
    final = txn.final/'Package/Clips/c-portrait/final.mp4'
    package = {**sealed, 'version': '4.0.18-m7', 'folder': str(txn.final/'Package'), 'delivery_manifest_path': str(txn.final/'Package/delivery.json'),
        'zip': str(txn.final/'delivery.zip'), 'package_content_id': content_id(txn.final/'delivery.zip', fresh=True), 'input_revision': 0, 'coverage': [row]}
    document = {'name': 'Authored unit fixture', 'settings': {}, 'source': {'path': str(source), 'source_id': content_id(source), 'info': {'duration': 4., 'audio_tracks': []}},
        'clips': {'c': {'title': 'Contoh', 'start': 0., 'end': 1., 'included': True, 'variants': {'portrait': {'settings': {}, 'result': {'absolute_file': str(final), 'output_content_id': output, 'dependency': 'fixture'}}}}}, 'exports': [package]}
    doc = service.store.create(document);engine.test_pid = doc['project_id'];engine.test_package = package
    monkeypatch.setattr(service, 'dependency', lambda *a, **kw: 'fixture')
    engine.workspaces.require(engine.test_actor, 'read', engine.test_pid)
    yield engine
    engine.close();service.queue.close()


def account(m8, platform='youtube', connected=True):
    credentials = {'access_token': 'secret-fixture-access', 'refresh_token': 'secret-fixture-refresh', 'client_id': 'fixture.apps.googleusercontent.com',
        'client_secret': 'secret-client', 'scopes': list(SCOPES.values()), 'expires_at': m8.db.clock()+3600} if connected else None
    row = m8.accounts.save(m8.test_actor, {'platform': platform, 'name': 'Authored account', 'remote_id': 'channel_fixture'}, credentials=credentials)
    if connected:
        m8.accounts.probe(m8.test_actor, row['id'])
    return row


def draft(m8, *, platform='youtube', connected=True, **extra):
    target = account(m8, platform, connected)
    return m8.publishing.draft(m8.test_actor, {'project_id': m8.test_pid, 'expected_revision': m8.service.store.get(m8.test_pid)['revision'],
        'package_content_id': m8.test_package['package_content_id'], 'clip_id': 'c', 'variant_id': 'portrait', 'account_id': target['id'],
        'metadata': {'title': 'Contoh', 'privacy': 'private'}, 'mode': 'youtube' if connected else 'handoff', **extra})


def approved(m8, **kw):
    value = draft(m8, **kw);proof = m8.publishing.preflight(m8.test_actor, value['id'])
    assert proof['ready'], proof
    return m8.publishing.approve(m8.test_actor, {'id': value['id'], 'expected_version': value['version'], 'approval_hash': proof['approval_hash']})


def test_jakarta_schedule_converts_across_utc_day():
    value = schedule('2026-10-16T01:30', 'Asia/Jakarta')
    assert value['utc'] == schedule('2026-10-15T18:30:00Z', 'Asia/Jakarta')['utc']
    assert value['local'].startswith('2026-10-16T01:30:00+07:00')


def test_dst_ambiguity_and_nonexistent_clock_are_explicit():
    with pytest.raises(ValueError, match='ambigu'):
        schedule('2026-11-01T01:30', 'America/New_York')
    assert schedule('2026-11-01T01:30', 'America/New_York', 0)['utc'] != schedule('2026-11-01T01:30', 'America/New_York', 1)['utc']
    with pytest.raises(ValueError, match='tidak ada'):
        schedule('2026-03-08T02:30', 'America/New_York')


@pytest.mark.parametrize('uri', ['http://www.googleapis.com/upload/youtube/v3/videos?upload_id=x', 'https://evil.example/upload/youtube/v3/videos?upload_id=x', 'https://www.googleapis.com:444/upload/youtube/v3/videos?upload_id=x', 'https://www.googleapis.com/else?upload_id=x'])
def test_upload_session_cannot_redirect_credentials(uri):
    with pytest.raises(ValueError):
        session_uri(uri)


def test_vault_ciphertext_authentication_and_no_plaintext_fallback(m8, monkeypatch):
    key = m8.vault.put({'access_token': 'very-secret-token'})
    path = m8.vault._path(key);assert b'very-secret-token' not in path.read_bytes()
    assert m8.vault.get(key)['access_token'] == 'very-secret-token'
    monkeypatch.setenv('CLIPPER_M8_VAULT_KEY', base64.b64encode(b'Z'*32).decode())
    with pytest.raises(ValueError):
        m8.vault.get(key)
    monkeypatch.delenv('CLIPPER_M8_VAULT_KEY')
    assert not m8.vault.ready()['ready']


def test_youtube_frozen_approval_actual_processing_and_private_receipt(m8):
    row = approved(m8)
    assert row['status'] == 'queued' and not row['remote']
    m8.worker.tick();m8.worker.tick();m8.worker.tick()
    result = m8.publishing.get(m8.test_actor, row['id'])
    assert result['status'] == 'published' and result['remote']['privacy'] == 'private'
    assert m8.transport.initializations == 1 and m8.transport.sends == 1


def test_lost_final_upload_response_reconciles_without_second_video(m8):
    row = approved(m8);m8.transport.lose_final_response = True
    m8.worker.tick();m8.worker.tick()
    m8.test_clock[0] += 5
    m8.worker.tick();m8.worker.tick()
    assert m8.publishing.get(m8.test_actor, row['id'])['status'] == 'published'
    assert m8.transport.initializations == 1 and m8.transport.sends == 1


def test_no_upload_on_revision_change_after_approval(m8):
    row = approved(m8)
    m8.service.store.mutate(m8.test_pid, 0, 'edit-after-approval', {}, lambda doc: doc.update(name='Changed'))
    m8.worker.tick()
    assert m8.publishing.get(m8.test_actor, row['id'])['status'] == 'stale'
    assert m8.transport.initializations == m8.transport.sends == 0


def test_handoff_contains_exact_video_sidecars_and_never_claims_post(m8):
    row = approved(m8, platform='tiktok', connected=False)
    m8.worker.tick();value = m8.publishing.get(m8.test_actor, row['id'])
    assert value['status'] == 'handoff_ready' and value['remote']['remote_id'] is None
    key = value['remote']['handoff_url'].rsplit('/', 1)[-1]
    with zipfile.ZipFile(m8.service.file(key)) as archive:
        assert archive.testzip() is None
        assert any(name.endswith('captions.srt') for name in archive.namelist())
        assert archive.read('video.mp4').startswith(b'authored protocol fixture')
    assert not m8.transport.calls


def test_sessions_roles_workspace_isolation_and_live_revocation(m8):
    owner = m8.test_actor
    secret = m8.workspaces.issue_session(owner, {'user_id': 'reviewer', 'role': 'reviewer', 'hours': 1})
    actor = m8.workspaces.authenticate(secret['token'])
    m8.workspaces.require(actor, 'review', m8.test_pid)
    with pytest.raises(AccessDenied):
        m8.workspaces.require(actor, 'publish', m8.test_pid)
    other = m8.workspaces.create(owner, {'name': 'Other'})
    with pytest.raises(AccessDenied):
        m8.workspaces.require(Actor(other['id'], 'local', local=True), 'read', m8.test_pid)
    m8.workspaces.revoke_session(owner, secret['id'])
    with pytest.raises(AccessDenied):
        m8.workspaces.require(actor)
    with m8.service.store.connect() as db:
        assert secret['token'] not in canonical([dict(r) for r in db.execute('SELECT * FROM m8_sessions')])


def test_idempotent_command_receipt_replay_and_conflicting_body(m8):
    request = {'schema_version': 1, 'command_id': 'stable-command-0001', 'action': 'account.save', 'args': {'platform': 'tiktok', 'name': 'Manual'}}
    first = m8.command(m8.test_actor, request)
    assert first == m8.command(m8.test_actor, request)
    assert len(m8.accounts.listing(m8.test_actor)) == 1
    request['args']['name'] = 'Different'
    with pytest.raises(ValueError, match='berbeda'):
        m8.command(m8.test_actor, request)


def test_metrics_missing_different_from_real_zero_and_periods_not_summed(m8):
    row = draft(m8, platform='tiktok', connected=False)
    m8.analytics.observe(m8.test_actor, {'publish_id': row['id'], 'start_date': '2026-10-01', 'end_date': '2026-10-02', 'values': {'views': 0}})
    report = m8.analytics.dashboard(m8.test_actor)
    views = next(r for r in report['rows'] if r['metric'] == 'views');likes = next(r for r in report['rows'] if r['metric'] == 'likes')
    assert views['value'] == 0 and likes['value'] is None and likes['reason']
    assert report['periods'][0]['metrics']['likes']['sum'] is None
    assert report['dropoff_prediction']['value'] is None


def test_quota_reservations_are_atomic_and_idempotent(m8):
    m8.workspaces.configure(m8.test_actor, {'expected_version': 0, 'daily_publish': 1})
    with m8.db.transaction() as db:
        a = m8.workspaces.reserve(db, m8.test_actor, 'publish', 'same')
        assert a == m8.workspaces.reserve(db, m8.test_actor, 'publish', 'same')
    with pytest.raises(ValueError, match='Kuota'):
        with m8.db.transaction() as db:
            m8.workspaces.reserve(db, m8.test_actor, 'publish', 'second')
