"""Best-effort process resource measurements with explicit coverage."""
import os
import shutil
import subprocess
import time
from pathlib import Path


class ResourceMeter:
    def __init__(self,pid):
        self.pid=pid;self.started=time.monotonic();self.samples=0;self.peak_rss=None;self.peak_vram=None
        self.gpu_at=0.;self.ram_scope='worker_process';self.gpu_scope='device_total_shared'
        self.proc_path=None
        if os.name=='posix':
            try:
                namespace=os.readlink('/proc/self/ns/pid')
                candidates=[Path('/proc/self')] if pid==os.getpid() else [Path(f'/proc/{pid}'),*Path('/proc').iterdir()]
                for p in candidates:
                    try:
                        if os.readlink(p/'ns/pid')!=namespace:continue
                        ids=next(r for r in (p/'status').read_text().splitlines() if r.startswith('NSpid:'))
                        if int(ids.split()[-1])==pid:self.proc_path=p;break
                    except (OSError,ValueError,StopIteration):continue
            except OSError:pass

    def sample(self):
        self.samples+=1
        try:
            import psutil
            process=psutil.Process(self.pid)
            rss=sum(p.memory_info().rss for p in [process,*process.children(recursive=True)] if p.is_running())
            self.ram_scope='worker_and_children'
        except Exception:
            rss=None
            if os.name=='nt':
                import ctypes
                from ctypes import wintypes
                class Counters(ctypes.Structure):
                    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
                        ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
                         'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
                try:
                    kernel=ctypes.windll.kernel32;kernel.OpenProcess.restype=wintypes.HANDLE
                    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
                    api=ctypes.windll.psapi.GetProcessMemoryInfo;api.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
                    handle=kernel.OpenProcess(0x410,False,self.pid)
                    if handle:
                        try:
                            info=Counters();info.cb=ctypes.sizeof(info)
                            if api(handle,ctypes.byref(info),info.cb):rss=int(info.PeakWorkingSetSize);self.ram_scope='worker_process_peak_working_set'
                        finally:kernel.CloseHandle(handle)
                except (OSError,AttributeError,ValueError):pass
            elif os.name=='posix':
                # The path was resolved once through PID namespace and NSpid.
                if self.proc_path:
                    try:
                        values=dict(line.split(':',1) for line in (self.proc_path/'status').read_text().splitlines() if ':' in line)
                        rss=int(values['VmRSS'].split()[0])*1024
                    except (OSError,ValueError,KeyError):pass
        if rss is not None:self.peak_rss=max(self.peak_rss or 0,rss)
        if time.monotonic()-self.gpu_at>=2 and shutil.which('nvidia-smi'):
            self.gpu_at=time.monotonic()
            try:
                p=subprocess.run(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=1)
                if p.returncode==0:
                    used=sum(int(v.strip()) for v in p.stdout.splitlines())*1024**2
                    self.peak_vram=max(self.peak_vram or 0,used)
            except (OSError,ValueError,subprocess.SubprocessError):pass

    def report(self):
        return {'wall_seconds':round(time.monotonic()-self.started,3),'samples':self.samples,
            'peak_ram_bytes':self.peak_rss,'ram_scope':self.ram_scope,'peak_vram_bytes':self.peak_vram,
            'vram_scope':self.gpu_scope,'sampling':'RAM every queue poll (~0.2 s), VRAM at most every 2 s; short peaks can be missed',
            'missing_measurement':'null means unavailable; zero is never substituted'}
