"""Offline routed-producer interface checks, without scoring model content."""

import copy
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
OLD = Path('D:/he_routed_001/formal')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'OFFLINE_INTERFACE_CHECK.json')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(HERE):
        raise ValueError('new_namespace_output')
    spec = importlib.util.spec_from_file_location('_occluded_transfer_scoring_interface', HERE / 'score_saved.py')
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    paths = [OLD / 'RUN_RESULT.json', OLD / 'LAUNCH_RESULT.json'] + [
        OLD / slot / 'c/CONSUMER.json' for slot in scorer.ORDER]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    run, launch = (json.loads(p.read_bytes()) for p in paths[:2])
    consumers = {slot: json.loads((OLD / slot / 'c/CONSUMER.json').read_bytes()) for slot in scorer.ORDER}
    checks = []
    for slot in scorer.ORDER:
        measured = scorer.terminal_binding(run, launch, slot, consumers[slot])
        checks.append({'name': 'actual_saved_routed_' + slot, 'passed': measured['passed'], 'actual': measured})
    controls = [
        ('missing_record_state', 'slot.execution_state', 'row', 'execution_state', None),
        ('wrong_record_group', 'run.records', 'row', 'group', 'P'),
        ('single_formal_schema', 'run.schema', 'run', 'schema', 'complete-witness-single-formal-v1'),
        ('post_route_error', 'slot.slot_wrapper_errors', 'row', 'slot_wrapper_errors', [{'type': 'control'}]),
        ('consumer_invalid', 'consumer.valid_completion', 'consumer', 'valid_completion', False),
        ('launch_error', 'launch.terminal_errors', 'launch', 'terminal_errors', [{'type': 'control'}]),
        ('extra_retry', 'run.outer_retries', 'run', 'outer_retries', 1),
    ]
    for name, expected, kind, key, value in controls:
        r, l, c = copy.deepcopy(run), copy.deepcopy(launch), copy.deepcopy(consumers['N1'])
        target = {'run': r, 'launch': l, 'consumer': c, 'row': r['records'][0]}[kind]
        target[key] = value
        measured = scorer.terminal_binding(r, l, 'N1', c)
        checks.append({'name': name, 'expected_failed_field': expected,
                       'passed': not measured['passed'] and expected in measured['failed_fields'], 'actual': measured})
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    require = before == after and all(c['passed'] for c in checks)
    output = {'schema': 'occluded-transfer-offline-routed-interface-v1', 'passed': require,
              'checks': checks, 'denominator': len(checks), 'saved_actual_producer_inputs_sha256': before,
              'originals_unchanged': before == after,
              'scorer_sha256': hashlib.sha256((HERE / 'score_saved.py').read_bytes()).hexdigest(),
              'new_product_raster_model_calls': 0, 'full_content_scoring_calls': 0}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': require, 'checks': len(checks)}))
    return 0 if require else 1


if __name__ == '__main__':
    raise SystemExit(main())
