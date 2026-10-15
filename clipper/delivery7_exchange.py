"""Small, explicit exchange adapters. Baked picture + active final audio only.

FCP7 XML v5: Premiere exchange; FCPXML 1.7: Final Cut exchange.
OTIO Clip.2: external references and rational source ranges. No native text claim.
"""
import json,os
from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET
from .storage import write_json


def fps_rate(value):
    return Fraction(str(value)).limit_denominator(1001000)


def sec(frames,fps):
    q=Fraction(frames,1)/fps_rate(fps)
    return f'{q.numerator}/{q.denominator}s'


def stable(row):return 'm7-'+row['key']


def fcp7(rows,path,name):
    from .projects import node,rate
    fps=rows[0]['fps'];total=sum(r['frames'] for r in rows)
    root=ET.Element('xmeml',version='5');seq=node(root,'sequence',id='sequence-'+rows[0]['key'])
    node(seq,'name',name);node(seq,'duration',total);rate(seq,fps)
    media=node(seq,'media');video=node(media,'video');char=node(node(video,'format'),'samplecharacteristics')
    rate(char,fps);node(char,'width',rows[0]['width']);node(char,'height',rows[0]['height']);node(char,'pixelaspectratio','square')
    vtrack=node(video,'track');audio=node(media,'audio');atrack=node(audio,'track');offset=0
    for row in rows:
        for track,kind in ((vtrack,'video'),(atrack,'audio')):
            item=node(track,'clipitem',id=stable(row)+'-'+kind);node(item,'name',row['title']);node(item,'enabled','TRUE')
            node(item,'duration',row['frames']);rate(item,fps);node(item,'start',offset);node(item,'end',offset+row['frames'])
            node(item,'in',0);node(item,'out',row['frames'])
            file=node(item,'file',id=stable(row)+'-file')
            if kind=='video':
                node(file,'name',Path(row['path']).name);node(file,'pathurl',Path(row['path']).resolve().as_uri());rate(file,fps);node(file,'duration',row['frames'])
                m=node(file,'media');v=node(node(m,'video'),'samplecharacteristics');rate(v,fps)
                node(v,'width',row['width']);node(v,'height',row['height']);node(v,'pixelaspectratio','square')
                a=node(node(m,'audio'),'samplecharacteristics');node(a,'depth',16);node(a,'samplerate',48000)
            source=node(item,'sourcetrack');node(source,'mediatype',kind);node(source,'trackindex',1)
        offset+=row['frames']
    ET.indent(root);ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)


def fcpxml(rows,path,name):
    fps=rows[0]['fps'];root=ET.Element('fcpxml',version='1.7');resources=ET.SubElement(root,'resources')
    ET.SubElement(resources,'format',id='r1',frameDuration=sec(1,fps),width=str(rows[0]['width']),height=str(rows[0]['height']))
    for row in rows:
        ET.SubElement(resources,'asset',id=stable(row),name=row['title'],src=Path(row['path']).resolve().as_uri(),
            start='0s',duration=sec(row['frames'],fps),hasVideo='1',hasAudio='1',format='r1',audioSources='1',audioChannels='2',audioRate='48000')
    library=ET.SubElement(root,'library');event=ET.SubElement(library,'event',name='Clipper M7')
    project=ET.SubElement(event,'project',name=name);seq=ET.SubElement(project,'sequence',format='r1',duration=sec(sum(r['frames'] for r in rows),fps),
        tcStart='0s',tcFormat='NDF',audioLayout='stereo',audioRate='48k');spine=ET.SubElement(seq,'spine');offset=0
    for row in rows:
        ET.SubElement(spine,'asset-clip',name=row['title'],ref=stable(row),offset=sec(offset,fps),start='0s',duration=sec(row['frames'],fps),format='r1',audioRole='dialogue')
        offset+=row['frames']
    ET.indent(root);ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)


def rt(value,rate):return {'OTIO_SCHEMA':'RationalTime.1','value':value,'rate':float(rate)}
def tr(frames,fps):return {'OTIO_SCHEMA':'TimeRange.1','start_time':rt(0,fps),'duration':rt(frames,fps)}


def otio(rows,path,name):
    children=[]
    for row in rows:
        children.append({'OTIO_SCHEMA':'Clip.2','name':row['title'],'metadata':{'clipper':{'key':row['key'],'layers':'baked final video/audio','source_clip_id':row.get('clip_id'),'variant_id':row.get('variant_id')}},
            'source_range':tr(row['frames'],row['fps']),'effects':[],'markers':[],'enabled':True,
            'media_references':{'DEFAULT_MEDIA':{'OTIO_SCHEMA':'ExternalReference.1','name':Path(row['path']).name,'metadata':{},
                'target_url':os.path.relpath(row.get('local_path',row['path']),Path(path).parent).replace(os.sep,'/'),'available_range':tr(row['frames'],row['fps'])}},
            'active_media_reference_key':'DEFAULT_MEDIA'})
    tracks=[]
    for kind in ('Video','Audio'):
        tracks.append({'OTIO_SCHEMA':'Track.1','name':kind,'metadata':{},'source_range':None,'effects':[],
            'markers':[],'enabled':True,'kind':kind,'children':children})
    write_json(path,{'OTIO_SCHEMA':'Timeline.1','name':name,'metadata':{'clipper':{'audio_policy':'final audio only; no doubled stems','native_import':'not_tested'}},
        'global_start_time':rt(0,rows[0]['fps']),'tracks':{'OTIO_SCHEMA':'Stack.1','name':'tracks','metadata':{},'source_range':None,'effects':[],'markers':[],'enabled':True,'children':tracks}})


def readback(path):
    """Re-read serialized cuts independently of the input plan for coverage QC."""
    path=Path(path)
    if path.suffix=='.otio':
        data=json.loads(path.read_text());tracks=data['tracks']['children']
        if data.get('OTIO_SCHEMA')!='Timeline.1' or len(tracks)!=2:raise ValueError('OTIO timeline/track tidak valid')
        out=[]
        for row in tracks[0]['children']:
            if row.get('OTIO_SCHEMA')!='Clip.2':raise ValueError('OTIO clip tidak valid')
            ref=row['media_references'][row['active_media_reference_key']]
            if ref['OTIO_SCHEMA']!='ExternalReference.1':raise ValueError('OTIO external reference tidak valid')
            out.append({'key':row['metadata']['clipper']['key'],'frames':row['source_range']['duration']['value'],'path':ref['target_url']})
        if [r['source_range'] for r in tracks[0]['children']]!=[r['source_range'] for r in tracks[1]['children']]:raise ValueError('OTIO audio/video tidak sinkron')
        return out
    root=ET.parse(path).getroot()
    if root.tag=='xmeml':
        seq=root.find('sequence');clips=seq.findall('./media/video/track/clipitem');a=seq.findall('./media/audio/track/clipitem')
        if [(r.findtext('start'),r.findtext('end')) for r in clips]!=[(r.findtext('start'),r.findtext('end')) for r in a]:raise ValueError('XML audio/video tidak sinkron')
        out=[];cursor=0
        for row in clips:
            start=int(row.findtext('start'));end=int(row.findtext('end'))
            if start!=cursor or end<=start:raise ValueError('XML gap/overlap tidak valid')
            cursor=end;out.append({'key':row.get('id').removeprefix('m7-').removesuffix('-video'),'frames':end-start,'path':row.findtext('./file/pathurl')})
        if cursor!=int(seq.findtext('duration')):raise ValueError('Durasi XML tidak cocok')
        return out
    if root.tag!='fcpxml':raise ValueError('Format exchange tidak dikenal')
    fmt=root.find('./resources/format');fps=1/Fraction(fmt.get('frameDuration').removesuffix('s'));assets={r.get('id'):r.get('src') for r in root.findall('./resources/asset')};out=[];cursor=0
    seq=root.find('.//sequence')
    for row in seq.findall('./spine/asset-clip'):
        start=Fraction(row.get('offset').removesuffix('s'))*fps;frames=Fraction(row.get('duration').removesuffix('s'))*fps
        if start!=cursor or frames.denominator!=1 or frames<=0:raise ValueError('FCPXML gap/overlap tidak valid')
        cursor+=frames;out.append({'key':row.get('ref').removeprefix('m7-'),'frames':int(frames),'path':assets[row.get('ref')]})
    if cursor!=Fraction(seq.get('duration').removesuffix('s'))*fps:raise ValueError('Durasi FCPXML tidak cocok')
    return out


def write(rows,folder,name,editors):
    if not rows:raise ValueError('Timeline exchange kosong')
    if any((r['width'],r['height'],r['fps'])!=(rows[0]['width'],rows[0]['height'],rows[0]['fps']) for r in rows):raise ValueError('Timeline gabungan memerlukan resolusi/fps yang sama')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);receipt={}
    for editor,ext,writer in [('premiere','xml',fcp7),('finalcut','fcpxml',fcpxml),('otio','otio',otio)]:
        if editor not in editors:continue
        path=folder/('timeline.'+ext);writer(rows,path,name);actual=readback(path)
        if [(r['key'],r['frames']) for r in actual]!=[(r['key'],r['frames']) for r in rows]:raise ValueError('Coverage exchange berubah: '+editor)
        receipt[editor]={'file':path.name,'construction_status':'generated','structural_status':'passed','roundtrip_scope':'serialized cut list, durations and references; native import not tested','native_status':'not_tested'}
    return receipt
