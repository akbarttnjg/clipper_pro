"""Checked 4.0.9 overlay, including the preceding complete repair payload."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_complete_release import build as complete_build


def build(output,source_commit,verification=None,source_origin='local'):
    return complete_build(output,source_commit,verification,source_origin,version='4.0.9',base_file='typography9_base_hashes.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--source-commit',required=True)
    parser.add_argument('--verification');parser.add_argument('--source-origin',choices=('local','github'),default='local')
    args=parser.parse_args();build(args.output,args.source_commit,args.verification,args.source_origin)
