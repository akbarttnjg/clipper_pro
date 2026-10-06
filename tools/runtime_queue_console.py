"""Small local fallback for the original 4.0.2 panel; Python stdlib only."""
import json
from pathlib import Path
import urllib.error
import urllib.request

BASE='http://127.0.0.1:8765/api/studio/runtime'


def request(path='',body=None):
    payload=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(BASE+path,data=payload,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:
        return json.loads(response.read().decode('utf-8'))


def list_jobs():
    data=request();rank={'running':0,'cancel_requested':0,'failed':1,'interrupted':1,'queued':2}
    rows=sorted(data['jobs'],key=lambda j:(rank.get(j['status'],3),-j['created']))
    print('\nDAFTAR PROSES (proses aktif lebih dahulu)')
    for index,job in enumerate(rows,1):
        options=job.get('options') or {}
        print(f"{index:2}. {job['component']} | {job['status']} | {job.get('progress',0):.1f}% | {options.get('model','')} {options.get('device','')}")
        print('    '+(job.get('message') or ''))
    return rows


def select_job(rows):
    answer=input('\nNomor proses (0 untuk kembali): ').strip()
    if answer=='0':return None
    if not answer.isdigit() or not 1<=int(answer)<=len(rows):raise ValueError('Nomor proses tidak tersedia.')
    return rows[int(answer)-1]


def main():
    print('KONTROL ANTREAN CLIPPER\nBiarkan mesin berjalan. Tidak ada unduhan/model baru yang dipasang oleh alat ini.')
    while True:
        try:
            print('\n1. Lihat semua proses\n2. Baca dan simpan log satu proses\n3. Batalkan satu proses\n0. Tutup')
            choice=input('Pilihan: ').strip()
            if choice=='0':return
            if choice not in ('1','2','3'):continue
            rows=list_jobs()
            if choice=='1':continue
            job=select_job(rows)
            if not job:continue
            if choice=='2':
                text=request('/jobs/'+job['id']+'/log')['text'];print('\n'+text)
                folder=Path(__file__).resolve().parent/'log_komponen';folder.mkdir(exist_ok=True)
                target=folder/(job['id']+'.log');target.write_text(text,encoding='utf-8')
                print('\nLog disimpan: '+str(target))
            else:
                if job['status'] not in ('queued','running','cancel_requested'):
                    print('Proses ini sudah berhenti; tidak perlu dibatalkan.');continue
                result=request('/jobs/'+job['id']+'/cancel',{})
                print('Status: '+result['status']+'. Unduhan parsial tetap disimpan.')
        except urllib.error.HTTPError as exc:
            print('Permintaan gagal: '+exc.read().decode('utf-8',errors='replace'))
        except urllib.error.URLError:
            print('Mesin belum dapat dihubungi. Jalankan JALANKAN_PRO.cmd dan pastikan http://localhost:8765 terbuka.')
        except (OSError,ValueError,KeyError) as exc:print(str(exc))


if __name__=='__main__':
    try:main()
    except (EOFError,KeyboardInterrupt):print('\nKontrol antrean ditutup.')
