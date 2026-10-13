"""M2 speech receipts: measured inference is separate from language coverage."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse
from .transcript_tracks import number, critical_review, language


def memory_receipt():
    try:
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),('PeakWorkingSetSize',ctypes.c_size_t),
                    ('WorkingSetSize',ctypes.c_size_t),('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]
            c=Counters();c.cb=ctypes.sizeof(c)
            if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(c),c.cb):raise OSError()
            peak=c.PeakWorkingSetSize
        else:
            import resource
            peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
        return {'peak_process_rss_bytes':peak,'gpu_peak_bytes':None,'gpu_measurement':'not_sampled','scope':'worker_lifetime_not_model_only'}
    except (ImportError,OSError,AttributeError):return {'peak_process_rss_bytes':None,'gpu_peak_bytes':None,'status':'not_measured'}


def pauses(segments,duration):
    merged=[]
    for row in sorted(segments,key=lambda x:x['start']):
        a=max(0.,number(row['start']));b=min(duration,number(row['end']))
        if b<=a:continue
        if merged and a<=merged[-1]['end']:merged[-1]['end']=max(b,merged[-1]['end'])
        else:merged.append({'start':a,'end':b})
    gaps=[];cursor=0.
    for row in merged:
        if row['start']>cursor:gaps.append({'start':cursor,'end':row['start'],'policy':'preserve'})
        cursor=row['end']
    if cursor<duration:gaps.append({'start':cursor,'end':duration,'policy':'preserve'})
    return {'speech_segments':merged,'pause_segments':gaps,'automatic_cutting':False,'source_time_preserved':True}


def vad_input(source,cfg):
    from faster_whisper.audio import decode_audio
    audio=decode_audio(source,sampling_rate=16000);duration=len(audio)/16000
    if cfg.vad_policy=='off':return audio,[0.,duration],{'provider':'disabled','inference_performed':False,**pauses([{'start':0.,'end':duration}],duration)}
    from faster_whisper.vad import get_speech_timestamps, VadOptions
    rows=get_speech_timestamps(audio,VadOptions(threshold=.5,min_silence_duration_ms=500,speech_pad_ms=200))
    segments=[{'start':r['start']/16000,'end':r['end']/16000} for r in rows]
    return audio,[v for r in segments for v in (r['start'],r['end'])],{'provider':'faster_whisper_silero','inference_performed':True,'gate_count':1,**pauses(segments,duration)}


def normalize(result,cfg):
    duration=number(result['duration'],'durasi ASR')
    reported=result.get('language');result['reported_language']=reported
    try:result['language']=language(reported) if reported and reported!='auto' else 'und'
    except ValueError:result['language']='und'
    lp=result.get('language_probability')
    if lp is not None and not 0<=number(lp,'language confidence')<=1:raise ValueError('Language confidence tidak valid')
    for field in ('words','raw_words','heard_words'):
        rows=result.get(field,result.get('words',[]))
        for i,w in enumerate(rows):
            w.setdefault('word_id',i);w['start']=number(w['start']);w['end']=number(w['end'])
            if not 0<=w['start']<w['end']<=duration:raise ValueError('ASR mengembalikan timestamp tidak valid')
            p=w.get('probability')
            if p is not None and not 0<=number(p,'confidence')<=1:raise ValueError('ASR mengembalikan confidence tidak valid')
            w['probability']=p;w.setdefault('confidence_kind','asr_probability' if p is not None else 'not_reported')
            w.setdefault('timing_status','asr_estimated');w.setdefault('speaker_id',None);w.setdefault('source_word_ids',[w['word_id']])
        result[field]=copy.deepcopy(rows)
    result.update(timebase='source_seconds',source_language=result.get('language'),output_language=cfg.output_language,
        code_switch_quality='needs_corpus_review',critical_review=critical_review(result['words'],cfg.glossary))
    result.setdefault('runtime_receipt',{}).setdefault('memory',memory_receipt())
    return result


def http_asr(source,cfg):
    import requests
    endpoint=os.environ.get('CLIPPER_ASR_ENDPOINT','');url=urlparse(endpoint)
    if not endpoint:raise ValueError('Isi CLIPPER_ASR_ENDPOINT untuk provider ASR HTTP pilihan')
    if url.scheme!='https' and not (url.scheme=='http' and url.hostname in ('localhost','127.0.0.1','::1')):raise ValueError('Provider ASR harus HTTPS atau localhost')
    if url.username or url.password:raise ValueError('Kredensial ASR menggunakan variabel lingkungan')
    from .media_context import inspect
    duration=inspect(source)['duration'];headers={};key=os.environ.get('CLIPPER_ASR_API_KEY')
    if key:headers['Authorization']='Bearer '+key
    options={'model':cfg.whisper_model,'response_format':'verbose_json','timestamp_granularities[]':'word'}
    if cfg.language!='auto':options['language']=cfg.language
    with open(source,'rb') as stream:
        response=requests.post(endpoint,data=options,files={'file':(Path(source).name,stream)},headers=headers,timeout=600)
    response.raise_for_status();data=response.json();rows=data.get('words')
    if not isinstance(rows,list) or not rows:raise ValueError('Provider harus mengembalikan timestamp kata; timing segmen tidak dipecah secara buatan')
    words=[{'word_id':i,'word':w['word'],'start':w['start'],'end':w['end'],'probability':w.get('probability')} for i,w in enumerate(rows)]
    return normalize({'words':words,'duration':duration,'language':data.get('language',cfg.language),'segments':data.get('segments',[]),
        'text':data.get('text',''),'runtime_receipt':{'provider':'http','requested_model':cfg.whisper_model,'actual_model':data.get('model'),
            'actual_device':data.get('device'),'device_status':'provider_reported' if data.get('device') else 'not_reported',
            'inference_performed':True,'generation':data.get('generation'),'memory':{'status':'remote_not_measured'}}},cfg)


def language_matrix(cfg):
    from .speech_jobs import alignment_availability
    availability=alignment_availability(cfg);model=cfg.whisper_model
    known=model in ('tiny','base','small','medium','large','large-v1','large-v2','large-v3','large-v3-turbo','turbo') or model.endswith('.en')
    return [{'language':lang,'asr_model':model,'model_support':('supported' if not model.endswith('.en') or lang=='en' else 'unsupported') if known else 'not_verified',
        'alignment':availability['status'],'alignment_language_quality':'not_measured','measured_quality':'not_tested',
        'wer':None,'timing_error_ms':None,'speaker_error_rate':None} for lang in ('id','en','zh','ja','ko','ar','es','fr','de','pt','hi','ru')]


def assign_speakers(words,segments):
    result=copy.deepcopy(words)
    for word in result:
        scores={}
        for segment in segments:
            overlap=max(0.,min(word['end'],segment['end'])-max(word['start'],segment['start']))
            if overlap:scores[segment['speaker_id']]=scores.get(segment['speaker_id'],0)+overlap
        ordered=sorted(scores.items(),key=lambda x:x[1],reverse=True)
        ambiguous=len(ordered)>1 and ordered[0][1]-ordered[1][1]<.05
        word.update(speaker_id=ordered[0][0] if ordered and not ambiguous else None,
            speaker_provenance='measured_audio_diarization',speaker_status='needs_review' if ambiguous or len(ordered)>1 or not ordered else 'assigned',
            overlapping_speakers=[x[0] for x in ordered] if len(ordered)>1 else [])
    return result


def _runtime(cfg,component):
    from .runtime.state import read,runtime_root,safe_path
    root=Path(cfg.visual_runtime_root) if cfg.visual_runtime_root else runtime_root();active=read(root/'components'/component/'active.json',{}) or {}
    if active.get('generation'):
        directory=safe_path(root/'generations',active['generation']);receipt=read(directory/'receipt.json',{}) or {}
        py=directory/'env'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        if receipt.get('installed') and py.is_file():return {'python':str(py),'directory':str(directory),'generation':active['generation'],'receipt':receipt}
    import importlib.util
    module='pyannote.audio' if component=='pyannote' else component
    try:available=importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:available=False
    if available:return {'python':sys.executable,'generation':'core','receipt':{}}
    raise ValueError(component+' belum terpasang pada runtime lokal; pasang dari panel Komponen lokal')


def run_isolated(kind,source,cfg):
    runtime=_runtime(cfg,'whisperx' if kind=='whisperx' else 'pyannote')
    if kind=='whisperx':
        from .speech_jobs import local_alignment_model
        local_alignment_model(cfg.alignment_model_path)
        if cfg.vad_policy!='silero':raise ValueError('WhisperX adapter memerlukan VAD Silero lokal')
        model=Path(cfg.whisper_model)
        if not (model/'model.bin').is_file():
            model=Path(runtime.get('directory',''))/'weights'
            choice=runtime['receipt'].get('model_choice')
            if choice!=cfg.whisper_model or not (model/'model.bin').is_file():raise ValueError('Generation WhisperX tidak cocok dengan model ASR pilihan; pilih bobot lokal yang lengkap')
        weights=str(model.resolve())
    else:
        weights=cfg.diarization_model_path.strip().strip('"\'')
        if not weights or not Path(weights).is_file():raise ValueError('Pilih config YAML pipeline diarization lokal dengan bobot lokal yang lengkap')
    environment={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','PYTHONPATH':str(Path(__file__).resolve().parents[1]),'PYTHONNOUSERSITE':'1'}
    with tempfile.TemporaryDirectory(prefix='clipper-m2-speech-') as tmp:
        request=Path(tmp)/'request.json';output=Path(tmp)/'result.json'
        request.write_text(json.dumps({'source':str(Path(source).resolve()),'cfg':asdict(cfg),'kind':kind,'weights':weights,'generation':runtime['generation']}))
        r=subprocess.run([runtime['python'],'-m','clipper.speech_m2',str(request),str(output)],capture_output=True,text=True,env=environment,cwd=str(Path(__file__).resolve().parents[1]))
        if r.returncode or not output.is_file():raise ValueError('Backend ucapan lokal gagal: '+r.stderr[-1800:])
        return json.loads(output.read_text())


def _worker(request):
    from .config import Config
    cfg=Config(**request['cfg']);source=request['source'];start=time.monotonic()
    if request['kind']=='diarization':
        import torch
        from pyannote.audio import Pipeline
        pipeline=Pipeline.from_pretrained(request['weights']);pipeline.to(torch.device('cpu'));annotation=pipeline(source)
        if hasattr(annotation,'speaker_diarization'):annotation=annotation.speaker_diarization
        segments=[{'start':float(t.start),'end':float(t.end),'speaker_id':str(s)} for t,_,s in annotation.itertracks(yield_label=True)]
        return {'segments':segments,'runtime_receipt':{'provider':'pyannote','actual_model':request['weights'],'actual_device':'cpu',
            'generation':request['generation'],'inference_performed':True,'elapsed_seconds':time.monotonic()-start,'memory':memory_receipt()},'face_identity_inferred':False}
    import torch
    import whisperx
    from .transcribe import _resolve_device
    # torch.hub Silero must resolve an already cached repository, never install during a job.
    cache=Path(torch.hub.get_dir());repos=sorted(cache.glob('snakers4_silero-vad_*'))
    if not repos:raise ValueError('Silero Torch repository belum tersimpan lokal untuk WhisperX; lakukan instalasi/uji komponen dahulu')
    original_load=torch.hub.load
    def local_load(repo_or_dir,model,*args,**kwargs):
        if str(repo_or_dir).startswith('snakers4/silero-vad'):
            kwargs={k:v for k,v in kwargs.items() if k not in ('force_reload','trust_repo','source')}
            return original_load(str(repos[-1]),model,*args,source='local',**kwargs)
        return original_load(repo_or_dir,model,*args,**kwargs)
    torch.hub.load=local_load
    device,compute=_resolve_device(cfg);audio=whisperx.load_audio(source)
    model=whisperx.load_model(request['weights'],device,compute_type=compute,vad_method='silero',local_files_only=True,
        language=None if cfg.language=='auto' else cfg.language)
    generated=model.transcribe(audio,batch_size=4,language=None if cfg.language=='auto' else cfg.language)
    aligner,metadata=whisperx.load_align_model(language_code=generated['language'],device='cpu',model_name=cfg.alignment_model_path)
    aligned=whisperx.align(generated['segments'],aligner,metadata,audio,'cpu',interpolate_method='ignore')
    words=[]
    for row in aligned.get('word_segments',[]):
        if not all(k in row for k in ('start','end','score')):raise ValueError('Alignment tidak menghasilkan semua waktu kata; review timestamp manual')
        score=number(row['score'],'alignment score')
        if not 0<=score<=1:raise ValueError('Alignment score tidak valid')
        words.append({'word_id':len(words),'word':row['word'],'start':row['start'],'end':row['end'],'probability':None,
            'alignment_confidence':score,'timing_status':'weak_alignment' if score<.5 else 'aligned_measured'})
    result={'words':words,'duration':len(audio)/16000,'language':generated['language'],'segments':generated['segments'],
        'text':' '.join(w['word'] for w in words),'vad':{'provider':'whisperx_local_silero','gate_count':1,**pauses(generated['segments'],len(audio)/16000)},
        'runtime_receipt':{'provider':'whisperx','actual_model':request['weights'],'requested_model':cfg.whisper_model,'actual_device':device,
            'alignment_device':'cpu','actual_compute_type':compute,'generation':request['generation'],'inference_performed':True,
            'elapsed_seconds':time.monotonic()-start,'memory':memory_receipt()}}
    return normalize(result,cfg)


if __name__=='__main__':
    data=json.loads(Path(sys.argv[1]).read_text());Path(sys.argv[2]).write_text(json.dumps(_worker(data),ensure_ascii=False,allow_nan=False))
