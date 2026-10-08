"""Offline CPU inference inside an installed component's own Python environment.

No model downloads or remote code. Original upstream network definitions are
loaded from the source revision already installed by the component manager.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'


def frame_at(source,time):
    import cv2
    cap=cv2.VideoCapture(source)
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC,time*1000);ok,frame=cap.read()
        if not ok:raise ValueError('Frame sumber tidak terbaca')
        return frame
    finally:cap.release()


def run(request):
    key=request['component'];directory=Path(request['directory']);weights=directory/'weights';folder=Path(request['output_dir']);folder.mkdir(parents=True,exist_ok=True)
    if key=='rapidocr':
        from rapidocr_onnxruntime import RapidOCR
        import cv2
        engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1);rows=[]
        cap=cv2.VideoCapture(request['source'])
        try:
            for t in request['times']:
                cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=cap.read()
                if not ok:continue
                h,w=frame.shape[:2];scale=min(1.,1100/max(w,h));small=cv2.resize(frame,(round(w*scale),round(h*scale)))
                found,_=engine(small);texts=[]
                for poly,text,score in found or []:
                    if float(score)<.72 or not str(text).strip():continue
                    xs=[p[0]/scale for p in poly];ys=[p[1]/scale for p in poly]
                    x=max(0,min(xs));y=max(0,min(ys))
                    texts.append({'text':str(text)[:240],'confidence':float(score),'box':[x,y,min(w,max(xs))-x,min(h,max(ys))-y]})
                rows.append({'time':t,'texts':texts})
        finally:cap.release()
        return {'status':'ready','frames':rows,'device':'cpu'}
    if key in ('smolvlm','qwen3-vl'):
        import torch
        from PIL import Image
        import io
        from transformers import AutoProcessor,AutoModelForImageTextToText
        torch.set_num_threads(4)
        decoded=subprocess.run(['ffmpeg','-nostdin','-v','error','-ss',str(request['time']),'-i',request['source'],'-frames:v','1','-f','image2pipe','-vcodec','png','-'],capture_output=True,timeout=60)
        if decoded.returncode:raise ValueError('Frame model visual tidak terbaca')
        image=Image.open(io.BytesIO(decoded.stdout)).convert('RGB');w,h=image.size;image.thumbnail((640,640))
        processor=AutoProcessor.from_pretrained(str(weights),local_files_only=True,trust_remote_code=False)
        model=AutoModelForImageTextToText.from_pretrained(str(weights),local_files_only=True,trust_remote_code=False,torch_dtype=torch.float32).eval()
        prompt='Classify this video frame. Return ONLY JSON: {"kind":"speaker|podcast|board|screen|chart|graphic|unknown", "confidence":0.0, "reason":"brief visible evidence"}. Do not infer names or speech. Use unknown if unclear.'
        messages=[{'role':'user','content':[{'type':'image','image':image},{'type':'text','text':prompt}]}]
        text=processor.apply_chat_template(messages,add_generation_prompt=True)
        inputs=processor(text=text,images=[image],return_tensors='pt')
        with torch.inference_mode():output=model.generate(**inputs,max_new_tokens=160,do_sample=False)
        answer=processor.batch_decode(output[:,inputs['input_ids'].shape[1]:],skip_special_tokens=True)[0]
        a=answer.find('{');b=answer.rfind('}')
        if a<0 or b<a:raise ValueError('Model visual tidak menghasilkan JSON keputusan')
        decision=json.loads(answer[a:b+1]);confidence=float(decision.get('confidence',0))
        if decision.get('kind') not in ('speaker','podcast','board','screen','chart','graphic','unknown') or not math.isfinite(confidence) or not 0<=confidence<=1:raise ValueError('Keputusan model visual tidak valid')
        return {'status':'ready','decision':{**decision,'confidence':confidence},'source_frame':{'time':request['time'],'width':w,'height':h},'device':'cpu'}
    if key=='talknet':return talknet(request,directory,folder)
    if key=='sam2':
        import torch
        import numpy as np
        from PIL import Image
        import cv2
        sys.path.insert(0,str(directory/'source'))
        from sam2.build_sam import build_sam2,build_sam2_video_predictor
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        torch.set_num_threads(4)
        checkpoint=next(weights.glob('*.pt'),None)
        if checkpoint is None:raise ValueError('Bobot SAM lokal belum ada')
        if request.get('span'):
            predictor=build_sam2_video_predictor('configs/sam2.1/sam2.1_hiera_t.yaml',str(checkpoint),device='cpu',apply_postprocessing=False)
            return sam_sequence(request,predictor,folder)
        frame=frame_at(request['source'],request['time']);h,w=frame.shape[:2]
        model=build_sam2('configs/sam2.1/sam2.1_hiera_t.yaml',str(checkpoint),device='cpu',apply_postprocessing=False)
        predictor=SAM2ImagePredictor(model)
        x,y,bw,bh=request['box']
        with torch.inference_mode():
            predictor.set_image(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            masks,scores,_=predictor.predict(box=np.array([x,y,x+bw,y+bh]),multimask_output=False)
        if not np.isfinite(scores).all() or not masks.any():raise ValueError('SAM tidak menghasilkan mask valid')
        name=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()[:24]
        path=folder/(name+'-mask.png');Image.fromarray((masks[0]*255).astype(np.uint8)).save(path)
        return {'status':'ready','artifacts':[str(path)],'mask':str(path),'score':float(scores[0]),'time':request['time'],'width':w,'height':h,
                'scope':'reference_frame_only','device':'cpu','note':'Mask frame acuan; belum mengikuti gerak objek sepanjang video'}
    raise ValueError('Backend visual tidak dikenal')


def sam_sequence(request,predictor,folder):
    """Bounded video propagation, with an explicit sampled mask timeline.

    Image paths are temporary. The original source is never altered, and masks
    stay in source coordinates. A sampled sequence is not a full-frame-rate matte.
    """
    import cv2
    import numpy as np
    import torch
    import tempfile
    from PIL import Image
    start,end=map(float,request['span'])
    if not 0<end-start<=6 or not start<=request['time']<end:raise ValueError('Rentang mask tidak valid')
    fps=5.;count=math.ceil((end-start)*fps)
    name=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()[:24]
    output=Path(folder)/('mask-sequence-'+name);output.mkdir(parents=True,exist_ok=True)
    entries={};times=[min(end-.001,start+i/fps) for i in range(count)]
    with tempfile.TemporaryDirectory(prefix='sam-frames-',dir=folder) as temporary:
        frames=Path(temporary);cap=cv2.VideoCapture(request['source'])
        try:
            for index,t in enumerate(times):
                cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=cap.read()
                if not ok:raise ValueError('Frame rentang SAM tidak terbaca')
                h,w=frame.shape[:2];scale=min(1,768/max(w,h))
                size=(round(w*scale),round(h*scale));small=cv2.resize(frame,size)
                if not cv2.imwrite(str(frames/f'{index:05d}.jpg'),small):raise ValueError('Frame sementara SAM gagal disimpan')
        finally:cap.release()
        prompt=min(range(count),key=lambda i:abs(times[i]-request['time']))
        x,y,bw,bh=request['box'];sx,sy=size[0]/w,size[1]/h
        box=np.array([x*sx,y*sy,(x+bw)*sx,(y+bh)*sy])
        with torch.inference_mode():
            state=predictor.init_state(video_path=str(frames),offload_video_to_cpu=True,offload_state_to_cpu=True)
            predictor.add_new_points_or_box(state,frame_idx=prompt,obj_id=1,box=box)
            for reverse in ([False,True] if prompt else [False]):
                for index,ids,logits in predictor.propagate_in_video(state,start_frame_idx=prompt,reverse=reverse):
                    if not 0<=index<count or 1 not in ids:continue
                    raw=logits[ids.index(1)].detach().cpu().numpy()
                    if not np.isfinite(raw).all():raise ValueError('Logit mask SAM tidak valid')
                    mask=cv2.resize((raw.reshape(size[1],size[0])>0).astype(np.uint8)*255,(w,h),interpolation=cv2.INTER_NEAREST)
                    path=output/f'{index:05d}.png';Image.fromarray(mask).save(path)
                    entries[index]={'time':times[index],'path':str(path),'foreground_fraction':float(np.mean(mask>0))}
        if len(entries)!=count or entries[prompt]['foreground_fraction']==0:raise ValueError('Propagasi mask SAM belum mencakup seluruh rentang')
    timeline=output/'timeline.json';payload={'source_content_id':request.get('source_content_id'),'start':start,'end':end,'width':w,'height':h,'fps':fps,
        'prompt_time':times[prompt],'frames':[entries[i] for i in range(count)],'scope':'selected_range_sampled','coordinate_space':'canonical_source_pixels'}
    timeline.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    return {'status':'ready',**payload,'mask':entries[prompt]['path'],'timeline':str(timeline),
        'artifacts':[str(timeline),*[entries[i]['path'] for i in range(count)]],'device':'cpu',
        'note':'Propagasi SAM pada rentang pilihan 5 fps; mask terpisah, belum matte 30 fps atau layer render/editor'}


def talknet(request,directory,folder):
    import cv2
    import numpy as np
    import torch
    import wave
    import python_speech_features
    sys.path.insert(0,str(directory/'source'))
    from model.talkNetModel import talkNetModel
    from loss import lossAV
    torch.set_num_threads(4)
    model=talkNetModel().eval();head=lossAV().eval()
    state=torch.load(directory/'weights/pretrain_TalkSet.model',map_location='cpu',weights_only=True)
    state={k.removeprefix('module.'):v for k,v in state.items()}
    model.load_state_dict({k.removeprefix('model.'):v for k,v in state.items() if k.startswith('model.')},strict=True)
    head.load_state_dict({k.removeprefix('lossAV.'):v for k,v in state.items() if k.startswith('lossAV.')},strict=True)
    scores=[];cap=cv2.VideoCapture(request['source']);coverage=[]
    try:
        for window_index,window in enumerate(request['windows']):
            start,end=window['start'],window['end'];duration=end-start
            audio=folder/f'talknet-{window_index}.wav'
            cmd=['ffmpeg','-nostdin','-v','error','-y','-ss',str(start),'-i',request['source'],'-t',str(duration),'-vn','-ac','1','-ar','16000',str(audio)]
            try:
                result=subprocess.run(cmd,capture_output=True,timeout=60)
                if result.returncode:raise ValueError('Audio tersinkron TalkNet tidak terbaca')
                with wave.open(str(audio)) as f:pcm=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2')
            finally:audio.unlink(missing_ok=True)
            features=python_speech_features.mfcc(pcm,16000,numcep=13,winlen=.025,winstep=.01)
            for track in window['tracks']:
                observations=track['observations'];faces=[];times=[]
                for t in np.arange(start,end,.04):
                    close=min(observations,key=lambda r:abs(r['time']-t))
                    if abs(close['time']-t)>.65:break
                    cap.set(cv2.CAP_PROP_POS_MSEC,float(t)*1000);ok,frame=cap.read()
                    if not ok:break
                    x,y,w,h=close['box'];cx=x+w/2;cy=y+h/2;s=max(w,h)*.75
                    padded=cv2.copyMakeBorder(frame,round(s),round(s),round(s),round(s),cv2.BORDER_CONSTANT,value=(110,110,110))
                    x0=round(cx-s)+round(s);y0=round(cy-s)+round(s);tile=padded[y0:y0+round(s*2),x0:x0+round(s*2)]
                    face=cv2.resize(cv2.cvtColor(tile,cv2.COLOR_BGR2GRAY),(224,224))[56:168,56:168]
                    faces.append(face);times.append(float(t))
                n=min(len(faces),len(features)//4)
                if n<25:continue
                with torch.inference_mode():
                    a=model.forward_audio_frontend(torch.from_numpy(features[:n*4]).float()[None])
                    v=model.forward_visual_frontend(torch.from_numpy(np.asarray(faces[:n])).float()[None])
                    a,v=model.forward_cross_attention(a,v);out=model.forward_audio_visual_backend(a,v)
                    probabilities=torch.softmax(head.FC(out),dim=-1)[:,1].cpu().numpy()
                scores.extend({'time':times[i],'track_id':track['track_id'],'score':float(p)} for i,p in enumerate(probabilities))
            coverage.append({'start':start,'end':end})
    finally:cap.release()
    if not scores:raise ValueError('Tidak ada crop wajah dan audio tersinkron yang cukup untuk TalkNet')
    return {'status':'ready','scores':scores,'audio_windows':coverage,'fps':25,'audio_rate':16000,'device':'cpu',
            'note':'Skor inferensi audio visual; bukan verifikasi manusia atas identitas pembicara'}


if __name__=='__main__':
    try:
        request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));result=run(request)
    except Exception as exc:result={'status':'failed','error':str(exc)[-1200:]}
    Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    sys.exit(0 if result.get('status')=='ready' else 1)
