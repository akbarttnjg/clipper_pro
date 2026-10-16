"""Adversarial M8 integration state, HTTP access, restore and offline RPC tests."""
import copy
import hashlib
import hmac
import io
import json
import zipfile
from pathlib import Path
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from clipper.api_m8 import router, install_security
from clipper.m8 import M8
from clipper.m8_contract import AccessDenied, Busy, canonical, schedule
from clipper.m8_workspace import Actor
from clipper.m8_worker import Worker
from clipper.m8_youtube import NetworkFailure, RemoteFailure
from clipper.m8_mcp import Protocol, serve
from clipper.project_store import Conflict
from .test_m8_contract import m8, account, draft, approved, ProtocolFixture


def test_double_approval_does_not_create_two_reservations(m8):
    row = draft(m8);report = m8.publishing.preflight(m8.test_actor, row['id'])
    args = {'id': row['id'], 'expected_version': row['version'], 'approval_hash': report['approval_hash']}
    m8.publishing.approve(m8.test_actor, args)
    with pytest.raises((Conflict, ValueError)):
        m8.publishing.approve(m8.test_actor, args)
    with m8.service.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM m8_ledger WHERE kind='publish'").fetchone()[0] == 1


def test_account_change_invalidates_frozen_approval(m8):
    row = approved(m8);target = m8.accounts.get(m8.test_actor, row['account_id'])
    m8.accounts.save(m8.test_actor, {'id': target['id'], 'expected_version': target['version'], 'platform': 'youtube', 'name': 'Renamed', 'remote_id': 'channel_fixture'})
    m8.worker.tick()
    assert m8.publishing.get(m8.test_actor, row['id'])['status'] == 'stale'
    assert m8.transport.initializations == 0


def test_future_local_schedule_does_not_upload_early(m8):
    row = approved(m8, local_time='2027-12-01T08:00:00', timezone='Asia/Jakarta')
    assert row['due'] > m8.db.clock()
    assert m8.worker.tick()['status'] == 'idle' and m8.transport.initializations == 0


def test_remote_schedule_is_private_and_has_exact_utc_time(m8):
    row = approved(m8, local_time='2027-12-01T08:00:00', timezone='Asia/Jakarta', remote_schedule=True,
        metadata={'title': 'Contoh', 'privacy': 'public'})
    m8.worker.tick();m8.worker.tick();m8.worker.tick()
    result = m8.publishing.get(m8.test_actor, row['id'])
    assert result['status'] == 'scheduled_remote' and result['remote']['privacy'] == 'private'
    assert result['remote']['publish_at'] == '2027-12-01T01:00:00Z'


def test_actual_privacy_mismatch_is_not_claimed_public_success(m8):
    row = approved(m8, metadata={'title': 'Contoh', 'privacy': 'public'})
    for _ in range(3):m8.worker.tick()
    result = m8.publishing.get(m8.test_actor, row['id'])
    assert result['status'] == 'remote_mismatch' and result['remote']['privacy'] == 'private'


def test_interrupted_process_reuses_saved_session(m8):
    row = approved(m8);m8.worker.tick()
    new = M8(m8.service, clock=m8.db.clock, transport=m8.transport, server_mode=False)
    new.worker.tick();new.worker.tick()
    assert new.publishing.get(m8.test_actor, row['id'])['status'] == 'published'
    assert m8.transport.initializations == 1


def test_unknown_submission_does_not_open_new_session(m8):
    row = approved(m8)
    original = m8.youtube.begin
    def lost(*a, **kw):
        original(*a, **kw)
        raise NetworkFailure('lost response')
    m8.youtube.begin = lost
    m8.worker.tick()
    result = m8.publishing.get(m8.test_actor, row['id'])
    assert result['status'] == 'needs_reconcile'
    with pytest.raises(ValueError, match='manual'):
        m8.publishing.retry(m8.test_actor, {'id': row['id'], 'expected_version': result['version']})
    m8.worker.tick();assert m8.transport.initializations == 1


def test_expired_session_after_attempt_is_blocked_from_fresh_upload(m8):
    row = approved(m8);m8.worker.tick()
    m8.youtube.upload_status = lambda *a: (_ for _ in ()).throw(RemoteFailure(404))
    m8.worker.tick()
    assert m8.publishing.get(m8.test_actor, row['id'])['status'] == 'needs_reconcile'
    assert m8.transport.initializations == 1


def test_cancel_before_submission_has_no_api_mutation(m8):
    row = approved(m8)
    result = m8.publishing.cancel(m8.test_actor, {'id': row['id'], 'expected_version': row['version']})
    assert result['status'] == 'canceled'
    m8.worker.tick();assert m8.transport.initializations == m8.transport.sends == 0


def test_cancel_during_final_put_keeps_remote_id_then_confirms_private(m8):
    row = approved(m8);m8.worker.tick()
    original = m8.youtube.chunk
    def in_flight(*a, **kw):
        current = m8.publishing.get(m8.test_actor, row['id'])
        m8.publishing.cancel(m8.test_actor, {'id': row['id'], 'expected_version': current['version'], 'remote_to_private': True})
        return original(*a, **kw)
    m8.youtube.chunk = in_flight
    m8.worker.tick()
    assert m8.publishing.get(m8.test_actor, row['id'])['status'] == 'cancel_requested'
    m8.worker.tick()
    result = m8.publishing.get(m8.test_actor, row['id'])
    assert result['status'] == 'canceled' and result['remote']['remote_cancel'] == 'confirmed_private_unscheduled'
    assert m8.transport.initializations == 1


def test_two_workers_fence_old_lease_and_never_claim_second_row(m8):
    row = approved(m8);claimed = m8.worker.claim();assert claimed['id'] == row['id']
    second = Worker(m8);assert second.claim() is None
    m8.test_clock[0] += 91
    other = second.claim();assert other['id'] == row['id']
    with pytest.raises(Busy):
        m8.worker.checkpoint(claimed, status='published')
    second.release(row['id'])


def test_changed_chunk_never_reaches_upload_transport(m8):
    row = approved(m8);m8.worker.tick()
    value = m8.publishing.get(m8.test_actor, row['id'], private=True)
    path = Path(value['request']['path']);path.write_bytes(b'CHANGED')
    uri = m8.vault.get(value['cursor']['session_ref'])['session_uri']
    with pytest.raises(ValueError, match='chunk'):
        m8.youtube.chunk(m8.accounts.get(m8.test_actor, row['account_id'], private=True), uri, path, 0,
            value['request']['chunk_size'], value['request']['chunk_hashes'])
    assert m8.transport.sends == 0


def test_revised_draft_revokes_approval_and_reactivated_reservation_counts(m8):
    row = approved(m8)
    revised = m8.publishing.revise(m8.test_actor, {'id': row['id'], 'expected_version': row['version'], 'metadata': {'title': 'Baru', 'privacy': 'private'}})
    assert revised['status'] == 'draft' and revised['approval'] is None
    proof = m8.publishing.preflight(m8.test_actor, row['id'])
    m8.publishing.approve(m8.test_actor, {'id': row['id'], 'expected_version': revised['version'], 'approval_hash': proof['approval_hash']})
    with m8.service.store.connect() as db:
        assert db.execute("SELECT state FROM m8_ledger WHERE reference=?", (row['id'],)).fetchone()[0] == 'reserved'


def test_scheduled_remote_metadata_edit_remains_scheduled(m8):
    row = approved(m8, local_time='2027-12-01T08:00', remote_schedule=True, metadata={'title': 'Contoh', 'privacy': 'public'})
    for _ in range(3):m8.worker.tick()
    current = m8.publishing.get(m8.test_actor, row['id'])
    m8.publishing.remote_edit(m8.test_actor, {'id': row['id'], 'expected_version': current['version'], 'metadata': {'title': 'Judul baru', 'privacy': 'public'}})
    m8.worker.tick()
    current = m8.publishing.get(m8.test_actor, row['id'])
    assert current['status'] == 'scheduled_remote' and current['remote']['metadata_update_confirmed']


def test_latest_metric_refresh_wins_even_same_timestamp(m8):
    row = draft(m8, platform='tiktok', connected=False)
    data = {'publish_id': row['id'], 'start_date': '2026-10-01', 'end_date': '2026-10-02', 'values': {'views': 5}}
    m8.analytics.observe(m8.test_actor, data);data['values']['views'] = 8;m8.analytics.observe(m8.test_actor, data)
    views = [r for r in m8.analytics.rows(m8.test_actor) if r['metric'] == 'views']
    assert len(views) == 1 and views[0]['value'] == 8


def test_metrics_api_actual_fields_and_missing_availability(m8):
    row = approved(m8)
    for _ in range(3):m8.worker.tick()
    m8.analytics.refresh(m8.test_actor, {'publish_id': row['id'], 'start_date': '2026-10-01', 'end_date': '2026-10-02'})
    values = {r['metric']: r for r in m8.analytics.rows(m8.test_actor)}
    assert values['views']['value'] == 12 and values['estimatedMinutesWatched']['value'] == 3.5
    assert values['likes']['value'] is None


def test_active_effort_excludes_waiting_and_overlapping_intervals(m8):
    base = {'project_id': m8.test_pid, 'expected_revision': 0, 'intervals': [{'start': m8.db.clock()-20, 'end': m8.db.clock()-10, 'activity': 'review'}]}
    assert m8.analytics.effort(m8.test_actor, base)['data']['active_seconds'] == 10
    base['intervals'][0]['activity'] = 'render_wait'
    with pytest.raises(ValueError):m8.analytics.effort(m8.test_actor, base)


def test_project_backup_restore_new_workspace_identity_and_no_publish_replay(m8):
    # Core source/transcript/history are real SQLite rows. Media-QC is tested separately.
    before = m8.service.store.get(m8.test_pid)
    take = m8.service.store.save_transcript(m8.test_pid, {'words': [], 'raw_words': [], 'duration': 4.})
    m8.service.store.mutate(m8.test_pid, 0, 'set-backup-transcript', {}, lambda d: d.update(transcript_id=take))
    result = m8.backups.create(m8.test_actor, {'project_id': m8.test_pid, 'expected_revision': 1})
    restored = m8.backups.restore(m8.test_actor, {'file_id': result['url'].rsplit('/', 1)[-1]})
    assert restored['project_id'] != m8.test_pid and restored['revision'] == 1 and not restored['publish_replay']
    doc = m8.service.store.get(restored['project_id']);assert Path(doc['source']['path']).read_bytes() == Path(before['source']['path']).read_bytes()
    assert doc['transcript_id'] != take
    m8.workspaces.require(m8.test_actor, 'manage', restored['project_id'])
    assert not m8.publishing.listing(m8.test_actor, restored['project_id'])


def test_backup_path_traversal_rejected_without_partial_project(m8, tmp_path):
    bad = tmp_path/'bad.zip'
    with zipfile.ZipFile(bad, 'w') as z:z.writestr('../escape', b'bad')
    count = len(m8.service.store.list())
    with pytest.raises(ValueError, match='Path'):
        m8.backups.restore(m8.test_actor, {'path': str(bad)})
    assert len(m8.service.store.list()) == count and not (tmp_path/'escape').exists()


def make_client(m8, *, server=False, peer='127.0.0.1', host='http://localhost'):
    m8.server_mode = server
    app = FastAPI();app.include_router(router(m8.service), prefix='/api/studio')
    @app.get('/api/studio/projects')
    def legacy():return {'legacy': True}
    install_security(app, m8.service)
    return TestClient(app, base_url=host, client=(peer, 5000))


def payload(action='status', args=None, key='http-stable-command'):
    return {'schema_version': 1, 'command_id': key, 'action': action, 'args': args or {}}


def test_http_local_origin_host_peer_and_request_size_boundaries(m8):
    client = make_client(m8)
    url = '/api/studio/m8/v1/command'
    assert client.post(url, json=payload()).status_code == 200
    assert client.get('/api/studio/projects').status_code == 200
    assert client.post(url, json=payload(), headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post(url, json=payload(), headers={'Host': 'evil.example'}).status_code == 403
    assert make_client(m8, peer='192.168.1.4').post(url, json=payload()).status_code == 403
    assert client.post(url, content=b' '* (1024**2+1), headers={'Content-Type': 'application/json'}).status_code == 413


def test_server_bearer_blocks_legacy_bypass_and_reviewer_publish(m8):
    value = m8.workspaces.issue_session(m8.test_actor, {'user_id': 'review', 'role': 'reviewer'})
    client = make_client(m8, server=True)
    url = '/api/studio/m8/v1/command';headers = {'Authorization': 'Bearer '+value['token']}
    assert client.post(url, json=payload()).status_code == 403
    assert client.post(url, json=payload(), headers=headers).status_code == 200
    assert client.get('/api/studio/projects', headers=headers).status_code == 403
    assert client.post(url, json=payload('account.save', {'name': 'No', 'platform': 'tiktok'}), headers=headers).status_code == 403
    assert client.post(url, json=payload('publish.draft', {'project_id': m8.test_pid}), headers=headers).status_code == 403
    m8.workspaces.revoke_session(m8.test_actor, value['id'])
    assert client.post(url, json=payload(), headers=headers).status_code == 403


def test_role_downgrade_blocks_cached_mutation_receipt(m8):
    value = m8.workspaces.issue_session(m8.test_actor, {'user_id': 'secondowner', 'role': 'owner'})
    actor = m8.workspaces.authenticate(value['token'])
    request = payload('account.save', {'name': 'One', 'platform': 'tiktok'})
    m8.command(actor, request)
    m8.workspaces.member(m8.test_actor, {'user_id': 'secondowner', 'role': 'reviewer'})
    with pytest.raises(AccessDenied):m8.command(actor, request)


def test_webhook_pinned_allowlist_signed_payload_and_same_event_retry(m8, monkeypatch):
    monkeypatch.setenv('CLIPPER_M8_WEBHOOK_HOSTS', 'hooks.example.com')
    row = m8.webhooks.save(m8.test_actor, {'url': 'https://hooks.example.com/clipper', 'events': ['custom']})
    key = m8.webhooks.signing_key(m8.test_actor, row['id'])['signing_key']
    with m8.db.transaction() as db:m8.db.event(db, 'solo', 'custom', m8.test_pid, 0, {'job_id': 'test', 'access_token': 'DO-NOT-EXPORT'})
    seen = []
    def sender(url, body, headers):
        signature = hmac.new(key.encode(), headers['X-Clipper-Timestamp'].encode()+b'.'+body, hashlib.sha256).hexdigest()
        assert headers['X-Clipper-Signature'] == 'sha256='+signature
        assert b'DO-NOT-EXPORT' not in body
        seen.append(headers['X-Clipper-Event-ID']);return 503 if len(seen) == 1 else 204
    m8.webhooks.sender = sender
    assert m8.webhooks.tick()['status'] == 'pending'
    m8.test_clock[0] += 100
    assert m8.webhooks.tick()['status'] == 'delivered' and seen[0] == seen[1]


def test_mcp_lifecycle_transport_and_error_is_not_success():
    class Client:
        def command(self, action, *a):
            if action == 'bad':raise ValueError('blocked')
            return {'status': 'queued'}
    protocol = Protocol(Client())
    assert 'error' in protocol.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
    protocol.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}})
    protocol.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    result = protocol.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'clipper_command', 'arguments': {'action': 'bad', 'args': {}, 'command_id': 'mcp-id-1'}}})
    assert result['result']['isError']
    stream = io.StringIO('not-json\n'+json.dumps({'jsonrpc': '2.0', 'id': 4, 'method': 'initialize'})+'\n');output = io.StringIO()
    serve(Client(), stream, output)
    values = [json.loads(line) for line in output.getvalue().splitlines()]
    assert values[0]['error']['code'] == -32700 and values[1]['result']['protocolVersion'] == '2025-06-18'


def test_plugin_registration_never_executes_untrusted_runtime(m8):
    value = m8.plugins.register(m8.test_actor, {'plugin_id': 'authored.fixture', 'schema_version': 1, 'capabilities': ['translate'], 'runtime': 'external_isolated_worker'})
    assert not value['data']['execution_enabled'] and value['data']['state'] == 'registered_unverified'
