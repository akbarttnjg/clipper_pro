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
from .dependency_cache import content_id, render_key, asset_id


class StaleJob(ValueError):pass


def save_analysis_take(service,pid,media,transcript,cfg):
    """Keep immutable ASR evidence separate from glossary-dependent display text."""
    from .transcript_correction import VERSION
    transcript=copy.deepcopy(transcript)
    raw=copy.deepcopy(transcript.get('raw_words',transcript['words']))
    for i,word in enumerate(raw):word.setdefault('word_id',i)
    raw_take='asr-raw-'+fingerprint([pid,media['source_id'],media['payload']['audio_stream_id'],
        raw,transcript.get('language'),transcript.get('duration')])[:32]
    evidence={**transcript,'words':raw,'raw_words':raw,'heard_words':raw}
    evidence.pop('correction_report',None);evidence.pop('asr_corrections',None)
    try:service.store.transcript(raw_take)
    except KeyError:service.store.save_transcript(pid,evidence,raw_take)
    processing={key:getattr(cfg,key) for key in ('glossary','approved_aliases','audience','transcript_correction')}
    transcript.update(raw_words=raw,raw_take_id=raw_take,
        display_processing={'version':VERSION,'settings':processing})
    take='display-'+fingerprint([raw_take,VERSION,processing,transcript['words'],
        transcript.get('heard_words'),transcript.get('segments')])[:32]
    try:service.store.transcript(take)
    except KeyError:service.store.save_transcript(pid,transcript,take)
    return take


def execute(service,job):
    if job['kind']=='export_project':
        from .batch7 import export_project
        return export_project(service,job)
    if job['kind']=='evaluation':return evaluation_job(service,job)
    from . import media_context, evidence, transcript_correction, story, analysis_adapter, editorial
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
        from . import pipeline
        transcript,candidates=pipeline.analyze(source,cfg,progress)
        take=save_analysis_take(service,pid,media,transcript,cfg)
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
        elif kind=='asr_recheck':
            from . import speech_jobs
            original=service.store.transcript(doc['transcript_id']);heard=copy.deepcopy(original.get('heard_words',original.get('raw_words',original['words'])))
            groups=[doc.get('shared_corrections',{}),*doc.get('clip_corrections',{}).values()]
            protected={i for group in groups for patch in group.values() if patch['transcript_id']==doc['transcript_id'] for i in patch['origin_word_ids']}
            for word in heard:
                if set(transcript_correction.source_ids([word]))&protected:word['manually_edited']=True
            payload={**original,'words':heard};options=copy.deepcopy(job['request'].get('options',{}))
            if cid and not options.get('origin_word_ids'):
                selected=[w for w in heard if w['end']>doc['clips'][cid]['start'] and w['start']<doc['clips'][cid]['end'] and transcript_correction.suspect_reason(w)]
                if not selected:result={'checked':0,'accepted':0,'note':'Tidak ada kata berkeyakinan rendah dalam klip ini.'}
                else:options['origin_word_ids']=transcript_correction.source_ids(selected)[:80]
            if not result:
                progress(12,'Mendengarkan ulang rentang terarah dengan model ASR lokal')
                response=speech_jobs.run(kind,source,payload,cfg,options);result=response['report']
                if response['changes']:
                    for word in response['words']:word.pop('manually_edited',None)
                    refined=speech_jobs.rechecked_transcript(original,response,cfg)
                    take='rechecked-'+fingerprint([pid,doc['transcript_id'],refined['heard_words']])[:32]
                    try:service.store.transcript(take)
                    except KeyError:service.store.save_transcript(pid,refined,take)
                    updates['transcript_id']=take;updates['correction_report']=refined['correction_report']
            updates['speech_reports']={**doc.get('speech_reports',{}),'asr_recheck':result}
        elif kind=='alignment':
            from . import speech_jobs
            payload=transcript;options=copy.deepcopy(job['request'].get('options',{}))
            if cid and not options.get('origin_word_ids'):
                selected=[w for w in words if w['end']>doc['clips'][cid]['start'] and w['start']<doc['clips'][cid]['end']
                    and (w.get('correction') or w.get('manually_edited') or len(w['word'].split())>1) and not w.get('aligned_words')]
                options['origin_word_ids']=transcript_correction.source_ids(selected)[:80]
                if not selected:result={'aligned':0,'attempted':0,'status':'skipped','errors':[],'device':'cpu','note':'Tidak ada frasa dalam klip ini yang memerlukan alignment.'}
            progress(12,'Menyelaraskan frasa yang dikoreksi dengan model CTC lokal pada CPU')
            response=speech_jobs.run(kind,source,payload,cfg,options) if not result else {'report':result,'patches':[]};result=response['report']
            alignment_patches=response['patches']
            updates['speech_reports']={**doc.get('speech_reports',{}),'alignment':result}
        elif kind=='boundary_review':
            reviewed=story.review_candidate(doc['clips'][cid],transcript,cfg,refresh=True)
            result={'review':reviewed}
        elif kind in ('visual_review','style_review'):
            from . import composition,editplan,ffmpeg_util,visual4
            from .studio_exchange import render_words
            clip={k:v for k,v in doc['clips'][cid].items() if k!='variants'};variant=service.variant(doc,cid,vid)
            if variant.get('timeline'):clip['manual_keep_spans']=variant['timeline']['keep_spans']
            display=render_words(transcript,doc,clip,cfg)
            progress(10,'Memeriksa wajah, materi dan ruang teks sepanjang klip')
            from .pipeline import source_plan
            display,plan=source_plan(source,display,clip,cfg,ffmpeg_util.probe(source),context_words=transcript['words'])
            if kind=='style_review':
                from .typography import make_plan
                from .placement import caption_anchors
                from .subtitle_edit import clean
                from .style5 import readability,annotate_prosody
                from . import render
                cleaned,_,_=clean(plan['words'],cfg.caption_cleanup,cfg.caption_punctuation,cfg)
                voice=render.voice_stem(source,plan,cfg,work/'style-review-audio')
                cleaned=annotate_prosody(cleaned,voice)
                plan['display_words']=cleaned
                captions=make_plan(cleaned,cfg,clip.get('keywords',[]),anchors=caption_anchors(plan,cfg))
                result=readability(captions,cfg)
                for phrase in result['phrases']:
                    span=next((s for s in plan['spans'] if s['start']<=phrase['start']<s['end']),None)
                    if span:phrase['source_start']=span['source_start']+phrase['start']-span['start']
                variant_updates.update(style_report=result,style_dependency=dependency)
            else:
                result=visual4.report(plan,source,cfg)
                variant_updates.update(visual_report=result,visual_dependency=dependency)
        elif kind in ('asset_proposals','asset_visual_review'):
            from . import illustrations
            clip={k:v for k,v in doc['clips'][cid].items() if k!='variants'}
            if cfg.broll_mode=='off':cfg=replace(cfg,broll_mode='local')
            recipe=illustrations.prepare(words,clip,cfg,progress,input_fingerprint=dependency)
            proposals=analysis_adapter.asset_proposal_set(recipe,source_id=media['source_id'],input_fingerprint=dependency,cfg=cfg)
            variant_updates.update(recipe=recipe,asset_proposals=proposals)
            if service.variant(doc,cid,vid).get('settings',{}).get('broll_mode',doc['settings'].get('broll_mode','off'))=='off':
                variant_updates['settings']={**service.variant(doc,cid,vid).get('settings',{}),'broll_mode':'local'}
            result={'proposals':len(recipe.get('scenes',[])),'notes':recipe.get('notes',[])}
        elif kind in ('preview','render'):
            from . import pipeline
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
                    work_dir=str(folder),out_dir=str(folder/'output'),job_id='',preview_seconds=0,
                    audio_cache_dir=cfg.audio_cache_dir or str(work),visual_cache_dir=cfg.visual_cache_dir or str(work/'visual4'))
                folder.mkdir(parents=True,exist_ok=True)
                if (work/'source-evidence.json').is_file():write_json(folder/'source-evidence.json',read_json(work/'source-evidence.json'))
            key=render_key(source,words,clip,cfg,fresh=True)
            # A full-content manifest is checked on every reuse, including the output itself.
            cached=read_json(Path(cfg.work_dir)/'render-cache'/f'{key}.json',{})
            path=Path(cached.get('absolute_file',''))
            if not job['request'].get('options',{}).get('force') and path.is_file() and cached.get('output_content_id')==content_id(path,fresh=True) and cached.get('plan_content_id') and cached['plan_content_id']==asset_id(cached.get('plan_path'),fresh=True):result=cached
            else:
                name=f'{cid}-{vid}-{key[:12]}'
                result=pipeline.render_clip(source,words,clip,name,cfg,progress,context_words=transcript['words'])
                path=Path(cfg.out_dir)/result['file']
                result.update(absolute_file=str(path.resolve()),output_content_id=content_id(path,fresh=True),fingerprint=key,dependency=dependency,
                    variant_id=vid,input_revision=doc['revision'],kind=kind,quality=job['request'].get('options',{}).get('quality','draft') if kind=='preview' else 'final')
                for field,suffix in [('ass_url','.ass'),('srt_url','.srt'),('credits_url','.credits.txt')]:
                    original=Path(cfg.out_dir)/(result[field].removeprefix('/clips/'))
                    result[field]=service.register_file(pid,original)
                result['url']=service.register_file(pid,path)
                result['plan_content_id']=content_id(result['plan_path'],fresh=True)
                write_json(Path(cfg.work_dir)/'render-cache'/f'{key}.json',result)
            plan=read_json(result['plan_path'],{})
            from . import visual4
            visual_report=visual4.report(plan,source,cfg)
            exchange=records(plan,result,doc,cid,vid,cfg,media)
            exchange_path=Path(result['plan_path']).with_name('exchange.json');write_json(exchange_path,exchange)
            result['exchange_path']=str(exchange_path)
            variant_updates.update({('preview' if kind=='preview' else 'result'):result,'schedule':plan.get('broll_schedule',[]),'schedule_dependency':dependency,
                'timeline_summary':{k:plan.get(k) for k in ('spans','duration','fps','width','height','warnings','audio_quality')},
                'shot_summary':[{k:s.get(k) for k in ('start','end','source_start','source_end','mode','has_material','composition_reason')} for s in plan.get('shots',[])],
                'visual_report':visual_report,'visual_dependency':dependency,
                'style_report':plan.get('style_report',{}),'style_dependency':dependency})
            result['evaluation_context']={'source_id':media['source_id'],'audio_stream_id':media['payload']['audio_stream_id'],
                'transcript_id':doc['transcript_id'],'word_fingerprint':fingerprint(words),
                'source_spans':[[s['source_start'],s['source_end']] for s in plan['spans']],
                'variant_id':vid,'width':cfg.target_w,'height':cfg.target_h,'fps':plan['fps'],
                'duration':plan['duration'],'quality':result.get('quality'),
                'audio_mix_content_id':content_id(plan['audio']['mix'],fresh=True)}
            from .workflow6 import BRAND_FIELDS
            result['evaluation_settings']={k:v for k,v in asdict(cfg).items() if k in BRAND_FIELDS}
            service.store.artifact(pid,cid,vid,kind,key,result)
        elif kind=='export':
            from . import projects
            final=service.variant(doc,cid,vid).get('result')
            if not final or final.get('dependency')!=dependency:raise ValueError('Render final revisi aktif dahulu sebelum ekspor editor')
            if not Path(final['absolute_file']).is_file() or content_id(final['absolute_file'],fresh=True)!=final['output_content_id']:raise ValueError('Berkas final berubah atau hilang; render ulang')
            if final.get('plan_content_id') and content_id(final['plan_path'],fresh=True)!=final['plan_content_id']:raise ValueError('Rencana final berubah; render ulang')
            result=projects.export_bundle([final],cfg,progress,mode=job['request'].get('options',{}).get('mode','hybrid'))
            result['url']=service.register_file(pid,result['zip']);result['clip_id']=cid;result['variant_id']=vid
            result.update(dependency=dependency,input_revision=doc['revision'])
            result['package_content_id']=content_id(result['zip'],fresh=True)
            result['reference']={k:final.get(k) for k in ('width','height','length','output_content_id','input_revision')}
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
        if kind in ('analyze','correction','asr_recheck') and old_take!=current['transcript_id']:
            current['transcript_revision']+=1
            compatible=kind in ('correction','asr_recheck')
            if kind=='analyze' and old_take and old_source==media['source_id'] and old_audio==media['payload']['audio_stream_id']:
                before=service.store.transcript(old_take)
                after=service.store.transcript(current['transcript_id'])
                compatible=before.get('raw_words',before['words'])==after.get('raw_words',after['words'])
            if kind=='analyze':
                current['transcript_lineage']={'from':old_take,'to':current['transcript_id'],
                    'manual_patches_preserved':compatible,'basis':'identical_source_audio_and_raw_words' if compatible else 'new_asr_evidence'}
            if compatible:
                for group in [current.get('shared_corrections',{}),*current.get('clip_corrections',{}).values()]:
                    for patch in group.values():
                        if patch['transcript_id']==old_take:patch['transcript_id']=current['transcript_id']
                timing=current.get('alignment_overrides',{})
                for group in [timing.get('shared',{}),*timing.get('clips',{}).values()]:
                    for patch in group.values():
                        if patch['transcript_id']==old_take:patch['transcript_id']=current['transcript_id']
        if kind in ('analyze','discovery') and current.get('discovery'):
            current['discovery']['transcript_id']=current['transcript_id']
            current['discovery']['transcript_revision']=current['transcript_revision']
        if kind=='alignment':
            patches=current.setdefault('alignment_overrides',{})
            group=patches.setdefault('clips',{}).setdefault(cid,{}) if cid else patches.setdefault('shared',{})
            for patch in alignment_patches:
                patch['transcript_id']=current['transcript_id'];patch['provenance'].update(source_id=media['source_id'],audio_stream_id=media['payload']['audio_stream_id'])
                from .stage3 import store_alignment
                store_alignment(group,patch)
            if alignment_patches:current['transcript_revision']+=1
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
    message='Selesai dan tersimpan pada revisi '+str(saved['revision'])
    if kind=='alignment':
        if result.get('errors'):
            message=f"Alignment perlu diperiksa: {result.get('aligned',0)} frasa berhasil, {len(result['errors'])} ditolak. Buka Alignment terakhir."
        elif not result.get('aligned'):
            message='Tidak ada koreksi baru yang perlu diselaraskan. Model belum menjalankan pengukuran.'
        else:message=f"Alignment berhasil: {result['aligned']} frasa diselaraskan pada CPU; tersimpan pada revisi {saved['revision']}."
    service.queue.update(job['id'],status='completed',progress=100,message=message,result=result)
    return result


def evaluation_job(service,job):
    """CPU comparison path avoids loading any ASR/CV/model or canonical decoder."""
    from .evaluation6 import evaluate_artifacts
    pid=job['project_id'];cid=job['target']['clip_id'];vid=job['target']['variant_id'];dependency=job['request']['dependency']
    def check():
        doc=service.store.get(pid)
        if service.queue.get(job['id'])['status'] in ('cancel_requested','canceled'):raise StaleJob('Evaluasi dibatalkan.')
        if dependency!=service.dependency(doc,cid,vid,fresh=True):raise StaleJob('Revisi masukan berubah; jalankan evaluasi ulang.')
        if content_id(doc['source']['path'],fresh=True)!=doc['source']['source_id']:raise StaleJob('Sumber berubah.')
        return doc
    def progress(value,message):service.queue.update(job['id'],progress=int(value),message=message)
    check();value=evaluate_artifacts(service,pid,job['request'].get('options',{}),progress);check()
    result=service.workspace.append('evaluations6',pid,value)
    for attempt in range(5):
        current=check()
        try:
            service.store.mutate(pid,current['revision'],job['id']+'-publish',{'evaluation_id':result['id']},
                lambda d: service.variant(d,cid,vid).update(evaluation_report=result),'Evaluasi dua hasil tersimpan')
            break
        except Conflict:
            if attempt==4:raise
    service.queue.update(job['id'],status='completed',progress=100,result=result,message='Perbedaan piksel diukur; penilaian manusia dapat diisi.')
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
    from .runtime.gpu import GPULease
    from .runtime.state import runtime_root
    import os
    os.environ['CLIPPER_RUNTIME_DIR']=str(runtime_root(service.root,service.work))
    try:
        with GPULease(runtime_root(service.root,service.work),'proyek '+job['kind']):
            try:execute(service,job)
            finally:
                from .editorial import release
                release(service.config(doc))
    except StaleJob as exc:queue.update(args.job,status='stale',message=str(exc),error=str(exc))
    except BaseException as exc:
        traceback.print_exc();queue.update(args.job,status='failed',message='Proses gagal; perubahan dan hasil sebelumnya tetap tersedia.',error=str(exc)[-4000:]);return 1
    return 0


if __name__=='__main__':sys.exit(main())
