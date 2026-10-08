"""Optional local Remotion execution of the saved CaptionPlan used by ASS."""
from __future__ import annotations
import base64
import json
import math
import os
from pathlib import Path
import shutil
import subprocess


def browser_path(folder,receipt):
    recorded=receipt.get('test',{}).get('browser_executable')
    if recorded and Path(recorded).is_file():return str(Path(recorded).resolve())
    for name in ('chromium','chromium-browser','google-chrome','chrome'):
        found=shutil.which(name)
        if found:return found
    for base in (folder/'node/.remotion',folder/'node/node_modules/.cache',folder/'node/node_modules/.remotion',folder/'node/.cache'):
        if not base.is_dir():continue
        for name in ('chrome-headless-shell','chrome-headless-shell.exe','chrome','chrome.exe'):
            candidates=sorted(base.rglob(name))
            if candidates and candidates[0].is_file():return str(candidates[0].resolve())
    return None


def readiness(cfg):
    from .runtime.state import runtime_root,safe_path,read
    root=Path(cfg.visual_runtime_root) if cfg.visual_runtime_root else runtime_root()
    try:
        active=read(root/'components/remotion/active.json',{}) or {}
        if not active.get('generation'):raise ValueError('No active generation')
        folder=safe_path(root/'generations',active['generation'])
        receipt=read(folder/'receipt.json',{}) or {};test=receipt.get('test',{})
        node=receipt.get('versions',{}).get('node') or shutil.which('node')
        packages=all((folder/'node/node_modules'/p/'package.json').is_file() for p in ('remotion','@remotion/renderer','@remotion/bundler','react','react-dom'))
        browser=browser_path(folder,receipt)
        if not receipt.get('installed') or not test.get('passed') or test.get('level')!='sample' or not node or not packages or not browser:
            return {'status':'unavailable','reason':'Remotion memerlukan paket renderer, browser lokal, dan uji sampel yang berhasil.'}
        return {'status':'ready','directory':str(folder.resolve()),'node':node,'browser':browser,'generation':active['generation']}
    except (KeyError,ValueError,TypeError,OSError):
        return {'status':'unavailable','reason':'Remotion lokal belum siap. Pasang dan uji komponennya di panel Komponen.'}


def signature(cfg):
    if cfg.caption_renderer=='ass':return ['ass','4.0.7']
    status=readiness(cfg)
    return [cfg.caption_renderer,'4.0.7',status['status'],status.get('generation'),status.get('browser')]


def render(plan,cfg,folder,duration):
    if cfg.caption_renderer=='ass':return {'engine':'ass','status':'ready','plan_version':plan['version']}
    state=readiness(cfg)
    if state['status']!='ready':
        if cfg.caption_renderer=='remotion':raise ValueError(state['reason'])
        return {'engine':'ass','status':'fallback','reason':state['reason']}
    from .font_catalog import FONTS
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    node_root=Path(state['directory'])/'node';project=node_root/'stage5-captions';project.mkdir(exist_ok=True)
    for path in (Path(__file__).parent/'runtime/templates/remotion5').iterdir():shutil.copy2(path,project/path.name)
    fonts={}
    for key in {w['font_id'] for p in plan['phrases'] for w in p['words']}:
        fonts[key]='data:font/ttf;base64,'+base64.b64encode((Path(cfg.fonts_dir)/FONTS[key]['file']).read_bytes()).decode('ascii')
    request=folder/'remotion-request.json';output=folder/'captions.webm'
    request.write_text(json.dumps({'plan':plan,'fonts':fonts,'duration_frames':max(1,math.ceil(duration*cfg.output_fps)),
                                  'fps':cfg.output_fps,'browser':state['browser'],'output':str(output.resolve())},ensure_ascii=False),encoding='utf-8')
    try:
        result=subprocess.run([state['node'],str(project/'render.cjs'),str(request.resolve())],cwd=node_root,capture_output=True,
                              timeout=max(180,cfg.visual_backend_timeout*4),env={**os.environ,'REMOTION_DISABLE_TELEMETRY':'1'})
        (folder/'remotion.log').write_bytes(result.stdout+b'\n'+result.stderr)
        if result.returncode or not output.is_file() or output.stat().st_size<100:raise ValueError('Render Remotion gagal; lihat remotion.log.')
        metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)],timeout=25))
        stream=next((s for s in metadata['streams'] if s.get('codec_type')=='video'),{})
        if stream.get('codec_name')!='vp9' or (stream.get('width'),stream.get('height'))!=(plan['width'],plan['height']) or str(stream.get('tags',{}).get('alpha_mode'))!='1':
            raise ValueError('Output Remotion belum memenuhi ukuran dan alpha VP9 yang diminta.')
        if abs(float(metadata['format']['duration'])-duration)>2/cfg.output_fps:raise ValueError('Durasi overlay Remotion tidak sesuai CaptionPlan.')
        return {'engine':'remotion','status':'ready','path':str(output.resolve()),'generation':state['generation'],'plan_version':plan['version'],'concurrency':1}
    except (OSError,subprocess.TimeoutExpired,ValueError) as exc:
        output.unlink(missing_ok=True)
        if cfg.caption_renderer=='remotion':raise ValueError(str(exc)) from exc
        return {'engine':'ass','status':'fallback','reason':str(exc)}
