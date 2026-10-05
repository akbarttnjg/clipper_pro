"""Source-first illustrations and clearly labelled, editable schematic diagrams."""
import hashlib
import re
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape
from . import evidence


def still_video(image,target):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    pending=target.with_name(target.stem+'.partial.mp4')
    try:
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-loop','1','-i',str(image),'-t','3',
            '-vf','scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x11151b,setsar=1',
            '-r','25','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-threads','2',str(pending)],
            capture_output=True,check=True,timeout=45)
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)


def from_source(query,context,cfg,excluded=()):
    import cv2
    from .stock import terms
    data=evidence.load(cfg)
    source=Path(data.get('source',''))
    if not source.is_file():return None
    wanted=terms(query+' '+context)
    matches=[]
    for f in data.get('frames',[]):
        text=' '.join(r['text'] for r in f['texts'])
        shared=terms(text)&wanted
        # At least two terms avoids matching a slide by a generic single word.
        if len(shared)>=2:
            matches.append((len(shared),f,text))
    for _,f,text in sorted(matches,key=lambda x:x[0],reverse=True):
        key='source-'+hashlib.sha256(f"{data['key']}|{f['time']}".encode()).hexdigest()[:18]
        if key in excluded:continue
        folder=Path(cfg.work_dir)/'source-assets';folder.mkdir(parents=True,exist_ok=True)
        target=folder/(key+'.mp4')
        if not target.is_file():
            cap=cv2.VideoCapture(str(source))
            try:
                cap.set(cv2.CAP_PROP_POS_MSEC,f['time']*1000);ok,frame=cap.read()
            finally:cap.release()
            if not ok:continue
            image=folder/(key+'.png');cv2.imwrite(str(image),frame)
            still_video(image,target)
        return {'id':key,'provider':'source','path':str(target.resolve()),'title':text[:160],
            'tags':text,'author':'Materi dari sumber proyek','page_url':'','license_url':'',
            'attribution':f"Cuplikan materi sumber pada {f['time']:.2f} detik; hak mengikuti pemilik video sumber.",
            'origin':{'type':'source_frame','time':f['time'],'ocr':text,'evidence_key':data['key']},
            'relevance':{'basis':'source_ocr','evidence':text,'reason':'Istilah di materi sumber cocok dengan konteks','visual_verified':False}}
    return None


def diagram(query,context,cfg,excluded=()):
    from PIL import Image,ImageDraw
    from .typography import font
    text=(query+' '+context).casefold()
    pattern='drop base drop' if re.search(r'\bdrop\s+base[d]?\s+drop\b|\bdbd\b',text) else 'rally base rally' if re.search(r'\brally\s+base[d]?\s+rally\b|\brbr\b',text) else None
    if not pattern:return None
    key='diagram-'+pattern.replace(' ','-')
    if key in excluded:return None
    folder=Path(cfg.work_dir)/'source-assets';folder.mkdir(parents=True,exist_ok=True)
    target=folder/(key+'.mp4');svg=folder/(key+'.svg');image=folder/(key+'.png')
    if not target.is_file() or not svg.is_file():
        labels=pattern.upper().split();down=labels[0]=='DROP'
        points=[(140,215 if down else 495),(465,365),(770,365),(1110,510 if down else 205)]
        im=Image.new('RGB',(1280,720),'#11151b');draw=ImageDraw.Draw(im)
        draw.text((72,45),pattern.upper(),font=font(cfg.fonts_dir,48,cfg.font_main),fill='#ffffff')
        draw.line(points,fill='#F6CF69',width=12)
        for label,(x,y) in zip(labels,[(250,540),(575,420),(915,540)]):
            draw.text((x,y),label,font=font(cfg.fonts_dir,34,cfg.font_main),fill='#ffffff')
        note='ILUSTRASI SKEMATIS — BUKAN DATA PASAR'
        draw.text((72,645),note,font=font(cfg.fonts_dir,25,cfg.font_main),fill='#a7b3c7')
        im.save(image)
        labels_svg=''.join(f'<text x="{x}" y="{y+32}" font-size="34">{escape(label)}</text>' for label,(x,y) in zip(labels,[(250,540),(575,420),(915,540)]))
        svg.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720"><rect width="1280" height="720" fill="#11151b"/><g fill="white" font-family="sans-serif"><text x="72" y="95" font-size="48">{escape(pattern.upper())}</text>{labels_svg}<text x="72" y="674" font-size="25">{escape(note)}</text></g><polyline points="'+ ' '.join(f'{x},{y}' for x,y in points)+'" fill="none" stroke="#F6CF69" stroke-width="12"/></svg>',encoding='utf-8')
        still_video(image,target)
    return {'id':key,'provider':'diagram','path':str(target.resolve()),'editable_path':str(svg.resolve()),
        'title':pattern.upper()+' · skematis','tags':pattern,'author':'Diagram lokal Clipper','page_url':'','license_url':'',
        'attribution':'Diagram skematis dibuat lokal; dapat diedit melalui SVG. Bukan data pasar atau hasil investasi.',
        'origin':{'type':'generated_diagram','template':pattern,'editable_format':'SVG','synthetic':True},
        'relevance':{'basis':'explicit_concept','reason':'Pola disebutkan dalam konteks sumber','evidence':pattern,'visual_verified':False}}
