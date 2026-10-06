"""python -m clipper.runtime.cli status / install ID / sample ID / calibrate."""
import argparse
import json
from pathlib import Path
import sys
from .state import runtime_root
from .manager import RuntimeManager, redact
from .download import Canceled


def main():
    parser=argparse.ArgumentParser(description='Pengelola komponen Clipper Studio tahap 2')
    parser.add_argument('action',choices=['status','install','probe','sample','calibrate','rollback','worker'])
    parser.add_argument('component',nargs='?');parser.add_argument('--root');parser.add_argument('--repo');parser.add_argument('--job')
    parser.add_argument('--source');parser.add_argument('--model',choices=['small','medium'],default='small');parser.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    args=parser.parse_args();repo=Path(args.repo or Path(__file__).resolve().parents[2]).resolve()
    manager=RuntimeManager(repo,args.root or runtime_root(repo),autostart=False,recover=args.action!='worker')
    if args.action=='status':print(json.dumps(manager.snapshot(),ensure_ascii=False,indent=2));return 0
    if args.action=='worker':
        if not args.job:parser.error('--job wajib')
        job=manager.job(args.job)
    else:
        if args.action!='calibrate' and not args.component:parser.error('ID komponen wajib')
        options={'model':args.model,'device':args.device}
        if args.source:options['source']=args.source
        job=manager.enqueue(args.component,args.action,options)
        claimed=manager.claim()
        if claimed!=job['id']:
            if claimed:manager.update(claimed,status='queued',owner=None)
            print('Proses tersimpan dalam antrean '+job['id']+'. Jalankan aplikasi untuk memprosesnya.');return 0
    from .tasks import execute
    try:
        result=execute(manager,job)
        manager.update(job['id'],status='completed',progress=100,message=result.get('message','Selesai. Periksa lingkup uji di detail.'),result=result)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Canceled as exc:manager.update(job['id'],status='canceled',message=redact(str(exc)));return 2
    except Exception as exc:
        message=redact(str(exc));manager.update(job['id'],status='failed',message=message,error=message)
        print(message,file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
