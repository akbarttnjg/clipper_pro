"""A's exchange adapter for C0 v1 (integration f67b032). C0 is owned by B.

All IDs/revisions/media identity enter from B. This module never saves projects,
assigns list-index clip IDs, or converts source times to render frames itself.
"""
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
from . import transcript_correction, subtitle_edit, typography, caption_checks
from .analysis_options import configured,checkpoint,DEPENDENCIES
from . import contracts

VERSION='A-4.0.3'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def envelope(kind,source_id,input_fingerprint,status='ready',**data):
    if not isinstance(source_id,str) or not source_id or not isinstance(input_fingerprint,str) or not input_fingerprint:
        raise ValueError('Identitas isi sumber dan input_fingerprint wajib dari layanan media B')
    if status not in ('ready','empty','blocked','error','stale'):raise ValueError('Status tidak dikenal')
    return contracts.envelope(kind,source_id,data,input_fingerprint,state=status,producer=VERSION)


def require_v1(value):
    if type(value.get('schema_version')) is not int or value['schema_version']!=1:
        raise ValueError('Skema belum didukung; data tidak diubah. Gunakan adapter/migrasi C0 yang sesuai.')
    return contracts.validate(value)


def asr_fingerprint(source_id,audio_stream_id,cfg,source_time_origin=0,alias_revision=None):
    from .correction_memory import signature
    cfg=configured(cfg)
    value=[VERSION,source_id,audio_stream_id,source_time_origin,
        {k:getattr(cfg,k,None) for k in DEPENDENCIES['asr'] if hasattr(cfg,k)},
        alias_revision if alias_revision is not None else signature(cfg)]
    from .runtime.bridge import managed_asr
    managed=managed_asr(cfg) if getattr(cfg,'whisper_isolate',True) else None
    if managed:value.append({k:managed[k] for k in ('generation','model_commit','lock_hash','recommended_device')})
    return digest(value)


def transcript_snapshot(transcript,cfg,*,source_id,transcript_id,revision,input_fingerprint,audio_stream_id,
                        clip_span=None):
    if not transcript_id or type(revision) is not int or revision<0:raise ValueError('ID/revisi transkrip diperlukan')
    refined=transcript_correction.refine(transcript,cfg)
    heard=[dict(w) for w in refined['raw_words']]
    identifiers=[w.get('word_id') for w in heard]
    if any(i is None for i in identifiers) or len(set(identifiers))!=len(identifiers):
        raise ValueError('ID kata asal harus ada dan unik di transkrip ini')
    heard=[{**w,'source_id':source_id,'transcript_id':transcript_id,'origin_word_ids':[w['word_id']]} for w in heard]
    from .stage3 import expand_aligned
    display,changes,warnings=subtitle_edit.clean(expand_aligned(refined['words']),cfg.caption_cleanup,cfg.caption_punctuation,cfg)
    tokens=[];occurrences={}
    for w in display:
        origins=transcript_correction.source_ids([w])
        if not origins or not set(origins)<=set(identifiers):raise ValueError('Lineage token tidak menunjuk kata asal')
        lineage=tuple(origins);ordinal=occurrences.get(lineage,0);occurrences[lineage]=ordinal+1
        alignment=bool(clip_span and (w['start']<clip_span[0]<w['end'] or w['start']<clip_span[1]<w['end']) and len(origins)>1)
        tokens.append(dict(token_id='tok-'+digest([source_id,transcript_id,origins,ordinal])[:24],
            origin_word_ids=origins,text=w['word'],source_start=w['start'],source_end=w['end'],
            correction_status='manual' if w.get('manually_edited') else w.get('correction','unchanged'),
            timing_status=w.get('timing_status','asr'),alignment_method=w.get('alignment_method'),
            provenance={'reason':w.get('correction'),'before':w.get('raw_word'),'manual':bool(w.get('manually_edited'))},
            requires_alignment=alignment))
    queue=[]
    for row in refined['correction_report']['review']:
        token=next((t for t in tokens if row.get('word_id') in t['origin_word_ids']),None)
        if token:queue.append({**row,'token_id':token['token_id'],'text':token['text']})
    return envelope('TranscriptSnapshot',source_id,input_fingerprint,'ready' if tokens else 'empty',
        transcript_id=transcript_id,revision=revision,audio_stream_id=audio_stream_id,words=heard,heard_words=heard,
        display_tokens=tokens,correction_evidence=refined['correction_report']['changes']+changes,
        review_queue=queue,warnings=warnings,corrected_words=refined['words'],
        origin_mapping={t['token_id']:t['origin_word_ids'] for t in tokens})


def correction_proposal(snapshot,token_id,text,*,expected_revision,expected_transcript_revision,operation_id,scope='clip'):
    """Project revision and transcript revision are separate B-owned clocks."""
    require_v1(snapshot)
    data=snapshot['payload']
    if type(expected_revision) is not int or expected_revision<0:raise ValueError('Revisi proyek tidak valid')
    if type(expected_transcript_revision) is not int or data['revision']!=expected_transcript_revision:
        raise ValueError('Revisi transkrip usang; muat snapshot baru dan pertahankan draf')
    if not operation_id or scope not in ('clip','shared_utterance','project_alias'):raise ValueError('Operation ID / scope tidak valid')
    token=next((t for t in data['display_tokens'] if t['token_id']==token_id),None)
    if token is None:raise ValueError('Token tidak ditemukan')
    if token.get('requires_alignment'):raise ValueError('Frasa melintasi batas klip; selaraskan frasa sebelum koreksi')
    if not isinstance(text,str) or not text.strip() or len(text)>120:raise ValueError('Koreksi harus 1–120 karakter')
    return {'expected_revision':expected_revision,'operation_id':operation_id,'operations':[
        {'op':'correct_token','scope':scope,'source_id':snapshot['source_id'],'transcript_id':data['transcript_id'],
         'transcript_revision':expected_transcript_revision,'token_id':token_id,'origin_word_ids':token['origin_word_ids'],'before':token['text'],'after':text.strip(),
         'provenance':{'kind':'user_approval','source_start':token['source_start'],'source_end':token['source_end']}}]}


def candidate_set(candidates,report,*,source_id,input_fingerprint,legacy=False):
    revision=report.get('analysis_revision') if not legacy else None
    coverage_id='coverage-'+digest([source_id,revision,report.get('round'),report.get('coverage')])[:20] if revision else None
    rows=[]
    for c in candidates:
        manual=c.get('selection_source') in ('manual','reviewed','manual-required')
        status='blocked' if c.get('selection_source')=='manual-required' else 'ready' if c.get('intelligence',{}).get('status')=='ready' else 'stale' if c.get('intelligence',{}).get('status')=='stale' else 'blocked'
        if legacy and not manual:status='stale'
        rows.append(dict(candidate_id=c.get('candidate_id') or 'cand-'+digest([source_id,c['start'],c['end'],c.get('main_claim',c['title'])])[:24],
            source_start=c['start'],source_end=c['end'],title=c['title'],reason=c.get('reason',''),status=status,
            review_status='needs_review' if status=='blocked' else status,evidence={
                'evidence_id':'evidence-'+digest([source_id,c['start'],c['end'],c.get('main_claim'),c.get('ending_evidence')])[:24],
                'claim':c.get('main_claim'),
                'ending':c.get('ending_evidence'),'context':c.get('source_context')},
            rejection_reasons=c.get('boundary_review',{}).get('issues',[]),
            origin='manual' if manual else 'legacy' if legacy else 'analysis',coverage_id=coverage_id,
            analysis_revision=revision,search_origin={'round':report.get('round'),'model':report.get('model'),'objective':report.get('objective')}))
    return envelope('CandidateSet',source_id,input_fingerprint,'ready' if rows else 'empty',candidates=rows,
                    coverage_id=coverage_id,analysis_revision=revision,coverage=report.get('coverage'),rejections=report.get('rejections',[]))


def scene_analysis(plan,media_context,*,input_fingerprint):
    require_v1(media_context)
    data=media_context['payload']
    if data.get('coordinate_space')!='canonical_source_pixels' or data.get('geometry_status')!='ready':
        return envelope('SceneAnalysis',media_context['source_id'],input_fingerprint,'blocked',scenes=[],
                        reasons=['Geometri kanonis belum disahkan layanan media B38'])
    width,height=data['display_size'];scenes=[]
    for shot in plan['shots']:
        scene_id='scene-'+digest([media_context['source_id'],shot['source_start'],shot['source_end']])[:20]
        common={'coordinate_space':'canonical_source_pixels','width':width,'height':height,
                'source_start':shot['source_start'],'source_end':shot['source_end']}
        rows=[]
        for item in shot.get('protected_source',[]):
            x,y,w,h=item['box'];x1,y1=max(0,x),max(0,y);x2,y2=min(width,x+w),min(height,y+h)
            if x2>x1 and y2>y1:rows.append({**common,'kind':item['kind'],'box':[x1,y1,x2-x1,y2-y1],
                'confidence':item.get('confidence'),'provenance':item.get('provenance','sampled_'+item['kind'])})
        scenes.append(dict(scene_id=scene_id,**common,faces=[r for r in rows if r['kind']=='face'],
            text_regions=[r for r in rows if r['kind'] in ('ocr','text')],material_regions=[r for r in rows if r['kind']=='material'],
            composition={'mode':shot['mode'],'rect':shot['rect'],'reason':shot.get('composition_reason')},
            confidence=None,provenance='A sampled face/text/material analysis'))
    return envelope('SceneAnalysis',media_context['source_id'],input_fingerprint,'ready' if scenes else 'empty',scenes=scenes)


def caption_plan(render_words,cfg,timeline,*,input_fingerprint,frame_mapper,anchors=None,keywords=()):
    require_v1(timeline)
    data=timeline['payload']
    if not callable(frame_mapper):raise ValueError('Pemetaan waktu render harus disediakan layanan B')
    fps=Fraction(data['fps']['numerator'],data['fps']['denominator'])
    if fps<=0 or not data.get('variant_id'):raise ValueError('FPS / variant_id diperlukan')
    if any('origin_word_ids' not in w or 'token_id' not in w for w in render_words):
        raise ValueError('Render words harus membawa token_id dan origin_word_ids dari pemetaan B')
    words=[{**w,'word':w.get('word',w.get('text','')),'word_id':w['token_id'],
            'source_word_ids':w['origin_word_ids']} for w in render_words]
    plan=typography.make_plan(words,cfg,keywords=keywords,anchors=anchors)
    checks=caption_checks.inspect_caption_plan(plan,cfg,expected_words=words)
    rows=[]
    for p in plan['phrases']:
        a,b=frame_mapper(p['start'],p['end'],data['fps'])
        if type(a) is not int or type(b) is not int or not 0<=a<b:raise ValueError('Pemetaan frame B tidak valid')
        rows.append({**p,'phrase_id':'phrase-'+digest([data['variant_id'],[w['word_id'] for w in p['words']]])[:20],
            'start_frame':a,'end_frame':b,'coordinate_space':'output_canvas_pixels','width':cfg.target_w,'height':cfg.target_h,
            'token_references':[t for w in p['words'] for t in w.get('token_ids',[w['word_id']])],
            'origin_word_ids':list(dict.fromkeys(i for w in p['words'] for i in w.get('word_ids',[]))),
            'animation_timebase':'seconds_relative_to_phrase'})
    return envelope('CaptionPlan',timeline['source_id'],input_fingerprint,'ready' if rows else 'empty',
        variant_id=data['variant_id'],timeline_revision=data['revision'],fps=data['fps'],phrases=rows,qc=checks)


def asset_proposal_set(recipe,*,source_id,input_fingerprint,cfg,cancellation_token=None):
    from .asset_review import poster,identity
    proposals=[]
    for scene in recipe.get('scenes',[]):
        checkpoint(cancellation_token)
        asset=scene['asset'];p=Path(asset['path'])
        fingerprint=identity(p)[-1] if p.is_file() else None
        visual=asset.get('visual_review',{});metadata=asset.get('relevance',{})
        try:poster_path=str(poster(asset,cfg)) if p.is_file() else None
        except (OSError,ValueError):poster_path=None
        proposals.append(dict(proposal_id=scene['id'],source_start=scene['source_start'],source_end=scene['source_end'],
            phrase_reference=scene.get('phrase_reference'),scene_reference=scene.get('scene_reference'),reason=scene['reason'],
            visual_intent=scene['query'],asset_id=asset['provider']+':'+asset['id'],path=str(p),content_fingerprint=fingerprint,
            duration=asset.get('duration'),poster=poster_path,editable_path=asset.get('editable_path'),tags=asset.get('tags',''),
            status='ready' if p.is_file() else 'blocked',availability='available' if p.is_file() else 'missing',
            enabled=scene.get('enabled',True),rights={'author':asset.get('author'),'source_url':asset.get('page_url'),
                'license_url':asset.get('license_url'),'attribution':asset.get('attribution'),'origin':asset.get('origin'),
                'permission_status':'user_supplied' if asset['provider']=='local' else 'source_owner' if asset['provider']=='source' else 'generated' if asset['provider']=='diagram' else 'provider_terms'},
            metadata_status='ready' if metadata else 'empty',metadata_evidence=metadata,
            visual_status='ready' if visual.get('visual_verified') and visual.get('accept') else 'blocked' if visual.get('status')=='rejected' else 'unavailable',
            visual_evidence=visual,usage_status='not_scheduled'))
    status='ready' if proposals else 'blocked' if recipe.get('status')=='unavailable' else 'empty'
    return envelope('AssetProposalSet',source_id,input_fingerprint,status,proposals=proposals,notes=recipe.get('notes',[]))


def manual_candidate_policy(count):
    """No fixed cap of twenty; B validates range/revision and assigns clip IDs."""
    if type(count) is not int or count<0:raise ValueError('Jumlah kandidat tidak valid')
    return {'allowed':True,'limit':None,'reason':'Jumlah mengikuti gagasan dan pilihan pengguna; pemuatan UI dilakukan bertahap.'}


def analyze_scenes(media_context,edit_plan,cfg,*,input_fingerprint,cancellation_token=None):
    import copy
    from . import composition
    require_v1(media_context);checkpoint(cancellation_token)
    data=media_context['payload']
    if data.get('geometry_status')!='ready' or data.get('coordinate_space')!='canonical_source_pixels':
        return scene_analysis({'shots':[]},media_context,input_fingerprint=input_fingerprint),None
    path=data.get('working_path') or data.get('source_path')
    if not path or not Path(path).is_file():raise ValueError('Media kanonis dari B tidak tersedia')
    w,h=data['display_size']
    import cv2
    cap=cv2.VideoCapture(path)
    try:ok,frame=cap.read()
    finally:cap.release()
    if not ok or tuple(frame.shape[:2])!=(h,w):
        return envelope('SceneAnalysis',media_context['source_id'],input_fingerprint,'blocked',scenes=[],
                        reasons=['Ukuran frame decoder berbeda dari MediaContext B38']),None
    plan=copy.deepcopy(edit_plan)
    info={'width':w,'height':h,'duration':data['duration']}
    composition.analyze(path,plan,cfg,info)
    checkpoint(cancellation_token)
    return scene_analysis(plan,media_context,input_fingerprint=input_fingerprint),plan
