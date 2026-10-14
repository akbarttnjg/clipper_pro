"""Measured source shots and local visual evidence; never guesses voice identity."""
import copy
import hashlib
import math
from pathlib import Path
import re
import subprocess
import time
from PIL import Image
import numpy as np
from . import camera4_contract as c
from .contracts import fingerprint
from .dependency_cache import content_id
from .storage import read_json,write_json


def backend(key,request,cfg,folder):
    from .visual4 import backend as native,component_runtime
    from .dependency_cache import model_identity
    runtime=component_runtime(key,cfg);weights=Path(runtime['directory'])/'weights' if runtime else None
    before=fingerprint(model_identity(weights,fresh=True)) if weights else None
    result=native(key,{**request,'m4_weights_digest':before},cfg,folder)
    if weights and fingerprint(model_identity(weights,fresh=True))!=before:raise ValueError('Bobot model visual berubah saat proses berjalan')
    if result.get('status')=='ready':result.setdefault('provenance',{})['weights_digest']=before
    return result


def scene_cuts(source,a,b,threshold,progress=lambda *_:None):
    command=['ffmpeg','-nostdin','-v','info','-ss',str(a),'-t',str(b-a),'-i',str(source),
        '-an','-progress','pipe:2','-stats_period','0.5','-vf',f'scale=320:-2,select=gte(scene\\,{threshold}),showinfo','-threads','1','-f','null','-']
    process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    cuts=[];tail=[]
    try:
        for line in process.stderr:
            tail.append(line);tail=tail[-12:]
            match=re.search(r'pts_time:([0-9.e+\-]+)',line)
            if match:
                t=a+float(match[1])
                if a+.03<t<b-.03:cuts.append(t)
                if len(cuts)>1000:raise ValueError('Terlalu banyak cut; pilih rentang lebih pendek')
                progress(5,'Memisahkan cut kamera dalam waktu sumber')
            if line.startswith('progress='):progress(5,'Memisahkan cut kamera dalam waktu sumber')
        if process.wait()!=0:raise ValueError('Scan shot FFmpeg gagal: '+''.join(tail)[-500:])
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=10)
    return sorted(set(round(t,6) for t in cuts))


def image_at(source,t,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);path=folder/(fingerprint([str(source),t])[:24]+'.png')
    begin=max(0,t-.35);delta=t-begin
    r=subprocess.run(['ffmpeg','-nostdin','-v','info','-y','-ss',str(begin),'-t',str(delta+.001),'-i',str(source),'-frames:v','1',
        '-vf',f'select=lte(t\\,{delta:.9f}),showinfo,reverse,scale=min(640\\,iw):-2','-threads','1',str(path)],capture_output=True,timeout=30)
    if r.returncode or not path.is_file():raise ValueError('Frame kamera tidak terbaca')
    measured=[float(v) for v in re.findall(rb'pts_time:([0-9.e+\-]+)',r.stderr)]
    if not measured:raise ValueError('Waktu frame belum terukur')
    write_json(path.with_suffix('.json'),{'requested_time':t,'time':begin+max(measured),'method':'last decoded frame at or before request'})
    with Image.open(path) as image:array=np.asarray(image.convert('RGB')).copy()
    return array,path


def detector(cfg):
    try:
        import cv2
        if not getattr(cv2,'__file__',None):return None,{'status':'unavailable','reason':'Native OpenCV belum tersedia'}
        from .visual4 import component_runtime
        runtime=component_runtime('yunet',cfg)
        path=Path(runtime['directory'])/'weights/yunet.onnx' if runtime else None
        if path and path.is_file():
            return ('yunet',cv2.FaceDetectorYN.create(str(path),'',(640,360))),{'status':'ready','provider':'yunet','runtime':runtime,'weights_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'probability_calibrated':False}
        if hasattr(cv2,'CascadeClassifier'):
            path=Path(cv2.data.haarcascades)/'haarcascade_frontalface_default.xml';model=cv2.CascadeClassifier(str(path))
            if not model.empty():return ('haar',model),{'status':'ready','provider':'haar_geometry','weights_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'probability_calibrated':False}
    except (ImportError,OSError,RuntimeError):pass
    return None,{'status':'unavailable','reason':'Detektor lokal belum siap; gunakan area manual atau frame utuh'}


def face_rows(array,model,width,height):
    if model is None:return []
    import cv2
    H,W=array.shape[:2];sx,sy=width/W,height/H
    if model[0]=='yunet':
        model[1].setInputSize((W,H));_,found=model[1].detect(cv2.cvtColor(array,cv2.COLOR_RGB2BGR))
        boxes=[] if found is None else [r[:4] for r in found if r[-1]>=.82]
    else:boxes=model[1].detectMultiScale(cv2.cvtColor(array,cv2.COLOR_RGB2GRAY),1.15,5,minSize=(22,22))
    result=[]
    for b in boxes:
        x,y,w,h=[float(v*s) for v,s in zip(b,(sx,sy,sx,sy))]
        x,y=max(0,x),max(0,y);w,h=min(w,width-x),min(h,height-y)
        if min(w,h)>0:result.append({'box':[x,y,w,h],'confidence':None,'descriptor':descriptor(array,b),'time':None})
    return result


def descriptor(image,b):
    x,y,w,h=map(int,b);tile=image[max(0,y):max(0,y)+h,max(0,x):max(0,x)+w]
    if not tile.size:return None
    # Appearance supports geometric association; this is not biometric identity.
    return np.histogram(tile,bins=12,range=(0,256),density=True)[0].tolist()


def associate(rows):
    tracks={};next_id=1
    for row in rows:
        if row.get('cut'):tracks={}
        candidates={k:v for k,v in tracks.items() if row['time']-v['time']<=1.5};used=set()
        for face in row['faces']:
            rankings=[]
            for ident,old in candidates.items():
                if ident in used:continue
                hit=c.intersection(face['box'],old['box']);iou=hit[2]*hit[3]/max(1,face['box'][2]*face['box'][3]+old['box'][2]*old['box'][3]-hit[2]*hit[3])
                desc=face.get('descriptor');prior=old.get('descriptor')
                distance=sum(abs(a-b) for a,b in zip(desc,prior)) if desc and prior else None
                if iou>=.18 and (distance is None or distance<=.05):rankings.append((iou,ident))
            rankings.sort(reverse=True)
            # Ambiguous crossings create a new proposal rather than swapping IDs.
            ambiguous=len(rankings)>1 and rankings[0][0]-rankings[1][0]<.15
            if rankings and not ambiguous:ident=rankings[0][1]
            else:ident='face-'+str(next_id).zfill(4);next_id+=1
            face.update(track_id=ident,time=row['time'],association='ambiguous_new_track' if ambiguous else 'geometry_and_appearance');used.add(ident);tracks[ident]=copy.deepcopy(face)
    return rows


def analyze(source,source_id,spans,settings,cfg,folder,progress=lambda *_:None):
    from .ffmpeg_util import probe
    info=probe(source);width,height=info['width'],info['height'];folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    model,receipt=detector(cfg) if settings['detect_faces'] else (None,{'status':'disabled'})
    identity=fingerprint([c.VERSION,content_id(source,fresh=True),spans,settings,cfg.visual_runtime_signature,receipt])
    cache=folder/(identity+'.json');cached=read_json(cache)
    if cache.exists() and not cached:raise ValueError('Cache kamera rusak; bukti lama tidak ditimpa')
    if cached:
        if cached.get('document_digest')!=fingerprint(cached.get('document')):raise ValueError('Cache kamera rusak; bukti lama tidak ditimpa')
        document=cached['document']
        if not all(Path(r['path']).is_file() and content_id(r['path'],fresh=True)==r['content_id'] for r in document['frames']):raise ValueError('Bukti frame cache berubah; bukti lama tidak ditimpa')
        return {**document,'cache_reused':True}
    folder=folder/identity[:32];folder.mkdir(parents=True,exist_ok=True)
    boundaries=[];shots=[]
    for a,b in spans:
        cuts=scene_cuts(source,a,b,settings['scene_threshold'],progress)
        points=[a,*cuts,b]
        for start,end in zip(points,points[1:]):
            if end-start<1/120:continue
            shots.append({'shot_id':'shot-'+fingerprint([source_id,start,end])[:24],'start':start,'end':end})
    if len(shots)>settings['frame_budget']//2:raise ValueError('Anggaran frame tidak cukup untuk dua sampel tiap shot; tingkatkan anggaran atau pendekkan klip')
    total=sum(b-a for a,b in spans);step=max(settings['interval_seconds'],total/max(1,settings['frame_budget']-len(shots)*2));rows=[]
    for shot in shots:
        times=[shot['start']+min(.02,(shot['end']-shot['start'])/4),shot['end']-min(.02,(shot['end']-shot['start'])/4)]
        times+=list(np.arange(shot['start']+step,shot['end']-.02,step))
        for t in sorted(set(times)):
            progress(15+int(35*len(rows)/max(1,settings['frame_budget'])),'Membaca frame dan area sumber')
            array,path=image_at(source,float(t),folder/'frames');faces=face_rows(array,model,width,height)
            actual_time=read_json(path.with_suffix('.json'))['time']
            rows.append({'time':actual_time,'requested_time':float(t),'shot_id':shot['shot_id'],'cut':len(rows)==0 or rows[-1]['shot_id']!=shot['shot_id'],
                'faces':faces,'path':str(path.resolve()),'content_id':content_id(path,fresh=True),'pixel_variance':float(array.var())})
    associate(rows);ocr={'status':'disabled'}
    for row in rows:
        for region in settings['regions']:
            if region['kind']=='subject' and region['start']<=row['time']<region['end']:
                manual=c.pixels(region['box'],width,height)
                row['faces']=[f for f in row['faces'] if c.intersection(f['box'],manual)[2]*c.intersection(f['box'],manual)[3]<f['box'][2]*f['box'][3]*.5]
                row['faces'].append({'box':manual,'track_id':region['id'],'time':row['time'],
                    'confidence':None,'descriptor':None,'association':'human_source_region'})
    if settings['ocr'] and rows:
        ocr=backend('rapidocr',{'source':str(source),'source_content_id':source_id,'times':[r['time'] for r in rows[::max(1,math.ceil(len(rows)/32))]]},cfg,folder/'ocr')
    for row in rows:row['ocr']=next((f.get('texts',[]) for f in ocr.get('frames',[]) if abs(f['time']-row['time'])<.001),[])
    document={'version':c.VERSION,'analysis_id':identity,'source_id':source_id,'media_content_id':content_id(source),'source_size':[width,height],
        'shots':shots,'frames':rows,'receipts':{'face_detector':receipt,'ocr':{k:v for k,v in ocr.items() if k!='frames'}},
        'coverage':{'shot_scan':'every_decoded_frame_scaled_320; FFmpeg scene metric','face_scan':'sampled','sample_count':len(rows),'frames_not_sampled_may_be_missed':True},
        'cache_reused':False,'g4':'real_corpus_pending'}
    write_json(cache,{'document':document,'document_digest':fingerprint(document)})
    return document
