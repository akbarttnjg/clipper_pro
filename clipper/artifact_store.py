"""Immutable render sets. Only a guarded database pointer makes a set public.

Staging and sealed directories share a volume. Interrupted staging is retained
for diagnosis; recovery never guesses that an incomplete render was successful.
"""
import copy
import os
import shutil
import uuid
from pathlib import Path
from .dependency_cache import content_id
from .runtime.state import read,write

VERSION='artifact-set-1'


def sync_directory(path):
    if os.name=='nt':return
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def rebase(value, before, after):
    if isinstance(value,str):
        prefix=str(before.resolve())
        return str(after.resolve())+value[len(prefix):] if value==prefix or value.startswith(prefix+os.sep) else value
    if isinstance(value,list):return [rebase(x,before,after) for x in value]
    if isinstance(value,dict):return {k:rebase(v,before,after) for k,v in value.items()}
    return value


def capture_plan_files(txn,plan,work):
    """Freeze prepared plates/overlays and selected assets referenced by a saved plan."""
    paths=set();work=Path(work).resolve()
    def visit(value):
        if isinstance(value,str):
            path=Path(value)
            if path.is_absolute():
                path=path.resolve()
                if path.is_relative_to(work) and path.is_file():paths.add(path)
        elif isinstance(value,dict):
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(plan)
    if plan.get('editor',{}).get('advanced_source_layer')=='baked':
        source=Path(plan.get('source',{}).get('path','')).resolve()
        if not source.is_file():raise ValueError('Source proxy M1 hilang sebelum pembekuan artifact; final sebelumnya dipertahankan.')
        paths.add(source)
    for event in plan.get('broll',[]):
        for value in (event.get('path'),event.get('asset',{}).get('path')):
            if value and Path(value).is_file():paths.add(Path(value).resolve())
    for i,source in enumerate(sorted(paths)):
        relative=Path('prepared-assets')/(str(i).zfill(4)+'-'+source.name)
        target=txn.staging/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        plan=rebase(plan,source,txn.final/relative)
    return plan


class ArtifactSet:
    def __init__(self,root,metadata=None,*,minimum_free_bytes=64*1024*1024):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(self.root).free<minimum_free_bytes:
            raise OSError('Ruang disk belum cukup untuk staging; hasil final sebelumnya dipertahankan.')
        self.set_id='set-'+uuid.uuid4().hex
        self.staging=self.root/'.staging'/self.set_id
        self.final=self.root/self.set_id
        self.journal=self.root/'.transactions'/(self.set_id+'.json')
        self.metadata=copy.deepcopy(metadata or {})
        self.staging.mkdir(parents=True)
        write(self.journal,{'set_id':self.set_id,'state':'preparing','metadata':self.metadata})

    def abort(self,exc):
        try:write(self.journal,{'set_id':self.set_id,'state':'failed','error':str(exc)[:2000],'metadata':self.metadata})
        except OSError:pass

    def seal(self):
        members={}
        for path in sorted(self.staging.rglob('*')):
            if path.is_symlink():raise ValueError('Symlink tidak diizinkan di ArtifactSet.')
            if not path.is_file():continue
            name=path.relative_to(self.staging).as_posix()
            with path.open('rb') as stream:os.fsync(stream.fileno())
            members[name]={'content_id':content_id(path,fresh=True),'size_bytes':path.stat().st_size}
        if not members:raise ValueError('ArtifactSet kosong tidak dapat dipublikasikan.')
        missing=set(self.metadata.get('required_members',[]))-set(members)
        if missing:raise ValueError('Anggota ArtifactSet wajib hilang: '+', '.join(sorted(missing)))
        manifest={'schema_version':1,'version':VERSION,'set_id':self.set_id,'state':'validated',
                  'metadata':self.metadata,'members':members}
        write(self.staging/'manifest.json',manifest)
        write(self.journal,{'set_id':self.set_id,'state':'prepared','metadata':self.metadata})
        for folder in sorted((p for p in self.staging.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):sync_directory(folder)
        sync_directory(self.staging)
        sync_directory(self.journal.parent)
        os.replace(self.staging,self.final)
        sync_directory(self.final.parent)
        write(self.journal,{'set_id':self.set_id,'state':'sealed','metadata':self.metadata})
        return {'artifact_set_id':self.set_id,'artifact_root':str(self.final),
                'artifact_manifest_path':str(self.final/'manifest.json'),
                'artifact_manifest_id':content_id(self.final/'manifest.json',fresh=True)}


def verify(result,*,fresh=True):
    try:return _verify(result,fresh=fresh)
    except (OSError,ValueError,TypeError,KeyError):return False


def _verify(result,*,fresh=True):
    path=result.get('artifact_manifest_path')
    if not path:return False
    path=Path(path)
    if not path.is_file() or path.is_symlink() or content_id(path,fresh=fresh)!=result.get('artifact_manifest_id'):return False
    manifest=read(path,{})
    if manifest.get('state')!='validated' or manifest.get('set_id')!=result.get('artifact_set_id'):return False
    if set(manifest.get('metadata',{}).get('required_members',[]))-set(manifest.get('members',{})):return False
    root=path.parent.resolve()
    for name,item in manifest.get('members',{}).items():
        relative=Path(name);member=root/relative
        if relative.is_absolute() or '..' in relative.parts or member.is_symlink() or not member.resolve().is_relative_to(root):return False
        if not member.is_file() or member.stat().st_size!=item['size_bytes'] or content_id(member,fresh=fresh)!=item['content_id']:return False
    return bool(manifest.get('members'))


def recovery(root):
    """Report exact recoverable state, without changing a published DB pointer."""
    root=Path(root).resolve();rows=[]
    for path in sorted((root/'.transactions').glob('set-*.json')):
        if path.is_symlink():continue
        try:data=read(path,{})
        except (OSError,ValueError):continue
        ident=data.get('set_id','')
        if not ident.startswith('set-') or len(ident)!=36 or any(c not in '0123456789abcdef' for c in ident[4:]):continue
        stage=root/'.staging'/ident;final=root/ident
        try:sealed=read(final/'manifest.json',{})
        except (OSError,ValueError):sealed={}
        rows.append({'set_id':ident,'state':'sealed_unreferenced' if sealed.get('state')=='validated' else 'incomplete',
                     'staging_exists':stage.is_dir(),'final_exists':final.is_dir(),'journal_state':data.get('state')})
    return rows


def studio_set(result,plan,doc,cid,vid,cfg,media,dependency,*,before_seal=lambda:None,reused=False):
    """New publication receipt/exchange for fresh renders and pixel cache hits."""
    from . import library_paths
    from .studio_exchange import records
    original=copy.deepcopy(result)
    if not verify(original):raise ValueError('Render set tidak lengkap atau berubah; render ulang.')
    source_root=Path(original['artifact_root'])
    manifest=read(original['artifact_manifest_path'])
    txn=ArtifactSet(library_paths.project_root(cfg)/'artifact-sets',
                    {'kind':'studio_render','project_id':doc['project_id'],'clip_id':cid,'variant_id':vid,
                     'requested_revision':doc['revision'],'dependency':dependency,'cache_reused':reused})
    if result.get('render_summary'):txn.metadata['render_summary']=result['render_summary']
    if result.get('draft_id'):txn.metadata.update(draft_id=result['draft_id'],snapshot_digest=result['snapshot_digest'],is_draft=True)
    try:
        for name in manifest['members']:
            source=source_root/name;target=txn.staging/name;target.parent.mkdir(parents=True,exist_ok=True)
            # Copy, rather than hardlink, sidecars that receive new publication metadata.
            shutil.copy2(source,target)
        value=rebase(original,source_root,txn.final)
        plan=rebase(copy.deepcopy(plan),source_root,txn.final)
        old_file=Path(original['absolute_file']).relative_to(source_root)
        value.update(file=library_paths.relative(cfg,txn.final/old_file),absolute_file=str(txn.final/old_file),
                     plan_path=str(txn.final/'edit-plan.json'),dependency=dependency,
                     input_revision=doc['revision'],requested_revision=doc['revision'],cache_reused=reused)
        value.setdefault('encode_provenance',{'input_revision':original.get('input_revision',doc['revision']),
                                            'output_content_id':original['output_content_id'],
                                            'artifact_set_id':original['artifact_set_id']})
        for field,suffix in [('ass_url','.ass'),('srt_url','.srt'),('credits_url','.credits.txt')]:
            candidates=[name for name in manifest['members'] if name.endswith(suffix)]
            if not candidates:raise ValueError('Anggota ArtifactSet wajib hilang: '+suffix)
            value[field]=library_paths.url(library_paths.relative(cfg,txn.final/candidates[0]))
        value['url']=library_paths.url(value['file'])
        plan['publication']={'requested_revision':doc['revision'],'dependency':dependency,
                             'encode_provenance':value['encode_provenance'],'cache_reused':reused}
        if value.get('render_summary'):plan['publication']['render_summary']=value['render_summary']
        if value.get('draft_id'):plan['publication'].update(draft_id=value['draft_id'],is_draft=True,snapshot_digest=value['snapshot_digest'])
        write(txn.staging/'edit-plan.json',plan)
        value['plan_content_id']=content_id(txn.staging/'edit-plan.json',fresh=True)
        exchange=records(plan,value,doc,cid,vid,cfg,media)
        write(txn.staging/'exchange.json',exchange)
        value['exchange_path']=str(txn.final/'exchange.json')
        value['exchange_content_id']=content_id(txn.staging/'exchange.json',fresh=True)
        write(txn.staging/'publication-receipt.json',{'requested_revision':doc['revision'],'dependency':dependency,
              'cache_reused':reused,'encode_provenance':value['encode_provenance'],'runtime_receipt':plan.get('runtime_receipt',{})})
        txn.metadata['required_members']=sorted(set(manifest['members'])|{'edit-plan.json','exchange.json','publication-receipt.json'})
        before_seal()
        value.update(txn.seal())
        return value,plan,exchange
    except BaseException as exc:txn.abort(exc);raise
