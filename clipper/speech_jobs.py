"""Explicit, bounded speech jobs using existing local models only.

Runs in a child of the owned Studio worker, so cancel kills the speech process
too. Missing weights are actionable errors; no job installs or downloads models.
"""
import copy
import importlib.util
import inspect
import json
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from .config import Config
from .contracts import fingerprint
from . import stage3, transcript_correction as correction


def _options(value):
    if not isinstance(value, dict): raise ValueError('Opsi proses harus objek.')
    limit = value.get('limit', 12)
    if type(limit) is not int or not 1 <= limit <= 24: raise ValueError('Batas proses harus 1–24 rentang.')
    ids = value.get('origin_word_ids', [])
    if not isinstance(ids, list) or len(ids) > 80 or any(type(i) not in (int, str) for i in ids):
        raise ValueError('Pilih maksimal 80 identitas kata sumber.')
    return {'limit': limit, 'origin_word_ids': ids}


def recheck_options(value):
    if set(value) - {'limit', 'origin_word_ids','model_ref'}: raise ValueError('Opsi uji ulang ASR tidak dikenal.')
    result=_options(value);ref=value.get('model_ref','')
    if not isinstance(ref,str) or len(ref)>160:raise ValueError('Pilihan model ASR tidak valid.')
    result['model_ref']=ref;return result


def available_asr_models():
    from .runtime.state import read, runtime_root, safe_path
    root=runtime_root();result=[]
    for component in ('faster-whisper','whisperx'):
        try:
            pointer=read(root/f'components/{component}/active.json',{})
            if not pointer.get('generation'):continue
            directory=safe_path(root/'generations',pointer['generation']);receipt=read(directory/'receipt.json',{})
            python=directory/'env'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            weights=directory/'weights'
            if receipt.get('installed') and python.is_file() and (weights/'model.bin').is_file():
                result.append({'id':'managed:'+pointer['generation'],'model':receipt.get('model_choice') or (receipt.get('weights') or {}).get('repo') or ('small' if component=='whisperx' else 'model lokal'),
                    'component':component,'python':str(python),'weights':str(weights)})
        except (OSError,ValueError):continue
    hub=Path(os.environ.get('HF_HUB_CACHE') or Path(os.environ.get('HF_HOME',str(Path.home()/'.cache/huggingface')))/'hub')
    if hub.is_dir():
        for path in sorted(hub.glob('models--*faster-whisper*/snapshots/*/model.bin')):
            if not path.is_file():continue
            result.append({'id':'cached:'+fingerprint(str(path.parent))[:24],'model':path.parents[2].name.split('faster-whisper-')[-1],
                'component':'cache ASR','python':sys.executable,'weights':str(path.parent)})
    return result[:40]


def alignment_options(value):
    if set(value) - {'limit', 'origin_word_ids', 'model_path'}: raise ValueError('Opsi alignment tidak dikenal.')
    result = _options(value); path = value.get('model_path', '')
    if not isinstance(path, str) or len(path) > 2000: raise ValueError('Lokasi model alignment tidak valid.')
    result['model_path'] = path.strip(); return result


def local_alignment_model(path):
    if not path: raise ValueError('Pilih folder model alignment lokal Wav2Vec2 CTC untuk bahasa sumber. Model ASR Whisper berbeda dari model alignment.')
    root = Path(path).expanduser().resolve()
    if not root.is_dir() or not (root/'config.json').is_file(): raise ValueError('Folder model alignment harus berisi config.json.')
    data = json.loads((root/'config.json').read_text(encoding='utf-8'))
    if data.get('model_type') != 'wav2vec2': raise ValueError('Adapter ini memerlukan model Wav2Vec2 CTC lokal.')
    if not any(root.glob('*.safetensors')) and not any(root.glob('pytorch_model*.bin')):
        raise ValueError('Bobot model alignment lokal belum lengkap.')
    if not all((root/name).is_file() for name in ('vocab.json', 'preprocessor_config.json')):
        raise ValueError('Tokenizer/vocab dan preprocessor model alignment belum lengkap.')
    return str(root)


def alignment_runtime(cfg, options):
    model = local_alignment_model(options.get('model_path') or cfg.alignment_model_path)
    from .runtime.state import read, runtime_root, safe_path
    root = runtime_root(); pointer = read(root/'components/whisperx/active.json', {})
    if pointer.get('generation'):
        directory = safe_path(root/'generations', pointer['generation']); receipt = read(directory/'receipt.json', {})
        python = directory/'env'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if receipt.get('installed') and python.is_file(): return {'python': str(python), 'model_path': model, 'generation': pointer['generation']}
    if importlib.util.find_spec('whisperx') is not None: return {'python': sys.executable, 'model_path': model, 'generation': 'core'}
    raise ValueError('WhisperX belum tersedia. Pasang melalui Komponen lokal; model alignment tetap dipilih dari folder lokal.')


def alignment_availability(cfg):
    try:
        runtime = alignment_runtime(cfg, {})
        return {'status': 'ready_to_try', 'model_path': runtime['model_path'], 'generation': runtime['generation'],
                'device': 'cpu', 'message': 'Model lokal tersedia; akurasi alignment masih diperiksa saat proses. Timing manual juga tersedia.'}
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return {'status': 'needs_local_model', 'device': 'cpu', 'message': str(exc), 'manual_available': True}


def _excerpt(source, start, end, target):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', str(start), '-t', str(end-start),
                    '-i', str(source), '-map', '0:a:0', '-vn', '-ar', '16000', '-ac', '1', str(target)],
                   check=True, capture_output=True)


def _asr_model_path(model):
    root = Path(model).expanduser()
    if root.is_dir() and (root/'model.bin').is_file(): return str(root.resolve())
    from faster_whisper.utils import download_model
    try: return download_model(model, local_files_only=True)
    except (ValueError, OSError) as exc:
        raise ValueError('Bobot ASR pilihan ini belum tersimpan lokal. Pilih model yang sudah tersedia; uji ulang tidak mengunduh model.') from exc


def selected_ranges(words, duration, limit):
    """Keep overlapping selected words inside the actual checked audio window."""
    ranges = []
    spans = sorted((max(0., w['start']-3), min(duration, w['end']+3)) for w in words)
    for a, b in spans:
        b = min(b, a+20.)
        if ranges and b <= ranges[-1][1]:
            continue
        if ranges and a <= ranges[-1][1] and b-ranges[-1][0] <= 20.:
            ranges[-1][1] = b
        else:
            ranges.append([a, b])
    return ranges[:limit]


def _recheck(source, transcript, cfg, options):
    from .transcribe import _add_cuda_dlls, _resolve_device
    from faster_whisper import WhisperModel
    _add_cuda_dlls(); selected = options['origin_word_ids']; words = copy.deepcopy(transcript['words'])
    targets = [w for w in words if not selected or set(correction.source_ids([w])) & set(selected)]
    if selected:
        ranges = selected_ranges(targets, transcript['duration'], options['limit'])
    else: ranges = [(a,min(b,a+20.)) for a,b in correction.recheck_ranges(targets, transcript['duration'], options['limit'])]
    if not ranges: return {'words': words, 'changes': [], 'report': {'checked': 0, 'accepted': 0, 'errors': [], 'note': 'Tidak ada rentang terarah yang perlu diuji ulang.'}}
    model_path = _asr_model_path(cfg.whisper_model); device, compute = _resolve_device(cfg); warnings = []
    def attempt(dev, dtype):
        model = WhisperModel(model_path, device=dev, compute_type=dtype, cpu_threads=max(1, min(8, os.cpu_count() or 4)), num_workers=1, local_files_only=True)
        result = copy.deepcopy(words); changes = []; checked = 0; errors = []; evidence = []
        with tempfile.TemporaryDirectory(prefix='clipper-recheck-') as tmp:
            for a, b in ranges:
                try:
                    audio = Path(tmp)/'excerpt.wav'; _excerpt(source, a, b, audio)
                    segments, _ = model.transcribe(str(audio), language=transcript.get('language') if cfg.language == 'auto' else cfg.language,
                        word_timestamps=True, vad_filter=False, beam_size=8, condition_on_previous_text=False,
                        initial_prompt=correction.prompt(cfg) or None)
                    heard = [{'word': w.word.strip(), 'start': float(w.start)+a, 'end': float(w.end)+a, 'probability': float(w.probability)}
                             for segment in segments for w in segment.words or []]
                    # Keep alternate facts as evidence for manual listening, never auto-apply.
                    before = [w for w in result if w['end'] > a and w['start'] < b]
                    result, accepted = correction.merge_recheck(result, heard); changes.extend(accepted); checked += 1
                    evidence.append({'start': a, 'end': b, 'heard': ' '.join(w['word'] for w in heard),
                        'fact_review': stage3.fact_review(' '.join(w['word'] for w in before), ' '.join(w['word'] for w in heard)), 'accepted': len(accepted)})
                except (ValueError, OSError, subprocess.SubprocessError) as exc:
                    errors.append({'start': a, 'end': b, 'message': str(exc)[:250]})
        del model
        return {'words': result, 'changes': changes, 'report': {'checked': checked, 'accepted': len(changes),
            'errors': errors, 'device': dev, 'ranges': evidence, 'warnings': warnings, 'basis': 'Targeted ASR; bukan forced alignment.'}}
    try: return attempt(device, compute)
    except RuntimeError as exc:
        if device != 'cuda': raise
        warnings.append('ASR beralih ke CPU: '+str(exc)[:200]); return attempt('cpu', 'int8')


def _alignment(source, transcript, cfg, options):
    import nltk
    # WhisperX otherwise downloads punkt_tab silently. An offline job must fail clearly.
    def no_download(*args, **kwargs): raise ValueError('Data NLTK punkt_tab belum ada di lingkungan WhisperX. Timing manual tersedia; alignment tidak mengunduh data otomatis.')
    nltk.download = no_download
    import whisperx
    model_path = local_alignment_model(options['model_path']); selected = options['origin_word_ids']
    words = [w for w in transcript['words'] if (set(correction.source_ids([w])) & set(selected) if selected else
             (w.get('correction') or w.get('manually_edited') or len(w['word'].split()) > 1)) and not w.get('aligned_words')][:options['limit']]
    if not words: return {'patches': [], 'report': {'aligned': 0, 'errors': [], 'device': 'cpu'}}
    language = transcript.get('language') or cfg.language
    if language == 'auto': raise ValueError('Bahasa transkrip belum diketahui. Pilih bahasa sebelum alignment.')
    kwargs={'language_code':language,'device':'cpu','model_name':model_path}
    if 'model_cache_only' in inspect.signature(whisperx.load_align_model).parameters:kwargs['model_cache_only']=True
    # Absolute local model paths also work in older WhisperX. The parent
    # enforces offline HF variables before starting this process.
    model, metadata = whisperx.load_align_model(**kwargs)
    patches = []; errors = []
    with tempfile.TemporaryDirectory(prefix='clipper-align-') as tmp:
        for word in words:
            a, b = stage3.alignment_window(word,transcript['words'],transcript['duration'])
            try:
                if b-a > 20: raise ValueError('Frasa terlalu panjang untuk alignment terarah. Pecah atau beri timing manual.')
                audio = Path(tmp)/'excerpt.wav'; _excerpt(source, a, b, audio)
                data = whisperx.align([{'start': 0., 'end': b-a, 'text': word['word']}], model, metadata,
                                     str(audio), device='cpu', interpolate_method='ignore', return_char_alignments=False)
                aligned = [{**w, 'start': w.get('start', math.nan)+a, 'end': w.get('end', math.nan)+a} for w in data.get('word_segments', [])]
                aligned = stage3.validate_alignment(word['word'], aligned, a, b, method='whisperx')
                patches.append({'origin_word_ids': correction.source_ids([word]), 'text': word['word'], 'words': aligned,
                    'audio_start': a, 'audio_end': b, 'method': 'whisperx', 'provenance': {'kind': 'local_forced_alignment',
                    'model_path': model_path, 'device': 'cpu', 'language': language}})
            except (ValueError, RuntimeError, KeyError, TypeError) as exc:
                errors.append({'origin_word_ids': correction.source_ids([word]), 'message': str(exc)[:350]})
    return {'patches': patches, 'report': {'aligned': len(patches), 'attempted': len(words), 'errors': errors,
        'status':'partial' if errors else 'aligned',
        'device': 'cpu', 'model_path': model_path, 'basis': 'Measured CTC word alignment; missing/interpolated word scores rejected.'}}


def run(kind, source, transcript, cfg, options):
    options = alignment_options(options) if kind == 'alignment' else recheck_options(options)
    runtime = alignment_runtime(cfg, options) if kind == 'alignment' else None
    if kind == 'asr_recheck':
        from .runtime.bridge import managed_asr
        managed = next((r for r in available_asr_models() if r['id']==options.get('model_ref')),None) if options.get('model_ref') else managed_asr(cfg)
        if options.get('model_ref') and managed is None:raise ValueError('Model ASR pilihan tidak lagi tersedia. Muat ulang pilihan model lokal.')
        if managed:
            runtime = managed; cfg = replace(cfg, whisper_model=managed['weights'], whisper_device=managed.get('recommended_device','cpu') if cfg.whisper_device == 'auto' else cfg.whisper_device)
    if kind == 'alignment': options['model_path'] = runtime['model_path']
    environment = os.environ.copy()
    environment.update(PYTHONPATH=str(Path(__file__).resolve().parent.parent), PYTHONNOUSERSITE='1',
        PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    with tempfile.TemporaryDirectory(prefix='clipper-speech-') as tmp:
        request, result = Path(tmp)/'request.json', Path(tmp)/'result.json'
        request.write_text(json.dumps({'kind': kind, 'source': str(source), 'transcript': transcript, 'config': asdict(cfg), 'options': options}, ensure_ascii=False), encoding='utf-8')
        process = subprocess.run([runtime['python'] if runtime else sys.executable, '-m', 'clipper.speech_jobs', str(request), str(result)],
            capture_output=True, env=environment, cwd=str(Path(__file__).resolve().parent.parent), text=True, encoding='utf-8', errors='replace')
        if process.returncode or not result.is_file(): raise ValueError('Proses ucapan gagal. '+process.stderr[-2000:])
        data=json.loads(result.read_text(encoding='utf-8'))
        data['report'].update(producer_version=stage3.VERSION,model_used=options['model_path'] if kind=='alignment' else cfg.whisper_model,
            runtime_generation=(runtime.get('generation') or runtime.get('id','core')) if runtime else 'core')
        return data


def rechecked_transcript(original, result, cfg):
    # Manual patches stay outside the immutable take. Heard words hold only ASR changes.
    new = copy.deepcopy(original); new['heard_words'] = result['words']; new['words'] = result['words']
    new['asr_corrections'] = original.get('asr_corrections', []) + result['changes']
    new['second_pass'] = result['report']; return correction.refine(new, cfg)


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit('Jalankan melalui antrean Studio.')
    data = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')); config = Config(**data['config'])
    result = _alignment(data['source'], data['transcript'], config, data['options']) if data['kind'] == 'alignment' else _recheck(data['source'], data['transcript'], config, data['options'])
    Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
