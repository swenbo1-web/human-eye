"""Freeze the compact region formatter, installed identity, and sole qualification."""

import ast
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import SCHEMA, registered_product, verify_freeze
from budget import LIMITS
from common import (ASSET, ASSET_SHA256, BASE_COMMIT, BASE_SOURCE_SHA, DENSE, EXTERNAL, FORMAL, GEOMETRY,
                    GEOMETRY_SHA256, ORDER, PRODUCT_BINDING, PROJECTED, ROOT, asset_identity, read, save, sha)


BASE = '76a46db953418c7204d7c4e80c7a2364fe0f26d8'
PLAN = '4f7616e4b58eedaacf593dac456527772e9007a88edc7b4436a1ece9a6c28147'
PRODUCT_FILE = 'human_eye_plugin/live_spatial_mcp.py'
ASSET_TRUTH = 'd4d05b3ffb713331c4348852335b9d17ebfe9690c7013062d39b82bb8087700a'
ORIGINAL_RECEIPT = 'a5f81128ed502163b141f730a199e7645e34a9e41cd0c65493f1c2b3fe533903'
ORIGINAL_ARCHIVE = 'edf804716aaff1dafe59f28f1adbe0901f6bf3a501cffda1c533d5d0fcc0f05d'
MANIFESTS = (
    (DENSE, '9f4f30c3104f9bd0fae9f1021618aeff324063ff826515343ab82938130946fb',
     'c17e62c10ef163137b8e6057cab0802c5dce6cf5cc96222fcb2aead09870d0ad'),
    (PROJECTED, '4655f4c824a46f6fc59cec1e0c629f7a4181318c5b7825f1718efc88836e0023',
     '163706e7167ca02220412321d268e53cb0f877537a708a4dd05ecabaf9e37775'),
)
CAP = 10800


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().split()


def freeze():
    started = time.perf_counter_ns()
    if (not sys.flags.isolated or not sys.dont_write_bytecode or (EXTERNAL / 'slots').exists()
            or git('rev-parse', 'HEAD') != [BASE]):
        raise ValueError('isolated_interpreter_and_clean_evidence_base_required')
    product = registered_product()
    if (git('rev-list', '--parents', '-n', '1', product['commit']) != [product['commit'], BASE_COMMIT]
            or git('diff', '--name-only', BASE_COMMIT, product['commit']) != [PRODUCT_FILE]):
        raise ValueError('exact_single_formatter_candidate_required')
    for name in ('REQUEST.json', 'PRODUCT_SCHEMA.json'):
        if (NS / 'inputs' / name).read_bytes() != (DENSE / 'inputs' / name).read_bytes():
            raise ValueError('original_request_or_public_definition_changed/' + name)

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
    truth = DENSE / 'truth/CURRENT_TRUTH.json'
    pin(truth, ASSET_TRUTH)
    pin(DENSE / 'checks/QUALIFICATION_QP.json', ORIGINAL_RECEIPT)
    index = read(DENSE / 'RUNTIME_INDEX.json')
    pin(index['archive']['path'], ORIGINAL_ARCHIVE, index['archive']['bytes'])
    for directory, freeze_digest, manifest_digest in MANIFESTS:
        frozen = directory / 'FROZEN.json'
        manifest = directory / 'CONTENT_MANIFEST.json'
        pin(frozen, freeze_digest)
        pin(manifest, manifest_digest)
        pin_rows(read(frozen)['direct_inputs'])
        for row in read(manifest)['files']:
            pin(directory / row['path'], row['sha256'], row['bytes'])

    install = read(NS / 'install/BUILD_INSTALL.json')
    candidate = read(PRODUCT_BINDING)
    baseline_path = PROJECTED / 'install/PRODUCT_RUN_BINDING.json'
    baseline = read(baseline_path)
    a, b = ({row['path']: row['sha256'] for row in binding['source_manifest']}
            for binding in (baseline, candidate))
    if (install['passed'] is not True or install['binding'] != candidate
            or install['actual_candidate_wheels'] != 1
            or install['historical_git_wheel_install_sources_verified'] != 143
            or install['tool_schema_matches_historical_actual_directory'] is not True
            or baseline['preparation_git'] != BASE_COMMIT or baseline['source_sha256'] != BASE_SOURCE_SHA
            or baseline['dependency_root'] != candidate['dependency_root']
            or len(a) != 143 or a.keys() != b.keys()
            or [name for name in a if a[name] != b[name]] != [PRODUCT_FILE]
            or read(NS / 'install/PRODUCT_SCHEMA.json') != read(NS / 'inputs/PRODUCT_SCHEMA.json')):
        raise ValueError('installed_candidate_is_not_a_verified_formatter_only_delta')
    for field in ('installed_files', 'historical_installed_files', 'execution_and_input_pins'):
        pin_rows(install[field])
    pin(PRODUCT_BINDING)
    pin(baseline_path)
    pin(candidate['wheel_path'], candidate['wheel_sha256'])

    offline_path = NS / 'checks/OFFLINE_CONTROLS.json'
    offline = read(offline_path)
    dense = offline['cases']['dense_brief']
    if (offline['passed'] is not True or offline['baseline_source_sha256'] != BASE_SOURCE_SHA
            or offline['candidate_source_sha256'] != product['source_sha256']
            or offline['direct_source_and_original_PNG_NPZ_verified'] is not True
            or any(offline[key] != 0 for key in ('actual_Blender_processes', 'actual_model_runs', 'actual_raster_attempts'))
            or dense['old_text_UTF8_bytes'] != 72253 or dense['new_text_UTF8_bytes'] > CAP
            or (dense['decoded_regions'], dense['observed_regions'], dense['native_images']) != (13, 11, 2)):
        raise ValueError('frozen_original_packet_and_offline_dense_delivery_gate_failed')
    pin_rows(offline['source_pins'])
    pin(FORMAL / 'publish.py')
    for needed in ('checks/brief_schema.py', 'checks/offline_controls.py', 'checks/live_review.py'):
        if not (NS / needed).is_file():
            raise ValueError('registered_offline_and_live_checks_required/' + needed)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)

    path = NS / 'FROZEN.json'
    save(path, {'schema': SCHEMA, 'slots': list(ORDER), 'ledger_limits': LIMITS, 'product': product,
                'baseline_product': {'commit': BASE_COMMIT, 'source_sha256': BASE_SOURCE_SHA},
                'asset_sha256': ASSET_SHA256, 'source_geometry_sha256': GEOMETRY_SHA256,
                'truth_sha256': ASSET_TRUTH, 'baseline_qualification_sha256': ORIGINAL_RECEIPT,
                'offline_sha256': sha(offline_path), 'started_ns': started, 'completed_ns': time.perf_counter_ns(),
                'owned_s': 600, 'task_s': 450, 'model_slots_max': 0, 'body_cap_bytes': CAP,
                'fixed_CLI': {'version': '0.152.1', 'MCP_bytes': 12000, 'history_approximate_tokens': 3000,
                              'header_bytes': [33, 34, 35]},
                'direct_inputs': [pins[key] for key in sorted(pins)]})
    print('Froze sole dense region product qualification', len(pins), verify_freeze())


if __name__ == '__main__':
    freeze()
