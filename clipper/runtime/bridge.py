"""Opt-in production ASR bridge, matching the project's selected model exactly."""
from pathlib import Path
from .state import read, runtime_root, safe_path, digest


def managed_asr(cfg):
    root=runtime_root();pointer=read(root/'components/faster-whisper/active.json',{})
    if not pointer.get('enabled'):return None
    try:
        directory=safe_path(root/'generations',pointer['generation']);receipt=read(directory/'receipt.json',{})
        test=receipt.get('test',{})
        if not receipt.get('installed') or not test.get('passed') or test.get('level')!='sample':return None
        if receipt.get('model_choice')!=cfg.whisper_model:return None
        py=directory/'env'/('Scripts/python.exe' if __import__('os').name=='nt' else 'bin/python')
        if not py.is_file() or not (directory/'weights/model.bin').is_file():return None
        return dict(python=str(py),weights=str(directory/'weights'),generation=pointer['generation'],
                    model_commit=receipt.get('weights',{}).get('commit'),lock_hash=digest(directory/'installed-lock.txt'),
                    recommended_device=read(root/'selected-profile.json',{}).get('device',test.get('device','cpu')))
    except (OSError,KeyError,ValueError):return None
