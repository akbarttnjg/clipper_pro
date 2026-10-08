"""A-owned caption validator; B qc.py may delegate through C0."""
def inspect_caption_plan(plan, cfg, expected_words=None):
    """Check settled positions and line edges against the requested placement."""
    issues = []
    readability = []
    if expected_words and not plan.get('phrases'):
        issues.append('Subtitle kosong meskipun transkrip berisi kata.')
    if isinstance(expected_words,list):
        expected={i for w in expected_words for i in w.get('source_word_ids',[w.get('word_id')]) if i is not None}
        actual={i for p in plan.get('phrases',[]) for w in p['words'] for i in w.get('word_ids',[w.get('word_id')]) if i is not None}
        if expected-actual:issues.append('Sebagian kata/frasa yang seharusnya tampil tidak ada di rencana subtitle.')
    if plan.get('title'):
        issues.append('Judul pembuka seharusnya tidak dirender.')
    for phrase in plan.get('phrases', []):
        if cfg.caption_position != 'auto' and phrase['position'] != cfg.caption_position:
            issues.append('Posisi subtitle berbeda dari pilihan manual.')
        align = cfg.caption_align
        if align == 'auto':
            align = phrase['position'] if phrase['position'] in ('left', 'right') else 'center'
        if phrase.get('alignment') != align:
            issues.append('Perataan subtitle berbeda dari pengaturan.')
        x, y, width, height = phrase['panel']
        duration = phrase['end']-phrase['start']
        cps = sum(len(w['text'])+1 for w in phrase['words'])/max(.01,duration)
        if cps > 24:
            readability.append({'start':phrase['start'],'end':phrase['end'],'reason':'Ucapan cepat; pertimbangkan memperpanjang batas atau menyederhanakan teks secara manual','characters_per_second':round(cps,1)})
        lines = {}
        for word in phrase['words']:
            lines.setdefault(word['baseline'], []).append(word)
            if not (0 <= word['x']-word['width']/2 < word['x']+word['width']/2 <= cfg.target_w):
                issues.append('Subtitle keluar dari lebar gambar.')
            samples = word.get('keyframes', [{'scale':1,'dx':0,'dy':0,'opacity':1}])
            stable=[f.get('t',0) for f in samples if f.get('opacity',1)>=.98 and f.get('blur',0)<=.5
                    and abs(f.get('scale',1)-1)<=.025]
            hold=max(stable)-min(stable) if len(stable)>1 else duration if not word.get('keyframes') else 0
            if hold<min(.25,duration*.4):
                readability.append({'start':phrase['start'],'token':word['text'],'reason':'Waktu diam terbaca singkat','visible_hold_seconds':round(hold,3)})
            for frame in samples:
                if frame.get('opacity',1)<.05:
                    continue
                half_w = word['width']*frame.get('scale',1)/2
                half_h = word['size']*frame.get('scale',1)*.66
                cx,cy = word['x']+frame.get('dx',0), word['y']+frame.get('dy',0)
                if not (-.5 <= cx-half_w and cx+half_w <= cfg.target_w+.5 and -.5 <= cy-half_h and cy+half_h <= cfg.target_h+.5):
                    issues.append('Animasi subtitle keluar dari batas gambar.')
                if not (x-.5 <= cx-half_w and cx+half_w <= x+width+.5 and y-.5 <= cy-half_h and cy+half_h <= y+height+.5):
                    issues.append('Animasi subtitle keluar dari area teks.')
            if cfg.caption_position == 'auto' and cfg.safe_placement:
                # Caption validation only needs rectangle arithmetic, not the
                # OpenCV frame detector used by production placement sampling.
                def overlap(a,b):
                    x,y,w,h=a;bx,by,bw,bh=b
                    return max(0,min(x+w,bx+bw)-max(x,bx))*max(0,min(y+h,by+bh)-max(y,by))
                for frame in word.get('keyframes', [{'scale': 1, 'dx': 0, 'dy': 0, 'opacity': 1}]):
                    if frame.get('opacity', 1) < .05:
                        continue
                    scale = frame.get('scale', 1)
                    box = [word['x']+frame.get('dx', 0)-word['width']*scale/2,
                           word['y']+frame.get('dy', 0)-word['size']*scale*.66,
                           word['width']*scale, word['size']*scale*1.32]
                    if any(overlap(box, item['box']) > .5 for item in phrase.get('protected', [])):
                        issues.append('Subtitle bertabrakan dengan area wajah/tulisan yang terdeteksi.')
        for row in lines.values():
            left = min(w['x']-w['width']/2 for w in row)
            right = max(w['x']+w['width']/2 for w in row)
            observed = left if align == 'left' else right if align == 'right' else (left+right)/2
            expected = x if align == 'left' else x+width if align == 'right' else x+width/2
            if abs(observed-expected) > 1:
                issues.append('Tepi baris subtitle belum sejajar.')
    if issues:
        raise ValueError('Pemeriksaan posisi subtitle gagal: ' + ' '.join(dict.fromkeys(issues)))
    return {'passed': True, 'phrases': len(plan.get('phrases', [])),
            'requested_position': cfg.caption_position, 'requested_alignment': cfg.caption_align,
            'readability':readability,'contrast_protection':bool(cfg.caption_backdrop),
            'checks': ['manual_position', 'line_alignment', 'horizontal_bounds', 'vertical_bounds', 'animation_envelope', 'reading_speed', 'detected_region_collision', 'no_title_overlay']}
