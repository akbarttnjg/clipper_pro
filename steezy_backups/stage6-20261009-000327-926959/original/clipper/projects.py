"""Editable project export. Native editor imports require a Windows acceptance test.

Resolve uses a supported XML interchange plus in-app Lua for Fusion typography.
CapCut uses pycapcut's native segments and a modern multi-timeline wrapper; its
undocumented draft format is explicitly reported as experimental.
"""
import copy
from dataclasses import replace
import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET
from PIL import Image
from .storage import read_json, write_json
from .timebase import seconds_to_us, endpoint_range, video_track_ranges


def srt_stamp(t):
    ms = max(0, round(t * 1000))
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def write_srt(plan, path):
    lines = []
    for i, p in enumerate(plan['captions']['phrases']):
        lines.extend([str(i + 1), f"{srt_stamp(p['start'])} --> {srt_stamp(p['end'])}",
                      ' '.join(w['text'] for w in p['words']), ''])
    Path(path).write_text('\n'.join(lines), encoding='utf-8-sig')


def lua_string(value):
    # Lua 5.1 supports UTF-8 bytes and these common JSON escapes, but not \u escapes.
    return json.dumps(str(value), ensure_ascii=False).replace('\\/', '/')


def fusion_comp(phrase, plan, path):
    """A native Text+ node per word, sharing baseline positions and source timing."""
    count = max(1, round(phrase['end']*plan['fps']) - round(phrase['start']*plan['fps']))
    nodes = ['BG = Background { Inputs = { Width = Input { Value = %d }, Height = Input { Value = %d }, TopLeftAlpha = Input { Value = 0 } } }' % (plan['width'], plan['height'])]
    previous = 'BG'
    def curve(name, samples, value):
        keys = ', '.join('[%d] = { %.8f, Flags = { Linear = true } }' % (k['frame'], value(k)) for k in samples)
        nodes.append(f'{name} = BezierSpline {{ KeyFrames = {{ {keys} }} }}')
        return 'Input { SourceOp = "' + name + '", Source = "Value" }'
    for i, w in enumerate(phrase['words']):
        ident = f'Word{i + 1}'
        c = plan['style']['accent'] if w.get('emphasis') else plan['style']['base']
        rgb = [int(c.lstrip('#')[j:j+2], 16) / 255 for j in (0, 2, 4)]
        family = w['family'] if w.get('font_id') else ('DejaVu Serif' if w.get('family') == 'serif' else 'DejaVu Sans')
        size = f"Input {{ Value = {w['size']/plan['height']:.8f} }}"
        center = f"Input {{ Value = {{ {w['x']/plan['width']:.8f}, {1-w['y']/plan['height']:.8f} }} }}"
        blend = 'Input { Value = 1 }'
        blur = 'Input { Value = 0 }'
        if w.get('keyframes'):
            samples = w['keyframes']
            size = curve(ident+'Size', samples, lambda k:w['size']/plan['height']*k['scale'])
            xx = curve(ident+'X', samples, lambda k:(w['x']+k['dx'])/plan['width'])
            yy = curve(ident+'Y', samples, lambda k:1-(w['y']+k['dy'])/plan['height'])
            nodes.append(f'{ident}Path = XYPath {{ Inputs = {{ X = {xx}, Y = {yy} }} }}')
            center = f'Input {{ SourceOp = "{ident}Path", Source = "Value" }}'
            blend = curve(ident+'Opacity', samples, lambda k:k['opacity'])
            blur = curve(ident+'Softness', samples, lambda k:k['blur']/min(plan['width'],plan['height'])*100)
        style = 'Book' if w.get('family') == 'regular' else 'Bold'
        if w.get('italic'):
            style = 'Oblique' if style == 'Book' else 'Bold Oblique'
        if w.get('font_id'):
            style = w['style']
        nodes.append(f'''{ident} = TextPlus {{ Inputs = {{
            GlobalIn = Input {{ Value = 0 }}, GlobalOut = Input {{ Value = {count - 1} }},
            Width = Input {{ Value = {plan['width']} }}, Height = Input {{ Value = {plan['height']} }},
            UseFrameFormatSettings = Input {{ Value = 1 }},
            StyledText = Input {{ Value = {lua_string(w['text'])} }}, Font = Input {{ Value = {lua_string(family)} }},
            Style = Input {{ Value = {lua_string(style)} }}, Size = {size},
            Center = {center},
            Red1 = Input {{ Value = {rgb[0]} }}, Green1 = Input {{ Value = {rgb[1]} }}, Blue1 = Input {{ Value = {rgb[2]} }},
            ShadingMappingLevel1 = Input {{ Value = 0 }} }} }}''')
        foreground = ident
        if w.get('keyframes') and any(k['blur'] for k in w['keyframes']):
            foreground = ident+'Blur'
            nodes.append(f'{foreground} = Blur {{ Inputs = {{ Filter = Input {{ Value = FuID {{ "Gaussian" }} }}, XBlurSize = {blur}, YBlurSize = {blur}, Input = Input {{ SourceOp = "{ident}", Source = "Output" }} }} }}')
        merge = f'Merge{i + 1}'
        nodes.append(f'{merge} = Merge {{ Inputs = {{ Blend = {blend}, Background = Input {{ SourceOp = "{previous}", Source = "Output" }}, Foreground = Input {{ SourceOp = "{foreground}", Source = "Output" }} }} }}')
        previous = merge
    nodes.append(f'MediaOut1 = MediaOut {{ Inputs = {{ Input = Input {{ SourceOp = "{previous}", Source = "Output" }}, Index = Input {{ Value = "0" }} }} }}')
    Path(path).write_text('{ Tools = ordered() {\n' + ',\n'.join(nodes) + '\n}, ActiveTool = "Word1" }\n', encoding='utf-8')


def node(parent, tag, value=None, **attrs):
    e = ET.SubElement(parent, tag, **attrs)
    if value is not None:
        e.text = str(value)
    return e


def rate(parent, fps):
    r = node(parent, 'rate')
    # FCP7 represents 29.97/59.94 with an integer timebase plus NTSC flag.
    node(r, 'timebase', round(fps))
    node(r, 'ntsc', 'TRUE' if abs(fps - round(fps) * 1000 / 1001) < .001 else 'FALSE')


def xml_timeline(plan, name, path, transparent):
    fps = plan['fps']
    root = ET.Element('xmeml', version='5')
    seq = node(root, 'sequence', id='seq-' + uuid.uuid4().hex)
    node(seq, 'name', name)
    node(seq, 'duration', plan['duration_frames'])
    rate(seq, fps)
    tc = node(seq, 'timecode'); rate(tc, fps); node(tc, 'string', '00:00:00:00'); node(tc, 'frame', 0); node(tc, 'displayformat', 'NDF')
    media = node(seq, 'media'); video = node(media, 'video')
    sc = node(node(video, 'format'), 'samplecharacteristics')
    node(sc, 'width', plan['width']); node(sc, 'height', plan['height']); rate(sc, fps)
    node(sc, 'pixelaspectratio', 'square'); node(sc, 'fielddominance', 'none')
    track = node(video, 'track')
    source = plan['source']
    def clipitem(track, label, file, start, frames, source_start, source_fps, isvideo, width=0, height=0, source_duration=None):
        c = node(track, 'clipitem', id='clip-' + uuid.uuid4().hex)
        node(c, 'name', label); node(c, 'enabled', 'TRUE'); node(c, 'duration', frames); rate(c, source_fps)
        node(c, 'start', start); node(c, 'end', start + frames)
        sin = round(source_start * source_fps)
        node(c, 'in', sin); node(c, 'out', sin + round(frames / fps * source_fps))
        f = node(c, 'file', id='file-' + uuid.uuid4().hex)
        node(f, 'name', Path(file).name); node(f, 'pathurl', Path(file).resolve().as_uri()); rate(f, source_fps)
        node(f, 'duration', round((source_duration or plan['duration'] + 1) * source_fps))
        fm = node(f, 'media')
        if isvideo:
            v = node(node(fm, 'video'), 'samplecharacteristics'); rate(v, source_fps)
            node(v, 'width', width); node(v, 'height', height); node(v, 'pixelaspectratio', 'square'); node(v, 'fielddominance', 'none')
        else:
            audio = node(fm, 'audio'); node(audio, 'channelcount', 2)
            sm = node(audio, 'samplecharacteristics'); node(sm, 'depth', 16); node(sm, 'samplerate', 48000)
            st = node(c, 'sourcetrack'); node(st, 'mediatype', 'audio'); node(st, 'trackindex', 1)
        return c
    for i, s in enumerate(plan['shots']):
        clipitem(track, f'SHOT_{i+1:03}', source['path'], s['start_frame'], s['duration_frames'],
                 s['source_start'], source['fps'], True, source['width'], source['height'], source['duration'])
    if plan.get('broll'):
        broll_track = node(video, 'track')
        for i, event in enumerate(plan['broll']):
            a, b = round(event['start']*fps), round(event['end']*fps)
            clipitem(broll_track, f'BROLL_{i+1:03}', event['path'], a, b-a, 0, fps,
                     True, plan['width'], plan['height'], event['duration'])
    text_track = node(video, 'track')
    for i, p in enumerate(plan['captions']['phrases']):
        a, b = round(p['start'] * fps), round(p['end'] * fps)
        clipitem(text_track, f'TEXT_{i+1:03}', transparent, a, max(1, b-a), 0, fps, True, plan['width'], plan['height'])
    if plan['captions'].get('title'):
        t = plan['captions']['title']
        clipitem(node(video, 'track'), 'TITLE', transparent, 0, round(t['end'] * fps), 0, fps, True, plan['width'], plan['height'])
    audio = node(media, 'audio'); node(audio, 'numOutputChannels', 2)
    for kind, file in plan['audio']['stems'].items():
        t = node(audio, 'track')
        clipitem(t, kind, file, 0, plan['duration_frames'], 0, fps, False)
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def resolve_export(items, root):
    folder = root / 'DaVinci'
    folder.mkdir()
    # Run inside Workspace > Console > Lua, which does not need external scripting.
    commands = [
        '-- Run inside Resolve: Workspace > Console > Lua > dofile([[C:/.../IMPORT_RESOLVE.lua]])',
        'local resolve = resolve or (bmd and bmd.scriptapp("Resolve"))',
        'assert(resolve, "Jalankan script dari Console Lua di DaVinci Resolve.")',
        'local pm = resolve:GetProjectManager()',
        'local project = pm:CreateProject("Clipper Studio " .. os.date("%Y%m%d-%H%M%S"))',
        'assert(project, "Tidak dapat membuat proyek baru.")',
        'project:SetSetting("timelineFrameRate", "30")',
        'local pool = project:GetMediaPool()',
        'local here = debug.getinfo(1,"S").source:sub(2):match("^(.*[/\\\\])")',
        'local failures = {}',
        'local function note(s) print(s); table.insert(failures,s) end',
    ]
    for i, item in enumerate(items):
        plan = item['plan']; name = f'{i+1:02d}-{item["title"]}'
        sub = folder / f'clip-{i+1:02d}'
        sub.mkdir()
        transparent = root / 'Media' / f'transparent-{plan["width"]}x{plan["height"]}.png'
        if not transparent.exists():
            Image.new('RGBA', (plan['width'], plan['height']), (0, 0, 0, 0)).save(transparent)
        xml_timeline(plan, name, sub / 'timeline.xml', transparent)
        write_srt(plan, sub / 'captions.srt')
        for j, phrase in enumerate(plan['captions']['phrases']):
            fusion_comp(phrase, plan, sub / f'text-{j+1:03d}.comp')
        title = plan['captions'].get('title')
        if title:
            p = {**title, 'words': [{**title, 'y': title['y'] + title['size'] / 2, 'emphasis': False}]}
            fusion_comp(p, plan, sub / 'title.comp')
        prefix = f'clip-{i+1:02d}/'
        commands += [f'local tl = pool:ImportTimelineFromFile(here .. {lua_string(prefix + "timeline.xml")}, {{timelineName={lua_string(name)}, importSourceClips=true}})',
            'if not tl then note("Gagal impor timeline XML") else', 'project:SetCurrentTimeline(tl)',
            'tl:SetSetting("useCustomSettings", "1")',
            f'tl:SetSetting("timelineResolutionWidth", "{plan["width"]}")',
            f'tl:SetSetting("timelineResolutionHeight", "{plan["height"]}")',
            'local shots = tl:GetItemListInTrack("video", 1) or {}']
        for j, shot in enumerate(plan['shots']):
            sx, sy, sw, sh = shot['rect']; source = plan['source']
            factor = min(plan['width'] / sw, plan['height'] / sh)
            base = min(plan['width'] / source['width'], plan['height'] / source['height'])
            zoom = factor / base
            pan = (source['width'] / 2 - sx - sw / 2) * factor
            tilt = (sy + sh / 2 - source['height'] / 2) * factor
            commands.append(f'if shots[{j+1}] then shots[{j+1}]:SetProperty({{ZoomX={zoom:.8f}, ZoomY={zoom:.8f}, Pan={pan:.5f}, Tilt={tilt:.5f}}}) end')
            if shot['zoom_at'] is not None:
                frame = round((shot['start'] + shot['zoom_at']) * plan['fps'])
                commands.append(f'tl:AddMarker({frame}, "Yellow", "Zoom accent", "MP4 memiliki zoom halus. Atur keyframe Inspector bila ingin menyamai geraknya.", 1)')
        commands += [f'local texts = tl:GetItemListInTrack("video", {3 if plan.get("broll") else 2}) or {{}}',
            'for i,item in ipairs(texts) do',
            f' local ok = item:ImportFusionComp(here .. {lua_string(prefix)} .. string.format("text-%03d.comp",i))',
            ' if not ok then note("Fusion teks belum terpasang: " .. tostring(i)) end', 'end']
        if title:
            commands += [f'local titles = tl:GetItemListInTrack("video", {4 if plan.get("broll") else 3}) or {{}}',
                         f'if titles[1] then titles[1]:ImportFusionComp(here .. {lua_string(prefix + "title.comp")}) end']
        commands += ['end']
    commands += ['pm:SaveProject()', 'print("Impor selesai. Periksa jumlah timeline, font, framing, dan track audio.")',
                 'print("Catatan impor: " .. tostring(#failures))']
    (folder / 'IMPORT_RESOLVE.lua').write_text('\n'.join(commands), encoding='utf-8')


def capcut_export(items, root):
    import pycapcut as cc
    from pycapcut import trange
    cap = root / 'CapCut'
    cap.mkdir()
    drafts = cc.DraftFolder(str(cap))
    timelines = []
    now = int(time.time() * 1e6)
    us = seconds_to_us
    for i, item in enumerate(items):
        p = item['plan']; W, H = p['width'], p['height']
        video_ranges, timeline_duration = video_track_ranges(p)
        name = f'CLIP_{i+1:02d}'
        script = drafts.create_draft(name, W, H, fps=p['fps'])
        script.add_track(cc.TrackType.video, 'Video')
        src = p['source']; fontmap = {}
        for shot, (target_start, duration) in zip(p['shots'], video_ranges):
            x, y, w, h = shot['rect']
            crop = cc.CropSettings(upper_left_x=x/src['width'], upper_left_y=y/src['height'],
                upper_right_x=(x+w)/src['width'], upper_right_y=y/src['height'],
                lower_left_x=x/src['width'], lower_left_y=(y+h)/src['height'],
                lower_right_x=(x+w)/src['width'], lower_right_y=(y+h)/src['height'])
            material = cc.VideoMaterial(src['path'], crop_settings=crop)
            source_start = us(shot['source_start'])
            # Some files round metadata down by a few microseconds.
            source_start = min(source_start, max(0, material.duration - duration))
            segment = cc.VideoSegment(material, trange(target_start, duration),
                source_timerange=trange(source_start, duration), volume=0)
            if shot['zoom_at'] is not None:
                z = shot['zoom_at']
                for t, value in [(0,1), (z,1), (z+8/p['fps'],1+shot['zoom_amount']),
                                 (z+3-12/p['fps'],1+shot['zoom_amount']), (z+3,1)]:
                    for prop in (cc.KeyframeProperty.scale_x, cc.KeyframeProperty.scale_y):
                        segment.add_keyframe(prop, us(t), value)
            script.add_segment(segment, 'Video')
        if p.get('broll'):
            script.add_track(cc.TrackType.video, 'Ilustrasi B-roll', relative_index=1)
            for event in p['broll']:
                material=cc.VideoMaterial(event['path'])
                start, duration = endpoint_range(event['start'], event['end'])
                duration=min(duration,material.duration)
                script.add_segment(cc.VideoSegment(material,trange(start,duration),
                    source_timerange=trange(0,duration),volume=0),'Ilustrasi B-roll')
        for kind, path in p['audio']['stems'].items():
            script.add_track(cc.TrackType.audio, kind)
            material = cc.AudioMaterial(path)
            difference = timeline_duration-material.duration
            if difference > 2000:
                raise ValueError(f'Track {kind} kurang {difference/1e6:.3f} detik dari timeline. Render ulang clip sebelum ekspor.')
            script.add_segment(cc.AudioSegment(material, trange(0, min(timeline_duration, material.duration))), kind)
        maxwords = max((len(ph['words']) for ph in p['captions']['phrases']), default=0)
        for k in range(maxwords):
            script.add_track(cc.TrackType.text, f'Kata {k+1}', relative_index=k)
        def text_segment(w, start, end, paint, track):
            if end - start < .015:
                return
            rgb = tuple(int(paint.lstrip('#')[j:j+2],16)/255 for j in (0,2,4))
            samples = w.get('keyframes', [])
            # Text opacity/blur keyframes are not supported by pycapcut's native
            # text mapping. Start at the reveal; preserve move and scale curves.
            reveal = next((k['t'] for k in samples if k['opacity'] > 0), 0.)
            duration = end-start-reveal
            if duration < .015:
                return
            target_start, target_duration = endpoint_range(start+reveal, end)
            seg = cc.TextSegment(w['text'], trange(target_start, target_duration),
                style=cc.TextStyle(size=w['size'] * 120 / min(W,H), bold=w.get('bold',w.get('family')!='regular'), italic=bool(w.get('italic')), color=rgb, align=1),
                clip_settings=cc.ClipSettings(transform_x=2*w['x']/W-1, transform_y=1-2*w['y']/H),
                border=cc.TextBorder(width=0 if samples else 8, alpha=.65))
            timed = {min(target_duration, max(0, us(k['t']-reveal))): k for k in samples if k['t'] >= reveal}
            for when, key in sorted(timed.items()):
                if key['t'] < reveal:
                    continue
                for prop, value in ((cc.KeyframeProperty.scale_x,key['scale']), (cc.KeyframeProperty.scale_y,key['scale']),
                    (cc.KeyframeProperty.position_x,2*(w['x']+key['dx'])/W-1),
                    (cc.KeyframeProperty.position_y,1-2*(w['y']+key['dy'])/H)):
                    seg.add_keyframe(prop, when, value)
            fontmap[seg.material_id] = w.get('file') or {'regular':'DejaVuSans.ttf','serif':'DejaVuSerif-Bold.ttf'}.get(w.get('family'),'DejaVuSans-Bold.ttf')
            script.add_segment(seg, track)
        for phrase in p['captions']['phrases']:
            for k, w in enumerate(phrase['words']):
                if w['emphasis'] and p['style']['caption_style'] == 'editorial':
                    text_segment(w, phrase['start'], w['start'], p['style']['base'], f'Kata {k+1}')
                    text_segment(w, w['start'], phrase['end'], p['style']['accent'], f'Kata {k+1}')
                else:
                    text_segment(w, phrase['start'], phrase['end'], p['style']['accent'] if w['emphasis'] else p['style']['base'], f'Kata {k+1}')
        title = p['captions'].get('title')
        if title:
            script.add_track(cc.TrackType.text, 'Judul', relative_index=maxwords+1)
            text_segment({**title, 'y': title['y'] + title['size']/2}, 0, title['end'], p['style']['base'], 'Judul')
        script.save()
        path = cap / name / 'draft_content.json'
        data = read_json(path)
        # pycapcut's template reuses its draft ID. The wrapper indexes files by
        # timeline ID; duplicates would overwrite earlier clips in the package.
        data['id'] = str(uuid.uuid4()).upper()
        for material in data['materials']['texts']:
            body = json.loads(material['content'])
            fontpath = str((root / 'Fonts' / fontmap[material['id']]).resolve()).replace('\\','/')
            for style in body['styles']:
                style['font'] = {'path': fontpath, 'id': ''}
                style['shadows'] = [{'diffuse': .02, 'alpha': .6, 'distance': 3,
                    'content': {'solid': {'color': [0., 0., 0.]}}, 'angle': -45}]
            material['content'] = json.dumps(body, ensure_ascii=False)
        data['name'] = item['title']
        data['canvas_config']['ratio'] = '9:16' if H>W else '16:9'
        write_json(path, data)
        # Keep each single-timeline draft as a fallback if 9.5 changes the modern wrapper.
        timelines.append({'id': data['id'], 'name': item['title'], 'folder': name, 'data': data})
        update_capcut_meta(cap / name, data, name, [data])
    combined = cap / 'CLIPPER_ALL_TIMELINES'
    combined.mkdir()
    for t in timelines:
        target = combined / 'Timelines' / t['id']
        write_json(target / 'draft_content.json', t['data'])
        write_json(target / 'draft_content.json.bak', t['data'])
        write_json(target / 'template.tmp', t['data'])
    project = {'id': str(uuid.uuid4()).upper(), 'main_timeline_id': timelines[0]['id'], 'version': 0,
        'config': {'color_space': -1, 'render_index_track_mode_on': False, 'use_float_render': False},
        'create_time': now, 'update_time': now, 'timelines': [
            {'id': t['id'], 'name': t['name'], 'is_marked_delete': False, 'create_time': now, 'update_time': now} for t in timelines]}
    write_json(combined / 'Timelines' / 'project.json', project)
    write_json(combined / 'Timelines' / 'project.json.bak', project)
    write_json(combined / 'timeline_layout.json', {'dockItems': [{'dockIndex': 0, 'ratio': 1,
        'timelineIds': [t['id'] for t in timelines], 'timelineNames': [t['name'] for t in timelines]}], 'layoutOrientation': 1})
    for filename in ('draft_content.json', 'draft_content.json.bak', 'template-2.tmp'):
        write_json(combined / filename, timelines[0]['data'])
    write_json(combined / 'draft_virtual_store.json', {'draft_materials': [], 'draft_virtual_store': []})
    write_json(combined / 'attachment_pc_common.json', {})
    write_json(combined / 'performance_opt_info.json', {})
    (combined / 'draft_settings').write_text('[General]\n', encoding='utf-8')
    (combined / 'draft_biz_config.json').write_text('{}', encoding='utf-8')
    update_capcut_meta(combined, timelines[0]['data'], 'Clipper Studio — semua clip', [t['data'] for t in timelines])
    return len(timelines)


def update_capcut_meta(folder, data, name, timelines):
    meta = read_json(folder / 'draft_meta_info.json', {})
    now = int(time.time() * 1e6)
    media = []
    seen = set()
    for timeline in timelines:
        for key in ('videos', 'audios'):
            for m in timeline['materials'][key]:
                if m.get('path') in seen:
                    continue
                seen.add(m.get('path'))
                media.append({'id': m['id'], 'file_Path': m.get('path', ''), 'metetype': 'video' if key == 'videos' else 'audio',
                    'duration': m.get('duration',0), 'width': m.get('width',0), 'height':m.get('height',0),
                    'extra_info': Path(m.get('path','')).name, 'roughcut_time_range': {'start':0,'duration':m.get('duration',0)},
                    'sub_time_range': {'start':-1,'duration':-1}, 'create_time': now//1000000, 'import_time':now//1000000})
    meta.update(draft_id=str(uuid.uuid4()).upper(), draft_name=name, draft_fold_path=str(folder.resolve()).replace('\\','/'),
        draft_root_path=str(folder.parent.resolve()).replace('\\','/'), draft_json_file=str((folder/'draft_content.json').resolve()).replace('\\','/'),
        tm_draft_create=now, tm_draft_modified=now, tm_duration=data['duration'],
        draft_materials=[{'type':0,'value':media}], draft_timeline_materials_size=sum(len(t['tracks']) for t in timelines))
    write_json(folder / 'draft_meta_info.json', meta)


def export_bundle(results, cfg, progress=lambda p,m: None):
    from .library_paths import project_root
    root = project_root(cfg) / 'projects' / f'project-{cfg.job_id}-{time.time_ns()}'
    root.mkdir(parents=True, exist_ok=False)
    (root / 'Media').mkdir()
    shutil.copytree(cfg.fonts_dir, root / 'Fonts')
    licenses = Path(__file__).parent / 'font-licenses'
    if licenses.is_dir():
        shutil.copytree(licenses, root / 'Font-Licenses')
    items = []
    for i, result in enumerate(results):
        p = read_json(result['plan_path'])
        if not p or p['revision'] != result['revision']:
            raise ValueError('Rencana edit tidak sesuai render terakhir.')
        if not Path(p['source']['path']).is_file():
            raise ValueError('Sumber dipindahkan. Pulihkan path sumber sebelum ekspor.')
        from . import render, qc
        original = copy.deepcopy(p)
        exchange=Path(result.get('exchange_path',Path(result['plan_path']).with_name('exchange.json')))
        if exchange.is_file():shutil.copyfile(exchange,root/f'exchange-{i+1:02}.json')
        clean_cfg = replace(cfg, target_w=p['width'], target_h=p['height'], output_fps=p['fps'],
                            **p.get('render_config', {}))
        clean = Path(result['plan_path']).parent / 'video-clean.mp4'
        cache = clean.with_suffix('.cache.json')
        fingerprint = {k:p.get(k) for k in ('shots','source','width','height','fps','duration','render_config')}
        fingerprint['version'] = '2.4-source-only'
        from .dependency_cache import content_id
        fingerprint['media_content_id'] = content_id(p['source']['path'],fresh=True)
        fingerprint['mix_content_id'] = content_id(p['audio']['mix'],fresh=True)
        key = hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()
        if not clean.exists() or read_json(cache,{}).get('key') != key:
            progress(round(5+30*i/max(1,len(results))), f'Menyiapkan video tanpa teks {i+1}/{len(results)}')
            render.video(p['source']['path'], {**p, 'broll': []}, clean_cfg, None, clean, p['audio']['mix'],
                lambda fraction: progress(round(5+30*(i+fraction)/max(1,len(results))),
                    f'Video tanpa teks {i+1}/{len(results)}'))
        qc.inspect(clean, clean_cfg, p['duration'])
        write_json(cache, {'key':key})
        packed_clean = root / 'Media' / f'{i+1:02}-video-clean.mp4'
        shutil.copy2(clean, packed_clean)
        from .illustrations import credits
        credit_rows=credits(p)
        write_json(root/'Media'/f'{i+1:02}-credits.json',credit_rows)
        (root/'Media'/f'{i+1:02}-credits.txt').write_text('\n'.join(c['credit'] for c in credit_rows),encoding='utf-8')
        for j,event in enumerate(p.get('broll',[])):
            packed=root/'Media'/f'{i+1:02}-broll-{j+1:02}.mp4'
            shutil.copy2(event['path'],packed)
            event['path']=str(packed.resolve());event['asset']['path']=str(packed.resolve())
        subtitle = Path(p.get('subtitle_path', Path(result['plan_path']).parent / 'captions.ass'))
        if subtitle.is_file():
            shutil.copy2(subtitle, root / 'Media' / f'{i+1:02}-captions.ass')
        write_srt(p, root / 'Media' / f'{i+1:02}-captions.srt')
        write_json(root / f'original-edit-plan-{i+1:02}.json', original)
        # Framing and zoom are baked into V1; typography and audio remain separate.
        # This preserves the material/speaker split exactly in both editors.
        p['source'] = {**p['source'], 'path': str(packed_clean.resolve()), 'fps': p['fps'],
                       'width': p['width'], 'height': p['height'], 'duration': p['duration']}
        p['shots'] = [{**s, 'source_start': s['start'], 'source_end': s['end'],
                       'rect': [0,0,p['width'],p['height']], 'mode': 'fill',
                       'face_rect': None, 'zoom_at': None} for s in p['shots']]
        for kind, source in list(p['audio']['stems'].items()):
            target = root / 'Media' / f'{i+1:02}-{kind}.wav'
            shutil.copy2(source, target)
            p['audio']['stems'][kind] = str(target.resolve())
        write_json(root / f'edit-plan-{i+1:02}.json', p)
        items.append({**result, 'plan': p})
    progress(35, 'Membuat timeline DaVinci dan komposisi teks editable')
    resolve_error = None
    try:
        resolve_export(items, root)
    except Exception as exc:
        resolve_error = str(exc)
    progress(65, 'Membuat draft CapCut dengan track video, kata, dan audio')
    capcut_error = None
    try:
        capcut_export(items, root)
    except Exception as exc:
        capcut_error = str(exc)
    manifest = {'version': 4, 'created_root': str(root.resolve()).replace('\\','/'), 'timelines': len(items),
        'source_files': sorted({p['plan']['source']['path'] for p in items}),
        'capcut_status': 'experimental-generated' if capcut_error is None else 'failed', 'capcut_error': capcut_error,
        'resolve_status': 'generated-unverified-in-editor' if resolve_error is None else 'failed', 'resolve_error': resolve_error,
        'export_mode': 'hybrid', 'editable_layers': ['text', 'audio', 'broll'],
        'baked_layers': ['source_framing', 'source_zoom'], 'native_editor_status': 'not_tested',
        'broll_layer': 'separate silent video track', 'limitations': [
            'B-roll ada pada track terpisah; credits.txt berisi sumber untuk deskripsi publikasi.',
            'Video tanpa teks, WAV, font, ASS master dan SRT ada di paket. Framing/zoom sudah menyatu di video.',
            'DaVinci: Fusion Text+ dengan kurva posisi, ukuran, opacity dan blur; perlu verifikasi tampilan di editor.',
            'CapCut: teks editable dengan gerak posisi/ukuran. Blur dan fade native belum dipetakan; MP4/ASS memuat efek lengkap.',
            'CapCut multi-timeline memakai format draft tidak resmi; perlu uji 9.5. Fallback draft per clip disediakan.']}
    write_json(root / 'manifest.json', manifest)
    shutil.copy2(Path(__file__).parent / 'project_install.py', root / 'PASANG_PROYEK.py')
    (root / 'PASANG_CAPCUT.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\npy -3 PASANG_PROYEK.py --capcut\r\nif errorlevel 1 echo Baca pesan di atas. Tidak ada proyek lama yang ditimpa.\r\npause\r\n', encoding='utf-8')
    (root / 'SIAPKAN_DAVINCI.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\npy -3 PASANG_PROYEK.py --relink\r\npause\r\n', encoding='utf-8')
    guide = '''PAKET PROYEK CLIPPER STUDIO

MP4 final berada di folder clips aplikasi dan dapat diunduh dari UI.
Ekstrak paket ke folder permanen. Video tanpa teks, suara, musik, efek, dan teks terpisah.
B-roll adalah layer video terpisah tanpa audio stok. Kredit ada di Media/XX-credits.txt.
Komposisi materi/pembicara serta zoom menyatu dalam video agar hasilnya konsisten.
original-edit-plan menyimpan keputusan terhadap sumber asli untuk referensi.
Media/XX-captions.ass adalah master animasi penuh; ASS tidak otomatis menjadi
layer editable native. Paket mengubah tipografi menjadi Text+ / track teks editor.
Media/XX-captions.srt merupakan fallback teks biasa tanpa animasi.

DAVINCI RESOLVE FREE
1. Jalankan SIAPKAN_DAVINCI.cmd agar path aset sesuai lokasi ekstrak.
2. Instal semua font TTF dalam Fonts bila belum ada (klik kanan > Install).
3. Buka Resolve > Workspace > Console. Pilih Lua.
4. Jalankan dofile([[C:/path/paket/DaVinci/IMPORT_RESOLVE.lua]]) dengan path Anda.
Script membuat satu proyek baru dengan satu timeline per clip; tidak menimpa proyek lama.
Alternatif: import setiap DaVinci/clip-XX/timeline.xml ke satu proyek secara manual,
lalu impor captions.srt. Tipografi Fusion memerlukan script atau Import Fusion Composition
pada clip TEXT_... menggunakan file text-XXX.comp yang sesuai.
Teks bisa diedit pada Fusion > Word1, Word2, dst. Zoom dasar di Inspector.
Gerak posisi, ukuran, opacity dan blur teks memiliki kurva animasi di Fusion.
Tata letak/animasi native perlu diperiksa; MP4 merupakan rujukan hasil render.

CAPCUT 9.5 — EKSPERIMENTAL
Tutup CapCut sepenuhnya, lalu jalankan PASANG_CAPCUT.cmd.
Installer menambahkan proyek CLIPPER_ALL_TIMELINES dan mencadangkan indeks proyek.
Jika wrapper multi-timeline tidak terbaca, jalankan:
py -3 PASANG_PROYEK.py --capcut --individual
untuk memasang draft per clip sebagai fallback. Tidak membutuhkan CapCut Pro.
Pilih teks, musik, video langsung pada track untuk mengubahnya.
Jika folder proyek CapCut dipindah dari lokasi standar, gunakan --draft-root "D:/...".
Jangan hapus folder paket setelah impor karena aset direferensikan dari sini.

BATAS VERIFIKASI
Status pembuatan dan kelengkapan tiap editor tersedia di verification.json.
Impor di Resolve Free 21.0.4 / CapCut 9.5
belum dijalankan dalam lingkungan pengembangan. Periksa satu clip dahulu.
Perbedaan yang diketahui: blur dan fade teks CapCut belum dipetakan; ukuran font dan
baseline kedua editor dapat berbeda. Semua efek penuh ada pada MP4 dan master ASS.
Komposisi kamera sudah menyatu di video tanpa teks. Ubah framing di aplikasi lalu
ekspor ulang jika ingin menggantinya. Pembuatan paket menambah satu render tanpa teks
per clip, yang disimpan untuk dipakai kembali selama revisi tidak berubah.
'''
    for editor, error in (('CAPCUT', capcut_error), ('DAVINCI', resolve_error)):
        if error:
            guide += '\nEKSPOR ' + editor + ' GAGAL: ' + error + '\nPeriksa verification.json; perbaiki penyebab tersebut lalu ekspor ulang.\n'
    (root / 'BACA_DULU.txt').write_text(guide, encoding='utf-8')
    from .export_verify import validate_bundle
    verification = validate_bundle(root, results)
    write_json(root / 'verification.json', verification)
    manifest['structural_status'] = verification['structural_status']
    manifest['editors'] = verification['editors']
    write_json(root / 'manifest.json', manifest)
    zip_path = shutil.make_archive(str(root), 'zip', root)
    return {'zip': zip_path, 'folder': str(root), 'timelines': len(items),
            'capcut_error': capcut_error, 'resolve_error': resolve_error,
            'structural_status': verification['structural_status'], 'editors': verification['editors'],
            'native_editor_status': 'not_tested', 'export_mode': 'hybrid',
            'note': ('Paket perlu diperiksa. ' if verification['issues'] else 'Struktur paket lolos pemeriksaan. ')
                    + 'Impor native perlu verifikasi di editor. Baca BACA_DULU.txt.'}
