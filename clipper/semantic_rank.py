"""Optional E5 proposals; similarity alone never removes a story."""
import math
from pathlib import Path


def neighbors(eligible,cfg):
    from .visual4 import component_runtime,backend
    report={'code':'e5_comparison','action':'review','source':'local_e5','status':'unavailable',
            'detail':'E5 lokal belum siap; pemeriksaan kutipan biasa tetap berjalan.','removed_by_embedding':0}
    if not component_runtime('e5',cfg):return [],report
    sampled=eligible if len(eligible)<=96 else [eligible[round(i*(len(eligible)-1)/95)] for i in range(96)]
    items=[{'id':i,'text':c['main_claim']+' '+c.get('ending_evidence','')} for i,c in sampled]
    folder=Path(cfg.work_dir)/'semantic-e5';folder.mkdir(parents=True,exist_ok=True)
    result=backend('e5',{'items':items,'adapter_version':'e5-proposals-4.0.10'},cfg,folder)
    report.update(status=result.get('status','failed'),sampled_claims=len(items),total_claims=len(eligible),
                  provenance=result.get('provenance'),cache_reused=result.get('cache_reused',False))
    if result.get('status')!='ready':
        report['detail']=result.get('note','E5 gagal; kandidat dan pemeriksaan kutipan dipertahankan.')
        return [],report
    valid={i for i,_ in sampled};pairs=[]
    try:
        for row in result.get('pairs',[]):
            a,b,score=row['a'],row['b'],float(row['score'])
            if type(a) is not int or type(b) is not int or a==b or a not in valid or b not in valid or not math.isfinite(score) or not -1<=score<=1:
                raise ValueError('Skor atau identitas E5 tidak valid')
            if score>=.88:pairs.append((score,min(a,b),max(a,b)))
        unique=list(dict.fromkeys((a,b) for _,a,b in sorted(pairs,reverse=True)))[:16]
    except (ValueError,TypeError,KeyError):
        report.update(status='failed',detail='Keluaran E5 tidak valid; tidak ada kandidat dihapus.')
        return [],report
    report.update(proposed_pairs=len(unique),detail='E5 mengusulkan pasangan lintas bab. Kutipan, angka, negasi dan syarat tetap diperiksa; skor bukan probabilitas duplikat.')
    return unique,report
