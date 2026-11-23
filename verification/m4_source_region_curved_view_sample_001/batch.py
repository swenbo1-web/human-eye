"""Lock the installed sparse-view experiment and seal its original receipts."""

import argparse
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import zipfile


HERE = Path(__file__).resolve().parent
V = HERE.parent
BASE = run_path(str(V/'m2_source_region_shared_normalization_live_001/experiment.py'))
require, read, write, pin, git = (BASE[name] for name in ('require', 'read', 'write', 'pin', 'git'))
BUILD = run_path(str(HERE/'build.py'))
RUN = BUILD['ROOT']
BINDINGS = {'A': BUILD['BASE_BINDING'], 'B': HERE/'install/PRODUCT_RUN_BINDING.json'}
PLAN = 'fcce15db5dfba851babdef6c321bc696ce6da992:docs/M4_SOURCE_REGION_CURVED_VIEW_SAMPLE_001_PLAN.md'
FROZEN = HERE/'FROZEN.json'
REPLAY = HERE/'replay.py'
LIMITS = {'left_median_selection_ns': 80_000_000, 'positive_selection_ns': 25_000_000,
          'live_Blender': 0, 'models': 0, 'replacement_slots': 0}


def freeze(proof, dry_name):
    require(not (RUN/'arms').exists() and not (RUN/'FORMAL_SEQUENCE.jsonl').exists(), 'one_freeze_before_formal_replay')
    require((HERE/'PLAN.md').read_bytes() == git('show', PLAN), 'fixed_plan_changed')
    dry = RUN/'preflight'/dry_name
    require(dry.is_relative_to(RUN/'preflight') and proof.resolve(strict=True).is_relative_to(RUN),
            'fixed_qualification_receipts_required')
    replay = run_path(str(REPLAY))
    require(pin(sys.executable)['sha256'] == replay['OLD']['PYTHON_SHA'], 'fixed_interpreter_changed')
    inputs = replay['sealed_inputs'](controls=True)
    pins = {}

    def add(path, reference=None):
        row = pin(path)
        if reference is not None:
            require(all(row[k] == reference[k] for k in ('bytes', 'sha256')), 'preflight_source_changed/' + row['path'])
        pins[row['path']] = row

    paths = (*replay['source_paths'](), sys.executable, *[p for p in HERE.rglob('*')
             if p.is_file() and p.suffix in ('.md','.py','.json')])
    for path in paths:
        add(path)
    for row in inputs['source_pins']:
        add(row['path'], row)
    dry_folders = ('base_main','base_compatibility','product_main','product_compatibility')
    add(RUN/'preflight/UNIT.json')
    attachment = read(proof)
    require(attachment['status'] == 'passed' and attachment['case_count'] == 24
            and attachment['product_commit'] == BUILD['CANDIDATE']
            and attachment['product_binding_sha256'] == pin(BINDINGS['B'])['sha256']
            and attachment['npz_serializer_read_count'] == attachment['blender_count'] == attachment['model_count'] == 0,
            'installed_attachment_qualification_failed')
    add(proof)
    reports = [RUN/'preflight/SPARSE_CONTROLS.json', RUN/'preflight/UNIT_WITH_OLD_FIXTURE.json',
               *(dry/name/'SUMMARY.json' for name in dry_folders)]
    for path in reports:
        receipt = read(path)
        require(receipt['passed'] is True, 'required_preflight_failed/' + str(path))
        add(path)
        for row in receipt.get('source_pins', []):
            add(row['path'], row)
    products = {}
    for label, path in BINDINGS.items():
        install = read(path)
        expected = BUILD[{'A': 'BASE','B': 'CANDIDATE'}[label]]
        require(install['preparation_git'] == expected and len(install['source_manifest']) == 143,
                'fixed_install_binding_changed')
        wheel = Path(install['wheel_path'])
        require(pin(wheel)['sha256'] == install['wheel_sha256'], 'wheel_changed')
        add(wheel)
        add(path)
        with zipfile.ZipFile(wheel) as w:
            for row in install['source_manifest']:
                source = Path(install['install_root'])/row['path']
                require(pin(source)['sha256'] == row['sha256'] and source.read_bytes() == w.read(row['path']),
                        'installed_runtime_source_changed/' + row['path'])
                add(source)
        products[label] = {key:install[key] for key in ('preparation_git','source_sha256','wheel_sha256')}
    write(FROZEN, {'plan': PLAN, 'products': products, 'order': list(replay['ORDER']), 'limits': LIMITS,
                   'inputs': sorted(pins.values(), key=lambda row:row['path'])})
    print('Frozen', verify_freeze(), len(pins), 'inputs', flush=True)


def verify_freeze():
    f = read(FROZEN)
    require(f['plan'] == PLAN and f['limits'] == LIMITS and all(pin(row['path']) == row for row in f['inputs']),
            'frozen_execution_inputs_changed')
    return pin(FROZEN)['sha256']


def formal():
    verify_freeze()
    require(not (RUN/'arms').exists() and not (RUN/'FORMAL_SEQUENCE.jsonl').exists(), 'no_formal_slot_replacements')
    args = [sys.executable,'-IB','-X','utf8',str(REPLAY),'--baseline',str(BINDINGS['A']),
            '--candidate',str(BINDINGS['B'])]
    return subprocess.run(args, cwd=HERE.parents[1]).returncode


def archive():
    verify_freeze()
    seal = BASE['archive']
    seal.__globals__['RUN'] = RUN
    seal()


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_runtime_required')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('phase', choices=('freeze','formal','archive'))
    cli.add_argument('--attachment-proof', type=Path)
    cli.add_argument('--dry-name', default='installed')
    a = cli.parse_args()
    if a.phase == 'freeze':
        require(a.attachment_proof is not None and Path(a.dry_name).name == a.dry_name,
                'actual_attachment_and_startup_preflight_required')
        freeze(a.attachment_proof, a.dry_name)
    else:
        raise SystemExit(globals()[a.phase]())
