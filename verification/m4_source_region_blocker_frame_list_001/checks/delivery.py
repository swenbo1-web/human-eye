"""Run the prior installed MCP paired replay against the frame-list repair."""

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys


NS = Path(__file__).resolve().parents[1]
PREVIOUS = NS.parent / 'm4_source_region_blocker_producer_reuse_001'
BASELINE_COMMIT = 'd293fbdd28df2956c17cc902d9b19f6e9d9e3d65'
BASE = PREVIOUS / 'install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS / 'install/PRODUCT_RUN_BINDING.json'


def run(output):
    spec = spec_from_file_location('_frozen_source_region_blocker_delivery', PREVIOUS / 'checks/delivery.py')
    replay = module_from_spec(spec)
    spec.loader.exec_module(replay)
    base, candidate = (json.loads(path.read_bytes()) for path in (BASE, CANDIDATE))
    replay.require(base['preparation_git'] == BASELINE_COMMIT
                   and candidate['historical_preparation_git'] == BASELINE_COMMIT
                   and candidate['historical_source_sha256'] == base['source_sha256']
                   and candidate['changed_product_sources'] == ['human_eye_plugin/live_service.py'],
                   'expected_one_frame_list_only_candidate_from_pinned_baseline')
    replay.BASE, replay.CANDIDATE = BASE, CANDIDATE
    replay.run(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        parser.error('use the pinned interpreter with -I -B')
    run(args.output)
