"""Audio-only A/B and stem export share the approved M1/M2/M5 snapshot."""
import copy
from dataclasses import replace
from pathlib import Path
from .audio6_contract import VERSION,number
from .dependency_cache import content_id
from .project_store import Conflict

def options(value):
    if not isinstance(value,dict) or set(value)-{'seconds'}:raise ValueError('Opsi audio M6 tidak dikenal')
    n=number(value.get('seconds',8.),0,30,'Sampel audio')
    if 0<n<2:raise ValueError('Sampel minimal dua detik; nol berarti audio lengkap')
    return {'seconds':n}

def execute(service,job):
    from .studio_worker import StaleJob
    from . import media_context,editplan
    from .studio_exchange import render_words
    from .editor_media import prepare
    from .audio6 import premix,finalize
    from .audio6_contract import effective
    from .artifact_store import ArtifactSet,capture_plan_files,rebase
    from .storage import write_json
    pid=job['project_id'];cid=job['target']['clip_id'];vid=job['target']['variant_id'];dependency=job['request']['dependency']
    doc=copy.deepcopy(job['request']['snapshot']);cfg=service.config(doc,cid,vid)
    def check():
        active=service.queue.get(job['id']);current=service.store.get(pid)
        if active['status']!='running' or active['owner']!=job['owner'] or active['lease_token']!=job['lease_token']:raise StaleJob('Audio dibatalkan; hasil sebelumnya dipertahankan')
        if service.dependency(current,cid,vid,fresh=True,kind='audio_m6')!=dependency:raise StaleJob('Input audio berubah; hasil lama tidak ditimpa')
        return current
    def progress(n,message):check();service.queue.update_owned(job,progress=n,message=message)
    check();folder=service.work/pid/'audio6-attempts'/job['id'];folder.mkdir(parents=True,exist_ok=True)
    progress(3,'Menyiapkan sumber dan clock audio')
    media=media_context.prepare(doc['source']['path'],cfg,progress);source=media['payload']['working_path']
    clip={k:copy.deepcopy(v) for k,v in doc['clips'][cid].items() if k!='variants'};variant=service.variant(doc,cid,vid)
    if variant.get('timeline'):clip['manual_keep_spans']=variant['timeline']['keep_spans']
    transcript=service.transcript(doc,cid,vid);words=render_words(transcript,doc,clip,cfg)
    source,words,clip,cfg,receipt=prepare(service,doc,cid,vid,source,words,clip,cfg,progress)
    seconds=job['request']['options']['seconds'];cfg=replace(cfg,preview_seconds=seconds,work_dir=str(folder),job_id='')
    if cfg.source_kind in ('board','screen','chart','graphic') and cfg.preserve_material_pauses:cfg=replace(cfg,trim_silence=False)
    plan=editplan.build(words,clip,cfg);plan['display_words']=plan['words'];plan['captions']={'phrases':[],'censor_intervals':[]};plan['source']={'path':str(source),'source_id':doc['source']['source_id']}
    plan['audio6_context']={'project_id':pid,'clip_id':cid,'variant_id':vid,'input_revision':doc['revision'],'dependency':dependency}
    if clip.get('_editor_clock'):plan['editor']={'clock':clip['_editor_clock'],'tracks':clip['_editor_tracks'],'advanced_source_layer':'baked'}
    if cfg.finishing5:
        from .finishing5_plan import censor_spans
        from .finishing5_contract import effective as style
        plan['captions']['censor_intervals']=censor_spans(plan['words'],style(cfg))
    progress(12,'Membuat sumber before/after, track dan ducking')
    mix=premix(source,plan,cfg,folder);progress(65,'Normalisasi mix final dan pengukuran audio')
    master=finalize(plan,cfg,mix,folder);check()
    plan['audio6']['input_revision']=doc['revision'];plan['audio6']['dependency']=dependency
    txn=ArtifactSet(service.work/pid/'audio6-sets',{'kind':'audio_m6','input_revision':doc['revision'],'dependency':dependency,'clip_id':cid,'variant_id':vid})
    try:
        plan=capture_plan_files(txn,plan,folder)
        report=txn.staging/'audio-report.json';write_json(report,plan);value={'version':VERSION,'master':plan['audio6']['master'],
            'before':plan['audio6']['source']['before'],'processed':plan['audio6']['source']['processed'],
            'stem_archive':plan['audio6'].get('stem_archive'),'report_path':str(txn.final/'audio-report.json'),
            'meter':plan['audio6']['meter_pcm'],'duration':plan['duration'],'settings':effective(cfg),
            'dependency':dependency,'input_revision':doc['revision'],'snapshot_digest':plan['audio6']['snapshot_digest']}
        txn.metadata['required_members']=[p.relative_to(txn.staging).as_posix() for p in txn.staging.rglob('*') if p.is_file()]
        check();value.update(txn.seal())
    except BaseException as exc:txn.abort(exc);raise
    for attempt in range(5):
        current=check()
        def publish(d):service.variant(d,cid,vid).setdefault('audio6',{})['review']=value
        try:
            service.store.mutate(pid,current['revision'],job['id']+'-publish',{'dependency':dependency},publish,'Audio M6 dan stem tersimpan',job_guard={**job,'clip_id':cid,'variant_id':vid},job_result=value)
            return value
        except Conflict:
            if attempt==4:raise
