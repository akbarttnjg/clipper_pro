"""Sampled scene boundaries and a locked composition for each shot.

No frame-by-frame face chasing, and no claim of audio active-speaker detection.
Small corner facecams and uncertain multi-person scenes preserve the full frame.
"""
import math
import cv2
import numpy as np
from . import crop
from .ffmpeg_util import even
from .typography import token


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


def material_panel(frame):
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
    cap = cv2.VideoCapture(str(media))
    W, H = info['width'], info['height']
    ratio = min(1., 640 / W)
    sw, sh = round(W * ratio), round(H * ratio)
    detector = crop._try_yunet(sw, sh)
    haar = None if detector is not None else cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
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
        else:
            found = haar.detectMultiScale(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), 1.15, 5, minSize=(22, 22))
            faces = [list(map(float, np.array(f) / ratio)) for f in found]
        faces.sort(key=lambda f: f[2] * f[3], reverse=True)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        area = [round(v / ratio) for v in active_area(small)]
        area[2], area[3] = min(area[2], W - area[0]), min(area[3], H - area[1])
        panel = material_panel(small)
        panel = [round(v/ratio) for v in panel] if panel else None
        return {'t': t, 'faces': faces, 'hist': hist, 'area': area, 'panel': panel}
    shots = []
    try:
        for span in plan['spans']:
            a, b = span['source_start'], min(span['source_end'], info['duration'])
            samples = [r for t in np.arange(a + .02, b, 1.5) if (r := sample(float(t))) is not None]
            if not samples:
                plan['warnings'].append('Adegan tidak terbaca; menggunakan framing tengah.')
                samples = [{'t': a, 'faces': [], 'area': [0, 0, W, H], 'hist': None}]
            groups, current = [], [samples[0]]
            boundaries = [a]
            for prior, item in zip(samples, samples[1:]):
                distance = cv2.compareHist(prior['hist'], item['hist'], cv2.HISTCMP_BHATTACHARYYA)
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
                    boundaries.append(hi)
                    groups.append(current)
                    current = []
                current.append(item)
            groups.append(current)
            boundaries.append(b)
            for i, group in enumerate(groups):
                left = round((boundaries[i] - a) * plan['fps'])
                right = round((boundaries[i + 1] - a) * plan['fps'])
                if right <= left:
                    continue
                area = list(map(int, np.median([r['area'] for r in group], axis=0)))
                area[2], area[3] = min(area[2], W - area[0]), min(area[3], H - area[1])
                faces = [r['faces'][0] for r in group if r['faces']]
                face = list(map(float, np.median(faces, axis=0))) if faces else None
                panels = [r['panel'] for r in group if r.get('panel')]
                material = region(cfg.material_rect, W, H)
                if material is None and len(panels) >= max(1, len(group)*.6):
                    material = list(map(int, np.median(panels, axis=0)))
                explicit_face = region(cfg.speaker_rect, W, H)
                separated = material and face and not (material[0] <= face[0]+face[2]/2 <= material[0]+material[2]
                    and material[1] <= face[1]+face[3]/2 <= material[1]+material[3])
                side_panel = material and max(material[0]-area[0], area[0]+area[2]-material[0]-material[2]) >= area[2]*.18
                multiple = sum(len(r['faces']) > 1 for r in group) > len(group) * .3
                small_face = face is not None and face[2] * face[3] / (area[2] * area[3]) < .012
                mode = cfg.layout
                if mode == 'auto':
                    mode = 'stream' if cfg.target_h > cfg.target_w and (separated or side_panel or material and explicit_face) else (
                        'fit' if material is not None or multiple or small_face or face is None else 'fill')
                if mode == 'split':
                    mode = 'fit'
                if mode == 'stream' and face is None and explicit_face is None and material is None:
                    mode = 'fit'
                rect = rectangle(area, face, cfg.target_w / cfg.target_h, cfg.framing_x) if mode == 'fill' else area
                face_rect = explicit_face or (speaker_panel(area, material, face, cfg.target_w/(cfg.target_h*(1-cfg.material_share)))
                    if material else rectangle(area, face, cfg.target_w/(cfg.target_h*(1-cfg.material_share))) if face else None)
                if mode == 'stream' and cfg.target_h > cfg.target_w:
                    rect = material or area
                start = (span['start_frame'] + left) / plan['fps']
                end = (span['start_frame'] + right) / plan['fps']
                pos = 'bottom'
                caption_panel = None
                if mode == 'stream' and cfg.target_h > cfg.target_w:
                    top = round(cfg.target_h*cfg.material_share)//2*2
                    shown_h = min(top, rect[3]*cfg.target_w/rect[2])
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
                keywords = {token(k) for k in plan['keywords']}
                emph = [w['start'] - start for w in plan['words'] if start + 2 <= w['start'] < end - 3 and token(w['word']) in keywords]
                zoom = emph[0] if cfg.punch_zoom and mode == 'fill' and end - start >= cfg.zoom_gap and emph else None
                shots.append({'source_start': a + left / plan['fps'], 'source_end': a + right / plan['fps'],
                    'start': start, 'end': end, 'start_frame': span['start_frame'] + left,
                    'duration_frames': right - left, 'rect': rect, 'mode': mode, 'position': pos,
                    'face': face, 'zoom_at': zoom, 'zoom_amount': cfg.zoom_amount,
                    'face_rect': face_rect, 'material_share': cfg.material_share, 'caption_panel': caption_panel})
                if mode == 'fit' and cfg.target_h > cfg.target_w:
                    plan['warnings'].append('Materi/tamu dipertahankan utuh. Periksa keterbacaan dalam format vertikal atau pilih 16:9.')
    finally:
        cap.release()
    plan['shots'] = shots
    plan['warnings'] = list(dict.fromkeys(plan['warnings']))
    plan['source'] = {'path': str(media), **info}
    return plan
