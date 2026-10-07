"""A-owned settings/dependencies; B registers these in the shared configuration.

AnalysisConfig is a test/legacy adapter, not a replacement for B's project model.
"""
from dataclasses import dataclass,fields
import re
from .config import Config

@dataclass
class AnalysisConfig(Config):
    ocr_enabled:bool=True
    ocr_max_frames:int=48
    ocr_interval_s:float=8.
    discovery_extra_windows:int=8
    visual_cues:bool=True
    broll_query_limit:int=3
    broll_visual_candidates:int=2
    vision_model:str=''
    vision_policy:str='optional'
    approved_aliases:list|None=None


SETTINGS={
    'ocr_enabled':dict(type='boolean',default=True,stages=['source_evidence','composition']),
    'ocr_max_frames':dict(type='integer',default=48,min=1,max=180,stages=['source_evidence','composition']),
    'ocr_interval_s':dict(type='number',default=8.,min=1,max=60,stages=['source_evidence']),
    'discovery_extra_windows':dict(type='integer',default=8,min=1,max=24,stages=['discovery']),
    'visual_cues':dict(type='boolean',default=True,stages=['source_evidence','discovery']),
    'broll_query_limit':dict(type='integer',default=3,min=1,max=5,stages=['asset_proposals']),
    'broll_visual_candidates':dict(type='integer',default=2,min=1,max=3,stages=['asset_visual_review','asset_proposals']),
    'vision_model':dict(type='string',default='',max_length=100,stages=['asset_visual_review','asset_proposals']),
    'vision_policy':dict(type='enum',default='optional',values=['optional','required','off'],stages=['asset_visual_review','asset_proposals']),
    'asr_recheck_windows':dict(type='integer',default=12,min=0,max=64,stages=['asr']),
    'alignment_model_path':dict(type='string',default='',max_length=2000,stages=['alignment']),
}

DEPENDENCIES={
    'asr':['source_content_hash','audio_stream_id','source_time_origin','whisper_model','language','whisper_compute',
           'glossary','audience','asr_second_pass','asr_recheck_windows','transcript_correction','alias_revision'],
    'correction':['transcript_id','transcript_revision','glossary','audience','alias_revision','manual_overrides'],
    'asr_recheck':['source_content_hash','audio_stream_id','transcript_id','transcript_revision','whisper_model','language','glossary','manual_overrides','model_ref','origin_word_ids','limit'],
    'alignment':['source_content_hash','audio_stream_id','transcript_id','transcript_revision','alignment_model_path','manual_overrides','origin_word_ids','limit'],
    'source_evidence':['source_content_hash','media_context_revision','ocr_enabled','ocr_max_frames','ocr_interval_s','visual_cues','ocr_engine_version'],
    'discovery':['transcript_id','transcript_revision','source_evidence_fingerprint','model','audience','min_clip_s','max_clip_s',
                 'topic_grace_s','selection_floor','search_depth','discovery_extra_windows','existing_candidate_ids','search_objective'],
    'caption':['transcript_id','correction_revision','timeline_revision','variant_id','font_content_hashes','caption_settings','protected_regions'],
    'asset_proposals':['source_content_hash','transcript_revision','candidate_id','audience','source_kind','broll_mode','broll_provider',
                       'broll_max','broll_query_limit','broll_visual_candidates','local_collection_revision','vision_model','vision_policy','asset_content_hashes'],
    'asset_visual_review':['asset_content_hash','visual_intent','source_context','vision_model','vision_policy','sample_frames'],
}

class AnalysisCancelled(RuntimeError):
    pass


def checkpoint(token=None):
    if token is None:return
    cancelled=token() if callable(token) else token.is_set()
    if cancelled:raise AnalysisCancelled('Analisis dibatalkan sebelum tahap berikutnya; hasil sah sebelumnya tetap disimpan.')


def validate_settings(values):
    import math
    result={}
    for name,spec in SETTINGS.items():
        if name not in values:continue
        value=values[name];kind=spec['type']
        if kind=='boolean':
            if type(value) is not bool:raise ValueError(name+' harus boolean')
        elif kind in ('integer','number'):
            if type(value) not in (int,float) or not math.isfinite(value) or kind=='integer' and type(value) is not int or not spec['min']<=value<=spec['max']:
                raise ValueError(name+' di luar batas')
        elif kind=='enum':
            if value not in spec['values']:raise ValueError(name+' tidak dikenal')
        elif name=='vision_model':
            if not isinstance(value,str) or value and not re.fullmatch(r'[a-zA-Z0-9_.:/-]{1,100}',value) or 'cloud' in value.lower():
                raise ValueError('Pilih nama model vision lokal yang valid')
        elif kind=='string':
            if not isinstance(value,str) or len(value)>spec['max_length']:raise ValueError(name+' tidak valid')
        result[name]=value
    return result


def configured(cfg,overrides=None):
    values={f.name:getattr(cfg,f.name) for f in fields(AnalysisConfig) if hasattr(cfg,f.name)}
    values.update(validate_settings(overrides or {}))
    return AnalysisConfig(**values)
