"""Atomic M7 delivery sets: coverage, final QC, portable editors and publishing kit."""
import copy,hashlib,json,os,shutil,zipfile
from dataclasses import replace
from pathlib import Path
from .artifact_store import ArtifactSet,verify
from .contracts import fingerprint
from .delivery7_contract import VERSION,options,capabilities,TARGETS
from .dependency_cache import content_id
from .storage import read_json,write_json
from . import delivery7_media as media


def key(result):
    return hashlib.sha256((str(result['clip_id'])+'|'+str(result['variant_id'])).encode()).hexdigest()[:20]


def copy_checked(source,dest,expected=None):
    source=Path(source);dest=Path(dest)
    before=content_id(source,fresh=True)
    if expected and before!=expected:raise ValueError('Masukan berubah sebelum ekspor: '+source.name)
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    if content_id(dest,fresh=True)!=before:raise ValueError('Salinan paket berubah: '+dest.name)
    return before


def import_editors(results,cfg,destination,published_destination,choices,progress):
    """Preserve existing CapCut writer; freeze exact master as its active audio."""
    from .projects import export_bundle
    from .delivery7_install import rewrite
    package=export_bundle(results,cfg,progress,mode=choices['mode'],master_audio=True)
    wanted=[k for k in ('capcut','resolve') if k in choices['editors']]
    for editor in wanted:
        state=package['editors'][editor]
        if state['construction_status']!='generated' or state['structural_status']!='passed':raise ValueError('Paket '+editor+' tidak lengkap: '+'; '.join(state['issues'][:8]))
    shutil.copytree(package['folder'],destination)
    rewrite(destination,str(Path(package['folder']).resolve()),str(published_destination.resolve()))
    # The temporary producer folder is disposable only after its verified copy exists.
    shutil.rmtree(package['folder']);Path(package['zip']).unlink(missing_ok=True)
    return {k:{**package['editors'][k],'target_version':TARGETS[k]} for k in wanted}


def publish_kit(plan,result,folder,revision):
    from .delivery7_sidecars import cue_rows
    folder.mkdir(parents=True,exist_ok=True);cues=cue_rows(plan)
    title=str(result.get('title') or 'Clip').strip()[:160];tags=[str(t)[:60] for t in plan.get('keywords',[])][:30]
    metadata={'schema_version':1,'title':title,'description':' '.join(r['text'] for r in cues),'tags':tags,
        'caption':' '.join(r['text'] for r in cues),'clip_id':result['clip_id'],'variant_id':result['variant_id'],
        'revision':revision,'clip_revision':plan.get('revision'),'plan_content_id':result['plan_content_id'],
        'reviewed_output_content_id':result['output_content_id'],'generation':'local extract from approved title/captions; no remote posting'}
    write_json(folder/'metadata.json',metadata)
    (folder/'title.txt').write_text(title,encoding='utf-8');(folder/'description.txt').write_text(metadata['description'],encoding='utf-8')
    (folder/'tags.txt').write_text(' '.join(tags),encoding='utf-8');(folder/'caption.txt').write_text(metadata['caption'],encoding='utf-8')
    media.run(['ffmpeg','-nostdin','-v','error','-y','-ss',str(min(.5,plan['duration']/2)),'-i',str(result['absolute_file']),'-frames:v','1','-q:v','2',str(folder/'cover.jpg')])
    return metadata


def build(results,cfg,request=None,*,project_id='',revision=0,dependency='',progress=lambda p,m:None,before_seal=lambda:None):
    from .library_paths import project_root
    from .delivery7_sidecars import write as sidecars,validate as sidecar_qc
    from .delivery7_fonts import freeze as fonts
    from .delivery7_exchange import write as exchange
    choices=options(request)
    ids=[(r['clip_id'],r['variant_id']) for r in results]
    if not results or len(set(ids))!=len(ids):raise ValueError('Coverage M7 kosong/duplikat')
    expected={(cid,vid) for cid in {r['clip_id'] for r in results} for vid in choices['ratios']}
    if set(ids)!=expected:raise ValueError('Coverage clip × ratio tidak lengkap')
    for r in results:
        if content_id(r['absolute_file'],fresh=True)!=r['output_content_id'] or content_id(r['plan_path'],fresh=True)!=r['plan_content_id']:raise ValueError('Final/plan berubah; render ulang')
        if not verify(r):raise ValueError('ArtifactSet final tidak lengkap; render ulang sebelum M7')
    txn=ArtifactSet(project_root(cfg)/'delivery7-sets',{'kind':'delivery_m7','version':VERSION,'project_id':project_id,
        'requested_revision':revision,'dependency':dependency,'coverage':[list(i) for i in ids]})
    root=txn.staging/'Package';published=txn.final/'Package';root.mkdir();coverage=[];checks=[];exchanges=[];editor_status={};roles={}
    def role(path,label):roles[Path(path).relative_to(root).as_posix()]=label
    try:
        for i,result in enumerate(results):
            before_seal();p=read_json(result['plan_path']);name=key(result);folder=root/'Clips'/name;folder.mkdir(parents=True)
            if p.get('revision')!=result.get('revision'):raise ValueError('Revisi plan dan final berbeda')
            progress(int(4+44*i/len(results)),f'M7 · QC dan sidecar {i+1}/{len(results)}')
            final=folder/'final.mp4';receipt=media.final(result['absolute_file'],final,p,cfg,choices['profile']);role(final,'final_mp4')
            copy_checked(result['plan_path'],folder/'reference-plan.json',result['plan_content_id']);role(folder/'reference-plan.json','provenance_plan; source paths are historical evidence')
            ref={'project_id':project_id,'requested_revision':revision,'clip_id':result['clip_id'],'variant_id':result['variant_id'],
                 'output_content_id':receipt['output_content_id'],'reviewed_output_content_id':result['output_content_id'],'plan_content_id':result['plan_content_id']}
            sidecars(p,folder/'Sidecars',reference=ref);sidecar_report=sidecar_qc(folder/'Sidecars',p)
            for path in (folder/'Sidecars').iterdir():role(path,'subtitle_transcript_same_revision')
            font_rows=fonts(p,root/'Fonts',cfg.fonts_dir)
            for f in font_rows:role(root/'Fonts'/f['file'],'licensed_font')
            write_json(folder/'font-provenance.json',[{k:v for k,v in f.items() if k!='path'} for f in font_rows])
            derived={}
            if choices['clean'] or choices['alpha']:
                clean=folder/'clean.mp4';derived['clean']=media.clean(p,cfg,clean);role(clean,'caption_free_video; other layers baked')
            if choices['alpha']:
                alpha=folder/'captions-alpha.mov';derived['alpha']=media.alpha(p,cfg,folder/'Sidecars/captions.ass',alpha);role(alpha,'caption_alpha_qtrle_argb')
            if choices['stems']:
                tracks={**p.get('audio',{}).get('stems',{}),'master':p['audio']['mix']};stem_rows=[]
                if not tracks:raise ValueError('Stem wajib tidak tersedia')
                for kind,source in tracks.items():
                    if not isinstance(kind,str) or not kind or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in kind):raise ValueError('Nama stem tidak aman')
                    target=folder/'Stems'/(kind+'.wav');copy_checked(source,target);report=media.audio_qc(target,p['duration'])
                    role(target,'active_final_master' if kind=='master' else 'premaster_stem_reference; not an identical-master editable mix')
                    stem_rows.append({'name':kind,'file':target.name,'content_id':content_id(target,fresh=True),'qc':report})
                write_json(folder/'Stems/manifest.json',{'tracks':stem_rows,'policy':'Master is active in editor. Premaster stems may not sum to nonlinear limited/normalized master; do not enable both.'})
            if choices['publish']:
                metadata=publish_kit(p,result,folder/'Publish',revision);metadata['delivered_output_content_id']=receipt['output_content_id'];write_json(folder/'Publish/metadata.json',metadata)
                for path in (folder/'Publish').iterdir():role(path,'publish_kit_revision_bound')
            row={**ref,'key':name,'title':result['title'],'file':final.relative_to(root).as_posix(),
                'width':p['width'],'height':p['height'],'fps':p['fps'],'frames':p['duration_frames'],'duration':p['duration'],
                'reference':{'width':p['width'],'height':p['height'],'duration':p['duration'],'output_content_id':receipt['output_content_id']},
                'local_path':str(final),'path':str(published/final.relative_to(root))}
            coverage.append(row);checks.append({'key':name,'final_qc':receipt,'sidecar_qc':sidecar_report,'derived':derived})
            matrix=[r for r in capabilities(p,choices['mode']) if r['editor'] in choices['editors']]
            write_json(folder/'capabilities.json',matrix)
            exchanges.append({'key':name,'writers':exchange([row],folder/'Exchange',result['title'],choices['editors'])})
        if set(ids)!={(r['clip_id'],r['variant_id']) for r in coverage}:raise ValueError('Coverage klip/rasio tidak lengkap')
        if any(e in choices['editors'] for e in ('capcut','resolve')):
            progress(52,'M7 · proyek editor dan master final')
            editor_status=import_editors(results,cfg,root/'Editors',published/'Editors',choices,lambda p,m:progress(52+int(p*.25),m))
        merged_rows=[]
        if choices['merged']:
            for ratio in choices['ratios']:
                subset=[r for r in coverage if r['variant_id']==ratio]
                if not subset:raise ValueError('Coverage rasio gabungan hilang')
                folder=root/'Merged'/ratio;folder.mkdir(parents=True);output=folder/'merged.mp4'
                receipt=media.merged(subset,output,cfg);role(output,'merged_baked_final');offset=0;members=[]
                for row in subset:
                    members.append({'key':row['key'],'clip_id':row['clip_id'],'variant_id':ratio,'start_frame':offset,'end_frame':offset+row['frames']});offset+=row['frames']
                writers=exchange(subset,folder/'Exchange','Clipper · '+ratio,choices['editors'])
                write_json(folder/'timeline.json',{'fps':subset[0]['fps'],'frames':offset,'members':members,'layers':'baked final clips; cut boundaries preserved'})
                merged_rows.append({'variant_id':ratio,'file':output.relative_to(root).as_posix(),'frames':offset,'members':members,'qc':receipt,'writers':writers})
                # Native merged timelines deliberately use final-picture cuts. Captions are baked.
                if any(e in choices['editors'] for e in ('capcut','resolve')):
                    audio=folder/'master.wav';media.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(output),'-vn','-ar','48000','-ac','2','-c:a','pcm_s16le',str(audio)],receipt['duration']);role(audio,'merged_final_audio')
                    p={'revision':revision,'width':subset[0]['width'],'height':subset[0]['height'],'fps':subset[0]['fps'],'duration_frames':offset,'duration':offset/subset[0]['fps'],
                        'source':{'path':str(output),'fps':subset[0]['fps'],'width':subset[0]['width'],'height':subset[0]['height'],'duration':offset/subset[0]['fps']},
                        'shots':[{'start_frame':r['start_frame'],'duration_frames':r['end_frame']-r['start_frame'],'start':r['start_frame']/subset[0]['fps'],'end':r['end_frame']/subset[0]['fps'],
                          'source_start':r['start_frame']/subset[0]['fps'],'source_end':r['end_frame']/subset[0]['fps'],'rect':[0,0,subset[0]['width'],subset[0]['height']],
                          'mode':'fill','face_rect':None,'zoom_at':None} for r in members],
                        'captions':{'phrases':[]},'style':{},'audio':{'stems':{'master':str(audio)},'mix':str(audio)}}
                    empty_ass=folder/'captions.ass'
                    empty_ass.write_text('[Script Info]\nScriptType: v4.00+\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n',encoding='utf-8')
                    p['subtitle_path']=str(empty_ass);plan_path=folder/'editor-input-plan.json';write_json(plan_path,p)
                    native_result={'title':'Semua klip · '+ratio,'clip_id':'merged-'+ratio,'variant_id':ratio,'revision':revision,
                        'plan_path':str(plan_path),'plan_content_id':content_id(plan_path,fresh=True),'absolute_file':str(output),
                        'output_content_id':content_id(output,fresh=True),'width':p['width'],'height':p['height'],'length':p['duration']}
                    merged_rows[-1]['editors']=import_editors([native_result],cfg,folder/'Editors',published/folder.relative_to(root)/'Editors',
                        {**choices,'mode':'native'},lambda _p,_m:None)
                    write_json(folder/'Editors/capabilities.json',{'native_status':'not_tested','caption':'baked','picture_cuts':'editable_candidate',
                        'audio':'final master only','members':members})
        # All native path references point to the eventual sealed root, then the extractor relinks them.
        from .delivery7_install import rewrite
        rewrite(root,str(root.resolve()),str(published.resolve()))
        shutil.copy2(Path(__file__).with_name('delivery7_install.py'),root/'SIAPKAN_PAKET.py')
        shutil.copy2(Path(__file__).with_name('project_install.py'),root/'EDITOR_RELINK_HELPER.py')
        for name,flag in [('CEK_PAKET.cmd','--check'),('SIAPKAN_PAKET.cmd','')]:
            (root/name).write_bytes(('@echo off\r\ncd /d "%~dp0"\r\nwhere py >nul 2>nul\r\nif errorlevel 1 (python SIAPKAN_PAKET.py '+flag+') else (py -3 SIAPKAN_PAKET.py '+flag+')\r\npause\r\n').encode())
        guide='''# Paket delivery M7

Jalankan CEK_PAKET.cmd lalu SIAPKAN_PAKET.cmd setelah ekstraksi atau pemindahan.
Clips/<key>/final.mp4 adalah hasil yang diperiksa. Sidecars berisi SRT, VTT,
ASS, TXT dan JSON dari revisi caption yang sama. metadata Publish menautkan hash final.

CapCut Desktop 4.7.0: setelah SIAPKAN_PAKET, jalankan Editors/PASANG_CAPCUT.cmd.
Draft per clip di Editors/CapCut/CLIP_XX merupakan fallback utama bila wrapper
multi timeline ditolak: py -3 PASANG_PROYEK.py --capcut --individual (di Editors).
Master final satu track aktif; stem premaster tidak boleh dicampur ulang bersama master.
Resolve Free 18.6.6: impor Editors/DaVinci/*/timeline.xml; teks/font EX05 tetap backlog.
Script Fusion disediakan sebagai kandidat, belum dinyatakan lolos native.
Merged/<rasio>/Editors memuat kandidat timeline gabungan; caption di sana menyatu
pada gambar. CapCut: jalankan PASANG_CAPCUT.cmd pada folder Editors tersebut.
Resolve: XML di DaVinci pada folder yang sama.

Premiere: Exchange/timeline.xml (FCP7 XML). Final Cut: timeline.fcpxml (1.7).
OTIO: timeline.otio. Semua exchange ini memakai video final, termasuk teks/efek
bakar; potongan media dapat disusun ulang, teks tidak menjadi native editable.
Fonts hanya membawa face yang dirujuk beserta izin/lisensi. Periksa lisensi font
custom sebelum menerbitkan. Source path di reference-plan adalah provenance,
bukan ketergantungan runtime editor. Aset editor aktif berada di paket.

Clean = tanpa caption, dengan b-roll/finishing menyatu. Alpha opsional adalah
caption-only qtrle ARGB MOV, dipasangkan di atas clean. Stem/master adalah WAV
48 kHz; master merupakan rujukan ducking/normalisasi/limiter final.
Publikasi manual: cover, judul, deskripsi, tag dan caption di Publish.
Tidak ada unggahan otomatis. Tautan review lokal memerlukan server yang berjalan,
izin dan masa berlaku. Mode review-only tetap dapat menampilkan data video;
ini pembatasan endpoint, bukan DRM. Jangan membuka server ke internet tanpa
konfigurasi jaringan/autentikasi yang sesuai.

Struktur/codec/full decode bukan bukti impor, font atau estetika di aplikasi target.
CapCut 4.7.0, Resolve 18.6.6, Premiere dan Final Cut harus diuji di mesin pengguna.
'''
        (root/'BACA_DULU.md').write_text(guide,encoding='utf-8')
        files=[]
        for path in sorted(root.rglob('*')):
            if path.is_symlink():raise ValueError('Symlink paket tidak diizinkan')
            if path.is_file():files.append({'path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,'content_id':content_id(path,fresh=True),
                'role':roles.get(path.relative_to(root).as_posix(),'editor_project' if 'Editors' in path.parts else 'qc_or_manifest_or_support')})
        rows=[{k:v for k,v in r.items() if k not in ('local_path','path')} for r in coverage]
        manifest={'schema_version':1,'version':VERSION,'created_root':str(published.resolve()).replace('\\','/'),'project_id':project_id,'requested_revision':revision,
            'dependency':dependency,'options':choices,'coverage':rows,'files':files,'checks':checks,'editors':editor_status,'exchange':exchanges,'merged':merged_rows,
            'gate_g7':'pending_target_editor_acceptance','native_editor_status':'not_tested','portable_asset_policy':'relative inventory + checked native relink; no external active media',
            'status':'validated','review_policy':'permission/expiry bound immutable ArtifactSet; local URL only'}
        write_json(root/'delivery.json',manifest)
        before_seal()
        from .delivery7_install import verify as verify_package
        verify_package(root)
        archive=txn.staging/'Clipper_M7_Delivery.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
            for path in sorted(root.rglob('*')):
                if path.is_file():z.write(path,'Clipper_M7_Delivery/'+path.relative_to(root).as_posix())
        with zipfile.ZipFile(archive) as z:
            if z.testzip():raise ValueError('CRC ZIP M7 gagal')
            if len(z.namelist())!=len(files)+1:raise ValueError('Anggota ZIP M7 tidak lengkap')
        txn.metadata['required_members']=[p.relative_to(txn.staging).as_posix() for p in txn.staging.rglob('*') if p.is_file()]
        before_seal();sealed=txn.seal()
        return {**sealed,'version':VERSION,'folder':str(published),'zip':str(txn.final/archive.name),'delivery_manifest_path':str(published/'delivery.json'),
            'package_content_id':content_id(txn.final/archive.name,fresh=True),'dependency':dependency,'input_revision':revision,
            'coverage':rows,'timelines':len(rows),'structural_status':'passed','editors':editor_status,'native_editor_status':'not_tested',
            'gate_g7':'pending_target_editor_acceptance','target_versions':TARGETS,'export_mode':choices['mode'],'options':choices,
            'note':'M7: final dan kelengkapan lolos; impor aplikasi target serta penilaian manusia masih perlu.'}
    except BaseException as exc:txn.abort(exc);raise
