"""All subtitle/transcript formats derive from one frozen caption revision."""
import copy,html,math,re,shutil
from pathlib import Path
from .storage import write_json
from .dependency_cache import content_id


def cue_rows(plan):
    duration=float(plan['duration']);out=[]
    if not math.isfinite(duration) or duration<=0:raise ValueError('Durasi subtitle tidak valid')
    for i,phrase in enumerate(plan.get('captions',{}).get('phrases',[])):
        a=float(phrase['start']);b=float(phrase['end'])
        if not math.isfinite(a+b) or not 0<=a<b<=duration+.001:raise ValueError('Batas subtitle di luar final')
        words=copy.deepcopy(phrase.get('words',[]))
        text=' '.join(str(w.get('text',w.get('word',''))).replace('\r',' ').replace('\n',' ') for w in words).strip()
        if not text:continue
        track=phrase.get('language_track','translation' if plan.get('display_mode')=='translation' else 'source')
        language=plan.get('display_language',plan.get('language','und')) if track=='translation' else plan.get('language','und')
        out.append({'id':i+1,'start':a,'end':min(duration,b),'text':text,'words':words,'language_track':track,'language':language})
    return out


def stamp(seconds,comma=False):
    ticks=max(0,round(seconds*1000));h,rest=divmod(ticks,3600000);m,rest=divmod(rest,60000);s,ms=divmod(rest,1000)
    return f'{h:02}:{m:02}:{s:02}{"," if comma else "."}{ms:03}'


def write(plan,folder,*,reference=None,ass=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);rows=cue_rows(plan)
    for ext in ('srt','vtt'):
        body='WEBVTT\n\n' if ext=='vtt' else ''
        body+='\n'.join(f'{i+1}\n{stamp(r["start"],ext=="srt")} --> {stamp(r["end"],ext=="srt")}\n{html.escape(r["text"])}\n' for i,r in enumerate(rows))
        (folder/('captions.'+ext)).write_text(body,encoding='utf-8-sig' if ext=='srt' else 'utf-8')
    (folder/'transcript.txt').write_text('\n'.join(r['text'] for r in rows)+('\n' if rows else ''),encoding='utf-8')
    languages=list(dict.fromkeys([plan.get('language','und'),plan.get('display_language',plan.get('language','und'))])) if plan.get('captions',{}).get('bilingual') else [plan.get('display_language',plan.get('language','und'))]
    value={'schema_version':1,'revision':plan.get('revision'),'publication':plan.get('publication',{}),
        'duration':plan['duration'],'language':'mul' if len(languages)>1 else languages[0],'languages':languages,'display_mode':plan.get('display_mode','bilingual' if plan.get('captions',{}).get('bilingual') else 'source'),'source_language':plan.get('language','und'),
        'reference':reference or {},'cues':rows,'display_words':copy.deepcopy(plan.get('display_words',plan.get('words',[]))),
        'clock':plan.get('editor',{}).get('clock'),'translation':plan.get('m2_translation',{}),
        'scope':'caption display revision; complete source speech remains in the edit plan'}
    write_json(folder/'transcript.json',value)
    source=Path(ass or plan.get('subtitle_path',''))
    if not source.is_file():raise ValueError('Master ASS revisi final hilang; render ulang')
    shutil.copy2(source,folder/'captions.ass')
    validate(folder,plan)
    return {p.name:content_id(p,fresh=True) for p in sorted(folder.iterdir()) if p.is_file()}


def validate(folder,plan):
    folder=Path(folder);expected=cue_rows(plan)
    for ext in ('srt','vtt'):
        text=(folder/('captions.'+ext)).read_text(encoding='utf-8-sig')
        blocks=re.findall(r'(\d+:\d\d:\d\d[.,]\d{3}) --> (\d+:\d\d:\d\d[.,]\d{3})\n([^\n]*(?:\n(?!\n)[^\n]+)*)',text)
        if len(blocks)!=len(expected):raise ValueError('Jumlah cue '+ext+' berbeda')
        for block,row in zip(blocks,expected):
            if block[0]!=stamp(row['start'],ext=='srt') or block[1]!=stamp(row['end'],ext=='srt') or html.unescape(block[2]).strip()!=row['text']:raise ValueError('Isi/waktu '+ext+' berbeda dari revisi final')
    from .storage import read_json
    data=read_json(folder/'transcript.json')
    if data['cues']!=expected or data['revision']!=plan.get('revision'):raise ValueError('Transkrip JSON berbeda dari revisi final')
    if (folder/'transcript.txt').read_text().strip()!='\n'.join(r['text'] for r in expected):raise ValueError('Transkrip TXT berbeda')
    ass=(folder/'captions.ass').read_text(encoding='utf-8-sig')
    if '[Events]' not in ass or '[Script Info]' not in ass:raise ValueError('ASS final tidak valid')
    return {'passed':True,'cues':len(expected),'formats':['srt','vtt','ass','txt','json']}


def bound_caption_tail(plan):
    """A readability hold may extend beyond the last frame; bind it to the clip.

    Spoken word times remain unchanged. Only the non-spoken tail is shortened;
    malformed word timing still fails. Keyframe curves retain their boundary value.
    """
    duration=plan['duration'];changed=False
    def bound(captions):
        nonlocal changed
        for phrase in captions.get('phrases',[]):
            if phrase['end']<=duration:continue
            if not 0<=phrase['start']<duration or phrase['end']-duration>.25 or any(w.get('end',0)>duration+.001 for w in phrase.get('words',[]) if not w.get('decorative')):raise ValueError('Caption/ucapan melewati batas klip final')
            phrase['end']=duration;changed=True;limit=duration-phrase['start']
            for word in phrase.get('words',[]):
                if word.get('decorative'):word['end']=min(word.get('end',duration),duration)
                frames=word.get('keyframes',[])
                if not frames:continue
                previous=next((k for k in reversed(frames) if k['t']<=limit),frames[0]);following=next((k for k in frames if k['t']>limit),None)
                boundary={**previous,'t':limit}
                if following and captions.get('keyframe_interpolation')!='hold' and following['t']>previous['t']:
                    fraction=(limit-previous['t'])/(following['t']-previous['t'])
                    for key,value in previous.items():
                        if key!='t' and type(value) in (int,float) and type(following.get(key)) in (int,float):boundary[key]=value+(following[key]-value)*fraction
                word['keyframes']=[k for k in frames if k['t']<limit]+[boundary]
        for name in ('source_plan','translation_plan'):
            if captions.get(name):bound(captions[name])
    bound(plan.get('captions',{}));return changed


def capture_language(plan,clip,cfg):
    plan['language']=clip.get('_source_language') or (cfg.language if cfg.language!='auto' else 'und')
    plan['display_language']=clip.get('_display_language') or clip.get('_m2_translation',{}).get('language') or plan['language']
    plan['display_mode']=clip.get('_display_mode') or ('bilingual' if plan.get('captions',{}).get('bilingual') else 'source')
