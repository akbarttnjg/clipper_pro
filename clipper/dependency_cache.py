"""Content identities and explicit stage dependencies for preview/final reuse."""
import hashlib
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from pathlib import Path
from .contracts import fingerprint

_HASHES={};_LOCK=threading.RLock()
_SCOPE=ContextVar('clipper_content_scope',default=None)
VERSION='studio4-content-v10-measured-phrases'


@contextmanager
def fresh_scope():
    """Read each unchanged file once within one fresh snapshot, never across jobs."""
    if _SCOPE.get() is not None:yield;return
    token=_SCOPE.set({})
    try:yield
    finally:_SCOPE.reset(token)


def active_recipe(recipe, cfg):
    if cfg.broll_mode == 'off':
        return {}
    return {'scenes': [s for s in recipe.get('scenes', []) if s.get('enabled', True)]}


def content_id(path,*,fresh=False):
    p=Path(path).resolve();s=p.stat()
    signature=(str(p),s.st_size,s.st_mtime_ns,s.st_ctime_ns,getattr(s,'st_ino',0))
    scope=_SCOPE.get()
    if scope is not None and signature in scope:return scope[signature]
    with _LOCK:
        if not fresh and signature in _HASHES:return _HASHES[signature]
    digest=hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):digest.update(block)
    after=p.stat()
    if (after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=(s.st_size,s.st_mtime_ns,s.st_ctime_ns):
        raise ValueError('Berkas berubah ketika dibaca; ulangi setelah penyalinan selesai')
    result='sha256:'+digest.hexdigest()
    if scope is not None:scope[signature]=result
    with _LOCK:
        if len(_HASHES)>1024:_HASHES.clear()
        _HASHES[signature]=result
    return result


def asset_id(path,*,fresh=False):
    if not path:return None
    p=Path(path)
    return content_id(p,fresh=fresh) if p.is_file() else 'missing:'+str(p)


def render_key(media,words,clip,cfg,*,fresh=False):
    settings=asdict(cfg)
    irrelevant={'out_dir','work_dir','pexels_key','job_id','ollama_url','model','whisper_model','whisper_device',
        'whisper_compute','whisper_isolate','ollama_timeout','ollama_num_gpu','ollama_num_ctx','num_clips','search_depth',
        'analysis_window_s','analysis_overlap_s','selection_floor','discovery_extra_windows','asr_recheck_windows',
        'asr_second_pass','auto_export','workflow','audio_cache_dir','visual_cache_dir'}
    for key in irrelevant:settings.pop(key,None)
    fonts=[(p.name,content_id(p,fresh=fresh)) for p in sorted(Path(cfg.fonts_dir).glob('*.ttf'))]
    assets=[asset_id(cfg.music_path,fresh=fresh),asset_id(cfg.sfx_path,fresh=fresh)]
    recipe=active_recipe(clip.get('_broll_recipe',{}),cfg)
    for scene in recipe.get('scenes',[]):assets.append(asset_id(scene.get('asset',{}).get('path'),fresh=fresh))
    # Runtime metadata and result paths do not affect rendered pixels.
    candidate={k:v for k,v in clip.items() if k not in ('result','preview','created','updated','_broll_recipe','included')}
    from .caption_renderer import signature
    parts=[VERSION,content_id(media,fresh=fresh),words,candidate,settings,fonts,assets,recipe,signature(cfg)]
    if cfg.align_selected_clips and cfg.alignment_model_path:
        from .runtime.state import signatures,runtime_root
        root=Path(cfg.visual_runtime_root) if cfg.visual_runtime_root else runtime_root()
        model=Path(cfg.alignment_model_path.strip().strip('\"\''))
        parts.append(signatures(root,keys=('whisperx',)))
        parts.append([(p.name,content_id(p,fresh=fresh)) for p in sorted(model.glob('*')) if p.is_file()])
    if cfg.illustration_mode!='off':
        from .explanation5 import STRUCTURES_VERSION
        parts.append(STRUCTURES_VERSION)
    return fingerprint(parts)


def settings_impact(changes):
    asr={'whisper_model','language','whisper_compute','whisper_device','audio_stream_index','asr_second_pass','asr_recheck_windows'}
    selection={'min_clip_s','max_clip_s','search_depth','discovery_extra_windows','model'}
    correction={'audience','glossary','approved_aliases','transcript_correction'}
    stages=[]
    if set(changes)&asr:stages+=['transcription','correction','discovery']
    elif set(changes)&correction:stages+=['correction','discovery']
    elif set(changes)&selection:stages+=['discovery']
    stages+=['preview','render','export'] if changes else []
    return list(dict.fromkeys(stages))
