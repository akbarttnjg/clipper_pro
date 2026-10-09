"""Standalone component process: no FastAPI or core heavy imports required.

Only declared operations are accepted. Import checks and inference checks have
different levels. A smoke test is never presented as a quality benchmark.
"""
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request

MODULES={'faster-whisper':'faster_whisper','silero-vad':'silero_vad','whisperx':'whisperx',
         'stable-ts':'stable_whisper','pyannote':'pyannote.audio','scenedetect':'scenedetect',
         'yunet':'cv2','rapidocr':'rapidocr_onnxruntime','mediapipe':'mediapipe','e5':'sentence_transformers',
         'qwen3-vl':'transformers','smolvlm':'transformers','siglip2':'transformers',
         'opentimelineio':'opentimelineio','pycapcut':'pycapcut','clipsai':'clipsai','auto-editor':'auto_editor',
         'fonttools':'fontTools','talknet':'torch','sam2':'torch'}


def command(args, timeout=120):
    result=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=timeout)
    if result.returncode:raise RuntimeError(result.stderr[-1800:] or result.stdout[-1800:])
    return result.stdout.strip()


def excerpt(request, directory):
    source=request.get('source')
    if not source:raise ValueError('Uji ini membutuhkan sumber video/audio. Pilih proyek atau isi path pada panel komponen.')
    audio=directory/'sample.wav'
    command(['ffmpeg','-nostdin','-v','error','-y','-i',source,'-t','6','-vn','-ar','16000','-ac','1',audio])
    import wave
    import numpy as np
    with wave.open(str(audio)) as stream:
        values=np.frombuffer(stream.readframes(stream.getnframes()),dtype=np.int16).astype(np.float32)/32768
    if not len(values):raise ValueError('Cuplikan sumber tidak mempunyai audio')
    return audio,values


def infer(request):
    key=request['component'];directory=Path(request['directory']);sample_dir=directory/'sample';sample_dir.mkdir(parents=True,exist_ok=True)
    repo=Path(request['repo']);weights=directory/'weights';source=directory/'source'
    sample=request.get('sample',False);device=request.get('device','cpu')
    if key=='clipsai':
        # Import only the clipping backend, avoiding the unrelated legacy
        # WhisperX/resize imports in the package facade. No network downloads
        # are permitted as an import side effect.
        import types
        import nltk
        nltk.download=lambda *args,**kwargs:False
        spec=importlib.util.find_spec('clipsai')
        if not spec or not spec.submodule_search_locations:raise ImportError('ClipsAI belum tersedia')
        package=types.ModuleType('clipsai');package.__path__=list(spec.submodule_search_locations);sys.modules['clipsai']=package
        importlib.import_module('clipsai.clip.clipfinder')
    elif key in MODULES:importlib.import_module(MODULES[key])
    if key in ('talknet','sam2'):
        sys.path.insert(0,str(source))
        importlib.import_module('model.talkNetModel' if key=='talknet' else 'sam2.build_sam')
    if key=='mediapipe':device='cpu'
    result={'passed':True,'level':'import','device':device,'detail':'Impor modul lulus; inference belum dijalankan','artifacts':[]}
    if key in ('ffmpeg','libass'):
        ffmpeg=shutil.which('ffmpeg');ffprobe=shutil.which('ffprobe')
        if not ffmpeg or not ffprobe:raise ValueError('FFmpeg / ffprobe belum ada di PATH. Gunakan pemasangan FFmpeg Windows yang sudah dipakai mesin.')
        version=command([ffmpeg,'-version']).splitlines()[0]
        result.update(versions={'ffmpeg':version,'ffmpeg_path':ffmpeg,'ffprobe':command([ffprobe,'-version']).splitlines()[0]})
        if key=='libass':
            filters=command([ffmpeg,'-hide_banner','-filters'])
            if not any(' ass ' in line or ' subtitles ' in line for line in filters.splitlines()):raise ValueError('Build FFmpeg belum menyediakan filter libass')
            ass=sample_dir/'subtitle.ass';ass.write_text('[Script Info]\nScriptType: v4.00+\nPlayResX: 320\nPlayResY: 180\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,DejaVu Sans,24,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,15,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Clipper tahap 2\n',encoding='utf-8')
            # Relative cwd path avoids Windows filter escaping ambiguities.
            r=subprocess.run([ffmpeg,'-nostdin','-v','error','-y','-f','lavfi','-i','color=c=black:s=320x180:d=1','-vf','ass=subtitle.ass','-frames:v','1','-threads','1','subtitle.png'],cwd=sample_dir,capture_output=True,text=True,timeout=60)
            if r.returncode:raise RuntimeError(r.stderr[-1600:])
            result.update(level='sample',detail='Frame subtitle libass berhasil dirender',artifacts=['sample/subtitle.png'])
        else:
            output=sample_dir/'ffmpeg.mp4'
            command([ffmpeg,'-nostdin','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=24:duration=1','-c:v','libx264','-threads','1',output])
            info=json.loads(command([ffprobe,'-v','error','-show_streams','-of','json',output]))
            if not any(s.get('codec_type')=='video' and s.get('width')==320 for s in info['streams']):raise ValueError('Video sampel FFmpeg tidak valid')
            result.update(level='sample',detail='Encode dan probe video 1 detik berhasil',artifacts=['sample/ffmpeg.mp4'])
        return result
    if key in ('remotion-skills','opus-skill'):
        docs=list(source.rglob('*.md'))
        if not docs:raise ValueError('Dokumentasi sumber belum tersedia')
        result.update(level='documents',detail=str(len(docs))+' dokumen dengan hash sumber. '+('Akses API OpusClip belum diuji; tidak ada unggahan atau job berbayar.' if key=='opus-skill' else 'Skills terpasang sebagai panduan; renderer diuji melalui komponen Remotion.'))
        return result
    if key=='qwen3':
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=15) as response:tags=json.load(response)
        if not any(m['name']=='qwen3:8b' for m in tags.get('models',[])):raise ValueError('qwen3:8b belum tersedia di Ollama lokal')
        if sample:
            body={'model':'qwen3:8b','prompt':'Jawab singkat: berapa hasil 2+2?','stream':False,'think':False,'keep_alive':0,'options':{'num_predict':16,'num_ctx':512}}
            request_=urllib.request.Request('http://127.0.0.1:11434/api/generate',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request_,timeout=240) as response:data=json.load(response)
            if not data.get('response','').strip():raise ValueError('Model tidak menghasilkan jawaban')
            result.update(level='sample',detail='Inference lokal berhasil: '+data['response'][:160])
        else:result['detail']='Model lokal terdeteksi; inference belum dijalankan'
        return result
    if key=='fonttools':
        from fontTools.ttLib import TTFont
        path=repo/'clipper/fonts/DejaVuSans.ttf'
        with TTFont(path) as font:
            if not all(ord(c) in font.getBestCmap() for c in 'Ada 2 klip'):raise ValueError('Glyph uji tidak lengkap')
        return {**result,'level':'sample','detail':'Font asli mesin terbaca dan glyph sampel lengkap'}
    if key=='opentimelineio':
        import opentimelineio as otio
        timeline=otio.schema.Timeline(name='Clipper stage 2');track=otio.schema.Track();timeline.tracks.append(track)
        track.append(otio.schema.Clip(name='Sampel',source_range=otio.opentime.TimeRange(otio.opentime.RationalTime(0,24),otio.opentime.RationalTime(24,24))))
        path=sample_dir/'timeline.otio';otio.adapters.write_to_file(timeline,str(path))
        if len(otio.adapters.read_from_file(str(path)).tracks[0])!=1:raise ValueError('Round-trip timeline gagal')
        return {**result,'level':'sample','detail':'Timeline 24 frame berhasil ditulis dan dibaca','artifacts':['sample/timeline.otio']}
    if key=='pycapcut':
        import pycapcut
        script=pycapcut.ScriptFile(320,180)
        script.add_track(pycapcut.TrackType.text)
        script.add_segment(pycapcut.TextSegment('Tahap 2',pycapcut.Timerange(0,1000000)))
        data=json.loads(script.dumps())
        if not data.get('tracks'):raise ValueError('Draft tidak mempunyai track teks')
        path=sample_dir/'draft_content.json';path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        return {**result,'level':'sample','detail':'Draft dengan track teks terpisah berhasil dibuat; ini bukan bukti impor native','artifacts':['sample/draft_content.json']}
    if not sample:return result
    import numpy as np
    if key in ('faster-whisper','stable-ts','whisperx','silero-vad','pyannote','auto-editor'):
        audio,values=excerpt(request,sample_dir)
        if key=='faster-whisper':
            from faster_whisper import WhisperModel
            model=WhisperModel(str(weights),device=device,compute_type='int8' if device=='cpu' else 'int8_float16',num_workers=1)
            segments,info=model.transcribe(str(audio),word_timestamps=True,vad_filter=True,beam_size=1)
            segments=list(segments);words=[dict(word=w.word,start=float(w.start),end=float(w.end)) for seg in segments for w in seg.words or []]
            payload={'language':info.language,'text':' '.join(s.text for s in segments),'words':words}
        elif key=='stable-ts':
            import stable_whisper
            model=stable_whisper.load_faster_whisper(str(weights),device=device,compute_type='int8' if device=='cpu' else 'int8_float16')
            output=model.transcribe_stable(str(audio),word_timestamps=True)
            payload=output.to_dict()
        elif key=='whisperx':
            import whisperx
            model=whisperx.load_model(str(weights),device,compute_type='int8' if device=='cpu' else 'float16',vad_method='silero')
            payload=model.transcribe(values,batch_size=1)
            payload['scope']='Uji ASR; alignment bahasa dan diarisasi belum diuji'
        elif key=='silero-vad':
            import torch
            from silero_vad import load_silero_vad,get_speech_timestamps
            model=load_silero_vad(onnx=True)
            payload={'speech':get_speech_timestamps(torch.from_numpy(values),model,sampling_rate=16000,return_seconds=True)}
        elif key=='pyannote':
            import inspect
            import torch
            from pyannote.audio import Pipeline
            params=inspect.signature(Pipeline.from_pretrained).parameters
            kwargs={'cache_dir':str(directory/'hf-cache')}
            if 'token' in params:kwargs['token']=os.environ.get('HF_TOKEN')
            elif 'use_auth_token' in params:kwargs['use_auth_token']=os.environ.get('HF_TOKEN')
            pipeline=Pipeline.from_pretrained(str(weights/'config.yaml'),**kwargs)
            if pipeline is None:raise ValueError('Pipeline gated belum dapat dibuka; periksa persetujuan akun dan HF_TOKEN')
            pipeline.to(torch.device(device))
            output=pipeline({'waveform':torch.from_numpy(values).unsqueeze(0),'sample_rate':16000})
            annotation=getattr(output,'speaker_diarization',output)
            payload={'speakers':[dict(start=float(span.start),end=float(span.end),speaker=str(label)) for span,_,label in annotation.itertracks(yield_label=True)],'scope':'Diarisasi cuplikan 6 detik; kualitas video panjang belum diukur'}
        else:
            output=sample_dir/'auto-editor.mp4'
            command([sys.executable,'-m','auto_editor',str(audio),'--no-open','--export','premiere','--output',str(sample_dir/'auto-editor.xml')],timeout=240)
            payload={'output':'sample/auto-editor.xml','scope':'Keputusan potong audio dan timeline pembanding'}
        path=sample_dir/'result.json';path.write_text(json.dumps(payload,ensure_ascii=False,default=str),encoding='utf-8')
        return {**result,'level':'sample','detail':'Sampel audio diproses. Kualitas dan kecocokan cerita perlu ditinjau.','artifacts':['sample/result.json']}
    if key=='scenedetect':
        from scenedetect import detect,ContentDetector
        video=sample_dir/'scenes.mp4'
        command(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','color=c=black:s=320x180:r=24:d=1','-f','lavfi','-i','color=c=white:s=320x180:r=24:d=1','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-threads','1',video])
        scenes=detect(str(video),ContentDetector(threshold=20,min_scene_len=5))
        if len(scenes)<2:raise ValueError('Pergantian dua adegan sampel tidak terdeteksi')
        return {**result,'level':'sample','detail':'Pergantian adegan buatan terdeteksi','artifacts':['sample/scenes.mp4']}
    if key=='yunet':
        import cv2
        detector=cv2.FaceDetectorYN.create(str(weights/'yunet.onnx'),'',(320,180))
        _,faces=detector.detect(np.zeros((180,320,3),dtype=np.uint8))
        return {**result,'level':'sample','detail':'Inference YuNet berhasil; gambar kosong tidak mempunyai wajah. Video pengguna belum dinilai.'}
    if key=='rapidocr':
        from PIL import Image,ImageDraw,ImageFont
        from rapidocr_onnxruntime import RapidOCR
        image=Image.new('RGB',(480,160),'white');ImageDraw.Draw(image).text((25,40),'Clipper 2026',font=ImageFont.truetype(str(repo/'clipper/fonts/DejaVuSans.ttf'),48),fill='black')
        output,_=RapidOCR()(np.array(image));text=' '.join(str(row[1]) for row in output or [])
        if 'clipper' not in text.lower():raise ValueError('OCR tidak mengenali teks contoh: '+text)
        image.save(sample_dir/'ocr.png')
        return {**result,'level':'sample','detail':'Teks sampel terbaca: '+text,'artifacts':['sample/ocr.png']}
    if key=='mediapipe':
        sys.path.insert(0,str(repo))
        from clipper.visual_worker import run
        video=sample_dir/'segment-input.mp4'
        command(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','color=c=gray:s=320x180:r=1:d=1','-c:v','libx264','-threads','1',video])
        payload=run({'component':key,'directory':str(directory),'output_dir':str(sample_dir),'source':str(video),
                     'source_content_id':'synthetic-gray-segmentation-sample-v1','times':[0.],'max_width':320})
        if payload.get('status')!='ready' or len(payload.get('frames',[]))!=1:raise ValueError('Inference segmentasi sampel belum lengkap.')
        (sample_dir/'segmentation.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
        return {**result,'level':'sample','detail':'Inference CPU enam kelas dan mask valid pada frame abu-abu. Akurasi wajah/pakaian video pengguna belum dinilai.',
                'artifacts':['sample/segment-input.mp4','sample/segmentation.json',*[str(Path(p).relative_to(directory)).replace('\\','/') for p in payload['artifacts']]]}
    if key=='e5':
        from sentence_transformers import SentenceTransformer
        model=SentenceTransformer(str(weights),device=device,local_files_only=True)
        vectors=model.encode(['query: cerita video','passage: cerita video pendek'],normalize_embeddings=True)
        if vectors.shape[0]!=2 or not np.isfinite(vectors).all():raise ValueError('Embedding sampel tidak valid')
        return {**result,'level':'sample','detail':'Dua embedding lokal valid; dimensi '+str(vectors.shape[1])}
    if key in ('qwen3-vl','smolvlm','siglip2'):
        import torch
        from PIL import Image
        from transformers import AutoProcessor
        resolution=int(request.get('resolution',336));image=Image.new('RGB',(resolution,resolution),(150,30,20));processor=AutoProcessor.from_pretrained(str(weights),local_files_only=True,trust_remote_code=False)
        if key=='siglip2':
            from transformers import AutoModel
            model=AutoModel.from_pretrained(str(weights),local_files_only=True,trust_remote_code=False).to(device)
            inputs=processor(text=['a red square','a blue square'],images=image,return_tensors='pt',padding='max_length').to(device)
            with torch.inference_mode():output=model(**inputs)
            if not torch.isfinite(output.logits_per_image).all():raise ValueError('Logit gambar tidak valid')
            detail='Similarity gambar/teks berhasil dihitung'
        else:
            from transformers import AutoModelForImageTextToText
            model=AutoModelForImageTextToText.from_pretrained(str(weights),local_files_only=True,trust_remote_code=False,torch_dtype=torch.float32 if device=='cpu' else torch.float16).to(device)
            messages=[{'role':'user','content':[{'type':'image','image':image},{'type':'text','text':'Describe the color briefly.'}]}]
            prompt=processor.apply_chat_template(messages,add_generation_prompt=True)
            inputs=processor(text=prompt,images=[image],return_tensors='pt').to(device)
            with torch.inference_mode():output=model.generate(**inputs,max_new_tokens=12)
            detail=processor.batch_decode(output[:,inputs['input_ids'].shape[1]:],skip_special_tokens=True)[0]
            if not detail.strip():raise ValueError('Model gambar tidak menghasilkan teks')
        return {**result,'level':'sample','detail':'Inference lokal berhasil: '+detail[:180]}
    if key=='talknet':
        import torch
        sys.path.insert(0,str(source))
        from model.talkNetModel import talkNetModel
        from loss import lossAV
        model=talkNetModel().to(device).eval();head=lossAV().to(device).eval()
        state=torch.load(weights/'pretrain_TalkSet.model',map_location='cpu',weights_only=True)
        state={k.removeprefix('module.'):v for k,v in state.items()}
        model.load_state_dict({k.removeprefix('model.'):v for k,v in state.items() if k.startswith('model.')},strict=True)
        head.load_state_dict({k.removeprefix('lossAV.'):v for k,v in state.items() if k.startswith('lossAV.')},strict=True)
        torch.manual_seed(7)
        with torch.inference_mode():
            a=model.forward_audio_frontend(torch.zeros(1,100,13,device=device))
            v=model.forward_visual_frontend(torch.zeros(1,25,112,112,device=device))
            a,v=model.forward_cross_attention(a,v);features=model.forward_audio_visual_backend(a,v)
            scores=torch.softmax(head.FC(features),dim=-1)[:,1].cpu().tolist()
        if len(scores)!=25 or not all(math.isfinite(s) and 0<=s<=1 for s in scores):raise ValueError('Skor TalkNet tidak valid')
        (sample_dir/'talknet.json').write_text(json.dumps({'scores':scores,'scope':'Tensor buatan; bukan uji identitas pembicara pada video asli.'}),encoding='utf-8')
        return {**result,'level':'sample','detail':'Bobot dan adapter TalkNet menghasilkan 25 skor. Akurasi video belum diuji.','artifacts':['sample/talknet.json']}
    if key=='sam2':
        import torch
        from PIL import Image
        sys.path.insert(0,str(source))
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        checkpoint=next(weights.glob('*.pt'),None)
        if not checkpoint:raise ValueError('Checkpoint SAM 2.1 .pt belum tersedia')
        model=build_sam2('configs/sam2.1/sam2.1_hiera_t.yaml',str(checkpoint),device=device,apply_postprocessing=False)
        predictor=SAM2ImagePredictor(model);image=np.zeros((128,128,3),dtype=np.uint8);image[32:96,32:96]=(210,80,40)
        with torch.inference_mode():
            predictor.set_image(image);masks,scores,_=predictor.predict(point_coords=np.array([[64,64]]),point_labels=np.array([1]),multimask_output=False)
        if masks.shape[-2:]!=(128,128) or not np.isfinite(scores).all() or not masks.any():raise ValueError('Mask sampel SAM tidak valid')
        Image.fromarray((masks[0]*255).astype(np.uint8)).save(sample_dir/'sam-mask.png')
        return {**result,'level':'sample','detail':'Mask gambar dan prompt titik berhasil dibuat; CUDA extension/postprocessing tidak dipakai.','artifacts':['sample/sam-mask.png']}
    if key=='clipsai':
        import torch
        from sentence_transformers import SentenceTransformer
        import clipsai.clip.clipfinder as backend
        encoder=SentenceTransformer(str(weights),device=device)
        class LocalEmbedder:
            def embed_sentences(self,sentences):return torch.tensor(encoder.encode(sentences))
        backend.TextEmbedder=LocalEmbedder
        class Transcript:
            end_time=96
            def __init__(self):
                topics=['A camera needs good light to record a face.','Clear speech makes a video easier to understand.','Charts need enough space to show every number.']
                self.rows=[];self.chars=[]
                for i in range(24):
                    text=topics[i//8];a=len(self.chars);self.chars.extend(text+' ')
                    self.rows.append(dict(sentence=text,start_time=i*4,end_time=(i+1)*4,start_char=a,end_char=len(self.chars)))
            def get_sentence_info(self):return self.rows
            def get_char_info(self):return self.chars
        clips=backend.ClipFinder(device=device,min_clip_duration=20,max_clip_duration=120).find_clips(Transcript())
        payload={'clips':[dict(start=float(c.start_time),end=float(c.end_time)) for c in clips],
                 'scope':'ClipFinder dan bobot RoBERTa asli pada transkrip buatan; bukan penilaian hasil video pengguna.'}
        if not payload['clips'] or not all(0<=c['start']<c['end']<=96 for c in payload['clips']):raise ValueError('Kandidat ClipsAI tidak valid')
        (sample_dir/'clipsai.json').write_text(json.dumps(payload),encoding='utf-8')
        return {**result,'level':'sample','detail':'ClipFinder lokal menghasilkan '+str(len(clips))+' kandidat dari transkrip contoh.','artifacts':['sample/clipsai.json']}
    raise ValueError('Operasi sampel tidak tersedia untuk komponen ini')


def main():
    if len(sys.argv)!=3:raise SystemExit('probe.py request.json result.json')
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));start=time.monotonic()
    try:result=infer(request)
    except BaseException as exc:
        traceback.print_exc();result=dict(passed=False,level='sample' if request.get('sample') else 'import',device=request.get('device','cpu'),detail=str(exc)[-2000:],artifacts=[])
    for key,value in os.environ.items():
        if value and len(value)>=4 and any(word in key.upper() for word in ('TOKEN','KEY','PASSWORD','SECRET')):
            result['detail']=result.get('detail','').replace(value,'[disembunyikan]')
    result['duration_seconds']=round(time.monotonic()-start,3)
    Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,default=str,allow_nan=False),encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__=='__main__':sys.exit(main())
