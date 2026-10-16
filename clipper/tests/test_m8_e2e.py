"""Actual FFmpeg/SQLite/M7/M8/HTTP/CLI/MCP path with authored source and transcript.

No external account is connected and no live platform upload is performed.
"""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from fastapi import FastAPI
import uvicorn
from clipper.api_studio import create_router
from clipper.api_m8 import install_security
from clipper.m8_client import Client
from clipper.studio_worker import execute
from clipper.artifact_store import verify
from clipper.dependency_cache import content_id
from ._m4_fixture import make_studio, change


def test_real_M7_to_M8_handoff_backup_HTTP_CLI_and_MCP(tmp_path):
    service = make_studio(tmp_path)
    server = None;thread = None
    try:
        pid, cid = service.test_pid, service.test_cid
        change(service, {'op': 'm4_ratio', 'variant_id_new': 'custom', 'width': 320, 'height': 180})
        change(service, {'op': 'm5_enable', 'enabled': True}, vid='custom')
        change(service, {'op': 'm6_enable', 'enabled': True}, vid='custom')
        before = service.store.get(pid)
        render = service.enqueue(pid, 'render', cid, 'custom', before['revision'])
        final = execute(service, render);assert verify(final, fresh=True)
        now = service.store.get(pid)
        job = service.enqueue(pid, 'delivery_m7', expected_revision=now['revision'], options={
            'ratios': ['custom'], 'editors': [], 'merged': False, 'clean': False, 'stems': False, 'publish': True})
        package = execute(service, job);assert verify(package, fresh=True)
        now = service.store.get(pid);m8 = service.integrations;actor = m8.local_actor()
        account = m8.accounts.save(actor, {'name': 'TikTok authored manual', 'platform': 'tiktok'})
        draft = m8.publishing.draft(actor, {'project_id': pid, 'expected_revision': now['revision'], 'package_content_id': package['package_content_id'],
            'clip_id': cid, 'variant_id': 'custom', 'account_id': account['id'], 'mode': 'handoff', 'metadata': {'title': 'Demo buatan M8', 'privacy': 'private'}})
        report = m8.publishing.preflight(actor, draft['id']);assert report['ready']
        approved = m8.publishing.approve(actor, {'id': draft['id'], 'expected_version': draft['version'], 'approval_hash': report['approval_hash']})
        m8.worker.tick();result = m8.publishing.get(actor, draft['id'])
        assert result['status'] == 'handoff_ready' and result['remote']['remote_id'] is None
        archive = service.file(result['remote']['handoff_url'].rsplit('/', 1)[-1])
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            assert 'sha256:'+hashlib.sha256(z.read('video.mp4')).hexdigest() == package['coverage'][0]['output_content_id']
            assert any(n.endswith('captions.srt') for n in z.namelist())
            assert any(n.endswith('cover.jpg') for n in z.namelist())
            assert json.loads(z.read('handoff.json'))['status'] == 'manual_upload_required'
        backup = m8.backups.create(actor, {'project_id': pid, 'expected_revision': now['revision']})
        restored = m8.backups.restore(actor, {'file_id': backup['url'].rsplit('/', 1)[-1]})
        assert restored['revision'] == now['revision'] and restored['project_id'] != pid
        assert content_id(service.store.get(restored['project_id'])['source']['path'], fresh=True) == now['source']['source_id']
        app = FastAPI();app.include_router(create_router(service));install_security(app, service)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0));port = sock.getsockname()[1]
        config = uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error', access_log=False)
        server = uvicorn.Server(config);thread = threading.Thread(target=server.run, daemon=True);thread.start()
        deadline = time.monotonic()+10
        while not server.started and time.monotonic() < deadline:
            time.sleep(.03)
        assert server.started
        origin = 'http://127.0.0.1:'+str(port)
        client = Client(origin);assert client.command('status')['version'] == '4.0.19-m8'
        listing = client.command('publish.list', {'project_id': pid});assert listing['requests'][0]['id'] == draft['id']
        base = [sys.executable, '-m', 'clipper.m8_cli', '--url', origin]
        cli = subprocess.run(base+['command', 'status', '--command-id', 'actual-http-cli-status'], capture_output=True, text=True, timeout=20)
        assert cli.returncode == 0, cli.stderr
        assert json.loads(cli.stdout)['result']['version'] == '4.0.19-m8'
        requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'clipper_status', 'arguments': {}}}]
        mcp = subprocess.run(base+['mcp'], input=''.join(json.dumps(r)+'\n' for r in requests), capture_output=True, text=True, timeout=20)
        assert mcp.returncode == 0, mcp.stderr
        receipts = [json.loads(line) for line in mcp.stdout.splitlines()]
        assert receipts[-1]['result']['structuredContent']['version'] == '4.0.19-m8' and not receipts[-1]['result']['isError']
        if os.environ.get('CLIPPER_M8_EVIDENCE'):
            folder = Path(os.environ['CLIPPER_M8_EVIDENCE']);folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archive, folder/'DEMO_BUATAN_M8_Handoff.zip')
            evidence = {'scope': 'authored colors/tones/manual transcript; actual local backend; no ASR/model/native editor/live account quality claim',
                'source_content_id': now['source']['source_id'], 'render_content_id': final['output_content_id'], 'M7_package_content_id': package['package_content_id'],
                'M8_handoff_content_id': content_id(archive, fresh=True), 'frozen_project_revision': now['revision'], 'approval_hash': approved['approval']['hash'],
                'handoff_status': result['status'], 'remote_id': result['remote']['remote_id'], 'backup_restore_new_project': True,
                'actual_HTTP': True, 'actual_CLI_subprocess': True, 'actual_MCP_stdio_subprocess': True, 'external_posts_created': 0}
            (folder/'backend-e2e.json').write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
    finally:
        if server:
            server.should_exit = True
        if thread:
            thread.join(timeout=5)
        service.integrations.close();service.queue.close()
