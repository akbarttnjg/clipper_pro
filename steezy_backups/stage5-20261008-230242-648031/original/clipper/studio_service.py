"""Studio 4 application service: revisions, variants, paged words and job inputs.

Only this service mutates project documents. Heavy work runs in studio_worker.
The heard transcript stays immutable; approved edits are sparse, scoped patches.
"""
import copy
import json
import math
import uuid
from functools import cached_property
from dataclasses import asdict, fields, replace
from pathlib import Path
from .config import Config, validate_overrides
from .contracts import fingerprint
from .project_store import ProjectStore, Conflict, dumps
from .job_queue import JobQueue
from .dependency_cache import VERSION as DEPENDENCY_VERSION, content_id, asset_id, settings_impact, active_recipe
from .storage import read_json, write_json
from . import stage3

CONFIG_FIELDS={f.name for f in fields(Config)}
PRIVATE={'pexels_key'}
VARIANTS={'portrait':('9:16',1080,1920),'landscape':('16:9',1920,1080)}


def identifier(prefix):return prefix+'-'+uuid.uuid4().hex[:20]


def origins(word):
    return word.get('source_word_ids',word.get('origin_word_ids',[word['word_id']]))


def apply_corrections(words,document,clip_id=None):
    rows=copy.deepcopy(words);take=document.get('transcript_id')
    shared=list(document.get('shared_corrections',{}).values())
    manual=list(document.get('clip_corrections',{}).get(clip_id,{}).values())
    manual_ids={i for r in manual if r['transcript_id']==take for i in r['origin_word_ids']}
    for change in [r for r in shared if not set(r['origin_word_ids'])&manual_ids]+manual:
        if change['transcript_id']!=take:continue
        ids=set(change['origin_word_ids']);positions=[i for i,w in enumerate(rows) if set(origins(w))&ids]
        if not positions:continue
        a,b=positions[0],positions[-1]
        if positions!=list(range(a,b+1)) or {i for w in rows[a:b+1] for i in origins(w)}!=ids:continue
        row={**rows[a],'word':change['after'],'end':rows[b]['end'],'source_word_ids':change['origin_word_ids'],
             'manually_edited':True,'correction':'user_approval','raw_word':' '.join(w['word'] for w in rows[a:b+1])}
        if row['word']!=' '.join(w['word'] for w in rows[a:b+1]):
            row.pop('aligned_words',None);row.pop('alignment_method',None)
        rows[a:b+1]=[row]
    return stage3.apply_alignments(rows,document,clip_id)


class StudioService:
    @cached_property
    def runtime(self):
        from .runtime.manager import RuntimeManager
        from .runtime.state import runtime_root
        return RuntimeManager(self.root,runtime_root(self.root,self.work),autostart=self.queue.autostart)

    def __init__(self,root,base=None,*,db_path=None,resource_lock=None,autostart=True,recover=True):
        self.root=Path(root).resolve();base=base or Config()
        self.base=replace(base,work_dir=str((self.root/base.work_dir).resolve()),out_dir=str((self.root/base.out_dir).resolve()))
        self.work=Path(self.base.work_dir);self.work.mkdir(parents=True,exist_ok=True)
        self.store=ProjectStore(db_path or self.work/'studio4.sqlite3')
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,project_id TEXT,path TEXT,UNIQUE(project_id,path))')
        self.queue=JobQueue(self.store,self.work,resource_lock,autostart=autostart,recover=recover)
        def maintenance():
            from .studio_storage import enforce_limit
            return enforce_limit(self)
        self.queue.on_idle=maintenance

    def register_file(self,project_id,path):
        if not path or not Path(path).is_file():return None
        path=str(Path(path).resolve())
        with self.store.connect() as db:
            row=db.execute('SELECT id FROM files WHERE project_id=? AND path=?',(project_id,path)).fetchone()
            key=row['id'] if row else identifier('file')
            if not row:db.execute('INSERT INTO files VALUES(?,?,?)',(key,project_id,path))
        return '/api/studio/files/'+key

    def file(self,file_id):
        with self.store.connect() as db:row=db.execute('SELECT path FROM files WHERE id=?',(file_id,)).fetchone()
        if not row or not Path(row['path']).is_file():raise KeyError('Berkas tidak ada. Buat preview ulang atau tautkan sumber.')
        path=Path(row['path'])
        if path.is_relative_to(self.work) and 'previews' in path.parts:
            # Access time for the cache policy, without altering media content.
            import os,time
            stat=path.stat();os.utime(path,ns=(time.time_ns(),stat.st_mtime_ns))
        return Path(row['path'])

    def config(self,doc,clip_id=None,variant_id=None):
        values={**asdict(self.base),**doc.get('settings',{})}
        if clip_id:
            variant=self.variant(doc,clip_id,variant_id)
            values.update(variant.get('settings',{}));_,w,h=VARIANTS[variant_id]
            values.update(target_w=w,target_h=h,variant_id=variant_id)
            values['visual_overrides']=variant.get('visual_controls',{})
        media=doc.get('source',{}).get('media_context',{}).get('payload',{})
        values.update(work_dir=str(self.work/doc['project_id']),out_dir=self.base.out_dir,job_id=doc['project_id'],
            fonts_dir=self.base.fonts_dir,
            approved_aliases=doc.get('aliases',[]),source_content_id=doc.get('source',{}).get('source_id',''),
            audio_stream_id=media.get('audio_stream_id',''),preview_seconds=0.,title_card=False)
        from .visual4 import runtime_signature
        from .runtime.state import runtime_root
        visual_runtime=runtime_root(self.root,self.work)
        values.update(visual_cache_dir=str(self.work/doc['project_id']/'visual4'),visual_runtime_root=str(visual_runtime),visual_runtime_signature=runtime_signature(visual_runtime))
        evidence_path=self.work/doc['project_id']/'source-evidence.json'
        values['visual_evidence_signature']=content_id(evidence_path) if evidence_path.is_file() else None
        return Config(**{k:v for k,v in values.items() if k in CONFIG_FIELDS})

    @staticmethod
    def variant(doc,clip_id,variant_id):
        if variant_id not in VARIANTS or clip_id not in doc.get('clips',{}):raise KeyError('Klip atau rasio tidak ditemukan')
        return doc['clips'][clip_id]['variants'][variant_id]

    def create(self,path,settings=None,name=None):
        from .media_context import inspect
        path=Path(path).expanduser().resolve()
        if not path.is_file():raise ValueError('Sumber video tidak ditemukan')
        info=inspect(path)
        if not info['audio_tracks']:raise ValueError('Video harus mempunyai track suara')
        settings=validate_overrides(settings or {})
        document={'name':str(name or path.stem)[:160],'settings':{**{k:v for k,v in asdict(self.base).items() if k not in PRIVATE},**settings},
            'source':{'path':str(path),'source_id':content_id(path,fresh=True),'info':info},
            'clips':{},'aliases':[],'shared_corrections':{},'clip_corrections':{},'transcript_revision':0,'exports':[]}
        return self.store.create(document)

    def add_candidates(self,doc,candidates):
        added=[]
        for candidate in candidates:
            matching=next((cid for cid,c in doc['clips'].items() if abs(c['start']-candidate['start'])<.15 and abs(c['end']-candidate['end'])<.15
                and (not candidate.get('main_claim') or c.get('main_claim')==candidate.get('main_claim'))),None)
            if matching:added.append(matching);continue
            clip_id=identifier('clip')
            doc['clips'][clip_id]={**copy.deepcopy(candidate),'clip_id':clip_id,'revision':0,
                'variants':{v:{'settings':{},'override_keys':[],'timeline_revision':0} for v in VARIANTS}}
            added.append(clip_id)
        return added

    def public(self,project_id):
        doc=self.store.get(project_id);out=copy.deepcopy(doc)
        # Correction patches and full words are read through their scoped endpoints.
        out.pop('shared_corrections',None);out.pop('clip_corrections',None);out.pop('alignment_overrides',None)
        out['settings']={k:v for k,v in out['settings'].items() if k not in PRIVATE}
        source=out['source'];source['available']=Path(source['path']).is_file()
        working=source.get('media_context',{}).get('payload',{}).get('working_path',source['path'])
        source['url']=self.register_file(project_id,working if Path(working).is_file() else source['path'])
        source['changed']=source['available'] and asset_id(source['path'])!=source['source_id']
        for cid,clip in out['clips'].items():
            for vid,variant in clip['variants'].items():
                variant['effective_settings']={k:v for k,v in asdict(self.config(doc,cid,vid)).items() if k not in PRIVATE}
                recipe=variant.pop('recipe',None)
                variant['illustration_count']=len(recipe.get('scenes',[])) if recipe else 0
                dependency=self.dependency(doc,cid,vid)
                if variant.get('schedule_dependency')!=dependency:
                    for event in variant.get('schedule',[]):event.update(status='stale',reason='Jadwal dari revisi lama; buat preview untuk memeriksa pemakaian terbaru')
                for kind in ('preview','result'):
                    result=variant.get(kind)
                    if result:
                        result['available']=Path(result.get('absolute_file','')).is_file()
                        result['url']=self.register_file(project_id,result.get('absolute_file'))
                        result['stale']=result.get('dependency')!=dependency
                variant['export_readiness']=self.export_readiness(doc,cid,vid,dependency=dependency)
                report=variant.get('visual_report')
                if report:
                    report['stale']=variant.get('visual_dependency')!=dependency
                    for shot in report.get('shots',[]):
                        if shot.get('poster_path'):shot['poster_url']=self.register_file(project_id,shot['poster_path'])
                        if shot.get('mask',{}).get('mask'):shot['mask']['url']=self.register_file(project_id,shot['mask']['mask'])
        out['jobs']=self.queue.list(project_id);return out

    def export_readiness(self,doc,clip_id,variant_id,*,dependency=None,fresh=False):
        result=self.variant(doc,clip_id,variant_id).get('result')
        if not result:
            return {'status':'missing','action':'render','message':'Buat render final sebelum menyiapkan paket editor.'}
        path=Path(result.get('absolute_file',''))
        if not path.is_file():
            return {'status':'missing','action':'render','message':'Berkas final tidak tersedia. Render ulang klip ini.'}
        dependency=dependency or self.dependency(doc,clip_id,variant_id,fresh=fresh)
        if result.get('dependency')!=dependency:
            return {'status':'stale','action':'render','message':'Pengaturan atau bahan klip berubah. Render final revisi aktif dahulu, lalu buat paket editor.',
                'input_revision':result.get('input_revision')}
        if fresh and result.get('output_content_id')!=content_id(path,fresh=True):
            return {'status':'changed','action':'render','message':'Isi berkas final berubah. Render ulang sebelum ekspor.'}
        return {'status':'ready','action':'export','message':'Final sesuai bahan dan pengaturan aktif. Paket editor dapat dibuat.',
            'input_revision':result.get('input_revision')}

    def transcript(self,doc,clip_id=None):
        if not doc.get('transcript_id'):raise ValueError('Transkripsi belum tersedia; jalankan analisis sumber')
        data=self.store.transcript(doc['transcript_id'])
        data['words']=apply_corrections(data['words'],doc,clip_id)
        return data

    def page(self,project_id,clip_id=None,*,offset=0,limit=150,q='',whole=False):
        doc=self.store.get(project_id)
        if not doc.get('transcript_id'):return dict(words=[],total=0,next_offset=None,revision=doc['revision'])
        clip=doc['clips'].get(clip_id) if clip_id and not whole else None
        page=self.store.words_page(doc['transcript_id'],offset=offset,limit=limit,q=q,
            start=clip['start'] if clip else None,end=clip['end'] if clip else None)
        heard={dumps(w['word_id']):w['word'] for w in self.store.heard_by_ids(doc['transcript_id'],[i for w in page['words'] for i in origins(w)])}
        # Pages remain indexed by immutable word IDs; display overlays never alter paging.
        for row in page['words']:
            row['heard']=' '.join(heard.get(dumps(i),'') for i in origins(row)).strip() or row['word'];rows=apply_corrections([row],doc,clip_id)
            row.update(rows[0])
            for change in list(doc.get('shared_corrections',{}).values())+list(doc.get('clip_corrections',{}).get(clip_id,{}).values()):
                if change['transcript_id']==doc['transcript_id'] and set(origins(row))&set(change['origin_word_ids']):
                    row['group_edit']=len(change['origin_word_ids'])>len(origins(row))
                    row['group_text']=change['after']
                    row['group_origin_word_ids']=change['origin_word_ids']
                    if row['group_edit']:
                        heard_group=self.store.heard_by_ids(doc['transcript_id'],change['origin_word_ids'])
                        if heard_group:
                            full={**row,'word':change['after'],'start':min(w['start'] for w in heard_group),'end':max(w['end'] for w in heard_group),'source_word_ids':change['origin_word_ids']}
                            full=stage3.apply_alignments([full],doc,clip_id)[0]
                            row['group_start']=full['start'];row['group_end']=full['end'];row['group_aligned_words']=full.get('aligned_words')
        return {**page,'revision':doc['revision'],'transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision']}

    def dependency(self,doc,clip_id=None,variant_id=None,*,fresh=False,kind='render'):
        source=doc['source'];source_hash=asset_id(source['path'],fresh=fresh)
        base=[DEPENDENCY_VERSION,source_hash,source['source_id'],doc.get('transcript_id'),doc.get('transcript_revision'),doc.get('aliases'),doc.get('shared_corrections'),doc.get('alignment_overrides',{}).get('shared')]
        if not clip_id:return fingerprint(base+[doc['settings'],kind])
        variant=self.variant(doc,clip_id,variant_id);clip=doc['clips'][clip_id]
        cfg=self.config(doc,clip_id,variant_id);settings=asdict(cfg)
        for key in ('out_dir','work_dir','pexels_key','variant_id','cache_limit_gb'):settings.pop(key,None)
        recipe=active_recipe(variant.get('recipe',{}),cfg)
        assets=[asset_id(s.get('asset',{}).get('path'),fresh=fresh) for s in recipe.get('scenes',[])]
        assets += [asset_id(cfg.music_path,fresh=fresh),asset_id(cfg.sfx_path,fresh=fresh)]
        fonts=[asset_id(p,fresh=fresh) for p in sorted(Path(cfg.fonts_dir).glob('*.ttf'))]
        candidate={k:v for k,v in clip.items() if k not in ('variants','revision','result','preview')}
        return fingerprint(base+[candidate,settings,recipe,assets,fonts,doc.get('clip_corrections',{}).get(clip_id),doc.get('alignment_overrides',{}).get('clips',{}).get(clip_id),variant.get('timeline',{})])

    def _correction_target(self,doc,clip_id,op):
        if op.get('transcript_id')!=doc.get('transcript_id'):raise ValueError('Transkrip telah diganti; draf tidak diterapkan pada ucapan lain')
        if op.get('transcript_revision')!=doc.get('transcript_revision'):raise Conflict(doc.get('revision',0),'Koreksi transkrip berubah; muat halaman terbaru')
        text=op.get('after')
        if not isinstance(text,str) or not text.strip() or len(text)>120:raise ValueError('Teks koreksi harus 1–120 karakter')
        if op.get('scope','clip') not in ('clip','shared_utterance'):raise ValueError('Cakupan koreksi tidak valid')
        if not clip_id and op.get('scope')!='shared_utterance':raise ValueError('Koreksi sumber penuh memakai cakupan ucapan bersama')
        if 'word_id' in op:
            self.store.word(doc['transcript_id'],op['word_id'])
            word=next((w for w in self.transcript(doc,clip_id)['words'] if op['word_id'] in origins(w)),None)
            if word is None:raise ValueError('Kata tidak ditemukan pada transkrip aktif')
            ids=origins(word)
            if clip_id:
                clip=doc['clips'][clip_id]
                if not (word['end']>clip['start'] and word['start']<clip['end']):raise ValueError('Kata di luar klip aktif')
            if op.get('before') is not None and op['before']!=word['word']:raise ValueError('Teks koreksi berubah; muat halaman terbaru')
            before=word['word']
        else:
            if op.get('source_id')!=doc['source']['source_id']:raise ValueError('Identitas sumber tidak cocok')
            snapshot=self.analysis_snapshot({'project_id':doc['project_id'],'clip_id':clip_id,'variant_id':'portrait'},document=doc)['data']['transcript']['payload']
            token=next((t for t in snapshot['display_tokens'] if t['token_id']==op.get('token_id')),None)
            if not token or token['origin_word_ids']!=op.get('origin_word_ids') or token['text']!=op.get('before'):raise ValueError('Token berubah atau tidak ada pada snapshot aktif')
            if token.get('requires_alignment'):raise ValueError('Koreksi melintasi batas klip; perbaiki batas dahulu')
            ids=token['origin_word_ids']
            before=token['text']
            siblings=[t for t in snapshot['display_tokens'] if t['origin_word_ids']==ids]
            if len(siblings)>1:raise ValueError('Kata ini bagian dari frasa yang sudah diselaraskan. Edit frasa utuh melalui Transkrip & cerita agar kata lain tetap tersimpan.')
        return ids,before,text.strip()

    def correction_review(self,request):
        doc=self.store.get(request['project_id'])
        if request.get('expected_revision')!=doc['revision']:raise Conflict(doc['revision'])
        operations=request.get('operations',[])
        if not isinstance(operations,list) or not 1<=len(operations)<=100:raise ValueError('Kirim 1–100 koreksi')
        reviews=[]
        for index,op in enumerate(operations):
            if op.get('op') not in ('correct_word','correct_token'):continue
            ids,before,after=self._correction_target(doc,request.get('clip_id'),op)
            review=stage3.fact_review(before,after)
            reviews.append({**review,'operation_index':index,'before':before,'after':after,
                'confirmation_stamp':stage3.approval_stamp(doc['transcript_id'],doc['transcript_revision'],ids,before,after)})
        return {'revision':doc['revision'],'reviews':reviews}

    def _correct(self,doc,clip_id,op):
        ids,before,text=self._correction_target(doc,clip_id,op)
        review=stage3.fact_review(before,text)
        if review['requires_confirmation']:
            stamp=stage3.approval_stamp(doc['transcript_id'],doc['transcript_revision'],ids,before,text)
            if op.get('fact_confirmation')!=stamp:raise ValueError(review['message']+' Buka tinjauan fakta sebelum menyimpan.')
        change={'transcript_id':doc['transcript_id'],'origin_word_ids':ids,'after':text.strip(),'provenance':'user_approval'}
        if review['requires_confirmation']:change['fact_approval']={**review,'before':before,'after':text,'stamp':stamp}
        key=fingerprint([doc['transcript_id'],ids])
        group=doc.setdefault('shared_corrections',{}) if op.get('scope')=='shared_utterance' else doc.setdefault('clip_corrections',{}).setdefault(clip_id,{})
        # Replacing a merged token must not leave competing patches for its origins.
        for old in list(group):
            if group[old]['transcript_id']==doc['transcript_id'] and set(group[old]['origin_word_ids'])&set(ids):del group[old]
        group[key]=change

    def changes(self,request):
        pid=request['project_id'];cid=request.get('clip_id');vid=request.get('variant_id','portrait')
        operations=request.get('operations',[])
        if not isinstance(operations,list) or not 1<=len(operations)<=100:raise ValueError('Kirim 1–100 perubahan kecil')
        def change(doc):
            if cid:self.variant(doc,cid,vid)
            touched=set();transcript_changed=False
            for op in operations:
                kind=op.get('op')
                if kind in ('correct_word','correct_token'):
                    self._correct(doc,cid,op);transcript_changed=True
                elif kind in ('alias_upsert','alias_remove'):
                    from .correction_memory import propose_change
                    doc['aliases']=propose_change(doc.get('aliases',[]),op)
                elif kind in ('settings','analysis_settings'):
                    values=validate_overrides(op.get('values',{}))
                    if not values:raise ValueError('Tidak ada pengaturan valid')
                    if op.get('scope')=='project' or kind=='analysis_settings':doc['settings'].update(values)
                    else:
                        variant=self.variant(doc,cid,vid);variant['settings'].update(values)
                        variant['override_keys']=sorted(set(variant.get('override_keys',[]))|set(values));touched.add((cid,vid))
                elif kind=='style':
                    from .edit_styles import recipe
                    values=recipe(op['style_id'])
                    targets=op.get('targets') or [{'clip_id':cid,'variant_id':vid}]
                    if len(targets)>500:raise ValueError('Maksimal 500 varian per batch')
                    for target in targets:
                        c,v=target['clip_id'],target['variant_id'];variant=self.variant(doc,c,v)
                        keep=set(variant.get('override_keys',[])) if not op.get('replace_manual',False) else set()
                        variant['settings'].update({k:value for k,value in values.items() if k not in keep});touched.add((c,v))
                elif kind=='visual_controls':
                    from .visual4 import validate_controls
                    variant=self.variant(doc,cid,vid)
                    values=copy.deepcopy(op.get('values',{}))
                    if not isinstance(values,dict):raise ValueError('Koreksi visual harus berupa objek')
                    if values.get('speaker_track') not in (None,'auto'):
                        report=variant.get('visual_report',{})
                        if not report.get('summary',{}).get('key') or variant.get('visual_dependency')!=self.dependency(doc,cid,vid):
                            raise ValueError('Perbarui analisis visual sebelum memilih lintasan pembicara')
                        values['speaker_evidence']=report['summary']['key']
                    elif values.get('speaker_track')=='auto':values['speaker_evidence']=None
                    merged={**variant.get('visual_controls',{}),**values}
                    variant['visual_controls']=validate_controls(merged,doc['source']['info']['duration']);touched.add((cid,vid))
                elif kind in ('bounds','manual_clip'):
                    a,b=float(op['start']),float(op['end']);duration=doc['source']['info']['duration']
                    if not all(math.isfinite(n) for n in (a,b)) or not 0<=a<b<=duration+.05:raise ValueError('Rentang klip harus di dalam sumber')
                    if kind=='manual_clip':self.add_candidates(doc,[{'start':a,'end':b,'title':str(op.get('title','Klip manual'))[:160],'selection_source':'manual','keywords':[],'reason':'Dipilih pengguna','boundary_pin':{'start':a,'end':b,'source':'manual'}}])
                    else:
                        doc['clips'][cid].update(start=a,end=b,selection_source='reviewed',boundary_pin={'start':a,'end':b,'source':'manual'});doc['clips'][cid]['revision']+=1
                elif kind=='restore_rejected':
                    row=next((r for r in stage3.rejection_rows(doc.get('discovery',{})) if r['rejection_id']==op.get('rejection_id')),None)
                    if not row:raise ValueError('Kandidat ditolak berubah atau tidak tersedia pada laporan aktif')
                    if doc.get('discovery',{}).get('transcript_id') not in (None,doc.get('transcript_id')):raise ValueError('Laporan memakai transkrip lama; jalankan penjelajahan lagi')
                    a,b=float(op.get('start',row.get('start',-1))),float(op.get('end',row.get('end',-1)))
                    duration=doc['source']['info']['duration']
                    if not all(math.isfinite(x) for x in (a,b)) or not 0<=a<b<=duration+.05:raise ValueError('Tentukan rentang sumber yang valid untuk memulihkan kandidat')
                    ids=self.add_candidates(doc,[{'title':str(op.get('title',row.get('title','Kandidat dipulihkan')))[:160],
                        'start':a,'end':b,'keywords':[],'selection_source':'manual','reason':'Dipulihkan pengguna: '+str(row.get('detail',row['code']))[:300],
                        'restored_rejection_id':row['rejection_id'],'boundary_pin':{'start':a,'end':b,'source':'manual'},
                        'warnings':['Pemulihan manual; belum dianggap lolos penilaian cerita otomatis.']}])
                    doc.setdefault('restored_rejections',{})[row['rejection_id']]=ids[0]
                elif kind=='align_words':
                    if op.get('transcript_id')!=doc.get('transcript_id') or op.get('transcript_revision')!=doc.get('transcript_revision'):raise ValueError('Timing memakai transkrip lama; muat ulang tanpa membuang draf')
                    rows=self.transcript(doc,cid)['words'];word=next((w for w in rows if origins(w)==op.get('origin_word_ids')),None)
                    if not word or word['word']!=op.get('text'):raise ValueError('Frasa telah berubah; timing tidak diterapkan')
                    if op.get('scope','clip') not in ('clip','shared_utterance') or not cid and op.get('scope')!='shared_utterance':raise ValueError('Cakupan timing tidak valid')
                    a,b=stage3.alignment_window(word,rows,doc['source']['info']['duration'])
                    aligned=stage3.validate_alignment(word['word'],op.get('words'),a,b)
                    patches=doc.setdefault('alignment_overrides',{})
                    group=patches.setdefault('shared',{}) if op.get('scope')=='shared_utterance' else patches.setdefault('clips',{}).setdefault(cid,{})
                    stage3.store_alignment(group,{'transcript_id':doc['transcript_id'],'origin_word_ids':origins(word),
                        'text':word['word'],'words':aligned,'audio_start':a,'audio_end':b,'method':'manual',
                        'provenance':{'kind':'user_timing','source_id':doc['source']['source_id']}})
                    transcript_changed=True
                elif kind in ('asset_enabled','asset_metadata','asset_timing','asset_replace'):
                    variant=self.variant(doc,cid,vid);scenes=variant.get('recipe',{}).get('scenes',[])
                    scene=next((s for s in scenes if s['id']==op.get('proposal_id') or
                        kind=='asset_metadata' and s['asset']['provider']+':'+s['asset']['id']==op.get('asset_id')),None)
                    if scene is None:raise ValueError('Ilustrasi tidak ditemukan; siapkan ilustrasi dahulu')
                    if kind=='asset_enabled':
                        if type(op.get('enabled')) is not bool:raise ValueError('Status ilustrasi harus boolean')
                        scene['enabled']=op['enabled']
                    elif kind=='asset_metadata':
                        for key in ('tags','attribution'):scene['asset'][key]=str(op.get(key,''))[:2000]
                    elif kind=='asset_timing':
                        a,b,offset=float(op['start']),float(op['end']),float(op.get('asset_start',0))
                        if not all(math.isfinite(n) for n in (a,b,offset)) or not doc['clips'][cid]['start']<=a<b<=doc['clips'][cid]['end'] or offset<0:raise ValueError('Waktu ilustrasi tidak valid')
                        scene.update(source_start=a,source_end=b,asset_start=offset)
                    else:
                        from .media_context import inspect
                        path=Path(op.get('path','')).expanduser().resolve();info=inspect(path)
                        scene['asset']={'id':content_id(path,fresh=True),'provider':'local','path':str(path),'duration':info['duration'],
                            'title':path.stem,'attribution':str(op.get('attribution','Aset milik pengguna'))[:2000]}
                        for proposal in variant.get('asset_proposals',{}).get('payload',{}).get('proposals',[]):
                            if proposal['proposal_id']==scene['id']:
                                proposal.update(path=str(path),poster=None,editable_path=None,duration=info['duration'],
                                    visual_status='unavailable',visual_evidence={},asset_id='local:'+scene['asset']['id'],
                                    content_fingerprint=scene['asset']['id'],rights={'attribution':scene['asset']['attribution'],'permission_status':'user_supplied'})
                    touched.add((cid,vid))
                elif kind=='timeline':
                    variant=self.variant(doc,cid,vid);intervals=op.get('keep_spans')
                    if not isinstance(intervals,list) or not 1<=len(intervals)<=200:raise ValueError('Timeline harus mempunyai 1–200 potongan')
                    previous=doc['clips'][cid]['start']
                    for pair in intervals:
                        if not isinstance(pair,list) or len(pair)!=2:raise ValueError('Rentang timeline tidak valid')
                        a,b=map(float,pair)
                        if not all(math.isfinite(n) for n in (a,b)) or not previous<=a<b<=doc['clips'][cid]['end']:raise ValueError('Potongan harus berurutan dan berada dalam klip')
                        previous=b
                    variant['timeline']={'keep_spans':intervals};touched.add((cid,vid))
                elif kind=='rename':doc['name']=str(op['name']).strip()[:160] or doc['name']
                else:raise ValueError('Operasi tidak dikenal: '+str(kind))
            if transcript_changed:doc['transcript_revision']+=1
            if any(op.get('op') in ('alias_upsert','alias_remove') or 'glossary' in op.get('values',{}) for op in operations):
                from .transcript_correction import glossary_entries
                glossary_entries(self.config(doc))
            for c,v in touched:doc['clips'][c]['variants'][v]['timeline_revision']+=1
            return {'impact':list(dict.fromkeys(stage for op in operations for stage in settings_impact(op.get('values',{}))))}
        return self.store.mutate(pid,request['expected_revision'],request['operation_id'],request,change,
            ' · '.join(dict.fromkeys(op.get('op','Edit') for op in operations)))

    def enqueue(self,project_id,kind,clip_id=None,variant_id='portrait',expected_revision=None,options=None):
        doc=self.store.get(project_id)
        if expected_revision is not None and expected_revision!=doc['revision']:raise Conflict(doc['revision'])
        if kind not in ('analyze','source_evidence','correction','asr_recheck','alignment','discovery','boundary_review','asset_proposals','asset_visual_review','visual_review','preview','render','export','waveform'):raise ValueError('Tahap tidak dikenal')
        if kind in ('analyze','source_evidence','correction','discovery','waveform'):clip_id=None
        if clip_id:self.variant(doc,clip_id,variant_id)
        if kind in ('preview','render','export','asset_proposals','asset_visual_review','boundary_review','visual_review') and not clip_id:raise ValueError('Pilih klip dahulu')
        if kind not in ('analyze','source_evidence','waveform') and not doc.get('transcript_id'):raise ValueError('Transkripsi belum tersedia')
        if kind=='asr_recheck':
            from .speech_jobs import recheck_options
            options=recheck_options(options or {})
        if kind=='alignment':
            from .speech_jobs import alignment_options, alignment_runtime
            options=alignment_options(options or {});alignment_runtime(self.config(doc,clip_id,variant_id),options)
        if kind in ('alignment','asr_recheck') and options.get('origin_word_ids'):
            rows=self.store.heard_by_ids(doc['transcript_id'],options['origin_word_ids'])
            if {w['word_id'] for w in rows}!=set(options['origin_word_ids']):raise ValueError('Identitas kata untuk proses ucapan tidak cocok dengan transkrip aktif')
            if clip_id and any(w['end']<=doc['clips'][clip_id]['start'] or w['start']>=doc['clips'][clip_id]['end'] for w in rows):raise ValueError('Kata untuk proses ucapan berada di luar klip aktif')
        target={'clip_id':clip_id,'variant_id':variant_id}
        request={'dependency':self.dependency(doc,clip_id,variant_id,fresh=True,kind=kind),'options':options or {}}
        if kind=='export':
            readiness=self.export_readiness(doc,clip_id,variant_id,dependency=request['dependency'],fresh=True)
            if readiness['status']!='ready':raise ValueError(readiness['message'])
        return self.queue.enqueue(project_id,kind,target,request)

    def analysis_snapshot(self,target,document=None):
        from . import analysis_adapter as adapter
        doc=document or self.store.get(target['project_id']);cid=target['clip_id'];vid=target['variant_id'];variant=self.variant(doc,cid,vid)
        cfg=self.config(doc,cid,vid);clip=doc['clips'][cid];data={'aliases':doc.get('aliases',[]),'discovery':doc.get('discovery',{})}
        if data['discovery']:data['discovery']={**data['discovery'],'rejections':stage3.rejection_rows(data['discovery'])[:30]}
        if doc.get('transcript_id'):
            # Bounded SQL pages for review; the full transcript is never sent to the DOM.
            page=self.store.words_page(doc['transcript_id'],start=clip['start'],end=clip['end'],limit=200)
            words=apply_corrections(page['words'],doc,cid)
            if words:
                raw=self.store.heard_by_ids(doc['transcript_id'],[i for w in words for i in origins(w)])
                present={i for w in raw for i in origins(w)}
                words=[w for w in words if set(origins(w))<=present]
                from . import evidence
                data['transcript']=adapter.transcript_snapshot({'words':words,'raw_words':raw,'ocr_suggestions':evidence.suggestions(words,evidence.load(cfg))},cfg,
                    source_id=doc['source']['source_id'],transcript_id=doc['transcript_id'],revision=doc['transcript_revision'],
                    input_fingerprint=fingerprint(words),audio_stream_id=cfg.audio_stream_id or 'audio:0',clip_span=(clip['start'],clip['end']))
            from .discovery import context
            data['boundary_context']=context(clip,self.transcript(doc,cid))
        if variant.get('asset_proposals'):
            proposals=copy.deepcopy(variant['asset_proposals']);by_id={s['id']:s for s in variant.get('recipe',{}).get('scenes',[])}
            for p in proposals['payload']['proposals']:
                scene=by_id.get(p['proposal_id'],{});asset=scene.get('asset',{})
                p['enabled']=scene.get('enabled',True);p['source_start']=scene.get('source_start',p['source_start']);p['source_end']=scene.get('source_end',p['source_end'])
                path=asset.get('path',p.get('path'));p['preview_url']=self.register_file(doc['project_id'],path) if Path(path or '').suffix.lower() in ('.mp4','.webm','.mov','.mkv') else None
                p['poster_url']=self.register_file(doc['project_id'],p.get('poster'));p['editable_url']=self.register_file(doc['project_id'],p.get('editable_path'))
                p['usage_status']='scheduled' if p['enabled'] and variant.get('schedule_dependency')==self.dependency(doc,cid,vid) and any(r.get('proposal_id')==p['proposal_id'] and r['status']=='scheduled' for r in variant.get('schedule',[])) else 'not_scheduled'
            data['asset_proposals']=proposals
        preview=variant.get('preview')
        if preview and preview.get('dependency')==self.dependency(doc,cid,vid):data['caption_preview']={'url':self.register_file(doc['project_id'],preview.get('absolute_file')),'revision':doc.get('revision',0)}
        return {'schema_version':1,'target':target,'revision':doc.get('revision',0),
            'capabilities':{'correction':True,'aliases':True,'shared_utterance':True,'assets':True,'asset_changes':True,'discovery':True},'data':data}

    def run_stage(self,request):
        kind=request['stage_id'];cid=request.get('clip_id') if kind in ('asset_proposals','asset_visual_review','boundary_review','alignment','asr_recheck') else None
        return self.enqueue(request['project_id'],kind,cid,request.get('variant_id','portrait'),request['expected_revision'],request.get('options'))

    def stage3_status(self,project_id,clip_id=None,offset=0,limit=40):
        doc=self.store.get(project_id)
        if clip_id and clip_id not in doc['clips']:raise KeyError('Klip tidak ditemukan')
        report=doc.get('discovery',{});rows=stage3.rejection_rows(report);offset=max(0,int(offset));limit=max(1,min(100,int(limit)))
        from .speech_jobs import alignment_availability,available_asr_models
        out={'version':stage3.VERSION,'revision':doc['revision'],'transcript_id':doc.get('transcript_id'),
            'transcript_revision':doc.get('transcript_revision',0),'coverage':report.get('coverage',{}),
            'chapters':report.get('chapters',[]),'rejections':rows[offset:offset+limit],'rejection_total':len(rows),
            'next_offset':offset+limit if offset+limit<len(rows) else None,'restored':doc.get('restored_rejections',{}),
            'alignment':alignment_availability(self.config(doc,clip_id,'portrait')),'speech_reports':doc.get('speech_reports',{}),
            'boundary_pin':doc['clips'][clip_id].get('boundary_pin') if clip_id else None}
        out['asr_models']=[{k:r[k] for k in ('id','model','component')} for r in available_asr_models()]
        if clip_id:out['boundary_proposal']=doc['clips'][clip_id].get('boundary_proposal')
        out['coverage_stale']=report.get('transcript_id') not in (None,doc.get('transcript_id')) or report.get('transcript_revision',doc.get('transcript_revision'))!=doc.get('transcript_revision')
        if clip_id and doc.get('transcript_id'):
            from .discovery import context
            out['boundary_context']=context(doc['clips'][clip_id],self.transcript(doc,clip_id))
        return out

    def migrate(self,states):
        """Copy old sessions once; their original JSON remains the recovery backup."""
        existing={p['project_id'] for p in self.store.list()};errors=[]
        for pid,st in states.items():
            if pid in existing:continue
            try:
                path=st.get('media') or st.get('media_path') or st.get('source')
                if not isinstance(path,str):continue
                cfg=st.get('cfg',self.base)
                if not Path(path).is_file():
                    duration=st.get('transcript',{}).get('duration') or max((c.get('end',0) for c in st.get('scored',[])),default=0)
                    doc=self.store.create({'name':Path(path).stem,'settings':{},'source':{'path':path,'source_id':'legacy-unverified:'+pid,
                        'requires_analysis':True,'info':{'duration':duration,'display_size':None,'audio_tracks':[]}},
                        'clips':{},'aliases':[],'shared_corrections':{},'clip_corrections':{},'transcript_revision':0,'exports':[]})
                else:doc=self.create(path,{},Path(path).stem)
                # Preserve the original project ID, output paths and edit settings.
                with self.store.connect() as db:db.execute('DELETE FROM projects WHERE id=?',(doc['project_id'],))
                doc.pop('revision',None);doc.pop('updated',None);doc['settings']={k:v for k,v in asdict(cfg).items() if k not in PRIVATE};doc['legacy_import']=True
                doc=self.store.create(doc,pid)
                transcript=st.get('transcript')
                if transcript and transcript.get('words'):
                    take=self.store.save_transcript(pid,transcript)
                    def change(d):
                        d['transcript_id']=take;self.add_candidates(d,st.get('scored',[]))
                        for i,(cid,c) in enumerate(d['clips'].items()):
                            for v in c['variants'].values():v['settings'].update(st.get('clip_settings',{}).get(str(i),st.get('clip_settings',{}).get(i,{})))
                            for word in st.get('edits',{}).get(i,[]):
                                if word.get('manually_edited'):
                                    ids=origins(word);d['clip_corrections'].setdefault(cid,{})[fingerprint([take,ids])]={'transcript_id':take,'origin_word_ids':ids,'after':word['word'],'provenance':'legacy_manual'}
                    self.store.mutate(pid,0,identifier('migration'),{'migration':'3.3'},change,'Impor sesi 3.3; file lama dipertahankan')
            except (ValueError,KeyError,OSError) as exc:errors.append({'project_id':pid,'error':str(exc)})
        if errors:write_json(self.work/'migration-report.json',errors)
        return errors
