"""Official-source plans, isolated installers and content locks.

All network metadata is read only when the user queues an install. Existing
environments are never upgraded by this module. A generation is exposed only
after files and package installation have completed.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from .catalog import get
from .download import fetch, Canceled
from .state import read, write, safe_path, digest

AGENT='Clipper-Studio/4.0.2'


def api(url, *, token=None, body=None):
    headers={'User-Agent':AGENT,'Accept':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    data=None if body is None else json.dumps(body).encode()
    if data is not None:headers['Content-Type']='application/json'
    with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=headers),timeout=40) as response:
        return json.load(response)


def stable_package(spec):
    if '==' in spec:return spec
    data=api('https://pypi.org/pypi/'+urllib.parse.quote(spec,safe='')+'/json')
    version=data['info']['version']
    if re.search(r'(?:a|b|rc|dev)\d',version):
        versions=[v for v,files in data.get('releases',{}).items() if files and not re.search(r'(?:a|b|rc|dev)\d',v) and any(not f.get('yanked') for f in files)]
        versions.sort(key=lambda v:tuple(int(n) for n in re.findall(r'\d+',v)))
        if not versions:raise ValueError('Tidak ada rilis stabil untuk '+spec)
        version=versions[-1]
    return spec+'=='+version


def source_plan(item):
    repo=item['repo'];token=os.environ.get('GITHUB_TOKEN')
    commit=api('https://api.github.com/repos/'+repo+'/commits/HEAD',token=token)['sha']
    tree=api('https://api.github.com/repos/'+repo+'/git/trees/'+commit+'?recursive=1',token=token)
    if tree.get('truncated'):raise ValueError('Daftar sumber terpotong; pemasangan tidak diteruskan')
    files=[]
    for row in tree['tree']:
        name=row['path'];suffix=Path(name).suffix.lower();key=item['id']
        if row['type']!='blob' or row.get('mode')=='120000':continue
        selected=(key in ('remotion-skills','opus-skill') and suffix in ('.md','.json','.sh','.py','.txt')) or \
                 (key=='talknet' and (name.startswith('model/') and suffix=='.py' or name in ('loss.py','README.md','LICENSE','requirement.txt'))) or \
                 (key=='sam2' and (name.startswith('sam2/') and suffix in ('.py','.yaml','.yml') or name in ('LICENSE','README.md','INSTALL.md'))) or \
                 (key=='yunet' and name in ('models/face_detection_yunet/face_detection_yunet_2023mar.onnx','LICENSE'))
        if selected:files.append(dict(path='source/'+name,url='https://raw.githubusercontent.com/'+repo+'/'+commit+'/'+urllib.parse.quote(name,safe='/'),
                                      hash=row['sha'],algorithm='git-sha1',size=row.get('size')))
    if not files:raise ValueError('Tidak ada berkas sumber yang sesuai resep')
    return dict(repo=repo,commit=commit,files=files)


def model_plan(model, token=None):
    data=api('https://huggingface.co/api/models/'+model+'?blobs=true',token=token)
    commit=data['sha'];files=[]
    for row in data.get('siblings',[]):
        name=row['rfilename'];suffix=Path(name).suffix.lower()
        # Never execute remote Python model code; select one weight format.
        if suffix not in ('.json','.txt','.model','.safetensors','.bin','.pt','.yaml','.yml','.tiktoken','.jinja') and name not in ('README.md','LICENSE','LICENSE.md'):continue
        if any(part in ('onnx','openvino','coreml','tf','flax') for part in Path(name).parts):continue
        if suffix=='.bin' and any(x['rfilename'].endswith('.safetensors') for x in data['siblings']):continue
        if name.startswith(('optimizer','training_args','rng_state')):continue
        lfs=row.get('lfs') or {};hash_=lfs.get('sha256') or row.get('blobId')
        if not hash_:raise ValueError('Sumber tidak menyediakan hash model: '+name)
        files.append(dict(path='weights/'+name,url='https://huggingface.co/'+model+'/resolve/'+commit+'/'+urllib.parse.quote(name,safe='/'),
                          hash=hash_,algorithm='sha256' if lfs else 'git-sha1',size=lfs.get('size',row.get('size'))))
    if not files:raise ValueError('Bobot model belum tersedia melalui akun ini')
    return dict(repo=model,commit=commit,files=files)


def choose_python():
    # Original research tools do not all support Python 3.13+.
    if (3,10)<=sys.version_info[:2]<=(3,12):return [sys.executable]
    if os.name=='nt' and shutil.which('py'):
        for version in ('3.11','3.12','3.10'):
            r=subprocess.run(['py','-'+version,'-c','import sys;print(sys.executable)'],capture_output=True,text=True,timeout=15)
            if r.returncode==0 and Path(r.stdout.strip()).is_file():return [r.stdout.strip()]
    raise ValueError('Komponen riset membutuhkan Python 3.10–3.12. Pasang Python 3.11 berdampingan; lingkungan utama tetap tersedia.')


def run(command, manager, jid, *, cwd=None, env=None, timeout=1800):
    manager.update(jid,message='Menjalankan '+Path(str(command[0])).name+' (lihat log untuk detail)')
    if manager.canceled(jid):raise Canceled('Proses dibatalkan')
    start=time.monotonic()
    proc=subprocess.Popen([str(x) for x in command],cwd=cwd,env=env,stdout=None,stderr=None)
    try:
        while proc.poll() is None:
            if manager.canceled(jid):raise Canceled('Proses dibatalkan; cache dan rencana pemasangan disimpan')
            if time.monotonic()-start>timeout:raise TimeoutError('Batas waktu proses tercapai; dapat dilanjutkan')
            time.sleep(.15)
        if proc.returncode:raise RuntimeError(Path(str(command[0])).name+' berhenti dengan kode '+str(proc.returncode)+'. Periksa log komponen; lingkungan utama tidak berubah.')
    except BaseException:
        proc.terminate()
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
        raise


def interpreter(directory):
    return Path(directory)/'env'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')


def plan(manager,job,directory):
    existing=read(directory/'plan.json')
    if existing:return existing
    item=get(job['component']);options=job['options'];packages=[stable_package(p) for p in item['packages']]
    if item['id']=='sam2':packages += [stable_package('opencv-python-headless')]
    if item['id']=='clipsai' and os.name=='nt':packages += [stable_package('python-magic-bin')]
    model=item['model']
    if item['id']=='faster-whisper':model='Systran/faster-whisper-'+options.get('model','small')
    result=dict(schema=1,component=item['id'],platform=sys.platform,python=sys.version,packages=packages,
                requested=item['requested_version'],source=None,weights=None,extra_models=[],created=time.time())
    if item['repo']:result['source']=source_plan(item)
    if model:
        try:result['weights']=model_plan(model,os.environ.get('HF_TOKEN'))
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403):raise ValueError('Model gated: buka halaman sumber, setujui syarat akun, lalu isi HF_TOKEN secara lokal. Kunci tidak ditampilkan di UI.') from exc
            raise
    if item['id']=='pyannote':
        for dependency in ('pyannote/segmentation-3.0','pyannote/wespeaker-voxceleb-resnet34-LM'):
            extra=model_plan(dependency,os.environ.get('HF_TOKEN'));prefix='dependencies/'+dependency.split('/')[-1]
            for entry in extra['files']:entry['path']=prefix+'/'+entry['path'].removeprefix('weights/')
            extra['prefix']=prefix;result['extra_models'].append(extra)
    result['model_choice']=options.get('model','small') if item['id']=='faster-whisper' else None
    if item['kind']=='node':
        result['node_packages']=(['remotion@4.0.533','@remotion/cli@4.0.533','react@18.3.1','react-dom@18.3.1'] if item['id']=='remotion' else
                                 ['@motion-canvas/core@3.17.2','@motion-canvas/2d@3.17.2','@motion-canvas/ui@3.17.2','@motion-canvas/vite-plugin@3.17.2','vite@5.4.14','typescript@5.7.3'])
    write(directory/'plan.json',result);return result


def install_node(manager,job,directory,recipe):
    node=shutil.which('node');npm=shutil.which('npm')
    if not node or not npm:
        if os.name!='nt':raise ValueError('Node.js belum tersedia. Pasang Node.js LTS dari https://nodejs.org/ lalu Lanjutkan. Python utama tetap tersedia.')
        pinned=read(manager.root/'node-plan.json')
        if not pinned:
            releases=api('https://nodejs.org/dist/index.json')
            release=next(r for r in releases if r['version'].startswith('v22.') and r.get('lts'))
            name='node-'+release['version']+'-win-x64.zip'
            with urllib.request.urlopen('https://nodejs.org/dist/'+release['version']+'/SHASUMS256.txt',timeout=30) as response:sums=response.read().decode()
            expected=next(line.split()[0] for line in sums.splitlines() if line.split()[-1]==name)
            pinned=dict(version=release['version'],archive=name,sha256=expected)
            write(manager.root/'node-plan.json',pinned)
        target=manager.root/'cache'/pinned['archive']
        fetch('https://nodejs.org/dist/'+pinned['version']+'/'+pinned['archive'],target,pinned['sha256'],canceled=lambda:manager.canceled(job['id']))
        parent=manager.root/'node';parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(target) as archive:
            for entry in archive.infolist():
                path=safe_path(parent,entry.filename.rstrip('/'))
                if entry.is_dir():path.mkdir(parents=True,exist_ok=True);continue
                if (entry.external_attr>>16)&0o170000==0o120000:raise ValueError('Arsip Node mempunyai symlink')
                path.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(entry) as source,path.open('wb') as output:shutil.copyfileobj(source,output)
        base=parent/pinned['archive'].removesuffix('.zip');node=str(base/'node.exe');npm=str(base/'npm.cmd')
    version=subprocess.check_output([node,'--version'],text=True,timeout=15).strip()
    if int(version.lstrip('v').split('.')[0])<18:raise ValueError('Node.js minimal 18 diperlukan; Node.js LTS 22 disarankan')
    folder=directory/'node';folder.mkdir(exist_ok=True)
    template=manager.repo/'clipper/runtime/samples'/job['component']
    shutil.copytree(template,folder,dirs_exist_ok=True)
    # Resolve npm's JS entrypoint, not cmd.exe, so paths with spaces stay arguments.
    candidates=[Path(node).parent/'node_modules/npm/bin/npm-cli.js',Path(npm).resolve().parent.parent/'lib/node_modules/npm/bin/npm-cli.js',Path(npm).resolve().parent/'npm-cli.js']
    npm_script=next((p for p in candidates if p.is_file()),None)
    if not npm_script:raise ValueError('Entrypoint npm tidak ditemukan. Pasang distribusi resmi Node.js LTS.')
    package={'name':'clipper-'+job['component']+'-sample','private':True,'version':'1.0.0',
             'dependencies':{p.rsplit('@',1)[0]:p.rsplit('@',1)[1] for p in recipe['node_packages']}}
    write(folder/'package.json',package)
    environment={**os.environ,'PATH':str(Path(node).parent)+os.pathsep+os.environ.get('PATH','')}
    run([node,npm_script,'install','--no-audit','--no-fund','--cache',str(manager.root/'cache/npm')],manager,job['id'],cwd=folder,env=environment)
    return dict(node=str(Path(node).resolve()),version=version,npm=str(npm_script))


def install(manager,job):
    item=get(job['component']);jid=job['id'];generation=item['id']+'/'+jid
    directory=safe_path(manager.root/'generations',generation);directory.mkdir(parents=True,exist_ok=True)
    manager.update(jid,message='Memeriksa sumber resmi dan mengunci rencana',progress=2)
    if shutil.disk_usage(directory).free<item['estimate_bytes']:raise OSError('Ruang disk bebas kurang dari perkiraan '+str(round(item['estimate_bytes']/1024**3,1))+' GB. Pilih komponen yang diperlukan lebih dahulu.')
    recipe=plan(manager,job,directory);checkpoint=read(directory/'checkpoint.json',{})
    all_files=sum([v.get('files',[]) for v in [recipe.get('source') or {},recipe.get('weights') or {},*recipe.get('extra_models',[])]],[])
    required=sum(r.get('size') or 0 for r in all_files)
    if shutil.disk_usage(directory).free<required+128*1024**2:raise OSError('Disk tidak cukup untuk bobot dan berkas sumber yang telah diukur')
    for index,entry in enumerate(all_files):
        def progress(done,total,index=index,entry=entry):
            manager.update(jid,progress=5+40*(index+(done/max(1,total) if total else 0))/max(1,len(all_files)),
                           message=entry['path']+' · '+str(round(done/1024**2,1))+' / '+(str(round(total/1024**2,1)) if total else '?')+' MB')
        token=os.environ.get('HF_TOKEN') if 'huggingface.co/' in entry['url'] else None
        fetch(entry['url'],safe_path(directory,entry['path']),entry['hash'],algorithm=entry['algorithm'],size=entry.get('size'),
              headers={'Authorization':'Bearer '+token} if token else {},progress=progress,canceled=lambda:manager.canceled(jid))
    versions={};environment={**os.environ,'PIP_CACHE_DIR':str(manager.root/'cache/pip'),'PYTHONNOUSERSITE':'1','SAM2_BUILD_CUDA':'0'}
    # External tools receive real probes; never claim they were installed by pip.
    if item['kind'] in ('pip','source'):
        py=interpreter(directory)
        if not py.is_file():
            manager.update(jid,progress=48,message='Membuat lingkungan '+item['group']+' terisolasi')
            run(choose_python()+['-m','venv',str(directory/'env')],manager,jid)
        if not checkpoint.get('pip_complete'):
            manager.update(jid,progress=50,message='Memasang paket di lingkungan tersendiri; wheel memakai cache pip')
            run([py,'-m','pip','install','--disable-pip-version-check','--report',str(directory/'pip-report.json'),*recipe['packages']],manager,jid,env=environment,timeout=3600)
            checkpoint['pip_complete']=True;write(directory/'checkpoint.json',checkpoint)
        freeze=subprocess.check_output([str(py),'-m','pip','freeze','--all'],env=environment,text=True,timeout=60)
        (directory/'installed-lock.txt').write_text(freeze,encoding='utf-8')
        versions=dict(line.split('==',1) for line in freeze.splitlines() if '==' in line)
        versions['python']=subprocess.check_output([str(py),'--version'],text=True,timeout=15).strip()
    elif item['kind']=='node':versions=install_node(manager,job,directory,recipe)
    elif item['kind']=='ollama':
        ollama=shutil.which('ollama')
        if not ollama:raise ValueError('Ollama lokal belum tersedia. Pasang dari https://ollama.com/download; model lama tidak akan diganti.')
        tags=api('http://127.0.0.1:11434/api/tags')
        selected=next((m for m in tags.get('models',[]) if m['name']=='qwen3:8b'),None)
        if selected is None:
            run([ollama,'pull','qwen3:8b'],manager,jid,timeout=7200)
            tags=api('http://127.0.0.1:11434/api/tags');selected=next((m for m in tags.get('models',[]) if m['name']=='qwen3:8b'),None)
        if not selected:raise ValueError('Qwen3 lokal belum tersedia setelah pull')
        versions=dict(model=selected['name'],digest=selected['digest'],ownership='Ollama bersama; rollback tidak menghapus model')
    if item['id']=='yunet':
        model_path=directory/'source/models/face_detection_yunet/face_detection_yunet_2023mar.onnx'
        pointer=model_path.read_bytes()
        if pointer.startswith(b'version https://git-lfs.github.com/spec/v1'):
            text=pointer.decode();sha=re.search(r'oid sha256:([a-f0-9]{64})',text);size=re.search(r'size (\d+)',text)
            if not sha or not size:raise ValueError('Pointer LFS YuNet tidak valid')
            entry=dict(path='weights/yunet.onnx',url='https://media.githubusercontent.com/media/'+item['repo']+'/'+recipe['source']['commit']+'/models/face_detection_yunet/face_detection_yunet_2023mar.onnx',hash=sha[1],algorithm='sha256',size=int(size[1]))
            fetch(entry['url'],safe_path(directory,entry['path']),entry['hash'],size=entry['size'],canceled=lambda:manager.canceled(jid));all_files.append(entry)
        else:
            target=directory/'weights/yunet.onnx';target.parent.mkdir(exist_ok=True);shutil.copy2(model_path,target)
            all_files.append(dict(path='weights/yunet.onnx',hash=digest(target),algorithm='sha256'))
    if item['id']=='talknet':
        # The official demo publishes a Drive ID but no authoritative checksum.
        # Record that distinction; safe weights_only loading is mandatory later.
        weight=directory/'weights/pretrain_TalkSet.model';weight.parent.mkdir(exist_ok=True)
        if not checkpoint.get('talknet_complete'):
            code='import gdown; p=gdown.download(id="1AbN9fCf9IexMxEKXLQY2KYBlb-IhSEea",output='+repr(str(weight))+',quiet=False,resume=True); assert p, "Google Drive download failed"'
            run([interpreter(directory),'-c',code],manager,jid,timeout=1800)
            checkpoint['talknet_complete']=True;write(directory/'checkpoint.json',checkpoint)
        if not weight.is_file() or weight.stat().st_size<1024**2:raise ValueError('Checkpoint TalkNet belum lengkap')
        all_files.append(dict(path='weights/pretrain_TalkSet.model',hash=digest(weight),algorithm='sha256',verification='hash dicatat saat unduh pertama; upstream tidak menerbitkan checksum'))
    if item['id']=='pyannote':
        # Construct a private HF cache from pinned, verified snapshots. The
        # upstream pipeline can use its original model IDs while offline.
        for model_info in [recipe['weights'],*recipe['extra_models']]:
            prefix=model_info.get('prefix','weights')
            cache=directory/'hf-cache'/('models--'+model_info['repo'].replace('/','--'))
            (cache/'refs').mkdir(parents=True,exist_ok=True);(cache/'refs/main').write_text(model_info['commit'],encoding='utf-8')
            all_files.append(dict(path=(cache/'refs/main').relative_to(directory).as_posix(),hash=digest(cache/'refs/main'),algorithm='sha256'))
            for entry in model_info['files']:
                relative=entry['path'].removeprefix(prefix+'/')
                cached=safe_path(cache/'snapshots'/model_info['commit'],relative);cached.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(safe_path(directory,entry['path']),cached)
                all_files.append(dict(path=cached.relative_to(directory).as_posix(),hash=entry['hash'],algorithm=entry['algorithm']))
    artifacts=[{k:v for k,v in entry.items() if k in ('path','hash','algorithm','verification')} for entry in all_files]
    for path in [directory/'plan.json',directory/'installed-lock.txt',directory/'pip-report.json',directory/'node/package-lock.json']:
        if path.is_file():artifacts.append(dict(path=path.relative_to(directory).as_posix(),hash=digest(path),algorithm='sha256'))
    if item['kind']=='node':
        for path in sorted((directory/'node').rglob('*')):
            if path.is_file() and 'node_modules' not in path.parts and path.name not in ('package-lock.json',):
                artifacts.append(dict(path=path.relative_to(directory).as_posix(),hash=digest(path),algorithm='sha256'))
    receipt=dict(component=item['id'],installed=True,generation=generation,created=time.time(),versions=versions,
                 weights={k:v for k,v in (recipe.get('weights') or {}).items() if k!='files'},source={k:v for k,v in (recipe.get('source') or {}).items() if k!='files'},
                 model_choice=recipe.get('model_choice'),artifacts=artifacts,test={},external=item['kind'] in ('system','ollama'))
    receipt['extra_models']=[{k:v for k,v in m.items() if k!='files'} for m in recipe.get('extra_models',[])]
    write(directory/'receipt.json',receipt)
    # Probe this staged generation before switching the active pointer.
    from .tasks import probe_generation
    manager.update(jid,progress=90,message='Memeriksa runtime dalam worker')
    test=probe_generation(manager,job,directory,receipt,sample=False)
    receipt['versions'].update(test.get('versions',{}))
    receipt['test']=test;write(directory/'receipt.json',receipt)
    if not test.get('passed'):raise RuntimeError('Lingkungan telah dibuat tetapi belum diaktifkan: '+test.get('detail','uji impor gagal'))
    manager.activate(item['id'],generation,receipt)
    return dict(generation=generation,test=test,versions=versions,message='Terpasang; '+('uji runtime lulus' if test.get('passed') else 'uji belum lulus, lihat detail'))
