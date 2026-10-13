"""Separate translation proposals with literal fact guards and human approval."""
import copy
import json
import re
from .transcript_tracks import language, critical_review


def validate(cues, rows, target_language):
    language(target_language)
    if not isinstance(rows,list) or len(rows)!=len(cues):raise ValueError('Jumlah cue terjemahan berubah')
    result=[];critical=[]
    for source,row in zip(cues,rows):
        if not isinstance(row,dict) or str(row.get('cue_id'))!=str(source['cue_id']):raise ValueError('ID/urutan cue terjemahan berubah')
        if any(k in row and row[k]!=source[k] for k in ('start','end')):raise ValueError('Waktu cue terjemahan harus tetap')
        text=row.get('text')
        if not isinstance(text,str) or not text.strip() or len(text)>2000:raise ValueError('Teks terjemahan tidak valid')
        if re.findall(r'\d+(?:[.,]\d+)*',source['text'])!=re.findall(r'\d+(?:[.,]\d+)*',text):raise ValueError('Angka literal berubah; koreksi terjemahan sebelum review')
        result.append({**copy.deepcopy(source),'text':text.strip()})
        flags=critical_review([{'word_id':source['cue_id'],'word':source['text'],'start':source['start'],'end':source['end'],'probability':1}])
        if flags:critical.append({'cue_id':source['cue_id'],'source':source['text'],'translation':text.strip(),'reasons':flags[0]['reasons']})
    return result,critical


def ollama(cues,target_language,cfg):
    import requests
    rows=[]
    for i in range(0,len(cues),30):
        batch=cues[i:i+30]
        prompt=('Translate every cue to '+language(target_language)+'. Preserve cue_id order, names, negation, literal numbers and units. '
            'Do not add explanations. Return JSON {"cues":[{"cue_id":"...","text":"..."}]}.\n'+json.dumps(batch,ensure_ascii=False))
        response=requests.post(cfg.ollama_url.rstrip('/')+'/api/generate',json={'model':cfg.model,'prompt':prompt,'format':'json','stream':False,
            'options':{'num_gpu':cfg.ollama_num_gpu,'num_ctx':cfg.ollama_num_ctx}},timeout=cfg.ollama_timeout)
        response.raise_for_status();data=response.json();rows.extend(json.loads(data['response'])['cues'])
    return rows,{'provider':'ollama','requested_model':cfg.model,'actual_model':data.get('model'),
        'inference_performed':True,'actual_device':None,'device_status':'not_reported_by_provider','quality':'not_measured','human_review_required':True}
