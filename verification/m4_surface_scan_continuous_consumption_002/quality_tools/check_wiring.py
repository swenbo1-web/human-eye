"""Minimal offline cycle/path/map wiring checks for the unchanged projection."""

import argparse
import importlib.util
from pathlib import Path
import tempfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = HERE.parents[2]
OLD = ROOT / 'verification/m4_surface_scan_continuous_consumption_001/quality_tools'
OLD_CYCLE = b'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-001'
NEW_CYCLE = b'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-002'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_wiring():
    pack = load('_continuous_002_quality_wiring', HERE / 'pack_quality.py')
    checker = load('_continuous_002_quality_binding_checker', HERE / 'check_package.py')
    checks = []

    def check(name, condition):
        checks.append({'check': name, 'passed': bool(condition)})

    reuse = pack.read_json(HERE / 'REUSE.json')
    for row in reuse['files']:
        original = (ROOT / row['source']).read_bytes()
        current = (HERE / row['target']).read_bytes()
        check(row['target'] + ':old_source_bytes', pack.sha(original) == row['source_sha256'])
        check(row['target'] + ':new_source_bytes', pack.sha(current) == row['target_sha256'])
        check(row['target'] + ':only_cycle_adaptation', current == original.replace(OLD_CYCLE, NEW_CYCLE))
    check('current_batch_path', BATCH.name == 'm4_surface_scan_continuous_consumption_002')
    check('packer_current_here_and_root', pack.HERE == HERE and pack.ROOT == ROOT)
    check('checker_imports_current_packer', checker.pack.HERE == HERE and checker.pack.CYCLE == NEW_CYCLE.decode())
    check('new_cycle_bound', pack.CYCLE == NEW_CYCLE.decode())
    check('scoring_contract_cycle_only_change',
          pack.read_json(HERE / 'SCORING_CONTRACT.json')['cycle'] == pack.CYCLE)
    check('error_and_resume_projection_preserved',
          (HERE / 'pack_quality.py').read_bytes().replace(NEW_CYCLE, OLD_CYCLE) == (OLD / 'pack_quality.py').read_bytes())
    plan_raw = (BATCH / 'PLAN.json').read_bytes()
    plan = pack.decode(plan_raw)
    mapping_raw = (BATCH / 'private/ANON_MAP.json').read_bytes()
    mapping = pack.decode(mapping_raw)
    rows = pack.validate_mapping(mapping)
    check('plan_cycle002', plan['cycle'] == pack.CYCLE)
    check('new_runtime_root', Path(plan['runtime_root']).resolve() == (ROOT / '.m4cc2').resolve())
    check('frozen_map_digest', pack.sha(mapping_raw) == plan['anonymous_map_sha256'])
    check('fixed_six_episode_order', tuple(row['cell'] for row in rows) == pack.CELLS)
    check('fixed_three_labels', pack.LABELS == ('BASE', 'REPEAT', 'EDIT'))
    check('plan_map_exact_bindings', len(plan['sequence']) == 6 and all(
        all(frozen[key] == row[key] for key in ('cell', 'group', 'pair', 'anonymous_episode_id', 'anonymous_turn_ids'))
        for frozen, row in zip(plan['sequence'], rows)))
    old_mapping = pack.read_json(OLD.parent / 'private/ANON_MAP.json')
    old_ids = {value for row in old_mapping['rows'] for value in (row['anonymous_episode_id'], *row['anonymous_turn_ids'])}
    new_ids = {value for row in rows for value in (row['anonymous_episode_id'], *row['anonymous_turn_ids'])}
    check('new_anonymous_ids_distinct_from001', not old_ids & new_ids)
    slots = []
    with tempfile.TemporaryDirectory(prefix='_offline_wiring_', dir=HERE) as temporary:
        temporary = Path(temporary).resolve()
        assert temporary.is_relative_to(HERE.resolve())
        for row in sorted(rows, key=lambda value: value['anonymous_episode_id']):
            for index, anon in enumerate(row['anonymous_turn_ids'], 1):
                value = pack.not_run_turn(anon, index, temporary / anon)
                slots.append(value)
                check(anon + ':slot_binding', value['anonymous_turn_id'] == anon and value['turn_index'] == index
                      and value['turn_label'] == pack.LABELS[index - 1])
    check('all_eighteen_not_run_slots_preserved', len(slots) == 18
          and all(row['execution_state'] == 'not_run' and row['valid_completion'] is False for row in slots))
    check('quality_unscored', all(row['content_quality'] == 'unscored' for row in slots))
    return {'schema': 'continuous_002_quality_wiring_check_v1', 'passed': all(row['passed'] for row in checks),
        'check_count': len(checks), 'checks': checks,
        'failed_checks': [row for row in checks if not row['passed']],
        'plan_sha256': pack.sha(plan_raw), 'map_sha256': pack.sha(mapping_raw),
        'projection_scope': 'Existing 001 projection is byte-identical after reversing the cycle literal change.',
        'full_projection_matrix_rerun': False, 'content_scoring': False, 'cost_unsealed': False,
        'model_calls': 0, 'Blender_calls': 0, 'product_calls': 0, 'API_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    result = check_wiring()
    pack = load('_continuous_002_quality_wiring_output', HERE / 'pack_quality.py')
    if args.receipt:
        pack.put(args.receipt, pack.encoded(result))
    print(pack.encoded(result).decode(), end='')
    raise SystemExit(0 if result['passed'] else 1)
