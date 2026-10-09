"""Bounded image statistics and stable caption-area scoring.

Faces, hair and recognized source material are hard constraints. Clothing is
an eligible surface, scored for clutter, rather than a whole-person exclusion.
"""
import numpy as np
from PIL import Image

VERSION='text-area-4.0.9'


def grid(frame):
    rgb=np.asarray(Image.fromarray(frame[:,:,::-1]).resize((128,72),Image.Resampling.BOX),dtype=np.float32)/255
    grey=rgb[:,:,0]*.2126+rgb[:,:,1]*.7152+rgb[:,:,2]*.0722
    edges=np.zeros_like(grey);edges[:,1:]+=abs(np.diff(grey,axis=1));edges[1:,:]+=abs(np.diff(grey,axis=0))
    cells=lambda a:a.reshape(18,4,32,4).mean(axis=(1,3)).round(4).tolist()
    return {'version':VERSION,'source_size':[int(frame.shape[1]),int(frame.shape[0])],
            'luminance':cells(grey),'clutter':cells(np.clip(edges*4,0,1))}


def output_quality(shot,W,H):
    from .placement import mappings,project_box
    samples=shot.get('area_samples',[]);tiles=[]
    for sample in samples[:8]:
        sw,sh=sample['source_size'];grey=sample['luminance'];busy=sample['clutter']
        classes=sample.get('categories')
        for row in range(18):
            for col in range(32):
                source=[col*sw/32,row*sh/18,sw/32,sh/18]
                for region,transform in mappings(shot,W,H):
                    box=project_box(source,region,transform)
                    if box:
                        tiles.append({'box':box,'clutter':busy[row][col],'luminance':grey[row][col],
                                      'clothes':classes[row][col][4] if classes else 0.,'hair_face':sum(classes[row][col][i] for i in (1,3)) if classes else 0.})
    return tiles


def choose(boxes,W,H,preferred=None,quality=()):
    from .placement import overlap
    portrait=H>W;candidates=[]
    # Portrait reserves the right-hand controls and bottom platform caption.
    max_y=.84 if portrait else .96
    if preferred:candidates.append((list(preferred),'bottom' if portrait else 'left' if preferred[0]/W<.2 and preferred[2]/W<.6 else 'right' if preferred[0]/W>.4 else 'bottom'))
    for yf in ((.51,.40,.24,.09,.59) if portrait else (.54,.63,.36,.08)):
        candidates.append(([W*.07,H*yf,W*(.80 if portrait else .84),H*(.27 if portrait else .30)],'bottom'))
    if not portrait:
        for xf,pos in ((.055,'left'),(.535,'right')):
            for yf in (.26,.12,.43):candidates.append(([W*xf,H*yf,W*.40,H*.45],pos))
    for wf in ((.78,.65,.55) if portrait else (.65,.50,.40)):
        for hf in ((.24,.20,.16) if portrait else (.32,.26,.20)):
            for xf in (.055,max(.055,.88-wf)):
                for yf in (.51,.66,.67,.68,.34,.12):candidates.append(([W*xf,H*yf,W*wf,H*hf],'bottom' if portrait or wf>.6 else 'left' if xf<.3 else 'right'))
    if not portrait:
        candidates.extend(([W*.07,H*.675,W*.84,H*hf],'bottom') for hf in (.20,.24,.28))
    ranked=[]
    for index,(panel,pos) in enumerate(candidates):
        x,y,w,h=panel
        if min(w,h)<=0 or x<W*.035 or y<H*.035 or x+w>W*(.90 if portrait else .97) or y+h>H*max_y:continue
        envelope=[x-W*.012,y-H*.012,w+W*.024,h+H*.024]
        hits=sum(overlap(envelope,b['box']) for b in boxes)
        weights=[(overlap(panel,t['box']),t) for t in quality];total=sum(a for a,_ in weights)
        busy=sum(a*t['clutter'] for a,t in weights)/max(1,total)
        brightness=sum(a*t['luminance'] for a,t in weights)/max(1,total)
        semantic=sum(a*t.get('hair_face',0) for a,t in weights)/max(1,total)
        clothing=sum(a*t.get('clothes',0) for a,t in weights)/max(1,total)
        # Capacity is a readability constraint; an empty but tiny corner loses
        # to a sufficiently large, plain shirt with no protected overlap.
        capacity=min(1,w/(W*.72))*min(1,h/(H*.24))
        score=capacity*3.5-busy*1.5-brightness*.15-semantic*8+clothing*(1-busy)*.15-abs((y+h*.5)/H-(.65 if portrait else .70))*.8
        stable=preferred is not None and overlap(panel,preferred)>=min(w*h,preferred[2]*preferred[3])*.95
        if stable:score+=1.4
        ranked.append(((hits>0,hits/max(1,w*h),-score,index),panel,pos))
    if not ranked:raise ValueError('Tidak ada kandidat area teks di dalam margin aman.')
    score,panel,pos=min(ranked,key=lambda r:r[0]);return panel,pos,not score[0]
