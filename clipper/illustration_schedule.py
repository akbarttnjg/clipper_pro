"""Map proposals across every retained shot with continuous asset offsets."""
from pathlib import Path


def attach(plan,recipe,cfg):
    events=[];report=[];fps=plan['fps'];warnings=plan.setdefault('warnings',[])
    def skip(scene,a,b,reason):
        if b>a:report.append({'proposal_id':scene.get('id'),'source_start':a,'source_end':b,'status':'skipped','reason':reason})
    for scene in recipe.get('scenes',[]):
        left,right=float(scene['source_start']),float(scene['source_end'])
        if not left<right:continue
        if cfg.broll_mode=='off' or not scene.get('enabled',True):
            skip(scene,left,right,'Dinonaktifkan');continue
        asset=scene.get('asset',{})
        if not Path(asset.get('path','')).is_file():
            skip(scene,left,right,'Berkas aset tidak ditemukan');continue
        covered=[]
        for shot in plan['shots']:
            a=max(left,shot['source_start']);b=min(right,shot['source_end'])
            if b<=a:continue
            covered.append((a,b))
            span=next((s for s in plan['spans'] if s['start']<=shot['start']<s['end']),{})
            reason=('Materi/papan tulis dipertahankan' if shot.get('has_material') or cfg.source_kind=='board'
                    else 'Pembuka kutipan dipertahankan' if span.get('kind')=='cold_open' else None)
            start_frame=round((shot['start']+a-shot['source_start'])*fps)
            end_frame=round((shot['start']+b-shot['source_start'])*fps)
            if not cfg.preview_seconds and (start_frame/fps<3.8 or end_frame/fps>plan['duration']-2):reason='Pembuka/penutup dipertahankan'
            if reason:skip(scene,a,b,reason);continue
            offset=float(scene.get('asset_start',0))+a-left
            available=asset.get('duration')
            if available is not None:end_frame=min(end_frame,start_frame+max(0,int((float(available)-offset)*fps)))
            if end_frame<=start_frame:skip(scene,a,b,'Aset terlalu pendek atau tidak ada frame');continue
            start,end=start_frame/fps,end_frame/fps
            # One-frame overlaps after quantization are removed deterministically.
            for prior in events:
                if start<prior['end'] and end>prior['start']:
                    reason='Bertumpuk dengan ilustrasi yang lebih dahulu dipilih';break
            if reason:skip(scene,a,b,reason);continue
            event={**scene,'source_start':a,'source_end':a+end-start,'start':start,'end':end,
                'start_frame':start_frame,'end_frame':end_frame,'duration':end-start,
                'asset_start':offset,'source_asset_start':offset,'path':asset['path']}
            events.append(event)
            report.append({'proposal_id':scene.get('id'),'source_start':a,'source_end':a+end-start,
                'start':start,'end':end,'asset_start':offset,'duration':end-start,'status':'scheduled','reason':'Rentang dipakai'})
            if a+end-start<b-1/fps:skip(scene,a+end-start,b,'Sisa durasi aset tidak cukup')
        cursor=left
        for a,b in sorted(covered):
            if a>cursor:skip(scene,cursor,a,'Bagian sumber terpangkas atau di luar klip')
            cursor=max(cursor,b)
        if cursor<right:skip(scene,cursor,right,'Bagian sumber terpangkas atau di luar klip')
    plan['broll']=sorted(events,key=lambda e:e['start']);plan['broll_schedule']=report
    warnings.extend(list(dict.fromkeys([*recipe.get('notes',[]),*(r['reason'] for r in report if r['status']=='skipped')])))
    return report


def credits(plan):
    return [{'provider':e['asset'].get('provider','local'),'title':e['asset'].get('title','Ilustrasi'),
        'author':e['asset'].get('author',''),'url':e['asset'].get('page_url',''),
        'license':e['asset'].get('license_url',''),'credit':e['asset'].get('attribution',''),
        'start':e['start'],'end':e['end'],'asset_start':e.get('source_asset_start',e.get('asset_start',0))}
        for e in plan.get('broll',[])]
