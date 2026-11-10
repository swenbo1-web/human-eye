"""Verify completed finite evidence and seal its current bytes; no product run."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
EXPECTED = '7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'
PRODUCT = ('human_eye_plugin/task_query.py', 'human_eye_plugin/live_service.py',
           'human_eye_plugin/live_spatial_mcp.py')
sha = lambda raw: hashlib.sha256(raw).hexdigest()
read = lambda path: json.loads(path.read_bytes())


def save(path, value):
    assert not path.exists(), path
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True)+'\n', encoding='utf8')


def main():
    tree = ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes())
    values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES')}
    names = set(values['_ROOT_MODULES']) | {path.relative_to(ROOT).as_posix()
        for package in ('human_eye_plugin', 'human_eye_module1_operators')
        for path in (ROOT/package).glob('*.py')}
    manifest = [dict(path=name, sha256=sha((ROOT/name).read_bytes())) for name in sorted(names)]
    material = dict(base_version=values['BASE_VERSION'],
        implementation_revision=values['IMPLEMENTATION_REVISION'], files=manifest)
    digest = sha(json.dumps(material, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    assert len(manifest) == 137 and digest == EXPECTED
    comparison = read(HERE/'compare_02/RESULTS.json')
    assert comparison['passed'] is True and not comparison['errors']
    assert comparison['strict_entry_core_pairs'] == 18
    assert comparison['entry_pairs_with_different_capture_binding'] == 0
    assert len(comparison['direct_groups']) == 9
    assert sum(row['observations'] for row in comparison['direct_groups']) == 11
    counts = {key: sum(row['counts']['candidate'][key] for row in comparison['entry_cases'])
              for key in ('capture', 'pair', 'kernel', 'rank', 'nearest', 'closed_solid')}
    assert counts == dict(capture=18, pair=24, kernel=24, rank=16, nearest=20, closed_solid=0)
    fixtures = None
    for name in ('baseline_02', 'candidate_02'):
        result = read(HERE/name/'RESULTS.json')
        identity = read(HERE/name/'EXECUTION_IDENTITY.json')
        assert result['successful'] is True and result['tests'] == 49
        assert not result['failures'] and not result['errors'] and not result['skipped']
        assert result['model_consumers'] == result['Blender_sessions'] == result['network_sessions'] == 0
        assert not result['external_operation_attempts']
        assert identity['guard_verify_loaded'] is True
        assert identity['checkout_files_unchanged'] is True
        assert identity['loaded_tests_unchanged'] is True
        assert identity['original_read_evidence_unchanged'] is True
        if fixtures is None:
            fixtures = identity['fixture_sha256']
        else:
            assert fixtures == identity['fixture_sha256']
        for path, expected in identity['fixture_sha256'].items():
            assert sha((ROOT/path).read_bytes()) == expected, path
        for path, entry in identity['loaded_tests'].items():
            assert sha((ROOT/path).read_bytes()) == entry['sha256'], path
    # Recheck the old sealed run AFTER qualification, without running it.
    previous_path = ROOT/'verification/m1_task_entry_001_eval/formal_run/EXECUTION_ARTIFACT_INDEX.json'
    previous = read(previous_path)
    old_rows = previous['files']+previous['duplicate_input_assets_retained_local_and_in_private_zip']
    for row in old_rows:
        data = (ROOT/row['path']).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256'], row['path']
    changed = subprocess.run(['git', '-C', str(ROOT), 'diff', '--name-only'],
        check=True, stdout=subprocess.PIPE, timeout=30).stdout.decode().splitlines()
    assert set(changed) == set(PRODUCT), changed
    excluded = {'ARTIFACT_INDEX.json', 'CANDIDATE_SEAL.json'}
    paths = sorted([ROOT/name for name in PRODUCT]+[path for path in HERE.rglob('*')
        if path.is_file() and path.name not in excluded
        and not {'engine', 'tmp', '__pycache__'}.intersection(path.relative_to(HERE).parts)])
    files = [dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size,
                  sha256=sha(path.read_bytes())) for path in paths]
    index = dict(cycle_id='M1-NEAREST-EVIDENCE-001', file_count=len(files),
        bytes=sum(row['bytes'] for row in files), files=files,
        policy='exact selected bytes; original failed attempts and corrected evidence retained; '
               'four duplicate 137-source engine snapshots and cleaned temporary directories excluded from Git')
    save(HERE/'ARTIFACT_INDEX.json', index)
    seal = dict(cycle_id='M1-NEAREST-EVIDENCE-001', source_sha256=digest, source_count=137,
        product_files=[row for row in manifest if row['path'] in PRODUCT],
        artifact_index_sha256=sha((HERE/'ARTIFACT_INDEX.json').read_bytes()),
        indexed_files=len(files), indexed_bytes=index['bytes'],
        final_methods_each_version=49, final_entry_records=18,
        existing_direct_groups=9, existing_direct_records=11,
        exact_core_and_counts_comparison=True, counts_each_version=counts,
        original_formal_files_unchanged=len(previous['files']),
        original_duplicate_inputs_unchanged=len(previous['duplicate_input_assets_retained_local_and_in_private_zip']),
        original_index_sha256=sha(previous_path.read_bytes()),
        retained_failures=['baseline_01: obsolete action-state-file assertion',
            'candidate_01: same obsolete action-state-file assertion',
            'compare_01: comparator repeated its source-hash normalization'],
        qualification='guarded source/fake RNA/real kernel; not installation or actual Blender qualification',
        model_consumers=0, model_benefit_measured=False, network_sessions=0,
        default_installation_activated=False, new_assets=0,
        report='verification/m1_nearest_evidence_001/REPORT.md')
    save(HERE/'CANDIDATE_SEAL.json', seal)
    print(json.dumps(seal, ensure_ascii=True))


if __name__ == '__main__':
    main()
