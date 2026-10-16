"""Podcast episode packages and exact source-range derivatives."""
import json
import shutil
import zipfile
from pathlib import Path
from .m8_contract import canonical, only, text
from .m9_contract import artifact, atomic_bytes, number, safe_media
from .m9_media import run, verify_media
from .dependency_cache import content_id
from .project_store import Conflict


class Delivery:
    def __init__(self,lab):self.lab=lab;self.m8=lab.m8;self.service=lab.service

    def podcast(self,actor,data):
        only(data,('project_id','expected_revision','chapters','notes','cover_id'),('project_id','expected_revision','chapters','notes'))
        pid=data['project_id'];self.m8.workspaces.require(actor,'edit',pid);doc=self.service.store.get(pid)
        if doc['revision']!=data['expected_revision']:raise Conflict(doc['revision'])
        chapters=data['chapters'];duration=doc['source']['info']['duration']
        if not isinstance(chapters,list) or not 1<=len(chapters)<=100:raise ValueError('Pilih 1–100 bab episode')
        previous=-1;validated=[]
        for row in chapters:
            only(row,('start','title'),('start','title'));start=number(row['start'],'Awal bab',0,duration)
            if start<=previous or (not validated and start!=0):raise ValueError('Bab pertama dimulai 0 dan bab berikutnya berurutan')
            validated.append({'start':start,'title':text(row['title'],'Judul bab',200)});previous=start
        cover=None
        if data.get('cover_id'):
            item=self.lab.store.get(actor,data['cover_id'])
            if item['kind']!='media':raise ValueError('Sampul harus aset gambar M9')
            path=safe_media(item['data']['path'],self.lab.root)
            from PIL import Image
            with Image.open(path) as im:im.verify()
            cover={'path':str(path),'content_id':content_id(path,fresh=True),'license':item['data'].get('license')}
        selected=self.service.config(doc).audio_stream_index
        if selected<0:selected=doc['source']['info']['audio_tracks'][0]['index']
        return self.lab.enqueue(actor,'podcast_m9',{'project_id':pid,'input_revision':doc['revision'],'source_path':doc['source']['path'],
            'source_content_id':doc['source']['source_id'],'audio_index':selected,'duration':duration,'name':doc['name'],
            'chapters':validated,'notes':text(data['notes'],'Catatan',30000,0),'cover':cover,'lineage':doc['source'].get('lineage')})

    def buffer(self,actor,data):
        only(data,('id','start','end','name'),('id','start','end','name'))
        item=self.lab.store.get(actor,data['id'],'edit')
        if item['kind']!='recording' or item['data']['status']!='ready':raise ValueError('Clipping saat capture berlangsung belum dibuka. Finalisasi rekaman, lalu pilih rentang.')
        pid=item['data']['project_id'];doc=self.service.store.get(pid);duration=doc['source']['info']['duration']
        a=number(data['start'],'Awal',0,duration);b=number(data['end'],'Akhir',a,duration)
        if b<=a or b-a>600:raise ValueError('Potongan 0–600 detik')
        return self.lab.enqueue(actor,'buffer_m9',{'project_id':pid,'input_revision':doc['revision'],'source_path':doc['source']['path'],
            'source_content_id':doc['source']['source_id'],'name':text(data['name'],'Nama',160),'start':a,'end':b,'live':False})

    def execute(self,job):
        snap=job['request']['m9'];actor=self.lab.operator(snap['workspace']);folder=self.lab.root/'deliveries'/job['id'];folder.mkdir(parents=True,exist_ok=True)
        def check():
            self.lab.check_job(job);doc=self.service.store.get(snap['project_id'])
            if doc['revision']!=snap['input_revision']:
                from .studio_worker import StaleJob
                raise StaleJob('Revisi episode berubah')
        check()
        if content_id(snap['source_path'],fresh=True)!=snap['source_content_id']:raise ValueError('Sumber episode berubah')
        if job['kind']=='buffer_m9':
            from .media_context import inspect
            is_video=inspect(snap['source_path'])['kind']=='video';out=folder/('recording-cut.mp4' if is_video else 'recording-cut.wav')
            codecs=['-c:v','libx264','-preset','veryfast','-c:a','aac'] if is_video else ['-c:a','pcm_s16le']
            run(['-ss',str(snap['start']),'-i',snap['source_path'],'-t',str(snap['end']-snap['start']),*codecs,str(out)],check=check)
            verify_media(out,check=check);manifest={'kind':'recording_cut9','source_project':snap['project_id'],'source_revision':snap['input_revision'],
                'source_content_id':snap['source_content_id'],'range':[snap['start'],snap['end']],'live':False,'output':artifact(out)}
            manifest_path=folder/'recording-cut9.json';atomic_bytes(manifest_path,(canonical(manifest)+'\n').encode())
            if content_id(snap['source_path'],fresh=True)!=snap['source_content_id']:raise ValueError('Sumber episode berubah')
            return self.lab.publish_derivative(job,actor,out,snap['name'],manifest,manifest_path,
                source_guard={'project_id':snap['project_id'],'revision':snap['input_revision'],'content_id':snap['source_content_id']})
        wav=folder/'episode.wav'
        run(['-i',snap['source_path'],'-map','0:'+str(snap['audio_index']),'-vn','-c:a','pcm_s16le','-ar','48000',str(wav)],check=check)
        info=verify_media(wav,check=check)
        notes=folder/'notes.md';atomic_bytes(notes,('# '+snap['name']+'\n\n'+snap['notes']+'\n\nSource revision: '+str(snap['input_revision'])+'\n').encode())
        chapters=folder/'chapters.json';atomic_bytes(chapters,(canonical({'source_project':snap['project_id'],'source_revision':snap['input_revision'],'chapters':snap['chapters']})+'\n').encode())
        members=[wav,notes,chapters];cover=snap.get('cover')
        if cover:
            if content_id(cover['path'],fresh=True)!=cover['content_id']:raise ValueError('Sampul berubah')
            target=folder/('cover'+Path(cover['path']).suffix);shutil.copy2(cover['path'],target);members.append(target)
        else:
            from PIL import Image,ImageDraw
            image=Image.new('RGB',(1000,1000),'#10283f');draw=ImageDraw.Draw(image);draw.text((70,450),'PODCAST',fill='#8de5d0',stroke_width=0)
            target=folder/'cover-placeholder.png';image.save(target);members.append(target)
        lineage=snap.get('lineage') or {};stems=[]
        if lineage.get('kind')=='recording9':
            original=safe_media(lineage['manifest'],self.lab.root);record=json.loads(original.read_text())
            for track in record['tracks']:
                if track['kind'] not in ('microphone','system_audio') and not track['mime'].startswith('audio/'):continue
                path=safe_media(original.parent/track['artifact']['name'],self.lab.root)
                if content_id(path,fresh=True)!=track['artifact']['content_id']:raise ValueError('Stem rekaman berubah')
                copied=folder/('stem-'+track['id']+path.suffix);shutil.copy2(path,copied);members.append(copied)
                stems.append({'participant':track['participant'],'file':copied.name,'offset':track['data']['offset'],'isolated_includes_backstage':True})
        manifest={'schema_version':1,'kind':'podcast9','source_project':snap['project_id'],'source_revision':snap['input_revision'],'source_content_id':snap['source_content_id'],
            'duration':info['duration'],'sample_rate':48000,'notes_provenance':'user_supplied_requires_review','cover_placeholder':cover is None,'stems':stems,
            'privacy':'host package; isolated stems can contain backstage conversation','members':[artifact(p) for p in members]}
        manifest_path=folder/'podcast9.json';atomic_bytes(manifest_path,(canonical(manifest)+'\n').encode());members.append(manifest_path)
        archive=folder/'podcast9.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for path in members:z.write(path,path.name)
        check()
        if content_id(snap['source_path'],fresh=True)!=snap['source_content_id']:raise ValueError('Sumber episode berubah')
        result={'project_id':snap['project_id'],'archive_path':str(archive),'manifest_path':str(manifest_path),'content_id':content_id(archive,fresh=True),'live':False}
        with self.m8.db.transaction() as db:
            row=db.execute('SELECT revision FROM projects WHERE id=?',(snap['project_id'],)).fetchone()
            if row['revision']!=snap['input_revision']:raise Conflict(row['revision'])
            self.lab.finish(db,job,result)
        return result
