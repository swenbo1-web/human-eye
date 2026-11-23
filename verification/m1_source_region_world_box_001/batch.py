"""Freeze, run and archive the world-box product qualification."""

import argparse
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import zipfile


HERE = Path(__file__).resolve().parent
V = HERE.parent
BASE = run_path(str(V/'m2_source_region_shared_normalization_live_001/experiment.py'))
require, read, write, pin, git = (BASE[key] for key in ('require', 'read', 'write', 'pin', 'git'))
BUILD = run_path(str(HERE/'build.py'))
RUN = BUILD['ROOT']
BINDINGS = {'A': BUILD['BASE_BINDING'], 'B': HERE/'install/PRODUCT_RUN_BINDING.json'}
PLAN = 'b96a4457ca9ec9ed6571c4718527faf9efbb10fd:docs/M1_SOURCE_REGION_WORLD_BOX_001_PLAN.md'
FROZEN = HERE/'FROZEN.json'
REPLAY = HERE/'replay.py'
CONTROLS = RUN/'controls_final/RESULT.json'
AUTHENTIC = RUN/'preflight/BILATERAL_INPUTS.json'


def collect(pins, path, expected=None):
    row = pin(path)
    if expected is not None:
        require(all(row[key] == expected[key] for key in ('bytes', 'sha256')), 'frozen_input_changed/' + str(path))
    pins[row['path']] = row


def freeze():
    require(not (RUN/'arms').exists() and not (RUN/'FORMAL_SEQUENCE.jsonl').exists(), 'one_freeze_before_formal_replay')
    require((HERE/'PLAN.md').read_bytes() == git('show', PLAN), 'planning_source_changed')
    replay = run_path(str(REPLAY))
    require(pin(sys.executable)['sha256'] == replay['PYTHON_SHA'], 'fixed_interpreter_changed')
    fixture = replay['sealed_inputs']()
    pins = {}
    for path in (*replay['source_paths'](), sys.executable, *[p for p in HERE.rglob('*')
                 if p.is_file() and p.suffix in ('.py','.md','.json')]):
        collect(pins, path)
    collect(pins, RUN/'preflight/ENTRY_FIRST_FAILURE.json')
    for row in fixture['source_pins']:
        collect(pins, row['path'], row)
    preflights = [AUTHENTIC, CONTROLS, *(RUN/'preflight'/arm/'SUMMARY.json'
                                       for arm in ('base_ordinary_v2','world_box_v2'))]
    for receipt in preflights:
        proof = read(receipt)
        require(proof['passed'] is True, 'qualification_receipt_failed/' + receipt.name)
        collect(pins, receipt)
        for row in proof.get('source_pins', []):
            collect(pins, row['path'], row)
    require({arm: len(rows) for arm, rows in read(CONTROLS)['cases'].items()} == {'A': 4, 'B': 44},
            'world_box_boundary_matrix_incomplete')
    products, units = {}, {}
    for label, name in BINDINGS.items():
        binding = read(name)
        expected = BUILD[{'A': 'BASE', 'B': 'CANDIDATE'}[label]]
        require(binding['preparation_git'] == expected and len(binding['source_manifest']) == 143, 'installed_arm_changed')
        wheel = Path(binding['wheel_path'])
        require(pin(wheel)['sha256'] == binding['wheel_sha256'], 'frozen_wheel_changed')
        collect(pins, wheel)
        collect(pins, name)
        with zipfile.ZipFile(wheel) as packaged:
            for item in binding['source_manifest']:
                path = Path(binding['install_root'])/item['path']
                require(pin(path)['sha256'] == item['sha256'] and path.read_bytes() == packaged.read(item['path']),
                        'frozen_installed_source_changed/' + item['path'])
                collect(pins, path)
        products[label] = {key: binding[key] for key in ('preparation_git','source_sha256','wheel_sha256')}
        unit = RUN/'preflight'/f'UNIT_{label}.json'
        units[label] = read(unit)
        collect(pins, unit)
    require((units['A']['tested'],units['A']['failures'],units['A']['errors']) == (50, [], []) and
            (units['B']['tested'],units['B']['failures'],units['B']['errors']) == (50, [], []),
            'existing_coverage_regressed')
    write(FROZEN, {'plan': PLAN, 'products': products, 'order': list(replay['ORDER']), 'max_selection_ns': 50_000_000,
          'actual_new_models': 0, 'actual_new_Blender': 0, 'inputs': sorted(pins.values(), key=lambda r:r['path'])})
    print('Frozen', verify_freeze(), len(pins), 'inputs', flush=True)


def verify_freeze():
    spec = read(FROZEN)
    require(spec['plan'] == PLAN and spec['max_selection_ns'] == 50_000_000 and
            all(pin(row['path']) == row for row in spec['inputs']), 'formal_frozen_inputs_changed')
    return pin(FROZEN)['sha256']


def formal():
    verify_freeze()
    require(not (RUN/'FORMAL_SEQUENCE.jsonl').exists() and not (RUN/'arms').exists(), 'no_formal_slot_replacements')
    done = subprocess.run([sys.executable, '-IB', '-X', 'utf8', str(REPLAY), '--baseline', str(BINDINGS['A']),
                           '--candidate', str(BINDINGS['B'])], cwd=HERE.parents[1])
    return done.returncode


def archive():
    verify_freeze()
    seal = BASE['archive']
    seal.__globals__['RUN'] = RUN
    seal()


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_runtime_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('freeze', 'formal', 'archive'))
    raise SystemExit(globals()[parser.parse_args().phase]())
