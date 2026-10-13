"""Lossless adapter from the nine historical panel draft stores to commands.

The adapter does not apply data. Its output goes through correction review,
the canonical validators, and the same revision transaction as saved edits.
"""
import json
import re
from collections import defaultdict
from .contracts import fingerprint
from .project_store import Conflict


def request(service, doc, payload):
    stores=payload.get('stores',{})
    if not isinstance(stores,dict) or len(stores)>100:
        raise ValueError('Registry draf tidak valid')
    pid=doc['project_id'];operations=[];groups=defaultdict(dict);revision=doc['revision']
    def base(value):
        if type(value) is not int or value!=revision:
            raise Conflict(revision,'Draf memakai revisi lama. Simpan melalui panel dengan tinjauan konflik, atau buat snapshot baru setelah meninjau kolom.')
    def target(cid,vid):
        service.variant(doc,cid,vid)
        return {'clip_id':cid,'variant_id':vid}
    def add(cid,vid,operation):
        operations.append({**target(cid,vid),**operation})
    def rows(raw):
        value=json.loads(raw) if isinstance(raw,str) else raw
        if not isinstance(value,list) or any(not isinstance(p,list) or len(p)!=2 for p in value):
            raise ValueError('Isi registry draf tidak dapat dibaca; ekspor salinannya dahulu')
        return dict(value)
    for key,raw in stores.items():
        if key in ('clipper4-drafts','clipper-analysis-drafts','clipper-stage3-drafts'):
            pairs=rows(raw)
            for ident,value in pairs.items():
                if not isinstance(ident,str) or not ident.startswith(pid+'|'):
                    continue
                parts=ident.split('|')
                if parts[-1] in ('base','__baseRevision'):
                    base(value);continue
                if key=='clipper-stage3-drafts':
                    cid=None if parts[1]=='source' else parts[1];vid='portrait';field='|'.join(parts[2:])
                else:
                    cid,vid=parts[1:3];field='|'.join(parts[3:])
                groups[(key,cid,vid)][field]=value
        elif key.startswith(('clipper5-style|','clipper4-visual-draft|','clipper4-visual-fields|','clipper-m1-fields|')):
            prefix,p,cid,vid=key.split('|',3)
            if p!=pid:continue
            value=json.loads(raw) if isinstance(raw,str) else raw
            if not isinstance(value,dict):raise ValueError('Objek draf tidak valid')
            base(value.get('revision'))
            if prefix=='clipper5-style':
                values=dict(value.get('values',{}))
                cfg=service.config(doc,cid,vid)
                if values.get('style_preset') not in (None,'legacy',cfg.style_preset):
                    values.update(font_main='dm_sans',font_accent='dm_serif_italic',caption_backdrop=True,
                        motion_intensity='calm' if values['style_preset']=='rapi' else 'balanced')
                if values:add(cid,vid,{'op':'settings','values':values})
            elif prefix=='clipper4-visual-draft':
                variant=service.variant(doc,cid,vid)
                area={'id':'area-'+fingerprint([key,value])[:20],'kind':value.get('kind','crop'),
                    'start':value.get('start'),'end':value.get('end'),'box':value.get('box')}
                name='protected' if area['kind']=='manual' else 'pins'
                add(cid,vid,{'op':'visual_controls','values':{name:[*variant.get('visual_controls',{}).get(name,[]),area]}})
            elif prefix=='clipper4-visual-fields':
                controls=service.variant(doc,cid,vid).get('visual_controls',{})
                settings={};changed={}
                for field,val in value.get('values',{}).items():
                    if field in ('visual_active_speaker','visual_vlm'):settings[field]=val
                    elif field=='speaker_track':changed[field]=val
                    elif field.startswith('ocr:'):changed.setdefault('ocr_edits',dict(controls.get('ocr_edits',{})))[field[4:]]=val
                    else:raise ValueError('Draf visual perlu disimpan melalui panel: '+field)
                if settings:add(cid,vid,{'op':'settings','values':settings})
                if changed:add(cid,vid,{'op':'visual_controls','values':changed})
            else:
                if value.get('values') and not value.get('operations'):
                    raise ValueError('JSON timeline/keyframe belum valid. Perbaiki sebelum membuat snapshot.')
                for operation in value.get('operations',[]):add(cid,vid,operation)
        elif key.startswith('clipper6-evaluation|'):
            continue
        else:
            raise ValueError('Registry tidak dikenal: '+key)
    for (kind,cid,vid),fields in groups.items():
        clip=doc['clips'].get(cid,{})
        variant=service.variant(doc,cid,vid) if cid else None
        if kind=='clipper4-drafts':
            cfg=vars(service.config(doc,cid,vid));settings={};assets=defaultdict(dict)
            bounds={};spans=None
            for key,value in fields.items():
                if key.startswith('word:'):
                    identity=key[5:]
                    word=next((w for w in service.transcript(doc,cid)['words'] if str(w['word_id'])==identity),None)
                    if not word:raise ValueError('Draf kata tidak ditemukan: '+identity)
                    add(cid,vid,{'op':'correct_word','word_id':word['word_id'],'before':word['word'],'after':value,'scope':'clip',
                        'transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision']})
                elif key in ('bound-start','bound-end'):bounds[key]=float(value)
                elif key=='keep-spans':spans=[[float(n.strip()) for n in re.split(r'\s*-\s*',line.strip())] for line in value.strip().splitlines()]
                elif key=='edit_style':add(cid,vid,{'op':'style','style_id':value})
                elif key.startswith('asset:'):
                    proposal,field=key[6:].rsplit(':',1);assets[proposal][field]=value
                elif key in cfg:
                    original=cfg[key]
                    settings[key]=value if not isinstance(original,(float,int)) or isinstance(original,bool) else float(value)
                else:raise ValueError('Draf kolom belum dapat dipetakan: '+key)
            if settings:add(cid,vid,{'op':'settings','values':settings})
            if bounds:add(cid,vid,{'op':'bounds','start':bounds.get('bound-start',clip['start']),'end':bounds.get('bound-end',clip['end'])})
            if spans is not None:add(cid,vid,{'op':'timeline','keep_spans':spans})
            for proposal,values in assets.items():
                scene=next((s for s in variant.get('recipe',{}).get('scenes',[]) if s['id']==proposal),None)
                if not scene:raise ValueError('Ilustrasi draf tidak tersedia')
                if 'path' in values:add(cid,vid,{'op':'asset_replace','proposal_id':proposal,'path':values.pop('path')})
                if values:add(cid,vid,{'op':'asset_timing','proposal_id':proposal,'start':float(values.get('start',scene['source_start'])),
                    'end':float(values.get('end',scene['source_end'])),'asset_start':float(values.get('offset',scene.get('asset_start',0)))})
        elif kind=='clipper-analysis-drafts':
            snapshot=service.analysis_snapshot({'project_id':pid,'clip_id':cid,'variant_id':vid},document=doc)
            transcript=snapshot['data']['transcript']['payload'];tokens={t['token_id']:t for t in transcript['display_tokens']}
            aliases={};assets=defaultdict(dict)
            for key,value in fields.items():
                if key in tokens:
                    token=tokens[key]
                    add(cid,vid,{'op':'correct_token','token_id':key,'before':token['text'],'after':value,'scope':'clip',
                        'source_id':doc['source']['source_id'],'transcript_id':doc['transcript_id'],
                        'transcript_revision':doc['transcript_revision'],'origin_word_ids':token['origin_word_ids']})
                elif key.startswith('alias:'):aliases[key[6:]]=value
                elif key.startswith('asset:'):
                    identity,field=key[6:].rsplit(':',1);assets[identity][field]=value
                else:raise ValueError('Draf analisis perlu ditinjau pada panel: '+key)
            if aliases:operations.append({'op':'alias_upsert','id':aliases.get('id'),'canonical':aliases.get('canonical',''),
                'alias':aliases.get('alias',''),'topic':aliases.get('topic','*'),'enabled':True})
            for identity,value in assets.items():
                scene=next((s for s in variant.get('recipe',{}).get('scenes',[]) if s['asset']['provider']+':'+s['asset']['id']==identity),None)
                if not scene:raise ValueError('Aset metadata draf tidak ditemukan')
                add(cid,vid,{'op':'asset_metadata','asset_id':identity,'tags':value.get('tags',scene['asset'].get('tags','')),
                    'attribution':value.get('credit',scene['asset'].get('attribution',''))})
        else:
            words=service.transcript(doc,cid)['words'];boundaries={};timings=defaultdict(dict)
            for key,value in fields.items():
                if key.startswith('boundary:'):boundaries[key[9:]]=value;continue
                if key=='model_path':
                    operations.append({'op':'analysis_settings','values':{'alignment_model_path':value}});continue
                if not key.startswith('word:'+doc['transcript_id']+':'):
                    raise ValueError('Draf transkrip memakai identitas lama atau kolom tidak dikenal')
                tail=key[len('word:'+doc['transcript_id']+':'):]
                end=tail.index(']')+1
                ids=json.loads(tail[:end]);word=next((w for w in words if service_origins(w)==ids),None)
                if not word:raise ValueError('Frasa draf tidak ditemukan pada transkrip aktif')
                if not tail[end:]:
                    operations.append({'op':'correct_word','clip_id':cid,'variant_id':vid,'word_id':word['word_id'],'before':word['word'],
                        'after':value,'scope':'clip' if cid else 'shared_utterance','transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision']})
                else:
                    index,field=tail[end+1:].split(':');timings[tuple(ids)][(int(index),field)]=value
            if boundaries:
                if not cid:raise ValueError('Simpan kandidat manual terlebih dahulu sebelum preview sumber penuh')
                add(cid,vid,{'op':'bounds','start':float(boundaries.get('start',clip['start'])),'end':float(boundaries.get('end',clip['end']))})
            for ids,values in timings.items():
                word=next(w for w in words if service_origins(w)==list(ids))
                aligned=[]
                for index,text in enumerate(word['word'].split()):
                    previous=word.get('aligned_words',[])
                    original=previous[index] if index<len(previous) else {}
                    try:aligned.append({'word':text,'start':float(values.get((index,'start'),original.get('start',''))),
                        'end':float(values.get((index,'end'),original.get('end','')))})
                    except ValueError as exc:raise ValueError('Isi seluruh timing frasa sebelum membuat snapshot') from exc
                operations.append({'op':'align_words','clip_id':cid,'variant_id':vid,'scope':'clip' if cid else 'shared_utterance',
                    'transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision'],'origin_word_ids':list(ids),'text':word['word'],'words':aligned})
    if not operations:raise ValueError('Tidak ada draf editor yang dapat dipreview')
    if len(operations)>100:raise ValueError('Lebih dari 100 operasi draft; simpan sebagian dahulu')
    return {'project_id':pid,'expected_revision':revision,'operation_id':payload['operation_id'],'operations':operations}


def service_origins(word):
    return word.get('source_word_ids',word.get('origin_word_ids',[word['word_id']]))
