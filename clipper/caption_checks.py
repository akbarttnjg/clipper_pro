"""A-owned caption validator; B qc.py may delegate through C0."""
from collections import Counter
import math
from .caption_readability import clear_time


def logical_ids(word):
    return word.get('token_ids') or [word.get('token_id',word.get('word_id'))]


def inspect_caption_plan(plan, cfg, expected_words=None):
    """Check settled positions and line edges against the requested placement."""
    if plan.get('m5_version'):
        from .finishing5_plan import check
        if plan.get('bilingual'):
            source=check(plan['source_plan'],cfg,plan['source_words']);translation=check(plan['translation_plan'],cfg,plan['translation_words'])
            return {**source,'translation':translation,'bilingual':True}
        return check(plan,cfg,expected_words)
    if plan.get('bilingual'):
        from .bilingual_m2 import check
        return check(plan,cfg)
    issues = []
    from .caption_geometry import bounds
    readability = []
    measurements=[]
    if expected_words and not plan.get('phrases'):
        issues.append('Subtitle kosong meskipun transkrip berisi kata.')
    if isinstance(expected_words,list):
        expected=[i for w in expected_words for i in logical_ids(w) if i is not None]
        actual=[i for p in plan.get('phrases',[]) for w in p['words'] if not w.get('decorative')
                for i in logical_ids(w) if i is not None]
        if Counter(expected)!=Counter(actual):issues.append('Coverage atau jumlah kata/frasa subtitle tidak sesuai transkrip; kata tidak ada, berlebih, atau duplikat.')
        elif expected!=actual:issues.append('Urutan kata/frasa subtitle berbeda dari transkrip.')
    if plan.get('title'):
        issues.append('Judul pembuka seharusnya tidak dirender.')
    for phrase in plan.get('phrases', []):
        if cfg.caption_position != 'auto' and phrase['position'] != cfg.caption_position:
            issues.append('Posisi subtitle berbeda dari pilihan manual.')
        align = cfg.caption_align
        if align == 'auto':
            align = phrase['position'] if phrase['position'] in ('left', 'right') else 'center'
            if plan.get('version')==5 and phrase.get('design',{}).get('alignment') in ('left','center','right'):
                align=phrase['design']['alignment']
        if phrase.get('alignment') != align:
            issues.append('Perataan subtitle berbeda dari pengaturan.')
        x, y, width, height = phrase['panel']
        duration = phrase['end']-phrase['start']
        if not math.isfinite(duration) or duration<=0:raise ValueError('Durasi frasa subtitle harus positif dan finite.')
        cps = sum(len(w['text'])+1 for w in phrase['words'])/max(.01,duration)
        if cps > 24:
            readability.append({'start':phrase['start'],'end':phrase['end'],'reason':'Ucapan cepat; pertimbangkan memperpanjang batas atau menyederhanakan teks secara manual','characters_per_second':round(cps,1)})
        lines = {}
        for word in phrase['words']:
            lines.setdefault(word['baseline'], []).append(word)
            if not (0 <= word['x']-word['width']/2 < word['x']+word['width']/2 <= cfg.target_w):
                issues.append('Subtitle keluar dari lebar gambar.')
            samples = word.get('keyframes', [{'scale':1,'dx':0,'dy':0,'opacity':1}])
            measured=clear_time(word,duration,interpolation=plan.get('keyframe_interpolation','hold'))
            measurements.append({'start':phrase['start'],'token':word['text'],**measured})
            hold=measured['longest_contiguous_clear']
            if hold<min(.25,duration*.4):
                readability.append({'start':phrase['start'],'token':word['text'],'reason':'Waktu diam terbaca singkat',
                                    'visible_hold_seconds':round(hold,3),'severity':'blocker',**measured})
            for frame in samples:
                if frame.get('opacity',1)<.05:
                    continue
                bx,by,bw,bh=bounds(word,frame)
                if not (-.5 <= bx and bx+bw <= cfg.target_w+.5 and -.5 <= by and by+bh <= cfg.target_h+.5):
                    issues.append('Animasi subtitle keluar dari batas gambar.')
                if not (x-.5 <= bx and bx+bw <= x+width+.5 and y-.5 <= by and by+bh <= y+height+.5):
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
                    box = bounds(word,frame)
                    if any(overlap(box, item['box']) > .5 for item in phrase.get('protected', [])):
                        issues.append('Subtitle bertabrakan dengan area wajah/tulisan yang terdeteksi.')
        for row in lines.values():
            left = min(w['x']-w['width']/2 for w in row)
            right = max(w['x']+w['width']/2 for w in row)
            observed = left if align == 'left' else right if align == 'right' else (left+right)/2
            ax,ay,aw,ah=phrase.get('alignment_panel',phrase['panel'])
            if not(x-.01<=ax and ax+aw<=x+width+.01 and y-.01<=ay and ay+ah<=y+height+.01 and aw>0 and ah>0):
                issues.append('Area perataan subtitle berada di luar area teks.')
            expected = ax if align == 'left' else ax+aw if align == 'right' else ax+aw/2
            if abs(observed-expected) > 1:
                issues.append('Tepi baris subtitle belum sejajar.')
    if issues:
        raise ValueError('Pemeriksaan posisi subtitle gagal: ' + ' '.join(dict.fromkeys(issues)))
    blocked=any(row.get('severity')=='blocker' for row in readability)
    return {'passed': not blocked,'geometry_passed':True,'inspection_state':'completed',
            'status':'needs_review' if blocked else 'pass','validator_version':'caption-qc-m0-1',
            'phrases': len(plan.get('phrases', [])),
            'requested_position': cfg.caption_position, 'requested_alignment': cfg.caption_align,
            'readability':readability,'clear_time_metrics':measurements,
            'contrast_protection':bool(cfg.caption_backdrop),'raster_contrast_status':'not_measured',
            'checks': ['manual_position', 'line_alignment', 'horizontal_bounds', 'vertical_bounds', 'animation_envelope', 'reading_speed', 'detected_region_collision', 'no_title_overlay']}
