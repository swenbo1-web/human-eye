"""Independently bind the frozen specification, saved asset and owned export."""

from collections import defaultdict
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE / 'SOURCE_REVIEW.json').exists()
    freeze = read(BATCH / 'FREEZE.json')
    checks = {}
    for record in freeze['specifications']:
        raw = (BATCH / record['copy']).read_bytes()
        committed = subprocess.run(['git', '-C', str(ROOT), 'cat-file', 'blob',
            freeze['parent_commit'] + ':' + record['parent_path']], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=True).stdout
        checks[record['copy'] + '_parent_commit_binding'] = raw == committed and hashlib.sha256(raw).hexdigest() == record['sha256']
    manifest = read(BATCH / 'worker/SOURCE_OUTPUT_MANIFEST.json')
    records = manifest['asset_worker_files_excluding_this_manifest']
    checks['asset_worker_manifest_complete'] = {record['path'] for record in records} == {
        path.relative_to(BATCH).as_posix() for directory in ('asset', 'worker')
        for path in (BATCH / directory).rglob('*') if path.is_file() and path.name != 'SOURCE_OUTPUT_MANIFEST.json'}
    checks['asset_worker_output_hashes'] = all(sha(BATCH / record['path']) == record['sha256']
        and (BATCH / record['path']).stat().st_size == record['bytes'] for record in records)
    checks['asset_worker_input_hashes'] = all(sha(Path(record['path'])) == record['sha256']
        and Path(record['path']).stat().st_size == record['bytes'] for record in manifest['input_sources'])
    binding = read(BATCH / 'asset/ASSET_BINDING.json')
    checks['unique_candidate_and_QA_read_copy'] = len(list((BATCH / 'asset').glob('*.blend'))) == 1
    checks['unique_candidate_and_QA_read_copy'] &= sha(BATCH / binding['asset']) == sha(BATCH / binding['QA_asset_copy']) == binding['asset_sha256'] == manifest['asset_sha256']
    snapshot = read(BATCH / binding['snapshot'])
    checks['actual_snapshot_hash'] = sha(BATCH / binding['snapshot']) == binding['snapshot_sha256'] == manifest['snapshot_sha256']
    session = read(BATCH / 'worker/qa/SESSION.json')
    receipt = read(BATCH / 'worker/EXPORT_RECEIPT.json')
    checks['actual_export_response_binding'] = json.loads(receipt['response']['result']['result']) == snapshot
    checks['actual_export_stdout_binding'] = read(BATCH / 'worker/qa/call_1/stdout.txt') == snapshot
    checks['actual_export_session_binding'] = Path(snapshot['blend_filepath']).resolve() == Path(session['asset_copy']).resolve() == (BATCH / binding['QA_asset_copy']).resolve()
    checks['actual_export_session_binding'] &= Path(session['asset']).resolve() == (BATCH / binding['asset']).resolve() and session['asset_sha256'] == binding['asset_sha256']
    started = read(BATCH / 'worker/BUILDER_STARTED.json')
    builder = read(BATCH / 'worker/BUILDER_CLOSED.json')
    close = read(BATCH / 'worker/QA_CLOSE.json')
    closed = read(BATCH / 'worker/qa/WORKER_CLOSED.json')
    preparation = read(BATCH / 'worker/PREPARATION.json')
    checks['factory_background_builder_bound_and_reaped'] = started['pid'] == builder['pid']
    checks['factory_background_builder_bound_and_reaped'] &= all(flag in started['argv'] for flag in ('--factory-startup', '--disable-autoexec', '--background'))
    checks['factory_background_builder_bound_and_reaped'] &= builder['process_reaped'] is True and builder['exit_code'] == 0
    checks['owned_QA_worker_exit_confirmed'] = session['pid'] == close['pid'] == closed['pid']
    checks['owned_QA_worker_exit_confirmed'] &= close['process_reaped'] is True and close['exit_code'] == 0 and close['error'] is None
    checks['owned_QA_worker_exit_confirmed'] &= close['response']['status'] == 'closed' and closed['poisoned'] is False
    checks['owned_QA_worker_geometry_and_files_unchanged'] = closed['initial_geometry_fingerprint'] == closed['final_geometry_fingerprint']
    checks['owned_QA_worker_geometry_and_files_unchanged'] &= close['source_file_unchanged'] is True and close['protected_files_unchanged'] is True
    checks['two_stages_one_geometry_no_product_model_images'] = preparation['Blender_sessions_started_or_attempted'] == 2
    checks['two_stages_one_geometry_no_product_model_images'] &= not preparation['errors'] and preparation['models'] == preparation['product_processes'] == preparation['images'] == 0
    checks['preparation_clock_original_window'] = preparation['ended_ns'] - preparation['started_ns'] == preparation['elapsed_ns']
    protected = read(BATCH / 'PROTECTED_BEFORE.json')
    checks['root_protected_inputs_unchanged'] = all((sha(Path(path)) if Path(path).is_file() else None) == expected
        for path, expected in protected.items())
    source = read(BATCH / 'SOURCE_BINDING.json')
    installed = Path(source['reused_installation']['install_root'])
    checks['same_137_source_worktree_and_install'] = len(source['source_manifest']) == 137 and all(
        sha(ROOT / record['path']) == record['sha256'] == sha(installed / record['path']) for record in source['source_manifest'])

    spec = importlib.util.spec_from_file_location('_independent_actual_math', HERE / 'actual_certificates.py')
    math = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(math)
    geometry = {}
    for obj in snapshot['objects']:
        vertices = [math.exact(point) for point in obj['vertices_world']]
        edges = defaultdict(list)
        for face in obj['triangles']:
            for a, b in zip(face, face[1:] + face[:1]):
                edges[tuple(sorted((a, b)))].append((a, b))
        checks[obj['name'] + '_actual_closed_oriented_edges'] = all(len(uses) == 2 and uses[0] == uses[1][::-1] for uses in edges.values())
        volume = sum(math.dot(vertices[a], math.cross(vertices[b], vertices[c])) for a, b, c in obj['triangles']) / 6
        checks[obj['name'] + '_actual_positive_volume'] = volume > 0
        if obj['name'] != 'Target':
            outward = []
            for face in obj['triangles']:
                a, b, c = (vertices[index] for index in face)
                opposite = vertices[next(index for index in range(4) if index not in face)]
                outward.append(math.dot(math.sub(opposite, a), math.cross(math.sub(b, a), math.sub(c, a))) < 0)
            checks[obj['name'] + '_actual_tetra_faces_outward'] = all(outward)
        geometry[obj['name']] = {'vertices': vertices, 'faces': obj['triangles'], 'actual_signed_volume_m3': str(volume)}
    a = geometry['Part_A']
    target_vertex = geometry['Target']['vertices'][0]
    reverse_witness = []
    for face in a['faces']:
        origin, second, third = (a['vertices'][index] for index in face)
        value = math.dot(math.sub(target_vertex, origin), math.cross(math.sub(second, origin), math.sub(third, origin)))
        if value > 0:
            reverse_witness.append({'A_face': face, 'Target_vertex': 0, 'strict_outside_plane_value': str(value)})
    checks['Target_not_contained_in_A_actual_tetra'] = bool(reverse_witness)
    outputs = {name: sha(BATCH / name) for name in ('FREEZE.json', 'SOURCE_BINDING.json', 'PROTECTED_BEFORE.json',
        'asset/ASSET_BINDING.json', 'asset/ACTUAL_SNAPSHOT.json', 'worker/SOURCE_OUTPUT_MANIFEST.json',
        'worker/EXPORT_AUDIT.json', 'worker/QA_CLOSE.json', 'worker/BUILDER_CLOSED.json',
        'review/ACTUAL_CERTIFICATES.json', 'review/actual_certificates.py', 'review/check_sources.py')}
    result = {'passed': all(checks.values()), 'checks': checks, 'files_sha256': outputs,
        'actual_signed_volumes_m3': {name: value['actual_signed_volume_m3'] for name, value in geometry.items()},
        'reverse_A_containment_exclusion': reverse_witness, 'preparation_elapsed_ns': preparation['elapsed_ns'],
        'qualification_scope': 'Source, owned-worker exit and actual oriented topology. Full intersection/containment oracle reviewed separately.',
        'reviewer_Blender_model_product_runs': 0}
    with (HERE / 'SOURCE_REVIEW.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'failed': [key for key, value in checks.items() if not value]}))


if __name__ == '__main__':
    main()
