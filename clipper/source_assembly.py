"""Explicit multi-source assembly creates a new source and retains original lineage."""
import copy
from pathlib import Path
import subprocess
from .contracts import fingerprint
from .dependency_cache import content_id
from .media_context import prepare,inspect
from .transcript_tracks import number,cues_from_words
from .project_store import Conflict


def instance_word_id(index, original):
    return 'instance-'+str(index)+':'+fingerprint(original)[:24]


def mapped_word(word,index,row,cursor,duration):
    """Map both outer and nested manual/measured times into the new source."""
    value=copy.deepcopy(word);aligned=value.get('aligned_words');left=row['start'];right=min(row['end'],left+duration)
    if aligned:
        from .stage3 import validate_alignment
        aligned=validate_alignment(value['word'],aligned,aligned[0]['start'],aligned[-1]['end'],method=value.get('alignment_method','manual'))
        selected=[{**part,'start':max(left,part['start']),'end':min(right,part['end'])} for part in aligned if part['end']>left and part['start']<right]
        if not selected:return None
        a=min(p['start'] for p in selected);b=max(p['end'] for p in selected)
        partial=len(selected)!=len(aligned) or any(p['start']<left or p['end']>right for p in aligned)
        value['origin_aligned_words']=copy.deepcopy(aligned)
        value['origin_text']=value['word'];value['word']=' '.join(p['word'] for p in selected)
        value['aligned_words']=[{**p,'start':cursor+p['start']-left,'end':cursor+p['end']-left} for p in selected]
        value['alignment_provenance']={**value.get('alignment_provenance',{}),'origin_source_id':row['source_id'],
            'source_time_mapping':{'source_start':left,'output_start':cursor}}
    else:
        a=max(word['start'],left);b=min(word['end'],right)
        if b<=a:return None
        partial=a>word['start'] or b<word['end']
    origins=word.get('source_word_ids',[word['word_id']])
    value.update(word_id=instance_word_id(index,word['word_id']),source_word_ids=[instance_word_id(index,i) for i in origins],
        origin_project_id=row['project_id'],origin_source_id=row['source_id'],origin_word_ids=origins,
        origin_source_start=a,origin_source_end=b,origin_original_bounds=[word['start'],word['end']],
        start=cursor+a-left,end=cursor+b-left)
    if partial:value['timing_status']='partial_word_needs_review'
    return value


def validate_segments(service,segments):
    if not isinstance(segments,list) or not 1<=len(segments)<=20:raise ValueError('Pilih 1–20 segmen sumber')
    rows=[];kinds=set()
    for item in segments:
        if not isinstance(item,dict):raise ValueError('Segmen sumber tidak valid')
        doc=service.store.get(item['project_id'])
        if type(item.get('revision')) is not int or item['revision']!=doc['revision']:raise Conflict(doc['revision'],'Revisi sumber gabungan berubah')
        actual=content_id(doc['source']['path'],fresh=True)
        if actual!=doc['source']['source_id']:raise ValueError('Sumber gabungan berubah; tautkan ulang')
        a=number(item['start']);b=number(item['end'])
        if not 0<=a<b<=doc['source']['info']['duration']:raise ValueError('Segmen di luar durasi sumber')
        kinds.add(doc['source']['info'].get('kind','video'));rows.append({'project_id':doc['project_id'],'revision':doc['revision'],'source_id':actual,'start':a,'end':b})
    if len(kinds)!=1:raise ValueError('Gabungkan seluruh sumber video atau seluruh sumber audio; tipe campuran perlu keputusan layout')
    return rows


def assemble(service,request,folder,check=lambda:None):
    rows=validate_segments(service,request['segments']);folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    files=[];lineage=[];words=[];raw=[];cursor=0.;languages=set();kind=None;fps=service.base.output_fps
    for i,row in enumerate(rows):
        check();doc=service.store.get(row['project_id']);cfg=service.config(doc);context=prepare(doc['source']['path'],cfg);p=context['payload'];kind=p['kind']
        # Every segment is rounded once onto the same output clock.
        count=max(1,round((row['end']-row['start'])*fps));duration=count/fps
        target=folder/(f'chunk-{i}.wav' if kind=='audio' else f'chunk-{i}.nut')
        command=['ffmpeg','-v','error','-nostdin','-y','-ss',str(row['start']),'-i',p['working_path'],'-t',str(duration)]
        if kind=='audio':command+=['-vn','-af',f'apad,atrim=duration={duration:.9f}','-ac','2','-ar','48000','-c:a','pcm_s16le',str(target)]
        else:command+=['-vf',f'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},setpts=PTS-STARTPTS',
            '-af',f'asetpts=PTS-STARTPTS,apad,atrim=duration={duration:.9f}','-ac','2','-ar','48000','-c:v','libx264','-preset','fast','-crf','18','-threads','4',
            '-c:a','pcm_s16le',str(target)]
        subprocess.run(command,check=True,capture_output=True,timeout=1800);files.append(target)
        lineage.append({**row,'source_path':doc['source']['path'],'output_start':cursor,'output_end':cursor+duration,'instance_id':f'source-{i}',
            'source_end_used':min(row['end'],row['start']+duration),'timebase':'source_seconds','source_layer':'baked'})
        if doc.get('transcript_id'):
            take=service.transcript(doc);languages.add(take.get('language','und'))
            selected=[]
            for word in take['words']:
                mapped=mapped_word(word,i,row,cursor,duration)
                if mapped:selected.append(mapped)
            words.extend(selected)
            needed={origin for word in selected for origin in word['origin_word_ids']}
            for word in take.get('raw_words',take['words']):
                if word['word_id'] not in needed:continue
                mapped=mapped_word(word,i,row,cursor,duration)
                if mapped is None:
                    # A reviewed alignment may move beyond the original ASR span.
                    # Keep the heard text/ID and original bounds as evidence, while
                    # explicitly relocating its derived view to the manual span.
                    linked=[w for w in selected if word['word_id'] in w['origin_word_ids']]
                    mapped=mapped_word({**word,'start':row['start'],'end':row['start']+duration,
                        'aligned_words':None},i,row,cursor,duration)
                    mapped.update(start=min(w['start'] for w in linked),end=max(w['end'] for w in linked),
                        origin_original_bounds=[word['start'],word['end']],source_time_basis='reviewed_span_for_original_heard_lineage',
                        timing_status='partial_word_needs_review')
                raw.append(mapped)
        cursor+=duration
    check();validate_segments(service,rows)
    listing=folder/'concat.txt';listing.write_text(''.join("file '"+str(p.resolve()).replace("'","'\\''")+"'\n" for p in files))
    target=folder/('assembled.wav' if kind=='audio' else 'assembled.mp4');pending=folder/('assembled.partial.wav' if kind=='audio' else 'assembled.partial.mp4')
    command=['ffmpeg','-v','error','-nostdin','-y','-f','concat','-safe','0','-i',str(listing),'-t',str(cursor)]
    command+=['-c:a','pcm_s16le'] if kind=='audio' else ['-c:v','copy','-c:a','aac','-movflags','+faststart']
    subprocess.run(command+[str(pending)],capture_output=True,check=True,timeout=1800);info=inspect(pending)
    if abs(info['duration']-cursor)>max(.1,2/fps):raise ValueError('Durasi gabungan tidak sesuai lineage')
    check();validate_segments(service,rows);pending.replace(target);sid=content_id(target,fresh=True)
    result={'path':str(target),'info':info,'content_id':sid,'lineage':lineage,'receipt':{'provider':'multi_source_assembly','source_content_id':sid,
        'source_count':len(rows),'lineage_digest':fingerprint(lineage),'complete_media_probed':True}}
    if words:
        words.sort(key=lambda w:w['start']);raw.sort(key=lambda w:w['start'])
        result['transcript']={'words':words,'raw_words':raw or copy.deepcopy(words),'cues':cues_from_words(words),'duration':info['duration'],
            'language':next(iter(languages)) if len(languages)==1 else 'mul','source_id':sid,'timebase':'source_seconds','source_lineage':lineage,
            'runtime_receipt':{'provider':'derived_source_tracks','inference_performed':False,'actual_model':None,'actual_device':None}}
    return result
