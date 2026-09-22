"""Isolated ASR process releases CUDA memory before Ollama starts."""
import gc
import json
import os
import subprocess
import sys
import sysconfig
import tempfile
from dataclasses import asdict
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
    device, compute = _resolve_device(cfg)
    warnings = []
    def attempt(dev, dtype):
        model = WhisperModel(cfg.whisper_model, device=dev, compute_type=dtype,
                             cpu_threads=max(1, min(8, os.cpu_count() or 4)), num_workers=1)
        try:
            segments, info = model.transcribe(media_path,
                language=None if cfg.language == 'auto' else cfg.language,
                task='transcribe', word_timestamps=True, vad_filter=True, beam_size=5,
                condition_on_previous_text=False)
            words, text = [], []
            for seg in segments:
                text.append(seg.text.strip())
                for w in seg.words or []:
                    words.append({'word_id': len(words), 'word': w.word.strip(),
                                  'start': float(w.start), 'end': float(w.end),
                                  'probability': float(w.probability)})
            return {'words': valid_words(words), 'text': ' '.join(text),
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
    with tempfile.TemporaryDirectory(prefix='steezy-asr-') as tmp:
        config_path, result_path = Path(tmp) / 'config.json', Path(tmp) / 'transcript.json'
        config_path.write_text(json.dumps(asdict(cfg)), encoding='utf-8')
        r = subprocess.run([sys.executable, '-m', 'clipper.transcribe', '--worker',
                           str(Path(media_path).resolve()), str(config_path), str(result_path)],
                           cwd=str(Path(__file__).resolve().parent.parent), capture_output=True,
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
