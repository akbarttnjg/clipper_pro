"""M3 source-grounded candidates. Editorial scores never authorize publication."""
import copy
import math
import re
import unicodedata
from collections import Counter
from .contracts import fingerprint
from .typography import STOP

VERSION = '4.0.15.1-m3'
PROFILES = ('general', 'education', 'finance', 'podcast', 'gaming', 'screen')
CONDITIONS = re.compile(r'\b(?:tetapi|tapi|namun|kecuali|hanya jika|asalkan|risiko|berisiko|bukan berarti|tidak selalu|unless|however|only if|risk)\b', re.I)
CONCLUSION = re.compile(r'\b(?:jadi|kesimpulan|intinya|itulah|maka|oleh karena itu|jawabannya|in conclusion|therefore|in summary)\b', re.I)
ATTACH_CONDITION = re.compile(r'^\s*(?:tetapi|tapi|namun|kecuali|hanya jika|asalkan|risiko|berisiko|bukan berarti|tidak selalu|perlu diingat|unless|however|only if|risk)\b',re.I)
QUESTION = re.compile(r'\b(?:mengapa|kenapa|bagaimana|gimana|apakah|pertanyaan|why|how|what)\b', re.I)
ORDINALS = {1:r'pertama|kesatu|first',2:r'kedua|second',3:r'ketiga|third',4:r'keempat|fourth',5:r'kelima|fifth',6:r'keenam|sixth',7:r'ketujuh|seventh',8:r'kedelapan|eighth',9:r'kesembilan|ninth',10:r'kesepuluh|tenth'}
NUMBERS = {'dua':2,'tiga':3,'empat':4,'lima':5,'enam':6,'tujuh':7,'delapan':8,'sembilan':9,'sepuluh':10,'two':2,'three':3,'four':4,'five':5}
PROMISE = re.compile(r'\b(?:ada|berikut|terdapat|these|here are)\s+(2|3|4|5|6|7|8|9|10|dua|tiga|empat|lima|enam|tujuh|delapan|sembilan|sepuluh|two|three|four|five)\s+(?:cara|langkah|alasan|hal|tips|prinsip|poin|steps|reasons|ways)\b',re.I)


def number(value, name='Waktu'):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError(name+' harus angka yang terukur')
    return float(value)


def tokens(text):
    return re.findall(r'[\w]+(?:[-\u2019\']\w+)*|[%+−-]',unicodedata.normalize('NFKC',str(text)).casefold())


def terms(text):
    return {t for t in tokens(text) if len(t)>1 and t not in STOP}


def contains_phrase(text,phrase):
    haystack=tokens(text);needle=tokens(phrase)
    return bool(needle) and any(haystack[i:i+len(needle)]==needle for i in range(len(haystack)-len(needle)+1))


def critical(text):
    # Preserve signs, decimal/group separators, literal units, and negations.
    return {'numbers':re.findall(r'(?<!\d)[+−-]?\d+(?:[.,]\d+)*(?:\s*(?:%|persen|percent|juta|ribu|miliar|rupiah|dolar|kg|km|cm|detik|menit))?',str(text).casefold()),
            'negations':[t for t in tokens(text) if t in {'tidak','bukan','jangan','belum','tanpa','kecuali','not','never','no','without','unless'}]}


def constraints(data, duration, cfg=None):
    if not isinstance(data,dict):raise ValueError('Permintaan seleksi harus berupa objek')
    duration=number(duration,'Durasi sumber')
    if not 0<duration<=86400:raise ValueError('Durasi sumber harus 0–24 jam')
    defaults={'count':getattr(cfg,'num_clips',2),'min_seconds':getattr(cfg,'min_clip_s',20.),
        'max_seconds':getattr(cfg,'max_clip_s',120.),'grace_seconds':getattr(cfg,'topic_grace_s',20.),
        'start':0.,'end':duration,'query':'','topics':[],'keywords':[],'speakers':[],
        'profile':'general','provider':'ollama','retrieval':'auto','scope':'display',
        'candidate_budget':500,'chunk_seconds':240.,'overlap_seconds':130.,
        'padding_before':.15,'padding_after':.25,'game_name':'','hud_terms':[],
        'signals':True,'frame_budget':24,'visual_model':'off',
        'voice_markers':['clip that','klip itu','potong bagian ini'],'marker_before':30.,'marker_after':5.}
    unknown=set(data)-set(defaults)
    if unknown:raise ValueError('Pengaturan seleksi tidak dikenal: '+', '.join(sorted(unknown)))
    result={**defaults,**copy.deepcopy(data)}
    for key in ('start','end','min_seconds','max_seconds','grace_seconds','chunk_seconds','overlap_seconds','padding_before','padding_after','marker_before','marker_after'):
        result[key]=number(result[key],key)
    if not 0<=result['start']<result['end']<=duration:raise ValueError('Rentang pencarian harus berada di dalam sumber')
    if not 1<=result['min_seconds']<=result['max_seconds']<=600 or not 0<=result['grace_seconds']<=60:raise ValueError('Durasi klip atau perluasan tidak valid')
    if not 30<=result['chunk_seconds']<=900 or not 0<result['overlap_seconds']<result['chunk_seconds']:raise ValueError('Jendela harus memiliki overlap yang lebih pendek')
    if any(not 0<=result[k]<=2 for k in ('padding_before','padding_after')):raise ValueError('Padding dibatasi 0–2 detik')
    if not 0<=result['marker_before']<=600 or not 0<=result['marker_after']<=120:raise ValueError('Rentang penanda suara di luar batas')
    for key,lo,hi in [('count',0,100),('candidate_budget',10,1000),('frame_budget',0,48)]:
        if type(result[key]) is not int or not lo<=result[key]<=hi:raise ValueError(key+' harus bilangan bulat dalam batas')
    if type(result['signals']) is not bool:raise ValueError('Sinyal harus boolean')
    for key,choices in [('profile',PROFILES),('provider',('rules','ollama')),('retrieval',('auto','lexical','e5')),('scope',('display','raw')),('visual_model',('off','smolvlm','qwen3-vl'))]:
        if result[key] not in choices:raise ValueError(key+' tidak dikenal')
    for key,limit in [('query',2000),('game_name',120)]:
        if not isinstance(result[key],str) or len(result[key])>limit:raise ValueError(key+' terlalu panjang atau bukan teks')
        result[key]=result[key].strip()
    for key in ('topics','keywords','speakers','hud_terms','voice_markers'):
        rows=result[key]
        if not isinstance(rows,list) or len(rows)>32 or any(not isinstance(s,str) or not 1<=len(s.strip())<=160 for s in rows):raise ValueError(key+' harus berupa daftar teks terbatas')
        result[key]=list(dict.fromkeys(s.strip() for s in rows))
    result['duration']=duration
    return result


def sentences(words, duration):
    if not isinstance(words,list) or len(words)>300000:raise ValueError('Transkrip tidak valid atau melebihi anggaran 300 ribu unit')
    from .transcript_tracks import effective_units
    words=effective_units(words,duration)
    normalized=[];seen=set()
    for i,w in enumerate(words):
        if not isinstance(w,dict) or not isinstance(w.get('word'),str) or not w['word'].strip():raise ValueError('Unit transkrip harus memiliki teks')
        a,b=number(w.get('start')),number(w.get('end'))
        if not 0<=a<b<=duration+.05:raise ValueError('Timing unit transkrip berada di luar sumber')
        wid=w.get('word_id',i)
        if type(wid) not in (int,str):raise ValueError('ID kata harus string atau integer')
        key=fingerprint(wid)
        if key in seen:raise ValueError('ID kata transkrip ganda')
        seen.add(key);normalized.append({**copy.deepcopy(w),'word_id':wid,'start':a,'end':b})
    normalized.sort(key=lambda w:(w['start'],w['end'],str(w['word_id'])))
    result=[];current=[]
    for i,w in enumerate(normalized):
        current.append(w);following=normalized[i+1] if i+1<len(normalized) else None
        natural=bool(re.search(r'[.!?]["\u201d\u2019]*$',w['word'].strip()))
        pause=following is None or following['start']-w['end']>=.8
        speaker_change=following is not None and following.get('speaker_id')!=w.get('speaker_id')
        if natural or pause or speaker_change or len(current)>=48:
            ids=[x['word_id'] for x in current];text=' '.join(x['word'].strip() for x in current)
            result.append({'id':len(result),'sentence_id':'sentence-'+fingerprint([ids,text])[:24],
                'start':min(x['start'] for x in current),'end':max(x['end'] for x in current),
                'text':text,'word_ids':ids,'natural_end':natural or pause,'speakers':sorted({x['speaker_id'] for x in current if x.get('speaker_id')})})
            current=[]
    return result,normalized


def chunks(rows, requested):
    """Time overlap covers a complete requested story, even with a small window."""
    eligible=[s for s in rows if s['start']>=requested['start'] and s['end']<=requested['end']]
    if not eligible:return []
    story_size=requested['max_seconds']+requested['grace_seconds']+4
    overlap=max(requested['overlap_seconds'],story_size)
    width=max(requested['chunk_seconds'],overlap+max(30.,story_size/2))
    result=[];i=0
    while i<len(eligible):
        a=eligible[i]['start'];j=i
        while j+1<len(eligible) and eligible[j+1]['end']-a<=width:j+=1
        block=eligible[i:j+1]
        result.append({'id':len(result),'start':block[0]['start'],'end':block[-1]['end'],'sentence_ids':[s['id'] for s in block],
            'effective_window_seconds':width,'effective_overlap_seconds':overlap})
        if j==len(eligible)-1:break
        next_time=eligible[j]['end']-overlap
        following=next((k for k in range(i+1,j+1) if eligible[k]['start']>=next_time),j)
        i=max(i+1,following)
    return result


def quote_evidence(row, role, source_id):
    return {'role':role,'sentence_id':row['sentence_id'],'source_id':source_id,'start':row['start'],'end':row['end'],
            'quote':row['text'],'word_ids':row['word_ids']}


def previous_list_start(rows,start_id):
    text=rows[start_id]['text']
    if not any(re.match(r'^\s*(?:yang\s+)?(?:'+pattern+r')\b',text,re.I) for pattern in ORDINALS.values()):return None
    for i in range(start_id-1,-1,-1):
        if rows[start_id]['start']-rows[i]['end']>300:break
        if CONCLUSION.search(rows[i]['text']):break
        if PROMISE.search(rows[i]['text']):return i
    return None


def spans(rows, requested, source_id, words):
    if not isinstance(rows,list) or not 1<=len(rows)<=32:raise ValueError('Cerita memerlukan 1–32 segmen sumber')
    result=[]
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Segmen sumber harus objek')
        if row.get('source_id',source_id)!=source_id:raise ValueError('Segmen memakai sumber berbeda; gunakan gabungan M2 dahulu')
        a,b=number(row.get('start')),number(row.get('end'))
        if row.get('kind','body')!='body':raise ValueError('M3 memakai segmen ucapan sumber; efek temporal diatur melalui editor')
        if not requested['start']<=a<b<=requested['end']:raise ValueError('Segmen berada di luar rentang pencarian')
        selected=[w for w in words if w['start']<b and w['end']>a]
        if any(w['start']<a-1e-6 or w['end']>b+1e-6 for w in selected):raise ValueError('Segmen memotong unit kata/cue; perluas ke batas ucapan')
        if any(max(a,r['start'])<min(b,r['end']) for r in result):raise ValueError('Segmen cerita bertumpang tindih atau berulang')
        result.append({'source_id':source_id,'start':a,'end':b,'word_ids':[w['word_id'] for w in selected],
            'kind':row.get('kind','body')})
    return result


def inspect_story(source_spans, rows, words, requested, source_id):
    selected=[s for span in source_spans for s in rows if s['start']>=span['start'] and s['end']<=span['end']]
    text=' '.join(s['text'] for s in selected);hard=[];review=[]
    duration=sum(r['end']-r['start'] for r in source_spans)
    if duration<requested['min_seconds']-1e-6:hard.append('duration_too_short')
    if duration>requested['max_seconds']+requested['grace_seconds']+1e-6:hard.append('duration_too_long')
    elif duration>requested['max_seconds']+1e-6:review.append('duration_extension')
    if not selected:review.append('non_dialogue_story')
    if any(any(s['start']<span['end'] and s['end']>span['start'] and not span['start']<=s['start']<s['end']<=span['end'] for s in rows) for span in source_spans):hard.append('partial_sentence')
    if selected:
        if not selected[-1]['natural_end']:hard.append('unfinished_utterance')
        if re.search(r'\b(?:dari|untuk|dengan|adalah|yaitu|karena|kalau|yang|dan|atau|bahwa|sehingga|ketika|from|because|and|with)\s*[,.]*$',selected[-1]['text'],re.I):hard.append('unfinished_ending')
        if selected[-1]['text'].rstrip().endswith('?'):hard.append('unanswered_ending')
        if re.match(r'^(?:biar|supaya|karena|ketika|yang|namun|tetapi|tapi|however|because)\b',selected[0]['text'],re.I):review.append('opening_context')
        for match in PROMISE.finditer(text):
            value=match.group(1).casefold();count=NUMBERS.get(value,int(value) if value.isdigit() else 0)
            found=[n for n in range(1,count+1) if re.search(r'\b(?:'+ORDINALS[n]+r')\b',text,re.I)]
            if found and len(found)<count:hard.append('incomplete_numbered_list')
            elif not found:review.append('list_items_require_review')
        # A nearby connected condition is required evidence, never replaced by
        # a high appeal score or an LLM's `complete:true` assertion.
        selected_ids={s['sentence_id'] for s in selected}
        for span in source_spans:
            block=[s for s in rows if span['start']<=s['start'] and s['end']<=span['end']]
            if not block:continue
            context=previous_list_start(rows,block[0]['id'])
            if context is not None and rows[context]['sentence_id'] not in selected_ids:hard.append('numbered_list_context_missing')
            last=block[-1];next_row=next((s for s in rows if s['start']>=last['end'] and s['sentence_id']!=last['sentence_id']),None)
            if next_row and next_row['sentence_id'] not in selected_ids and next_row['start']-last['end']<=6:
                if ATTACH_CONDITION.search(next_row['text']):hard.append('following_caveat_missing')
                elif CONCLUSION.search(next_row['text']):hard.append('following_conclusion_missing')
        if requested['profile']=='finance' and re.search(r'\b(?:untung|return|profit|keuntungan|imbal hasil)\b',text,re.I) and not CONDITIONS.search(text):review.append('financial_assumptions_and_risk')
    if any(r['start']<l['start'] for l,r in zip(source_spans,source_spans[1:])):review.append('source_order_changed')
    covered=[w for span in source_spans for w in words if span['start']<=w['start'] and w['end']<=span['end']]
    probabilities=[w.get('probability') for w in covered]
    measured=[p for p in probabilities if type(p) in (int,float) and math.isfinite(p) and 0<=p<=1]
    unknown=len(probabilities)-len(measured)
    if any(p<.35 for p in measured):review.append('weak_source_confidence')
    caveats=[quote_evidence(s,'caveat',source_id) for s in selected if CONDITIONS.search(s['text'])]
    claims=[quote_evidence(s,'claim',source_id) for s in selected[:1]]
    conclusions=[quote_evidence(s,'conclusion',source_id) for s in selected[-1:]]
    return {'duration':round(duration,6),'hard_blockers':list(dict.fromkeys(hard)),
        'review_flags':list(dict.fromkeys(review)),'text':text,'claims':claims,'caveats':caveats,'conclusion':conclusions,
        'critical_tokens':critical(text),'confidence':{'status':'unknown' if unknown else 'measured' if measured else 'not_applicable',
            'mean':sum(measured)/len(measured) if measured else None,'measured_units':len(measured),'unknown_units':unknown,
            'meaning_accuracy':'not_measured'},'semantic_completeness':'requires_human_review'}


def candidate(source_spans, rows, words, requested, source_id, *, title='', provider='rules', evidence=None):
    source_spans=spans(source_spans,requested,source_id,words)
    audit=inspect_story(source_spans,rows,words,requested,source_id)
    selected=[s for span in source_spans for s in rows if s['start']>=span['start'] and s['end']<=span['end']]
    identity=fingerprint([VERSION,source_id,requested['scope'],source_spans,[s['text'] for s in selected]])
    return {'candidate_id':'cand-'+identity[:32],'content_fingerprint':identity,'source_id':source_id,
        'source_spans':source_spans,'start':min(s['start'] for s in source_spans),'end':max(s['end'] for s in source_spans),
        'duration':audit['duration'],'title':str(title or (selected[0]['text'] if selected else 'Momen sumber'))[:160],
        'requested_constraints':copy.deepcopy(requested),'claims':audit['claims'],'caveats':audit['caveats'],'conclusion':audit['conclusion'],
        'completeness':{k:v for k,v in audit.items() if k not in ('text','claims','caveats','conclusion')},
        'confidence':audit['confidence'],'text':audit['text'],'selection_status':'needs_review' if audit['hard_blockers'] or audit['review_flags'] else 'proposed',
        'scores':{},'reason':'Rentang sumber dan penutup tersedia untuk ditinjau; skor tidak menjamin views.',
        'provider':provider,'evidence':copy.deepcopy(evidence or []),'alternatives':[],'dedupe_group':None,'recommended':False,
        'critical_tokens':audit['critical_tokens'],'created_from':'M3'}


def equivalent(a,b):
    """Conservative equivalence; overlap or embeddings alone never delete a story."""
    if a['candidate_id']==b['candidate_id']:return True
    if not a.get('text') or not b.get('text'):return False
    return tokens(a['text'])==tokens(b['text']) and a.get('critical_tokens')==b.get('critical_tokens')


def rank_set(candidates, requested):
    eligible=[c for c in candidates if not c['completeness']['hard_blockers']]
    def quality(c):
        def measured(name):
            value=c['scores'].get(name,{}).get('value')
            return value if type(value) in (int,float) and math.isfinite(value) else -math.inf
        return (not c['completeness']['review_flags'],measured('relevance'),measured('appeal'),-c['start'])
    ordered=sorted(eligible,key=quality,reverse=True);groups=[]
    for c in ordered:
        prior=next((group[0] for group in groups if equivalent(c,group[0])),None)
        if prior:
            group=next(g for g in groups if g[0] is prior);group.append(c)
            gid=prior['dedupe_group'] or 'dedupe-'+fingerprint([prior['candidate_id']])[:20]
            for item in group:item['dedupe_group']=gid
            prior['alternatives'].append(c['candidate_id']);c['not_selected_reason']='duplicate_source_meaning'
        else:groups.append([c])
    representatives=[g[0] for g in groups];chosen=[];covered=set();diversity=set();limit=requested['count'] or len(representatives)
    pending=list(representatives)
    while pending and len(chosen)<limit:
        # Requested-topic diversity precedes repeating the highest ranked topic.
        best=max(pending,key=lambda c:(len(set(c.get('coverage_labels',c.get('matched_topics',[])))-diversity),quality(c)))
        pending.remove(best);chosen.append(best);covered.update(best.get('matched_topics',[]));diversity.update(best.get('coverage_labels',c.get('matched_topics',[])));best['recommended']=True
    for c in pending:c['not_selected_reason']='target_count_reached'
    for c in candidates:
        if c['completeness']['hard_blockers']:c['not_selected_reason']='hard_constraint'
    return {'recommended_ids':[c['candidate_id'] for c in chosen],
        'requested_count':requested['count'],'available_distinct_complete':len(representatives),
        'shortfall':max(0,requested['count']-len(chosen)),
        'topics_covered':sorted(covered),'topics_missing':[t for t in requested['topics'] if t not in covered],
        'diversity_labels':sorted(diversity),'coverage_method':'requested_literal_topics_or_source_time_buckets; semantic_coverage_requires_review',
        'reason':'Jumlah tidak dipaksakan; kandidat tetap perlu keputusan manusia.',
        'semantic_duplicate_policy':'exact_source_text_and_critical_tokens; embedding pairs are review proposals'}
