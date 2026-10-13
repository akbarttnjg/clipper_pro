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
VERSION='studio4-content-v13-m2-reviewed-source-tracks'


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


def model_identity(path, *, fresh=False):
    """Recursive content identity: filenames and generation labels are insufficient."""
    root=Path(path)
    if root.is_file():return [('model',content_id(root,fresh=fresh))]
    if not root.is_dir():return [('missing',str(root))]
    return [(p.relative_to(root).as_posix(),content_id(p,fresh=fresh))
            for p in sorted(root.rglob('*')) if p.is_file()]


def asr_identity(cfg,*,fresh=False):
    provider=getattr(cfg,'asr_provider','faster_whisper')
    if provider=='http':
        import os
        return {'status':'unresolved','provider':'http','endpoint_digest':fingerprint(os.environ.get('CLIPPER_ASR_ENDPOINT','')),'requested_model':cfg.whisper_model}
    if provider=='whisperx':
        from .speech_m2 import _runtime
        try:
            runtime=_runtime(cfg,'whisperx');root=Path(cfg.whisper_model)
            if not (root/'model.bin').is_file():
                root=Path(runtime.get('directory',''))/'weights'
                if runtime.get('receipt',{}).get('model_choice')!=cfg.whisper_model:raise ValueError('Model mismatch')
            if not (root/'model.bin').is_file():raise ValueError('Missing local weights')
            return {'status':'verified','provider':provider,'weights':model_identity(root,fresh=fresh),'generation':runtime['generation'],
                'alignment':model_identity(cfg.alignment_model_path,fresh=fresh)}
        except (ImportError,ValueError,OSError):return {'status':'unresolved','provider':provider,'requested_model':cfg.whisper_model}
    from .runtime.bridge import managed_asr
    managed=managed_asr(cfg) if cfg.whisper_isolate else None
    root=Path(managed['weights']) if managed else Path(cfg.whisper_model).expanduser()
    if not root.is_dir() or not (root/'model.bin').is_file():
        try:
            from .speech_jobs import _asr_model_path
            root=Path(_asr_model_path(cfg.whisper_model))
        except (ImportError,ValueError,OSError,RuntimeError):
            return {'status':'unresolved','requested_model':cfg.whisper_model}
    if not root.is_dir() or not (root/'model.bin').is_file():return {'status':'unresolved','requested_model':cfg.whisper_model}
    result={'status':'verified','weights':model_identity(root,fresh=fresh)}
    if managed:result['managed']={k:managed[k] for k in ('generation','model_commit','lock_hash','recommended_device')}
    return result


def alignment_identity(cfg, *, fresh=False):
    if not cfg.align_selected_clips:return []
    from .runtime.state import signatures,runtime_root,read,safe_path
    root=Path(cfg.visual_runtime_root) if cfg.visual_runtime_root else runtime_root()
    identity=list(signatures(root,keys=('whisperx',)))
    model=cfg.alignment_model_path.strip().strip('\"\'')
    if model:identity.append(['selected_model',model_identity(model,fresh=fresh)])
    active=read(root/'components/whisperx/active.json',{}) or {}
    if active.get('generation'):
        directory=safe_path(root/'generations',active['generation'])
        identity.append(['generation_weights',model_identity(directory/'weights',fresh=fresh)])
    return identity


def component_identity(root,keys,*,fresh=False):
    """Active local weights participate even when receipt and mtimes stay unchanged."""
    from .runtime.state import signatures,read,safe_path
    root=Path(root);items=list(signatures(root,keys=keys))
    for key in keys:
        active=read(root/'components'/key/'active.json',{}) or {}
        if active.get('generation'):
            folder=safe_path(root/'generations',active['generation'])
            items.append([key,'weights',model_identity(folder/'weights',fresh=fresh)])
    return items


def render_key(media,words,clip,cfg,*,fresh=False):
    settings=asdict(cfg)
    irrelevant={'asr_provider','vad_policy','output_language','diarization_model_path','out_dir','work_dir','pexels_key','job_id','ollama_url','model','whisper_model','whisper_device',
        'whisper_compute','whisper_isolate','ollama_timeout','ollama_num_gpu','ollama_num_ctx','num_clips','search_depth',
        'analysis_window_s','analysis_overlap_s','selection_floor','discovery_extra_windows','asr_recheck_windows',
        'asr_second_pass','auto_export','workflow','audio_cache_dir','visual_cache_dir','cache_limit_gb',
        'variant_id','visual_runtime_signature','source_content_id','audio_stream_id'}
    if not cfg.align_selected_clips:irrelevant.add('alignment_model_path')
    if not cfg.use_nvenc:irrelevant.add('allow_backend_fallback')
    for key in irrelevant:settings.pop(key,None)
    fonts=[(p.name,content_id(p,fresh=fresh)) for p in sorted(Path(cfg.fonts_dir).glob('*.ttf'))]
    assets=[asset_id(cfg.music_path,fresh=fresh),asset_id(cfg.sfx_path,fresh=fresh)]
    recipe=active_recipe(clip.get('_broll_recipe',{}),cfg)
    for scene in recipe.get('scenes',[]):assets.append(asset_id(scene.get('asset',{}).get('path'),fresh=fresh))
    # Runtime metadata and result paths do not affect rendered pixels.
    candidate={k:v for k,v in clip.items() if k not in ('result','preview','created','updated','_broll_recipe','included','revision','variants')}
    from .caption_renderer import signature
    parts=[VERSION,content_id(media,fresh=fresh),words,candidate,settings,fonts,assets,recipe,signature(cfg)]
    parts.append(alignment_identity(cfg,fresh=fresh))
    if cfg.visual_enabled:
        from .runtime.state import signatures,runtime_root
        root=Path(cfg.visual_runtime_root) if cfg.visual_runtime_root else runtime_root()
        parts.append(component_identity(root,('yunet','rapidocr','talknet','smolvlm','qwen3-vl','sam2','mediapipe'),fresh=fresh))
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
