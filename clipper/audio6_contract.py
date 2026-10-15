"""M6 audio controls have explicit units and never imply an unavailable model."""
import copy
import math
import re

VERSION = '4.0.17-m6'
RATE = 48000
MAX_SECONDS = 600
DEFAULTS = dict(normalize=True,target_lufs=-16.,peak_db=-1.5,limiter=True,
    source_gain_db=0.,denoise='off',noise_reduction_db=8.,hum_hz=0,
    enhancement=False,dereverb=False,dereverb_strength=.35,
    eq_bands=[],compressor=False,compressor_threshold_db=-20.,compressor_ratio=2.,
    compressor_attack_ms=15.,compressor_release_ms=180.,
    separation='off',model_directory='',model_name='htdemucs',separation_background_db=0.,
    pitch_semitones=0.,ducking=True,duck_db=-14.,duck_attack_ms=80.,duck_release_ms=350.,
    sfx_enabled=True,smooth_ms=5.,export_stems=True)
BOOLS = {'normalize','limiter','enhancement','dereverb','compressor','ducking','sfx_enabled','export_stems'}
NUMBERS = {'target_lufs':(-30.,-10.),'peak_db':(-9.,-1.),'source_gain_db':(-36.,18.),
    'noise_reduction_db':(1.,24.),'dereverb_strength':(0.,1.),'separation_background_db':(-60.,0.),
    'compressor_threshold_db':(-48.,0.),'compressor_ratio':(1.,8.),
    'compressor_attack_ms':(1.,200.),'compressor_release_ms':(10.,2000.),
    'pitch_semitones':(-12.,12.),'duck_db':(-30.,0.),'duck_attack_ms':(5.,500.),
    'duck_release_ms':(20.,3000.),'smooth_ms':(0.,15.)}
ROLES = ('music','sfx','voiceover','reaction','dubbing')

def number(value,lo,hi,label):
    if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
        raise ValueError(f'{label} harus angka {lo:g}–{hi:g}')
    return float(value)

def text(value,limit,label):
    if not isinstance(value,str) or len(value)>limit or '\x00' in value:raise ValueError(label+' tidak valid')
    return value.strip()

def settings(values):
    if not isinstance(values,dict) or set(values)-set(DEFAULTS):raise ValueError('Field audio M6 tidak dikenal')
    out=copy.deepcopy(values)
    for key,v in out.items():
        if key in BOOLS:
            if type(v) is not bool:raise ValueError(key+' harus boolean')
        elif key in NUMBERS:out[key]=number(v,*NUMBERS[key],key)
        elif key=='denoise':
            if v not in ('off','fft','nlmeans'):raise ValueError('Denoise tidak dikenal')
        elif key=='hum_hz':
            if type(v) not in (int,float) or v not in (0,50,60):raise ValueError('Hum memakai 0, 50 atau 60 Hz')
        elif key=='separation':
            if v not in ('off','demucs'):raise ValueError('Pemisahan memakai model Demucs lokal atau nonaktif')
        elif key=='model_directory':out[key]=text(v,2000,'Folder model')
        elif key=='model_name':
            if not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',v):raise ValueError('Nama model tidak valid')
        elif key=='eq_bands':
            if not isinstance(v,list) or len(v)>8:raise ValueError('EQ maksimal delapan band')
            out[key]=[]
            for row in v:
                if not isinstance(row,dict) or set(row)!={'hz','gain_db','q'}:raise ValueError('Band EQ memakai hz, gain_db dan q')
                out[key].append({'hz':number(row['hz'],20,20000,'Frekuensi EQ'),'gain_db':number(row['gain_db'],-12,12,'Gain EQ'),'q':number(row['q'],.1,8,'Q EQ')})
    return out

def effective(cfg):
    base={**copy.deepcopy(DEFAULTS),'normalize':cfg.audio_normalize,'target_lufs':cfg.audio_target_lufs,
          'peak_db':cfg.audio_peak_db,'smooth_ms':cfg.join_fade_ms,'sfx_enabled':cfg.sfx_mode!='off'}
    return {**base,**settings((cfg.audio6 or {}).get('settings',{}))}

def tracks(rows):
    if not isinstance(rows,list) or len(rows)>24:raise ValueError('M6 maksimal 24 track tambahan')
    out=[];ids=set()
    defaults=dict(enabled=True,muted=False,start=0.,end=5.,asset_start=0.,gain_db=-18.,
        fade_in=.08,fade_out=.15,loop=False,loop_crossfade=.04,timebase='output',
        beat_bpm=0.,beat_offset=0.,beat_snap=False,language='',speaker_id='',reviewed=False,replace_source=False)
    allowed={'id','role','asset_id',*defaults}
    for row in rows:
        if not isinstance(row,dict) or set(row)-allowed:raise ValueError('Field track audio tidak dikenal')
        r={**defaults,**copy.deepcopy(row)}
        r['id']=text(r.get('id'),80,'ID track')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',r['id']) or r['id'] in ids:raise ValueError('ID track harus unik')
        ids.add(r['id'])
        if r.get('role') not in ROLES:raise ValueError('Peran track audio tidak dikenal')
        r['asset_id']=text(r.get('asset_id'),100,'ID aset')
        if not r['asset_id']:raise ValueError('Pilih aset audio lokal')
        for k in ('enabled','muted','loop','beat_snap','reviewed','replace_source'):
            if type(r[k]) is not bool:raise ValueError(k+' harus boolean')
        for k,lo,hi in [('start',0,86400),('end',0,86400),('asset_start',0,86400),('gain_db',-60,12),('fade_in',0,10),('fade_out',0,10),('loop_crossfade',0,2),('beat_bpm',0,250),('beat_offset',-60,60)]:r[k]=number(r[k],lo,hi,k)
        if r['end']<=r['start'] or r['end']-r['start']>MAX_SECONDS:raise ValueError('Durasi track harus positif, maksimal 600 detik')
        if r['fade_in']+r['fade_out']>r['end']-r['start']:raise ValueError('Fade track melebihi durasi')
        if r['timebase'] not in ('source','output'):raise ValueError('Clock track memakai source/output')
        if r['beat_snap'] and (r['timebase']!='output' or r['beat_bpm']<20):raise ValueError('Beat snap membutuhkan BPM 20–250 dan clock output')
        for k in ('language','speaker_id'):r[k]=text(r[k],96,k)
        if r['role']=='dubbing' and (not r['language'] or not r['speaker_id'] or not r['reviewed']):raise ValueError('Dubbing memerlukan bahasa, speaker dan review')
        if r['replace_source'] and (r['role']!='dubbing' or not r['reviewed']):raise ValueError('Penggantian suara hanya untuk dubbing yang ditinjau')
        if r['role']!='music' and r['loop']:raise ValueError('Loop hanya untuk musik')
        out.append(r)
    return out

def asset_signature(state,*,fresh=False):
    from .dependency_cache import asset_id,model_identity
    return {'assets':[(r['id'],asset_id(r['asset']['path'],fresh=fresh)) for r in (state or {}).get('tracks',[]) if r.get('enabled') and not r.get('muted') and r.get('asset')],
            'model':model_identity(state['settings']['model_directory'],fresh=fresh) if state and state.get('settings',{}).get('separation')=='demucs' else []}
