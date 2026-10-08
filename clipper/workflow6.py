"""Stage 6 workspace policy. No model, network, or automatic render at import."""
import copy
import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from .config import validate_overrides
from .contracts import fingerprint
from .dependency_cache import content_id
from .project_store import Conflict, dumps

VERSION = '4.0.6'
BRAND_FIELDS = frozenset({'style_preset','font_main','font_accent','accent_hex','base_hex',
    'caption_style','caption_position','caption_align','caption_scale','caption_backdrop',
    'motion_intensity','layout','material_share','semantic_emphasis','safe_placement'})
SOURCE_FIELDS = frozenset({'language','audio_stream_index','whisper_model','whisper_device',
    'whisper_compute','whisper_isolate','asr_second_pass','asr_recheck_windows','alignment_model_path',
    'audience','glossary','transcript_correction','model','ollama_num_ctx','ollama_num_gpu',
    'processing_mode','source_kind','min_clip_s','max_clip_s','search_depth','num_clips',
    'analysis_window_s','analysis_overlap_s','discovery_extra_windows','selection_floor',
    'adaptive_clips','topic_grace_s','topic_review','ocr_enabled','ocr_max_frames','ocr_interval_s',
    'visual_cues','vision_model','ollama_url','ollama_timeout'})
SOURCE_ONLY = {'waveform': frozenset({'audio_stream_index'}),
    'source_evidence': frozenset({'audio_stream_index','ocr_enabled','ocr_max_frames','ocr_interval_s','visual_cues','vision_model'}),
    'correction': frozenset({'audio_stream_index','audience','glossary','transcript_correction','model','ollama_num_ctx','ollama_num_gpu','ollama_url','ollama_timeout'})}
EXPORT_MODES = {
    'preserved': {'label':'Tampilan terjaga', 'editable_layers':[],
        'baked_layers':['video','caption','illustration','audio_mix'],
        'limitations':['MP4 mempertahankan hasil final. Teks, framing, dan efek di dalam MP4 sudah menyatu.',
            'SRT/ASS disertakan sebagai berkas pendamping; tidak otomatis menjadi layer editor.']},
    'hybrid': {'label':'Hibrida', 'editable_layers':['caption_text','audio_stems','broll_track'],
        'baked_layers':['source_framing','source_zoom','broll_plate_geometry'],
        'limitations':['Framing dan zoom sumber menyatu dalam video tanpa teks.',
            'CapCut: blur/fade teks belum dipetakan. Resolve: Text+ dan metrik font perlu diuji native.',
            'B-roll dapat dipindah/dipangkas; isi plate ilustrasi sudah dirender.']},
    'native': {'label':'Native dasar', 'editable_layers':['source_cuts','static_crop','caption_text','audio_stems','broll_track'],
        'baked_layers':['broll_plate_geometry'],
        'limitations':['Hanya shot crop tunggal tanpa zoom animasi; layout materi + pembicara memakai mode hibrida.',
            'Salinan video sumber utuh masuk paket agar potongan dan crop dapat diedit.',
            'Posisi/ukuran teks dipetakan; kesamaan blur, fade, font dan hasil akhir belum dibuktikan di editor.']}}


def brand_values(values):
    if not isinstance(values, dict) or not values or set(values)-BRAND_FIELDS:
        raise ValueError('Brand kit hanya menyimpan font, warna, gerak dan aturan layout.')
    validated = validate_overrides(values)
    # Reject silent drops/clamps, including invalid fonts and non-finite sizes.
    if set(validated)!=set(values) or any(validated[k]!=values[k] for k in values):
        raise ValueError('Nilai brand kit tidak valid atau di luar batas.')
    return validated


def native_reasons(plan):
    if not plan or not plan.get('shots'):return ['Render final dahulu untuk memeriksa shot.']
    reasons=[]
    if any(s.get('mode') not in ('fill','fit') for s in plan['shots']):
        reasons.append('Komposisi beberapa area tidak dipetakan ke crop native; gunakan hibrida.')
    if any(s.get('zoom_at') is not None for s in plan['shots']):
        reasons.append('Zoom bergerak belum memiliki pemetaan identik di kedua editor; gunakan hibrida.')
    if any(s.get('mode')=='fit' and s.get('image_height',plan.get('height'))!=plan.get('height') for s in plan['shots']):
        reasons.append('Area fit dengan tinggi khusus belum dipetakan ke native; gunakan hibrida.')
    return reasons


def export_options(variant):
    from .storage import read_json
    plan=read_json(variant.get('result',{}).get('plan_path',''),{})
    rows=[]
    for mode,entry in EXPORT_MODES.items():
        reasons=native_reasons(plan) if mode=='native' else []
        rows.append({'id':mode,**copy.deepcopy(entry),'available':not reasons,'reasons':reasons,
            'native_status':'not_tested','target_versions':{'capcut':'9.5.0','resolve':'21'}})
    return rows


def stage_status(doc):
    source=doc.get('source',{});variants=[v for c in doc.get('clips',{}).values() for v in c['variants'].values()]
    return [
        {'id':'source','label':'Sumber','ready':bool(doc.get('transcript_id')) and not source.get('requires_analysis') and not source.get('changed'),
         'help':'Bahasa, track suara dan kamus memengaruhi analisis. Perubahan warna hanya memerlukan preview/final baru.'},
        {'id':'story','label':'Pilih klip','ready':bool(doc.get('clips')), 'count':len(doc.get('clips',{})),
         'help':'Dengarkan awal/akhir dan tinjau kandidat ditolak; durasi boleh melewati batas lunak agar cerita selesai.'},
        {'id':'edit','label':'Tata gaya','ready':any(v.get('style_report') and not v['style_report'].get('stale') for v in variants),
         'help':'Simpan pengaturan pada rasio aktif, periksa keterbacaan, lalu bandingkan preview. Brand kit menjaga koreksi manual.'},
        {'id':'results','label':'Periksa / ekspor','ready':any(v.get('export_readiness',{}).get('status')=='ready' for v in variants),
         'help':'Periksa final revisi aktif dan batas layer setiap mode. Struktur paket dan bukti impor editor memiliki status terpisah.'}]


class Workspace:
    def __init__(self,service):
        self.service=service;self.store=service.store
        with self.store.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS brand_kits(id TEXT PRIMARY KEY,revision INTEGER,name TEXT,settings TEXT,updated REAL);
              CREATE TABLE IF NOT EXISTS workspace_preferences(id TEXT PRIMARY KEY,data TEXT);
              CREATE TABLE IF NOT EXISTS evaluations6(id TEXT PRIMARY KEY,project_id TEXT,data TEXT,created REAL);
              CREATE TABLE IF NOT EXISTS native_evidence6(id TEXT PRIMARY KEY,project_id TEXT,data TEXT,created REAL);
              CREATE TABLE IF NOT EXISTS feedback6(id TEXT PRIMARY KEY,project_id TEXT,data TEXT,created REAL);
            ''')

    def kits(self):
        with self.store.connect() as db:rows=db.execute('SELECT * FROM brand_kits ORDER BY name,id').fetchall()
        return [{**dict(r),'settings':json.loads(r['settings'])} for r in rows]

    def kit(self,key):
        return next((r for r in self.kits() if r['id']==key),None) or self._missing()

    @staticmethod
    def _missing():raise ValueError('Brand kit tidak ditemukan.')

    def save_kit(self,data):
        name=str(data.get('name','')).strip()
        if not 1<=len(name)<=80:raise ValueError('Nama brand kit harus 1–80 karakter.')
        settings=brand_values(data.get('settings'));key=data.get('id') or 'kit-'+uuid.uuid4().hex[:20]
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT revision FROM brand_kits WHERE id=?',(key,)).fetchone()
            if row and data.get('expected_revision')!=row['revision']:
                db.rollback();raise Conflict(row['revision'],'Brand kit berubah; muat ulang sebelum menyimpan.')
            if not row and data.get('id'):db.rollback();raise ValueError('Brand kit tidak ditemukan.')
            revision=row['revision']+1 if row else 0
            db.execute('INSERT OR REPLACE INTO brand_kits VALUES(?,?,?,?,?)',(key,revision,name,dumps(settings),time.time()));db.commit()
        return self.kit(key)

    def apply_brand(self,doc,operation,clip_id,variant_id):
        kit=self.kit(operation.get('kit_id'))
        if operation.get('kit_revision')!=kit['revision']:raise ValueError('Brand kit berubah; tinjau nilai terbaru.')
        scope=operation.get('scope','variant')
        if scope not in ('variant','project'):raise ValueError('Cakupan brand kit tidak valid.')
        targets=[(clip_id,variant_id)] if scope=='variant' else [(c,v) for c,clip in doc['clips'].items() for v in clip['variants']]
        if scope=='project':doc['settings'].update(kit['settings'])
        touched=set();kept={}
        for c,v in targets:
            variant=self.service.variant(doc,c,v);manual=set(variant.get('override_keys',[]))
            values={k:val for k,val in kit['settings'].items() if k not in manual}
            # Kit-owned keys can be updated again; user's sparse overrides stay authoritative.
            variant['settings'].update(values)
            variant['brand_kit']={'id':kit['id'],'revision':kit['revision'],'name':kit['name'],'applied_keys':sorted(values)}
            kept[c+'|'+v]=sorted(manual&set(kit['settings']))
            if values:touched.add((c,v))
        doc['last_brand_apply']={'kit_id':kit['id'],'protected_keys':kept}
        return touched

    def preference(self):
        with self.store.connect() as db:row=db.execute("SELECT data FROM workspace_preferences WHERE id='default'").fetchone()
        return json.loads(row['data']) if row else {'settings':{},'source':'built_in','revision':0}

    def rows(self,table,pid):
        if table not in ('evaluations6','native_evidence6','feedback6'):raise ValueError('Jenis laporan tidak valid.')
        with self.store.connect() as db:rows=db.execute(f'SELECT data FROM {table} WHERE project_id=? ORDER BY created DESC LIMIT 100',(pid,)).fetchall()
        return [json.loads(r['data']) for r in rows]

    def append(self,table,pid,value):
        if table not in ('evaluations6','native_evidence6','feedback6'):raise ValueError('Jenis laporan tidak valid.')
        self.store.get(pid);value={**copy.deepcopy(value),'id':table+'-'+uuid.uuid4().hex,'created':time.time()}
        with self.store.connect() as db:db.execute(f'INSERT INTO {table} VALUES(?,?,?,?)',(value['id'],pid,dumps(value),value['created']))
        return value

    def evaluation(self,pid,key):
        row=next((r for r in self.rows('evaluations6',pid) if r['id']==key),None)
        if not row:raise ValueError('Hasil perbandingan tidak ditemukan.')
        from .evaluation6 import validate_record
        validate_record(row)
        return row

    def feedback(self,pid,data):
        evaluated=self.evaluation(pid,data.get('evaluation_id'))
        choice=data.get('choice')
        if choice not in ('baseline','candidate','tie'):raise ValueError('Pilih baseline, variasi, atau setara.')
        note=str(data.get('note','')).strip()
        if not 1<=len(note)<=2000:raise ValueError('Tuliskan alasan penilaian; angka SSIM bukan penilaian estetika.')
        metrics={}
        for k in ('manual_corrections','collisions','unique_stories'):
            v=data.get(k)
            if v is not None and (type(v) is not int or not 0<=v<=100000):raise ValueError('Jumlah mutu harus bilangan bulat atau belum diukur.')
            metrics[k]=v
        return self.append('feedback6',pid,{'evaluation_id':evaluated['id'],'choice':choice,'note':note,
            'metrics':metrics,'assessment':'human_reported','candidate_settings':evaluated.get('candidate_settings',{})})

    def promote(self,pid,data):
        feedback=next((r for r in self.rows('feedback6',pid) if r['id']==data.get('feedback_id')),None)
        if not feedback or feedback['choice']!='candidate':raise ValueError('Default baru memerlukan variasi yang dinilai lebih baik pada perbandingan tersimpan.')
        self.evaluation(pid,feedback['evaluation_id'])
        values=brand_values(feedback['candidate_settings'])
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT data FROM workspace_preferences WHERE id='default'").fetchone()
            prior=json.loads(row['data']) if row else {'revision':0}
            if data.get('expected_revision')!=prior['revision']:db.rollback();raise Conflict(prior['revision'],'Preferensi berubah; muat ulang.')
            preference={'revision':prior['revision']+1,'settings':values,'source':'reviewed_variation',
                'feedback_id':feedback['id'],'updated':time.time(),'assessment':'human_reported'}
            db.execute("INSERT OR REPLACE INTO workspace_preferences VALUES('default',?)",(dumps(preference),));db.commit()
        return preference

    def native_matrix(self,pid):
        doc=self.store.get(pid);rows=[];evidence=self.rows('native_evidence6',pid)
        for package in doc.get('exports',[]):
            if package.get('export_mode')=='preserved':continue
            for editor,version in (('capcut','9.5.0'),('resolve','21')):
                match=next((e for e in evidence if e['package_content_id']==package.get('package_content_id') and e['editor']==editor and e['variant_id']==package['variant_id']),None)
                status='not_tested'
                if match:
                    try:
                        if content_id(package['zip'],fresh=True)!=match['package_content_id'] or content_id(match['render_path'],fresh=True)!=match['render_content_id']:
                            status='stale'
                        else:status=match['status']
                    except (OSError,ValueError):status='evidence_missing'
                rows.append({'package_content_id':package.get('package_content_id'),'variant_id':package['variant_id'],
                    'editor':editor,'target_version':version,'status':status,'evidence':match})
        for variant in ('portrait','landscape'):
            for editor,version in (('capcut','9.5.0'),('resolve','21')):
                if not any(r['variant_id']==variant and r['editor']==editor for r in rows):
                    rows.append({'package_content_id':None,'variant_id':variant,'editor':editor,
                        'target_version':version,'status':'not_tested','evidence':None})
        return rows

    def native_evidence(self,pid,data):
        doc=self.store.get(pid);package=next((e for e in doc.get('exports',[]) if e.get('package_content_id')==data.get('package_content_id')),None)
        if not package or package.get('export_mode')=='preserved':raise ValueError('Pilih paket editor yang tersimpan.')
        if content_id(package['zip'],fresh=True)!=package['package_content_id']:raise ValueError('Isi paket berubah; ekspor ulang.')
        if data.get('editor') not in ('capcut','resolve'):raise ValueError('Editor tidak valid.')
        editor_state=package.get('editors',{}).get(data['editor'],{})
        if editor_state.get('construction_status')!='generated' or editor_state.get('structural_status')!='passed':
            raise ValueError('Pembuatan/struktur paket editor ini belum lolos; perbaiki paket dahulu.')
        version=str(data.get('version','')).strip()
        required='9.5.0' if data['editor']=='capcut' else '21'
        if not (version==required or data['editor']=='resolve' and version.startswith('21.')):raise ValueError('Gunakan versi target CapCut 9.5.0 atau Resolve 21.x.')
        flags={k:data.get(k) for k in ('opened','text_edited','saved','rendered','compared')}
        if any(type(v) is not bool for v in flags.values()):raise ValueError('Lengkapi lima langkah bukti impor.')
        from .evaluation6 import media_info
        path=Path(data.get('render_path','')).expanduser().resolve();info=media_info(path)
        target=package.get('reference') or doc['clips'][package['clip_id']]['variants'][package['variant_id']].get('result',{})
        if [info['width'],info['height']]!=[target.get('width'),target.get('height')]:raise ValueError('Rasio/resolusi render editor berbeda dari final rujukan.')
        duration=target.get('length',target.get('duration'))
        if duration is not None and abs(info['duration']-float(duration))>.1:raise ValueError('Durasi render editor berbeda dari final rujukan.')
        note=str(data.get('note','')).strip()
        if not note or len(note)>2000:raise ValueError('Tuliskan hasil pembandingan font, efek dan audio.')
        return self.append('native_evidence6',pid,{**flags,'editor':data['editor'],'version':version,
            'variant_id':package['variant_id'],'package_content_id':package['package_content_id'],
            'render_path':str(path),'render_content_id':content_id(path,fresh=True),'media':info,'note':note,
            'status':'user_reported_passed' if all(flags.values()) else 'user_reported_issue',
            'assessment':'user_reported; media identity and dimensions checked; editor actions not automated'})

    def summary(self,pid):
        doc=self.service.public(pid)
        return {'version':VERSION,'stages':stage_status(doc),'kits':self.kits(),'preference':self.preference(),
            'evaluations':self.rows('evaluations6',pid),'feedback':self.rows('feedback6',pid),'native_matrix':self.native_matrix(pid)}

    def manifest(self,pid):
        doc=self.store.get(pid)
        from .studio_storage import inventory
        files=[e for e in inventory(self.service)['entries'] if e['project_id']==pid]
        return {'schema_version':1,'version':VERSION,'project_id':pid,'revision':doc['revision'],
            'source_content_id':doc['source']['source_id'],'folders':{'work':str(self.service.work/pid),
                'final':str(Path(self.service.base.out_dir)/pid),'database':str(self.store.path)},
            'files':files,'bytes':sum(f['bytes'] for f in files),
            'stages':{k:self.service.dependency(doc,kind=k) for k in ('analyze','correction','discovery','waveform')},
            'variants':[{ 'clip_id':cid,'variant_id':vid,'dependency':self.service.dependency(doc,cid,vid),
                'preview':self.service.export_readiness(doc,cid,vid),'manual_keys':v.get('override_keys',[])}
                for cid,c in doc['clips'].items() for vid,v in c['variants'].items()],
            'protection':'Sumber, final, paket editor, database, model dan aset yang masih dirujuk dilindungi.'}
