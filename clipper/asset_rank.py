"""Bounded, optional local SigLIP2 ranking before selective visual review."""
import hashlib
import json
from pathlib import Path


def signature(cfg):
    if cfg.broll_ranker=='off':return ['off']
    from .runtime.state import runtime_root,safe_path,read
    root=Path(cfg.visual_runtime_root) if cfg.visual_runtime_root else runtime_root()
    try:
        active=read(root/'components/siglip2/active.json',{}) or {}
        folder=safe_path(root/'generations',active['generation'])
        receipt=folder/'receipt.json'
        return [cfg.broll_ranker,active['generation'],hashlib.sha256(receipt.read_bytes()).hexdigest()]
    except (KeyError,ValueError,TypeError,OSError):return [cfg.broll_ranker,'unavailable']


def rerank(assets,query,context,cfg):
    if cfg.broll_ranker=='off' or not assets:return assets,[]
    from .visual4 import component_runtime,backend
    if not component_runtime('siglip2',cfg):
        note='SigLIP2 lokal belum siap; peringkat visual belum dijalankan.'
        return ([] if cfg.broll_ranker=='siglip2' else assets),[note]
    from .dependency_cache import content_id
    candidates=[{'id':a['provider']+':'+a['id'],'path':a['path'],'content_id':content_id(a['path']),
                 'duration':a.get('duration',3)} for a in assets[:cfg.broll_visual_candidates]]
    folder=Path(cfg.work_dir)/'siglip-ranks';folder.mkdir(parents=True,exist_ok=True)
    request={'assets':candidates,'text':'A video showing '+query+'. '+context[:800]}
    response=backend('siglip2',request,cfg,folder)
    if response.get('status')!='ready':return ([] if cfg.broll_ranker=='siglip2' else assets),[response.get('note','Peringkat visual belum tersedia.')]
    scores={r['id']:r for r in response.get('ranking',[])}
    if any(a['provider']+':'+a['id'] not in scores for a in assets):return assets,['Peringkat visual tidak lengkap; urutan metadata dipertahankan.']
    ranked=[]
    for asset in assets:
        score=scores[asset['provider']+':'+asset['id']]
        ranked.append({**asset,'visual_rank':{**score,'model':'siglip2','provenance':response.get('provenance'),
                       'scope':'relative_image_text_similarity','visual_verified':False,
                       'reason':'Kandidat diurutkan menurut kesamaan frame dengan konteks; pemeriksaan visual tetap terpisah.'}})
    ranked.sort(key=lambda a:(-a['visual_rank']['score'],a['id']))
    return ranked,[]
