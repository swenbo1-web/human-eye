"""Read-only diagnosis of the formal startup import boundary."""

import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NS = ROOT / 'verification/m4_dense_sweep_integrated_native_pilot_recovery_001'
RUN = Path(__file__).resolve().parents[1]
FORMAL = RUN / 'slots/N1'
OUTPUT = Path(__file__).with_suffix('.json')


class OfflineBoundaryReached(Exception):
    """The real startup imported its runtime without constructing it."""


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    path = path.resolve(strict=True)
    data = path.read_bytes()
    return {'path': path.as_posix(), 'bytes': len(data), 'sha256': sha256(data).hexdigest()}


def mark_imports(mode):
    entry = run_path(str(NS / 'harness/run_slot.py'))
    run, admission = entry['run'], entry['admission']
    original = run.__globals__['validate_admission']
    require(original is admission.validate_admission, 'exact_admission_callable_required')
    source = Path(run.__code__.co_filename)
    definition = next(node for node in ast.parse(source.read_bytes()).body
                      if isinstance(node, ast.FunctionDef) and node.name == 'run')
    at_runtime_construction, = (
        node.lineno for node in ast.walk(definition) if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
        and node.value.func.id == 'Runtime'
    )
    checkpoints = {}

    def admitted(label, path):
        before = sys.path[:]
        checkpoints['before_admission'] = before
        try:
            receipt = original(label, path)
            checkpoints['after_actual_admission'] = sys.path[:]
            return receipt
        finally:
            if mode == 'restore':
                sys.path[:] = before
            checkpoints['before_return_to_runtime'] = sys.path[:]

    def trace(frame, event, arg):
        if frame.f_code is not run.__code__:
            return None
        if event == 'line' and frame.f_lineno == at_runtime_construction:
            require(all(name in sys.modules for name in ('runtime', 'budget', 'bridge')), 'required_runtime_imports_missing')
            checkpoints['at_runtime_construction'] = {
                name: pin(Path(sys.modules[name].__file__)) for name in ('runtime','budget','bridge')
            }
            require(hasattr(sys.modules['budget'], 'Budget'), 'actual_runtime_budget_class_missing')
            raise OfflineBoundaryReached('offline_stop_before_runtime_construction')
        return trace

    popen = subprocess.Popen

    def show_git_only(command, *args, **kwargs):
        require(isinstance(command, list) and command[:2] == ['git', 'show'],
                'offline_control_forbids_runtime_process_start')
        return popen(command,*args,**kwargs)

    require('budget' not in sys.modules and 'runtime' not in sys.modules, 'fresh_budget_import_required')
    # Redirect only formal output and admission's slot-order observation to a
    # fresh temporary namespace. Actual freeze, derived proof and old evidence
    # paths remain as captured by the original admission module.
    with TemporaryDirectory(prefix='m4-runtime-import-') as directory:
        scratch = Path(directory)
        with patch.object(admission, 'EXTERNAL', scratch), patch.dict(run.__globals__, {
            'EXTERNAL': scratch, 'validate_admission': admitted,
        }), patch.object(subprocess, 'Popen', show_git_only):
            sys.settrace(trace)
            try:
                ret = run('N1')
            finally:
                sys.settrace(None)
        slot = scratch / 'slots/N1'
        receipt = read(slot / 'SLOT_RESULT.json')
        publication = read(slot / 'SLOT_PUBLICATION.json')
        require(set(p.name for p in slot.iterdir()) == {'SLOT_STARTED.json','SLOT_RESULT.json','SLOT_PUBLICATION.json'},
                'unexpected_offline_slot_side_effect')
    require(ret == 1 and receipt['paid_API_calls'] == receipt['model_consumers'] == 0
            and receipt['actual_model_admitted'] is False and 'budget' not in receipt
            and publication['status'] == 'failed', 'offline_stop_not_confirmed')
    imported_budget = pin(Path(sys.modules['budget'].__file__))
    failure, = receipt['errors']
    real_failure, = read(FORMAL / 'SLOT_RESULT.json')['errors']
    require(failure['stage'] == 'runtime_start' and 'after_actual_admission' in checkpoints,
            'did_not_reach_actual_post_admission_runtime')
    leaked = str(NS / 'qualification')
    require(leaked not in checkpoints['before_admission']
            and leaked in checkpoints['after_actual_admission'], 'qualifier_path_shadow_not_observed')
    if mode == 'original':
        require(failure['type'] == real_failure['type'] == 'ImportError'
                and failure['message'] == real_failure['message']
                and imported_budget['path'] == (NS / 'qualification/budget.py').as_posix()
                and 'at_runtime_construction' not in checkpoints,
                'original_production_failure_not_reproduced')
    else:
        require(failure['type'] == 'OfflineBoundaryReached'
                and failure['message'] == 'offline_stop_before_runtime_construction'
                and imported_budget['path'] == (NS / 'harness/budget.py').as_posix()
                and checkpoints['before_return_to_runtime'] == checkpoints['before_admission'],
                'fixed_path_control_did_not_reach_construction_boundary')
    return {
        'mode': mode, 'actual_retained_run_source': pin(source), 'runtime_construction_line': at_runtime_construction,
        'same_frozen_admission_reached': True, 'freeze_sha256': receipt['freeze_sha256'],
        'failure': {key: failure[key] for key in ('stage','type','message')},
        'imported_budget': imported_budget, 'checkpoints': checkpoints,
        'Blender_starts': 0, 'model_starts': 0,
    }


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_isolated_python_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('original','restore'))
    args = parser.parse_args()
    if args.mode:
        result = mark_imports(args.mode)
        print(json.dumps(result, ensure_ascii=False, separators=(',',':')))
        return
    cases = {}
    for mode in ('original','restore'):
        call = subprocess.run([sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()), '--mode', mode],
                              cwd=ROOT, capture_output=True, timeout=45, check=True)
        lines = call.stdout.splitlines()
        cases[mode] = {'stdout_sha256': sha256(call.stdout).hexdigest(), 'stdout_bytes': len(call.stdout),
                       'stderr_sha256': sha256(call.stderr).hexdigest(), 'stderr_bytes': len(call.stderr),
                       'result': json.loads(lines[-1])}
    originals = [FORMAL / 'SLOT_RESULT.json', FORMAL / 'SLOT_PUBLICATION.json',
                 RUN / 'preflight/SEQUENCE.jsonl', NS / 'FROZEN.json',
                 RUN / 'preflight/DERIVED_ADMISSION.json', NS / 'harness/run_slot.py',
                 NS / 'harness/admission.py', NS / 'qualification/recovery.py']
    receipt = {'schema': 'm4-formal-runtime-import-isolation-v1', 'passed': True,
               'scope': 'Post-close original and fixed-path controls. Fresh temporary namespace; native constructor forbidden.',
               'actual_formal_outcome_unchanged': {'N1':'failed', 'P1':'unrun'},
               'new_Blender_starts': 0, 'new_model_starts': 0, 'controls': cases,
               'source_pins': [pin(path) for path in [Path(__file__), *originals]]}
    require(not (RUN / 'slots/P1').exists(), 'actual_P1_must_remain_unrun')
    with OUTPUT.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(OUTPUT.as_posix(), pin(OUTPUT)['sha256'])


if __name__ == '__main__':
    main()
