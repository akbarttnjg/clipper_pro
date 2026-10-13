"""Audio sources remain audio through ASR; only final rendering creates an audiogram."""
import copy
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from . import editplan,render,captions_pro,qc,ffmpeg_util,library_paths
from .contracts import fingerprint
from .dependency_cache import content_id
from .storage import read_json,write_json


def draw(source,plan,cfg,ass,target,mix,on_progress=None):
    w,h,fps=plan['width'],plan['height'],plan['fps'];target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    pending=target.with_name(target.stem+'.rendering.mp4');wave_w=round(w*.84)//2*2;wave_h=round(h*.19)//2*2
    graph=f'[1:a]showwaves=s={wave_w}x{wave_h}:mode=line:rate={fps}:colors={cfg.accent_hex.replace("#","0x")}[wave];[0:v][wave]overlay=(W-w)/2:H*0.22:shortest=1[base];[base]'
    graph+=(ffmpeg_util.ass_filter(ass,cfg) if ass else 'null')+'[out]'
    script=target.with_suffix('.filter.txt');script.write_text(graph,encoding='utf-8');codec=cfg.video_codec
    if cfg.use_nvenc and not cfg.allow_backend_fallback and codec!='h264_nvenc':raise ValueError('NVENC diwajibkan tetapi belum tersedia')
    command=['ffmpeg','-v','warning','-y','-f','lavfi','-i',f'color=c=0x11151b:s={w}x{h}:r={fps}:d={plan["duration"]}',
        '-i',str(mix),'-filter_complex_threads','1',*ffmpeg_util.filter_file_args(script),'-map','[out]','-map','1:a',
        '-t',str(plan['duration']),'-r',str(fps),'-c:v',codec,*ffmpeg_util.encoder_args(codec),'-threads','4','-pix_fmt','yuv420p',
        '-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart',str(pending)]
    try:
        actual,warnings=ffmpeg_util.encode(command,codec,target.with_suffix('.render.log'),on_progress,plan['duration'],allow_fallback=cfg.allow_backend_fallback)
        pending.replace(target)
    finally:pending.unlink(missing_ok=True)
    plan['encoder']=actual;plan['warnings'].extend(warnings);return str(target)


def render_clip(source,words,clip,name,cfg,on_progress=lambda p,m:None):
    started=time.monotonic();info=ffmpeg_util.probe(source)
    if not info['has_audio'] or not 0<=clip['start']<clip['end']<=info['duration']+.01:raise ValueError('Batas klip audio tidak valid')
    # VAD reports pauses. Audio clipping preserves them unless operator supplies explicit spans.
    plan=editplan.build(words,clip,replace(cfg,trim_silence=False,cold_open=False));plan.update(source_kind='audio',source={'path':str(source),'kind':'audio'},
        visual_summary={'status':'not_applicable','face_detection':'not_applicable','reason':'audio_only_source'},
        selected_alignment={'status':'not_run','reason':'source_timestamp_preserved; request alignment explicitly'})
    plan['shots']=[{**s,'mode':'audiogram','rect':[0,0,cfg.target_w,cfg.target_h],'zoom_at':None,'image_height':cfg.target_h,
        'composition_reason':'actual_audio_waveform; no_face_detection'} for s in plan['spans']]
    if clip.get('_editor_clock'):plan['editor']={'schema_version':1,'clock':clip['_editor_clock'],'tracks':clip['_editor_tracks'],
        'original_source':clip['_editor_source'],'original_bounds':clip['_editor_original_bounds'],'advanced_source_layer':'baked'}
    locations=library_paths.destinations(cfg,name);video_base,text_base,report_base=locations['video'],locations['text'],locations['report'];work=Path(cfg.work_dir)/'renders'/name;work.mkdir(parents=True,exist_ok=True)
    ass=captions_pro.write_ass(plan['words'],work/'captions.ass',cfg,keywords=clip.get('keywords',[]));plan['captions']=read_json(Path(ass).with_suffix('.caption-plan.json'))
    if clip.get('_m2_translation'):
        from . import bilingual_m2
        translated=bilingual_m2.translation_words(clip['_m2_translation'],plan,clip);plan['captions']=bilingual_m2.make_plan(plan['words'],translated,cfg)
        ass=captions_pro.write_plan(plan['captions'],work/'captions.ass',cfg)
    plan['display_words']=plan['words'];plan['subtitle_path']=str(ass);plan['caption_renderer']={'engine':'ass','status':'ready','reason':'audio or bilingual uses measured libass layout'}
    plan['caption_checks']=qc.inspect_caption_plan(plan['captions'],cfg,expected_words=plan['words'])
    if not plan['caption_checks']['passed']:raise ValueError('Subtitle audiogram perlu review: '+'; '.join(plan['caption_checks'].get('issues',[])))
    mix=render.audio_stems(source,plan,cfg,work);on_progress(25,'Merender audiogram dari audio sumber')
    target=draw(source,plan,cfg,ass,work/(name+'.mp4'),mix,lambda p:on_progress(30+round(p*60),'Encoding audiogram'))
    checked=qc.inspect(target,cfg,plan['duration']);plan['status']='done';plan['render_seconds']=time.monotonic()-started
    from .audio_quality import inspect
    plan['audio_quality']=inspect(target,cfg)
    from .style5 import readability
    plan['style_report']=readability(plan['captions'],cfg);plan['render_config']={};plan['style']={'font_main':cfg.font_main,'font_accent':cfg.font_accent}
    shutil.copy2(ass,text_base.with_suffix('.ass'))
    from .projects import write_srt
    write_srt(plan,text_base.with_suffix('.srt'));report_base.with_suffix('.credits.txt').write_text('Audiogram dari audio sumber milik pengguna.\n',encoding='utf-8')
    final=video_base.with_suffix('.mp4');shutil.move(target,final);path=work/'edit-plan.json';write_json(path,plan)
    return {'file':library_paths.relative(cfg,final),'url':library_paths.url(library_paths.relative(cfg,final)),
        'ass_url':library_paths.url(library_paths.relative(cfg,text_base.with_suffix('.ass'))),'srt_url':library_paths.url(library_paths.relative(cfg,text_base.with_suffix('.srt'))),
        'credits_url':library_paths.url(library_paths.relative(cfg,report_base.with_suffix('.credits.txt'))),'title':clip['title'],'reason':clip.get('reason',''),
        'start':clip['start'],'end':clip['end'],'length':checked['duration'],'width':cfg.target_w,'height':cfg.target_h,'fps':cfg.output_fps,
        'encoder':plan['encoder'],'revision':clip.get('revision',0),'plan_path':str(path),'render_version':'4.0.13-m2','broll_count':0,
        'subtitle_flags':0,'render_seconds':plan['render_seconds'],'selection_source':clip.get('selection_source'),'qc':checked,'warnings':plan['warnings']}


def edited_source(service,doc,cid,vid,source,words,clip,cfg,progress=lambda *_:None):
    from . import editor_contract as ec
    from .editor_media import _chunks,_atempo
    editor=service.variant(doc,cid,vid).get('editor',{});tracks=ec.track_state(editor)
    if any(editor.get('curves',{}).values()):raise ValueError('Sumber audio tidak mempunyai gambar untuk keyframe visual')
    clock=ec.build_clock(ec.segments_for(doc['clips'][cid],service.variant(doc,cid,vid)),cfg.output_fps)
    if any(r['camera_id']!='primary' for r in clock['slices']):raise ValueError('Sumber audio tidak mempunyai kamera')
    key=fingerprint([content_id(source,fresh=True),clock,tracks]);folder=service.work/doc['project_id']/'audio-editor'/key[:32];folder.mkdir(parents=True,exist_ok=True)
    output=folder/'edited.wav';cached=read_json(folder/'receipt.json',{})
    if not output.is_file() or cached.get('content_id')!=content_id(output,fresh=True):
        files=[]
        for i,row in enumerate(_chunks(clock)):
            a=ec.seconds(row['source_start_tick']);b=ec.seconds(row['source_end_tick']);duration=row['duration_frames']/clock['fps'];path=folder/f'chunk-{i}.wav'
            if row['kind']=='freeze' or not tracks['voice']['enabled']:
                command=['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',str(duration),'-c:a','pcm_s16le',str(path)]
            else:
                rate=(b-a)/duration;filters=['asetpts=PTS-STARTPTS']
                if row['reverse']:filters.append('areverse')
                filters += [_atempo(rate),'apad',f'atrim=duration={duration:.9f}']
                command=['ffmpeg','-v','error','-nostdin','-y','-ss',str(a),'-t',str(b-a),'-i',str(source),'-vn','-af',','.join(filters),'-ac','2','-ar','48000','-c:a','pcm_s16le',str(path)]
            subprocess.run(command,check=True,capture_output=True,timeout=180);files.append(path)
        listing=folder/'concat.txt';listing.write_text(''.join("file '"+str(p.resolve()).replace("'","'\\''")+"'\n" for p in files))
        pending=folder/'edited.partial.wav';subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-f','concat','-safe','0','-i',str(listing),'-t',str(clock['duration']),'-c:a','copy',str(pending)],check=True,capture_output=True)
        if abs(ffmpeg_util.probe(str(pending))['duration']-clock['duration'])>1/cfg.output_fps:raise ValueError('Clock edit audio tidak cocok')
        pending.replace(output);write_json(folder/'receipt.json',{'content_id':content_id(output,fresh=True),'clock':clock,'source_id':content_id(source),'policy':'speed/reverse measured; freeze/mute silence'})
    mapped=ec.remap_words(words,clock,editor.get('hidden_caption_word_ids',[]));display=[w for w in mapped if not w.get('caption_hidden')] if tracks['captions']['enabled'] else []
    adjusted={**clip,'start':0.,'end':clock['duration'],'manual_keep_spans':[[0.,clock['duration']]],'_editor_clock':clock,'_editor_tracks':tracks,
        '_editor_original_bounds':[clip['start'],clip['end']],'_editor_source':str(source),'_editor_proxy_content_id':content_id(output)}
    cfg=replace(cfg,trim_silence=False,cold_open=False,align_selected_clips=False,music_path=cfg.music_path if tracks['music']['enabled'] else '',sfx_mode=cfg.sfx_mode if tracks['sfx']['enabled'] else 'off')
    return str(output),display,adjusted,cfg,{'clock':clock,'proxy_path':str(output),'content_id':content_id(output),'source_layer':'baked'}
