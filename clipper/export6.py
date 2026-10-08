"""Preserved MP4 package; native/hybrid adapter remains in projects.py."""
import copy
import shutil
import time
from pathlib import Path
from .dependency_cache import content_id
from .storage import write_json,read_json
from .workflow6 import EXPORT_MODES


def preserved(results,cfg,progress=lambda p,m:None):
    from .library_paths import project_root
    from .projects import write_srt
    root=project_root(cfg)/'projects'/f'preserved-{cfg.job_id}-{time.time_ns()}'
    (root/'Media').mkdir(parents=True,exist_ok=False)
    inventory=[]
    for i,result in enumerate(results,1):
        source=Path(result.get('absolute_file',''))
        expected=result.get('output_content_id')
        if not expected or content_id(source,fresh=True)!=expected:raise ValueError('Final berubah; render ulang sebelum membuat paket.')
        plan=read_json(result.get('plan_path',''),{})
        if not plan or plan.get('revision')!=result.get('revision'):raise ValueError('Rencana tidak sesuai final.')
        target=root/'Media'/f'{i:02}-final.mp4';shutil.copyfile(source,target)
        if content_id(target,fresh=True)!=expected:raise ValueError('Salinan final tidak sesuai checksum.')
        write_srt(plan,root/'Media'/f'{i:02}-captions.srt')
        ass=Path(plan.get('subtitle_path',Path(result['plan_path']).parent/'captions.ass'))
        if ass.is_file():shutil.copyfile(ass,root/'Media'/f'{i:02}-captions.ass')
        # Avoid packing source paths, secrets, or unrelated source material.
        reference={'revision':plan['revision'],'width':plan['width'],'height':plan['height'],
            'fps':plan['fps'],'duration':plan['duration'],'captions':plan['captions'],
            'quality':plan.get('caption_checks',{}),'render_content_id':expected}
        write_json(root/f'reference-plan-{i:02}.json',reference)
        inventory.append({'path':target.relative_to(root).as_posix(),'bytes':target.stat().st_size,'content_id':expected})
        progress(round(i/max(1,len(results))*80),'Menyalin final dengan checksum yang sama')
    manifest={'version':6,'export_mode':'preserved',**copy.deepcopy(EXPORT_MODES['preserved']),
        'timelines':len(results),'structural_status':'passed','native_editor_status':'not_applicable',
        'editors':{},'inventory':inventory}
    write_json(root/'manifest.json',manifest)
    write_json(root/'verification.json',{'structural_status':'passed','checks':['Exact final MP4 SHA-256 copied'],'inventory':inventory,
        'native_editor_status':'not_applicable','quality_status':'human_review_required'})
    (root/'BACA_DULU.txt').write_text('TAMPILAN TERJAGA\n\nMedia/XX-final.mp4 adalah salinan final dengan checksum sama.\n'
        'Impor MP4 ke editor sebagai video biasa. Teks, efek dan audio di MP4 sudah menyatu.\n'
        'SRT/ASS adalah pendamping, bukan layer native otomatis.\n',encoding='utf-8')
    archive=shutil.make_archive(str(root),'zip',root)
    return {'zip':archive,'folder':str(root),'timelines':len(results),'export_mode':'preserved',
        'editors':{},'structural_status':'passed','native_editor_status':'not_applicable',
        'editable_layers':[],'baked_layers':manifest['baked_layers'],'limitations':manifest['limitations'],
        'note':'Final MP4 disalin dengan checksum identik. Caption dan efek menyatu di video.'}
