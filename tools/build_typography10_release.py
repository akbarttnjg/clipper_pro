"""4.0.10 installer overlay against the recovered, verified 4.0.9 main tree."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_complete_release import build as complete_build


def build(output,source_commit,verification=None,source_origin='local'):
    return complete_build(output,source_commit,verification,source_origin,
                          version='4.0.10',base_file='typography10_base_hashes.json')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--source-commit',required=True)
    p.add_argument('--verification');p.add_argument('--source-origin',choices=('local','github'),default='local')
    a=p.parse_args();build(a.output,a.source_commit,a.verification,a.source_origin)
