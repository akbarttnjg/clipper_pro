"""Optional, bounded MediaPipe evidence used by caption placement.

Only hair, face and accessories add protected regions. Clothing remains an
eligible caption surface. Models are installed explicitly in isolated runtime
generations; rendering never downloads weights.
"""
from pathlib import Path

VERSION='segmentation-4.0.10'
MODEL_URL='https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/1/selfie_multiclass_256x256.tflite'
MODEL_SHA256='c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0'
MODEL_BYTES=16371837
MODEL_GENERATION='1682480015568195'
MODEL_LABELS=['background','hair','body-skin','face-skin','clothes','others']


def enrich(media,plan,cfg):
    from . import visual4
    from .dependency_cache import content_id
    summary={'version':VERSION,'status':'disabled','budget_frames':8,'device':'cpu',
             'protected_classes':['hair','face-skin','others'],'clothing_overlay':True}
    plan['segmentation']=summary
    if not cfg.visual_enabled or not cfg.segmentation_enabled or cfg.style_preset=='legacy':return summary
    if not visual4.component_runtime('mediapipe',cfg):
        summary.update(status='unavailable',note='MediaPipe opsional belum dipasang dan lulus uji sampel; YuNet/OCR dan statistik gambar tetap dipakai.')
        return summary
    shots=plan.get('shots',[])
    # Request the exact frame used for image statistics. Never assign the
    # midpoint mask to an earlier/later grid from a moving person.
    times=sorted(set(round(t,3) for s in shots for t in
        ([a['time'] for a in s.get('area_samples',[]) if isinstance(a.get('time'),(int,float))] or
         [(s['source_start']+s['source_end'])/2]) if s['source_start']<=t<s['source_end']))
    if len(times)>8:times=[times[round(i*(len(times)-1)/7)] for i in range(8)]
    if not times:summary['status']='no_frames';return summary
    result=visual4.backend('mediapipe',{'source':str(Path(media).resolve()),'source_content_id':content_id(media),
        'times':times,'max_width':512,'budget':8,'adapter_version':VERSION},cfg,visual4.analysis_folder(cfg))
    summary.update({k:v for k,v in result.items() if k not in ('frames','artifacts','artifact_content_ids')})
    summary['generation']=result.get('provenance',{}).get('generation')
    if result.get('status')!='ready':return summary
    if len(result.get('frames',[]))>8:raise ValueError('Backend segmentasi melampaui anggaran frame.')
    used=0
    for shot in shots:
        for sample in shot.get('area_samples',[]):
            sample.pop('categories',None);sample.pop('segmentation_time',None)
        frames=[f for f in result['frames'] if shot['source_start']<=f['time']<shot['source_end']]
        if not frames:continue
        used+=1
        for f in frames:
            shot.setdefault('protected_source',[]).extend(f['protected'])
        for sample in shot.get('area_samples',[]):
            sample.pop('categories',None)
            sample.pop('segmentation_time',None)
            match=next((f for f in frames if isinstance(sample.get('time'),(int,float)) and abs(f['time']-sample['time'])<=.002),None)
            if match:
                sample['categories']=match['categories']
                sample['segmentation_time']=match['time']
        shot['segmentation']={'status':'sampled','times':[f['time'] for f in frames],'generation':summary['generation'],
                              'policy':'face_hair_accessories_protected; plain_clothes_eligible'}
    summary.update(sampled_frames=len(result['frames']),sampled_shots=used,total_shots=len(shots),
                   scope='sampled_source_frames; detector/OCR fallback on unsampled shots')
    return summary
