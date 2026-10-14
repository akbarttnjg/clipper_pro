"""Actual source previews and covers; atomic publication under the queue lease."""
import copy,json,subprocess
from dataclasses import replace
from pathlib import Path
from .finishing5_contract import TEMPLATES,number,text
from .contracts import fingerprint
from .dependency_cache import content_id
from .project_store import Conflict

def options(kind,values):
    if not isinstance(values,dict):raise ValueError('Opsi M5 harus objek')
    if kind=='gallery_m5':
        if set(values)-{'templates','seconds'}:raise ValueError('Opsi galeri tidak dikenal')
        ids=values.get('templates',[r['id'] for r in TEMPLATES])
        if not isinstance(ids,list) or not 1<=len(ids)<=6 or len(set(ids))!=len(ids) or set(ids)-{r['id'] for r in TEMPLATES}:raise ValueError('Pilih 1–6 template')
        return {'templates':ids,'seconds':number(values.get('seconds',5.),2,12,'Durasi galeri')}
    if set(values)-{'time','text','rect','color'}:raise ValueError('Opsi cover tidak dikenal')
    from .finishing5_contract import rect,HEX
    color=values.get('color','#FFFFFF')
    if not HEX.fullmatch(color):raise ValueError('Warna cover tidak valid')
    return {'time':number(values.get('time',0.),0,86400,'Waktu frame'),'text':text(values.get('text',''),160,'Teks cover'),'rect':rect(values.get('rect',[7,9,80,40])),'color':color}

def execute(service,job):
    from .studio_worker import StaleJob
    from .finishing5_assets import sha,font_info
    from .finishing5_service import assets
    from . import pipeline,media_context
    pid=job['project_id'];cid=job['target']['clip_id'];vid=job['target']['variant_id'];dependency=job['request']['dependency'];kind=job['kind'];opts=job['request']['options'];doc=copy.deepcopy(job['request']['snapshot']);cfg=service.config(doc,cid,vid)
    def check():
        active=service.queue.get(job['id']);current=service.store.get(pid)
        if active['status']!='running' or active['owner']!=job['owner'] or active['lease_token']!=job['lease_token']:raise StaleJob('M5 dibatalkan atau lease berubah')
        if service.dependency(current,cid,vid,kind=kind,fresh=True)!=dependency:raise StaleJob('Masukan M5 berubah; hasil lama dipertahankan')
        return current
    def progress(value,message):
        check();service.queue.update_owned(job,progress=max(0,min(99,round(value))),message=message)
    check();folder=service.work/pid/'finishing5'/job['id'];folder.mkdir(parents=True)
    if kind=='cover_m5':
        from PIL import Image,ImageDraw,ImageFont
        v=service.variant(doc,cid,vid);current=service.dependency(doc,cid,vid)
        rendered=next((r for r in (v.get('result'),v.get('preview')) if r and r.get('dependency')==current),None)
        if not rendered:raise ValueError('Buat preview/final revisi aktif sebelum memilih frame cover')
        from .artifact_store import verify
        if not verify(rendered,fresh=True):raise ValueError('Media cover berubah/tidak lengkap')
        t=opts['time'];path=rendered['absolute_file'];info=__import__('clipper.ffmpeg_util',fromlist=['probe']).probe(path)
        if t>=info['duration']:raise ValueError('Frame cover di luar hasil klip')
        import math,re
        target=folder/'cover.png';decoded=subprocess.run(['ffmpeg','-nostdin','-v','info','-y','-ss',str(t),'-copyts','-i',path,'-vf','showinfo','-frames:v','1',str(target)],capture_output=True,check=True)
        measured=re.search(r'pts_time:([0-9.]+)',decoded.stderr.decode('utf-8','replace'))
        if not measured:raise ValueError('Timestamp frame cover belum terukur')
        actual_time=float(measured.group(1))
        with Image.open(target) as im:
            im=im.convert('RGB');W,H=im.size;x,y,w,h=[opts['rect'][i]*(W if i%2==0 else H)/100 for i in range(4)];meta=font_info(cfg.fonts_dir,cfg.font_main);size=math.ceil(W/360*14/.53);f=ImageFont.truetype(str(Path(cfg.fonts_dir)/meta['file']),size)
            from .finishing5_assets import choose_font
            if opts['text']:
                choose_font(cfg.fonts_dir,cfg.font_main,[],opts['text'])
                lines=[];line=''
                for token in opts['text'].split():
                    candidate=(line+' '+token).strip()
                    if f.getlength(candidate)>w and line:lines.append(line);line=token
                    else:line=candidate
                if line:lines.append(line)
                line_h=size*1.25
                if any(f.getlength(s)>w for s in lines) or len(lines)*line_h>h:raise ValueError('Teks cover tidak muat; perbesar area atau gunakan teks lebih pendek')
                d=ImageDraw.Draw(im);d.rounded_rectangle((x-4,y-4,x+w+4,y+h+4),radius=8,fill='#101820')
                for index,line in enumerate(lines):d.text((x,y+index*line_h),line,font=f,fill=opts['color'])
            im.save(target)
        value=dict(path=str(target),sha256=sha(target),output_time=actual_time,requested_output_time=t,origin_output_digest=content_id(path,fresh=True),clip_id=cid,variant_id=vid,dependency=service.dependency(doc,cid,vid),options=opts,font_digest=meta['sha256']);field='cover'
    else:
        from .studio_exchange import render_words
        from .camera4_service import renderable
        from .editor_media import prepare
        media=media_context.prepare(doc['source']['path'],cfg,progress);source=media['payload']['working_path'];clip={k:copy.deepcopy(v) for k,v in doc['clips'][cid].items() if k!='variants'};v=service.variant(doc,cid,vid);transcript=service.transcript(doc,cid,vid);words=render_words(transcript,doc,clip,cfg)
        if transcript.get('m2_translation') and transcript['m2_translation']['display_mode']=='bilingual':clip['_m2_translation']=transcript['m2_translation']
        if v.get('timeline'):clip['manual_keep_spans']=v['timeline']['keep_spans']
        camera=renderable(service,doc,cid,vid)
        if camera:clip['_m4_camera']=camera
        clip['_broll_recipe']={'scenes':[],'notes':[]};factor=640/max(cfg.target_w,cfg.target_h);cfg=replace(cfg,target_w=max(64,round(cfg.target_w*factor/2)*2),target_h=max(64,round(cfg.target_h*factor/2)*2),preview_seconds=opts['seconds'],work_dir=str(folder),out_dir=str(folder/'outputs'),job_id='')
        source,words,clip,cfg,receipt=prepare(service,doc,cid,vid,source,words,clip,cfg,progress);items=[]
        for i,key in enumerate(opts['templates']):
            progress(5+i*85/len(opts['templates']),'Merender template '+key+' pada potongan video Anda')
            state=copy.deepcopy(cfg.finishing5);state['style']['template_id']=key;state['decorations']=[];local=replace(cfg,finishing5=state,caption_template_policy='manual',illustration_mode='off',broll_mode='off')
            result=pipeline.render_clip(source,words,clip,'gallery-'+key,local,lambda p,m:progress(5+(i+p/100)*85/len(opts['templates']),m),context_words=words)
            items.append(dict(template_id=key,absolute_file=result['absolute_file'],output_content_id=result['output_content_id'],plan_path=result['plan_path'],renderer=local.caption_renderer,artifact_manifest_path=result['artifact_manifest_path'],artifact_manifest_id=result['artifact_manifest_id']))
        value={'items':items,'dependency':service.dependency(doc,cid,vid),'source_id':doc['source']['source_id'],'input_revision':doc['revision'],'options':opts};field='gallery'
    result={field:value}
    for attempt in range(5):
        current=check()
        def publish(d):
            v=service.variant(d,cid,vid);v.setdefault('finishing5',{})[field]=value
        try:
            service.store.mutate(pid,current['revision'],job['id']+'-publish',{'dependency':dependency},publish,'M5 '+field+' tersimpan',job_guard={**job,'clip_id':cid,'variant_id':vid},job_result=result);return result
        except Conflict:
            if attempt==4:raise
