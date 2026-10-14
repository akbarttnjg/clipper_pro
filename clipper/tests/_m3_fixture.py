"""Explicitly authored source-time references, not ASR/quality measurements."""
from pathlib import Path
import subprocess
from clipper.config import Config

TEXTS=['Bagaimana menjaga saldo uang usaha?',
    'Pisahkan biaya usaha dari belanja pribadi.',
    'Jadi catat saldo usaha dan simpan bukti transaksi.',
    'Ada tiga langkah untuk memeriksa risiko investasi.',
    'Pertama periksa pengeluaran dan biaya usaha.',
    'Kedua hitung modal yang masih tersedia.',
    'Ketiga sisihkan dana cadangan untuk risiko.',
    'Jadi jangan menganggap keuntungan investasi pasti.']


def reference(texts=TEXTS,step=6.):
    words=[{'word_id':i,'source_word_ids':[i],'word':text,'start':i*step+.2,'end':(i+1)*step-.2,
        'probability':None,'speaker_id':'S1','speaker_provenance':'user_review'} for i,text in enumerate(texts)]
    return {'duration':len(words)*step,'words':words,'raw_words':words,
        'runtime_receipt':{'provider':'authored_test_reference','inference_performed':False}}


def options(**kw):
    return {'provider':'rules','retrieval':'lexical','signals':False,'min_seconds':5.,'max_seconds':30.,
        'grace_seconds':6.,'count':2,**kw}


def config(tmp_path,**kw):
    return Config(work_dir=str(tmp_path),out_dir=str(tmp_path/'clips'),use_nvenc=False,
        visual_enabled=False,segmentation_enabled=False,align_selected_clips=False,**kw)


def wav(path,seconds=48):
    path=Path(path);subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
        '-i','sine=frequency=440:duration='+str(seconds),'-ar','48000',str(path)],check=True,capture_output=True)
    return path
