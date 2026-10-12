"""Clear-time intervals; frame-held ASS/Remotion is the production default.

Linear interpolation is supported for declared analytical fixtures. It must not
be silently substituted for the frame-held renderer used by current plans.
"""
import math


def _clear(frame):
    values=[frame.get(k,v) for k,v in [('opacity',1.),('blur',0.),('scale',1.)]]
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):return False
    opacity,blur,scale=values
    return .98<=opacity<=1 and 0<=blur<=.5 and .975<=scale<=1.025


def _linear(a,b):
    left,right=0.,1.
    for key,default,low,high in [('opacity',1.,.98,1.),('blur',0.,0.,.5),('scale',1.,.975,1.025)]:
        x,y=a.get(key,default),b.get(key,default)
        if not all(type(v) in (int,float) and math.isfinite(v) for v in (x,y)):return None
        if x==y:
            if not low<=x<=high:return None
            continue
        crossings=sorted(((low-x)/(y-x),(high-x)/(y-x)))
        left=max(left,crossings[0]);right=min(right,crossings[1])
    return (left,right) if right>left else None


def clear_time(word,duration,*,interpolation='hold'):
    if type(duration) not in (int,float) or not math.isfinite(duration) or duration<=0:
        raise ValueError('Durasi caption tidak valid.')
    if interpolation not in ('hold','linear'):raise ValueError('Interpolasi caption belum didukung.')
    frames=word.get('keyframes') or []
    intervals=[]
    if not frames:
        fade=word.get('fade_seconds',min(.065,duration/4))
        if type(fade) not in (int,float) or not math.isfinite(fade) or fade<0:raise ValueError('Fade caption tidak valid.')
        start,end=.98*fade,duration-.98*fade
        if end>start:intervals=[(start,end)]
    else:
        times=[frame.get('t') for frame in frames]
        if any(type(t) not in (int,float) or not math.isfinite(t) for t in times) or times!=sorted(times):
            raise ValueError('Keyframe caption harus mempunyai waktu berurutan dan finite.')
        for a,b in zip(frames,frames[1:]):
            if b['t']<=a['t']:continue
            if interpolation=='hold':
                candidate=(a['t'],b['t']) if _clear(a) else None
            else:
                fraction=_linear(a,b)
                candidate=(a['t']+(b['t']-a['t'])*fraction[0],a['t']+(b['t']-a['t'])*fraction[1]) if fraction else None
            if candidate:
                start,end=max(0.,candidate[0]),min(duration,candidate[1])
                if end>start:intervals.append((start,end))
    merged=[]
    for start,end in sorted(intervals):
        if merged and start<=merged[-1][1]+1e-9:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:merged.append((start,end))
    return {'total_clear_seconds':round(sum(b-a for a,b in merged),6),
            'longest_contiguous_clear':round(max((b-a for a,b in merged),default=0.),6),
            'clear_intervals':[[round(a,6),round(b,6)] for a,b in merged],
            'interpolation':interpolation,'measurement_scope':'caption_plan_opacity_blur_scale'}
