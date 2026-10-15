"""Cleanup is a reviewed video+audio edit, never an invisible speech deletion."""
import copy
import re
from .contracts import fingerprint
from .editor_contract import segments_for,seconds,tick

def proposals(service,doc,cid,vid):
    clip=doc['clips'][cid];variant=service.variant(doc,cid,vid)
    rows=[w for w in service.transcript(doc,cid,vid)['words'] if w['end']>clip['start'] and w['start']<clip['end']]
    signature=fingerprint([doc['source']['source_id'],doc['transcript_id'],doc['transcript_revision'],rows,segments_for(clip,variant)])
    retained=segments_for(clip,variant);out=[]
    def add(kind,a,b,ids,reason):
        if b-a<.04:return
        if sum(max(0.,min(b,seconds(s['source_end_tick']))-max(a,seconds(s['source_start_tick']))) for s in retained if s['kind']=='body')<.04:return
        out.append({'id':fingerprint([signature,kind,a,b,ids])[:24],'kind':kind,'start':a,'end':b,'word_ids':ids,'reason':reason,'requires_review':True,'approved':False})
    previous=clip['start']
    for row in rows:
        if row['start']-previous>=.8:add('silence',previous+.12,row['start']-.12,[],'Jeda; dapat bermakna atau berisi suara yang tidak ditranskripsi. Dengarkan dahulu.')
        previous=max(previous,row['end'])
        if re.sub(r'[^\w]','',row['word'].casefold()) in {'eh','eee','ee','hmm','em','uh','um'}:
            add('filler',max(clip['start'],row['start']),min(clip['end'],row['end']),[row['word_id']],'Usulan filler dari transkrip; tidak dipotong otomatis.')
    for i in range(len(rows)-5):
        first=rows[i:i+3];second=rows[i+3:i+6]
        if [r['word'].casefold() for r in first]==[r['word'].casefold() for r in second] and second[0]['start']-first[-1]['end']<1.:
            from .audio6 import re_critical
            if any(re_critical(r['word']) for r in first):continue
            add('retake',first[0]['start'],first[-1]['end'],[r['word_id'] for r in first],'Tiga token berulang; konfirmasi retake, bukan penegasan yang disengaja.')
    return {'signature':signature,'proposals':out[:100],'timebase':'source_seconds','automatic_deletion':False}

def apply(service,doc,cid,vid,op):
    from .editor_service import targets,check_lock,_set_segments
    if op.get('reviewed') is not True:raise ValueError('Dengarkan konteks dan setujui cleanup dahulu')
    selected=targets(service,doc,cid,vid,op,temporal=True);requests=[]
    for c,v in selected:
        p=proposals(service,doc,c,v)
        if op.get('signature')!=p['signature']:raise ValueError('Usulan cleanup sudah berubah; tinjau ulang tiap rasio atau pisahkan versi editorial')
        ids=op.get('proposal_ids')
        if not isinstance(ids,list) or not ids or len(set(ids))!=len(ids):raise ValueError('Pilih ID usulan cleanup yang unik')
        cuts=[r for r in p['proposals'] if r['id'] in ids]
        if len(cuts)!=len(ids):raise ValueError('Usulan cleanup tidak ada pada snapshot aktif')
        check_lock(service,doc,c,v,{'op':'editor_segments'})
        rows=[]
        for segment in segments_for(doc['clips'][c],service.variant(doc,c,v)):
            if segment['kind']=='freeze':rows.append(copy.deepcopy(segment));continue
            remaining=[(segment['source_start_tick'],segment['source_end_tick'])]
            for cut in cuts:
                a,b=tick(cut['start']),tick(cut['end']);next_rows=[]
                for left,right in remaining:
                    if b<=left or a>=right:next_rows.append((left,right));continue
                    if left<a:next_rows.append((left,a))
                    if b<right:next_rows.append((b,right))
                remaining=next_rows
            if segment.get('reverse'):remaining.reverse()
            for j,(left,right) in enumerate(remaining):
                row={**copy.deepcopy(segment),'id':segment['id']+'-clean-'+str(j),'source_start_tick':left,'source_end_tick':right}
                if row.get('speed_curve'):raise ValueError('Cleanup pada speed ramp memerlukan edit batas manual agar kurva tetap terjaga')
                rows.append(row)
        if not rows:raise ValueError('Cleanup akan mengosongkan timeline')
        requests.append((c,v,rows,cuts))
    for c,v,rows,cuts in requests:
        variant=service.variant(doc,c,v);before=copy.deepcopy(variant.get('editor',{}))
        _set_segments(service,doc,c,v,rows)
        variant.setdefault('audio6',{'enabled':False,'settings':{},'tracks':[]}).setdefault('cleanup_history',[]).append({'source_signature':op['signature'],'cuts':cuts,'before_editor':before,'reviewed':True,'source_unchanged':True})
    return {'touched':[(c,v) for c,v,_,_ in requests]}
