"""One isolated heavy stage per process. Publish only against matching inputs."""
import argparse
import copy
import sys
import traceback
from dataclasses import asdict, replace
from pathlib import Path
from .studio_service import StudioService, identifier, CONFIG_FIELDS
from .config import Config
from .project_store import Conflict
from .storage import read_json, write_json
from .contracts import fingerprint
from .dependency_cache import content_id, render_key


class StaleJob(ValueError):pass


def execute(service,job):
    from . import pipeline, media_context, evidence, transcript_correction, story, analysis_adapter, illustrations, editorial
    pid=job['project_id'];target=job['target'];cid=target.get('clip_id');vid=target.get('variant_id','portrait');kind=job['kind']
    doc=service.store.get(pid);dependency=job['request']['dependency'];cfg=service.config(doc,cid,vid)
    work=Path(cfg.work_dir);work.mkdir(parents=True,exist_ok=True)
    def progress(value,message):service.queue.update(job['id'],progress=max(0,min(100,int(value))),message=message)
    def check(current=None):
        current=current or service.store.get(pid)
        if service.queue.get(job['id'])['status']=='cancel_requested':raise StaleJob('Proses sudah dibatalkan')
        if dependency!=service.dependency(current,cid,vid,fresh=True,kind=kind):raise StaleJob('Masukan berubah ketika proses berjalan. Hasil lama dipertahankan; jalankan ulang revisi aktif.')
        if kind!='analyze' and current['source'].get('requires_analysis'):raise StaleJob('Sesi lama belum mempunyai identitas sumber yang terverifikasi. Analisis ulang sebelum menerapkan koreksi atau render.')
        if kind!='analyze' and content_id(current['source']['path'],fresh=True)!=current['source']['source_id']:
            raise StaleJob('Isi sumber berubah. Analisis ulang sebelum memakai transkrip atau hasil lama.')
        return current
    check()
    progress(1,'Memeriksa revisi dan berkas sumber')
    # ASR, local LLM and OCR/vision have no simultaneous GPU ownership.
    editorial.release(cfg)
    prior_media=doc['source'].get('media_context',{}).get('payload',{})
    expected_track=cfg.audio_stream_index if cfg.audio_stream_index>=0 else doc['source']['info']['audio_tracks'][0]['index']
    if kind not in ('analyze','source_evidence','waveform') and prior_media and prior_media.get('selected_audio_index')!=expected_track:
        raise StaleJob('Track suara berubah; analisis sumber kembali sebelum merender subtitle.')
    media=media_context.prepare(doc['source']['path'],cfg,progress)
    cfg=replace(cfg,source_content_id=media['source_id'],audio_stream_id=media['payload']['audio_stream_id'])
    source=media['payload']['working_path'];result={};updates={};variant_updates={}
    if kind=='analyze':
        transcript,candidates=pipeline.analyze(source,cfg,progress)
        # Stable immutable take IDs: cache reuse does not invalidate approved patches.
        take='asr-'+fingerprint([pid,media['source_id'],media['payload']['audio_stream_id'],transcript.get('raw_words',transcript['words'])])[:32]
        try:service.store.transcript(take)
        except KeyError:service.store.save_transcript(pid,transcript,take)
        updates.update(transcript_id=take,discovery=read_json(work/'selection-report.json',{}))
        result={'candidates':len(candidates),'transcript_id':take,'timings':transcript.get('timings')}
    elif kind=='source_evidence':
        report=evidence.scan(source,cfg,media['payload']['duration'],progress,input_fingerprint=media['input_fingerprint'])
        result={'evidence':report};updates['evidence_summary']={k:v for k,v in report.items() if k not in ('frames','audio')}
    elif kind=='waveform':
        from .audio_quality import waveform
        result=waveform(source,media['payload']['duration']);updates['waveform']=result
    else:
        transcript=service.transcript(doc,cid);words=transcript['words']
        if kind=='correction':
            transcript['ocr_suggestions']=evidence.suggestions(words,evidence.load(cfg))
            refined=transcript_correction.refine(transcript,cfg)
            take='corrected-'+fingerprint([pid,doc['transcript_id'],refined['words'],doc.get('aliases')])[:32]
            try:service.store.transcript(take)
            except KeyError:service.store.save_transcript(pid,refined,take)
            updates['transcript_id']=take;updates['correction_report']=refined['correction_report'];result={'review_items':len(refined['correction_report']['review'])}
        elif kind=='discovery':
            candidates=story.select(transcript,cfg,progress,existing=list(doc['clips'].values()))
            updates['discovery']=read_json(work/'selection-report.json',{});result={'candidates':len(candidates)}
        elif kind=='boundary_review':
            reviewed=story.review_candidate(doc['clips'][cid],transcript,cfg,refresh=True)
            result={'review':reviewed}
        elif kind in ('asset_proposals','asset_visual_review'):
            clip={k:v for k,v in doc['clips'][cid].items() if k!='variants'}
            if cfg.broll_mode=='off':cfg=replace(cfg,broll_mode='local')
            recipe=illustrations.prepare(words,clip,cfg,progress,input_fingerprint=dependency)
            proposals=analysis_adapter.asset_proposal_set(recipe,source_id=media['source_id'],input_fingerprint=dependency,cfg=cfg)
            variant_updates.update(recipe=recipe,asset_proposals=proposals)
            if service.variant(doc,cid,vid).get('settings',{}).get('broll_mode',doc['settings'].get('broll_mode','off'))=='off':
                variant_updates['settings']={**service.variant(doc,cid,vid).get('settings',{}),'broll_mode':'local'}
            result={'proposals':len(recipe.get('scenes',[])),'notes':recipe.get('notes',[])}
        elif kind in ('preview','render'):
            clip={k:v for k,v in doc['clips'][cid].items() if k!='variants'};variant=service.variant(doc,cid,vid)
            from .studio_exchange import render_words,records
            words=render_words(transcript,doc,clip,cfg)
            clip['revision']=variant.get('timeline_revision',0)+doc['transcript_revision']
            clip['_broll_recipe']=variant.get('recipe') or {'scenes':[],'notes':['Siapkan ilustrasi untuk memilih aset.']}
            if variant.get('timeline'):clip['manual_keep_spans']=variant['timeline']['keep_spans']
            if kind=='preview':
                quality=job['request'].get('options',{}).get('quality','draft');edge=1280 if quality=='detail' else 640
                scale=edge/max(cfg.target_w,cfg.target_h)
                folder=work/'cache'/'previews'/(dependency[:24]+'-'+quality)
                cfg=replace(cfg,target_w=round(cfg.target_w*scale/2)*2,target_h=round(cfg.target_h*scale/2)*2,
                    work_dir=str(folder),out_dir=str(folder/'output'),job_id='',preview_seconds=0)
                folder.mkdir(parents=True,exist_ok=True)
                if (work/'source-evidence.json').is_file():write_json(folder/'source-evidence.json',read_json(work/'source-evidence.json'))
            key=render_key(source,words,clip,cfg,fresh=True)
            # A full-content manifest is checked on every reuse, including the output itself.
            cached=read_json(Path(cfg.work_dir)/'render-cache'/f'{key}.json',{})
            path=Path(cached.get('absolute_file',''))
            if path.is_file() and cached.get('output_content_id')==content_id(path,fresh=True):result=cached
            else:
                name=f'{cid}-{vid}-{key[:12]}'
                result=pipeline.render_clip(source,words,clip,name,cfg,progress)
                path=Path(cfg.out_dir)/result['file']
                result.update(absolute_file=str(path.resolve()),output_content_id=content_id(path,fresh=True),fingerprint=key,dependency=dependency,
                    variant_id=vid,input_revision=doc['revision'],kind=kind,quality=job['request'].get('options',{}).get('quality','draft') if kind=='preview' else 'final')
                for field,suffix in [('ass_url','.ass'),('srt_url','.srt'),('credits_url','.credits.txt')]:
                    original=Path(cfg.out_dir)/(result[field].removeprefix('/clips/'))
                    result[field]=service.register_file(pid,original)
                result['url']=service.register_file(pid,path)
                write_json(Path(cfg.work_dir)/'render-cache'/f'{key}.json',result)
            plan=read_json(result['plan_path'],{})
            exchange=records(plan,result,doc,cid,vid,cfg,media)
            exchange_path=Path(result['plan_path']).with_name('exchange.json');write_json(exchange_path,exchange)
            result['exchange_path']=str(exchange_path)
            variant_updates.update({('preview' if kind=='preview' else 'result'):result,'schedule':plan.get('broll_schedule',[]),'schedule_dependency':dependency,
                'timeline_summary':{k:plan.get(k) for k in ('spans','duration','fps','width','height','warnings','audio_quality')},
                'shot_summary':[{k:s.get(k) for k in ('start','end','source_start','source_end','mode','has_material','composition_reason')} for s in plan.get('shots',[])]})
            service.store.artifact(pid,cid,vid,kind,key,result)
        elif kind=='export':
            from . import projects
            final=service.variant(doc,cid,vid).get('result')
            if not final or final.get('dependency')!=dependency:raise ValueError('Render final revisi aktif dahulu sebelum ekspor editor')
            if not Path(final['absolute_file']).is_file() or content_id(final['absolute_file'],fresh=True)!=final['output_content_id']:raise ValueError('Berkas final berubah atau hilang; render ulang')
            result=projects.export_bundle([final],cfg,progress)
            result['url']=service.register_file(pid,result['zip']);result['clip_id']=cid;result['variant_id']=vid
    check()
    def publish(current):
        old_take=current.get('transcript_id');old_source=current['source']['source_id']
        old_audio=current['source'].get('media_context',{}).get('payload',{}).get('audio_stream_id')
        current['source'].update(source_id=media['source_id'],media_context=media,info={k:v for k,v in media['payload'].items() if k!='working_content_id'})
        current.update(updates)
        if kind in ('analyze','discovery'):
            if old_take and (current['source'].get('requires_analysis') or old_source!=media['source_id'] or old_audio and old_audio!=media['payload']['audio_stream_id']):
                current.setdefault('archived_clips',[]).append({'source_id':old_source,'transcript_id':old_take,'clips':current['clips']})
                current['clips']={}
            service.add_candidates(current,candidates)
            current['candidate_set']=analysis_adapter.candidate_set(list(current['clips'].values()),current.get('discovery',{}),
                source_id=media['source_id'],input_fingerprint=dependency)
        if kind in ('analyze','correction') and old_take!=current['transcript_id']:
            current['transcript_revision']+=1
            if kind=='correction':
                for group in [current.get('shared_corrections',{}),*current.get('clip_corrections',{}).values()]:
                    for patch in group.values():
                        if patch['transcript_id']==old_take:patch['transcript_id']=current['transcript_id']
        if kind=='analyze':current['source']['requires_analysis']=False
        if cid:
            service.variant(current,cid,vid).update(variant_updates)
            if kind=='boundary_review':
                keep=current['clips'][cid]['variants'];current['clips'][cid].update(reviewed);current['clips'][cid]['variants']=keep
        if kind=='export':current.setdefault('exports',[]).append(result)
    for attempt in range(5):
        current=check()
        try:
            saved=service.store.mutate(pid,current['revision'],job['id']+'-publish',{'job_id':job['id'],'dependency':dependency},publish,'Selesai: '+kind);break
        except Conflict:
            if attempt==4:raise
    editorial.release(cfg)
    service.queue.update(job['id'],status='completed',progress=100,message='Selesai dan tersimpan pada revisi '+str(saved['revision']),result=result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--db',required=True);parser.add_argument('--job',required=True);args=parser.parse_args()
    from .project_store import ProjectStore
    from .job_queue import JobQueue
    store=ProjectStore(args.db);queue=JobQueue(store,Path(args.db).parent,autostart=False,recover=False);job=queue.get(args.job)
    doc=store.get(job['project_id']);settings=doc.get('settings',{})
    cfg=Config(**{k:v for k,v in settings.items() if k in CONFIG_FIELDS})
    cfg=replace(cfg,work_dir=str(Path(args.db).resolve().parent))
    service=StudioService(Path(__file__).resolve().parent.parent,cfg,db_path=args.db,autostart=False,recover=False)
    try:execute(service,job)
    except StaleJob as exc:queue.update(args.job,status='stale',message=str(exc),error=str(exc))
    except BaseException as exc:
        traceback.print_exc();queue.update(args.job,status='failed',message='Proses gagal; perubahan dan hasil sebelumnya tetap tersedia.',error=str(exc)[-4000:]);return 1
    return 0


if __name__=='__main__':sys.exit(main())
