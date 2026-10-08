"""Source-grounded explanation cards with an optional real Motion Canvas runner."""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def lines_for(text,cfg):
    from .typography import font
    for size in range(68,27,-1):
        face=font(cfg.fonts_dir,size,cfg.font_main);lines=[];line=''
        for word in text.split():
            candidate=(line+' '+word).strip()
            if line and face.getlength(candidate)>990:lines.append(line);line=word
            else:line=candidate
        if line:lines.append(line)
        if len(lines)<=3 and all(face.getlength(v)<=990 for v in lines):return lines,size
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


def make_asset(text,word_ids,cfg):
    from .font_catalog import FONTS
    from .typography import font
    from PIL import Image,ImageDraw
    lines,size=lines_for(text,cfg);face_path=Path(cfg.fonts_dir)/FONTS[cfg.font_main]['file']
    key=hashlib.sha256(json.dumps([text,word_ids,face_path.read_bytes().hex(),'explanation5-request-root-v2'],ensure_ascii=False).encode()).hexdigest()[:24]
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
        draw.rounded_rectangle((80,160,1200,560),radius=24,fill='#1d2937')
        draw.text((640,207),'DARI UCAPAN SUMBER',font=font(cfg.fonts_dir,25,cfg.font_main),anchor='mm',fill='#a7b3c7')
        draw.multiline_text((640,360),'\n'.join(lines),font=font(cfg.fonts_dir,size,cfg.font_main),anchor='mm',align='center',spacing=12,fill='#F6CF69')
        draw.text((640,509),'KUTIPAN · TANPA DATA TAMBAHAN',font=font(cfg.fonts_dir,22,cfg.font_main),anchor='mm',fill='#a7b3c7')
        image=folder/'poster.png';im.save(image)
        from .source_assets import still_video
        still_video(image,target)
    return {'id':'explanation-'+key,'provider':'explanation','path':str(target.resolve()),'duration':3.,'width':1280,'height':720,
            'title':text,'author':'Kutipan sumber proyek','attribution':'Kartu berisi ucapan sumber; tanpa angka, fakta atau data grafik tambahan.',
            'page_url':'','license_url':'','editable_path':str(project.resolve()),
            'origin':{'type':'source_quote','quote':text,'source_word_ids':word_ids},'renderer':engine,'motion_canvas':motion,
            'relevance':{'basis':'verbatim_source_quote','reason':'Kutipan sama dengan frasa yang diucapkan.','visual_verified':False}}


def prepare(words,clip,cfg):
    if cfg.illustration_mode=='off' or cfg.source_kind=='board':return {'scenes':[],'notes':[]}
    from .typography import groups
    selected=[w for w in words if clip['start']<=w['start']<clip['end']];scenes=[];notes=[]
    for phrase in groups(selected,cfg):
        start=phrase[0]['start'];end=min(start+3.,clip['end']-6.)
        if start<clip['start']+4 or end-start<2 or scenes and start-scenes[-1]['source_start']<10:continue
        text=' '.join(w['word'] for w in phrase)
        if len(text)<12:continue
        ids=[wid for w in phrase for wid in w.get('word_ids',[]) if wid is not None]
        try:
            asset=make_asset(text,ids,cfg)
            scenes.append({'id':asset['id'],'source_start':start,'source_end':end,'asset_start':0.,'enabled':True,'asset':asset,
                           'query':text,'reason':'Kutipan sumber memperjelas frasa yang sedang dibahas.','source_quote':text,
                           'phrase_reference':{'word_ids':ids,'start':start,'end':phrase[-1]['end']}})
            if asset['motion_canvas']['status']!='rendered':notes.append('Kartu kutipan dirender lokal; Motion Canvas '+asset['motion_canvas']['status']+'.')
        except (OSError,ValueError,subprocess.SubprocessError) as exc:notes.append('Kartu penjelas dilewati: '+str(exc)[:180])
        if len(scenes)>=min(2,cfg.broll_max):break
    return {'scenes':scenes,'notes':notes}
