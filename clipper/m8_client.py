"""Dependency-free Python HTTP client; all interfaces use the same command API."""
import json
import os
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit


class ClientError(ValueError):
    def __init__(self, status, receipt):
        self.status = status;self.receipt = receipt
        super().__init__(receipt.get('message', receipt.get('detail', 'Permintaan gagal')))


class Client:
    def __init__(self, url='http://127.0.0.1:8765', token=None):
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.scheme not in ('http', 'https'):
            raise ValueError('URL server harus berupa origin HTTP/HTTPS tanpa credential')
        if parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('Server nonlokal memerlukan HTTPS')
        self.url = url.rstrip('/')
        self.token = token if token is not None else os.environ.get('CLIPPER_M8_TOKEN')

    def post(self, path, value):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer '+self.token
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        if len(body) > 1024**2:
            raise ValueError('Perintah melebihi 1 MiB')
        request = urllib.request.Request(self.url+'/api/studio/m8/v1/'+path, data=body, headers=headers, method='POST')
        # Proxy environment must not capture local commands or bearer credentials.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=60) as response:
                content = response.read(10*1024**2+1)
                if len(content) > 10*1024**2:
                    raise ValueError('Receipt terlalu besar')
                return json.loads(content)
        except urllib.error.HTTPError as exc:
            try:
                receipt = json.loads(exc.read(1024**2))
            except ValueError:
                receipt = {'message': 'Server menolak permintaan'}
            raise ClientError(exc.code, receipt) from None
        except urllib.error.URLError:
            raise ValueError('Server tidak tersedia. Periksa antrean/event sebelum mengulang perintah dengan ID yang sama.') from None

    def command(self, action, args=None, command_id=None):
        return self.post('command', {'schema_version': 1, 'command_id': command_id or str(uuid.uuid4()), 'action': action, 'args': args or {}})
