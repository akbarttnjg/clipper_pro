"""Cached, optional local alignment on uncertain words in the selected clip.

No full-source inference, no transcript rewriting, no changes to manual timing.
The measured render copy is separate from the stored transcript.
"""
import copy
from pathlib import Path
from .contracts import fingerprint
from .storage import read_json,write_json

VERSION='selected-alignment-4.0.10'


def eligible(word):
    if word.get('aligned_words') or word.get('alignment_method')=='manual' or word.get('timing_status') in ('manual','aligned'):
        return False
    return bool(word.get('correction') or word.get('manually_edited') or len(word['word'].split())>1 or
                (isinstance(word.get('probability'),(int,float)) and word['probability']<.70))


def apply_patches(words,patches,clip):
    from .stage3 import validate_alignment,alignment_window
    from .transcript_correction import source_ids
    output=copy.deepcopy(words);applied=0
    for word in output:
        if not eligible(word) or word['start']<clip['start'] or word['end']>clip['end']:continue
        for patch in patches:
            if patch.get('origin_word_ids')!=source_ids([word]) or patch.get('text')!=word['word']:continue
            a,b=alignment_window(word,words,max(clip['end'],words[-1]['end']))
            a=max(a,clip['start']);b=min(b,clip['end'])
            try:aligned=validate_alignment(word['word'],patch['words'],a,b,method='whisperx')
            except (ValueError,KeyError,TypeError):continue
            # Keep one-to-one lineage. Multiword units remain measured spans
            # and are expanded only by the existing transcript adapter.
            word.update(start=aligned[0]['start'],end=aligned[-1]['end'],
                        alignment_method='whisperx',timing_status='aligned',
                        alignment_provenance=patch.get('provenance',{}))
            if len(aligned)>1:word['aligned_words']=aligned
            applied+=1;break
    return output,applied


def prepare(source,words,clip,cfg):
    from . import speech_jobs
    from .transcript_correction import source_ids
    from .dependency_cache import content_id
    report={'version':VERSION,'status':'disabled','scope':'selected_clip_uncertain_words','applied':0,'transcript_saved':False}
    if not cfg.align_selected_clips:return words,report
    selected=[w for w in words if clip['start']<=w['start']<w['end']<=clip['end'] and eligible(w)]
    if not selected:report['status']='no_candidates';return words,report
    selected=selected[:24];ids=source_ids(selected)
    if len(ids)>80:ids=ids[:80]
    report.update(attempted=len(selected),selected_ids=ids)
    try:runtime=speech_jobs.alignment_runtime(cfg,{})
    except (ValueError,OSError,TypeError) as exc:
        report.update(status='unavailable',reason=str(exc));return words,report
    model=Path(runtime['model_path'])
    signature=[(p.name,content_id(p)) for p in sorted(model.iterdir()) if p.is_file()]
    key=fingerprint([VERSION,content_id(source),words,clip['start'],clip['end'],ids,runtime,signature,cfg.language])
    path=Path(cfg.audio_cache_dir or cfg.work_dir)/'selected-alignment'/(key+'.json')
    response=read_json(path);reused=response is not None
    try:
        if response is None:
            transcript={'words':words,'duration':max(clip['end'],max(w['end'] for w in words)),'language':cfg.language}
            response=speech_jobs.run('alignment',source,transcript,cfg,{'limit':24,'origin_word_ids':ids,'model_path':runtime['model_path']})
            # Failed jobs may be retried after a component or language repair.
            if response.get('patches'):write_json(path,response)
        output,applied=apply_patches(words,response.get('patches',[]),clip)
        report.update(status='aligned' if applied else 'not_applied',applied=applied,cache_reused=reused,
                      evidence=response.get('report',{}),runtime_generation=runtime.get('generation'))
        return output,report
    except (ValueError,OSError,TypeError,KeyError) as exc:
        report.update(status='failed',reason=str(exc)[-600:]);return words,report
