"""Account metadata has no bearer tokens. OAuth uses a temporary loopback listener."""
import base64
import hashlib
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
from .m8_contract import PLATFORMS, SCOPES, canonical, integer, only, text
from .m8_store import ident
from .m8_youtube import checked
from .project_store import Conflict


class Accounts:
    def __init__(self, m8):
        self.m8 = m8
        self.flows = {}

    def get(self, actor, key, *, private=False):
        self.m8.workspaces.require(actor)
        with self.m8.service.store.connect() as db:
            row = db.execute('SELECT * FROM m8_accounts WHERE id=? AND workspace=?', (key, actor.workspace)).fetchone()
        if not row:
            raise KeyError('Akun tidak ditemukan')
        value = {k: row[k] for k in ('id', 'platform', 'name', 'version', 'enabled')}
        value['data'] = json.loads(row['data'])
        value['connection'] = 'oauth' if row['secret_ref'] else 'handoff'
        value['capabilities'] = self.capabilities(value)
        if private:
            value['_secret_ref'] = row['secret_ref']
        return value

    def listing(self, actor):
        self.m8.workspaces.require(actor)
        with self.m8.service.store.connect() as db:
            keys = [r[0] for r in db.execute('SELECT id FROM m8_accounts WHERE workspace=? ORDER BY name', (actor.workspace,))]
        return [self.get(actor, key) for key in keys]

    @staticmethod
    def capabilities(account):
        connected = account['platform'] == 'youtube' and account['connection'] == 'oauth' and bool(account['enabled'])
        scopes = set(account['data'].get('scopes', []))
        can_upload = connected and SCOPES['upload'] in scopes
        can_manage = connected and bool({SCOPES['manage'], 'https://www.googleapis.com/auth/youtube'} & scopes)
        return {'handoff': True, 'upload': can_upload, 'remote_schedule': can_upload,
                'remote_edit': can_manage, 'remote_cancel_to_private': can_manage,
                'statistics': connected, 'period_analytics': connected and SCOPES['analytics'] in scopes,
                'thumbnail_upload': False, 'subtitle_upload': False, 'native_acceptance': 'not_tested',
                'reason': None if can_upload else 'Akun/API belum tersambung; paket handoff lokal tersedia.'}

    def save(self, actor, data, *, credentials=None):
        self.m8.workspaces.require(actor, 'manage')
        only(data, ('id', 'expected_version', 'platform', 'name', 'remote_id', 'enabled', 'scopes', 'expires_at'), ('platform', 'name'))
        platform = data['platform']
        if platform not in PLATFORMS:
            raise ValueError('Platform tidak dikenal')
        key = data.get('id') or ident('account')
        name = text(data['name'], 'Nama akun', 160)
        remote_id = text(data.get('remote_id', ''), 'Identitas remote', 200, 0)
        enabled = data.get('enabled', True)
        if type(enabled) is not bool:
            raise ValueError('Status akun harus boolean')
        prior = self.get(actor, key, private=True) if data.get('id') else None
        if prior and prior['version'] != data.get('expected_version'):
            raise Conflict(prior['version'])
        if prior and prior['platform'] != platform:
            raise ValueError('Platform akun tidak dapat diubah; buat profil baru')
        info = {'remote_id': remote_id, 'scopes': [], 'expires_at': None, 'probed_at': None}
        reference = None
        if credentials:
            if platform != 'youtube' or not isinstance(credentials.get('access_token'), str):
                raise ValueError('Credential OAuth tidak valid')
            info.update(scopes=credentials['scopes'], expires_at=credentials['expires_at'])
            reference = self.m8.vault.put(credentials)
        elif prior:
            info.update(prior['data']);info['remote_id'] = remote_id
            reference = prior['_secret_ref']
        # Arbitrary caller claims of granted scopes/token expiry are never trusted.
        with self.m8.db.transaction() as db:
            if prior:
                row = db.execute('SELECT version FROM m8_accounts WHERE id=? AND workspace=?', (key, actor.workspace)).fetchone()
                if row['version'] != data['expected_version']:
                    raise Conflict(row['version'])
            version = prior['version']+1 if prior else 0
            db.execute('INSERT INTO m8_accounts VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,version=excluded.version,data=excluded.data,secret_ref=excluded.secret_ref,enabled=excluded.enabled',
                (key, actor.workspace, platform, name, version, canonical(info), reference, int(enabled)))
            self.m8.db.event(db, actor.workspace, 'account.saved', data={'id': key, 'platform': platform, 'version': version})
        if prior and credentials and prior['_secret_ref']:
            self.m8.vault.delete(prior['_secret_ref'])
        return self.get(actor, key)

    def probe(self, actor, key):
        self.m8.workspaces.require(actor, 'manage')
        account = self.get(actor, key, private=True)
        if account['connection'] != 'oauth':
            return {'ready': False, 'mode': 'handoff', 'capabilities': account['capabilities']}
        result = self.m8.youtube.probe(account)
        with self.m8.db.transaction() as db:
            row = db.execute('SELECT data FROM m8_accounts WHERE id=?', (key,)).fetchone()
            info = json.loads(row['data']);info['probed_at'] = result['checked_at']
            db.execute('UPDATE m8_accounts SET data=? WHERE id=?', (canonical(info), key))
            self.m8.db.event(db, actor.workspace, 'account.probed', data={'id': key, 'remote_id': result['remote_id']})
        return {'ready': True, 'mode': 'youtube_resumable', **result}

    def disconnect(self, actor, key, version):
        self.m8.workspaces.require(actor, 'manage')
        row = self.get(actor, key, private=True)
        if version != row['version']:
            raise Conflict(row['version'])
        with self.m8.db.transaction() as db:
            result = db.execute('UPDATE m8_accounts SET enabled=0,secret_ref=NULL,version=version+1 WHERE id=? AND workspace=? AND version=?', (key, actor.workspace, version))
            if result.rowcount != 1:
                raise Conflict(self.get(actor, key)['version'])
            self.m8.db.event(db, actor.workspace, 'account.disconnected', data={'id': key})
        if row['_secret_ref']:
            self.m8.vault.delete(row['_secret_ref'])
        return {'id': key, 'disconnected': True}

    def oauth_start(self, actor, data):
        self.m8.workspaces.require(actor, 'manage')
        only(data, ('client_id', 'client_secret', 'name', 'manage_remote'), ('client_id', 'name'))
        if not self.m8.vault.ready()['ready']:
            raise ValueError('Siapkan vault sebelum menghubungkan akun')
        if len([v for v in self.flows.values() if v['status'] == 'waiting']) >= 3:
            raise ValueError('Selesaikan proses koneksi yang masih terbuka')
        client_id = text(data['client_id'], 'Google Desktop OAuth client ID', 300)
        if not client_id.endswith('.apps.googleusercontent.com'):
            raise ValueError('Gunakan client ID OAuth bertipe Desktop dari Google Cloud')
        client_secret = text(data.get('client_secret', ''), 'Client secret', 500, 0)
        name = text(data['name'], 'Nama profil', 160)
        manage = data.get('manage_remote', False)
        if type(manage) is not bool:
            raise ValueError('Pilihan manage harus boolean')
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        state = secrets.token_urlsafe(32)
        key = ident('oauth')
        flow = {'id': key, 'status': 'waiting', 'expires': self.m8.db.clock()+600, 'actor': actor}
        accounts = self
        class Receiver(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                parsed = urlsplit(self.path)
                query = parse_qs(parsed.query)
                valid = parsed.path == '/callback' and query.get('state') == [state] and len(query.get('code', [])) == 1 and flow['status'] == 'waiting' and flow['expires'] > accounts.m8.db.clock()
                if not valid:
                    self.send_response(400);self.end_headers();self.wfile.write(b'Callback tidak valid.');return
                flow['status'] = 'exchanging'
                try:
                    accounts.m8.workspaces.require(actor, 'manage')
                    response = checked(accounts.m8.transport.request('POST', 'https://oauth2.googleapis.com/token', data={
                        'client_id': client_id, 'client_secret': client_secret, 'code': query['code'][0],
                        'code_verifier': verifier, 'redirect_uri': redirect, 'grant_type': 'authorization_code'})).json()
                    scopes = str(response.get('scope', '')).split()
                    if SCOPES['upload'] not in scopes:
                        raise ValueError('Izin unggah tidak diberikan')
                    temporary = {'access_token': response['access_token'], 'refresh_token': response.get('refresh_token'),
                        'expires_at': accounts.m8.db.clock()+float(response.get('expires_in', 3600)),
                        'client_id': client_id, 'client_secret': client_secret, 'scopes': scopes}
                    result = checked(accounts.m8.transport.request('GET', 'https://www.googleapis.com/youtube/v3/channels',
                        headers={'Authorization': 'Bearer '+temporary['access_token']}, params={'part': 'id,snippet', 'mine': 'true', 'maxResults': 50})).json()
                    rows = result.get('items', [])
                    if len(rows) != 1:
                        raise ValueError('Pilih satu channel tujuan pada akun Google, lalu hubungkan kembali')
                    saved = accounts.save(actor, {'platform': 'youtube', 'name': name, 'remote_id': rows[0]['id']}, credentials=temporary)
                    flow.update(status='connected', account_id=saved['id'])
                    message = 'Akun tersambung. Tutup tab ini dan kembali ke Clipper.'
                except Exception:
                    flow.update(status='failed', error='Koneksi gagal; periksa client Desktop, consent, dan izin channel lalu coba kembali.')
                    message = flow['error']
                self.send_response(200);self.send_header('Content-Type', 'text/plain; charset=utf-8');self.send_header('Cache-Control', 'no-store');self.end_headers();self.wfile.write(message.encode())
        listener = HTTPServer(('127.0.0.1', 0), Receiver)
        listener.timeout = 1
        redirect = 'http://127.0.0.1:'+str(listener.server_port)+'/callback'
        scopes = [SCOPES[k] for k in ('upload', 'read', 'analytics')] + ([SCOPES['manage']] if manage else [])
        url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({'client_id': client_id, 'redirect_uri': redirect,
            'response_type': 'code', 'scope': ' '.join(scopes), 'state': state, 'code_challenge': challenge,
            'code_challenge_method': 'S256', 'access_type': 'offline', 'prompt': 'consent'})
        self.flows[key] = flow
        def run():
            try:
                while flow['status'] == 'waiting' and flow['expires'] > self.m8.db.clock():
                    listener.handle_request()
                if flow['status'] == 'waiting':
                    flow['status'] = 'expired'
            finally:
                listener.server_close()
        threading.Thread(target=run, daemon=True, name='m8-oauth-loopback').start()
        return {'id': key, 'url': url, 'expires': flow['expires'], 'redirect_uri': redirect}

    def oauth_status(self, actor, key):
        self.m8.workspaces.require(actor, 'manage')
        flow = self.flows.get(key)
        if not flow or flow['actor'].workspace != actor.workspace or flow['actor'].user_id != actor.user_id:
            raise KeyError('Proses koneksi tidak ditemukan')
        return {k: v for k, v in flow.items() if k in ('id', 'status', 'expires', 'account_id', 'error')}

    def close(self):
        for value in self.flows.values():
            if value['status'] == 'waiting':
                value['status'] = 'canceled'
