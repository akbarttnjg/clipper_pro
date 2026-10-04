"""Timeline scheduling owned by workstream B."""
from pathlib import Path

def attach(plan,recipe,cfg):
    events=[]; notices=[]
    if cfg.broll_mode=='off': plan['broll']=[];return
    for scene in recipe.get('scenes',[]):
        if not scene.get('enabled',True): continue
        asset=scene['asset']
        if not Path(asset['path']).is_file():
            notices.append('Satu aset B-roll dipindah; bagian itu memakai sumber asli.');continue
        for shot in plan['shots']:
            start=max(scene['source_start'],shot['source_start']);end=min(scene['source_end'],shot['source_end'])
            if end-start<.8: continue
            if shot.get('has_material') or cfg.source_kind=='board':
                notices.append('Ilustrasi dilewati saat materi/papan tulis terlihat.');continue
            span=next((s for s in plan['spans'] if s['start']<=shot['start']<s['end']),{})
            if span.get('kind')=='cold_open': continue
            a=round((shot['start']+start-shot['source_start'])*plan['fps'])/plan['fps']
            b=round((shot['start']+end-shot['source_start'])*plan['fps'])/plan['fps']
            if not cfg.preview_seconds and (a<3.8 or b>plan['duration']-2): continue
            events.append({**scene,'start':a,'end':b,'duration':b-a,'asset_start':max(0.,start-scene['source_start']),'path':asset['path']})
            break
    plan['broll']=sorted(events,key=lambda e:e['start'])
    plan['warnings'].extend(list(dict.fromkeys([*recipe.get('notes',[]),*notices])))


def credits(plan):
    return [{'provider':e['asset']['provider'],'title':e['asset']['title'],'author':e['asset']['author'],
        'url':e['asset']['page_url'],'license':e['asset']['license_url'],'credit':e['asset'].get('attribution',''),
        'start':e['start'],'end':e['end']} for e in plan.get('broll',[])]
