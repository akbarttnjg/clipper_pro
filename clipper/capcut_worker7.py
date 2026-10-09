"""Managed pyCapCut subprocess. No downloads or editor mutations."""
import json
from pathlib import Path
import sys
import traceback


def main():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    try:
        from clipper.projects import capcut_export
        capcut_export(request['items'],Path(request['root']))
        result={'passed':True}
    except Exception as exc:
        traceback.print_exc();result={'passed':False,'error':str(exc)}
    Path(request['response']).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
