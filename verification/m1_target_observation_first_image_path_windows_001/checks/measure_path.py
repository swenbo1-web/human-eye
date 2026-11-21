"""Repeat the original 60-pair cost measurement for the Windows candidate."""

import argparse
import json
from pathlib import Path
import runpy


NS = Path(__file__).resolve().parents[1]
PROBE = NS.parent / 'm1_target_observation_first_image_path_001/checks/path_cost.py'


def collect(output):
    previous = runpy.run_path(str(PROBE))
    measure = previous['measure']
    measure.__globals__['NS'] = NS
    result = measure()
    result['schema'] = 'm1-target-observation-first-image-path-windows-cost-v1'
    result['reused_timing_harness'] = previous['pin'](PROBE)
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=NS / 'checks/PATH_COST.json')
    collect(parser.parse_args().output)
