"""Pure geometry for locked speaker crops and conservative source protection."""
import math

VERSION = '4.0.8'
MATERIAL_KINDS = frozenset({'board', 'screen', 'chart', 'graphic'})


def overlap(a, b):
    return max(0., min(a[0]+a[2], b[0]+b[2])-max(a[0], b[0])) * max(0., min(a[1]+a[3], b[1]+b[3])-max(a[1], b[1]))


def union(a, b):
    x, y = min(a[0], b[0]), min(a[1], b[1])
    return [x, y, max(a[0]+a[2], b[0]+b[2])-x, max(a[1]+a[3], b[1]+b[3])-y]


def crop_rect(area, face, aspect, focus=-1):
    """A static crop with headroom, clamped to the sampled active source area."""
    ax, ay, aw, ah = area
    if not all(math.isfinite(float(v)) for v in (*area, aspect)) or min(aw, ah, aspect) <= 0:
        raise ValueError('Ukuran area/crop tidak valid.')
    rw, rh = (ah*aspect, ah) if aw/ah > aspect else (aw, aw/aspect)
    rw = min(aw, max(2, int(rw)//2*2)); rh = min(ah, max(2, int(rh)//2*2))
    cx = ax+aw*focus if focus >= 0 else face[0]+face[2]/2 if face else ax+aw/2
    cy = face[1]+face[3]*1.5 if face else ay+ah/2
    x = max(ax, min(cx-rw/2, ax+aw-rw))
    y = max(ay, min(cy-rh/2, ay+ah-rh))
    if face:
        y = min(y, max(ay, face[1]-face[3]*.65))
    # Chroma subsampling requires even crop extents; the origin stays in bounds.
    return [int(max(ax, min(round(x), ax+aw-rw))), int(max(ay, min(round(y), ay+ah-rh))), int(rw), int(rh)]


def compact_protected(items):
    """Union repeated detections without dropping any protected source pixels."""
    result = []
    for item in items:
        box = item.get('box', [])
        if len(box) != 4 or not all(math.isfinite(float(v)) for v in box) or min(box[2:]) <= 0:
            continue
        row = {**item, 'box':list(map(float, box))}
        match = None
        for old in result:
            if old['kind'] != row['kind']:continue
            # A region ID prevents different OCR phrases from becoming one area.
            if (old.get('ocr_id') or row.get('ocr_id')) and old.get('ocr_id') != row.get('ocr_id'):continue
            hit = overlap(old['box'], box)
            iou = hit / max(1., old['box'][2]*old['box'][3]+box[2]*box[3]-hit)
            if iou >= .55:
                match = old; break
        if match is None:
            result.append(row)
        else:
            match['box'] = union(match['box'], box)
            match['samples'] = match.get('samples', 1)+1
    return result


def geometry_is_protected(scene_kind, has_material):
    # Texture detections have no recognized text. In a verified speaker scene
    # they are diagnostics; OCR and explicit protected regions remain protected.
    return has_material or scene_kind not in ('speaker', 'podcast')


def zoom_keeps_heads(boxes, width, height, amount):
    factor = 1+amount
    for row in boxes:
        if row['kind'] != 'face':continue
        x, y, w, h = row['box']
        x = width/2+(x-width/2)*factor; y = height/2+(y-height/2)*factor
        if x < -.5 or y < -.5 or x+w*factor > width+.5 or y+h*factor > height+.5:
            return False
    return True
