"""M3 project transactions, human feedback, source maps and queued publication."""
import copy
from dataclasses import replace
import time
from pathlib import Path
from .contracts import fingerprint
from .dependency_cache import content_id,fresh_scope
from .project_store import Conflict
from . import selection_contract as sc


def transcript(service,doc,scope='display'):
    if not doc.get('transcript_id'):
        return {'duration':doc['source']['info']['duration'],'words':[],
            'runtime_receipt':{'inference_performed':False,'provider':'no_transcript_requested'}}
    if scope=='display':return service.transcript(doc)
    data=service.store.transcript(doc['transcript_id'])
    data['words']=copy.deepcopy(data.get('heard_words',data.get('raw_words',data['words'])))
    from .transcript_service import project_words
    data['words']=project_words(data['words'],doc)
    return data


def signature(service,doc,scope='display'):
    data=transcript(service,doc,scope)
    rows,words=sc.sentences(data['words'],data['duration'])
    return fingerprint([sc.VERSION,doc['source']['source_id'],doc.get('transcript_id'),scope,
        [[w['word_id'],w['word'],w['start'],w['end'],w.get('speaker_id'),w.get('speaker_provenance'),w.get('probability'),w.get('aligned_words'),w.get('alignment_method')] for w in words]])


def required_review(candidate):
    required=['claim','caveats','conclusion','source_order','critical_tokens'] if candidate['claims'] else ['source_audio_visual','source_order']
    for flag,name in [('duration_extension','duration_extension'),('list_items_require_review','list_items'),('speaker_identity_requires_review','speaker_identity'),('opening_context','opening_context'),('weak_source_confidence','weak_source_confidence'),('financial_assumptions_and_risk','financial_risk')]:
        if flag in candidate['completeness']['review_flags']:required.append(name)
    return required


def snapshot(service,pid,*,offset=0,limit=25):
    doc=service.store.get(pid);report=copy.deepcopy(doc.get('selection3') or {})
    stale=bool(report and report.get('source_signature')!=signature(service,doc,report['requested_constraints']['scope']))
    offset=max(0,int(offset));limit=max(1,min(100,int(limit)));candidates=report.pop('candidates',[])
    ids=set(report.get('selection',{}).get('recommended_ids',[]));candidates.sort(key=lambda c:(c['candidate_id'] not in ids,c['start'],c['candidate_id']))
    for c in candidates[offset:offset+limit]:
        decision=doc.get('m3_decisions',{}).get(c['candidate_id'])
        if decision and decision.get('content_fingerprint')==c['content_fingerprint'] and decision.get('source_signature')==report.get('source_signature'):
            c['selection_status']=decision['status'];c['human_decision']=decision
        c['required_review']=required_review(c)
        working=doc['source'].get('media_context',{}).get('payload',{}).get('working_path',doc['source']['path'])
        c['source_url']=service.register_file(pid,working)
        for evidence in c.get('evidence',[]):
            path=evidence.get('frame_path')
            if path and Path(path).is_file():evidence['frame_url']=service.register_file(pid,path)
    return {'project_id':pid,'revision':doc['revision'],'transcript_id':doc.get('transcript_id'),
        'transcript_revision':doc.get('transcript_revision',0),'report':report,'candidates':candidates[offset:offset+limit],
        'total':len(candidates),'next_offset':offset+limit if offset+limit<len(candidates) else None,
        'stale':stale,'source_markers':doc.get('m3_markers',[]),'feedback_count':len(doc.get('m3_feedback',[])),
        'source':{'url':service.register_file(pid,doc['source'].get('media_context',{}).get('payload',{}).get('working_path',doc['source']['path'])),
            'kind':doc['source']['info'].get('kind','video'),'duration':doc['source']['info']['duration']},
        'render_selection_count':sum(c.get('included',True) and (c.get('created_from')!='M3' or c.get('selection_status')=='accepted') for c in doc.get('clips',{}).values()),
        'review_contract':'A human decision is separate from model scores; rejected clips cannot render or publish.'}


def _active(service,doc,op):
    report=doc.get('selection3')
    if not report or report.get('analysis_id')!=op.get('analysis_id'):raise ValueError('Hasil seleksi berubah; muat kandidat terbaru tanpa membuang draf')
    scope=report['requested_constraints']['scope'];current_signature=signature(service,doc,scope)
    if report.get('source_signature')!=current_signature:raise ValueError('Teks/timing/speaker sumber berubah; lakukan seleksi ulang tanpa ASR ulang')
    if content_id(doc['source']['path'],fresh=True)!=doc['source']['source_id']:raise ValueError('Isi sumber berubah; kandidat lama belum dapat dipakai')
    return report,current_signature


def apply_command(service,doc,cid,vid,op,revision):
    kind=op.get('op')
    if kind not in ('m3_decide','m3_story','m3_marker','m3_select_set'):return None
    if kind=='m3_marker':
        t=sc.number(op.get('time'));duration=doc['source']['info']['duration']
        if not 0<=t<=duration:raise ValueError('Penanda berada di luar sumber')
        label=op.get('label','Penanda pengguna')
        if not isinstance(label,str) or not 1<=len(label.strip())<=160:raise ValueError('Judul penanda tidak valid')
        ident='marker-'+fingerprint([doc['source']['source_id'],t,label])[:24]
        if not any(r['event_id']==ident for r in doc.get('m3_markers',[])):
            doc.setdefault('m3_markers',[]).append({'event_id':ident,'kind':'user_source_marker','time':t,
                'source_id':doc['source']['source_id'],'label':label,'provenance':'human_hotkey_or_button',
                'created_at':time.time(),'confidence':None})
        return {'touched':[],'transcript_changed':False}
    report,source_signature=_active(service,doc,op)
    requested=report['requested_constraints'];data=transcript(service,doc,requested['scope']);rows,words=sc.sentences(data['words'],data['duration'])
    if kind=='m3_select_set':
        ids=op.get('candidate_ids',report['selection']['recommended_ids'])
        if not isinstance(ids,list) or not 1<=len(ids)<=100 or len(set(ids))!=len(ids):raise ValueError('Pilih 1–100 kandidat untuk set render')
        accepted=doc.get('m3_decisions',{})
        if any(i not in accepted or accepted[i]['status']!='accepted' or accepted[i].get('source_signature')!=source_signature for i in ids):
            raise ValueError('Terima seluruh kandidat dalam set ini terlebih dahulu')
        if requested['count'] and len(ids)>requested['count']:raise ValueError('Set melebihi jumlah diminta; pilih sesuai target atau ubah jumlah pencarian')
        wanted={accepted[i]['clip_id'] for i in ids}
        for clip_id,clip in doc['clips'].items():clip['included']=clip_id in wanted
        doc['m3_selected_set']={'analysis_id':report['analysis_id'],'candidate_ids':ids,'clip_ids':sorted(wanted),
            'requested_count':requested['count'],'selected_count':len(ids),'shortfall':max(0,requested['count']-len(ids)),
            'created_at':time.time(),'decision_basis':'explicit_human_render_set'}
        return {'touched':[],'transcript_changed':False}
    if kind=='m3_story':
        source_spans=op.get('source_spans')
        if source_spans is None:
            ids=op.get('candidate_ids')
            if not isinstance(ids,list) or not 2<=len(ids)<=16 or len(set(ids))!=len(ids):raise ValueError('Pilih 2–16 kandidat berbeda dalam urutan cerita')
            by_id={c['candidate_id']:c for c in report['candidates']}
            if any(i not in by_id for i in ids):raise ValueError('Kandidat gabungan tidak ditemukan')
            source_spans=[span for ident in ids for span in by_id[ident]['source_spans']]
        proposed=sc.candidate(source_spans,rows,words,requested,doc['source']['source_id'],title=op.get('title','Cerita beberapa segmen'),provider='human_story_proposal')
        proposed['source_links']=[{'source_id':span['source_id'],'source_start':span['start'],'source_end':span['end']} for span in proposed['source_spans']]
        proposed['matched_topics']=[]
        proposed['scores']={'completeness':{'value':0. if proposed['completeness']['hard_blockers'] else 1.,'basis':'structural_checks'},'appeal':{'value':None,'probability_of_views':None}}
        if not any(c['candidate_id']==proposed['candidate_id'] for c in report['candidates']):report['candidates'].append(proposed)
        doc['last_m3_story_candidate']=proposed['candidate_id']
        return {'touched':[],'transcript_changed':False}
    current=next((c for c in report['candidates'] if c['candidate_id']==op.get('candidate_id')),None)
    if current is None:raise ValueError('Kandidat tidak ditemukan pada analisis aktif')
    status=op.get('status')
    if status not in ('accepted','rejected','needs_review'):raise ValueError('Pilih terima, tolak, atau perlu ditinjau')
    reason=op.get('reason','')
    if not isinstance(reason,str) or len(reason)>1000 or status=='rejected' and not reason.strip():raise ValueError('Penolakan memerlukan alasan; maksimal 1000 karakter')
    reviewed=op.get('reviewed',[])
    if not isinstance(reviewed,list) or any(not isinstance(r,str) for r in reviewed):raise ValueError('Daftar pemeriksaan manusia tidak valid')
    decision={'candidate_id':current['candidate_id'],'content_fingerprint':current['content_fingerprint'],
        'analysis_id':report['analysis_id'],'source_signature':source_signature,'status':status,'reason':reason.strip(),
        'reviewed':sorted(set(reviewed)),'created_at':time.time(),'actor':'local_user','source_id':doc['source']['source_id'],
        'transcript_take':doc.get('transcript_id'),'transcript_revision':doc.get('transcript_revision',0),
        'model_scores_unchanged':True,'decision_basis':'human_review'}
    clip_id='clip-'+fingerprint([doc['project_id'],current['candidate_id']])[:24];touched=[]
    if status=='accepted':
        rebuilt=sc.candidate(current['source_spans'],rows,words,requested,doc['source']['source_id'],title=current['title'])
        if rebuilt['content_fingerprint']!=current['content_fingerprint']:raise ValueError('Isi kandidat tidak lagi cocok dengan sumber aktif')
        if rebuilt['completeness']['hard_blockers']:raise ValueError('Kandidat belum memenuhi syarat: '+', '.join(rebuilt['completeness']['hard_blockers']))
        required=required_review(current)
        if not set(required)<=set(reviewed):raise ValueError('Periksa sumber dahulu: '+', '.join(k for k in required if k not in reviewed))
        if clip_id not in doc['clips']:
            from . import editor_contract as ec
            clip={'clip_id':clip_id,'candidate_id':current['candidate_id'],'start':current['start'],'end':current['end'],'duration':current['duration'],
                'source_spans':copy.deepcopy(current['source_spans']),'title':current['title'],'reason':current['reason'],
                'keywords':sorted(sc.terms(current['text']))[:8],'main_claim':current['claims'][0]['quote'] if current['claims'] else '',
                'ending_evidence':current['conclusion'][0]['quote'] if current['conclusion'] else '',
                'selection_source':'manual','created_from':'M3','approved':True,'selection_status':'accepted',
                'revision':0,'included':True,'warnings':[],'boundary_review':{'status':'checked','issues':[],'approved_by':'human'},
                'm3_source_signature':source_signature,'m3_scope':requested['scope'],'selection_evidence':copy.deepcopy(current)}
            segments=ec.validate_segments([{'id':'m3-span-'+str(i),'start':s['start'],'end':s['end']} for i,s in enumerate(current['source_spans'])],clip)
            clock=ec.build_clock(segments,service.config(doc).output_fps)
            clip['variants']={v:{'settings':{},'override_keys':[],'timeline_revision':0,
                'editor':{'segments':copy.deepcopy(segments),'clock_digest':clock['digest']},
                'timeline':{'keep_spans':[[s['start'],s['end']] for s in current['source_spans']]}} for v in ('portrait','landscape')}
            doc['clips'][clip_id]=clip
        else:doc['clips'][clip_id].update(included=True,selection_status='accepted',approved=True,m3_source_signature=source_signature)
        decision['clip_id']=clip_id;touched=[(clip_id,v) for v in ('portrait','landscape')]
    elif clip_id in doc['clips']:
        doc['clips'][clip_id].update(included=False,selection_status=status,approved=False);decision['clip_id']=clip_id
        touched=[(clip_id,v) for v in ('portrait','landscape')]
    current['selection_status']=status
    doc.setdefault('m3_decisions',{})[current['candidate_id']]=decision
    doc.setdefault('m3_feedback',[]).append(copy.deepcopy(decision))
    return {'touched':touched,'transcript_changed':False}


def renderable(service,doc,clip):
    if clip.get('created_from')!='M3':return
    if clip.get('selection_status')!='accepted':raise ValueError('Klip M3 belum diterima atau sudah ditolak; final tidak dapat dibuat')
    if clip.get('m3_source_signature')!=signature(service,doc,clip.get('m3_scope','display')):
        raise ValueError('Sumber teks/timing berubah setelah keputusan M3; seleksi dan review ulang sebelum final')


def invalidate(service,doc):
    cache={}
    for clip in doc.get('clips',{}).values():
        if clip.get('created_from')!='M3' or clip.get('selection_status')!='accepted':continue
        scope=clip.get('m3_scope','display')
        if scope not in cache:cache[scope]=signature(service,doc,scope)
        if cache[scope]!=clip.get('m3_source_signature'):
            clip.update(selection_status='needs_review',included=False,approved=False)


def execute(service,job):
    from .studio_worker import StaleJob
    from . import media_context,selection_engine
    doc=copy.deepcopy(job['request']['snapshot']);pid=doc['project_id'];requested=job['request']['options'];cfg=service.config(doc)
    def check(*,fresh=False):
        active=service.queue.get(job['id'])
        if active['status']!='running' or active['owner']!=job['owner'] or active.get('lease_token')!=job.get('lease_token'):raise StaleJob('Seleksi dibatalkan atau lease berubah')
        current=service.store.get(pid)
        if content_id(current['source']['path'],fresh=fresh)!=current['source']['source_id']:
            raise StaleJob('Isi sumber berubah; analisis atau tautkan sumber yang benar sebelum seleksi')
        expected=fingerprint([service.dependency(current,kind='selection_m3',fresh=fresh),requested])
        if expected!=job['request']['dependency']:raise StaleJob('Sumber seleksi berubah; proposal lama dipertahankan')
        return current
    def progress(value,message):
        check();service.queue.update_owned(job,progress=int(value),message=message)
    check(fresh=True);media=media_context.prepare(doc['source']['path'],cfg,progress)
    scope=requested.get('scope','display');data=transcript(service,doc,scope)
    previous=doc['source'].get('media_context',{}).get('payload',{})
    if data['words'] and previous and previous.get('selected_audio_index')!=media['payload']['selected_audio_index']:
        raise ValueError('Track suara berubah; transkripsikan atau verifikasi subtitle sumber baru sebelum seleksi M3')
    try:
        report=selection_engine.analyze(data,requested,cfg,source_id=media['source_id'],take=doc.get('transcript_id'),
            media=media['payload']['working_path'],media_kind=media['payload']['kind'],markers=doc.get('m3_markers',[]),progress=progress)
    finally:
        if requested['provider']=='ollama':
            from .editorial import release
            release(cfg)
    report.update(source_signature=signature(service,doc,scope),input_revision=doc['revision'],
        transcript_revision=doc.get('transcript_revision',0),input_dependency=job['request']['dependency'])
    empty_take=None
    if not doc.get('transcript_id'):
        empty_take='m3-without-transcript-'+fingerprint([pid,media['source_id'],media['payload']['audio_stream_id']])[:24]
        empty={'duration':media['payload']['duration'],'words':[],'raw_words':[],'raw_words_available':False,
            'source_id':media['source_id'],'runtime_receipt':{'provider':'no_transcript_requested','inference_performed':False},
            'warnings':['Kandidat visual/audio tanpa transkrip; isi ucapan belum dinilai.']}
        try:service.store.transcript(empty_take)
        except KeyError:service.store.save_transcript(pid,empty,empty_take)
    result={'analysis_id':report['analysis_id'],'candidates':len(report['candidates']),
        'recommended':len(report['selection']['recommended_ids']),'shortfall':report['selection']['shortfall'],
        'asr_invoked':False,'provider':report['requested_constraints']['provider'],'index_reused':report['index']['cache_reused']}
    def publish(current):
        check(fresh=True)
        if current.get('selection3'):
            current.setdefault('selection3_history',[]).append(copy.deepcopy(current['selection3']))
        current['selection3']=copy.deepcopy(report)
        current['source'].update(media_context=media,source_id=media['source_id'])
        if not current.get('transcript_id'):
            current['transcript_id']=empty_take;current['transcript_revision']=current.get('transcript_revision',0)+1
            current['selection3']['transcript_take']=empty_take;current['selection3']['source_signature']=signature(service,current,scope)
        current['source']['requires_analysis']=False
        invalidate(service,current)
    for attempt in range(5):
        current=check(fresh=True)
        try:
            saved=service.store.mutate(pid,current['revision'],job['id']+'-publish',{'job_id':job['id'],'dependency':job['request']['dependency']},publish,
                'Seleksi M3 · '+str(len(report['candidates']))+' kandidat',job_guard=job,job_result=result)
            break
        except Conflict:
            if attempt==4:raise
    service.queue.update_owned(job,message='Seleksi M3 tersimpan pada revisi '+str(saved['revision'])+'; terima kandidat sebelum render')
    return result
