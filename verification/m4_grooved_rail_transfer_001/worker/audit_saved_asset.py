"""Offline export/source/lifecycle binding checks. Geometry truth is independent."""

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    freeze = read(BATCH / 'FREEZE.json')
    preparation = read(HERE / 'PREPARATION.json')
    started = read(HERE / 'PREPARATION_STARTED.json')
    build = read(BATCH / 'asset/BUILD_RESULT.json')
    snapshot = read(BATCH / 'asset/ACTUAL_SNAPSHOT.json')
    binding = read(BATCH / 'asset/ASSET_BINDING.json')
    receipt = read(HERE / 'EXPORT_RECEIPT.json')
    assert json.loads(receipt['response']['result']['result']) == snapshot
    for spec in freeze['specifications']:
        assert sha(BATCH / spec['copy']) == spec['sha256']
    for name, path in [('controller_sha256', HERE / 'prepare_asset.py'),
                       ('build_script_sha256', BATCH / 'asset/build_assets.py'),
                       ('export_script_sha256', BATCH / 'asset/export_snapshot.py'),
                       ('freeze_sha256', BATCH / 'FREEZE.json')]:
        assert started[name] == sha(path)
    helper = ROOT / 'verification/native_plugin_complex_003/reused/accepted_native.py'
    assert started['helper_sha256'] == sha(helper)
    asset = BATCH / binding['asset']
    copy = BATCH / binding['QA_asset_copy']
    assert sha(asset) == sha(copy) == binding['asset_sha256'] == build['asset_sha256']
    assert sha(BATCH / binding['snapshot']) == binding['snapshot_sha256']
    assert sha(BATCH / 'asset/BUILD_RESULT.json') == binding['build_result_sha256']
    assert sha(HERE / 'EXPORT_RECEIPT.json') == binding['export_receipt_sha256']
    builder = read(HERE / 'BUILDER_CLOSED.json')
    assert builder['pid'] == build['pid'] == read(HERE / 'BUILDER_STARTED.json')['pid']
    assert builder['process_reaped'] and builder['exit_code'] == 0
    close = read(HERE / 'QA_CLOSE.json')
    closed = read(HERE / 'qa/WORKER_CLOSED.json')
    session = read(HERE / 'qa/SESSION.json')
    assert close['pid'] == closed['pid'] == session['pid'] == snapshot['pid']
    assert close['process_reaped'] and close['exit_code'] == 0 and close['error'] is None
    assert close['source_file_unchanged'] and close['protected_files_unchanged']
    assert close['response']['status'] == 'closed'
    assert closed['initial_geometry_fingerprint'] == closed['final_geometry_fingerprint']
    assert not closed['poisoned']
    assert not preparation['errors'] and preparation['Blender_sessions_started_or_attempted'] == 2
    assert snapshot['counts'] == {'objects': 4, 'vertices': 26, 'triangles': 36}
    assert snapshot['scale_length'] == snapshot['unit_scale_m'] == 1.0
    source_objects = {row['name']: row for row in build['frozen_construction']}
    actual_matrix = snapshot['objects'][0]['matrix_world']
    for obj in snapshot['objects']:
        expected = source_objects[obj['name']]
        normalized = [[struct.unpack('<f', struct.pack('<f', float(Fraction(x))))[0]
                       for x in point] for point in expected['vertices_exact_local_mm']]
        assert obj['vertices_local'] == normalized
        assert obj['triangles'] == obj['faces'] == expected['triangles']
        assert obj['matrix_world'] == actual_matrix
        assert obj['parent'] is None and not obj['modifiers'] and not obj['constraints']
        assert not obj['animation_present'] and not obj['shape_keys_present']
        assert not obj['object_custom_properties'] and not obj['mesh_custom_properties']
        assert not obj['material_names']
        for local, world in zip(obj['vertices_local'], obj['vertices_world']):
            for axis in range(3):
                matrix = obj['matrix_world'][axis]
                assert ((matrix[0] * local[0] + matrix[1] * local[1])
                        + matrix[2] * local[2]) + matrix[3] == world[axis]
    assert {o['name'] for o in snapshot['objects']} == {'Target', 'Part_A', 'Part_B', 'Part_C'}
    input_matrix = build['matrix_world_input_binary32']
    matrix_difference = max(abs(actual_matrix[row][col] - input_matrix[row][col])
                            for row in range(4) for col in range(4))
    images = [str(p.relative_to(BATCH)) for p in BATCH.rglob('*')
              if p.is_file() and p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')]
    assert not images
    checks = {
        'status': 'source_export_and_owned_shutdown_bound',
        'geometry_qualification': 'independent_oracle_pending',
        'actual_counts': snapshot['counts'], 'asset_sha256': sha(asset),
        'snapshot_sha256': sha(BATCH / binding['snapshot']),
        'all_actual_matrices_identical': True,
        'actual_vs_input_matrix_max_abs_element_difference': matrix_difference,
        'matrix_storage_note': 'Blender decomposes assigned matrix into stored quaternion and scale; actual readback is preserved without correction',
        'construction_local_coordinates_match_binary32_of_frozen_rationals': True,
        'construction_triangles_match_saved_export': True,
        'world_coordinates_match_declared_binary64_evaluation': True,
        'no_answer_custom_properties_or_materials': True,
        'controller_window_elapsed_ns': preparation['elapsed_ns'],
        'controller_window_scope': preparation['window_scope'],
        'Blender_sessions': 2, 'distinct_geometry_candidates': 1,
        'builder_exit0_reaped': True, 'QA_exit0_reaped': True,
        'QA_geometry_unchanged': True,
        'models': 0, 'product_processes': 0, 'images': 0,
        'failure_records': []}
    save(HERE / 'EXPORT_AUDIT.json', checks)
    paths = [p for folder in ('asset', 'worker') for p in (BATCH / folder).rglob('*') if p.is_file()]
    source_inputs = [BATCH / 'FREEZE.json'] + [BATCH / s['copy'] for s in freeze['specifications']] + [helper]
    manifest = {'asset_sha256': sha(asset), 'snapshot_sha256': sha(BATCH / binding['snapshot']),
                'input_sources': [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in source_inputs],
                'asset_worker_files_excluding_this_manifest': [
                    {'path': p.relative_to(BATCH).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
                    for p in sorted(paths)]}
    save(HERE / 'SOURCE_OUTPUT_MANIFEST.json', manifest)
    print(json.dumps(checks))


if __name__ == '__main__':
    main()
