"""Bounded M5 style, brand and layer schema; values are never silently dropped."""
import copy,math,re
VERSION='4.0.16.1'
LEGACY=frozenset('font_main font_accent accent_hex base_hex caption_style style_preset caption_template_policy caption_composition caption_seed caption_position caption_align caption_scale caption_backdrop motion_intensity semantic_emphasis accent_font caption_renderer safe_placement'.split())
DEFAULTS=dict(template_id='editorial',granularity='phrase',karaoke=False,emoji=False,speaker_color=False,speaker_labels=False,speaker_styles=[],emoji_map=[],fallback_fonts=['dejavu'],stroke_px=1.8,stroke_hex='#141821',shadow_px=2.,shadow_hex='#000000',glow_px=0.,glow_hex='#F6CF69',minimum_glyph_px=14.,display_width_px=360,motion_budget=.03,censor_mode='off',censor_terms=[],censor_approved=False,source_caption_mode='avoid',source_captions=[],manual_panel=None,builder=None)
FIELDS=LEGACY|set(DEFAULTS)
HEX=re.compile(r'^#[0-9a-fA-F]{6}$');ID=re.compile(r'^[a-zA-Z0-9_-]{1,96}$')
TEMPLATES=[dict(id=k,name=n,motion=m,accent_ratio=a,max_rows=2,line_gap=.23) for k,n,m,a in [('editorial','Editorial','rise',1.10),('focus','Fokus makna','rise',1.22),('quote','Kutipan tenang','still',1.06),('news','Berita bersih','still',1.08),('stack','Daftar','slide',1.12),('minimal','Minimal','still',1.)]]
PRESETS=[dict(id=k,name=n,values=dict(template_id=t,font_main=f,font_accent=a,style_preset=p,caption_position=pos,caption_align=al,motion_intensity='calm',emoji=False,karaoke=ka,semantic_emphasis=em,caption_backdrop=True,caption_template_policy='auto',motion_budget=.02)) for k,n,t,f,a,p,pos,al,ka,em in [('education','Edukasi','editorial','dm_sans','dm_serif_italic','rapi','left','left',False,True),('editorial','Editorial','editorial','dm_sans','dm_serif_italic','adaptif','auto','left',False,True),('social','Sosial','focus','montserrat','dm_serif','ekspresif','auto','center',True,True),('accessible','Aksesibel','minimal','dejavu','dejavu','rapi','bottom','center',False,False)]]

def number(v,lo,hi,label):
    if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError(label+' di luar batas')
    return v
def text(v,n,label):
    if not isinstance(v,str) or len(v)>n or any(ord(c)<32 and c not in '\n\t' for c in v):raise ValueError(label+' tidak valid')
    return v.strip()
def rect(v):
    if not isinstance(v,list) or len(v)!=4:raise ValueError('Area harus [x,y,lebar,tinggi] persen')
    x,y,w,h=[number(t,0,100,'Area') for t in v]
    if min(w,h)<1 or x+w>100.001 or y+h>100.001:raise ValueError('Area di luar canvas')
    return list(v)
def builder(v):
    if v is None:return None
    if not isinstance(v,dict) or set(v)-{'id','name','motion','accent_ratio','max_rows','line_gap','roles','version'}:raise ValueError('Schema builder tidak valid')
    if not ID.fullmatch(str(v.get('id',''))) or not text(v.get('name',''),80,'Nama'):raise ValueError('ID/nama template diperlukan')
    if v.get('motion','still') not in ('still','rise','slide','fade'):raise ValueError('Motion template tidak valid')
    rows=number(v.get('max_rows',2),1,3,'Baris')
    if type(rows) is not int:raise ValueError('Baris harus integer')
    roles=v.get('roles',['narration'])
    if not isinstance(roles,list) or not roles or set(roles)-{'narration','number_or_warning','list','conclusion'}:raise ValueError('Peran template tidak valid')
    return dict(id=v['id'],name=v['name'],motion=v.get('motion','still'),accent_ratio=number(v.get('accent_ratio',1.1),1,1.3,'Hierarki'),max_rows=rows,line_gap=number(v.get('line_gap',.23),.12,.5,'Jarak'),roles=roles,version=1)
def style(values):
    if not isinstance(values,dict) or set(values)-FIELDS:raise ValueError('Field gaya M5 tidak dikenal')
    from .config import validate_overrides
    out={}
    for k,v in values.items():
        if k in LEGACY:
            if k in ('font_main','font_accent') and isinstance(v,str) and v.startswith('font-') and ID.fullmatch(v):out[k]=v;continue
            if k=='caption_renderer' and v=='raster':out[k]=v;continue
            checked=validate_overrides({k:v})
            if checked.get(k)!=v or k not in checked:raise ValueError('Gaya '+k+' tidak valid')
            if isinstance(v,bool) and k not in ('semantic_emphasis','accent_font','caption_backdrop','safe_placement'):raise ValueError('Jenis gaya tidak valid')
            out[k]=v
        elif k in ('karaoke','emoji','speaker_color','speaker_labels','censor_approved'):
            if type(v) is not bool:raise ValueError(k+' harus boolean')
            out[k]=v
        elif k in ('stroke_px','shadow_px','glow_px','minimum_glyph_px','display_width_px','motion_budget'):
            lo,hi={'stroke_px':(0,8),'shadow_px':(0,12),'glow_px':(0,12),'minimum_glyph_px':(14,22),'display_width_px':(240,720),'motion_budget':(0,.08)}[k];out[k]=number(v,lo,hi,k)
            if k=='display_width_px' and type(v) is not int:raise ValueError('Lebar layar harus integer')
        elif k.endswith('_hex'):
            if not isinstance(v,str) or not HEX.fullmatch(v):raise ValueError('Warna tidak valid')
            out[k]=v
        elif k in ('template_id','granularity','censor_mode','source_caption_mode'):
            opts={'template_id':[t['id'] for t in TEMPLATES]+['custom'],'granularity':['phrase','word'],'censor_mode':['off','mask','bleep_mask'],'source_caption_mode':['avoid','cover','reconstruct']}[k]
            if v not in opts:raise ValueError(k+' tidak valid')
            out[k]=v
        elif k in ('fallback_fonts','censor_terms'):
            if not isinstance(v,list) or len(v)>(4 if k=='fallback_fonts' else 100):raise ValueError(k+' tidak valid')
            out[k]=[text(t,96,k) for t in v]
            if any(not t for t in out[k]):raise ValueError('Nilai kosong')
        elif k=='manual_panel':out[k]=None if v is None else rect(v)
        elif k=='builder':out[k]=builder(v)
        else:
            if not isinstance(v,list) or len(v)>100:raise ValueError(k+' tidak valid')
            rows=[]
            for r in v:
                if not isinstance(r,dict):raise ValueError(k+' harus objek')
                if k=='speaker_styles':
                    if set(r)-{'speaker_id','label','color','approved'} or r.get('approved') is not True or not HEX.fullmatch(str(r.get('color',''))):raise ValueError('Identitas/warna speaker harus disetujui')
                    rows.append(dict(speaker_id=text(r.get('speaker_id',''),96,'Speaker'),label=text(r.get('label',''),80,'Label'),color=r['color'],approved=True))
                elif k=='emoji_map':
                    if set(r)-{'keyword','icon'}:raise ValueError('Schema emoji tidak valid')
                    rows.append(dict(keyword=text(r.get('keyword',''),80,'Keyword'),icon=text(r.get('icon',''),8,'Ikon')))
                else:
                    if set(r)-{'rect','start','end','provenance','approved'} or r.get('approved') is not True:raise ValueError('Area subtitle sumber harus ditinjau')
                    a=number(r.get('start'),0,86400,'Awal');b=number(r.get('end'),0,86400,'Akhir')
                    if b<=a:raise ValueError('Interval kosong')
                    rows.append(dict(rect=rect(r.get('rect')),start=a,end=b,provenance=text(r.get('provenance','manual'),160,'Asal'),approved=True))
            if k=='speaker_styles' and len({r['speaker_id'] for r in rows})!=len(rows):raise ValueError('Speaker duplikat')
            out[k]=rows
    return copy.deepcopy(out)
def effective(cfg):return {**{k:getattr(cfg,k) for k in LEGACY},**copy.deepcopy(DEFAULTS),**(cfg.finishing5 or {}).get('style',{})}
def layers(values):
    if not isinstance(values,list) or len(values)>20:raise ValueError('Maksimal 20 layer')
    out=[];ids=set()
    for r in values:
        if not isinstance(r,dict) or set(r)-set('id kind enabled start end rect opacity anchor asset_id text speaker_id reason transition transition_s quote items values unit attribution'.split()):raise ValueError('Schema layer tidak valid')
        key=r.get('id');kind=r.get('kind')
        if not isinstance(key,str) or not ID.fullmatch(key) or key in ids:raise ValueError('ID layer duplikat/tidak valid')
        ids.add(key)
        if kind not in ('logo','image','video','title','intro','outro','lower_third','diagram'):raise ValueError('Jenis layer tidak valid')
        if type(r.get('enabled',True)) is not bool:raise ValueError('Enabled harus boolean')
        a=number(r.get('start'),0,86400,'Awal');b=number(r.get('end'),0,86400,'Akhir')
        if b<=a:raise ValueError('Durasi kosong')
        anchor=r.get('anchor','manual');tr=r.get('transition','cut')
        if anchor not in ('manual','top_left','top_right','bottom_left','bottom_right','center') or tr not in ('cut','fade','blur','glitch'):raise ValueError('Anchor/transisi tidak valid')
        row={**copy.deepcopy(r),'enabled':r.get('enabled',True),'rect':rect(r.get('rect')),'opacity':number(r.get('opacity',1.),0,1,'Opacity'),'anchor':anchor,'transition':tr,'transition_s':number(r.get('transition_s',0.),0,.4,'Durasi transisi')}
        for f,n in [('text',500),('quote',2000),('reason',240),('attribution',1000),('speaker_id',96),('unit',40)]:
            if f in r:row[f]=text(r[f],n,f)
        if kind in ('title','intro','outro') and not row.get('text'):raise ValueError('Teks kartu diperlukan')
        if kind in ('logo','image','video') and not ID.fullmatch(str(r.get('asset_id',''))):raise ValueError('Pilih aset terdaftar')
        if kind=='diagram':
            if not isinstance(r.get('items'),list) or not 1<=len(r['items'])<=8:raise ValueError('Diagram memerlukan 1–8 item utuh')
            row['items']=[text(t,100,'Item') for t in r['items']]
            if any(not item for item in row['items']):raise ValueError('Item diagram tidak boleh kosong')
            if r.get('values') is not None:
                if not isinstance(r['values'],list) or len(r['values'])!=len(row['items']):raise ValueError('Nilai diagram tidak lengkap')
                row['values']=[number(t,-1e12,1e12,'Nilai') for t in r['values']]
            if not row.get('quote'):raise ValueError('Diagram memerlukan kutipan sumber')
        if kind=='lower_third' and not row.get('speaker_id'):raise ValueError('Lower-third memerlukan speaker')
        out.append(row)
    return out
