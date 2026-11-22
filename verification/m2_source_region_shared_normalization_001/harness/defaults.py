"""Run unchanged default observation callers through the same held server."""

import argparse
from pathlib import Path
from runpy import run_path
import sys


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('fixed_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--preflight',action='store_true')
    mode.add_argument('--review-preflight',action='store_true')
    args = parser.parse_args()
    replay = run_path(str(Path(__file__).with_name('replay.py')))
    output,binding_path = args.output.resolve(),args.binding.resolve(strict=True)
    if not args.review_preflight:
        replay['run'](output,binding_path,'defaults',False,args.preflight)
        return
    require,read = replay['require'],replay['read']
    require(output==(replay['RUN']/'preflight/defaults').resolve(strict=True),
            'receipt_review_only_for_already_closed_baseline_default_slot')
    binding = read(binding_path)
    require(binding['preparation_git']==replay['BASE_GIT'],'receipt_review_requires_fixed_baseline')
    fixture = replay['sealed_inputs']('defaults')
    folders = [output/'mcp'/f'rpc_{n+4:02d}' for n in range(len(fixture['calls']))]
    replies = [read(folder/'RX.bin') for folder in folders]
    receipts = [read(folder/'RECEIPT.json') for folder in folders]
    for reply in replies:
        require(reply['result']['isError'] is False,'archived_default_response_was_error')
    closure = read(output/'mcp/HELD_CLOSE.json')
    start = read(output/'mcp/START.json')['started_ns']
    replay['verify_replay'](output,binding,fixture,False,True,closure,replies,receipts,start,
                            receipts[-1]['closed_ns'],closure['closed_ns'],replayed_receipts=True)


if __name__=='__main__':
    main()
