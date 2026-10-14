"""M4 camera geometry: source seconds/pixels, immutable evidence, explicit motion."""
import copy
import math
from .contracts import fingerprint

VERSION='4.0.15-m4'
LAYOUTS=('auto','fit','subject','grid','screen','pip','gameplay')
PROFILES=('general','education','podcast','screen','gaming')


def number(value,name='Nilai'):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError(name+' harus angka terukur')
    return float(value)


def box(value,width=100.,height=100.):
    if not isinstance(value,list) or len(value)!=4:raise ValueError('Area harus [x,y,lebar,tinggi]')
    x,y,w,h=[number(v,'Koordinat') for v in value]
    if min(x,y)<0 or min(w,h)<=0 or x+w>width+1e-6 or y+h>height+1e-6:raise ValueError('Area berada di luar sumber')
    return [x,y,w,h]


def controls(value,duration):
    defaults={'profile':'general','layout':'auto','motion':'static','background':'pillarbox','detect_faces':True,
        'ocr':True,'active_speaker':'auto','frame_budget':180,'interval_seconds':.5,'scene_threshold':.30,
        'deadzone':.05,'smoothing':.65,'max_speed':.15,'safe_margins':[.04,.06,.10,.18],
        'regions':[],'keyframes':[],'speaker_links':[],'shot_overrides':[],'tracker':None,'mask':None,'attachment':None}
    if not isinstance(value,dict) or set(value)-set(defaults):raise ValueError('Pengaturan kamera M4 tidak dikenal')
    result={**defaults,**copy.deepcopy(value)}
    for key,choices in [('profile',PROFILES),('layout',LAYOUTS),('motion',('static','track','manual')),('background',('pillarbox','blur')),('active_speaker',('auto','off'))]:
        if result[key] not in choices:raise ValueError(key+' tidak dikenal')
    for key in ('detect_faces','ocr'):
        if type(result[key]) is not bool:raise ValueError(key+' harus boolean')
    if type(result['frame_budget']) is not int or not 8<=result['frame_budget']<=600:raise ValueError('Anggaran frame 8–600')
    for key,lo,hi in [('interval_seconds',.1,5),('scene_threshold',.05,.9),('deadzone',0,.3),('smoothing',0,.95),('max_speed',.01,.5)]:
        result[key]=number(result[key],key)
        if not lo<=result[key]<=hi:raise ValueError(key+' di luar batas')
    if result['profile']=='education' and result['motion']!='static':raise ValueError('Profil edukasi no-pan harus statis; pilih profil lain untuk gerak eksplisit')
    margins=result['safe_margins']
    if not isinstance(margins,list) or len(margins)!=4 or any(not 0<=number(v)<=.3 for v in margins):raise ValueError('Margin platform harus kiri,atas,kanan,bawah (0–0.3)')
    if margins[0]+margins[2]>=.6 or margins[1]+margins[3]>=.6:raise ValueError('Area aman platform terlalu kecil')
    for key,limit in [('regions',64),('keyframes',64),('speaker_links',32),('shot_overrides',100)]:
        if not isinstance(result[key],list) or len(result[key])>limit:raise ValueError(key+' melebihi anggaran')
    ids=set()
    for row in result['regions']:
        if not isinstance(row,dict) or set(row)-{'id','kind','start','end','box'}:raise ValueError('Area sumber tidak valid')
        if row.get('kind') not in ('subject','material','hud','protected','object','crop'):raise ValueError('Jenis area tidak dikenal')
        if not isinstance(row.get('id'),str) or not 1<=len(row['id'])<=100 or row['id'] in ids:raise ValueError('ID area harus unik')
        ids.add(row['id']);row['box']=box(row.get('box'))
        if not 0<=number(row.get('start'))<number(row.get('end'))<=duration:raise ValueError('Rentang area di luar sumber')
    last=-1
    for row in result['keyframes']:
        if not isinstance(row,dict) or set(row)!={'time','box'}:raise ValueError('Keyframe harus time dan box')
        t=number(row['time']);row['box']=box(row['box'])
        if not 0<=t<=duration or t<=last:raise ValueError('Keyframe harus urut dalam detik sumber')
        last=t
    if result['keyframes'] and result['motion']!='manual':raise ValueError('Keyframe hanya aktif pada gerak manual')
    if result['keyframes'] and any(r['box'][2:]!=result['keyframes'][0]['box'][2:] for r in result['keyframes']):raise ValueError('Ukuran crop keyframe harus tetap; x/y dapat berubah')
    for row in result['speaker_links']:
        if not isinstance(row,dict) or set(row)!={'speaker_id','track_id','reviewed'} or row['reviewed'] is not True or not all(isinstance(row[k],str) and row[k] for k in ('speaker_id','track_id')):raise ValueError('Pemetaan suara-wajah memerlukan tinjauan manusia')
    for row in result['shot_overrides']:
        if not isinstance(row,dict) or set(row)-{'shot_id','layout','subject_ids'} or not isinstance(row.get('shot_id'),str) or row.get('layout') not in LAYOUTS:raise ValueError('Override adegan tidak valid')
        if not isinstance(row.get('subject_ids',[]),list) or any(not isinstance(i,str) for i in row.get('subject_ids',[])):raise ValueError('ID subjek tidak valid')
    for key in ('tracker','mask'):
        row=result[key]
        if row is None:continue
        allowed={'start','end','time','box','mode'} if key=='tracker' else {'start','end','time','box'}
        if not isinstance(row,dict) or set(row)!=allowed:raise ValueError(key+' tidak lengkap')
        a,b,t=number(row['start']),number(row['end']),number(row['time']);row['box']=box(row['box'])
        if not 0<=a<=t<b<=duration or b-a>(30 if key=='tracker' else 6):raise ValueError('Rentang '+key+' di luar batas')
        if key=='tracker' and row['mode'] not in ('object','planar'):raise ValueError('Mode tracker tidak dikenal')
    attachment=result['attachment']
    if attachment is not None:
        if not isinstance(attachment,dict) or set(attachment)!={'path','opacity'} or not isinstance(attachment['path'],str) or not attachment['path'] or not 0<number(attachment['opacity'])<=1:raise ValueError('Attachment harus gambar lokal dan opacity (0–1)')
        if result['tracker'] is None:raise ValueError('Attachment memerlukan tracker objek/planar')
    return result


def pixels(percent,width,height):return [v*s/100 for v,s in zip(box(percent),(width,height,width,height))]


def spans(clip):
    rows=clip.get('source_spans') or [{'start':clip['start'],'end':clip['end']}]
    ordered=sorted((number(r['start']),number(r['end'])) for r in rows);merged=[]
    for a,b in ordered:
        if a>=b:raise ValueError('Span kamera tidak valid')
        if merged and a<=merged[-1][1]+1e-6:merged[-1][1]=max(merged[-1][1],b)
        else:merged.append([a,b])
    if sum(b-a for a,b in merged)>1800:raise ValueError('Analisis kamera dibatasi 30 menit bahan klip per tugas')
    return merged


def fit(region,viewport):
    x,y,w,h=region;vx,vy,vw,vh=viewport;scale=min(vw/w,vh/h)
    return [scale,vx+(vw-w*scale)/2-x*scale,vy+(vh-h*scale)/2-y*scale]


def intersection(a,b):
    x,y=max(a[0],b[0]),max(a[1],b[1]);right,bottom=min(a[0]+a[2],b[0]+b[2]),min(a[1]+a[3],b[1]+b[3])
    return [x,y,max(0,right-x),max(0,bottom-y)]


def projected(region,viewport,protected):
    scale,dx,dy=fit(region,viewport);hit=intersection(region,protected)
    return [hit[0]*scale+dx,hit[1]*scale+dy,hit[2]*scale,hit[3]*scale] if min(hit[2:])>0 else None


def crop(area,subject,aspect):
    from .framing import crop_rect
    return crop_rect(area,subject,aspect)


def smoothed_path(observations,initial,settings,width,height):
    """Opt-in only; deadzone/speed bound in source pixels, no identity switching."""
    x,y,w,h=initial;path=[];last=None
    for row in observations:
        t=row['time'];b=row['box'];tx=max(0,min(width-w,b[0]+b[2]/2-w/2));ty=max(0,min(height-h,b[1]+b[3]*1.4-h/2))
        if last is not None:
            dt=max(0,t-last);cap=settings['max_speed']*width*dt
            for axis,target,size in ((0,tx,width),(1,ty,height)):
                current=x if axis==0 else y;delta=target-current
                moved=0 if abs(delta)<=settings['deadzone']*size else max(-cap,min(cap,delta*(1-settings['smoothing'])))
                if axis==0:x+=moved
                else:y+=moved
        path.append({'time':t,'box':[x,y,w,h]});last=t
    return path
