"""Structural export checks and an explicit, still-required native editor gate."""
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from .dependency_cache import content_id
from .storage import read_json


def validate_bundle(root,results):
    root=Path(root);checks=[];issues=[];reference=root/'Reference';reference.mkdir(exist_ok=True)
    for i,result in enumerate(results):
        plan=read_json(result['plan_path'])
        if not plan:issues.append('Rencana render tidak tersedia');continue
        checks.append({'clip':i+1,'duration':plan['duration'],'width':plan['width'],'height':plan['height'],
            'fps':plan['fps'],'captions':len(plan.get('captions',{}).get('phrases',[])),
            'broll_events':len(plan.get('broll',[])),'subtitle_qc':plan.get('caption_checks',{})})
        final=Path(result.get('absolute_file',''))
        if final.is_file():
            target=reference/f'{i+1:02}-reference.mp4';shutil.copyfile(final,target)
            checks[-1]['reference_content_id']=content_id(target,fresh=True)
    xml=list(root.rglob('timeline.xml'))
    for path in xml:
        try:
            tree=ET.parse(path)
            if tree.find('.//sequence') is None:issues.append('Sequence XML tidak tersedia: '+path.name)
        except ET.ParseError as exc:issues.append(str(exc))
    for path in root.rglob('draft_content.json'):
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data.get('tracks'),list):issues.append('Track CapCut tidak tersedia')
        except (ValueError,OSError) as exc:issues.append(str(exc))
    if not xml:issues.append('Timeline Resolve tidak tersedia')
    return {'schema_version':1,'structural_status':'passed' if not issues else 'needs_review','issues':issues,'timelines':checks,
        'native_editor_status':'not_tested','native_tests':[
            {'editor':'CapCut','status':'requires_local_import','checks':['media online','text baseline','animation','B-roll offset','audio sync','duration']},
            {'editor':'DaVinci Resolve','status':'requires_local_import','checks':['media online','Fusion text','B-roll offset','audio stems','duration']}],
        'comparison':'Bandingkan hasil ekspor editor dengan Reference/*.mp4 pada pembuka, pergantian B-roll, tengah dan penutup. Catat versi editor dan perbedaan nyata.',
        'limitations':['Pemeriksaan struktur tidak membuktikan bahwa impor native berhasil.','Blur/fade CapCut belum setara dengan ASS. Framing sumber sudah menyatu pada V1.']}
