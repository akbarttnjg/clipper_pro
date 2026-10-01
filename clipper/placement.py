"""Sampled face/text protection and stable caption boxes in output coordinates.

The text detector finds stroke geometry on light or dark backgrounds; it does
not claim to read handwriting. Dense scenes get a separate caption band.
"""
import cv2
import numpy as np


def text_regions(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 7))
    dark = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    light = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
    strokes = cv2.max(dark, light)
    _, binary = cv2.threshold(strokes, 32, 255, cv2.THRESH_BINARY)
    joined = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 9), np.uint8))
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        density = np.mean(binary[y:y+bh, x:x+bw] > 0)
        if 3 <= bh <= h*.13 and bw >= max(12, bh*1.1) and .08 <= density <= .98:
            boxes.append([max(0, x-3), max(0, y-3), min(w-x+3, bw+6), min(h-y+3, bh+6)])
    return boxes


def _fit(rect, box, cover=False, top=False):
    x, y, w, h = rect
    bx, by, bw, bh = box
    scale = max(bw/w, bh/h) if cover else min(bw/w, bh/h)
    return [scale, bx+(bw-w*scale)/2-x*scale, by+(0 if top else (bh-h*scale)/2)-y*scale, box]


def mappings(shot, W, H):
    rect = shot['rect']
    if shot['mode'] == 'stream' and shot.get('face_rect'):
        if W > H:
            image_h = shot.get('image_height') or H
            side = round(W*.30)//2*2
            gap = max(2, round(W*.008)//2*2)
            return [(rect, _fit(rect, [side+gap, 0, W-side-gap, image_h])),
                    (shot['face_rect'], _fit(shot['face_rect'], [gap/2, 0, side, image_h]))]
        top_h = round(H*shot.get('material_share', .62))//2*2
        image_h = shot.get('material_image_height') or top_h
        mat = _fit(rect, [0, 0, W, image_h], top=bool(shot.get('caption_panel')))
        if not shot.get('caption_panel'):
            mat[2] += (top_h-image_h)/2
        return [(rect, mat), (shot['face_rect'], _fit(shot['face_rect'], [0, top_h, W, H-top_h]))]
    if shot['mode'] == 'fill':
        # rectangle() already matches the target aspect, allowing subpixel drift.
        return [(rect, _fit(rect, [0, 0, W, H], cover=True))]
    image_h = shot.get('image_height') or H
    return [(rect, _fit(rect, [0, 0, W, image_h]))]


def project_box(box, region, transform):
    x, y, w, h = box
    rx, ry, rw, rh = region
    left, top, right, bottom = max(x, rx), max(y, ry), min(x+w, rx+rw), min(y+h, ry+rh)
    if right <= left or bottom <= top:
        return None
    scale, dx, dy, viewport = transform
    vx, vy, vw, vh = viewport
    left, top = max(vx, left*scale+dx), max(vy, top*scale+dy)
    right, bottom = min(vx+vw, right*scale+dx), min(vy+vh, bottom*scale+dy)
    return [left, top, right-left, bottom-top] if right > left and bottom > top else None


def protected_boxes(shot, W, H):
    output = []
    for item in shot.get('protected_source', []):
        box = item['box']
        if item['kind'] == 'face':
            x, y, w, h = box
            box = [x-w*.25, y-h*.45, w*1.5, h*1.7]
        for region, transform in mappings(shot, W, H):
            projected = project_box(box, region, transform)
            if projected:
                output.append({'kind': item['kind'], 'box': projected})
    return output


def overlap(a, b):
    x, y, w, h = a
    bx, by, bw, bh = b
    return max(0, min(x+w, bx+bw)-max(x, bx)) * max(0, min(y+h, by+bh)-max(y, by))


def choose_panel(boxes, W, H, preferred=None):
    portrait = H > W
    # Platform UI margins are reserved before comparing available space.
    wide = W*.78 if portrait else W*.72
    tall = H*.22 if portrait else H*.24
    candidates = []
    if preferred:
        candidates.append((list(preferred), 'bottom'))
    if not portrait:
        for x, pos in ((W*.05, 'left'), (W*.55, 'right')):
            for y in (H*.20, H*.42, H*.06):
                candidates.append(([x, y, W*.40, H*.40], pos))
    for y in ((H*.56, H*.35, H*.10) if portrait else (H*.68, H*.08, H*.40)):
        candidates.append(([W*.07, y, wide, tall], 'bottom'))
    best = None
    for order, (panel, pos) in enumerate(candidates):
        # No detected face, text or material may intersect the animation envelope.
        x, y, w, h = panel
        envelope = [x-W*.012, y-H*.012, w+W*.024, h+H*.024]
        hits = sum(overlap(envelope, b['box']) for b in boxes)
        value = (hits > 0, hits/max(1, w*h), order)
        if best is None or value < best[0]:
            best = (value, panel, pos)
    return best[1], best[2], best[0][0] is False


def place_shot(shot, cfg):
    W, H = cfg.target_w, cfg.target_h
    if cfg.caption_position != 'auto' or not cfg.safe_placement:
        shot['placement'] = {'mode': 'manual' if cfg.caption_position != 'auto' else 'disabled'}
        return
    boxes = protected_boxes(shot, W, H)
    selected, pos, clear = choose_panel(boxes, W, H, shot.get('caption_panel'))
    if not clear:
        # Preserve the source in a separate image region. This also protects
        # missed text inside the material, instead of guessing between letters.
        if shot['mode'] == 'stream' and H > W and shot.get('face_rect'):
            top = round(H*shot.get('material_share', .62))//2*2
            shot['material_image_height'] = max(2, int((top-H*.23)//2*2))
            selected = [W*.08, top-H*.22, W*.78, H*.20]
        else:
            shot['image_height'] = int(H*(.60 if H > W else .73))//2*2
            if shot['mode'] == 'fill':
                shot['mode'] = 'fit'
            selected = [W*.08, H*(.625 if H > W else .755), W*.78, H*.215]
        shot['zoom_at'] = None
        shot['caption_panel'] = selected
        pos = 'bottom'
        boxes = protected_boxes(shot, W, H)
    else:
        # Output masks cover the sampled geometry. Suppress crop zoom when it
        # could move a protected region underneath a fixed caption block.
        if boxes:
            shot['zoom_at'] = None
    shot.update(caption_panel=selected, position=pos, protected_output=boxes,
                placement={'mode': 'empty_space' if clear else 'reserved_band',
                           'detector': 'sampled_faces_and_text_geometry', 'regions': len(boxes)})


def apply(plan, cfg):
    for shot in plan['shots']:
        place_shot(shot, cfg)
    plan['placement_summary'] = {
        'shots': len(plan['shots']),
        'empty_space': sum(s.get('placement', {}).get('mode') == 'empty_space' for s in plan['shots']),
        'reserved_band': sum(s.get('placement', {}).get('mode') == 'reserved_band' for s in plan['shots']),
        'note': 'Deteksi wajah dan pola tulisan pada frame sampel; gunakan area manual bila deteksi meleset.'}


def protect_broll(plan, cfg):
    """B-roll uses the shot's caption band; never cover its own subject with text.

    When an insert is present, reserve one consistent band for its entire shot.
    The renderer fits both the insert and source above it, preventing jumps.
    """
    if cfg.caption_position != 'auto' or not cfg.safe_placement:
        return
    W, H = cfg.target_w, cfg.target_h
    for shot in plan['shots']:
        touching = [e for e in plan.get('broll', []) if e['start'] < shot['end'] and e['end'] > shot['start']]
        if not touching:
            continue
        if shot['mode'] == 'stream' and H > W and shot.get('face_rect'):
            # A stock insert replaces the whole canvas; keep a common lower band.
            shot['mode'] = 'fit'
            shot['rect'] = [0, 0, plan['source']['width'], plan['source']['height']]
        shot['image_height'] = int(H*(.60 if H > W else .73))//2*2
        shot['mode'] = 'fit' if shot['mode'] == 'fill' else shot['mode']
        shot['zoom_at'] = None
        shot['caption_panel'] = [W*.08, H*(.625 if H > W else .755), W*.78, H*.215]
        shot['position'] = 'bottom'
        shot['placement'] = {'mode': 'reserved_band', 'reason': 'broll'}
        shot['protected_output'] = protected_boxes(shot, W, H)
        for event in touching:
            event['image_height'] = shot['image_height']


def caption_anchors(plan):
    return [{'time': (s['start']+s['end'])/2, 'start': s['start'], 'end': s['end'],
             'position': s['position'], 'panel': s.get('caption_panel'),
             'protected': s.get('protected_output', [])} for s in plan['shots']]
