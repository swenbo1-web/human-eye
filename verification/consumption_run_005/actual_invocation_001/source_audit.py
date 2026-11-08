"""RUN-005 read-only byte audit; no product/helper/consumer imports or execution."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

OUT = Path(__file__).resolve().parent
RUN = OUT.parent
ROOT = RUN.parents[1]
BASE = ROOT / 'verification/consumption_run_001'
ACTIVATION = Path('D:/hefe/verification/fixes/20261107_nearest_contract/consumption_run_005_prepared')
sha = lambda value: hashlib.sha256(value).hexdigest()
load = lambda path: json.loads(Path(path).read_bytes())


def main():
    output = OUT / 'SOURCE_AUDIT.json'
    assert not output.exists(), 'source audit evidence must not be silently replaced'
    plan = load(RUN / 'PLAN.json')
    package = load(RUN / 'PACKAGE.json')
    expected = dict(product_commit='24bfe492c4888caf1d989ddb22f36e5752829d46',
        source_sha256='74263d8b18aec48fac21e3c3b25e26c890739c6b697503a9f6b91acf7c30c0e3',
        package_sha256='86426dc401fd3b62d19b3daacaa60e11c072fa8c3784e757fbcaddd14153bbbb',
        plan_sha256='9fc4df544ced0961b9831f0eedc42dd7f8ea9df1b5e13c74adc4d259987f7ed0',
        product_zip_sha256='9d473d31bab1f5cfcaad7592842dc9797a89613f8d2bde5f5579e1d5970b12ea')
    assert plan['source_commit'] == expected['product_commit']
    assert plan['source_sha256'] == expected['source_sha256']
    assert sha((RUN / 'PACKAGE.json').read_bytes()) == expected['package_sha256']
    assert sha((RUN / 'PLAN.json').read_bytes()) == expected['plan_sha256']
    assert sha((RUN / 'PRODUCT_BYTES.zip').read_bytes()) == expected['product_zip_sha256']
    package_checks = []
    declared = {item['path']: item for item in package['files']}
    for name in ('runner.py', 'bridge.py', 'he_bootstrap.py', 'PRODUCT_BYTES.zip', 'PLAN.json', 'PACKAGE.json', 'PREPARATION.json'):
        data = (RUN / name).read_bytes()
        expected = declared.get(name, {}).get('sha256')
        package_checks.append(dict(path=name, bytes=len(data), sha256=sha(data),
            expected_sha256=expected, declared_hash_matches=expected is None or sha(data) == expected,
            exact_activation_copy=data == (ACTIVATION / name).read_bytes()))
    component_checks = []
    for item in plan['runtime_components']:
        digest = sha((RUN / item['path']).read_bytes())
        component_checks.append(dict(path=item['path'], sha256=digest,
            expected_sha256=item['sha256'], matches=digest == item['sha256']))
    actual_manifest = []
    source_checks = []
    archive_path = RUN / 'PRODUCT_BYTES.zip'
    with zipfile.ZipFile(archive_path) as archive:
        members_match = sorted(archive.namelist()) == sorted(item['path'] for item in plan['product_manifest'])
        for item in plan['product_manifest']:
            disk_digest = sha((ROOT / item['path']).read_bytes())
            archive_digest = sha(archive.read(item['path']))
            actual_manifest.append(dict(path=item['path'], sha256=disk_digest))
            source_checks.append(dict(path=item['path'], sha256=disk_digest,
                archived_sha256=archive_digest, expected_sha256=item['sha256'],
                matches=disk_digest == archive_digest == item['sha256']))
        tree = ast.parse(archive.read('human_eye_plugin/runtime_identity.py'))
        constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION')}
    roots = next(ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == '_ROOT_MODULES')
    enumerated = set(roots)
    for package_name in ('human_eye_plugin', 'human_eye_module1_operators'):
        assert (ROOT / package_name / '__init__.py').is_file()
        enumerated.update(package_name + '/' + path.name for path in (ROOT / package_name).glob('*.py'))
    independent_source_paths_match = sorted(enumerated) == sorted(item['path'] for item in plan['product_manifest'])
    actual_manifest.sort(key=lambda row: row['path'])
    canonical = dict(base_version=constants['BASE_VERSION'],
        implementation_revision=constants['IMPLEMENTATION_REVISION'], files=actual_manifest)
    canonical_sha = sha(json.dumps(canonical, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    material = load(BASE / 'materials/MATERIAL_MANIFEST.json')
    asset_checks = []
    for task in material['tasks']:
        data = Path(task['source_asset_path']).read_bytes()
        asset_checks.append(dict(task_id=task['task_id'], source_path=task['source_asset_path'],
            bytes=len(data), sha256=sha(data), expected_sha256=task['asset_sha256'],
            matches=sha(data) == task['asset_sha256']))
    helper = material['neutral_helper']
    helper_data = (BASE / 'materials' / helper['local_path']).read_bytes()
    helper_check = dict(path=helper['local_path'], bytes=len(helper_data), sha256=sha(helper_data),
        expected_sha256=helper['sha256'], matches=sha(helper_data) == helper['sha256'])
    passed = (len(package_checks) == 7 and all(row['declared_hash_matches'] and row['exact_activation_copy'] for row in package_checks)
        and len(component_checks) == 17 and all(row['matches'] for row in component_checks)
        and len(source_checks) == 131 and all(row['matches'] for row in source_checks)
        and independent_source_paths_match and members_match and canonical_sha == plan['source_sha256']
        and all(row['matches'] for row in asset_checks) and helper_check['matches'])
    result = dict(cycle_id='CONSUMPTION-RUN-005', checked_utc=datetime.now(timezone.utc).isoformat(),
        scope='static source/package/assets/helper bytes only; no final PID audit or quality/answer interpretation',
        passed=passed, product_commit=plan['source_commit'], product_archive_path=str(archive_path), package_sha256=sha((RUN / 'PACKAGE.json').read_bytes()), plan_sha256=sha((RUN / 'PLAN.json').read_bytes()), package_checks=package_checks, component_count=len(component_checks),
        component_checks=component_checks, product_source_count=len(source_checks),
        product_source_checks=source_checks, independent_source_paths_match=independent_source_paths_match, independently_enumerated_source_count=len(enumerated), archive_members_exact=members_match, expected_fixed_identity=expected,
        product_zip_sha256=sha(archive_path.read_bytes()), product_canonical_sha256=canonical_sha,
        expected_product_canonical_sha256=plan['source_sha256'], original_asset_hashes=asset_checks,
        helper_check=helper_check, actual_product_imports=0, actual_consumers=0,
        actual_Blender=0, actual_RPC=0, final_PID_checks=0, quality_scoring_performed=False)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps(dict(passed=passed, exact_activation_files=7, component_count=len(component_checks),
        product_source_count=len(source_checks), product_canonical_sha256=canonical_sha,
        source_audit_sha256=sha(output.read_bytes()))))
    assert passed


if __name__ == '__main__':
    main()
