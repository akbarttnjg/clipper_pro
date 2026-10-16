"""Auditable source derivatives: fixed FFmpeg operations before subtitles/editor.

The original is untouched. A recipe is frozen against exact source/revision.
No arbitrary filter string, automatic pan, hook, generative fill or hidden crop.
"""
import copy
import json
from pathlib import Path
from .m8_contract import AccessDenied, canonical, integer, only, text
from .m8_store import ident
from .m9_contract import artifact, atomic_bytes, number, spans
from .m9_media import available_filters, run, verify_media
from .dependency_cache import content_id
from .project_store import Conflict

FILTERS = {'color': 'eq', 'curves': 'curves', 'denoise': 'hqdn3d', 'upscale': 'scale', 'interpolate': 'minterpolate','chroma':'chromakey','overlay':'overlay',
    'lens': 'lenscorrection', 'stabilize': 'deshake', 'v360': 'v360', 'fade': 'fade', 'blur': 'boxblur', 'mosaic': 'scale', 'lut': 'lut3d'}


def recipe(value, duration, size, *, no_pan=True):
    only(value, ('operations', 'no_pan', 'protected_regions', 'material_reviewed','hook','version'), ('operations', 'material_reviewed'))
    if 'version' in value and (type(value['version']) is not int or value['version']!=1):raise ValueError('Versi resep belum didukung')
    if value.get('hook',False) is not False:raise ValueError('Hook tidak dijalankan pada efek sumber')
    if value['material_reviewed'] is not True:raise ValueError('Periksa wajah, teks, slide, dan area penting dahulu')
    if value.get('no_pan', True) is not True:raise ValueError('Rilis ini menjaga no-pan; pan bergerak belum dibuka')
    operations = value['operations']
    if not isinstance(operations, list) or not 1 <= len(operations) <= 12:raise ValueError('Resep memerlukan 1–12 operasi')
    protected = value.get('protected_regions', [])
    if not isinstance(protected, list) or len(protected) > 30:raise ValueError('Area penting tidak valid')
    w, h = size
    def rectangle(row):
        if not isinstance(row, list) or len(row) != 4:raise ValueError('Area harus [x,y,w,h]')
        x,y,rw,rh = [integer(v, 'Koordinat', 0, max(w,h)) for v in row]
        if rw < 2 or rh < 2 or x+rw > w or y+rh > h:raise ValueError('Area keluar dari gambar')
        return [x,y,rw,rh]
    protected = [rectangle(r) for r in protected];result = [];geometry_seen = False
    for original in operations:
        if not isinstance(original, dict):raise ValueError('Operasi harus object')
        op = copy.deepcopy(original);kind = op.get('kind')
        if kind not in FILTERS:raise ValueError('Efek belum tersedia pada rilis ini: '+str(kind))
        if geometry_seen:raise ValueError('Efek geometri/resolusi harus operasi terakhir agar koordinat area tetap benar')
        if kind == 'color':
            only(op, ('kind','brightness','contrast','saturation','gamma'))
            for key, default, low, high in [('brightness',0,-.3,.3),('contrast',1,.5,2),('saturation',1,0,2),('gamma',1,.5,2)]:op[key] = number(op.get(key,default), key,low,high)
        elif kind == 'curves':
            only(op, ('kind','points'), ('kind','points'))
            pts = op['points']
            if not isinstance(pts,list) or not 2 <= len(pts) <= 16:raise ValueError('Kurva memerlukan 2–16 titik')
            last = -1.
            for p in pts:
                if not isinstance(p,list) or len(p)!=2:raise ValueError('Titik kurva [x,y]')
                x=number(p[0],'x',0,1);number(p[1],'y',0,1)
                if x<=last:raise ValueError('Titik kurva harus berurutan')
                last=x
        elif kind == 'denoise':
            only(op, ('kind','strength'));op['strength']=number(op.get('strength',2),'Kekuatan denoise',.1,6)
        elif kind == 'upscale':
            only(op, ('kind','width','height'), ('kind','width','height'))
            for key in ('width','height'):
                op[key]=integer(op[key],key,64,3840)
                if op[key]%2:raise ValueError('Resolusi harus genap')
            if op['width']*h != op['height']*w:raise ValueError('Upscale harus menjaga rasio sumber')
            if op['width']<w or op['height']<h:raise ValueError('Pilih resolusi yang tidak lebih kecil')
            geometry_seen=True
        elif kind == 'interpolate':
            only(op,('kind','fps'),('kind','fps'));op['fps']=integer(op['fps'],'FPS',24,60)
            if duration>120 or w*h>1920*1080:raise ValueError('Interpolasi CPU dibatasi 120 detik dan 1080p')
        elif kind == 'lens':
            only(op, ('kind','k1','k2','crop_reviewed'), ('kind','crop_reviewed'))
            if op['crop_reviewed'] is not True or protected:raise ValueError('Koreksi lensa perlu review tepi dan tidak boleh mengubah area penting terlindungi')
            op['k1']=number(op.get('k1',0),'k1',-.5,.5);op['k2']=number(op.get('k2',0),'k2',-.5,.5);geometry_seen=True
        elif kind == 'stabilize':
            only(op,('kind','crop_reviewed'),('kind','crop_reviewed'))
            if op['crop_reviewed'] is not True or protected:raise ValueError('Stabilisasi perlu review tepi; area penting harus diperiksa pada salinan')
            geometry_seen=True
        elif kind == 'v360':
            only(op,('kind','projection','yaw','pitch','fov','width','height'),('kind','projection','width','height'))
            if op['projection']!='equirectangular':raise ValueError('Hanya sumber equirectangular yang dinyatakan pengguna')
            for key in ('width','height'):op[key]=integer(op[key],key,64,1920)
            if op['width']%2 or op['height']%2:raise ValueError('Resolusi viewport harus genap')
            op['yaw']=number(op.get('yaw',0),'Yaw',-180,180);op['pitch']=number(op.get('pitch',0),'Pitch',-89,89);op['fov']=number(op.get('fov',90),'FOV',30,120)
            if protected:raise ValueError('Viewport 360 harus direview terpisah dari area penting sumber')
            geometry_seen=True
        elif kind == 'fade':
            only(op,('kind','direction','start','duration'),('kind','direction','start','duration'))
            if op['direction'] not in ('in','out'):raise ValueError('Arah fade tidak valid')
            op['start']=number(op['start'],'Awal fade',0,duration);op['duration']=number(op['duration'],'Durasi fade',.04,min(3,duration))
            if op['start']+op['duration']>duration:raise ValueError('Fade melewati akhir media')
        elif kind in ('blur','mosaic'):
            only(op,('kind','rect','ranges','strength'),('kind','rect','ranges'))
            op['rect']=rectangle(op['rect']);op['ranges']=spans(op['ranges'],duration)
            if not op['ranges']:raise ValueError('Pilih interval mask')
            x,y,rw,rh=op['rect']
            if any(x<px+pw and x+rw>px and y<py+ph and y+rh>py for px,py,pw,ph in protected):raise ValueError('Mask menutupi area penting terlindungi')
            op['strength']=integer(op.get('strength',10),'Kekuatan mask',2,30)
        elif kind == 'lut':
            only(op,('kind','asset_id'),('kind','asset_id'));text(op['asset_id'],'LUT terdaftar',100)
        elif kind=='chroma':
            import re
            only(op,('kind','key_color','background','similarity','blend','edges_reviewed'),('kind','key_color','background','edges_reviewed'))
            if op['edges_reviewed'] is not True or protected:raise ValueError('Chroma perlu review tepi/materi; area penting tidak boleh dikunci warnanya')
            for key in ('key_color','background'):
                if not isinstance(op[key],str) or not re.fullmatch('#[0-9a-fA-F]{6}',op[key]):raise ValueError('Warna harus #RRGGBB')
            op['similarity']=number(op.get('similarity',.1),'Similarity',.01,.4);op['blend']=number(op.get('blend',.05),'Feather/blend',0,.3)
        elif kind=='overlay':
            only(op,('kind','asset_id','rect','opacity','ranges'),('kind','asset_id','rect','ranges'))
            text(op['asset_id'],'ID gambar',100);op['rect']=rectangle(op['rect']);op['ranges']=spans(op['ranges'],duration);op['opacity']=number(op.get('opacity',1),'Opacity',.01,1)
            if not op['ranges']:raise ValueError('Pilih interval overlay')
            x,y,rw,rh=op['rect']
            if any(x<px+pw and x+rw>px and y<py+ph and y+rh>py for px,py,pw,ph in protected):raise ValueError('Overlay menutupi materi terlindungi')
        result.append(op)
    return {'operations':result,'no_pan':True,'protected_regions':protected,'material_reviewed':True,'hook':False,'version':1}


class Effects:
    def __init__(self, lab):self.lab=lab;self.service=lab.service;self.m8=lab.m8

    def prepare(self, actor, data):
        only(data,('project_id','expected_revision','recipe','start','end'),('project_id','expected_revision','recipe'))
        pid=data['project_id'];self.m8.workspaces.require(actor,'edit',pid);doc=self.service.store.get(pid)
        if doc['revision']!=data['expected_revision']:raise Conflict(doc['revision'])
        if content_id(doc['source']['path'],fresh=True)!=doc['source']['source_id']:raise ValueError('Sumber berubah')
        info=doc['source']['info']
        if info['kind']!='video':raise ValueError('Efek visual memerlukan video')
        # Explicit SDR support avoids silently applying SDR controls to HDR footage.
        if info.get('color_transfer') in ('smpte2084','arib-std-b67'):raise ValueError('Konversi HDR ke SDR perlu dikerjakan/review dahulu')
        a=number(data.get('start',0),'Awal',0,info['duration']);b=number(data.get('end',info['duration']),'Akhir',a,info['duration'])
        if b<=a or b-a>3600:raise ValueError('Rentang efek 0–3600 detik')
        normalized=recipe(data['recipe'],b-a,info['display_size'])
        filters=available_filters();missing=sorted({FILTERS[o['kind']] for o in normalized['operations']}-filters)
        if missing:raise ValueError('FFmpeg ini belum memiliki filter: '+', '.join(missing))
        assets={}
        for op in normalized['operations']:
            if op['kind'] in ('lut','overlay'):
                item=self.lab.store.get(actor,op['asset_id'])
                if op['kind']=='lut' and item['kind']!='lut':raise ValueError('Aset bukan LUT')
                if op['kind']=='overlay':
                    if item['kind']!='media':raise ValueError('Overlay harus aset gambar M9')
                    from PIL import Image
                    with Image.open(item['data']['path']) as image:image.verify()
                assets[item['id']]=item['data']
        return {'project_id':pid,'input_revision':doc['revision'],'source_path':doc['source']['path'],'source_content_id':doc['source']['source_id'],
            'audio_stream_index':self.service.config(doc).audio_stream_index,'output_fps':self.service.config(doc).output_fps,'display_size':info['display_size'],
            'recipe':normalized,'assets':assets,'start':a,'end':b,'fps':info['fps'],'workspace':actor.workspace,'name':doc['name']+' — efek M9'}

    def register_lut(self, actor, data):
        only(data,('path','license','name'),('path','license','name'))
        if not actor.local:raise AccessDenied('Registrasi LUT dari path memerlukan operator lokal')
        path=Path(data['path']).expanduser().resolve()
        if not path.is_file() or path.suffix.lower()!='.cube' or path.stat().st_size>16*1024**2:raise ValueError('LUT .cube maksimal 16 MiB')
        raw=path.read_bytes();lines=raw.decode('utf-8-sig').splitlines();size=None;rows=[]
        for line in lines:
            line=line.strip()
            if not line or line.startswith(('#','TITLE','DOMAIN_MIN','DOMAIN_MAX')):continue
            if line.startswith('LUT_3D_SIZE'):
                size=integer(int(line.split()[1]),'Ukuran LUT',2,64);continue
            vals=line.split()
            if len(vals)!=3:raise ValueError('LUT memuat perintah tidak didukung')
            rows.append([number(float(v),'Nilai LUT',-1,4) for v in vals])
        if size is None or len(rows)!=size**3:raise ValueError('Jumlah nilai LUT tidak cocok')
        key=ident('m9lut');target=self.lab.root/'assets'/(key+'.cube');atomic_bytes(target,raw)
        return self.lab.store.create(actor,'lut',{'name':text(data['name'],'Nama',100),'path':str(target),'content_id':content_id(target,fresh=True),'license':text(data['license'],'Lisensi',2000)},key)

    def graph(self, snapshot, folder):
        parts=[];label='0:v:0';overlay_input=1
        for index,op in enumerate(snapshot['recipe']['operations']):
            kind=op['kind'];output='f'+str(index)
            if kind=='color':f='eq='+':'.join(f'{k}={op[k]:.6f}' for k in ('brightness','contrast','saturation','gamma'))
            elif kind=='curves':f="curves=all='"+' '.join(f'{p[0]:.6f}/{p[1]:.6f}' for p in op['points'])+"'"
            elif kind=='denoise':s=op['strength'];f=f'hqdn3d={s:.6f}:{s:.6f}:{s*1.5:.6f}:{s*1.5:.6f}'
            elif kind=='upscale':f=f'scale={op["width"]}:{op["height"]}:flags=lanczos'
            elif kind=='interpolate':f=f'minterpolate=fps={op["fps"]}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir'
            elif kind=='lens':f=f'lenscorrection=k1={op["k1"]:.6f}:k2={op["k2"]:.6f}:i=bilinear'
            elif kind=='stabilize':f='deshake=rx=16:ry=16:edge=blank'
            elif kind=='v360':f=f'v360=input=equirect:output=flat:w={op["width"]}:h={op["height"]}:yaw={op["yaw"]:.6f}:pitch={op["pitch"]:.6f}:h_fov={op["fov"]:.6f}'
            elif kind=='fade':f=f'fade=t={op["direction"]}:st={op["start"]:.6f}:d={op["duration"]:.6f}'
            elif kind=='chroma':
                key=op['key_color'].replace('#','0x');bg=op['background'].replace('#','0x')
                # A generated uniform background is sized from the source link;
                # scale2ref keeps dimensions exact even after earlier filters.
                rate=snapshot['fps'];framerate=str(rate['numerator'])+'/'+str(rate['denominator'])
                parts.append(f'color=c={bg}:s=16x16:r={framerate}:d={snapshot["end"]-snapshot["start"]:.6f}[bg{index}]')
                parts.append(f'[bg{index}][{label}]scale2ref[bgfit{index}][src{index}]')
                parts.append(f'[src{index}]chromakey=color={key}:similarity={op["similarity"]:.6f}:blend={op["blend"]:.6f}[key{index}]')
                parts.append(f'[bgfit{index}][key{index}]overlay=shortest=1[{output}]');label=output;continue
            elif kind=='overlay':
                x,y,w,h=op['rect'];enabled='+'.join(f'between(t,{a:.6f},{b:.6f})' for a,b in op['ranges'])
                parts.append(f'[{overlay_input}:v:0]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x00000000,format=rgba,colorchannelmixer=aa={op["opacity"]:.6f}[overlay{index}]')
                parts.append(f'[{label}][overlay{index}]overlay={x}:{y}:enable=\'{enabled}\':eof_action=repeat[{output}]');label=output;overlay_input+=1;continue
            elif kind=='lut':
                item=snapshot['assets'][op['asset_id']];path=Path(item['path'])
                if content_id(path,fresh=True)!=item['content_id']:raise ValueError('LUT berubah')
                # Short generated name, relative to process-independent absolute escaped path.
                copied=folder/('lut'+str(index)+'.cube');copied.write_bytes(path.read_bytes())
                escaped=str(copied).replace('\\','/').replace(':','\\:').replace("'","'\\''")
                f="lut3d=file='"+escaped+"'"
            elif kind in ('blur','mosaic'):
                x,y,w,h=op['rect'];strength=op['strength'];base='b'+str(index);roi='r'+str(index)
                parts.append(f'[{label}]split=2[{base}][{roi}]')
                if kind=='blur':transform=f'boxblur=luma_radius={min(strength,(min(w,h)-1)//2)}:luma_power=2'
                else:transform=f'scale={max(1,w//strength)}:{max(1,h//strength)}:flags=neighbor,scale={w}:{h}:flags=neighbor'
                parts.append(f'[{roi}]crop={w}:{h}:{x}:{y},{transform}[m{index}]')
                enabled='+'.join(f'between(t,{a:.6f},{b:.6f})' for a,b in op['ranges'])
                parts.append(f'[{base}][m{index}]overlay={x}:{y}:enable=\'{enabled}\'[{output}]');label=output;continue
            parts.append(f'[{label}]{f}[{output}]');label=output
        parts.append(f'[{label}]setsar=1,format=yuv420p[out]')
        return ';'.join(parts)

    def execute(self, job):
        snap=job['request']['m9'];actor=self.lab.operator(snap['workspace']);pid=snap['project_id']
        folder=self.lab.root/'effects'/job['id'];folder.mkdir(parents=True,exist_ok=True)
        def check():
            self.lab.check_job(job)
            doc=self.service.store.get(pid)
            if doc['revision']!=snap['input_revision']:
                from .studio_worker import StaleJob
                raise StaleJob('Revisi/sumber efek berubah; hasil tidak diaktifkan')
        check()
        if content_id(snap['source_path'],fresh=True)!=snap['source_content_id']:raise ValueError('Sumber efek berubah')
        from dataclasses import replace
        from .media_context import prepare
        parent_cfg=self.service.config(self.service.store.get(pid))
        cfg=replace(self.service.base,audio_stream_index=snap.get('audio_stream_index',parent_cfg.audio_stream_index),output_fps=snap.get('output_fps',parent_cfg.output_fps))
        context=prepare(snap['source_path'],cfg)['payload']
        check()
        if context['source_content_id']!=snap['source_content_id']:raise ValueError('Sumber efek berubah saat normalisasi')
        working=context['working_path']
        render_snap={**snap,'fps':context['fps']}
        graph=self.graph(render_snap,folder);out=folder/'effect-source.mp4';duration=snap['end']-snap['start']
        # -ss before input re-bases both audio and video together; subtitles are
        # not present at this source-derivative stage.
        overlay_inputs=[]
        for op in snap['recipe']['operations']:
            if op['kind']=='overlay':
                item=snap['assets'][op['asset_id']];path=Path(item['path']);expected=item['artifact']['content_id']
                if content_id(path,fresh=True)!=expected:raise ValueError('Gambar overlay berubah')
                overlay_inputs+=['-loop','1','-i',str(path)]
        metrics=run(['-ss',str(snap['start']),'-i',working,*overlay_inputs,'-t',str(duration),'-filter_complex',graph,
            '-map','[out]','-map','0:a:0','-c:v','libx264','-preset','veryfast','-crf','18','-c:a','aac','-ar','48000','-movflags','+faststart',str(out)],check=check)
        info=verify_media(out,check=check)
        if abs(info['duration']-duration)>.15:raise ValueError('Efek mengubah durasi melewati toleransi 150 ms')
        expected_size=list(snap.get('display_size',context['display_size']))
        for op in snap['recipe']['operations']:
            if op['kind'] in ('upscale','v360'):expected_size=[op['width'],op['height']]
        if info['display_size']!=expected_size or info['sample_aspect_ratio']!={'numerator':1,'denominator':1}:
            raise ValueError('Geometri keluaran efek berbeda dari bidang tampilan resep')
        if content_id(working,fresh=True)!=context['working_content_id']:raise ValueError('Media kanonis efek berubah')
        manifest={'schema_version':1,'kind':'effects9','source_project':pid,'source_revision':snap['input_revision'],'source_content_id':snap['source_content_id'],
            'source_range':[snap['start'],snap['end']],'media_context':context,'recipe':snap['recipe'],'output':artifact(out),'filter_plan':graph,
            'media_info':{k:info[k] for k in ('duration','display_size','fps','color_transfer','color_space')},'metrics':metrics,
            'synthetic':False,'editable_native_effects':False,'caption_stage':'before captions; analyze derivative to create correctly timed transcript',
            'quality_acceptance':'full decode passed; visual artifact/material comparison required'}
        manifest_path=folder/'effects9.json';atomic_bytes(manifest_path,(canonical(manifest)+'\n').encode());check()
        if content_id(snap['source_path'],fresh=True)!=snap['source_content_id']:raise ValueError('Sumber efek berubah selama render')
        result=self.lab.publish_derivative(job,actor,out,snap['name'],{'kind':'effects9','manifest':str(manifest_path),
            'parent_project_id':pid,'parent_revision':snap['input_revision'],'parent_source_content_id':snap['source_content_id'],'source_range':[snap['start'],snap['end']]},manifest_path,
            source_guard={'project_id':pid,'revision':snap['input_revision'],'content_id':snap['source_content_id']})
        return result
