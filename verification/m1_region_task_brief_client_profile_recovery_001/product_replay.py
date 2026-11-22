"""Bind the unchanged archived-product worker to the fixed recovery workspace."""

import argparse
from pathlib import Path
from runpy import run_path
import sys
from types import FunctionType

sys.path.insert(0,str(Path(__file__).resolve().parent/'harness'))
from common import EXTERNAL, PREVIOUS, PREVIOUS_RUN

retained = run_path(str(PREVIOUS/'product_replay.py'))
requests = retained['requests']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',nargs=2,metavar=('ROOT','SLOT'),required=True)
    args=parser.parse_args()
    target,slot=args.worker
    root=Path(target).resolve()
    allowed=EXTERNAL.resolve()
    old=retained['worker']
    if (old.__globals__['WORKSPACE']!=PREVIOUS_RUN or root==allowed or not root.is_relative_to(allowed)
            or not sys.flags.isolated or not sys.dont_write_bytecode):
        raise ValueError('fixed_recovery_product_workspace_required')
    worker=FunctionType(old.__code__,dict(old.__globals__,WORKSPACE=allowed))
    worker(root,slot,30)
