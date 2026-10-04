"""Caption geometry validation; owned by workstream A."""
def inspect_caption_plan(plan, cfg):
    """Check settled positions and line edges against the requested placement."""
    issues = []
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
        lines = {}
        for word in phrase['words']:
            lines.setdefault(word['baseline'], []).append(word)
            if not (0 <= word['x']-word['width']/2 < word['x']+word['width']/2 <= cfg.target_w):
                issues.append('Subtitle keluar dari lebar gambar.')
            if cfg.caption_position == 'auto' and cfg.safe_placement:
                from .placement import overlap
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
            'checks': ['manual_position', 'line_alignment', 'horizontal_bounds', 'detected_region_collision', 'no_title_overlay']}

