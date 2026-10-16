"""YouTube REST adapter. Persist session before sending bytes; reconcile first.

All endpoint hosts are fixed. Requests never follow redirects or log responses.
Live account/API acceptance is separate from offline protocol-fixture tests.
"""
import re
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from .m8_contract import SCOPES


class NetworkFailure(ValueError):
    pass


class RemoteFailure(ValueError):
    def __init__(self, status, reason='remote_error'):
        self.status = status
        self.reason = reason
        super().__init__('Platform mengembalikan HTTP ' + str(status) + ' (' + reason + ')')


class Transport:
    HOSTS = {'www.googleapis.com', 'oauth2.googleapis.com', 'youtubeanalytics.googleapis.com'}

    def request(self, method, url, **kwargs):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in self.HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError('Tujuan API tidak diizinkan')
        try:
            import requests
            if 'content' in kwargs:
                kwargs['data'] = kwargs.pop('content')
            with requests.Session() as client:
                client.trust_env = False
                with client.request(method, url, timeout=(10,30), allow_redirects=False, stream=True, **kwargs) as response:
                    parts = []
                    size = 0
                    for part in response.iter_content(65536):
                        size += len(part)
                        if size > 2*1024**2:
                            raise NetworkFailure('Respons API terlalu besar')
                        parts.append(part)
                    class Reply:
                        def __init__(self, status, headers, data):
                            self.status_code=status;self.headers=headers;self.data=data
                        def json(self):
                            return json.loads(self.data)
                    return Reply(response.status_code, response.headers, b''.join(parts))
        except (ImportError, OSError, TimeoutError) as exc:
            raise NetworkFailure('Jaringan atau dependency HTTP belum tersedia; status remote harus diperiksa') from None
        except Exception as exc:
            if isinstance(exc, (NetworkFailure, ValueError)):
                raise
            raise NetworkFailure('Koneksi terputus; rekonsiliasi diperlukan sebelum mencoba ulang') from None


def checked(response, accepted=(200,)):
    if response.status_code not in accepted:
        reason = 'remote_error'
        try:
            found = response.json().get('error', {}).get('errors', [{}])[0].get('reason')
            if found in {'quotaExceeded', 'dailyLimitExceeded', 'forbidden', 'insufficientPermissions', 'invalidCredentials', 'notFound', 'uploadLimitExceeded', 'rateLimitExceeded'}:
                reason = found
        except (ValueError, AttributeError, IndexError, TypeError):
            pass
        raise RemoteFailure(response.status_code, reason)
    return response


def session_uri(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.hostname != 'www.googleapis.com' or parsed.path != '/upload/youtube/v3/videos' or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment:
        raise ValueError('Lokasi sesi upload tidak diizinkan')
    if 'upload_id=' not in parsed.query:
        raise ValueError('Identitas sesi upload hilang')
    return value


def video_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{6,64}', value):
        raise ValueError('Remote video ID belum terverifikasi')
    return value


class YouTube:
    def __init__(self, m8):
        self.m8 = m8

    def credentials(self, account):
        value = self.m8.vault.get(account['_secret_ref'])
        if value.get('expires_at', 0) <= self.m8.db.clock() + 60:
            if not value.get('refresh_token'):
                raise ValueError('Token berakhir; hubungkan ulang akun')
            response = self.m8.transport.request('POST', 'https://oauth2.googleapis.com/token', data={
                'grant_type': 'refresh_token', 'refresh_token': value['refresh_token'],
                'client_id': value['client_id'], 'client_secret': value.get('client_secret', '')})
            refreshed = checked(response).json()
            if not isinstance(refreshed.get('access_token'), str):
                raise ValueError('Token baru tidak tersedia')
            value.update(access_token=refreshed['access_token'], expires_at=self.m8.db.clock()+float(refreshed.get('expires_in', 3600)))
            if refreshed.get('refresh_token'):
                value['refresh_token'] = refreshed['refresh_token']
            self.m8.vault.put(value, account['_secret_ref'])
            with self.m8.db.transaction() as db:
                row = db.execute('SELECT data FROM m8_accounts WHERE id=?', (account['id'],)).fetchone()
                import json
                data = json.loads(row['data']);data['expires_at'] = value['expires_at']
                db.execute('UPDATE m8_accounts SET data=? WHERE id=?', (json.dumps(data), account['id']))
        return value

    def request(self, account, method, url, **kwargs):
        value = self.credentials(account)
        headers = dict(kwargs.pop('headers', {}))
        headers['Authorization'] = 'Bearer ' + value['access_token']
        return self.m8.transport.request(method, url, headers=headers, **kwargs)

    def probe(self, account):
        response = checked(self.request(account, 'GET', 'https://www.googleapis.com/youtube/v3/channels',
            params={'part': 'id,snippet', 'mine': 'true', 'maxResults': 50})).json()
        match = next((r for r in response.get('items', []) if r.get('id') == account['data'].get('remote_id')), None)
        if not match:
            raise ValueError('Token tidak memiliki channel tujuan yang dipilih')
        return {'remote_id': match['id'], 'name': match.get('snippet', {}).get('title', ''), 'checked_at': self.m8.db.clock()}

    def begin(self, account, request, path):
        meta = request['metadata']
        remote_schedule = request['remote_schedule']
        status = {'privacyStatus': 'private' if remote_schedule else meta['privacy'], 'selfDeclaredMadeForKids': meta['made_for_kids']}
        if remote_schedule:
            if not request['schedule']['utc'] or request['schedule']['utc'] <= self.m8.db.clock():
                raise ValueError('Jadwal remote harus berada di masa depan')
            status['publishAt'] = datetime.fromtimestamp(request['schedule']['utc'], timezone.utc).isoformat().replace('+00:00', 'Z')
        snippet = {'title': meta['title'], 'description': meta['description'], 'tags': meta['tags'], 'categoryId': meta['category_id']}
        response = checked(self.request(account, 'POST', 'https://www.googleapis.com/upload/youtube/v3/videos',
            params={'uploadType': 'resumable', 'part': 'snippet,status,contentDetails'},
            headers={'X-Upload-Content-Length': str(path.stat().st_size), 'X-Upload-Content-Type': 'video/mp4'},
            json={'snippet': snippet, 'status': status}), (200, 201))
        return session_uri(response.headers.get('location', ''))

    def upload_status(self, account, uri, total):
        response = self.request(account, 'PUT', session_uri(uri), headers={'Content-Length': '0', 'Content-Range': 'bytes */'+str(total)}, content=b'')
        return self.progress(response, total)

    @staticmethod
    def progress(response, total):
        if response.status_code in (200, 201):
            value = response.json()
            return {'complete': True, 'remote_id': video_id(value.get('id')), 'offset': total}
        checked(response, (308,))
        header = response.headers.get('range', '')
        if not header:
            return {'complete': False, 'offset': 0}
        match = re.fullmatch(r'bytes=0-(\d+)', header)
        if not match or not 0 < int(match[1])+1 <= total:
            raise ValueError('Range upload dari platform tidak valid')
        return {'complete': False, 'offset': int(match[1])+1}

    def chunk(self, account, uri, path, offset, chunk_size=8*1024**2, expected_chunks=None):
        total = path.stat().st_size
        if not 0 <= offset < total:
            raise ValueError('Offset unggahan tidak valid')
        with path.open('rb') as source:
            aligned = offset//chunk_size*chunk_size
            source.seek(aligned)
            whole = source.read(chunk_size)
        if expected_chunks is not None and (offset//chunk_size >= len(expected_chunks) or hashlib.sha256(whole).hexdigest() != expected_chunks[offset//chunk_size]):
            raise ValueError('Isi chunk berbeda dari file yang disetujui')
        block = whole[offset-aligned:]
        response = self.request(account, 'PUT', session_uri(uri),
            headers={'Content-Type': 'video/mp4', 'Content-Length': str(len(block)),
                     'Content-Range': 'bytes '+str(offset)+'-'+str(offset+len(block)-1)+'/'+str(total)}, content=block)
        return self.progress(response, total)

    def poll(self, account, remote_id):
        remote_id = video_id(remote_id)
        result = checked(self.request(account, 'GET', 'https://www.googleapis.com/youtube/v3/videos',
            params={'part': 'status,processingDetails,snippet,statistics', 'id': remote_id})).json()
        row = next((r for r in result.get('items', []) if r.get('id') == remote_id), None)
        if not row:
            raise ValueError('Video remote belum ditemukan; unggahan baru tidak akan dibuat otomatis')
        status = row.get('status', {})
        return {'id': remote_id, 'privacy': status.get('privacyStatus'), 'publish_at': status.get('publishAt'),
                'upload_status': status.get('uploadStatus'), 'processing_status': row.get('processingDetails', {}).get('processingStatus'),
                'url': 'https://www.youtube.com/watch?v='+remote_id, 'snippet': row.get('snippet', {}), 'statistics': row.get('statistics', {}),
                'checked_at': self.m8.db.clock()}

    def change(self, account, remote_id, *, cancel=False, metadata=None):
        if not ({SCOPES['manage'], 'https://www.googleapis.com/auth/youtube'} & set(account['data'].get('scopes', []))):
            raise ValueError('Izin perubahan remote belum diberikan; gunakan YouTube Studio atau hubungkan ulang dengan izin manage')
        before = self.poll(account, remote_id)
        if cancel:
            payload = {'id': remote_id, 'status': {'privacyStatus': 'private'}}
            part = 'status'
        else:
            old = before['snippet']
            snippet = {k: old[k] for k in ('categoryId', 'defaultLanguage', 'defaultAudioLanguage') if k in old}
            snippet.update(title=metadata['title'], description=metadata['description'], tags=metadata['tags'])
            if 'categoryId' not in snippet:
                snippet['categoryId'] = metadata['category_id']
            payload = {'id': remote_id, 'snippet': snippet};part = 'snippet'
        checked(self.request(account, 'PUT', 'https://www.googleapis.com/youtube/v3/videos', params={'part': part}, json=payload))
        return self.poll(account, remote_id)

    def analytics(self, account, remote_id, start, end):
        if SCOPES['analytics'] not in account['data'].get('scopes', []):
            return {'available': False, 'reason': 'scope_analytics_not_granted', 'values': {}}
        response = checked(self.request(account, 'GET', 'https://youtubeanalytics.googleapis.com/v2/reports', params={
            'ids': 'channel==MINE', 'startDate': start, 'endDate': end, 'filters': 'video=='+video_id(remote_id),
            'metrics': 'views,likes,comments,shares,estimatedMinutesWatched,averageViewDuration,averageViewPercentage'})).json()
        headers = [r.get('name') for r in response.get('columnHeaders', [])]
        rows = response.get('rows', [])
        if len(rows) != 1 or len(rows[0]) != len(headers):
            return {'available': False, 'reason': 'platform_has_no_period_data', 'values': {}}
        return {'available': True, 'reason': None, 'values': dict(zip(headers, rows[0]))}
