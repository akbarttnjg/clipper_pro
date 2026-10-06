"""The 26 components from the upgrade report, with explicit installation recipes.

Package indexes resolve stable versions once per installation plan. The resulting
lock, source commits and weight hashes belong to a generation, never to a claim
that a component has already been tested on the user's hardware.
"""
from copy import deepcopy


def component(key, name, role, kind, *, packages=(), model=None, repo=None,
              group='visual', estimate_gb=1, access=None, note='', version='stable, dikunci saat pemasangan'):
    official=('https://github.com/'+repo if repo else
              'https://pypi.org/project/'+packages[0].split('==')[0]+'/' if packages else
              {'ffmpeg':'https://ffmpeg.org/','libass':'https://github.com/libass/libass',
               'remotion':'https://www.remotion.dev/','motion-canvas':'https://motioncanvas.io/'}.get(key,'https://ollama.com/'))
    return dict(id=key, name=name, role=role, kind=kind, packages=list(packages),
                model=model, repo=repo, group=group, estimate_bytes=int(estimate_gb*1024**3),
                access=access, note=note, requested_version=version,
                source=official,code_source=official,weight_source=('https://huggingface.co/'+model if model else
                    'Drive ID dari demo resmi; checksum upstream tidak tersedia' if key=='talknet' else
                    'YuNet dari Git LFS resmi' if key=='yunet' else 'Termasuk wheel paket' if key in ('rapidocr','silero-vad') else None),
                platforms=['Windows','Linux / WSL'],runtime=('Node.js >=18; LTS 22 portabel pada Windows' if kind=='node' else
                    'Ollama lokal' if kind=='ollama' else 'FFmpeg di PATH' if kind=='system' else
                    'Dokumentasi dengan commit sumber' if kind=='docs' else 'Python 3.10–3.12, venv terisolasi'),
                default_enabled=False)


CATALOG = [
    component('ffmpeg','FFmpeg / ffprobe','Potong, encode, audio, probe media','system',group='core',estimate_gb=.2,version='biner terdeteksi; hash dan versi dicatat'),
    component('libass','libass','Render subtitle ASS di FFmpeg','system',group='core',estimate_gb=0,version='fitur build FFmpeg terdeteksi'),
    component('fonttools','FontTools','Baca font dan periksa cakupan glyph','pip',packages=['fonttools'],group='core',estimate_gb=.1),
    component('faster-whisper','faster-whisper','Transkripsi lokal dengan timestamp kata','pip',packages=['faster-whisper','Pillow','nvidia-cublas-cu12','nvidia-cudnn-cu12'],model='Systran/faster-whisper-small',group='asr',estimate_gb=5,note='Bobot small untuk uji awal; model medium lama tetap menjadi pilihan mesin.'),
    component('silero-vad','Silero VAD','Deteksi suara versus hening','pip',packages=['silero-vad','torch==2.8.0','torchaudio==2.8.0','numpy','onnxruntime'],group='asr',estimate_gb=7,note='Uji ONNX memakai NumPy dan ONNX Runtime CPU. Pemasangan Silero lama dapat dilengkapi melalui tools/repair_silero_vad.py tanpa memasang ulang Torch.'),
    component('whisperx','WhisperX','Alignment kata dan backend transkripsi pembanding','pip',packages=['whisperx','torch==2.8.0','torchaudio==2.8.0','torchvision==0.23.0','silero-vad'],model='Systran/faster-whisper-small',group='asr',estimate_gb=10,note='Uji impor terpisah dari uji alignment; alignment memerlukan model bahasa.'),
    component('stable-ts','Stable-ts','Pembanding timestamp Whisper','pip',packages=['stable-ts==2.19.1','faster-whisper','torch==2.8.0','torchaudio==2.8.0'],model='Systran/faster-whisper-small',group='asr',estimate_gb=8,version='2.19.1 + bobot small terkunci'),
    component('pyannote','pyannote.audio','Diarisasi pembicara','pip',packages=['pyannote.audio','torch==2.8.0','torchaudio==2.8.0'],model='pyannote/speaker-diarization-3.1',group='asr',estimate_gb=9,access='HF_TOKEN',note='Persetujuan model gated melalui akun Hugging Face diperlukan; paket saja belum berarti model dapat dipakai.'),
    component('scenedetect','PySceneDetect','Deteksi pergantian adegan','pip',packages=['scenedetect','opencv-python-headless'],estimate_gb=.8),
    component('yunet','OpenCV + YuNet','Deteksi wajah untuk framing','pip',packages=['opencv-python-headless'],repo='opencv/opencv_zoo',estimate_gb=.8),
    component('rapidocr','RapidOCR','Baca teks pada layar dan grafik','pip',packages=['rapidocr-onnxruntime'],estimate_gb=1),
    component('e5','multilingual E5 small','Kemiripan cerita dan pencarian aset','pip',packages=['sentence-transformers','torch==2.8.0'],model='intfloat/multilingual-e5-small',estimate_gb=7),
    component('qwen3','Qwen3 lokal','Editor cerita yang sudah digunakan mesin','ollama',group='core',estimate_gb=6,version='tag lokal + digest Ollama; qwen3:8b',note='Memakai Ollama lokal. Pemasangan/pull tidak mengubah model aktif proyek.'),
    component('qwen3-vl','Qwen3-VL 2B','Analisis gambar selektif','pip',packages=['transformers','accelerate','torch==2.8.0','torchvision==0.23.0','Pillow'],model='Qwen/Qwen3-VL-2B-Instruct',estimate_gb=13,note='CPU sebagai uji awal. Tidak diasumsikan muat pada VRAM 4 GB.'),
    component('smolvlm','SmolVLM 500M','Pembanding analisis gambar ringan','pip',packages=['transformers','accelerate','torch==2.8.0','torchvision==0.23.0','Pillow'],model='HuggingFaceTB/SmolVLM-500M-Instruct',estimate_gb=9),
    component('siglip2','SigLIP 2','Penilaian relevansi gambar dan teks','pip',packages=['transformers','torch==2.8.0','Pillow'],model='google/siglip2-base-patch16-224',estimate_gb=8),
    component('talknet','TalkNet-ASD','Uji pembicara aktif dari suara dan wajah','source',packages=['torch==2.8.0','torchvision==0.23.0','numpy','scipy','python_speech_features','gdown'],repo='TaoRuijie/TalkNet-ASD',group='talknet',estimate_gb=8,note='Adapter CPU tersendiri; uji tensor tidak membuktikan akurasi pada video pengguna.'),
    component('sam2','SAM 2.1 tiny','Segmentasi objek untuk komposisi','source',packages=['torch==2.8.0','torchvision==0.23.0','hydra-core','iopath','Pillow','tqdm'],repo='facebookresearch/sam2',model='facebook/sam2.1-hiera-tiny',group='sam',estimate_gb=9,note='Windows: CPU tanpa ekstensi CUDA untuk uji awal; fitur CUDA penuh disarankan melalui WSL.'),
    component('remotion','Remotion','Renderer komposisi berbasis React','node',group='node',estimate_gb=2,version='4.0.533',note='Termasuk komposisi contoh, preview frame, dan render MP4 1 detik.'),
    component('remotion-skills','Remotion official skills','Panduan resmi untuk membuat komposisi','docs',repo='remotion-dev/skills',group='node',estimate_gb=.03,version='commit sumber dikunci',note='Dokumentasi untuk agent, bukan model atau renderer tambahan.'),
    component('motion-canvas','Motion Canvas','Pembanding animasi canvas','node',group='node',estimate_gb=2,version='3.17.2',note='Build contoh dan uji tangkapan animasi pada browser tersendiri.'),
    component('opentimelineio','OpenTimelineIO','Pertukaran struktur timeline','pip',packages=['opentimelineio'],group='core',estimate_gb=.4),
    component('pycapcut','pyCapCut','Menulis draft CapCut berlapis','pip',packages=['pycapcut==0.0.3','requests'],group='core',estimate_gb=.4,version='0.0.3',note='Backend CapCut yang sudah bekerja tetap digunakan; instalasi terisolasi untuk verifikasi.'),
    component('clipsai','ClipsAI','Pembanding pencarian klip','pip',packages=['clipsai==0.2.1','numpy==1.26.4','sentence-transformers==2.7.0','transformers==4.40.2','mediapipe==0.10.21','pyannote.audio==3.3.2'],model='sentence-transformers/all-roberta-large-v1',group='experiments',estimate_gb=14,version='0.2.1',note='Uji ClipFinder memakai transkrip contoh dan bobot RoBERTa asli yang dikunci. Komponen ini tidak mengganti pemilih cerita utama.'),
    component('auto-editor','Auto-Editor','Pembanding pemotongan berdasarkan audio','pip',packages=['auto-editor'],group='experiments',estimate_gb=1),
    component('opus-skill','OpusClip skill','Konektor pembanding layanan OpusClip','docs',repo='opus-pro/opus-skills',group='experiments',estimate_gb=.03,access='OPUSCLIP_API_KEY',version='commit sumber dikunci',note='Unduh dokumentasi saja. Tidak membuat job berbayar atau mengirim video.'),
]
BY_ID = {item['id']:item for item in CATALOG}
assert len(CATALOG) == len(BY_ID) == 26


def get(key):
    if not isinstance(key,str) or key not in BY_ID: raise ValueError('Komponen tidak dikenal: '+str(key))
    return deepcopy(BY_ID[key])


def stock_status(environ):
    return [dict(id=key,name=name,configured=bool(environ.get(token)) if token else True,
                 status=('siap lokal' if not token else 'kunci tersedia; akses belum diuji' if environ.get(token) else 'memerlukan kunci'),
                 tested=False,network_tested=False)
            for key,name,token in [('local','Berkas lokal',None),('source','Potongan dari sumber',None),
                                   ('pexels','Pexels','PEXELS_API_KEY'),('pixabay','Pixabay','PIXABAY_API_KEY'),('coverr','Coverr','COVERR_API_KEY')]]
