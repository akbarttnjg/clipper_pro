"""Historical release tests use frozen public sources, never future branch code."""
import hashlib
import json
from pathlib import Path
import zipfile


def restore(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    fixture=Path(__file__).resolve().parents[2]/'docs/releases/m0_fixture.zip'
    if not fixture.is_file():
        from tools.freeze_m0_baseline import export_baseline
        export_baseline(fixture)
    with zipfile.ZipFile(fixture) as z:
        provenance=json.loads(z.read('__provenance__.json'))
        for name,expected in provenance['raw_sha256'].items():
            data=z.read(name)
            if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Frozen baseline checksum mismatch')
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return root
