"""Preserve the original raw evidence and the two planned formal denominators."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


NS = Path(__file__).resolve().parent
ROOT = NS.parents[1]
RUN = Path('D:/he_m4_cross_scale_live_task_001')
BASE = 'f32b02b5d4a32bdbe37e8e6a43e3f977c6981d31'
LABELS = ('QN', 'QP', 'N1', 'P1')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, value):
    with path.open('x', encoding='utf8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write('\n')


def record_cost():
    slots = []
    for label in LABELS:
        path = RUN / 'slots' / label
        if not (path / 'SLOT_PUBLICATION.json').is_file():
            slots.append({'label': label, 'status': 'unrun', 'reason': 'paired_qualification_failed',
                          'model_consumers': 0, 'business_calls': 0, 'rasters': 0})
            continue
        result_path = path / 'SLOT_RESULT.json'
        result, publication = read(result_path), read(path / 'SLOT_PUBLICATION.json')
        if sha(result_path) != publication['result_sha256'] or label != result['label']:
            raise ValueError('original result identity differs')
        failure = read(path / 'native/START_FAILURE.json')
        stderr = path / 'native/worker_stderr.txt'
        if 'visual004_native_display_fixed_mesh_inventory' not in stderr.read_text(encoding='utf8'):
            raise ValueError('expected exact blocking error absent for ' + label)
        if (path / 'owner').exists() or (path / 'client').exists() or result['diagnostic_calls']:
            raise ValueError('startup-only observation required')
        slots.append({'label': label, 'status': result['status'], 'full_slot_ns': publication['complete_slot_ns'],
                      'worker_admission_through_startup_failure_ns': failure['elapsed_ns'],
                      'Blender_started': 1, 'business_calls': 0, 'rasters': 0, 'model_consumers': 0,
                      'worker_stderr_sha256': sha(stderr), 'worker_result_sha256': sha(result_path),
                      'worker_start_failure': failure, 'errors': result['errors'],
                      'observed_blocker': 'visual004_native_display_fixed_mesh_inventory',
                      'unrun_phases': ['installed_MCP', 'scene_capture', 'partition', 'spatial_index',
                                       'raster', 'PNG/NPZ', 'model_context', 'model_answer']})
    builder = read(RUN / 'fixture_preparation/RESULT.json')
    write(NS / 'RUNTIME_REVIEW.json', {'slots': slots, 'builder': builder, 'provider_usage': None,
          'actual_paid_API_calls': 0, 'failure_scope': 'Both real qualification worker starts stopped before tools.'})


def archive():
    paths = []
    for component in ('slots', 'budget', 'preflight', 'fixture', 'fixture_preparation'):
        root = RUN / component
        for path in root.rglob('*'):
            if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('runtime reparse point ' + str(path))
            if path.is_file():
                paths.append(path)
    paths.sort()
    rows = [{'path': p.relative_to(RUN).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in paths]
    output = RUN / 'ORIGINAL_RUNTIME.zip'
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=4) as archive:
        for p, row in zip(paths, rows, strict=True):
            archive.write(p, row['path'])
    with zipfile.ZipFile(output) as archive:
        if archive.namelist() != [row['path'] for row in rows]:
            raise ValueError('archive members differ')
        for path, row in zip(paths, rows, strict=True):
            with archive.open(row['path']) as stream:
                seen = hashlib.file_digest(stream, 'sha256').hexdigest()
            if seen != row['sha256'] or sha(path) != seen or path.stat().st_size != row['bytes']:
                raise ValueError('archive bytes differ ' + row['path'])
    write(NS / 'RUNTIME_INDEX.json', {'files': rows, 'count': len(rows),
          'original_bytes': sum(r['bytes'] for r in rows),
          'archive': {'path': str(output), 'bytes': output.stat().st_size, 'sha256': sha(output)}})
    print(len(rows), sha(output))


def finalize():
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    if any(not path.startswith(prefix) for path in changed):
        raise ValueError('project outside qualification has changed')
    freeze = NS / 'FROZEN.json'
    for row in read(freeze)['direct_inputs']:
        path = Path(row['path'])
        if sha(path) != row['sha256'] or path.stat().st_size != row['bytes']:
            raise ValueError('frozen input changed ' + str(path))
    qualification = read(NS / 'QUALIFICATION.json')
    if qualification['passed'] or qualification['freeze_sha256'] != sha(freeze):
        raise ValueError('original denied admission required for this batch closeout')
    proofs = ['REPORT.md', 'QUALIFICATION.json', 'RUNTIME_REVIEW.json', 'RUNTIME_INDEX.json', 'scoring/QUALITY.json']
    write(NS / 'DECISION.json', {'task': 'M4-CROSS-SCALE-LIVE-TASK-001', 'qualified': False,
          'qualification': {'QN': 'failed', 'QP': 'failed'}, 'formal': {'N1': 'unrun', 'P1': 'unrun'},
          'freeze_sha256': sha(freeze), 'original_owned_launches': 2, 'replacements': 0, 'model_consumers': 0,
          'product_diff_files': 0, 'raster_attempts': 0, 'paid_API_calls': 0,
          'evidence': {name: sha(NS / name) for name in proofs}})
    manifest = NS / 'CONTENT_MANIFEST.json'
    files = [p for p in sorted(NS.rglob('*')) if p.is_file() and p != manifest]
    if any(p.suffix == '.pyc' for p in files):
        raise ValueError('runtime bytecode unexpectedly entered evidence')
    rows = [{'path': p.relative_to(NS).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files]
    write(manifest, {'files': rows, 'count': len(rows), 'self_excluded': True})
    print(len(rows) + 1, sha(manifest))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('action', choices=('archive', 'finalize'))
    if cli.parse_args().action == 'archive':
        record_cost()
        archive()
    else:
        finalize()
