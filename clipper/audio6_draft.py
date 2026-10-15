"""Lossless M6 panel draft adapter for the shared review/snapshot workflow."""
import json
import math
from .audio6_contract import DEFAULTS,settings,tracks

TRACK_NUMBERS={'start','end','asset_start','gain_db','fade_in','fade_out','loop_crossfade','beat_bpm','beat_offset'}

def number(raw,key):
    if not isinstance(raw,str) or not raw.strip():raise ValueError('Angka M6 belum lengkap: '+key)
    try:value=float(raw)
    except ValueError as exc:raise ValueError('Angka M6 belum lengkap: '+key) from exc
    if not math.isfinite(value):raise ValueError('Angka M6 harus finite: '+key)
    return value

def operations(value):
    fields=value.get('fields')
    if not isinstance(fields,dict) or set(fields)-set(DEFAULTS)-{'enabled','tracks'} or any(not isinstance(v,str) for v in fields.values()):
        raise ValueError('Kolom draf M6 tidak dikenal atau rusak; ekspor salinannya dahulu')
    values={};out=[]
    for key,raw in fields.items():
        if key in ('enabled','tracks'):continue
        default=DEFAULTS[key]
        if isinstance(default,bool):
            if raw not in ('true','false'):raise ValueError('Boolean draf M6 tidak valid: '+key)
            parsed=raw=='true'
        elif isinstance(default,(float,int)):parsed=number(raw,key)
        elif isinstance(default,list):parsed=json.loads(raw)
        else:parsed=raw
        values[key]=parsed
    if values:out.append({'op':'m6_settings','values':settings(values)})
    if 'tracks' in fields:
        rows=json.loads(fields['tracks'])
        if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise ValueError('Draf track M6 rusak')
        parsed=[{k:number(v,k) if k in TRACK_NUMBERS else v for k,v in row.items()} for row in rows]
        out.append({'op':'m6_tracks','values':tracks(parsed)})
    if 'enabled' in fields:
        if fields['enabled'] not in ('true','false'):raise ValueError('Enabled draf M6 harus boolean')
        out.append({'op':'m6_enable','enabled':fields['enabled']=='true'})
    return out
