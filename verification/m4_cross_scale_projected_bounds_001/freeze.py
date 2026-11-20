"""Freeze the direct isolated candidate, exact requests and six Blender slots."""

import ast
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import SCHEMA, registered_products, verify_freeze
from budget import LIMITS
from common import BINDINGS, EXTERNAL, FORMAL, ORDER, PIXEL, ROOT, asset_identity, read, save, sha


BASE = '58920560404544bfc973463761bcd2db55acc5ff'
PLAN = '64c63dc683f10bb09a212c65dffcbfae36a9b9a5e1e3d90a3b46a4e580c4e378'
PIXEL_FREEZE = '16fb39a0c242333c88dc8343a3a78eb5ef66255b62d7c6af0c2376697a09f684'
PIXEL_MANIFEST = 'd8a4dd30690b2e58b9c940891f7db61d097b44cd9d4103032957a3a7ea401b92'
ASSET = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
PRODUCT_FILE = 'human_eye_plugin/active_observation.py'
PERFORMANCE_GATE = {'median_paired_cold_global_index_reduction_percent_min': 20,
                    'cold_rpc_improving_pairs_min': 2,
                    'median_paired_cold_server_rpc_change_ms_exclusive_max': 0}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().split()


def freeze():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or (EXTERNAL / 'slots').exists():
        raise ValueError('isolated_interpreter_and_fresh_schedule_required')
    products = registered_products()
    baseline, candidate = (products[arm]['commit'] for arm in ('A', 'B'))
    if (git('rev-parse', 'HEAD') != [BASE]
            or git('rev-list', '--parents', '-n', '1', candidate) != [candidate, baseline]
            or git('diff', '--name-only', baseline, candidate) != [PRODUCT_FILE]):
        raise ValueError('candidate_not_a_direct_single_file_delta')
    request, prediction = (read(NS / 'inputs' / name) for name in ('REQUEST.json', 'PREDICTION.json'))
    for filename in ('REQUEST.json', 'PREDICTION.json', 'PRODUCT_SCHEMA.json'):
        if (NS / 'inputs' / filename).read_bytes() != (PIXEL / 'inputs' / filename).read_bytes():
            raise ValueError('registered_actual_request_or_schema_changed/' + filename)
    if prediction != dict(request, include_image=False, response_detail='full'):
        raise ValueError('registered_same_generation_prediction_required')

    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        row = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
        if ((digest is not None and row['sha256'] != digest)
                or (size is not None and row['bytes'] != size)
                or (path in pins and pins[path] != row) or path.suffix == '.pyc'):
            raise ValueError('registered_input_changed/' + str(path))
        pins[path] = row

    def pin_rows(rows):
        for row in rows:
            path = Path(row['path']).resolve()
            if path in pins:
                if pins[path]['sha256'] != row['sha256'] or pins[path]['bytes'] != row['bytes']:
                    raise ValueError('inconsistent_historical_pin/' + str(path))
            else:
                pin(path, row['sha256'], row['bytes'])

    bindings = {arm: read(path) for arm, path in BINDINGS.items()}
    if any(bindings[arm]['preparation_git'] != value['commit']
           or bindings[arm]['source_sha256'] != value['source_sha256']
           for arm, value in products.items()):
        raise ValueError('registered_product_install_changed')
    a, b = (bindings[arm] for arm in ('A', 'B'))
    sources = [{row['path']: row['sha256'] for row in item['source_manifest']} for item in (a, b)]
    if (len(sources[0]) != 143 or sources[0].keys() != sources[1].keys()
            or [name for name in sources[0] if sources[0][name] != sources[1][name]] != [PRODUCT_FILE]
            or a['dependency_root'] != b['dependency_root']):
        raise ValueError('unregistered_installed_source_or_dependency_difference')
    for path in BINDINGS.values():
        pin(path)
    for item in bindings.values():
        for row in item['source_manifest']:
            pin(Path(item['install_root']) / row['path'], row['sha256'])

    install = read(NS / 'install/BUILD_INSTALL.json')
    if (install['passed'] is not True or install['binding'] != b
            or install['actual_candidate_wheels'] != 1
            or install['historical_git_wheel_install_sources_verified'] != 143
            or install['tool_schema_matches_historical_actual_directory'] is not True
            or read(NS / 'install/PRODUCT_SCHEMA.json') != read(NS / 'inputs/PRODUCT_SCHEMA.json')):
        raise ValueError('verified_direct_candidate_install_and_same_tool_definitions_required')
    for key in ('installed_files', 'historical_installed_files', 'execution_and_input_pins'):
        pin_rows(install[key])

    controls = read(NS / 'checks/PROJECTED_BOUNDS_CONTROLS.json')
    if (controls['passed'] is not True or not all(controls['offline_gates'].values())
            or any(controls[field] != 0 for field in ('owned_Blender', 'model_consumers', 'actual_new_rasters'))
            or any(controls['product_identity'][arm]['preparation_git'] != item['commit']
                   or controls['product_identity'][arm]['source_sha256'] != item['source_sha256']
                   for arm, item in products.items())):
        raise ValueError('projected_bounds_offline_qualification_failed')
    for row in controls['sources']:
        reference = row['path']
        if reference.startswith(BASE + ':'):
            _, relative = reference.split(':', 1)
            raw = subprocess.check_output(['git', 'show', reference], cwd=ROOT)
            if len(raw) != row['bytes'] or sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('sealed_offline_Git_input_changed/' + relative)
            pin(ROOT / relative, row['sha256'], row['bytes'])
        else:
            pin_rows((row,))
    path, asset = asset_identity()
    pin(path, ASSET)
    pin(NS / 'inputs/PLAN.md', PLAN)
    pin(PIXEL / 'FROZEN.json', PIXEL_FREEZE)
    pin_rows(read(PIXEL / 'FROZEN.json')['direct_inputs'])
    pin(PIXEL / 'CONTENT_MANIFEST.json', PIXEL_MANIFEST)
    for row in read(PIXEL / 'CONTENT_MANIFEST.json')['files']:
        pin(PIXEL / row['path'], row['sha256'], row['bytes'])
    for relative, digest in (
        ('he_m4_cross_scale_pixel_evidence_001/slots/P1/TERMINAL_SOURCE.json',
         'a550a7018e07fc8e18204ffe77231b254d93a9558b2114036d2113898120a52b'),
        ('he_m4_assembly_evidence_consumption_001/slots/A1/TERMINAL_SOURCE.json',
         '81c84f4d7273cd9045702c7afb95b9c8fc21b02764106ff9d8289c7120e0964c'),
        ('he_m4_cross_scale_cold_frustum_001/slots/B1/TERMINAL_SOURCE.json',
         '31e69a857baf1f66e33722dec5ef63086565c0fbf3029c39071415782c7a0233'),
        ('he_m4_cross_scale_pixel_evidence_001/ORIGINAL_RUNTIME.zip',
         '583456c1838a6fd200104fcfaf72dfa279beaf928901a5b42164b99f60415bae'),
    ):
        pin(Path('D:/') / relative, digest)
    pin(FORMAL / 'publish.py')
    if not (NS / 'checks/live_review.py').is_file():
        raise ValueError('independent_pair_checker_required_before_first_slot')
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)

    path = NS / 'FROZEN.json'
    save(path, {'schema': SCHEMA, 'slots': list(ORDER), 'ledger_limits': LIMITS, 'products': products,
                'started_ns': started, 'completed_ns': time.perf_counter_ns(), 'owned_s': 600, 'task_s': 450,
                'asset_sha256': asset, 'runtime_model_quota': 0, 'performance_gate': PERFORMANCE_GATE,
                'direct_inputs': [pins[name] for name in sorted(pins)]})
    print('Froze six ordered slots', len(pins), verify_freeze())


if __name__ == '__main__':
    freeze()
