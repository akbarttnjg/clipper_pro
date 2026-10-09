"""Exercise an external pyCapCut source snapshot with real ffprobe metadata.

The adapter supplies MediaInfo-shaped metadata only; draft construction uses
the real SDK. Native editor import and the installed Windows SDK are separate
acceptance gates. The SDK itself is not included with this project.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import types
import inspect
import os
import shutil
import textwrap
import venv


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sdk',required=True);parser.add_argument('--results',required=True)
    parser.add_argument('--output',required=True);args=parser.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(args.sdk).resolve()))
    class MediaInfo:
        @staticmethod
        def can_parse():return True
        @staticmethod
        def parse(path,**kwargs):
            response=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,check=True)
            info=json.loads(response.stdout);video=[];audio=[]
            for stream in info['streams']:
                row=types.SimpleNamespace(duration=float(stream.get('duration') or info['format']['duration'])*1000,
                    width=stream.get('width'),height=stream.get('height'))
                if stream['codec_type']=='video':video.append(row)
                elif stream['codec_type']=='audio':audio.append(row)
            return types.SimpleNamespace(video_tracks=video,audio_tracks=audio,image_tracks=[],general_tracks=[])
    adapter=types.ModuleType('pymediainfo');adapter.MediaInfo=MediaInfo;sys.modules['pymediainfo']=adapter
    from clipper.config import Config
    from clipper.projects import export_bundle
    from clipper.storage import read_json,write_json
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    results=read_json(args.results)
    cfg=Config(work_dir=str(output/'work'),out_dir=str(output/'clips'),job_id='serializer-qa',use_nvenc=False)
    package=export_bundle(results,cfg,mode='hybrid')
    verification=read_json(Path(package['folder'])/'verification.json')
    report={'sdk':str(Path(args.sdk).resolve()),'metadata_adapter':'Actual ffprobe streams shaped as MediaInfo. No MediaInfo binding used.',
            'native_editor_status':'not_tested','package':package,'verification':verification}
    # Exercise the real isolated child process, not just a mocked runtime path.
    runtime=output/'managed-runtime';generation=runtime/'generations/serializer-fixture';env=generation/'env'
    venv.EnvBuilder(with_pip=False,system_site_packages=True).create(env)
    site=env/('Lib/site-packages' if os.name=='nt' else f'lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages')
    shutil.copytree(Path(args.sdk)/'pycapcut',site/'pycapcut',dirs_exist_ok=True)
    (site/'pymediainfo.py').write_text('import json,subprocess,types\n'+textwrap.dedent(inspect.getsource(MediaInfo)),encoding='utf-8')
    python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    sample=generation/'sample.json'
    subprocess.run([str(python),'-I','-c',
        'import pycapcut as c,sys; s=c.ScriptFile(320,180); s.add_track(c.TrackType.text); s.add_segment(c.TextSegment("sample",c.Timerange(0,1000000))); s.dump(sys.argv[1])',str(sample)],capture_output=True,check=True)
    write_json(generation/'receipt.json',{'installed':True,'test':{'passed':True,'level':'sample','detail':'QA snapshot with ffprobe metadata adapter'}})
    write_json(runtime/'components/pycapcut/active.json',{'generation':'serializer-fixture'})
    sys.path.remove(str(Path(args.sdk).resolve()))
    for name in list(sys.modules):
        if name=='pycapcut' or name.startswith('pycapcut.'):sys.modules.pop(name)
    try:import cv2
    except ImportError:sys.modules['cv2']=types.ModuleType('cv2')
    managed=export_bundle(results,replace(cfg,visual_runtime_root=str(runtime),job_id='managed-serializer-qa'),mode='hybrid')
    manifest=read_json(Path(managed['folder'])/'manifest.json')
    report['managed_worker']={'package':managed,'backend':manifest.get('capcut_backend'),
        'scope':'Real isolated Python and SDK serialization using a QA generation; not the user Windows runtime.'}
    if manifest.get('capcut_backend',{}).get('environment')!='managed_component':raise ValueError('Managed worker was not used.')
    write_json(output/'serializer-report.json',report)
    print(json.dumps({'status':package['structural_status'],'editors':package['editors']},ensure_ascii=False))
    return 0 if package['structural_status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
