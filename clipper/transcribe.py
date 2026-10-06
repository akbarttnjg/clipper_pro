"""Isolated ASR process releases CUDA memory before Ollama starts."""
import gc
import json
import os
import subprocess
import sys
import sysconfig
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from .config import Config


def _add_cuda_dlls():
    if sys.platform != 'win32':
        return
    root = Path(sysconfig.get_paths()['purelib']) / 'nvidia'
    dirs = [str(root / x / 'bin') for x in ('cublas', 'cudnn') if (root / x / 'bin').is_dir()]
    os.environ['PATH'] = os.pathsep.join(dirs + [os.environ.get('PATH', '')])


def _resolve_device(cfg):
    if cfg.whisper_device != 'auto':
        return cfg.whisper_device, cfg.whisper_compute if cfg.whisper_device == 'cuda' else 'int8'
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return 'cuda', cfg.whisper_compute
    except Exception:
        pass
    return 'cpu', 'int8'


def _run(media_path, cfg):
    _add_cuda_dlls()
    from faster_whisper import WhisperModel
    from .typography import valid_words
    from .transcript_correction import prompt, recheck_ranges, merge_recheck
    device, compute = _resolve_device(cfg)
    warnings = []
    def attempt(dev, dtype):
        model = WhisperModel(cfg.whisper_model, device=dev, compute_type=dtype,
                             cpu_threads=max(1, min(8, os.cpu_count() or 4)), num_workers=1)
        try:
            segments, info = model.transcribe(media_path,
                language=None if cfg.language == 'auto' else cfg.language,
                task='transcribe', word_timestamps=True, vad_filter=True, beam_size=5,
                condition_on_previous_text=False, initial_prompt=prompt(cfg) or None)
            words, text, sentences = [], [], []
            for seg in segments:
                text.append(seg.text.strip())
                sentences.append({'id': len(sentences), 'start': float(seg.start),
                                  'end': float(seg.end), 'text': seg.text.strip()})
                for w in seg.words or []:
                    words.append({'word_id': len(words), 'word': w.word.strip(),
                                  'start': float(w.start), 'end': float(w.end),
                                  'probability': float(w.probability)})
            raw_words = valid_words(words)
            heard_words, corrections = raw_words, []
            checked, errors = 0, []
            if cfg.asr_second_pass and cfg.transcript_correction:
                for a, b in recheck_ranges(raw_words, float(info.duration), cfg.asr_recheck_windows):
                    try:
                        with tempfile.TemporaryDirectory(prefix='clipper-listen-') as tmp:
                            audio = Path(tmp) / 'excerpt.wav'
                            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', str(a),
                                '-t', str(b-a), '-i', str(media_path), '-vn', '-ar', '16000', '-ac', '1', str(audio)],
                                capture_output=True, check=True)
                            retry, _ = model.transcribe(str(audio), language=info.language,
                                word_timestamps=True, vad_filter=False, beam_size=8,
                                condition_on_previous_text=False, initial_prompt=prompt(cfg) or None)
                            heard = [{'word': w.word.strip(), 'start': float(w.start)+a, 'end': float(w.end)+a,
                                      'probability': float(w.probability)} for seg in retry for w in seg.words or []]
                        heard_words, accepted = merge_recheck(heard_words, heard)
                        corrections.extend(accepted)
                        checked += 1
                    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                        errors.append(str(exc)[:180])
                        break
            return {'words': heard_words, 'raw_words': raw_words, 'heard_words': heard_words,
                    'asr_corrections': corrections, 'second_pass': {'checked': checked, 'errors': errors},
                    'text': ' '.join(text), 'segments': sentences,
                    'duration': float(info.duration), 'language': info.language,
                    'device': dev, 'warnings': warnings}
        finally:
            del model
            gc.collect()
    try:
        return attempt(device, compute)
    except RuntimeError as exc:
        if device != 'cuda':
            raise
        warnings.append('Transkripsi beralih ke CPU: ' + str(exc)[:200])
        return attempt('cpu', 'int8')


def transcribe(media_path, cfg):
    if not cfg.whisper_isolate:
        return _run(media_path, cfg)
    from .runtime.bridge import managed_asr
    managed=managed_asr(cfg)
    worker_cfg=replace(cfg,whisper_model=managed['weights'],whisper_device=managed['recommended_device'] if cfg.whisper_device=='auto' else cfg.whisper_device) if managed else cfg
    environment=os.environ.copy()
    if managed:
        environment['PYTHONPATH']=str(Path(__file__).resolve().parent.parent)
        environment['PYTHONNOUSERSITE']='1'
    with tempfile.TemporaryDirectory(prefix='steezy-asr-') as tmp:
        config_path, result_path = Path(tmp) / 'config.json', Path(tmp) / 'transcript.json'
        config_path.write_text(json.dumps(asdict(worker_cfg)), encoding='utf-8')
        r = subprocess.run([managed['python'] if managed else sys.executable, '-m', 'clipper.transcribe', '--worker',
                           str(Path(media_path).resolve()), str(config_path), str(result_path)],
                           cwd=str(Path(__file__).resolve().parent.parent), capture_output=True,env=environment,
                           text=True, encoding='utf-8', errors='replace')
        if r.returncode or not result_path.exists():
            raise RuntimeError('Transkripsi gagal. ' + r.stderr[-2500:])
        return json.loads(result_path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    if len(sys.argv) != 5 or sys.argv[1] != '--worker':
        raise SystemExit('Jalankan transkripsi melalui aplikasi.')
    cfg = Config(**json.loads(Path(sys.argv[3]).read_text(encoding='utf-8')))
    result = _run(sys.argv[2], cfg)
    Path(sys.argv[4]).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
