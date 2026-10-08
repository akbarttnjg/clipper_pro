"""Sampled scene boundaries and a locked composition for each shot.

No frame-by-frame face chasing, and no claim of audio active-speaker detection.
Small corner facecams and uncertain multi-person scenes preserve the full frame.
"""
import math
from pathlib import Path
import cv2
import numpy as np
from . import crop
from .ffmpeg_util import even
from .typography import token
from . import placement


def active_area(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    rows = np.mean(gray > 18, axis=1)
    cols = np.mean(gray > 18, axis=0)
    ys, xs = np.where(rows > .04)[0], np.where(cols > .04)[0]
    h, w = gray.shape
    if not len(xs) or not len(ys):
        return [0, 0, w, h]
    x, y = int(xs[0]), int(ys[0])
    aw, ah = int(xs[-1] - x + 1), int(ys[-1] - y + 1)
    if aw < w * .5 or ah < h * .5:
        return [0, 0, w, h]
    return [x, y, aw, ah]


def rectangle(area, face, aspect, focus=-1):
    ax, ay, aw, ah = area
    rw, rh = (ah * aspect, ah) if aw / ah > aspect else (aw, aw / aspect)
    cx = ax + aw * focus if focus >= 0 else (face[0] + face[2] / 2 if face else ax + aw / 2)
    # Leave headroom and keep upper body in view when horizontal footage is cropped.
    cy = face[1] + face[3] * 1.5 if face else ay + ah / 2
    rw, rh = min(aw, even(rw)), min(ah, even(rh))
    x = round(max(ax, min(cx - rw / 2, ax + aw - rw)))
    y = round(max(ay, min(cy - rh / 2, ay + ah - rh)))
    if face:
        # Face boxes exclude hair and can move down when someone reads a tablet.
        y = min(y, max(ay, round(face[1]-face[3]*.65)))
    return [x, y, int(rw), int(rh)]


def region(value, width, height):
    if not value:
        return None
    x, y, w, h = map(float, value.split(','))
    return [round(x*width/100), round(y*height/100), even(w*width/100), even(h*height/100)]


def material_panel(frame, faces=()):
    """Detect a large bright presentation panel. This is geometry, not OCR.

    Confidence gates avoid treating an entire bright room as a slide. Manual
    regions remain available for dark slides, screen recordings, and diagrams.
    """
    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 0, 180]), np.array([180, 95, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9,9), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x,y,w,h = cv2.boundingRect(contour)
        share = w*h/(width*height)
        coverage = cv2.contourArea(contour)/max(1,w*h)
        if .16 < share < .8 and w > width*.25 and h > height*.4 and coverage > .72:
            candidates.append((w*h, [x,y,w,h]))
    # Writing and a bottom gradient can split a whiteboard into many contours.
    # Projection recovers the panel only when there is a distinct darker side.
    bright = (hsv[:, :, 2] > 170) & (hsv[:, :, 1] < 95)
    columns = np.mean(bright, axis=0) > .43
    edges = np.diff(np.r_[False, columns, False].astype(int))
    for left, right in zip(np.where(edges == 1)[0], np.where(edges == -1)[0]):
        if not .27 * width < right-left < .81 * width:
            continue
        rows = np.where(np.mean(bright[:, left:right], axis=1) > .42)[0]
        if not len(rows) or rows[-1]-rows[0] < height*.45:
            continue
        top, bottom = int(rows[0]), int(rows[-1])+1
        side = bright[:, :left] if left > width-right else bright[:, right:]
        if side.size and np.mean(side) < .23 and np.mean(bright[top:bottom, left:right]) > .55:
            candidates.append(((right-left)*(bottom-top), [int(left), top, int(right-left), bottom-top]))
    def writing(rect):
        x,y,w,h=rect
        boxes=placement.text_regions(frame[y:y+h,x:x+w])
        cells={(min(3,int((bx+bw/2)/w*4)),min(3,int((by+bh/2)/h*4))) for bx,by,bw,bh in boxes}
        return len(boxes)>=4 and len(cells)>=3
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if w*h/(width*height)>.80 and cv2.contourArea(contour)/max(1,w*h)>.60 and writing([x,y,w,h]):
            candidates.append((w*h,[x,y,w,h]))
    neutral=cv2.inRange(hsv,np.array([0,0,140]),np.array([180,95,255]))
    neutral=cv2.morphologyEx(neutral,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
    for contour in cv2.findContours(neutral,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,w,h=cv2.boundingRect(contour)
        if not .045<w*h/(width*height)<.55 or cv2.contourArea(contour)/max(1,w*h)<.60: continue
        tile=hsv[y:y+h,x:x+w]
        ink=(tile[:,:,1]>110)&(tile[:,:,2]>100)&((tile[:,:,0]<12)|(tile[:,:,0]>165)|((tile[:,:,0]>35)&(tile[:,:,0]<95)))
        ys,xs=np.where(ink)
        if .002<np.mean(ink)<.16 and len(xs) and xs.max()-xs.min()>w*.25 and ys.max()-ys.min()>h*.2:
            candidates.append((w*h,[x,y,w,h]))
    candidates=[(area,rect) for area,rect in candidates if area>.65*width*height or
                not any(placement.overlap(rect,face)>=face[2]*face[3]*.2 for face in faces)]
    if len(candidates)>1:
        boxes=[r for _,r in candidates]
        x=min(r[0] for r in boxes);y=min(r[1] for r in boxes)
        w=max(r[0]+r[2] for r in boxes)-x;h=max(r[1]+r[3] for r in boxes)-y
        if w*h<width*height*.70 and not any(placement.overlap([x,y,w,h],face)>0 for face in faces):
            candidates.append((w*h,[x,y,w,h]))
    return max(candidates, default=(0, None), key=lambda r:r[0])[1]


def speaker_panel(area, material, face, aspect):
    ax,ay,aw,ah = area
    mx,my,mw,mh = material
    left, right = mx-ax, ax+aw-(mx+mw)
    # A separate region prevents the diagram from leaking into the face crop.
    if max(left,right) < aw*.14:
        return rectangle(area, face, aspect)
    side = [ax,ay,left,ah] if left >= right else [mx+mw,ay,right,ah]
    return rectangle(side, face, aspect)


def analyze(media, plan, cfg, info):
    from . import evidence
    from . import visual4
    source_evidence = evidence.load(cfg)
    automatic_placement = cfg.caption_position == 'auto' and cfg.safe_placement
    cap = cv2.VideoCapture(str(media))
    W, H = info['width'], info['height']
    ratio = min(1., 640 / W)
    sw, sh = round(W * ratio), round(H * ratio)
    managed=visual4.component_runtime('yunet',cfg) if cfg.visual_enabled else None
    detector=None
    if managed and (Path(managed['directory'])/'weights/yunet.onnx').is_file():
        try:detector=cv2.FaceDetectorYN.create(str(Path(managed['directory'])/'weights/yunet.onnx'),'',(sw,sh))
        except (cv2.error,RuntimeError):pass
    if detector is None and cfg.visual_enabled:
        if crop._YUNET_PATH.is_file():
            try:detector=cv2.FaceDetectorYN.create(str(crop._YUNET_PATH),'',(sw,sh))
            except (cv2.error,RuntimeError):pass
    elif detector is None:detector = crop._try_yunet(sw, sh)
    # Some OpenCV 5 wheels omit the old cascade API. Preserve the frame if
    # neither detector is available; explicit source regions still work.
    haar = None
    if detector is None and hasattr(cv2, 'CascadeClassifier'):
        haar = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    if detector is None and haar is None:
        plan['warnings'].append('Detektor wajah tidak tersedia; gunakan komposisi utuh atau tandai area pembicara.')
    def sample(t):
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0, t) * 1000)
        ok, frame = cap.read()
        if not ok:
            return None
        small = cv2.resize(frame, (sw, sh))
        if detector is not None:
            detector.setInputSize((sw, sh))
            _, found = detector.detect(small)
            faces = [] if found is None else [list(map(float, f[:4] / ratio)) for f in found if f[-1] >= .82]
            confidence={} if found is None else {str(list(map(float,f[:4]/ratio))):float(f[-1]) for f in found if f[-1]>=.82}
        elif haar is not None:
            found = haar.detectMultiScale(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), 1.15, 5, minSize=(22, 22))
            faces = [list(map(float, np.array(f) / ratio)) for f in found]
            confidence={str(f):.75 for f in faces} # Haar has no calibrated probability.
        else:
            faces = []
            confidence={}
        faces.sort(key=lambda f: f[2] * f[3], reverse=True)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        area = [round(v / ratio) for v in active_area(small)]
        area[2], area[3] = min(area[2], W - area[0]), min(area[3], H - area[1])
        panel = material_panel(small, [[v*ratio for v in face] for face in faces])
        panel = [round(v/ratio) for v in panel] if panel else None
        texts = [[round(v/ratio) for v in box] for box in placement.text_regions(small)]
        ocr=[r for frame in source_evidence.get('frames',[]) if abs(frame['time']-t)<.3 and frame['width']==W and frame['height']==H for r in frame['texts']]
        return {'t': t, 'faces': faces, 'hist': hist, 'area': area, 'panel': panel, 'texts': texts,'ocr':ocr,
                'face_confidence':confidence,'face_detector':'yunet' if detector is not None else 'haar_heuristic' if haar is not None else 'none'}
    shots = []
    try:
        rows,visual_summary=visual4.collect(media,plan,cfg,info,sample) if cfg.visual_enabled else ([],{})
        active=visual4.active_analysis(media,rows,cfg) if cfg.visual_enabled else {'status':'disabled'}
        plan['visual_summary']={**visual_summary,'active_speaker':{k:v for k,v in active.items() if k not in ('scores','artifacts')},'manual_controls':bool(cfg.visual_overrides)}
        for span in plan['spans']:
            a, b = span['source_start'], min(span['source_end'], info['duration'])
            samples = [r for r in rows if a<=r['t']<b] if cfg.visual_enabled else [r for t in np.arange(a + .02, b, 1.5) if (r := sample(float(t))) is not None]
            if not samples:
                plan['warnings'].append('Adegan tidak terbaca; menggunakan framing tengah.')
                samples = [{'t': a, 'faces': [], 'tracks':[], 'area': [0, 0, W, H], 'hist': None}]
            groups, current = [], [samples[0]]
            boundaries = [a]
            for prior, item in zip(samples, samples[1:]):
                distance = cv2.compareHist(prior['hist'], item['hist'], cv2.HISTCMP_BHATTACHARYYA) if prior['hist'] is not None and item['hist'] is not None else 0
                if distance > .53 and item['t'] - boundaries[-1] > 1.5:
                    # Locate the cut to ~2 frames instead of switching framing 1.5 seconds late.
                    lo, hi = prior['t'], item['t']
                    for _ in range(5):
                        mid = sample((lo + hi) / 2)
                        if mid is None:
                            break
                        if cv2.compareHist(prior['hist'], mid['hist'], cv2.HISTCMP_BHATTACHARYYA) > .40:
                            hi = mid['t']
                        else:
                            lo = mid['t']
                    if hi-a<.35 or b-hi<.35:
                        current.append(item)
                        continue
                    boundaries.append(hi)
                    groups.append(current)
                    current = []
                current.append(item)
            groups.append(current)
            boundaries.append(b)
            if cfg.visual_enabled:groups,boundaries=visual4.split_groups(groups,boundaries,cfg,active)
            for i, group in enumerate(groups):
                left = round((boundaries[i] - a) * plan['fps'])
                right = round((boundaries[i + 1] - a) * plan['fps'])
                if right <= left:
                    continue
                area = list(map(int, np.median([r['area'] for r in group], axis=0)))
                area[2], area[3] = min(area[2], W - area[0]), min(area[3], H - area[1])
                faces = [r['faces'][0] for r in group if r['faces']]
                face = list(map(float, np.median(faces, axis=0))) if faces else None
                visual=visual4.describe(media,group,cfg,info,active,allow_vlm=sum(s.get('visual',{}).get('vlm',{}).get('status') not in (None,'not_needed','budget_exhausted') for s in shots)<3,
                                       source_bounds=(boundaries[i],boundaries[i+1]),observation_key=visual_summary.get('key')) if cfg.visual_enabled else None
                selected=visual['speaker']['selected'] if visual else None
                if visual:face=selected['center_box'] if selected else None
                panels = [r['panel'] for r in group if r.get('panel')]
                material = region(cfg.material_rect, W, H)
                if material is None and len(panels) >= max(1, len(group)*.6):
                    material = list(map(int, np.median(panels, axis=0)))
                explicit_face = region(cfg.speaker_rect, W, H)
                separated = material and face and not (material[0] <= face[0]+face[2]/2 <= material[0]+material[2]
                    and material[1] <= face[1]+face[3]/2 <= material[1]+material[3])
                side_panel = material and max(material[0]-area[0], area[0]+area[2]-material[0]-material[2]) >= area[2]*.18
                multiple = sum(len(r['faces']) > 1 for r in group) > len(group) * .3 and selected is None
                small_face = face is not None and face[2] * face[3] / (area[2] * area[3]) < .012
                mode = cfg.layout
                if mode == 'auto':
                    mode = 'stream' if (separated or side_panel or material and explicit_face) else (
                        'fit' if material is not None or multiple or small_face or face is None else 'fill')
                    if visual and visual['scene']['kind'] in ('unknown','chart','screen','graphic'):mode='fit'
                if mode == 'split':
                    mode = 'fit'
                if mode == 'stream' and face is None and explicit_face is None and material is None:
                    mode = 'fit'
                rect = rectangle(area, face, cfg.target_w / cfg.target_h, cfg.framing_x) if mode == 'fill' else area
                if visual:
                    for pin in visual['pins']:
                        if pin.get('kind','crop')=='crop':rect=[int(v)//2*2 for v in pin['box']];mode='fit'
                        elif pin.get('kind')=='speaker':
                            explicit_face=[int(v)//2*2 for v in pin['box']]
                            if not material:rect=explicit_face;mode='fit'
                        elif pin.get('kind')=='material':material=[int(v)//2*2 for v in pin['box']];mode='stream' if face or explicit_face else 'fit';rect=material
                face_rect = explicit_face or (speaker_panel(area, material, face, cfg.target_w/(cfg.target_h*(1-cfg.material_share)))
                    if material else rectangle(area, face, cfg.target_w/(cfg.target_h*(1-cfg.material_share))) if face else None)
                if mode == 'stream' and material:
                    rect = material
                    if cfg.target_w > cfg.target_h:
                        face_rect = explicit_face or speaker_panel(area, material, face, cfg.target_w*.30/(cfg.target_h*.82))
                start = (span['start_frame'] + left) / plan['fps']
                end = (span['start_frame'] + right) / plan['fps']
                pos = 'bottom'
                caption_panel = None
                image_height = None
                material_image_height = None
                material_share = cfg.material_share
                if mode == 'stream' and cfg.target_h > cfg.target_w:
                    if cfg.layout == 'auto' and automatic_placement and material:
                        natural_h = min(cfg.target_h*.52,rect[3]*cfg.target_w/rect[2])
                        material_share = max(.40,min(.72,natural_h/cfg.target_h+.19))
                        if not explicit_face:
                            face_rect = speaker_panel(area,material,face,cfg.target_w/(cfg.target_h*(1-material_share)))
                    top = round(cfg.target_h*material_share)//2*2
                    shown_h = min(top, rect[3]*cfg.target_w/rect[2])
                    gap = top-shown_h
                    if automatic_placement and gap <= cfg.target_h*.17:
                        material_image_height = even(top-cfg.target_h*.19)
                        shown_h = min(material_image_height, rect[3]*cfg.target_w/rect[2])
                        gap = top-shown_h
                    if gap > cfg.target_h*.17:
                        margin = cfg.target_h*.012
                        caption_panel = [cfg.target_w*.085, shown_h+margin, cfg.target_w*.78, gap-margin*2]
                if cfg.target_w > cfg.target_h and face is not None and mode != 'stream':
                    relx = (face[0] + face[2] / 2 - rect[0]) / rect[2]
                    if relx < .35:
                        pos = 'right'
                    elif relx > .65:
                        pos = 'left'
                if automatic_placement and cfg.target_w > cfg.target_h:
                    if material is not None and mode != 'fill':
                        # Reserve a caption strip instead of covering a face or a diagram.
                        image_height = even(cfg.target_h * .82)
                        caption_panel = [cfg.target_w*.08, cfg.target_h*.835,
                                         cfg.target_w*.84, cfg.target_h*.145]
                        pos = 'bottom'
                    elif face is not None:
                        from .typography import panel
                        caption_panel = list(panel(cfg, pos))
                keywords = {token(k) for k in plan['keywords']}
                emph = [w['start'] - start for w in plan['words'] if start + 2 <= w['start'] < end - 3 and token(w['word']) in keywords]
                zoom = emph[0] if cfg.punch_zoom and mode == 'fill' and end - start >= cfg.zoom_gap and emph else None
                shots.append({'source_start': a + left / plan['fps'], 'source_end': a + right / plan['fps'],
                    'start': start, 'end': end, 'start_frame': span['start_frame'] + left,
                    'duration_frames': right - left, 'rect': rect, 'mode': mode, 'position': pos,
                    'face': face, 'zoom_at': zoom, 'zoom_amount': cfg.zoom_amount,
                    'face_rect': face_rect, 'material_share': material_share, 'caption_panel': caption_panel,
                    'image_height': image_height, 'material_image_height': material_image_height, 'has_material': material is not None})
                if mode == 'fit' and cfg.target_h > cfg.target_w:
                    plan['warnings'].append('Materi/tamu dipertahankan utuh. Periksa keterbacaan dalam format vertikal atau pilih 16:9.')
                protected = [{'kind': 'face', 'box': f} for r in group for f in r['faces']]
                protected += [{'kind': 'text', 'box': box} for r in group for box in r.get('texts', [])]
                protected += [{'kind':'ocr','box':box} for box in evidence.protected_boxes(source_evidence,
                    a+left/plan['fps'],a+right/plan['fps'],W,H)]
                if material:
                    protected.append({'kind': 'material', 'box': material})
                if explicit_face:
                    protected.append({'kind': 'face', 'box': explicit_face})
                shots[-1]['protected_source'] = protected
                if visual:
                    shots[-1]['visual']=visual
                    shots[-1]['protected_source'] += [{'kind':'ocr','box':r['box'],'confidence':r['confidence'],'ocr_id':r['id']} for r in visual['ocr'] if r['text']]
                    shots[-1]['protected_source'] += [{'kind':'manual','box':r['box']} for r in visual['protected']]
                    if selected:
                        shots[-1]['protected_source'].append({'kind':'face','box':selected['box']})
                        # A fixed crop must include the whole sampled head trajectory.
                        if mode=='fill' and placement.overlap(rect,selected['box'])<selected['box'][2]*selected['box'][3]*.98:
                            shots[-1].update(rect=area,mode='fit',zoom_at=None)
                            shots[-1]['visual']['speaker']['reason']+='; lintasan melewati crop, gambar utuh dipertahankan'
                shots[-1]['composition_reason'] = ('Materi dan pembicara dipisah; ruang teks mengikuti rasio materi' if mode=='stream'
                    else 'Materi utuh, tanpa memangkas diagram' if material else 'Framing pembicara')
                if visual:shots[-1]['composition_reason']+=' · '+visual['scene']['reason']+' · '+visual['speaker']['reason']
    finally:
        cap.release()
    plan['shots'] = shots
    plan['warnings'] = list(dict.fromkeys(plan['warnings']))
    plan['source'] = {'path': str(media), **info}
    # Keep an established crop through minor detector noise. A cut resets track
    # identity, and explicit source pins always retain their requested geometry.
    previous=None
    for shot in shots:
        selected=shot.get('visual',{}).get('speaker',{}).get('selected')
        prior=previous.get('visual',{}).get('speaker',{}).get('selected') if previous else None
        if selected and prior and selected['track_id']==prior['track_id'] and shot['mode']==previous['mode']=='fill' and not shot.get('visual',{}).get('pins'):
            box=selected['box'];old=previous['rect']
            if visual4.iou(old,shot['rect'])>.85 and placement.overlap(old,box)>=box[2]*box[3]*.98:shot['rect']=old.copy()
        previous=shot
    placement.apply(plan, cfg)
    if cfg.visual_enabled:visual4.caption_envelopes(plan,cfg)
    return plan
