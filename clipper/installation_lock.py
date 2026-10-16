"""OS-owned installation lease; shared runtimes exclude code replacement.

The installer embeds the same class so historical offline packages remain
standalone. No PID file or stale-lock deletion is used.
"""
import os
from pathlib import Path


class InstallationLease:
    def __init__(self, root, exclusive=False):
        self.handle = None
        path = Path(root).resolve()/'.clipper-install.lock'
        try:
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                              wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
                kernel.CreateFileW.restype = wintypes.HANDLE
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel.CreateFileW(str(path), 0x80000000 | (0x40000000 if exclusive else 0),
                                            0 if exclusive else 1, None, 4, 0x80, None)
                if handle == wintypes.HANDLE(-1).value:
                    raise OSError(ctypes.get_last_error(), 'installation lease unavailable')
                self.handle = handle
                self.kernel = kernel
            else:
                import fcntl
                handle = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
                try:
                    fcntl.flock(handle, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                except BaseException:
                    os.close(handle)
                    raise
                self.handle = handle
        except OSError as exc:
            raise ValueError('Instalasi sedang dipakai server/worker atau pemasang. Hentikan semua proses Clipper sebelum upgrade/pemulihan.') from exc

    def close(self):
        handle, self.handle = self.handle, None
        if handle is not None:
            if os.name == 'nt':
                self.kernel.CloseHandle(handle)
            else:
                os.close(handle)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()
