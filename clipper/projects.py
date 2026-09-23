"""Editable project export. Native editor imports require a Windows acceptance test.

Resolve uses a supported XML interchange plus in-app Lua for Fusion typography.
CapCut uses pycapcut's native segments and a modern multi-timeline wrapper; its
undocumented draft format is explicitly reported as experimental.
"""
import copy
import json
import shutil
import time
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET
from PIL import Image
from .storage import read_json, write_json


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
    count = max(1, round((phrase['end'] - phrase['start']) * plan['fps']))
    nodes = ['BG = Background { Inputs = { Width = Input { Value = %d }, Height = Input { Value = %d }, TopLeftAlpha = Input { Value = 0 } } }' % (plan['width'], plan['height'])]
    previous = 'BG'
    for i, w in enumerate(phrase['words']):
        ident = f'Word{i + 1}'
        c = plan['style']['accent'] if w.get('emphasis') else plan['style']['base']
        rgb = [int(c.lstrip('#')[j:j+2], 16) / 255 for j in (0, 2, 4)]
        family = 'DejaVu Serif' if w.get('family') == 'serif' else 'DejaVu Sans'
        nodes.append(f'''{ident} = TextPlus {{ Inputs = {{
            GlobalIn = Input {{ Value = 0 }}, GlobalOut = Input {{ Value = {count - 1} }},
            Width = Input {{ Value = {plan['width']} }}, Height = Input {{ Value = {plan['height']} }},
            UseFrameFormatSettings = Input {{ Value = 1 }},
            StyledText = Input {{ Value = {lua_string(w['text'])} }}, Font = Input {{ Value = {lua_string(family)} }},
            Style = Input {{ Value = "Bold" }}, Size = Input {{ Value = {w['size'] / plan['height']:.8f} }},
            Center = Input {{ Value = {{ {w['x'] / plan['width']:.8f}, {1 - w['y'] / plan['height']:.8f} }} }},
            Red1 = Input {{ Value = {rgb[0]} }}, Green1 = Input {{ Value = {rgb[1]} }}, Blue1 = Input {{ Value = {rgb[2]} }},
            ShadingMappingLevel1 = Input {{ Value = 0 }} }} }}''')
        merge = f'Merge{i + 1}'
        nodes.append(f'{merge} = Merge {{ Inputs = {{ Background = Input {{ SourceOp = "{previous}", Source = "Output" }}, Foreground = Input {{ SourceOp = "{ident}", Source = "Output" }} }} }}')
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
        commands += ['local texts = tl:GetItemListInTrack("video", 2) or {}',
            'for i,item in ipairs(texts) do',
            f' local ok = item:ImportFusionComp(here .. {lua_string(prefix)} .. string.format("text-%03d.comp",i))',
            ' if not ok then note("Fusion teks belum terpasang: " .. tostring(i)) end', 'end']
        if title:
            commands += ['local titles = tl:GetItemListInTrack("video", 3) or {}',
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
    us = lambda seconds: round(seconds * 1e6)
    for i, item in enumerate(items):
        p = item['plan']; W, H = p['width'], p['height']
        name = f'CLIP_{i+1:02d}'
        script = drafts.create_draft(name, W, H, fps=p['fps'])
        script.add_track(cc.TrackType.video, 'Video')
        src = p['source']; fontmap = {}
        for shot in p['shots']:
            x, y, w, h = shot['rect']
            crop = cc.CropSettings(upper_left_x=x/src['width'], upper_left_y=y/src['height'],
                upper_right_x=(x+w)/src['width'], upper_right_y=y/src['height'],
                lower_left_x=x/src['width'], lower_left_y=(y+h)/src['height'],
                lower_right_x=(x+w)/src['width'], lower_right_y=(y+h)/src['height'])
            material = cc.VideoMaterial(src['path'], crop_settings=crop)
            duration = us(shot['end'] - shot['start'])
            source_start = us(shot['source_start'])
            # Some files round metadata down by a few microseconds.
            source_start = min(source_start, max(0, material.duration - duration))
            segment = cc.VideoSegment(material, trange(us(shot['start']), duration),
                source_timerange=trange(source_start, duration), volume=0)
            if shot['zoom_at'] is not None:
                z = shot['zoom_at']
                for t, value in [(0,1), (z,1), (z+8/p['fps'],1+shot['zoom_amount']),
                                 (z+3-12/p['fps'],1+shot['zoom_amount']), (z+3,1)]:
                    for prop in (cc.KeyframeProperty.scale_x, cc.KeyframeProperty.scale_y):
                        segment.add_keyframe(prop, us(t), value)
            script.add_segment(segment, 'Video')
        for kind, path in p['audio']['stems'].items():
            script.add_track(cc.TrackType.audio, kind)
            script.add_segment(cc.AudioSegment(path, trange(0, us(p['duration']))), kind)
        maxwords = max((len(ph['words']) for ph in p['captions']['phrases']), default=0)
        for k in range(maxwords):
            script.add_track(cc.TrackType.text, f'Kata {k+1}', relative_index=k)
        def text_segment(w, start, end, paint, track):
            if end - start < .015:
                return
            rgb = tuple(int(paint.lstrip('#')[j:j+2],16)/255 for j in (0,2,4))
            seg = cc.TextSegment(w['text'], trange(us(start), us(end-start)),
                style=cc.TextStyle(size=w['size'] * 120 / min(W,H), bold=True, color=rgb, align=1),
                clip_settings=cc.ClipSettings(transform_x=2*w['x']/W-1, transform_y=1-2*w['y']/H),
                border=cc.TextBorder(width=8, alpha=.65))
            fontmap[seg.material_id] = 'DejaVuSerif-Bold.ttf' if w.get('family') == 'serif' else 'DejaVuSans-Bold.ttf'
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
    root = Path(cfg.out_dir) / f'project-{cfg.job_id}-{int(time.time())}'
    root.mkdir(parents=True, exist_ok=False)
    (root / 'Media').mkdir()
    shutil.copytree(cfg.fonts_dir, root / 'Fonts')
    items = []
    for i, result in enumerate(results):
        p = read_json(result['plan_path'])
        if not p or p['revision'] != result['revision']:
            raise ValueError('Rencana edit tidak sesuai render terakhir.')
        if not Path(p['source']['path']).is_file():
            raise ValueError('Sumber dipindahkan. Pulihkan path sumber sebelum ekspor.')
        for kind, source in list(p['audio']['stems'].items()):
            target = root / 'Media' / f'{i+1:02}-{kind}.wav'
            shutil.copy2(source, target)
            p['audio']['stems'][kind] = str(target.resolve())
        write_json(root / f'edit-plan-{i+1:02}.json', p)
        items.append({**result, 'plan': p})
    progress(35, 'Membuat timeline DaVinci dan komposisi teks editable')
    resolve_export(items, root)
    progress(65, 'Membuat draft CapCut dengan track video, kata, dan audio')
    capcut_error = None
    try:
        capcut_export(items, root)
    except Exception as exc:
        capcut_error = str(exc)
    manifest = {'version': 2, 'created_root': str(root.resolve()).replace('\\','/'), 'timelines': len(items),
        'source_files': sorted({p['plan']['source']['path'] for p in items}),
        'capcut_status': 'experimental-generated' if capcut_error is None else 'failed', 'capcut_error': capcut_error,
        'resolve_status': 'generated-unverified-in-editor', 'limitations': [
            'Sumber video asli direferensikan; jangan dipindah. WAV dan font ada di paket.',
            'DaVinci: Fusion teks tetap editable; animasi penekanan dan zoom dapat berbeda dari MP4.',
            'Mode materi+pembicara saat ini diekspor ke editor sebagai gambar utuh; susun ulang split bila diperlukan.',
            'CapCut multi-timeline memakai format draft tidak resmi; perlu uji 9.5. Fallback draft per clip disediakan.']}
    write_json(root / 'manifest.json', manifest)
    shutil.copy2(Path(__file__).parent / 'project_install.py', root / 'PASANG_PROYEK.py')
    (root / 'PASANG_CAPCUT.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\npy -3 PASANG_PROYEK.py --capcut\r\nif errorlevel 1 echo Baca pesan di atas. Tidak ada proyek lama yang ditimpa.\r\npause\r\n', encoding='utf-8')
    (root / 'SIAPKAN_DAVINCI.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\npy -3 PASANG_PROYEK.py --relink\r\npause\r\n', encoding='utf-8')
    guide = '''PAKET PROYEK CLIPPER STUDIO

MP4 final berada di folder clips aplikasi dan dapat diunduh dari UI.
Sumber video asli tetap dipakai. Jangan pindahkan/hapus sumber tersebut.
Ekstrak paket ke folder permanen. Track suara, musik, efek, dan teks terpisah.

DAVINCI RESOLVE FREE
1. Jalankan SIAPKAN_DAVINCI.cmd agar path aset sesuai lokasi ekstrak.
2. Instal dua font TTF dalam Fonts bila belum ada (klik kanan > Install).
3. Buka Resolve > Workspace > Console. Pilih Lua.
4. Jalankan dofile([[C:/path/paket/DaVinci/IMPORT_RESOLVE.lua]]) dengan path Anda.
Script membuat satu proyek baru dengan satu timeline per clip; tidak menimpa proyek lama.
Alternatif: import setiap DaVinci/clip-XX/timeline.xml ke satu proyek secara manual,
lalu impor captions.srt. Tipografi Fusion memerlukan script atau Import Fusion Composition
pada clip TEXT_... menggunakan file text-XXX.comp yang sesuai.
Teks bisa diedit pada Fusion > Word1, Word2, dst. Zoom dasar di Inspector.
Marker kuning menunjukkan penekanan zoom yang dapat ditambahkan keyframe.
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
File proyek telah dibuat secara terstruktur; impor di Resolve Free 21.0.4 / CapCut 9.5
belum dijalankan dalam lingkungan pengembangan. Periksa satu clip dahulu.
Perbedaan yang diketahui: penekanan teks Fusion statis, zoom halus Resolve berupa marker,
dan split materi+pembicara pada editor perlu disusun ulang. MP4 memakai semua efek renderer.
'''
    if capcut_error:
        guide += '\nEKSPOR CAPCUT GAGAL: ' + capcut_error + '\nInstal requirements-pro.txt lalu ekspor ulang.\n'
    (root / 'BACA_DULU.txt').write_text(guide, encoding='utf-8')
    zip_path = shutil.make_archive(str(root), 'zip', root)
    return {'zip': zip_path, 'folder': str(root), 'timelines': len(items), 'capcut_error': capcut_error,
            'note': 'Impor native perlu verifikasi di editor. Baca BACA_DULU.txt.'}
