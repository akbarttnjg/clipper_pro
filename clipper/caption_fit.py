"""Measure spoken phrases before choosing empty space or shrinking the image."""
from dataclasses import replace
import math


def required_height(phrases, cfg, width):
    from .style5 import caption_plan
    from .caption_director import readable
    needed=0.
    # Fixed geometry, no image evidence or nested placement decisions here.
    for phrase in phrases:
        if not phrase:continue
        anchor={'time':phrase[0]['start'],'start':phrase[0]['start']-.01,
                'end':phrase[-1]['end']+.3,'panel':[0.,0.,width,cfg.target_h*.90],
                'position':'bottom','protected':[]}
        plan=caption_plan(phrase,replace(cfg,caption_position='auto'),anchors=[anchor])
        if any(not readable(p['words'],cfg) for p in plan['phrases']):return None
        needed=max(needed,max((p['measured_height'] for p in plan['phrases']),default=0))
    return math.ceil(needed/.96+max(4.,cfg.target_h*.006)) if needed else None


def choose(phrases, cfg, boxes, preferred=None, quality=()):
    from .placement import overlap
    W,H=cfg.target_w,cfg.target_h;portrait=H>W
    gap=min(W,H)*.012
    left,top,right,bottom=W*.055,H*.05,W*(.885 if portrait else .95),H*(.835 if portrait else .95)
    best=None
    widths=[preferred[2]] if preferred else []
    widths += [W*r for r in ((.80,.65,.50) if portrait else (.84,.65,.50,.40))]
    for width in dict.fromkeys(round(v,3) for v in widths):
        try:height=required_height(phrases,cfg,width)
        except ValueError:continue
        if height is None or height>bottom-top or width>right-left:continue
        xs={left,right-width};ys={max(top,min(bottom-height,H*(.66 if portrait else .69)))}
        if preferred:xs.add(preferred[0]);ys.add(preferred[1])
        for item in boxes:
            x,y,w,h=item['box'];xs.update((x-width-gap,x+w+gap));ys.update((y-height-gap,y+h+gap))
        xs={max(left,min(right-width,x)) for x in xs};ys={max(top,min(bottom-height,y)) for y in ys}
        for x in sorted(xs):
            for y in sorted(ys):
                panel=[x,y,width,height]
                envelope=[x-gap,y-gap,width+gap*2,height+gap*2]
                if any(overlap(envelope,b['box'])>.5 for b in boxes):continue
                # Stable, wide, low-clutter surfaces outrank narrow corners.
                weighted=[(overlap(panel,t['box']),t) for t in quality]
                total=max(1.,sum(a for a,_ in weighted))
                clutter=sum(a*t['clutter'] for a,t in weighted)/total
                semantic=sum(a*t.get('hair_face',0) for a,t in weighted)/total
                stable=preferred is not None and abs(x-preferred[0])<1 and abs(y-preferred[1])<1
                score=width/W*2-clutter*1.5-semantic*8-abs((y+height*.5)/H-.72)+(1.4 if stable else 0)
                if best is None or score>best[0]:
                    pos='bottom' if portrait or width>W*.60 else 'left' if x<W*.3 else 'right'
                    best=(score,panel,pos)
    return (best[1],best[2],True) if best else None
