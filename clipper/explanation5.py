"""Source-grounded explanation cards with an optional real Motion Canvas runner."""
from __future__ import annotations
import base64
import hashlib
import json
import re
from html import escape
from pathlib import Path
import shutil
import subprocess

STRUCTURES_VERSION='explanation5-structured-v5-complete-block'


def lines_for(text,cfg,*,max_size=68,max_lines=3):
    from .typography import font
    for size in range(max_size,27,-1):
        face=font(cfg.fonts_dir,size,cfg.font_main);lines=[];line=''
        for word in text.split():
            candidate=(line+' '+word).strip()
            if line and face.getlength(candidate)>990:lines.append(line);line=word
            else:line=candidate
        if line:lines.append(line)
        if len(lines)<=max_lines and all(face.getlength(v)<=990 for v in lines):return lines,size
    raise ValueError('Kutipan terlalu panjang untuk kartu penjelas.')


def motion_runtime(cfg):
    from .runtime.state import runtime_root,safe_path,read
    from .caption_renderer import browser_path
    root=Path(cfg.visual_runtime_root) if cfg.visual_runtime_root else runtime_root()
    try:
        active=read(root/'components/motion-canvas/active.json',{}) or {}
        folder=safe_path(root/'generations',active['generation']);receipt=read(folder/'receipt.json',{}) or {}
        test=receipt.get('test',{});node=receipt.get('versions',{}).get('node') or shutil.which('node')
        browser=browser_path(folder,receipt)
        if not browser:
            from .caption_renderer import readiness
            browser=readiness(cfg).get('browser')
        if not receipt.get('installed') or not test.get('passed') or test.get('level') not in ('build','sample') or not node or not browser or not (folder/'node/node_modules/playwright-core/package.json').is_file():return None
        return {'folder':str(folder),'node':node,'browser':browser,'generation':active['generation']}
    except (OSError,KeyError,ValueError,TypeError):return None


def structures(words):
    """Only illustrate explicit contrasts or complete, short numbered lists.

    Labels retain the actual spoken connectors and words. Long clauses and
    ambiguous lists are skipped instead of being summarized by invented text.
    """
    sentences=[];current=[]
    for w in words:
        if current and w['start']-current[-1]['end']>1.2:
            sentences.append(current);current=[]
        current.append(w)
        if re.search(r'[.!?]$',w['word']):sentences.append(current);current=[]
    if current:sentences.append(current)
    for row in sentences:
        tokens=[re.sub(r'[^\w]','',w['word'].lower()) for w in row]
        if 'bukan' not in tokens:continue
        a=tokens.index('bukan')
        b=next((i for i in range(a+2,len(tokens)) if tokens[i] in ('tapi','tetapi','melainkan')),None)
        if b is None or b-a>7 or not 2<=len(row)-b<=7:continue
        selected=row[a:]
        yield {'kind':'contrast','labels':[' '.join(w['word'] for w in row[a:b]),' '.join(w['word'] for w in row[b:])],'words':selected}
    ordinals=('pertama','kedua','ketiga','keempat')
    for a,w in enumerate(words):
        if re.sub(r'[^\w]','',w['word'].lower())!='pertama':continue
        row=[]
        for v in words[a:]:
            if row and v['start']-row[-1]['end']>3:break
            # An explicit conclusion closes the list. A fixed word window
            # cannot establish completeness: a later fifth item matters.
            if row and re.search(r'[.!?]$',row[-1]['word']) and re.sub(r'[^\w]','',v['word'].lower()) in ('kesimpulannya','itulah','selesai'):
                break
            row.append(v)
        tokens=[re.sub(r'[^\w]','',v['word'].lower()) for v in row]
        if any(t in ('kelima','keenam','ketujuh','kedelapan','kesembilan','kesepuluh') for t in tokens):continue
        positions=[next((i for i,t in enumerate(tokens) if t==o),None) for o in ordinals]
        count=next((i for i,p in enumerate(positions) if p is None),4)
        if count<2 or any(p is not None for p in positions[count:]) or positions[:count]!=sorted(positions[:count]):continue
        prior=' '.join(v['word'].lower() for v in words[max(0,a-18):a])
        promised=re.search(r'\b(?:ada|berikut|terdapat)\s+(dua|tiga|empat|lima|[2-5])\s+(?:cara|langkah|alasan|hal|tips|prinsip)\b',prior)
        if promised and {'dua':2,'tiga':3,'empat':4,'lima':5}.get(promised[1],int(promised[1]) if promised[1].isdigit() else 0)!=count:continue
        labels=[];selected=[]
        for i,p in enumerate(positions[:count]):
            stop=positions[i+1] if i+1<count else len(row)
            clause=row[p:stop]
            ending=next((k+1 for k,v in enumerate(clause) if re.search(r'[.!?]$',v['word'])),len(clause))
            # Intermediate items must be complete short clauses. Do not drop
            # a caveat between an item and the next numbered marker.
            if ending!=len(clause):break
            clause=clause[:ending]
            if not 2<=len(clause)<=7:break
            labels.append(' '.join(v['word'] for v in clause));selected.extend(clause)
        if len(labels)==count:yield {'kind':'list','labels':labels,'words':selected}


def make_asset(text,word_ids,cfg,diagram=None):
    from .font_catalog import FONTS
    from .typography import font
    from PIL import Image,ImageDraw
    lines,size=lines_for(text,cfg);face_path=Path(cfg.fonts_dir)/FONTS[cfg.font_main]['file']
    key=hashlib.sha256(json.dumps([text,word_ids,diagram,cfg.accent_hex,face_path.read_bytes().hex(),STRUCTURES_VERSION],ensure_ascii=False).encode()).hexdigest()[:24]
    folder=Path(cfg.work_dir)/'explanations'/key;folder.mkdir(parents=True,exist_ok=True)
    runtime=motion_runtime(cfg)
    # The editable project is retained even when the optional renderer is absent.
    project=(Path(runtime['folder'])/'node/stage5-explanations'/key) if runtime else folder/'motion-canvas'
    project.mkdir(parents=True,exist_ok=True)
    template=Path(__file__).parent/'runtime/templates/motion5'
    for source in template.rglob('*'):
        if source.is_file():
            target=project/source.relative_to(template);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    data={'quote':text,'source_word_ids':word_ids,'lines':lines,'font_size':size,'duration':3.,'fps':25,
          'font_url':'data:font/ttf;base64,'+base64.b64encode(face_path.read_bytes()).decode('ascii')}
    labels=diagram['labels'] if diagram else [text]
    panels=[]
    for i,label in enumerate(labels):
        ls,sz=lines_for(label,cfg,max_size=58 if len(labels)==2 else 48 if len(labels)>1 else 68,max_lines=2 if diagram else 3)
        if diagram and diagram['kind']=='contrast':
            # Two vertical rows remain legible when the video is cropped for a
            # portrait insert. Position is part of the editable request.
            y=250+i*220;sz=min(sz,58)
        else:y=360+(i-(len(labels)-1)/2)*140;sz=min(sz,52 if len(labels)>1 else 68)
        panels.append({'lines':ls,'font_size':sz,'y':y,'height':170 if len(labels)==2 else 125})
    data.update(panels=panels,accent=cfg.accent_hex,diagram=diagram or {'kind':'quote','labels':labels})
    (project/'request.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    target=folder/'explanation.mp4';engine='pillow_ffmpeg';motion={'status':'unavailable','reason':'Motion Canvas memerlukan komponen lokal, browser, dan adapter frame.'}
    if runtime:
        frames=folder/'motion-frames';request=folder/'motion-request.json'
        request.write_text(json.dumps({**data,'frames':str(frames.resolve()),'browser':runtime['browser']}),encoding='utf-8')
        try:
            result=subprocess.run([runtime['node'],str(project/'run.cjs'),str(request.resolve())],cwd=project,capture_output=True,timeout=cfg.visual_backend_timeout)
            (folder/'motion.log').write_bytes(result.stdout+b'\n'+result.stderr)
            if result.returncode or len(list(frames.glob('*.png')))!=75:raise ValueError('Urutan frame Motion Canvas belum lengkap.')
            pending=target.with_suffix('.rendering.mp4')
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-framerate','25','-i',str(frames/'%06d.png'),'-frames:v','75',
                            '-c:v','libx264','-pix_fmt','yuv420p','-threads','2',str(pending)],capture_output=True,check=True,timeout=60)
            pending.replace(target);engine='motion-canvas';motion={'status':'rendered','generation':runtime['generation'],'frame_count':75}
        except (OSError,ValueError,subprocess.SubprocessError) as exc:motion={'status':'failed','reason':str(exc)[:300]}
    if engine!='motion-canvas':
        im=Image.new('RGB',(1280,720),'#11151b');draw=ImageDraw.Draw(im)
        for panel in panels:
            y=panel['y'];h=panel['height']
            draw.rounded_rectangle((80,y-h/2,1200,y+h/2),radius=24,fill='#1d2937')
            draw.multiline_text((640,y),'\n'.join(panel['lines']),font=font(cfg.fonts_dir,panel['font_size'],cfg.font_main),anchor='mm',align='center',spacing=8,fill=cfg.accent_hex)
        image=folder/'poster.png';im.save(image)
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-loop','1','-i',str(image),'-t','3',
                        '-vf','fps=25,fade=t=in:st=0:d=0.18,fade=t=out:st=2.82:d=0.18',
                        '-c:v','libx264','-threads','2','-pix_fmt','yuv420p',str(target)],capture_output=True,check=True,timeout=60)
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">','<rect width="1280" height="720" fill="#11151b"/>']
    for panel in panels:
        y=panel['y'];h=panel['height']
        svg.append(f'<rect x="80" y="{y-h/2}" width="1120" height="{h}" rx="24" fill="#1d2937"/>')
        for i,line in enumerate(panel['lines']):
            baseline=y+(i-(len(panel['lines'])-1)/2)*(panel['font_size']+8)+panel['font_size']*.34
            svg.append(f'<text x="640" y="{baseline}" text-anchor="middle" font-family="{escape(cfg.font_main)}" font-size="{panel["font_size"]}" fill="{cfg.accent_hex}">{escape(line)}</text>')
    svg.append('</svg>');editable=folder/'diagram.svg';editable.write_text('\n'.join(svg),encoding='utf-8')
    return {'id':'explanation-'+key,'provider':'explanation','path':str(target.resolve()),'duration':3.,'width':1280,'height':720,
            'title':text,'author':'Kutipan sumber proyek','attribution':'Kartu berisi ucapan sumber; tanpa angka, fakta atau data grafik tambahan.',
            'page_url':'','license_url':'','editable_path':str((editable if diagram else project).resolve()),
            'editable_svg_path':str(editable.resolve()),'motion_project_path':str(project.resolve()),
            'origin':{'type':'source_structure' if diagram else 'source_quote','quote':text,'source_word_ids':word_ids,'diagram':diagram},'renderer':engine,'motion_canvas':motion,
            'relevance':{'basis':'verbatim_source_quote','reason':'Kutipan sama dengan frasa yang diucapkan.','visual_verified':False}}


def prepare(words,clip,cfg):
    if cfg.illustration_mode=='off' or cfg.source_kind in ('board','screen','chart','graphic') or clip.get('intelligence',{}).get('broll')=='preserve_speaker':return {'scenes':[],'notes':[]}
    selected=[w for w in words if clip['start']<=w['start']<clip['end']];scenes=[];notes=[]
    for structure in structures(selected):
        phrase=structure['words'];start=phrase[-1]['end'];end=min(start+3.,clip['end']-6.)
        if start<clip['start']+4 or end-start<2 or scenes and start-scenes[-1]['source_start']<10:continue
        text=' '.join(w['word'] for w in phrase)
        if len(text)<12:continue
        ids=list(dict.fromkeys(wid for w in phrase for wid in w.get('word_ids',w.get('source_word_ids',[w.get('word_id')])) if wid is not None))
        try:
            asset=make_asset(text,ids,cfg,{k:v for k,v in structure.items() if k!='words'})
            scenes.append({'id':asset['id'],'source_start':start,'source_end':end,'asset_start':0.,'enabled':True,'asset':asset,
                           'query':text,'reason':'Diagram mempertahankan perbandingan atau urutan yang telah diucapkan.','source_quote':text,
                           'phrase_reference':{'word_ids':ids,'start':phrase[0]['start'],'end':phrase[-1]['end']}})
            if asset['motion_canvas']['status']!='rendered':notes.append('Kartu kutipan dirender lokal; Motion Canvas '+asset['motion_canvas']['status']+'.')
        except (OSError,ValueError,subprocess.SubprocessError) as exc:notes.append('Kartu penjelas dilewati: '+str(exc)[:180])
        if len(scenes)>=min(2,cfg.broll_max):break
    if not scenes:notes.append('Tidak ada perbandingan atau daftar singkat yang cukup jelas untuk dibuat menjadi diagram.')
    return {'scenes':scenes,'notes':notes}
