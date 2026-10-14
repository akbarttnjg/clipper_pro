"""Build M0 against the byte-verified 4.0.10 application baseline."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_complete_release import build as complete_build
from freeze_m0_baseline import export_baseline


def build(output,source_commit,verification=None,source_origin='local'):
    # Historical tests select a frozen producer. Do not generate or inspect
    # an unrelated archive in the currently installed M2 working tree.
    fixture=Path(complete_build.__globals__['ROOT'])/'docs/releases/m0_fixture.zip'
    if not fixture.is_file():export_baseline(fixture)
    return complete_build(output,source_commit,verification,source_origin,
                          version='4.0.11',base_file='m0_base_hashes.json')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--source-commit',required=True)
    p.add_argument('--verification');p.add_argument('--source-origin',choices=('local','github'),default='local')
    a=p.parse_args();build(a.output,a.source_commit,a.verification,a.source_origin)
