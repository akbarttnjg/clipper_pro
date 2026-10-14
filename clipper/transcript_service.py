"""M2 immutable tracks, scoped source edits, revisioned review and export."""
import copy
import json
import time
from pathlib import Path
from .contracts import fingerprint
from .dependency_cache import content_id
from .project_store import Conflict, dumps
from . import transcript_tracks as tracks


def scope_group(doc, cid, vid, scope, stem):
    if scope in ('project','shared_utterance'):return doc.setdefault(stem,{})
    if not cid:raise ValueError('Pilih klip untuk cakupan ini')
    if scope=='clip':return doc.setdefault('clip_'+stem,{}).setdefault(cid,{})
    if scope in ('variant','phrase'):
        if vid not in doc.get('clips',{}).get(cid,{}).get('variants',{}):raise ValueError('Rasio tidak valid')
        return doc.setdefault('variant_'+stem,{}).setdefault(cid,{}).setdefault(vid,{})
    raise ValueError('Cakupan tidak valid')


def project_words(words, doc, cid=None, vid=None):
    words=copy.deepcopy(words);take=doc.get('transcript_id')
    layers=[doc.get('source_timing_overrides',{}),doc.get('clip_source_timing_overrides',{}).get(cid,{}),
        doc.get('variant_source_timing_overrides',{}).get(cid,{}).get(vid,{})]
    for group in layers:
        for patch in group.values():
            if patch['transcript_id']!=take:continue
            for row in words:
                if row.get('source_word_ids',[row['word_id']])==patch['origin_word_ids']:
                    row.update(start=patch['start'],end=patch['end'],timing_status='manual_source_time',manually_edited=True)
                    row.pop('aligned_words',None);row.pop('alignment_method',None)
    diarization=doc.get('diarization',{})
    if diarization.get('transcript_id')==take:
        from .speech_m2 import assign_speakers
        words=assign_speakers(words,diarization.get('segments',[]))
    for row in words:
        for wid in row.get('source_word_ids',[row['word_id']]):
            patch=doc.get('manual_speakers',{}).get(dumps(wid))
            if patch and patch['transcript_id']==take:row.update(speaker_id=patch['speaker_id'],speaker_provenance='user_review')
    return words


def validate_timing_targets(service, before, after, cid, vid, scope, ids):
    """Validate the effective layers changed by a broad patch, not just one tab."""
    if scope in ('project','shared_utterance'):
        targets=[(None,None)]+[(c,v) for c in after['clips'] for v in [None,*after['clips'][c]['variants']]]
    elif scope=='clip':targets=[(cid,v) for v in [None,*after['clips'][cid]['variants']]]
    else:targets=[(cid,vid)]
    ids=set(ids)
    for c,v in targets:
        previous=service.transcript(before,c,v)['words'];rows=service.transcript(after,c,v)['words']
        for word in rows:
            origins=set(word.get('source_word_ids',[word['word_id']]))
            if not origins&ids:continue
            old=next((w for w in previous if w.get('source_word_ids',[w['word_id']])==word.get('source_word_ids',[word['word_id']])),None)
            if old and (old['start'],old['end'])==(word['start'],word['end']):continue
            for other in rows:
                if set(other.get('source_word_ids',[other['word_id']]))&origins:continue
                if other.get('speaker_id')==word.get('speaker_id') and word['start']<other['end'] and word['end']>other['start']:
                    raise ValueError('Waktu bertumpang tindih dengan kata speaker yang sama pada '+(f'{c}/{v or "kedua rasio"}' if c else 'sumber proyek'))


def apply_command(service,doc,cid,vid,op,revision):
    kind=op.get('op')
    if kind not in ('m2_timing','m2_speaker','m2_track_display'):return None
    if kind=='m2_track_display':
        variant=service.variant(doc,cid,vid);mode=op.get('mode');tid=op.get('track_id')
        if mode not in ('source','translation','bilingual'):raise ValueError('Mode track tidak valid')
        if mode!='source':
            track=doc.get('translation_tracks',{}).get(tid)
            if not track or not track.get('approved') or track['source_take']!=doc.get('transcript_id') or track['source_revision']!=doc['transcript_revision']:
                raise ValueError('Terjemahan belum disetujui atau sudah usang; tinjau ulang')
        variant['transcript_display']={'mode':mode,'track_id':tid if mode!='source' else None}
        return {'touched':[(cid,vid)],'transcript_changed':False}
    if op.get('transcript_id')!=doc.get('transcript_id'):raise ValueError('Identitas transkrip berubah')
    if op.get('transcript_revision')!=doc['transcript_revision']:raise Conflict(revision,'Transkrip berubah; draf tetap tersedia')
    ids=op.get('origin_word_ids')
    if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)):raise ValueError('ID kata harus lengkap dan unik')
    rows=service.transcript(doc,cid,vid)['words'];positions=[i for i,w in enumerate(rows) if set(w.get('source_word_ids',[w['word_id']]))&set(ids)]
    if not positions or positions!=list(range(positions[0],positions[-1]+1)) or set(x for i in positions for x in rows[i].get('source_word_ids',[rows[i]['word_id']]))!=set(ids):
        raise ValueError('Frasa berubah atau tidak berurutan')
    selected=[rows[i] for i in positions]
    if cid and any(w['end']<=doc['clips'][cid]['start'] or w['start']>=doc['clips'][cid]['end'] for w in selected):raise ValueError('Kata di luar klip aktif')
    if kind=='m2_speaker':
        speaker=op.get('speaker_id')
        if speaker is not None and (not isinstance(speaker,str) or not 1<=len(speaker.strip())<=100):raise ValueError('Nama speaker tidak valid')
        for wid in ids:doc.setdefault('manual_speakers',{})[dumps(wid)]={'transcript_id':doc['transcript_id'],'speaker_id':speaker.strip() if speaker else None}
    else:
        if len(selected)!=1:raise ValueError('Edit waktu per unit transkrip; frasa impor tetap satu unit cue')
        start=tracks.number(op.get('start'));end=tracks.number(op.get('end'));duration=doc['source']['info']['duration']
        if not 0<=start<end<=duration:raise ValueError('Waktu di luar durasi sumber')
        scope=op.get('scope','clip')
        if cid and scope not in ('project','shared_utterance') and not doc['clips'][cid]['start']<=start<end<=doc['clips'][cid]['end']:raise ValueError('Waktu di luar batas klip')
        before=copy.deepcopy(doc)
        patch={'transcript_id':doc['transcript_id'],'origin_word_ids':ids,'start':start,'end':end,'provenance':'user_source_time_review'}
        group=scope_group(doc,cid,vid,op.get('scope','clip'),'source_timing_overrides')
        for key in list(group):
            if set(group[key]['origin_word_ids'])&set(ids):del group[key]
        group[fingerprint(ids)]=patch
        validate_timing_targets(service,before,doc,cid,vid,scope,ids)
    return {'touched':[(cid,vid)] if cid else [],'transcript_changed':True}


class TranscriptService:
    def __init__(self,service):
        self.service=service
        with service.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS m2_track_drafts(id TEXT PRIMARY KEY,project_id TEXT,revision INTEGER,kind TEXT,payload TEXT,digest TEXT,created REAL)')

    def _doc(self,pid,revision=None):
        doc=self.service.store.get(pid)
        if revision is not None and (type(revision) is not int or revision!=doc['revision']):raise Conflict(doc['revision'])
        if content_id(doc['source']['path'],fresh=True)!=doc['source']['source_id']:raise ValueError('Sumber berubah; tautkan dan analisis ulang')
        return doc

    def _draft(self,doc,kind,payload):
        digest=fingerprint([doc['project_id'],doc['revision'],kind,payload]);did='m2-'+digest[:32]
        with self.service.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO m2_track_drafts VALUES(?,?,?,?,?,?,?)',(did,doc['project_id'],doc['revision'],kind,dumps(payload),digest,time.time()))
        return {'draft_id':did,'digest':digest,'revision':doc['revision'],'kind':kind,**payload}

    def draft(self,pid,did,kind,digest):
        with self.service.store.connect() as db:row=db.execute('SELECT * FROM m2_track_drafts WHERE id=? AND project_id=?',(did,pid)).fetchone()
        if not row or row['kind']!=kind or row['digest']!=digest:raise ValueError('Proposal tidak ada atau digest berubah')
        return dict(row),json.loads(row['payload'])

    def snapshot(self,pid):
        doc=self._doc(pid);data=self.service.transcript(doc) if doc.get('transcript_id') else None
        from .speech_m2 import language_matrix
        translated=[{**v,'track_id':k,'stale':v['source_take']!=doc.get('transcript_id') or v['source_revision']!=doc['transcript_revision']} for k,v in doc.get('translation_tracks',{}).items()]
        return {'revision':doc['revision'],'transcript_id':doc.get('transcript_id'),'transcript_revision':doc['transcript_revision'],
            'source_id':doc['source']['source_id'],'duration':doc['source']['info']['duration'],'kind':doc['source']['info'].get('kind','video'),
            'language':data.get('language') if data else None,'runtime_receipt':data.get('runtime_receipt') if data else None,
            'vad':data.get('vad') if data else None,'tracks':translated,'language_matrix':language_matrix(self.service.config(doc)),
            'critical_review':tracks.critical_review(data['words'],doc['settings'].get('glossary',''))[:200] if data else [],
            'translation_proposals':doc.get('translation_proposals',[]),'source_lineage':doc['source'].get('lineage',[])}

    def import_review(self,pid,data):
        doc=self._doc(pid,data['expected_revision'])
        track=tracks.parse(data['text'],data['format'],doc['source']['source_id'],doc['source']['info']['duration'],
            source_language=data.get('language','und'),offset=data.get('offset_seconds',0),provider=data.get('provider','user_import'))
        review=tracks.review_import(track,expected_language=data.get('source_language',data.get('language','und')),
            language_checked=data.get('language_checked',False),source_time_checked=data.get('source_time_checked',False),overlaps_checked=data.get('overlaps_checked',False))
        return self._draft(doc,'import',{'track':track,'review':review})

    def commit_import(self,pid,data):
        row,payload=self.draft(pid,data['draft_id'],'import',data['digest']);doc=self._doc(pid)
        if data['expected_revision']!=row['revision']:raise Conflict(doc['revision'],'Proposal berasal dari revisi lain')
        if not payload['review']['ready']:raise ValueError('Bahasa/offset subtitle belum lolos review')
        take='import-'+row['digest'][:32]
        try:self.service.store.transcript(take)
        except KeyError:self.service.store.save_transcript(pid,payload['track'],take)
        def change(current):
            old=current.get('transcript_id');current['transcript_id']=take;current['transcript_revision']+=1
            current.setdefault('transcript_track_history',[]).append({'from':old,'to':take,'review':payload['review'],'provider':payload['track']['provenance']})
            current['source']['requires_analysis']=False
            return {'transcript_id':take}
        return self.service.store.mutate(pid,data['expected_revision'],data['operation_id'],data,change,'M2 impor subtitle yang ditinjau')

    def translation_review(self,pid,data,*,owned_worker=False):
        doc=self._doc(pid,data['expected_revision']);source=self.service.transcript(doc);cues=tracks.cues_from_words(source['words'])
        target=tracks.language(data['target_language']);provider=data.get('provider','manual')
        from . import translation_m2
        if provider=='ollama':
            if not owned_worker:raise ValueError('Terjemahan Ollama harus melalui antrean GPU')
            rows,receipt=translation_m2.ollama(cues,target,self.service.config(doc))
        elif provider=='manual':rows=data['cues'];receipt={'provider':'manual','inference_performed':False,'actual_model':None,'actual_device':None,'quality':'not_measured'}
        else:raise ValueError('Provider terjemahan tidak valid')
        translated,critical=translation_m2.validate(cues,rows,target)
        words=[{'word_id':'tr:'+str(c['cue_id']),'word':c['text'],'start':c['start'],'end':c['end'],'probability':None,
            'timing_status':'translation_source_cue','speaker_id':c.get('speaker_id'),'source_word_ids':c['origin_word_ids']} for c in translated]
        track={'source_id':doc['source']['source_id'],'words':words,'raw_words':copy.deepcopy(words),'cues':translated,
            'duration':source['duration'],'language':target,'runtime_receipt':receipt,'timebase':'source_seconds',
            'provenance':{'provider':provider,'source_take':doc['transcript_id'],'source_revision':doc['transcript_revision']}}
        return self._draft(doc,'translation',{'track':track,'critical_cues':critical,'source_cues':cues,'source_take':doc['transcript_id'],'source_revision':doc['transcript_revision'],'approved':False})

    def commit_translation(self,pid,data):
        row,payload=self.draft(pid,data['draft_id'],'translation',data['digest']);doc=self._doc(pid)
        proposal=next((p for p in doc.get('translation_proposals',[]) if p.get('draft_id')==row['id'] and p.get('digest')==row['digest']),None)
        allowed=proposal['approval_revision'] if proposal else row['revision']
        if data['expected_revision']!=allowed:raise Conflict(doc['revision'],'Proposal terjemahan berasal dari revisi lain')
        if payload['source_take']!=doc.get('transcript_id') or payload['source_revision']!=doc['transcript_revision']:raise ValueError('Transkrip sumber berubah; buat terjemahan ulang')
        critical={str(x['cue_id']) for x in payload['critical_cues']}
        approved={str(x) for x in data.get('critical_cue_ids',[])}
        if data.get('all_cues_reviewed') is not True or not critical<=approved:raise ValueError('Tinjau semua cue, nama, negasi, angka dan satuan sebelum persetujuan')
        take='translation-'+row['digest'][:32]
        try:self.service.store.transcript(take)
        except KeyError:self.service.store.save_transcript(pid,payload['track'],take)
        def change(current):
            current.setdefault('translation_tracks',{})[take]={'take_id':take,'source_take':payload['source_take'],'source_revision':payload['source_revision'],
                'language':payload['track']['language'],'approved':True,'approval':'human_all_cues_and_critical_facts','runtime_receipt':payload['track']['runtime_receipt']}
            return {'track_id':take}
        return self.service.store.mutate(pid,data['expected_revision'],data['operation_id'],data,change,'M2 persetujuan track terjemahan')

    def export(self,pid,data):
        doc=self._doc(pid,data['expected_revision']);tid=data.get('track_id');cid=data.get('clip_id');vid=data.get('variant_id')
        if tid:
            approved=doc.get('translation_tracks',{}).get(tid)
            if not approved or not approved['approved'] or approved['source_take']!=doc.get('transcript_id') or approved['source_revision']!=doc['transcript_revision']:raise ValueError('Track terjemahan belum disetujui atau usang')
            track=self.service.store.transcript(tid)
        else:track=self.service.transcript(doc,cid,vid)
        track=copy.deepcopy(track);track['source_id']=doc['source']['source_id']
        if cid:
            clip=doc['clips'][cid];track['words']=[w for w in track['words'] if w['end']>clip['start'] and w['start']<clip['end']]
            for w in track['words']:w['start']=max(w['start'],clip['start']);w['end']=min(w['end'],clip['end'])
            track['cues']=tracks.cues_from_words(track['words'])
        else:track['cues']=tracks.effective_cues(track)
        fmt=data['format'];metadata={'project_id':pid,'revision':doc['revision'],'transcript_revision':doc['transcript_revision'],
            'track_id':tid or doc['transcript_id'],'clip_id':cid,'variant_id':vid,'timebase':'source_seconds',
            'chapters':[{'clip_id':k,'start':c['start'],'end':c['end'],'title':c.get('title','')} for k,c in doc['clips'].items()],
            'critical_review':tracks.critical_review(track['words'],doc['settings'].get('glossary','')),'source_lineage':doc['source'].get('lineage',[])}
        text=tracks.export_track(track,fmt,metadata=metadata);key=fingerprint([text,metadata]);folder=self.service.work/pid/'transcript-exports'/key[:24];folder.mkdir(parents=True,exist_ok=True)
        path=folder/('transcript.'+fmt);path.write_text(text,encoding='utf-8');sidecar=folder/'provenance.json';sidecar.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        self._doc(pid,doc['revision'])
        return {'url':self.service.register_file(pid,path),'provenance_url':self.service.register_file(pid,sidecar),'content_id':content_id(path,fresh=True),'revision':doc['revision'],'timebase':'source_seconds'}


def all_patches(document):
    groups=[]
    def walk(value):
        if not isinstance(value,dict):return
        if 'transcript_id' in value and 'origin_word_ids' in value:groups.append(value)
        else:
            for child in value.values():walk(child)
    for key in ('shared_corrections','clip_corrections','variant_corrections','source_timing_overrides','clip_source_timing_overrides','variant_source_timing_overrides','alignment_overrides'):
        walk(document.get(key,{}))
    return groups
