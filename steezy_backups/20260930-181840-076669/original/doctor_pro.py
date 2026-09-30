"""Read-only diagnostics, no model downloads and no secret/environment dumps."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import urllib.request
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env.pro', override=True)
from clipper.config import Config
from clipper.font_catalog import FONTS
from clipper.looks import LOOKS
from clipper.ffmpeg_util import nvenc_available, nvenc_diagnostic, render_diagnostic
cfg = Config()
print('Python:', sys.version.split()[0])
for name in ('faster_whisper', 'cv2', 'PIL', 'requests', 'fastapi', 'uvicorn', 'multipart', 'pycapcut'):
    print(name + ':', 'OK' if importlib.util.find_spec(name) else 'BELUM TERPASANG')
for name in ('ffmpeg', 'ffprobe'):
    print(name + ':', 'OK' if shutil.which(name) else 'TIDAK DITEMUKAN')
print('Encoder:', 'NVENC tersedia' if nvenc_available() else 'CPU libx264 (fallback)')
print('FFmpeg yang diuji:', nvenc_diagnostic()['ffmpeg'])
render_check = render_diagnostic()
print('Filter + subtitle + encode:', 'OK' if render_check['available'] else 'GAGAL')
if not render_check['available']:
    print(render_check['detail'])
if not nvenc_available():
    print('Alasan probe NVENC:', nvenc_diagnostic()['detail'])
print('Whisper:', cfg.whisper_model, '/', cfg.whisper_device, '/', cfg.whisper_compute)
try:
    with urllib.request.urlopen(cfg.ollama_url + '/api/tags', timeout=5) as r:
        models = [x['name'] for x in json.load(r)['models']]
    print('Ollama:', 'OK')
    print('Model pilihan:', cfg.model, 'TERSEDIA' if cfg.model in models else 'BELUM DIUNDUH')
    if cfg.model not in models:
        print('Unduh gratis dengan: ollama pull ' + cfg.model)
except Exception:
    print('Ollama belum berjalan. Buka aplikasi Ollama; mode video utuh tidak membutuhkan Ollama.')
print('Font berpasangan:', 'OK' if all((Path(cfg.fonts_dir) / f['file']).is_file() for f in FONTS.values()) else 'BELUM LENGKAP')
print('Galeri tipografi:', 'OK' if all((Path(__file__).parent / 'static/templates' / (t['id']+'.mp4')).is_file() for t in LOOKS) else 'BELUM LENGKAP')
print('Studio 2.4: pasangan font -> preview dari posisi sumber -> render -> proyek editable')
print('Native CapCut/Resolve: periksa satu proyek percobaan pada editor Anda.')
