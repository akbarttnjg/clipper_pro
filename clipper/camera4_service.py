"""M4 queue/CAS/publication and operator decisions, independent of model scores."""
import copy
from pathlib import Path
from .contracts import fingerprint
from .dependency_cache import content_id
from . import camera4_contract as c


def spans_for(service,doc,cid,vid):
    from .editor_contract import segments_for,seconds
    rows=segments_for(doc['clips'][cid],service.variant(doc,cid,vid))
    return c.spans({'source_spans':[{'start':seconds(r['source_start_tick']),'end':seconds(r['source_end_tick'])} for r in rows]})


def effective_controls(service,doc,cid,vid):
    variant=service.variant(doc,cid,vid)
    if 'camera4_controls' in variant:return c.controls(variant['camera4_controls'],doc['source']['info']['duration'])
    old=variant.get('visual_controls',{});regions=[]
    for row in old.get('pins',[])+old.get('protected',[]):
        kind={'speaker':'subject','material':'material','manual':'protected','crop':'crop'}.get(row.get('kind'),'protected')
        regions.append({'id':'legacy-'+row['id'],'kind':kind,'start':row['start'],'end':row['end'],'box':row['box']})
    cfg=service.config(doc,cid,vid);clip=doc['clips'][cid]
    for key,kind in [('material_rect','material'),('speaker_rect','subject')]:
        text=getattr(cfg,key,'')
        if text:regions.append({'id':'legacy-'+key,'kind':kind,'start':clip['start'],'end':clip['end'],'box':[float(v) for v in text.split(',')]})
    return c.controls({'regions':regions},doc['source']['info']['duration'])


def signature(service,doc,cid,vid):
    from .editor_contract import segments_for,render_inputs
    variant=service.variant(doc,cid,vid);clip=doc['clips'][cid]
    data=service.transcript(doc,cid,vid) if doc.get('transcript_id') else {'words':[]}
    return fingerprint([c.VERSION,doc['source']['source_id'],spans_for(service,doc,cid,vid),segments_for(clip,variant),
        render_inputs(variant.get('editor',{})),doc.get('diarization'),doc.get('manual_speakers'),
        [[w['start'],w['end'],w.get('speaker_id'),w.get('speaker_provenance')] for w in data['words']],
        effective_controls(service,doc,cid,vid),content_id(variant['camera4_controls']['attachment']['path'],fresh=True) if variant.get('camera4_controls',{}).get('attachment') else None,
        service.config(doc,cid,vid).audio_stream_index])


def renderable(service,doc,cid,vid):
    variant=service.variant(doc,cid,vid)
    if not variant.get('camera4_enabled'):return None
    report=variant.get('camera4_report')
    if not report or not report.get('approved') or report.get('source_signature')!=signature(service,doc,cid,vid):raise ValueError('Komposisi M4 belum ditinjau atau sumber/clock berubah; analisis dan terima ulang kamera')
    if content_id(doc['source']['path'],fresh=True)!=doc['source']['source_id']:raise ValueError('Isi sumber berubah; kamera lama tidak dipakai')
    editor=variant.get('editor',{})
    if any(editor.get('curves',{}).values()):raise ValueError('M4 menggunakan crop/keyframe sumber sendiri. Hapus kurva transformasi M1 atau matikan M4 pada rasio ini')
    if any(r.get('camera_id','primary')!='primary' for r in editor.get('segments',[])):raise ValueError('Komposisi M4 ini untuk kamera utama; kamera alternatif perlu analisis tersendiri')
    for frame in report.get('frames',[]):
        if not Path(frame['path']).is_file() or content_id(frame['path'],fresh=True)!=frame['content_id']:raise ValueError('Bukti frame M4 berubah/hilang; hasil lama tetap tersedia')
    if report.get('matte') and content_id(report['matte']['path'],fresh=True)!=report['matte']['content_id']:raise ValueError('Carrier mask M4 berubah; analisis ulang mask')
    for sample in report.get('matte',{}).get('model_samples',[]):
        if not Path(sample['path']).is_file() or content_id(sample['path'],fresh=True)!=sample['content_id']:raise ValueError('Bukti sampel mask berubah; final sebelumnya dipertahankan')
    return copy.deepcopy(report)


def covers(report,spans):
    intervals=sorted((s['start'],s['end']) for s in report['segments'])
    for a,b in spans:
        cursor=a
        for left,right in intervals:
            if left>cursor+1e-5:break
            if right>cursor:cursor=right
            if cursor>=b-1e-5:break
        if cursor<b-1e-5:return False
    return True


def snapshot(service,pid,cid,vid):
    doc=service.store.get(pid);variant=service.variant(doc,cid,vid);report=copy.deepcopy(variant.get('camera4_report'));cfg=service.config(doc,cid,vid)
    if report:
        report['stale']=report.get('source_signature')!=signature(service,doc,cid,vid)
        for row in report.get('frames',[]):row['url']=service.register_file(pid,row['path'])
        if report.get('matte'):report['matte']['url']=service.register_file(pid,report['matte']['path'])
    working=doc['source'].get('media_context',{}).get('payload',{}).get('working_path',doc['source']['path'])
    return {'project_id':pid,'clip_id':cid,'variant_id':vid,'revision':doc['revision'],'enabled':bool(variant.get('camera4_enabled')),
        'controls':effective_controls(service,doc,cid,vid),'report':report,'source':{'url':service.register_file(pid,working),'duration':doc['source']['info']['duration']},
        'dimensions':[cfg.target_w,cfg.target_h],'history_count':len(variant.get('camera4_history',[])),
        'ratios':list(doc['clips'][cid]['variants']),'requirements':['VF'+str(i).zfill(2) for i in range(1,18)]}


def apply_command(service,doc,cid,vid,op,revision):
    kind=op.get('op')
    if kind not in ('m4_controls','m4_decide','m4_disable','m4_copy','m4_ratio'):return None
    if not cid:raise ValueError('Pilih klip untuk kamera M4')
    variant=service.variant(doc,cid,vid);duration=doc['source']['info']['duration'];touched=[(cid,vid)]
    if kind=='m4_controls':
        values=c.controls(op.get('values'),duration)
        if values['attachment']:
            from PIL import Image
            path=Path(values['attachment']['path']).expanduser().resolve()
            if path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp') or not path.is_file():raise ValueError('Pilih gambar attachment lokal yang tersedia')
            with Image.open(path) as image:
                if image.width*image.height>16_000_000:raise ValueError('Gambar attachment terlalu besar')
                image.verify()
            values['attachment']['path']=str(path)
        variant['camera4_controls']=values;variant['camera4_enabled']=False
    elif kind=='m4_disable':variant['camera4_enabled']=False
    elif kind=='m4_decide':
        report=variant.get('camera4_report')
        if not report or report['analysis_id']!=op.get('analysis_id') or report.get('source_signature')!=signature(service,doc,cid,vid):raise ValueError('Analisis kamera berubah; muat bukti sumber terbaru')
        accepted=op.get('accepted')
        if type(accepted) is not bool:raise ValueError('Keputusan kamera harus boolean')
        reason=op.get('reason','')
        if not isinstance(reason,str) or not 1<=len(reason.strip())<=1000:raise ValueError('Isi alasan keputusan kamera')
        required={'speaker_identity','material_hud','motion_no_pan','safe_area','source_order'}
        if report.get('matte'):required.add('continuous_mask')
        if report.get('tracking'):required.add('tracking_drift')
        if accepted and not required<=set(op.get('reviewed',[])):raise ValueError('Periksa speaker, materi, gerak, safe area dan urutan sumber sebelum menerima kamera')
        if accepted and content_id(doc['source']['path'],fresh=True)!=doc['source']['source_id']:raise ValueError('Isi sumber berubah')
        if accepted:
            from .camera4_plan import layers
            cfg=service.config(doc,cid,vid)
            for segment in report['segments']:layers(segment,cfg.target_w,cfg.target_h,report['settings'])
        variant.setdefault('camera4_feedback',[]).append({'analysis_id':report['analysis_id'],'accepted':accepted,'reason':reason.strip(),
            'reviewed':sorted(set(op.get('reviewed',[]))),'basis':'human_review','project_revision':revision+1})
        report['approved']=accepted;report['approved_revision']=revision+1;variant['camera4_enabled']=accepted
    elif kind=='m4_copy':
        destinations=op.get('variant_ids')
        if not isinstance(destinations,list) or not destinations or len(set(destinations))!=len(destinations):raise ValueError('Pilih rasio tujuan')
        source_report=variant.get('camera4_report')
        if source_report and source_report.get('source_signature')!=signature(service,doc,cid,vid):raise ValueError('Analisis sumber kamera usang; tidak disalin sebagai bukti baru')
        for target in destinations:
            other=service.variant(doc,cid,target)
            if source_report and not covers(source_report,spans_for(service,doc,cid,target)):raise ValueError('Rentang rasio tujuan belum mempunyai bukti kamera; analisis M4 pada rasio itu')
            def voices(v):return [[w['start'],w['end'],w.get('speaker_id')] for w in service.transcript(doc,cid,v)['words']] if doc.get('transcript_id') else []
            if voices(vid)!=voices(target):raise ValueError('Timing/speaker rasio tujuan berbeda; analisis kameranya secara terpisah')
            other['camera4_controls']=copy.deepcopy(effective_controls(service,doc,cid,vid));other['camera4_enabled']=False
            if variant.get('camera4_report'):
                other['camera4_report']=copy.deepcopy(variant['camera4_report']);other['camera4_report']['approved']=False
                other['camera4_report']['source_signature']=signature(service,doc,cid,target)
            touched.append((cid,target))
    else:
        name=op.get('variant_id_new');width=op.get('width');height=op.get('height')
        if name not in ('square','feed','custom') or any(type(v) is not int or not 64<=v<=3840 or v%2 for v in (width,height)):raise ValueError('Rasio tambahan memerlukan ukuran genap 64–3840 pixel')
        if name in doc['clips'][cid]['variants']:raise ValueError('Rasio sudah ada; edit rasionya secara eksplisit')
        new={'settings':{},'override_keys':[],'timeline_revision':0,'camera4_ratio':[width,height],'camera4_enabled':False,
            'editor':copy.deepcopy(variant.get('editor',{})),'timeline':copy.deepcopy(variant.get('timeline',{})),
            'camera4_controls':copy.deepcopy(variant.get('camera4_controls',{}))}
        doc['clips'][cid]['variants'][name]=new;touched.append((cid,name))
    return {'touched':touched,'transcript_changed':False}


def execute(service,job):
    from .studio_worker import claimed_job,StaleJob
    from . import media_context,camera4_observe,camera4_plan,camera4_tracking
    job=claimed_job(service,job);pid=job['project_id'];cid=job['target']['clip_id'];vid=job['target']['variant_id'];doc=job['request']['snapshot'];cfg=service.config(doc,cid,vid);variant=service.variant(doc,cid,vid)
    settings=effective_controls(service,doc,cid,vid);dependency=job['request']['dependency']
    def check(fresh=False):
        current=service.store.get(pid);state=service.queue.get(job['id'])
        if state['status'] in ('cancel_requested','canceled') or state['owner']!=job['owner'] or state['lease_token']!=job['lease_token']:raise StaleJob('Kamera M4 dibatalkan atau lease berubah')
        if dependency!=service.dependency(current,cid,vid,fresh=fresh,kind='camera_m4'):raise StaleJob('Masukan kamera berubah; laporan lama dipertahankan')
        if content_id(current['source']['path'],fresh=fresh)!=current['source']['source_id']:raise StaleJob('Sumber berubah; kamera lama dipertahankan')
        return current
    def progress(p,message):check();service.queue.update_owned(job,progress=p,message=message)
    check(fresh=True)
    if doc['source']['info'].get('kind')=='audio':raise ValueError('M4 kamera tidak berlaku pada sumber audio tanpa gambar')
    media=media_context.prepare(doc['source']['path'],cfg,progress);source=media['payload']['working_path']
    previous=doc['source'].get('media_context',{}).get('payload',{})
    if previous and previous.get('selected_audio_index')!=media['payload']['selected_audio_index']:raise StaleJob('Track suara berubah; ASR/diarization harus mengikuti track yang dipilih')
    folder=service.work/pid/'camera4'/job['id'];report=camera4_observe.analyze(source,doc['source']['source_id'],spans_for(service,doc,cid,vid),settings,cfg,folder,progress)
    data=service.transcript(doc,cid,vid) if doc.get('transcript_id') else {'words':[]};active=camera4_plan.active_evidence(source,report,settings,cfg,folder)
    report.update(settings=settings,active_speaker=active,source_signature=signature(service,doc,cid,vid),approved=False)
    if settings['tracker']:
        report['tracking']=camera4_tracking.track(source,settings['tracker'],report['source_size'],folder,progress,cuts=[s['start'] for s in report['shots']])
        if settings['attachment']:report['attachment']={**settings['attachment'],'content_id':content_id(settings['attachment']['path'],fresh=True)}
    if settings['mask']:
        from .camera4_observe import backend
        request=settings['mask'];result=backend('sam2',{'source':str(source),'source_content_id':content_id(source,fresh=True),
            'time':request['time'],'span':[request['start'],request['end']],'box':c.pixels(request['box'],*report['source_size'])},cfg,folder/'mask')
        report['matte']=camera4_tracking.matte(result,source,request,report['source_size'],folder/'matte')
    report['segments']=camera4_plan.build(report,settings,data['words'],active)
    if report.get('matte'):
        for segment in report['segments']:
            if segment['start']<report['matte']['end'] and segment['end']>report['matte']['start']:
                segment['protected_source'].append({'id':'continuous-mask-envelope','kind':'gesture','box':report['matte']['protected_union']})
    if report.get('tracking'):
        for segment in report['segments']:
            measured=[r['box'] for r in report['tracking']['measurements'] if segment['start']<=r['time']<segment['end']]
            if measured:
                x=min(r[0] for r in measured);y=min(r[1] for r in measured);right=max(r[0]+r[2] for r in measured);bottom=max(r[1]+r[3] for r in measured)
                segment['protected_source'].append({'id':'tracked-object','kind':'object','box':[x,y,right-x,bottom-y]})
    progress(90,'Menyimpan keputusan kamera sebagai proposal')
    def publish(current):
        target=service.variant(current,cid,vid)
        if target.get('camera4_report'):target.setdefault('camera4_history',[]).append(copy.deepcopy(target['camera4_report']))
        target['camera4_report']=report;target['camera4_enabled']=False
    result={'analysis_id':report['analysis_id'],'shots':len(report['shots']),'segments':len(report['segments']),'approved':False}
    from .project_store import Conflict
    for attempt in range(5):
        current=check(fresh=True)
        try:
            service.store.mutate(pid,current['revision'],job['id']+'-publish',{'dependency':dependency},publish,'Proposal kamera M4 tersimpan',
                job_guard={**job,'clip_id':cid,'variant_id':vid},job_result=result)
            break
        except Conflict:
            if attempt==4:raise
    return result
