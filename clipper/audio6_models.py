"""Optional Demucs uses an explicit local repository, never the remote default."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
from .dependency_cache import model_identity

def availability(settings,*,fresh=False):
    root=Path(settings['model_directory']).expanduser()
    package=importlib.util.find_spec('demucs')
    weights=list(root.glob('*.th')) if settings['model_directory'] and root.is_dir() else []
    name=settings['model_name'];signatures={p.stem.split('-')[0] for p in weights};selected=name in signatures
    reason=None
    if package and weights and (root/(name+'.yaml')).is_file():
        try:
            import yaml
            bag=yaml.safe_load((root/(name+'.yaml')).read_text(encoding='utf-8'))
            wanted=bag.get('models',[]) if isinstance(bag,dict) else []
            selected=bool(wanted) and all(isinstance(s,str) and s in signatures for s in wanted)
            if not selected:reason='YAML model terpilih tidak mempunyai seluruh bobot .th lokal yang diperlukan.'
        except Exception:
            # A malformed optional local YAML must not break opening the editor.
            selected=False;reason='Metadata YAML model lokal tidak dapat dibaca; model belum tersedia.'
    ok=bool(package and weights and selected)
    return {'backend':'demucs','status':'ready' if ok else 'unavailable',
        'reason':None if ok else reason or 'Pilih model yang tersedia dalam repo Demucs lokal berisi .th/YAML dan pasang runtime Demucs pada environment mesin.',
        'model_name':settings['model_name'],'weights':model_identity(root,fresh=fresh) if weights else [],
        'network_policy':'local repo only; no automatic model download','actual_inference_performed':False}

def separate(source,target_folder,settings):
    state=availability(settings,fresh=True)
    if state['status']!='ready':raise ValueError(state['reason'])
    folder=Path(target_folder);folder.mkdir(parents=True,exist_ok=True)
    request={'source':str(Path(source).resolve()),'directory':str(Path(settings['model_directory']).expanduser().resolve()),
             'model':settings['model_name'],'output':str(folder.resolve())}
    file=folder/'request.json';file.write_text(json.dumps(request))
    result=subprocess.run([sys.executable,'-m','clipper.audio6_models',str(file)],capture_output=True,text=True,timeout=1800)
    if result.returncode:raise ValueError('Pemisahan Demucs lokal gagal: '+result.stderr[-1600:])
    receipt=json.loads((folder/'separation.json').read_text())
    if model_identity(request['directory'],fresh=True)!=state['weights']:raise ValueError('Bobot berubah selama pemisahan; hasil tidak dipakai')
    return {**receipt,'weight_identity':state['weights'],'network_policy':state['network_policy']}

def _run(path):
    import torch
    import numpy as np
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    from demucs.audio import convert_audio
    from .audio6_dsp import decode,write,fixed
    from .audio6_contract import RATE
    data=json.loads(Path(path).read_text());source=decode(data['source']);count=len(source)
    # repo is mandatory: get_model(repo=None) would select RemoteRepo.
    model=get_model(name=data['model'],repo=Path(data['directory']))
    model.to('cpu');model.eval()
    if model.audio_channels not in (1,2):raise ValueError('Model memerlukan channel yang tidak didukung')
    x=convert_audio(torch.from_numpy(source.T.copy()),RATE,model.samplerate,model.audio_channels)
    reference=x.mean(0);mean=reference.mean();std=reference.std()
    scale=std.clamp(min=1e-8);x=(x-mean)/scale
    torch.manual_seed(0)
    with torch.no_grad():stems=apply_model(model,x[None],device='cpu',shifts=0,split=True,overlap=.25,progress=False,num_workers=0,segment=6.)[0]
    names=list(model.sources)
    if 'vocals' not in names:raise ValueError('Model tidak mempunyai stem vocals')
    speech=stems[names.index('vocals')]*scale+mean
    voice=convert_audio(speech,model.samplerate,RATE,2).cpu().numpy().T
    voice=fixed(voice,count);music=source-voice;folder=Path(data['output'])
    result={'backend':'demucs','model_name':data['model'],'actual_inference_performed':True,'device':'cpu',
        'speech':write(folder/'separated-vocals.wav',voice),'music':write(folder/'separated-background.wav',music),
        'sample_rate':RATE,'sample_count':count,'method':'vocals estimate; accompaniment is source minus vocals',
        'quality':'estimated stems; listen against retained original; not a perfect original speech recording'}
    (folder/'separation.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__':_run(sys.argv[1])
