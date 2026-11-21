"""Seal the original image, exact serializer replay, and distinct host outcomes."""

from hashlib import file_digest, sha256
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile


NS = Path(__file__).resolve().parent
ROOT = NS.parents[1]
P2 = NS.parent / 'perf050_source_region_active_view_p2'
BASE = '30c9cfc121bbdee72b61afda59cbcf23e9080b67'
HISTORY = '1a6375dc81dbce7db08ad1dc5d7a073ecd75410b'
PLAN = '66e2523184e8e24251b5d335c4d4b0cb9d00a295:docs/M1_SOURCE_REGION_FINAL_IMAGE_001_PLAN.md'
CHANGED = 'human_eye_plugin/live_spatial_mcp.py'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with Path(path).open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write('\n')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def seal():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('use_pinned_isolated_interpreter')
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    if any(not row.startswith(prefix) for row in git('diff', '--name-only', HISTORY).decode().splitlines()):
        raise ValueError('original_or_unrelated_evidence_changed')
    plan = NS / 'PLAN.md'
    if plan.read_bytes() != git('show', PLAN):
        raise ValueError('registered_plan_changed')
    build = read(NS / 'install/BUILD_INSTALL.json')
    binding = read(NS / 'install/PRODUCT_RUN_BINDING.json')
    candidate = binding['preparation_git']
    if (git('rev-list', '--parents', '-n', '1', candidate).decode().split() != [candidate, BASE]
            or git('diff', '--name-only', BASE, candidate).decode().splitlines() != [CHANGED]
            or build['passed'] is not True or build['binding'] != binding
            or len(binding['source_manifest']) != 143 or binding['changed_product_sources'] != [CHANGED]
            or build['tool_schema_matches_historical_actual_directory'] is not True):
        raise ValueError('one_isolated_serializer_candidate_required')

    sources = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        row = sources.get(path)
        if row is None:
            row = sources[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        if (digest is not None and row['sha256'] != digest or size is not None and row['bytes'] != size
                or path.suffix == '.pyc'):
            raise ValueError('selected_original_or_input_bytes_changed/' + str(path))
        return row

    def bind(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    receipts = {}
    for filename in ('WIRE_AUDIT.json', 'BASELINE_SERIALIZER.json', 'SERIALIZER.json'):
        path = NS / 'checks' / filename
        data = read(path)
        if data['passed'] is not True:
            raise ValueError('required_archive_or_serializer_gate_failed/' + filename)
        bind(data['source_pins'])
        receipts[filename] = pin(path)['sha256']
    host_path = NS / 'checks/HOST_OPEN.json'
    host = read(host_path)
    original = host['selected_original']
    png = pin(original['path'], original['sha256'], original['bytes'])
    if (host['closed_before_open'] is not True or host['actual_file_open']['passed'] is not True
            or host['actual_host_file_image']['returned_bytes_match_original'] is not True
            or host['actual_host_file_image']['same_image_forwarded_in_current_exchange'] is not True):
        raise ValueError('actual_closed_slot_file_image_open_required')

    replay = read(NS / 'checks/SERIALIZER.json')
    if replay['candidate_runtime_source_sha256'] != binding['source_sha256']:
        raise ValueError('serializer_replay_uses_a_different_install')
    for name in ('cold_brief', 'brief'):
        observed = replay['cold_and_hot'][name]
        if (observed['path'] != original['path'] or observed['original_PNG_sha256'] != png['sha256']
                or observed['opened_bytes'] != png['bytes'] or observed['fixed_CLI']['passed'] is not True
                or len(observed['fixed_CLI']['stages']) != 6
                or not all(stage['body_exact'] and stage['PNG_exact'] for stage in observed['fixed_CLI']['stages'])):
            raise ValueError('candidate_reference_must_reopen_the_exact_original/' + name)

    quality = read(P2 / 'QUALITY.json')
    if (quality['actual_slot']['quality_earned'], quality['actual_slot']['quality_possible']) != (4, 5):
        raise ValueError('historical_P2_grade_changed')
    original_index = P2 / 'RUNTIME_INDEX.json'
    idx = read(original_index)
    zip_row = idx['archive']
    pin(zip_row['path'], zip_row['sha256'], zip_row['bytes'])
    with ZipFile(zip_row['path']) as zipped:
        if idx['count'] != 338 or len(idx['files']) != 338 or zipped.namelist() != [row['path'] for row in idx['files']]:
            raise ValueError('original_P2_archive_membership_changed')
        for row in idx['files']:
            with zipped.open(row['path']) as source:
                if zipped.getinfo(row['path']).file_size != row['bytes'] or file_digest(source, 'sha256').hexdigest() != row['sha256']:
                    raise ValueError('original_P2_archive_member_bytes_changed/' + row['path'])
        if sha256(zipped.read('slots/P2/consumer/PUBLIC_FINAL.txt')).hexdigest() != quality['actual_slot']['answer_sha256']:
            raise ValueError('original_P2_scorable_answer_changed')
    pin(P2 / 'answers/P2.txt', quality['actual_slot']['answer_sha256'])
    pin(P2 / 'QUALITY.json')
    pin(original_index)
    pin(host_path)
    for key in ('installed_files', 'historical_installed_files', 'execution_and_input_pins', 'staged_candidate_git_files'):
        bind(build[key])
    pin(binding['wheel_path'], binding['wheel_sha256'])
    pin(sys.executable)
    for path in NS.rglob('*'):
        if path.is_file():
            pin(path)

    frozen = NS / 'FROZEN.json'
    write(frozen, {'schema': 'm1-source-region-final-image-v1', 'baselined_product': BASE,
          'candidate': {'commit': candidate, 'source_sha256': binding['source_sha256'],
                        'wheel_sha256': binding['wheel_sha256'], 'runtime_sources': 143},
          'old_P2_quality': [4, 5], 'old_P2_answer_sha256': quality['actual_slot']['answer_sha256'],
          'original_archive_sha256': zip_row['sha256'], 'original_archive_member_count': 338,
          'selected_original': original, 'receipts': receipts, 'actual_host_open_sha256': sha(host_path),
          'direct_inputs': [sources[path] for path in sorted(sources)]})
    write(NS / 'DECISION.json', {'scope': 'offline_serializer_and_one_closed_slot_local_file_image',
          'passed_serializer_and_local_file': True, 'freeze_sha256': sha(frozen), 'product_changed_files': [CHANGED],
          'actual_product_builds': 1, 'candidate_serializer_positive_replays': 2,
          'native_file_read_proven': True, 'prepared_host_file_image_demonstrations': 1,
          'confirmed_codex_panel_opens': 0, 'observed_user_clicks': 0, 'natural_model_final_attachment_tests': 0,
          'Blender_starts': 0, 'models': 0, 'rasters': 0, 'Google_API_calls': 0, 'extra_paid_calls': 0,
          'replacements': 0})
    manifest = NS / 'CONTENT_MANIFEST.json'
    rows = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
            for path in sorted(NS.rglob('*')) if path.is_file() and path != manifest]
    write(manifest, {'count': len(rows), 'files': rows, 'self_excluded': True})
    print('Sealed', len(rows), sha(manifest), 'frozen', sha(frozen), flush=True)


if __name__ == '__main__':
    seal()
