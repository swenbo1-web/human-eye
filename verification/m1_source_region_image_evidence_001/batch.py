"""Freeze the completed baseline preflights, qualify once, and seal originals."""

import argparse
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
BUILD = run_path(str(HERE/'build.py'))
BASE = run_path(str(V/'m2_source_region_shared_normalization_live_001/experiment.py'))
read, write, append, pin, require, git = (BASE[k] for k in ('read','write','append','pin','require','git'))
RUN = BUILD['ROOT']
PLAN = '76f952c98ca26a4919e304378d236686bf5042ad:docs/M1_SOURCE_REGION_IMAGE_EVIDENCE_001_PLAN.md'
FROZEN = HERE/'FROZEN.json'
BINDINGS = {'A':BUILD['BASE_BINDING'], 'B':HERE/'install/PRODUCT_RUN_BINDING.json'}
JOURNAL = RUN/'FORMAL_SEQUENCE.jsonl'
SLOTS = {'B':('evidence/B','B',False), 'AS':('standard/A','A',True), 'BS':('standard/B','B',True)}
LIMITS = {'primary_body_bytes':10800, 'Blender':0, 'models':0, 'replacements':0, 'builds':1, 'installs':1}


def freeze(baseline_evidence, baseline_controls, candidate_controls):
    require(not FROZEN.exists() and not JOURNAL.exists(), 'only_one_preregistered_qualification')
    require((HERE/'PLAN.md').read_bytes() == git('show', PLAN), 'fixed_plan_changed')
    replay = run_path(str(HERE/'replay.py'))
    source = replay['inputs']()
    unit = RUN/'preflight/UNIT.json'
    reports = [baseline_evidence.resolve(strict=True), baseline_controls.resolve(strict=True),
               candidate_controls.resolve(strict=True), unit]
    require(all(p.is_relative_to(RUN/'preflight') for p in reports), 'original_baseline_preflight_reports_required')
    pins = {}

    def add(path, expected=None):
        current = pin(path)
        if expected is not None:
            require(all(current[key] == expected[key] for key in ('bytes','sha256')),
                    'pinned_preflight_input_changed/'+current['path'])
        pins[current['path']] = current

    for path in (*replay['source_paths'](), Path(sys.executable), *[p for p in HERE.rglob('*')
                 if p.is_file() and p.suffix in ('.md','.py','.json')]):
        add(path)
    for row in source['source_pins']:
        add(row['path'], row)
    for path, arm in zip(reports, ('BASE','BASE','CANDIDATE','CANDIDATE'), strict=True):
        p = read(path)
        require(p['passed'] is True and (p.get('product_git') or p.get('product_commit')) ==
                BUILD[arm], 'preflight_receipt_not_accepted/'+str(path))
        add(path)
        for row in p.get('source_pins', []):
            add(row['path'], row)
    products = {}
    for label, path in BINDINGS.items():
        installed = read(path)
        expected = BUILD['BASE' if label == 'A' else 'CANDIDATE']
        require(installed['preparation_git'] == expected and len(installed['source_manifest']) == 143,
                'wrong_fixed_install/'+label)
        wheel = Path(installed['wheel_path'])
        require(pin(wheel)['sha256'] == installed['wheel_sha256'], 'wrong_fixed_wheel/'+label)
        add(path)
        add(wheel)
        with ZipFile(wheel) as archive:
            for row in installed['source_manifest']:
                path = Path(installed['install_root'])/row['path']
                require(pin(path)['sha256'] == row['sha256'] and path.read_bytes() == archive.read(row['path']),
                        'install_source_changed/'+row['path'])
                add(path)
        products[label] = {key:installed[key] for key in ('preparation_git','source_sha256','wheel_sha256')}
    write(FROZEN, {'plan':PLAN, 'products':products, 'limits':LIMITS, 'order':list(SLOTS),
                   'baseline_evidence':pin(reports[0]), 'baseline_controls':pin(reports[1]),
                   'candidate_controls':pin(reports[2]), 'unit':pin(unit),
                   'inputs':sorted(pins.values(),key=lambda p:p['path'])})
    print('Frozen', verify_freeze(), len(pins), 'inputs', flush=True)


def verify_freeze():
    group = read(FROZEN)
    require(group['plan'] == PLAN and group['order'] == list(SLOTS) and group['limits'] == LIMITS
            and all(pin(row['path']) == row for row in group['inputs']), 'fixed_group_inputs_changed')
    return pin(FROZEN)['sha256']


def formal():
    digest = verify_freeze()
    JOURNAL.open('x').close()
    all_passed = True
    for label, (folder,arm,standard) in SLOTS.items():
        output = RUN/folder
        require(not output.exists(), 'frozen_slot_is_already_present')
        argv = [sys.executable,'-IB','-X','utf8',str(HERE/'replay.py'),
                '--binding',str(BINDINGS[arm]), '--root',str(output)]
        if standard:
            argv.append('--standard')
        start = time.perf_counter_ns()
        append(JOURNAL, {'event':'start','label':label,'perf_ns':start,'freeze_sha256':digest})
        try:
            process = subprocess.run(argv, cwd=V.parent, capture_output=True, timeout=240)
            stdout, stderr, exit_code = process.stdout, process.stderr, process.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr, exit_code = error.stdout or b'', (error.stderr or b'') + b'\ncontroller deadline\n', None
        end = time.perf_counter_ns()
        output.mkdir(parents=True,exist_ok=True)
        (output/'CONTROLLER_STDOUT.bin').write_bytes(stdout)
        (output/'CONTROLLER_STDERR.bin').write_bytes(stderr)
        summary = output/'SUMMARY.json'
        passed = exit_code == 0 and summary.is_file() and read(summary)['passed'] is True
        append(JOURNAL, {'event':'closed','label':label,'perf_ns':end,'elapsed_ns':end-start,
                         'exit_code':exit_code,'passed':passed,'summary':pin(summary) if summary.is_file() else None})
        print(label, 'passed' if passed else 'failed', flush=True)
        all_passed &= passed
    return 0 if all_passed else 1


def archive():
    verify_freeze()
    seal = BASE['archive']
    seal.__globals__['RUN'] = RUN
    seal()


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_interpreter_required')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('phase', choices=('freeze','formal','archive'))
    cli.add_argument('--baseline-evidence', type=Path)
    cli.add_argument('--baseline-controls', type=Path)
    cli.add_argument('--candidate-controls', type=Path)
    args = cli.parse_args()
    if args.phase == 'freeze':
        freeze(args.baseline_evidence, args.baseline_controls, args.candidate_controls)
    else:
        raise SystemExit(globals()[args.phase]())
