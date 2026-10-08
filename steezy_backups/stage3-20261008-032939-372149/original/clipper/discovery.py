"""Search objectives, source coverage and auditable semantic diversity."""
import hashlib
import json
import re
from pathlib import Path
import requests
from .storage import read_json, write_json

OBJECTIVES = (
    'Temukan contoh konkret dan demonstrasi yang mandiri, termasuk di bagian akhir sumber.',
    'Temukan jawaban pertanyaan dan koreksi kesalahan; pertahankan konteks yang dibutuhkan.',
    'Temukan langkah praktis dan perbandingan dua cara, lengkap dengan syarat dan risiko.',
    'Temukan analogi, pengalaman, atau penjelasan sebab akibat yang belum terwakili.',
)


def history(cfg):
    return read_json(Path(cfg.work_dir)/'discovery-history.json',[]) or []


def revision(transcript,cfg):
    return hashlib.sha256(json.dumps([transcript['words'],cfg.model,cfg.audience,cfg.min_clip_s,
        cfg.max_clip_s,cfg.selection_floor,'discovery-1'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]


def extra_windows(segments, cfg, existing, cues, round_number):
    if not segments:
        return []
    duration = segments[-1]['end']
    centers = [(float(c['time']),c['kind']) for c in sorted(cues,key=lambda c:c.get('strength',0),reverse=True)]
    # Sweep uncovered source on two scales; offsets change on a new discovery.
    step = max(cfg.min_clip_s, cfg.analysis_window_s/3)
    t = (round_number % 3 + .5)*step/3
    while t < duration:
        if not any(c['start']<=t<=c['end'] for c in existing):
            centers.append((t,'uncovered'))
        t += step
    centers += [(s['start'],'bridge') for s in segments if s['start']%max(1,cfg.analysis_window_s)<8]
    result, seen = [], set()
    # Limit work, not output count. Spread the budget throughout the recording.
    if len(centers)>cfg.discovery_extra_windows:
        visual = centers[:min(3,sum(k not in ('uncovered','bridge') for _,k in centers))]
        rest = centers[len(visual):]
        n = max(1,cfg.discovery_extra_windows-len(visual))
        centers = visual+[rest[min(len(rest)-1,int(i*len(rest)/n))] for i in range(n)] if rest else visual
    for i,(center,kind) in enumerate(centers):
        span = max(cfg.max_clip_s+cfg.topic_grace_s,90) if i%2==0 else cfg.analysis_window_s*1.35
        block = [s for s in segments if center-span/2<=s['start']<center+span/2]
        if not block:
            continue
        key = (block[0]['id'],block[-1]['id'])
        if key in seen:
            continue
        seen.add(key);result.append((block,kind))
    return result[:cfg.discovery_extra_windows]


def coverage(blocks, completed, duration):
    intervals = sorted((blocks[i][0]['start'],blocks[i][-1]['end']) for i in completed if blocks[i])
    merged=[]
    for a,b in intervals:
        if merged and a<=merged[-1][1]+.05:
            merged[-1][1]=max(b,merged[-1][1])
        else:
            merged.append([a,b])
    return {'source_ranges':merged,'source_seconds':round(sum(b-a for a,b in merged),2),
            'source_duration':duration,'basis':'Jendela transkrip berhasil diperiksa; bukan seluruh frame video'}


def context(candidate, transcript):
    a,b=candidate['start'],candidate['end']
    words=transcript['words'];duration=transcript['duration']
    before=[w for w in words if a-12<=w['start']<a]
    after=[w for w in words if b<=w['start']<=b+12]
    return {'before':{'start':max(0,a-8),'end':min(duration,a+3),'quote':' '.join(w['word'] for w in before)},
            'after':{'start':max(a,b-3),'end':min(duration,b+8),'quote':' '.join(w['word'] for w in after)},
            'note':'Dengarkan sumber di sekitar batas. Usulan AI hanya diterapkan bila bukti dan rentangnya valid.'}


def semantic_groups(candidates, cfg):
    """One bounded local model pass compares grounded claims, including paraphrases.

    No claim quote -> no semantic removal. Model failures keep candidates.
    """
    from . import editorial
    eligible=[(i,c) for i,c in enumerate(candidates) if c.get('main_claim')]
    if len(eligible)<2:
        return set(),[]
    removed, decisions=set(),[]
    # Compare chapters in bounded batches; lexical source dedup handles the rest.
    for offset in range(0,len(eligible),24):
        chunk=eligible[offset:offset+24]
        payload=[{'id':i,'kind':c.get('story_kind'),'quote':c['main_claim'],'ending':c.get('ending_evidence','')} for i,c in chunk]
        key=hashlib.sha256(json.dumps([payload,cfg.model,'semantic-1'],sort_keys=True).encode()).hexdigest()[:24]
        path=Path(cfg.work_dir)/'semantic-reviews'/(key+'.json')
        data=read_json(path)
        try:
            if data is None:
                props={'keep':{'type':'integer'},'duplicate':{'type':'integer'},'reason':{'type':'string'}}
                schema={'type':'object','properties':{'pairs':{'type':'array','items':{'type':'object','properties':props,'required':list(props)}}},'required':['pairs']}
                r=requests.post(editorial.local_url(cfg)+'/api/generate',json={'model':cfg.model,'stream':False,'think':False,
                    'format':schema,'keep_alive':'5m','system':'Bandingkan gagasan dalam kutipan DATA. Tandai duplikat hanya jika kesimpulan, syarat, angka dan negasi SAMA walau parafrasa. Contoh baru, jawaban berbeda, demonstrasi dan kontra-argumen bukan duplikat. Jangan tandai hanya karena topik sama. Pilih id keep/duplicate berbeda dari DATA; utamakan kutipan paling lengkap. JSON pairs kosong bila ragu.',
                    'prompt':json.dumps(payload,ensure_ascii=False),'options':{'temperature':0,'num_ctx':cfg.ollama_num_ctx,'num_gpu':cfg.ollama_num_gpu,'num_predict':1000}},timeout=cfg.ollama_timeout)
                r.raise_for_status();data=json.loads(r.json()['response'])
            if not isinstance(data,dict) or not isinstance(data.get('pairs'),list):
                raise ValueError('Format perbandingan gagasan tidak valid')
            valid={i:c for i,c in chunk}
            checked=[]
            for pair in data['pairs']:
                a,b=pair.get('keep'),pair.get('duplicate')
                if type(a) is not int or type(b) is not int or a==b or a not in valid or b not in valid or a in removed:
                    continue
                ca,cb=valid[a],valid[b]
                # Different story types and quantities are deliberately retained.
                if ca.get('story_kind')!=cb.get('story_kind') or re.findall(r'\d+(?:[.,]\d+)*',ca['main_claim'])!=re.findall(r'\d+(?:[.,]\d+)*',cb['main_claim']):
                    continue
                from .transcript_correction import PROTECTED,norm
                if ({norm(x) for x in ca['main_claim'].split()}&PROTECTED)!=({norm(x) for x in cb['main_claim'].split()}&PROTECTED):
                    continue
                if not isinstance(pair.get('reason'),str) or not pair['reason'].strip():
                    continue
                removed.add(b);checked.append(pair)
                decisions.append({'code':'semantic_duplicate','start':cb['start'],'end':cb['end'],'title':cb['title'],
                    'detail':pair['reason'][:250],'kept_title':ca['title'],'action':'compare','source':'local_semantic_review'})
            write_json(path,{'pairs':checked})
        except (requests.RequestException,ValueError,KeyError,TypeError):
            decisions.append({'code':'semantic_review_unavailable','detail':'Perbandingan makna belum berhasil; kandidat dipertahankan.','action':'review'})
    return removed,decisions


def save_report(report,cfg):
    prior=history(cfg)
    report['round']=len(prior)+1
    report['created_at']=time_now()
    prior.append(report)
    write_json(Path(cfg.work_dir)/'discovery-history.json',prior)
    write_json(Path(cfg.work_dir)/'selection-report.json',report)


def time_now():
    from datetime import datetime,timezone
    return datetime.now(timezone.utc).isoformat()
