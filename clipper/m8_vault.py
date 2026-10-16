"""Secrets at rest: Windows user DPAPI, or an externally provisioned AES-GCM key.

No plaintext fallback, key generation alongside ciphertext, or credential export.
"""
import base64
import ctypes
import json
import os
import re
import uuid
from pathlib import Path
from .m8_contract import canonical


class Vault:
    def __init__(self, root):
        self.root = Path(root) / '.credentials8'

    def _path(self, key):
        if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{32}', key):
            raise ValueError('Referensi credential tidak valid')
        return self.root / (key + '.bin')

    def _aes(self):
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            value = base64.b64decode(os.environ.get('CLIPPER_M8_VAULT_KEY', ''), validate=True)
            if len(value) != 32:
                raise ValueError()
            return AESGCM(value)
        except (ImportError, ValueError):
            raise ValueError('Vault belum siap. Windows memakai DPAPI; host lain memerlukan cryptography dan CLIPPER_M8_VAULT_KEY dari pengelola host.') from None

    @staticmethod
    def _dpapi(data, decrypt=False):
        from ctypes import wintypes
        class Blob(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
        buffer = ctypes.create_string_buffer(data)
        incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        outgoing = Blob()
        api = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
        api.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        api.restype = wintypes.BOOL
        if not api(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
            raise ValueError('DPAPI gagal; jalankan dengan akun Windows pemilik credential')
        try:
            return ctypes.string_at(outgoing.data, outgoing.size)
        finally:
            ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            ctypes.windll.kernel32.LocalFree(outgoing.data)

    def ready(self):
        try:
            if os.name != 'nt':
                self._aes()
            return {'ready': True, 'backend': 'windows-user-dpapi' if os.name == 'nt' else 'external-key-aes256gcm'}
        except ValueError:
            return {'ready': False, 'backend': 'not_configured'}

    def put(self, value, key=None):
        key = key or uuid.uuid4().hex
        path = self._path(key)
        raw = canonical(value).encode()
        if os.name == 'nt':
            data = b'DP8\x00' + self._dpapi(raw)
        else:
            nonce = os.urandom(12)
            data = b'AE8\x00' + nonce + self._aes().encrypt(nonce, raw, key.encode())
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink():
            raise ValueError('Folder vault tidak boleh symlink')
        temporary = self.root / (key + '.' + uuid.uuid4().hex + '.tmp')
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return key

    def get(self, key):
        path = self._path(key)
        if path.is_symlink():
            raise ValueError('Credential tidak boleh symlink')
        data = path.read_bytes()
        try:
            if data.startswith(b'DP8\x00') and os.name == 'nt':
                raw = self._dpapi(data[4:], True)
            elif data.startswith(b'AE8\x00'):
                raw = self._aes().decrypt(data[4:16], data[16:], key.encode())
            else:
                raise ValueError()
            return json.loads(raw)
        except Exception:
            raise ValueError('Credential tidak dapat dibuka pada host/akun ini; hubungkan ulang akun') from None

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)
