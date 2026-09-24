"""FFmpeg executes an edit plan in one video encode, with reusable audio stems."""
from pathlib import Path
import subprocess
from .ffmpeg_util import ass_filter, encoder_args, encode, filter_file_args


def run_audio(args, target, log):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-v', 'error', '-y', *map(str, args),
                        '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(target)], capture_output=True)
    if r.returncode:
        message = r.stderr.decode('utf-8', 'replace')[-2400:]
        Path(log).write_text(message, encoding='utf-8')
        raise RuntimeError('Audio FFmpeg gagal: ' + message)


def audio_stems(source, plan, cfg, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    duration = plan['duration']
    seek = min(s['source_start'] for s in plan['spans'])
    end = max(s['source_end'] for s in plan['spans'])
    parts = []
    for i, s in enumerate(plan['spans']):
        parts.append(f"[0:a]atrim=start={s['source_start'] - seek:.8f}:end={s['source_end'] - seek:.8f},asetpts=PTS-STARTPTS[a{i}]")
    norm = (f',apad=pad_dur=3,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,atrim=duration={duration:.8f}'
            if cfg.audio_normalize else '')
    parts.append(''.join(f'[a{i}]' for i in range(len(plan['spans']))) + f"concat=n={len(plan['spans'])}:v=0:a=1{norm}[voice]")
    voice = folder / 'voice.wav'
    run_audio(['-ss', seek, '-t', end - seek, '-i', source, '-filter_complex_threads', '2',
               '-filter_complex', ';'.join(parts), '-map', '[voice]', '-t', duration], voice, folder / 'audio.log')
    stems = {'voice': str(voice.resolve())}
    if cfg.music_path:
        music = folder / 'music-ducked.wav'
        fade = max(0., duration - 1.2)
        graph = (f'[0:a]volume={cfg.music_db}dB,afade=t=in:d=0.7,afade=t=out:st={fade}:d=1.2[m];'
                 '[m][1:a]sidechaincompress=threshold=0.025:ratio=8:attack=15:release=400:makeup=1[out]')
        run_audio(['-stream_loop', '-1', '-i', cfg.music_path, '-i', voice,
                   '-filter_complex', graph, '-map', '[out]', '-t', duration], music, folder / 'audio.log')
        stems['music'] = str(music.resolve())
    events = []
    if cfg.sfx_path:
        events = [s['start'] + s['zoom_at'] for s in plan['shots'] if s['zoom_at'] is not None]
        if plan['spans'][0]['kind'] == 'cold_open':
            events.insert(0, plan['spans'][0]['end'])
        sparse = []
        for t in sorted(events):
            if not sparse or t - sparse[-1] >= 10:
                sparse.append(t)
        events = sparse[:6]
        if events:
            sfx = folder / 'effects.wav'
            graph = []
            for i, t in enumerate(events):
                graph.append(f'[0:a]atrim=duration=0.65,asetpts=PTS-STARTPTS,afade=t=out:st=0.35:d=0.3,'
                             f'volume={cfg.sfx_db}dB,adelay={round(t * 1000)}:all=1[e{i}]')
            graph.append(''.join(f'[e{i}]' for i in range(len(events))) + f'amix=inputs={len(events)}:normalize=0,apad[out]')
            run_audio(['-i', cfg.sfx_path, '-filter_complex', ';'.join(graph), '-map', '[out]', '-t', duration], sfx, folder / 'audio.log')
            stems['effects'] = str(sfx.resolve())
    master = folder / 'mix.wav'
    inputs = []
    for path in stems.values():
        inputs.extend(['-i', path])
    graph = ''.join(f'[{i}:a]' for i in range(len(stems))) + f'amix=inputs={len(stems)}:normalize=0:duration=longest,alimiter=limit=0.84:level=0:latency=1[out]'
    run_audio([*inputs, '-filter_complex', graph, '-map', '[out]', '-t', duration], master, folder / 'audio.log')
    plan['audio'] = {'stems': stems, 'mix': str(master.resolve()), 'music_original': cfg.music_path,
                     'music_db': cfg.music_db, 'sfx_original': cfg.sfx_path, 'sfx_events': events}
    return str(master)


def video(source, plan, cfg, ass, target, mix, on_progress=None):
    W, H, fps = plan['width'], plan['height'], plan['fps']
    seek = min(s['source_start'] for s in plan['shots'])
    end = max(s['source_end'] for s in plan['shots'])
    graph = []
    for i, shot in enumerate(plan['shots']):
        x, y, w, h = shot['rect']
        prefix = (f"[0:v]trim=start={shot['source_start'] - seek:.8f}:end={shot['source_end'] - seek:.8f},"
                  f"setpts=PTS-STARTPTS,fps={fps},crop={w}:{h}:{x}:{y}")
        suffix = f",setsar=1,format=yuv420p,trim=end_frame={shot['duration_frames']},setpts=N/({fps}*TB)[v{i}]"
        if shot['mode'] == 'stream' and H > W and shot.get('face_rect'):
            top = round(H * shot.get('material_share', .62)) // 2 * 2
            fx, fy, fw, fh = shot['face_rect']
            graph.append(prefix + f",scale={W}:{top}:force_original_aspect_ratio=decrease,pad={W}:{top}:(ow-iw)/2:(oh-ih)/2:color=0x11151b[mat{i}]")
            graph.append(f"[0:v]trim=start={shot['source_start'] - seek:.8f}:end={shot['source_end'] - seek:.8f},setpts=PTS-STARTPTS,fps={fps},crop={fw}:{fh}:{fx}:{fy},scale={W}:{H-top}:force_original_aspect_ratio=increase,crop={W}:{H-top}[face{i}]")
            graph.append(f'[mat{i}][face{i}]vstack=inputs=2' + suffix)
        else:
            if shot['mode'] == 'fill':
                prefix += f',scale={W}:{H}:flags=bicubic'
            else:
                prefix += f',scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x11151b'
            if shot['zoom_at'] is not None:
                zf = round(shot['zoom_at'] * fps)
                envelope = f'max(0,min(1,min((on-{zf})/8,({zf + 3 * fps}-on)/12)))'
                prefix += f",zoompan=z='1+{cfg.zoom_amount}*{envelope}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={fps}"
            graph.append(prefix + suffix)
    graph.append(''.join(f'[v{i}]' for i in range(len(plan['shots']))) + f"concat=n={len(plan['shots'])}:v=1:a=0,{ass_filter(ass, cfg)}[out]")
    target = Path(target)
    pending = target.with_name(target.stem + '.rendering.mp4')
    script = target.with_suffix('.filter.txt')
    script.write_text(';\n'.join(graph), encoding='utf-8')
    codec = cfg.video_codec
    command = ['ffmpeg', '-hide_banner', '-v', 'warning', '-y', '-ss', str(seek), '-t', str(end - seek), '-i', str(source),
        '-i', str(mix), '-filter_complex_threads', '2', *filter_file_args(script),
        '-map', '[out]', '-map', '1:a', '-t', str(plan['duration']), '-r', str(fps),
        '-c:v', codec, *encoder_args(codec), '-pix_fmt', 'yuv420p', '-threads', '6',
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', str(pending)]
    try:
        actual, warnings = encode(command, codec, target.with_suffix('.render.log'), on_progress, plan['duration'])
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)
    plan['encoder'] = actual
    plan['warnings'].extend(warnings)
    return str(target)
