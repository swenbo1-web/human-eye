"""Reproduce the old assembly score with only the approved public-event reader substituted."""

import argparse
import json
from pathlib import Path
from runpy import run_path
import sys
from types import SimpleNamespace

from inputs import ASSETS, RUN, pin, require
from score import verify_public_final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot',type=Path,required=True)
    parser.add_argument('--claims',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a = parser.parse_args()
    slot,claims,output = (p.resolve() for p in (a.slot,a.claims,a.output))
    assembly = ASSETS['assembly']['root'].resolve(strict=True)
    require(sys.flags.isolated and sys.dont_write_bytecode and slot.name in ('N1','P1')
            and slot == assembly/'slots'/slot.name and claims == assembly/'score'/f'{slot.name}_CLAIMS.json'
            and output.is_relative_to(RUN.resolve()) and not output.exists(), 'only_the_original_assembly_baseline_can_run')
    source = ASSETS['assembly']['evidence']/'score.py'
    old = run_path(str(source))
    inherited = old['OLD']
    approved = SimpleNamespace(**{**vars(inherited),'verify_public_final':verify_public_final})
    legacy = inherited.with_replacements(old['score_slot'],OLD=approved)
    score, failure = None, None
    try:
        score = legacy(slot,claims)
    except AttributeError as error:
        failure = {'type':type(error).__name__,'message':str(error)}
    status = int(score is None or score['quality_complete'] is not True)
    with output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump({'slot':slot.name,'original_entry':pin(source),
                   'adaptation':'approved public event reader only',
                   'reader':pin(Path(verify_public_final.__code__.co_filename)),
                   'confirmed_original_baseline_exit':status,'score':score,'exception':failure},
                  stream,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
