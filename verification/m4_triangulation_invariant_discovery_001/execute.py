"""Run each registered engineering phase once and retain its outer clocks."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent


def write_new(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('proof', 'legacy', 'correctness', 'observations', 'benchmark'), required=True)
    options = parser.parse_args()
    execution = HERE / 'execution'
    execution.mkdir(exist_ok=True)
    started = time.perf_counter_ns()
    write_new(execution / (options.phase + '_INTENT.json'), {
        'phase': options.phase, 'started_ns': started, 'pid': os.getpid(),
        'source': str(Path(__file__).resolve()), 'status': 'intent',
    })
    result = {'phase': options.phase, 'started_ns': started, 'pid': os.getpid(), 'passed': False}
    try:
        raw = (HERE / 'FROZEN.json').read_bytes()
        frozen = json.loads(raw)
        for path, wanted in frozen['files_sha256'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != wanted:
                raise RuntimeError('frozen_source_or_input_changed:' + path)
        result['source_freeze_sha256'] = hashlib.sha256(raw).hexdigest()
        result['binding_closed_ns'] = time.perf_counter_ns()
        name = '_triangulation_phase_' + options.phase
        source = HERE / ('build_inputs_and_prove.py' if options.phase == 'proof' else 'engineering.py')
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        result['module_loaded_ns'] = time.perf_counter_ns()
        if options.phase == 'proof':
            module.verify_existing()
            result['passed'] = True
        elif options.phase == 'observations':
            quality = json.loads((HERE / 'runs/correctness/RESULTS.json').read_bytes())
            if not quality['passed']:
                raise RuntimeError('correctness_failed_before_observation')
            chains = []
            for scene in ('grid4_permuted_alternating', 'grid16_permuted_alternating'):
                for variant in ('reference', 'candidate'):
                    output = HERE / 'runs' / ('observe_' + scene + '_' + variant)
                    current = module.observe_chain(scene, variant, output, HERE / 'render_budget')
                    summary = current['final_state']
                    accepted = bool(current['passed'] and summary and len(summary['covered_roi_ids']) == 5
                                    and len(summary['unresolved_roi_ids']) == 1
                                    and summary['unresolved_roi_ids'] == ['roi_16a6e8906884476acdedfc96']
                                    and not current['final_pixel_shortfall_roi_ids'])
                    chains.append({'scene': scene, 'variant': variant, 'output': str(output),
                                   'passed': accepted, 'render_attempts': current['actual_chain_render_attempts']})
                    result['chains'] = chains
                    if not accepted:
                        raise RuntimeError('observation_chain_failed:' + scene + ':' + variant)
            result['passed'] = True
        else:
            if options.phase == 'benchmark':
                gate = json.loads((execution / 'observations_RESULT.json').read_bytes())
                if not gate['passed'] or gate['source_freeze_sha256'] != result['source_freeze_sha256']:
                    raise RuntimeError('four_same_source_observation_chains_required')
            entry = {'legacy': module.legacy_baseline, 'correctness': module.correctness,
                     'benchmark': module.benchmark}[options.phase]
            current = entry(HERE / 'runs' / options.phase)
            result['passed'] = current.get('passed', True)
    except BaseException as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    result['closed_before_result_publication_ns'] = time.perf_counter_ns()
    result['elapsed_before_result_publication_ns'] = result['closed_before_result_publication_ns'] - started
    write_new(execution / (options.phase + '_RESULT.json'), result)
    print(json.dumps(result, ensure_ascii=False))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
