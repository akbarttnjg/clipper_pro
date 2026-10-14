"""Bounded local object/planar measurements and continuous mask artifacts."""
import hashlib
import math
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image
from . import camera4_contract as c
from .dependency_cache import content_id
from .storage import write_json


def track(source,request,source_size,folder,progress=lambda *_:None,*,cuts=()):
    try:
        import cv2
        if not getattr(cv2,'__file__',None):raise ImportError()
    except ImportError:raise ValueError('Tracking objek/planar memerlukan OpenCV native; pengaturan lama tetap tersimpan')
    from .camera4_observe import image_at
    W,H=source_size;start,end=request['start'],request['end'];prompt=request['time'];region=c.pixels(request['box'],W,H)
    initial,_=image_at(source,prompt,Path(folder)/'tracking-frames');h,w=initial.shape[:2];sx,sy=w/W,h/H
    gray=cv2.cvtColor(initial,cv2.COLOR_RGB2GRAY);mask=np.zeros_like(gray);x,y,bw,bh=region
    mask[max(0,int(y*sy)):min(h,int((y+bh)*sy)),max(0,int(x*sx)):min(w,int((x+bw)*sx))]=255
    points=cv2.goodFeaturesToTrack(gray,maxCorners=100,qualityLevel=.03,minDistance=5,mask=mask)
    if points is None or len(points)<8:raise ValueError('Area tracking kurang fitur; jangan mengarang lintasan')
    corners=np.float32([[x*sx,y*sy],[(x+bw)*sx,y*sy],[(x+bw)*sx,(y+bh)*sy],[x*sx,(y+bh)*sy]])
    measurements=[{'time':prompt,'box':region,'corners':(corners/np.array([sx,sy])).tolist(),'inlier_fraction':1.,'status':'manual_anchor'}];failures=[]
    for direction in (1,-1):
        prior=gray;old=points.copy();origin=points.copy();prior_time=prompt
        times=np.arange(prompt+direction/8,end if direction==1 else start-1e-6,direction/8)
        for t in times:
            if not start<=t<end:continue
            if any(min(prior_time,t)<cut<=max(prior_time,t) for cut in cuts):failures.append({'time':float(t),'reason':'camera_cut'});break
            progress(65,'Mengukur lintasan objek/permukaan')
            image,_=image_at(source,float(t),Path(folder)/'tracking-frames');current=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY)
            newer,status,error=cv2.calcOpticalFlowPyrLK(prior,current,old,None,winSize=(21,21),maxLevel=3)
            if newer is None or status is None:failures.append({'time':float(t),'reason':'lost_optical_flow'});break
            back,back_status,_=cv2.calcOpticalFlowPyrLK(current,prior,newer,None,winSize=(21,21),maxLevel=3)
            if back is None or back_status is None:failures.append({'time':float(t),'reason':'lost_reverse_flow'});break
            valid=(status.reshape(-1)>0)&(back_status.reshape(-1)>0)&(np.max(abs(old-back).reshape(-1,2),axis=1)<1.5)
            if valid.sum()<8:failures.append({'time':float(t),'reason':'occlusion_or_drift'});break
            matched=newer[valid];anchors=origin[valid]
            if request['mode']=='planar':
                transform,inliers=cv2.findHomography(anchors,matched,cv2.RANSAC,3.)
            else:
                affine,inliers=cv2.estimateAffinePartial2D(anchors,matched,method=cv2.RANSAC,ransacReprojThreshold=3.)
                transform=np.vstack([affine,[0,0,1]]) if affine is not None else None
            fraction=float(inliers.mean()) if inliers is not None else 0.
            if transform is None or not np.isfinite(transform).all() or fraction<.65:failures.append({'time':float(t),'reason':'insufficient_inliers'});break
            moved=cv2.perspectiveTransform(corners.reshape(1,-1,2),transform)[0]/np.array([sx,sy]);left=moved.min(axis=0);right=moved.max(axis=0)
            area=float(np.prod(right-left)/(bw*bh))
            if min(left)<-1 or right[0]>W+1 or right[1]>H+1 or not .4<area<2.5:failures.append({'time':float(t),'reason':'out_of_frame_or_scale_drift'});break
            measurements.append({'time':float(t),'box':[float(left[0]),float(left[1]),float(right[0]-left[0]),float(right[1]-left[1])],
                'corners':moved.tolist(),'homography':transform.tolist(),'inlier_fraction':fraction,'status':'measured'})
            prior=current;old=matched;origin=anchors;prior_time=float(t)
    measurements.sort(key=lambda r:r['time'])
    return {'status':'partial' if failures else 'ready','mode':request['mode'],'source_content_id':content_id(source),
        'start':start,'end':end,'measurements':measurements,'failures':failures,'sample_fps':8,
        'scope':'source_geometry; explicit attachment required','drift_policy':'stop; never extrapolate across loss','provider':'OpenCV_LK_RANSAC','version':getattr(cv2,'__version__',None)}


def matte(result,source,request,source_size,folder):
    """Validate every propagated mask, then create a lossless full-rate carrier.

    The carrier is sample-held, not a claim of 30 fps neural inference.
    """
    if result.get('status')!='ready' or result.get('scope')!='selected_range_sampled':raise ValueError('Mask kontinu memerlukan propagasi rentang SAM, bukan poster frame')
    a,b=request['start'],request['end'];W,H=source_size;fps=30.;source_hash=content_id(source,fresh=True)
    if result.get('source_content_id')!=source_hash or [result.get('width'),result.get('height')]!=[W,H] or abs(result.get('start',-1)-a)>1e-6 or abs(result.get('end',-1)-b)>1e-6:raise ValueError('Identitas/rentang/geometri mask berbeda dari sumber')
    frames=result.get('frames',[]);sample_fps=result.get('fps')
    if type(sample_fps) not in (int,float) or not 1<=sample_fps<=30 or len(frames)!=math.ceil((b-a)*sample_fps):raise ValueError('Timeline mask belum mencakup seluruh rentang')
    checked=[];bounds=[]
    for index,row in enumerate(frames):
        if abs(row.get('time',-1)-(a+index/sample_fps))>1e-4:raise ValueError('Ada celah atau urutan salah pada timeline mask')
        path=Path(row['path'])
        with Image.open(path) as image:
            if image.size!=(W,H):raise ValueError('Ukuran mask tidak sesuai sumber')
            array=np.asarray(image.convert('L'));ys,xs=np.where(array>127)
            if len(xs):bounds.append([float(xs.min()),float(ys.min()),float(xs.max()-xs.min()+1),float(ys.max()-ys.min()+1)])
        checked.append({'time':row['time'],'path':str(path.resolve()),'content_id':content_id(path,fresh=True)})
    if not bounds:raise ValueError('Tidak ada foreground mask terukur')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);path=folder/'continuous-matte.nut';pending=folder/'continuous-matte.pending.nut'
    command=['ffmpeg','-nostdin','-v','error','-y','-f','rawvideo','-pix_fmt','gray','-s',str(W)+'x'+str(H),'-r',str(fps),'-i','-',
        '-c:v','ffv1','-level','3','-frames:v',str(round((b-a)*fps)),str(pending)]
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for index in range(round((b-a)*fps)):
            row=checked[min(len(checked)-1,int(index/fps*sample_fps))]
            with Image.open(row['path']) as image:process.stdin.write(image.convert('L').tobytes())
        process.stdin.close();error=process.stderr.read();code=process.wait(timeout=90)
        if code:raise ValueError('Carrier mask FFmpeg gagal: '+error.decode('utf-8','replace')[-500:])
        pending.replace(path)
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=10)
        pending.unlink(missing_ok=True)
    x=min(r[0] for r in bounds);y=min(r[1] for r in bounds);right=max(r[0]+r[2] for r in bounds);bottom=max(r[1]+r[3] for r in bounds)
    receipt={'status':'ready','path':str(path.resolve()),'content_id':content_id(path,fresh=True),'source_content_id':source_hash,
        'start':a,'end':b,'fps':fps,'frames':round((b-a)*fps),'width':W,'height':H,'model_samples':checked,'model_sample_fps':sample_fps,
        'interpolation':'nearest_sample_hold','protected_union':[x,y,right-x,bottom-y],'provenance':result.get('provenance'),
        'scope':'continuous_render_carrier; sampled_neural_masks; real_gesture_quality_not_measured'}
    write_json(folder/'matte-receipt.json',receipt);return receipt
