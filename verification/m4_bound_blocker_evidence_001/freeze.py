"""Freeze the source-bound blocker candidate and only actual qualification."""

import ast
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import CHANGED, SCHEMA, registered_product, verify_freeze
from budget import LIMITS
from common import (ASSET, ASSET_SHA256, BASE_BINDING, BASE_COMMIT, BASE_SOURCE_SHA, BRIEF, DENSE, EXTERNAL, FORMAL,
                    GEOMETRY, GEOMETRY_SHA256, ORDER, PRODUCT_BINDING, ROOT, asset_identity, read, save, sha)


BASE = '0ed73acd26a95c5c7125484d56ddb94f856113d2'
PLAN = '04758a428c3fd795560953a5e7076d50083f68d13c114e73c5dcbd895b7de82e'
TRUTH = 'd4d05b3ffb713331c4348852335b9d17ebfe9690c7013062d39b82bb8087700a'
BASE_ARCHIVE = '0afc0e820eaef19efcf5c2c4c502191c3d69e0852d9f6d732da04312713deb42'
MANIFESTS = (
    (BRIEF, 'b0660b1eb64afec1c6f8a6c78e208dbe194c117efc9a36ccbae30213186a0f50',
     '47bc5f9aaa240fc91bd66564f4d0712ea3d270c86f163f4de087d487a2ea548e'),
    (NS.parent / 'm4_dense_panel_sweep_formal_001', '777ff348d9282e7b9f7c402d7f97a34f46b4116b5b8f20decbaa773d57d4d97e',
     '77c690e651f9a933bc66beff4ac276d04dbe25c1700c86f57ef9a750cc4608db'),
)
CAP = 10800


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().split()


def freeze():
    started = time.perf_counter_ns()
    if (not sys.flags.isolated or not sys.dont_write_bytecode or (EXTERNAL / 'slots').exists()
            or git('rev-parse', 'HEAD') != [BASE]):
        raise ValueError('isolated_interpreter_and_fixed_evidence_ancestry_required')
    product = registered_product()
    if (git('rev-list', '--parents', '-n', '1', product['commit']) != [product['commit'], BASE_COMMIT]
            or git('diff', '--name-only', BASE_COMMIT, product['commit']) != CHANGED):
        raise ValueError('candidate_not_a_direct_delta_in_the_registered_product_sources')
    for name in ('REQUEST.json', 'PRODUCT_SCHEMA.json'):
        if (NS / 'inputs' / name).read_bytes() != (DENSE / 'inputs' / name).read_bytes():
            raise ValueError('original_dense_request_or_product_definition_changed/' + name)

    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        row = pins.get(path)
        if row is None:
            row = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
        if ((digest is not None and row['sha256'] != digest)
                or (size is not None and row['bytes'] != size) or path.suffix == '.pyc'):
            raise ValueError('registered_input_changed/' + str(path))
        pins[path] = row

    def pin_rows(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    asset, digest = asset_identity()
    if asset != ASSET.resolve() or digest != ASSET_SHA256:
        raise ValueError('registered_dense_asset_required')
    pin(asset, digest)
    pin(GEOMETRY, GEOMETRY_SHA256)
    pin(NS / 'inputs/PLAN.md', PLAN)
    pin(DENSE / 'truth/CURRENT_TRUTH.json', TRUTH)
    old_index = read(BRIEF / 'RUNTIME_INDEX.json')
    pin(old_index['archive']['path'], BASE_ARCHIVE, old_index['archive']['bytes'])
    for directory, freeze_digest, manifest_digest in MANIFESTS:
        frozen = directory / 'FROZEN.json'
        manifest = directory / 'CONTENT_MANIFEST.json'
        pin(frozen, freeze_digest)
        pin(manifest, manifest_digest)
        pin_rows(read(frozen)['direct_inputs'])
        for row in read(manifest)['files']:
            pin(directory / row['path'], row['sha256'], row['bytes'])

    baseline, candidate = (read(path) for path in (BASE_BINDING, PRODUCT_BINDING))
    install = read(NS / 'install/BUILD_INSTALL.json')
    a, b = ({row['path']: row['sha256'] for row in binding['source_manifest']}
            for binding in (baseline, candidate))
    if (install['passed'] is not True or install['binding'] != candidate
            or install['actual_candidate_wheels'] != 1
            or install['historical_git_wheel_install_sources_verified'] != 143
            or install['tool_schema_matches_historical_actual_directory'] is not True
            or baseline['preparation_git'] != BASE_COMMIT or baseline['source_sha256'] != BASE_SOURCE_SHA
            or baseline['dependency_root'] != candidate['dependency_root']
            or len(a) != 143 or a.keys() != b.keys() or [name for name in a if a[name] != b[name]] != CHANGED
            or read(NS / 'install/PRODUCT_SCHEMA.json') != read(NS / 'inputs/PRODUCT_SCHEMA.json')):
        raise ValueError('registered_installed_sources_or_actual_tools_changed')
    for field in ('installed_files', 'historical_installed_files', 'execution_and_input_pins'):
        pin_rows(install[field])
    pin(BASE_BINDING)
    pin(PRODUCT_BINDING)
    pin(candidate['wheel_path'], candidate['wheel_sha256'])

    geometry_path, format_path = (NS / 'checks' / filename for filename in (
        'GEOMETRY_CONTROLS.json', 'FORMAT_CONTROLS.json'))
    geometry, projection = (read(path) for path in (geometry_path, format_path))
    for receipt in (geometry, projection):
        if (receipt['passed'] is not True or receipt['baseline_source_sha256'] != BASE_SOURCE_SHA
                or receipt['candidate_source_sha256'] != product['source_sha256']):
            raise ValueError('independent_geometry_or_format_qualification_failed')
        pin_rows(receipt['source_pins'])
    dense = projection['cases']['dense_brief']
    if (projection['geometry_receipt_sha256'] != sha(geometry_path)
            or dense['old_text_UTF8_bytes'] != 8242 or dense['new_text_UTF8_bytes'] > CAP
            or (dense['qualified_region_count'], dense['witness_count'], dense['original_image_count']) != (13, 11, 2)
            or len(geometry['fixtures']['dense']['rows']) != 2):
        raise ValueError('registered_fixed_CLI_and_two_bound_blockers_required')
    pin(FORMAL / 'publish.py')
    for name in ('checks/geometry_controls.py', 'checks/format_controls.py', 'checks/live_review.py',
                 'harness/run_slot.py', 'publish.py'):
        if not (NS / name).is_file():
            raise ValueError('missing_registered_preflight_or_live_checker/' + name)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)

    path = NS / 'FROZEN.json'
    save(path, {'schema': SCHEMA, 'slots': list(ORDER), 'ledger_limits': LIMITS, 'product': product,
         'baseline_product': {'commit': BASE_COMMIT, 'source_sha256': BASE_SOURCE_SHA},
         'started_ns': started, 'completed_ns': time.perf_counter_ns(), 'asset_sha256': ASSET_SHA256,
         'source_geometry_sha256': GEOMETRY_SHA256, 'truth_sha256': TRUTH,
         'geometry_controls_sha256': sha(geometry_path), 'format_controls_sha256': sha(format_path),
         'body_cap_bytes': CAP, 'owned_s': 600, 'task_s': 450, 'model_slots_max': 0,
         'fixed_CLI': {'version': '0.152.1', 'MCP_bytes': 12000, 'history_approximate_tokens': 3000,
                       'header_bytes': [33, 34, 35]},
         'direct_inputs': [pins[path] for path in sorted(pins)]})
    print('Froze sole source-bound blocker qualification', len(pins), verify_freeze())


if __name__ == '__main__':
    freeze()
