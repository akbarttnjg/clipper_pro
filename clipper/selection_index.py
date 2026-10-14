"""Revisioned local M3 indexes; prompt changes never invoke ASR or replace an index."""
import json
import math
from pathlib import Path
import sqlite3
import time
from .contracts import fingerprint
from .selection_contract import VERSION,terms

PREPROCESSING = 'm3-sentences-3-stride-2-1800char-passages-v2'


def model_runtime(cfg):
    from .visual4 import component_runtime
    from .dependency_cache import model_identity
    runtime=component_runtime('e5',cfg)
    if runtime is None:return None
    files=model_identity(Path(runtime['directory'])/'weights',fresh=True)
    if not files or any(name=='missing' for name,_ in files):raise ValueError('Bobot E5 lokal tidak tersedia; status instalasi saja tidak membuktikan model')
    return {**runtime,'weights_digest':fingerprint(files)}


def documents(rows):
    result=[]
    for i in range(0,len(rows),2):
        group=rows[i:i+3];text=' '.join(r['text'] for r in group)
        # Imported cues keep their original time and text; do not invent word
        # timings merely to split a very long cue into embedding tokens.
        start=0;pieces=[]
        while start<len(text):
            end=min(len(text),start+1800)
            if end<len(text):
                boundary=text.rfind(' ',start,end)
                if boundary>start:end=boundary+1
            pieces.append((start,end,text[start:end]));start=end
        for part,(a,b,portion) in enumerate(pieces):
            result.append({'id':'passage-'+fingerprint([[r['sentence_id'] for r in group],part,a,b])[:24],
                'sentence_ids':[r['id'] for r in group],'start':min(r['start'] for r in group),
                'end':max(r['end'] for r in group),'text':portion,'terms':sorted(terms(portion)),
                'embedding_text':portion,'embedding_truncated':False,'source_text_offsets':[a,b],
                'timing_resolution':'whole_source_units; subtext_does_not_create_word_timestamps'})
    return result


def validate_vectors(items, result, expected_runtime):
    if result.get('status')!='ready':raise ValueError(result.get('note','Embedding lokal belum siap'))
    provenance=result.get('provenance',{})
    if any(provenance.get(k)!=expected_runtime.get(k) for k in ('generation','model_commit','source_commit')):
        raise ValueError('Generation embedding berubah selama indexing; hasil lama tetap tersedia')
    vectors=result.get('vectors')
    if not isinstance(vectors,list) or len(vectors)!=len(items):raise ValueError('Jumlah embedding tidak sesuai passage')
    dim=None;normalized=[]
    for row,item in zip(vectors,items):
        if not isinstance(row,dict) or row.get('id')!=item['id'] or not isinstance(row.get('values'),list):raise ValueError('ID embedding tidak cocok')
        values=row['values']
        if not 1<=len(values)<=2048 or dim is not None and len(values)!=dim:raise ValueError('Dimensi embedding tidak valid')
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):raise ValueError('Embedding memiliki nilai tidak terukur')
        norm=math.sqrt(sum(v*v for v in values))
        if not .98<=norm<=1.02:raise ValueError('Embedding harus normalisasi unit; nilai nol ditolak')
        dim=len(values);normalized.append([float(v)/norm for v in values])
    return normalized


class SelectionIndex:
    def __init__(self, work):
        self.work=Path(work);self.work.mkdir(parents=True,exist_ok=True);self.database=self.work/'m3-index.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS m3_indexes(id TEXT PRIMARY KEY,document TEXT NOT NULL,sha256 TEXT NOT NULL,created REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS m3_queries(id TEXT PRIMARY KEY,index_id TEXT NOT NULL,document TEXT NOT NULL,created REAL NOT NULL,sha256 TEXT)')
            if 'sha256' not in {r[1] for r in db.execute('PRAGMA table_info(m3_queries)')}:db.execute('ALTER TABLE m3_queries ADD COLUMN sha256 TEXT')
    def connect(self):return sqlite3.connect(self.database,timeout=30)

    def _embedding(self,items,cfg,runtime,mode):
        from .visual4 import backend
        result=backend('e5',{'operation':'m3_embeddings','items':items,'prefix':mode,
            'preprocessing':PREPROCESSING,'weights_digest':runtime['weights_digest']},cfg,self.work/'m3-e5')
        values=validate_vectors(items,result,runtime)
        current=model_runtime(cfg)
        if current is None or current['weights_digest']!=runtime['weights_digest']:raise ValueError('Bobot E5 berubah ketika proses berjalan')
        return values

    def build(self, rows, *, source_id,take,scope,cfg,policy='auto',progress=lambda p,m:None):
        runtime=None
        if policy!='lexical':
            runtime=model_runtime(cfg)
        if policy=='e5' and runtime is None:raise ValueError('E5 lokal belum lolos uji sampel; pilih pencarian teks atau siapkan komponen E5')
        provider='e5' if runtime else 'lexical';parts=documents(rows)
        key=fingerprint([VERSION,PREPROCESSING,source_id,take,scope,provider,runtime,
            [[s['sentence_id'],s['start'],s['end'],s['text'],s['speakers']] for s in rows]])
        with self.connect() as db:cached=db.execute('SELECT document,sha256 FROM m3_indexes WHERE id=?',(key,)).fetchone()
        if cached:
            data=json.loads(cached[0])
            if fingerprint(data)!=cached[1]:raise ValueError('Index M3 tersimpan rusak; generasi lama tidak ditimpa')
            return {**data,'cache_reused':True}
        vectors=[]
        if runtime:
            for i in range(0,len(parts),64):
                progress(8+int(12*i/max(1,len(parts))),'Membangun index E5 dari transkrip tersimpan')
                items=[{'id':r['id'],'text':r['embedding_text']} for r in parts[i:i+64]]
                vectors.extend(self._embedding(items,cfg,runtime,'passage'))
            if len({len(v) for v in vectors})>1:raise ValueError('Dimensi model E5 berubah antar batch')
        data={'index_id':key,'version':VERSION,'source_id':source_id,'transcript_take':take,'scope':scope,
            'provider':provider,'preprocessing':PREPROCESSING,'runtime':runtime,'documents':parts,'vectors':vectors,
            'embedding_performed':bool(vectors),'source_passages':len(parts),
            'model_generation':runtime.get('generation') if runtime else None,
            'model_digest':runtime.get('weights_digest') if runtime else None,
            'semantic_quality':'not_measured','asr_invoked':False,'cache_reused':False}
        encoded=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        with self.connect() as db:db.execute('INSERT OR IGNORE INTO m3_indexes VALUES(?,?,?,?)',(key,encoded,fingerprint(data),time.time()))
        return data

    def query(self,index,text,cfg):
        key=fingerprint([VERSION,index['index_id'],text])
        with self.connect() as db:cached=db.execute('SELECT document,sha256 FROM m3_queries WHERE id=?',(key,)).fetchone()
        if cached:
            result=json.loads(cached[0])
            if fingerprint(result)!=cached[1]:raise ValueError('Cache query M3 rusak; hasil lama tidak ditimpa')
            return {**result,'cache_reused':True}
        scores={};query_terms=terms(text);vector=None
        if text and index['provider']=='e5':
            vector=self._embedding([{'id':'query','text':text}],cfg,index['runtime'],'query')[0]
            if index['vectors'] and len(vector)!=len(index['vectors'][0]):raise ValueError('Embedding query dan index berbeda dimensi')
        for i,row in enumerate(index['documents']):
            overlap=len(query_terms&set(row['terms']))/max(1,len(query_terms))
            scores[row['id']]=sum(a*b for a,b in zip(vector,index['vectors'][i])) if vector is not None else overlap if text else 1.
        result={'query_id':key,'index_id':index['index_id'],'query':text,'provider':index['provider'],
            'scores':scores,'cache_reused':False,'asr_invoked':False,'score_kind':'cosine_similarity' if vector is not None else 'literal_term_coverage',
            'probability_of_correct_topic':None}
        with self.connect() as db:db.execute('INSERT OR IGNORE INTO m3_queries VALUES(?,?,?,?,?)',(key,index['index_id'],json.dumps(result,ensure_ascii=False),time.time(),fingerprint(result)))
        return result


def candidate_relevance(candidate,index,query):
    matched=[row for row in index['documents'] if any(row['start']<s['end'] and row['end']>s['start'] for s in candidate['source_spans'])]
    return max((query['scores'][r['id']] for r in matched),default=0.)


def semantic_pairs(candidates,index,*,budget=96):
    """E5 similarity proposes comparisons; it has no deletion authority."""
    if index['provider']!='e5' or not index['vectors']:
        return {'status':'unavailable','pairs':[],'removed':0,'calibration':'not_measured'}
    samples=candidates if len(candidates)<=budget else [candidates[round(i*(len(candidates)-1)/(budget-1))] for i in range(budget)]
    vectors=[]
    for c in samples:
        indices=[i for i,row in enumerate(index['documents']) if any(row['start']<s['end'] and row['end']>s['start'] for s in c['source_spans'])]
        if not indices:vectors.append(None);continue
        mean=[sum(index['vectors'][i][d] for i in indices)/len(indices) for d in range(len(index['vectors'][0]))]
        norm=math.sqrt(sum(v*v for v in mean));vectors.append([v/norm for v in mean] if norm else None)
    pairs=[]
    for i,a in enumerate(samples):
        if vectors[i] is None:continue
        for j in range(i+1,len(samples)):
            if vectors[j] is None:continue
            score=sum(x*y for x,y in zip(vectors[i],vectors[j]))
            overlap=sum(max(0,min(x['end'],y['end'])-max(x['start'],y['start'])) for x in a['source_spans'] for y in samples[j]['source_spans'])
            if score>=.88:pairs.append({'a':a['candidate_id'],'b':samples[j]['candidate_id'],'similarity':min(1.,score),
                'temporal_overlap_seconds':overlap,'action':'human_compare','critical_tokens_equal':a['critical_tokens']==samples[j]['critical_tokens']})
    return {'status':'review_proposals','pairs':sorted(pairs,key=lambda p:p['similarity'],reverse=True)[:64],
        'sampled_candidates':len(samples),'total_candidates':len(candidates),'removed':0,
        'calibration':'not_measured; threshold_only_triggers_review','model_generation':index['model_generation'],
        'embedding_basis':'mean_normalized_source_passage_vectors'}
