"""M7 delivery choices and honest per-layer editor capabilities (EX01–13)."""
import copy
from .contracts import fingerprint

VERSION='4.0.18-m7'
RATIOS=('portrait','landscape','square','feed','custom')
EDITORS=('capcut','resolve','premiere','finalcut','otio')
TARGETS={'capcut':'4.7.0','resolve':'18.6.6','premiere':'FCP7 XML v5 exchange',
         'finalcut':'FCPXML 1.7 exchange','otio':'OTIO JSON 0.15 Clip.2'}
PROFILES={
    'reference':{'label':'Salinan final terverifikasi','codec':'copy','quality':'same bytes as reviewed MP4'},
    'balanced':{'label':'H.264 seimbang','codec':'libx264','preset':'fast','crf':18},
    'archive':{'label':'H.264 mutu tinggi','codec':'libx264','preset':'slow','crf':16},
    'compact':{'label':'H.264 hemat ukuran','codec':'libx264','preset':'fast','crf':23}}
DEFAULT={'ratios':['portrait','landscape'],'editors':list(EDITORS),'mode':'hybrid','profile':'reference',
         'clean':True,'alpha':False,'stems':True,'merged':True,'publish':True}


def options(value=None):
    if value is None:value={}
    if not isinstance(value,dict) or set(value)-set(DEFAULT):raise ValueError('Opsi M7 tidak dikenal')
    out=copy.deepcopy(DEFAULT);out.update(copy.deepcopy(value))
    for key,allowed in [('ratios',RATIOS),('editors',EDITORS)]:
        rows=out[key]
        if not isinstance(rows,list) or any(type(r) is not str or r not in allowed for r in rows) or len(rows)!=len(set(rows)) or (key=='ratios' and not rows):raise ValueError('Pilihan '+key+' M7 tidak valid')
        out[key]=[r for r in allowed if r in rows]
    if out['mode'] not in ('hybrid','native','preserved'):raise ValueError('Mode proyek editor M7 tidak valid')
    if type(out['profile']) is not str or out['profile'] not in PROFILES:raise ValueError('Profil video M7 tidak valid')
    for key in ('clean','alpha','stems','merged','publish'):
        if type(out[key]) is not bool:raise ValueError(key+' harus boolean')
    if out['mode']=='preserved' and out['editors']:raise ValueError('Paket tampilan terjaga memakai MP4; kosongkan pilihan editor atau pilih Hibrida')
    return out


def capabilities(plan,mode='hybrid'):
    """Generated tracks are candidates; editable claims require local import proof."""
    out=[]
    for editor in EDITORS:
        baked=editor in ('premiere','finalcut','otio') or mode=='preserved'
        layers={
            'source_cuts': 'editable_candidate' if not baked and mode=='native' else 'baked',
            'source_time_map':'baked', 'crop_layout_mask':'editable_candidate' if not baked and mode=='native' else 'baked',
            'caption_text_timing':'baked' if baked else 'editable_candidate',
            'caption_font_style':'baked' if baked else 'editable_candidate' if editor=='capcut' else 'backlog',
            'caption_motion':'baked' if baked else 'partial_candidate' if editor=='capcut' else 'backlog',
            'master_gain_offset':'editable_candidate','restoration_ducking_limiter':'baked',
            'music_sfx_voice_stems':'reference_only','broll':'baked' if baked else 'editable_candidate',
            'finishing_graphics_transitions':'baked','source_provenance':'metadata'}
        out.append({'editor':editor,'target_version':TARGETS[editor],'layers':layers,
            'native_acceptance':'not_tested','structural_status':'not_run',
            'limitations':['Impor, simpan, edit dan render harus diuji di aplikasi target.',
                'Resolve text/font tetap EX05 backlog.' if editor=='resolve' else
                'Blur/opacity CapCut belum setara dengan ASS.' if editor=='capcut' else
                'Exchange memakai clip final dengan teks/efek menyatu; tidak menjanjikan teks editable.']})
    return out


def selection(service,doc,request=None,*,fresh=False,require_ready=False):
    from .storage import read_json
    from .workflow6 import native_reasons
    choices=options(request);rows=[];blockers=[];matrix=[]
    for cid,c in doc.get('clips',{}).items():
        if not c.get('included',True) or c.get('created_from')=='M3' and c.get('selection_status')!='accepted':continue
        from .selection_service import renderable
        renderable(service,doc,c)
        for vid in choices['ratios']:
            if vid not in c['variants']:
                blockers.append({'clip_id':cid,'variant_id':vid,'message':'Buat rasio '+vid+' melalui panel M4 untuk klip ini dahulu.','status':'missing_variant'})
                rows.append({'clip_id':cid,'variant_id':vid,'dependency':None,'output_content_id':None,'plan_content_id':None,'reference':{}})
                continue
            variant=service.variant(doc,cid,vid);dep=service.dependency(doc,cid,vid,fresh=fresh)
            ready=service.export_readiness(doc,cid,vid,dependency=dep,fresh=fresh)
            result=variant.get('result') or {};plan=read_json(result.get('plan_path',''),{})
            if ready['status']!='ready':blockers.append({'clip_id':cid,'variant_id':vid,**ready})
            if choices['mode']=='native' and choices['editors']:
                for reason in native_reasons(plan):blockers.append({'clip_id':cid,'variant_id':vid,'message':reason,'status':'unsupported'})
            rows.append({'clip_id':cid,'variant_id':vid,'dependency':dep,'output_content_id':result.get('output_content_id'),
                'plan_content_id':result.get('plan_content_id'),'reference':{k:result.get(k) for k in ('width','height','length','duration','output_content_id')}})
            matrix.append({'clip_id':cid,'variant_id':vid,'capabilities':capabilities(plan,choices['mode'])})
    if not rows:raise ValueError('Pilih minimal satu klip yang diterima')
    if len(rows)>100:raise ValueError('Batas paket M7 adalah 100 timeline per tugas')
    if require_ready and blockers:raise ValueError('Final M7 belum lengkap: '+'; '.join(b['message'] for b in blockers[:10]))
    return {'version':VERSION,'options':choices,'targets':rows,'coverage':len(rows),'blockers':blockers,'ready':not blockers,
            'capabilities':matrix,'profiles':PROFILES,'dependency':fingerprint([VERSION,choices,rows]),
            'gate_g7':'pending_target_editor_acceptance'}
