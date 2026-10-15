"""M7 queue lease, immutable snapshot and guarded publication."""
import copy
from pathlib import Path
from .delivery7_contract import selection
from .dependency_cache import content_id,fresh_scope
from .project_store import Conflict
from .studio_worker import claimed_job,StaleJob


def execute(service,job):
    job=claimed_job(service,job);pid=job['project_id'];choices=job['request']['options'];expected=job['request']['dependency']
    def check(current=None):
        with fresh_scope():
            doc=current or service.store.get(pid);active=service.queue.get(job['id'])
            if active['status']!='running' or active.get('owner')!=job['owner'] or active.get('lease_token')!=job['lease_token']:raise StaleJob('M7 dibatalkan atau lease berubah')
            if selection(service,doc,choices,fresh=True,require_ready=True)['dependency']!=expected:raise StaleJob('Pilihan/hasil final M7 berubah; buat paket kembali')
            if doc['source'].get('requires_analysis') or not Path(doc['source']['path']).is_file() or content_id(doc['source']['path'],fresh=True)!=doc['source']['source_id']:raise StaleJob('Sumber berubah; analisis/render ulang')
            return doc
    doc=check();state=selection(service,doc,choices,fresh=True,require_ready=True);results=[]
    for row in state['targets']:
        cid=row['clip_id'];vid=row['variant_id'];result=copy.deepcopy(service.variant(doc,cid,vid)['result'])
        result.update(clip_id=cid,variant_id=vid,title=doc['clips'][cid]['title']);results.append(result)
    from .delivery7 import build
    value=build(results,service.config(doc),choices,project_id=pid,revision=doc['revision'],dependency=expected,
        progress=lambda p,m:service.queue.update_owned(job,progress=int(p),message=m),before_seal=check)
    value.update(variant_id='both' if len(choices['ratios'])>1 else choices['ratios'][0],clip_ids=list(dict.fromkeys(r['clip_id'] for r in results)))
    value['url']=service.register_file(pid,value['zip'])
    def publish(current):
        check(current);current.setdefault('exports',[]).append(value)
    for attempt in range(5):
        current=check()
        try:
            saved=service.store.mutate(pid,current['revision'],job['id']+'-publish',{'dependency':expected},publish,'Delivery M7 · '+str(len(results))+' final',job_guard=job,job_result=value);break
        except Conflict:
            if attempt==4:raise
    service.queue.update_owned(job,message=f"M7 tersimpan · {len(results)} hasil · revisi {saved['revision']}")
    return value
