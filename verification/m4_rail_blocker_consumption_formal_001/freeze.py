"""Freeze the formal continuation, with the original rail setup and zero new qualification."""

import ast
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
OLD = NS.parent / 'm4_rail_blocker_consumption_001'
sys.path[:0] = [str(NS / 'harness'), str(NS / 'qualification')]
from admission import SCHEMA, verify_freeze
from budget import LIMITS
from common import ASSET, ASSET_SHA256, BINDINGS, EXTERNAL, ORDER, PRODUCTS, ROOT, TRUTH, read, save, sha
from derive import verify_sealed


BASE = '69c48d35f581b72ef8762ccf5cdae545adaaf882'
PLAN_GIT = 'daf3cbe8016263cff75e2e767dfdff816636fc6e'
PLAN = 'docs/M4_RAIL_BLOCKER_CONSUMPTION_FORMAL_001_PLAN.md'
ORIGINAL_FREEZE = '2162f98f38568f9510db6db6aa11e8cb720556e9915fbe93d30f83d4272d2fce'
REQUIRED_ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')


def freeze():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or EXTERNAL.exists() or (NS / 'FROZEN.json').exists():
        raise ValueError('fresh_formal_run_directory_and_isolated_interpreter_required')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() != BASE:
        raise ValueError('original_rail_evidence_commit_must_be_the_base')
    if tuple(ORDER) != REQUIRED_ORDER:
        raise ValueError('fixed_six_formal_routes_changed')
    old_freeze = OLD / 'FROZEN.json'
    if sha(old_freeze) != ORIGINAL_FREEZE:
        raise ValueError('original_frozen_registration_changed')

    pins = {}

    def accept(path, expected_sha=None, size=None):
        path = Path(path).resolve()
        if path not in pins:
            pins[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        row = pins[path]
        if ((expected_sha is not None and row['sha256'] != expected_sha) or
                (size is not None and row['bytes'] != size) or path.suffix == '.pyc'):
            raise ValueError('registered_dependency_changed/' + str(path))

    def bind(rows):
        for row in rows:
            accept(row['path'], row['sha256'], row.get('bytes'))

    prior = read(old_freeze)
    if prior['products'] != PRODUCTS or prior['asset_sha256'] != ASSET_SHA256:
        raise ValueError('original_model_trial_inputs_changed')
    bind(prior['direct_inputs'])
    accept(old_freeze, ORIGINAL_FREEZE)
    accept(ASSET, ASSET_SHA256)
    accept(TRUTH, prior['truth_sha256'])
    for binding in BINDINGS.values():
        accept(binding)
    original_manifest = OLD / 'CONTENT_MANIFEST.json'
    accept(original_manifest)
    for item in read(original_manifest)['files']:
        accept(OLD / item['path'], item['sha256'], item['bytes'])
    for path in (OLD / 'inputs/PROMPT_COMMON.txt', OLD / 'inputs/REQUEST.json', OLD / 'scoring/RUBRIC.md'):
        accept(path)
    actual_plan = subprocess.check_output(['git', 'show', PLAN_GIT + ':' + PLAN], cwd=ROOT)
    plan = NS / 'PLAN.md'
    if plan.read_bytes() != actual_plan:
        raise ValueError('registered_formal_plan_bytes_changed')
    accept(plan)

    derived = NS / 'qualification/DERIVED.json'
    verify_sealed()
    gate = read(derived)
    bind(gate.get('source_pins', []))
    qualification_preflight = read(derived.parent / 'PREFLIGHT.json')
    dispatch_preflight = read(NS / 'harness/DISPATCH_PREFLIGHT.json')
    if (qualification_preflight['passed'] is not True or dispatch_preflight['passed'] is not True or
            any(dispatch_preflight[key] != 0 for key in ('actual_Blender_processes', 'actual_model_runs', 'actual_raster_attempts'))):
        raise ValueError('registered_zero_launch_preflight_required')
    bind(qualification_preflight.get('source_pins', []))
    bind(dispatch_preflight.get('source_pins', []))
    scoring_preflight = read(NS / 'scoring/PREFLIGHT.json')
    if scoring_preflight['passed'] is not True:
        raise ValueError('formal_scoring_preflight_failed')
    bind(scoring_preflight.get('source_pins', []))

    proof = read(OLD / 'harness/DISPATCH_PREFLIGHT.json')['cli_proof']
    if Path(proof['Python_path']).resolve() != Path(sys.executable).resolve():
        raise ValueError('fixed_isolated_CLI_host_interpreter_required')
    accept(proof['CLI_path'], proof['CLI_sha256'])
    accept(proof['Python_path'], proof['Python_sha256'])
    login = subprocess.run([proof['CLI_path'], 'login', 'status'], capture_output=True, check=True, timeout=15)
    if b'Logged in using ChatGPT' not in login.stdout + login.stderr:
        raise ValueError('current_fixed_CLI_ChatGPT_login_required')

    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            accept(path)

    output = NS / 'FROZEN.json'
    save(output, {'schema': SCHEMA, 'slots': list(ORDER), 'products': PRODUCTS, 'ledger_limits': LIMITS,
                  'plan_commit': PLAN_GIT, 'plan_sha256': sha(plan), 'original_qualification_freeze_sha256': ORIGINAL_FREEZE,
                  'derived_qualification_sha256': sha(derived), 'asset_sha256': ASSET_SHA256,
                  'truth_sha256': prior['truth_sha256'], 'started_ns': started, 'completed_ns': time.perf_counter_ns(),
                  'task_s': 450, 'owned_s': 600, 'product_diff_files': 0, 'new_qualifications': 0,
                  'request_model': prior['request_model'], 'performance_gate': prior['performance_gate'],
                  'direct_inputs': [pins[p] for p in sorted(pins)]})
    print('Froze formal trial, reused sealed QA/QB originals and preserved old failed gate.', len(pins),
          verify_freeze(output), flush=True)


if __name__ == '__main__':
    freeze()
