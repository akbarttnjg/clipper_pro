"""Selected-clip coverage and immutable export snapshots for both ratios."""
import copy
from .contracts import fingerprint

RATIOS=('portrait','landscape')


def targets(doc):
    rows=[{'clip_id':cid,'variant_id':vid} for cid,c in doc.get('clips',{}).items()
          if c.get('included',True) for vid in RATIOS]
    if not rows:raise ValueError('Pilih setidaknya satu klip untuk kedua rasio.')
    return rows


def snapshot(service,doc,*,fresh=False,mode=None,require_ready=False):
    from .dependency_cache import fresh_scope
    with fresh_scope():return _snapshot(service,doc,fresh=fresh,mode=mode,require_ready=require_ready)


def _snapshot(service,doc,*,fresh=False,mode=None,require_ready=False):
    rows=[];blockers=[]
    if mode is not None:
        from .workflow6 import EXPORT_MODES
        if mode not in EXPORT_MODES:raise ValueError('Mode ekspor tidak valid.')
    for target in targets(doc):
        cid=target['clip_id'];vid=target['variant_id'];variant=service.variant(doc,cid,vid)
        dependency=service.dependency(doc,cid,vid,fresh=fresh)
        readiness=service.export_readiness(doc,cid,vid,dependency=dependency,fresh=fresh)
        if readiness['status']!='ready':blockers.append({**target,**readiness,'title':doc['clips'][cid]['title']})
        if mode=='native' and readiness['status']=='ready':
            from .workflow6 import export_options
            choice=next(r for r in export_options(variant) if r['id']==mode)
            if not choice['available']:blockers.append({**target,'status':'unsupported','title':doc['clips'][cid]['title'],'message':' '.join(choice['reasons'])})
        result=variant.get('result') or {}
        rows.append({**target,'dependency':dependency,
                     'reference':{k:result.get(k) for k in ('width','height','length','duration','output_content_id')},
                     'output_content_id':result.get('output_content_id'),
                     'plan_content_id':result.get('plan_content_id'),
                     'absolute_file':result.get('absolute_file'),'plan_path':result.get('plan_path')})
    if require_ready and blockers:
        names='; '.join(f"{r['title']} ({'9:16' if r['variant_id']=='portrait' else '16:9'}): {r['message']}" for r in blockers[:12])
        raise ValueError('Paket seluruh klip belum lengkap. '+names)
    return {'targets':rows,'dependency':fingerprint(['batch7-v1',rows]),'blockers':blockers,
            'selected_clips':len(rows)//2,'timelines':len(rows),'ready':not blockers}


def export_project(service,job):
    from pathlib import Path
    from . import projects
    from .dependency_cache import content_id, fresh_scope
    from .project_store import Conflict
    from .studio_worker import StaleJob
    pid=job['project_id'];options=job['request'].get('options',{});mode=options.get('mode','hybrid')
    expected=job['request']['dependency']
    def check():
        with fresh_scope():return validate()
    def validate():
        doc=service.store.get(pid)
        if service.queue.get(job['id'])['status']=='cancel_requested':raise StaleJob('Paket dibatalkan.')
        current=snapshot(service,doc,fresh=True,mode=mode,require_ready=True)
        if expected!=current['dependency']:raise StaleJob('Pilihan klip atau hasil final berubah; buat paket kembali.')
        if doc['source'].get('requires_analysis') or not Path(doc['source']['path']).is_file() or content_id(doc['source']['path'],fresh=True)!=doc['source']['source_id']:
            raise StaleJob('Sumber berubah; analisis ulang sebelum membuat paket.')
        return doc,current
    doc,state=check();results=[]
    for target in state['targets']:
        cid=target['clip_id'];vid=target['variant_id']
        result=copy.deepcopy(service.variant(doc,cid,vid)['result'])
        result.update(clip_id=cid,variant_id=vid,title=doc['clips'][cid]['title']+' ['+('9x16' if vid=='portrait' else '16x9')+']')
        results.append(result)
    def progress(value,message):service.queue.update(job['id'],progress=int(value),message=message)
    result=projects.export_bundle(results,service.config(doc),progress,mode=mode)
    if result['timelines']!=state['timelines']:raise ValueError('Jumlah timeline tidak sesuai klip dan rasio yang dipilih.')
    result.update(variant_id='both',clip_ids=list(dict.fromkeys(t['clip_id'] for t in state['targets'])),
                  coverage=[{k:t[k] for k in ('clip_id','variant_id','output_content_id','reference')} for t in state['targets']],
                  dependency=expected,input_revision=doc['revision'],package_content_id=content_id(result['zip'],fresh=True))
    result['url']=service.register_file(pid,result['zip'])
    def publish(current):
        if snapshot(service,current,fresh=True,mode=mode,require_ready=True)['dependency']!=expected:raise StaleJob('Hasil final berubah sebelum paket tersimpan.')
        current.setdefault('exports',[]).append(result)
    for attempt in range(5):
        current,_=check()
        try:
            saved=service.store.mutate(pid,current['revision'],job['id']+'-publish',{'dependency':expected},publish,'Paket seluruh klip · dua rasio');break
        except Conflict:
            if attempt==4:raise
    service.queue.update(job['id'],status='completed',progress=100,message=f"Paket {len(results)} timeline tersimpan · revisi {saved['revision']}",result=result)
    return result
