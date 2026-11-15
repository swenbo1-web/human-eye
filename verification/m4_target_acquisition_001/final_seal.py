"""Verify and seal the fixed A qualification and its not-realized exit."""

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = Path('D:/he_m4_target_001')
BASELINE = 'fde0e9ab21fb6eaee1750befd64ad1bebdde2961'
A_GIT = 'cbbbd2611031f3c2d469280a71bcd410fb47447a'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, label):
    if not value:
        raise AssertionError(label)


def dump(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def deliverable_files():
    return sorted(path for path in HERE.rglob('*')
                  if path.is_file() and '__pycache__' not in path.parts)


def pins(rows, root=ROOT):
    for row in rows:
        path = Path(row['path'])
        path = path if path.is_absolute() else root / path
        require(sha(path) == row['sha256'], 'changed input ' + str(path))
        if 'bytes' in row:
            require(path.stat().st_size == row['bytes'], 'changed size ' + str(path))
    return len(rows)


def jsonl(path):
    return [json.loads(row) for row in path.read_bytes().splitlines() if row.strip()]


def verify_sources():
    base = read(HERE / 'BASELINE.json')
    for path, expected in base['protected_old_pins'].items():
        require(sha(path) == expected, 'old protected input ' + path)
    binding = read(HERE / 'build_A/RUN_BINDING.json')
    require(pins(binding['source_manifest']) == 141, 'working source count')
    require(pins(binding['source_manifest'], Path(binding['install_root'])) == 141, 'installed source count')
    freeze = read(HERE / 'SOURCE_FREEZE_A.json')
    require(freeze['runtime_manifest'] == binding['source_manifest'], 'A source freeze and install')
    identity = {key: binding[key] for key in ('base_version', 'implementation_revision')}
    identity['files'] = binding['source_manifest']
    aggregate = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    require(aggregate == binding['source_sha256'] == 'b7868c46119b2f5dcb3ca426e78a2ac9bb45b51167a01d323516c7707eb81e76', 'A source aggregate')
    tree = {}
    for row in subprocess.check_output(['git', 'ls-tree', '-r', A_GIT], cwd=ROOT).decode().splitlines():
        fields, path = row.split('\t', 1)
        tree[path] = fields.split()[2]
    for row in binding['source_manifest']:
        blob = (ROOT / row['path']).read_bytes()
        digest = hashlib.sha1(b'blob ' + str(len(blob)).encode() + b'\0' + blob).hexdigest()
        require(tree[row['path']] == digest, 'A committed source ' + row['path'])
    wheel = next((HERE / 'build_A').glob('*.whl'))
    require(sha(wheel) == binding['wheel_sha256'], 'A wheel bytes')
    with zipfile.ZipFile(wheel) as container:
        for row in binding['source_manifest']:
            require(hashlib.sha256(container.read(row['path'])).hexdigest() == row['sha256'], 'A wheel source ' + row['path'])
    require(sha(HERE / 'ADMINISTRATOR_PLAN.md') == 'fd82d81865574f9c9401f82f7cfa9dd2c856f6ef3fb2ccd0cb21b9b75eaca43b', 'fixed plan')
    plan = read(HERE / 'fixtures/INPUT_PLAN.json')
    source_pins = pins(plan['source_pins'])
    assets = read(RUNTIME / 'assets_01/ASSETS.json')
    for asset in assets['inputs']:
        require(sha(asset['asset']) == asset['asset_sha256'], 'derived asset source')
        require(sha(asset['geometry']) == asset['geometry_sha256'], 'derived asset geometry')
    require(not (RUNTIME / 'B').exists() and not (HERE / 'SOURCE_FREEZE_B.json').exists(), 'B remains unrun')
    require(not (RUNTIME / 'formal').exists(), 'formal remains unrun')
    return {'A_source_files_verified_in_worktree_Git_wheel_install': 141,
            'old_protected_pins_verified': len(base['protected_old_pins']),
            'original_input_pins_verified': source_pins, 'fixed_owned_assets_verified': len(assets['inputs'])}


def verify_actual():
    slot = RUNTIME / 'qualification/A_peripheral_02'
    result = read(slot / 'RESULT.json')
    require(result['passed'] is True and not result['errors'], 'actual A completed')
    require(result['MCP_runtime_exit']['confirmed'] and result['MCP_runtime_exit']['exit_code'] == 0, 'MCP held exit')
    require(result['stdio_close']['confirmed'] and result['stdio_close']['process_handle_closed'], 'stdio held close')
    require(result['native_close']['exit_code'] == 0 and result['native_close']['process_reaped'], 'Blender held exit')
    require(read(slot / 'RUNTIME_PROOF.json')['confirmed'] is True, 'actual runtime provenance')
    capture = read(slot / 'CAPTURE_01.json')
    public = read(slot / 'PUBLIC_01.json')
    require(public['schema'] == 'active-observation-brief-v5', 'actual default projection')
    require(public['binding']['runtime_source_sha256'] == result['source_sha256'], 'actual installed product version')
    require(sum(len(mesh['vertices']) for mesh in capture['meshes']) == 3474, 'actual full vertices')
    require(sum(len(mesh['faces']) for mesh in capture['meshes']) == 6146, 'actual full triangles')
    meshes = {mesh['name']: mesh for mesh in capture['meshes']}
    target, near = meshes['M4_Far_00'], meshes['M4_Near']
    require(len(target['faces']) == 512, 'target source triangles')
    points = [tuple(Fraction(x) for x in point) for point in target['vertices']]
    require(all(point[0] == 1 for point in points), 'target plane')
    signed_area = Fraction(0)
    for face in target['faces']:
        a, b, c = [points[index] for index in face]
        normal_x = (b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1])
        require(normal_x < 0, 'target oriented -X')
        signed_area -= normal_x / 2
    require(signed_area == 1, 'target area independent sum')
    near_points = [tuple(Fraction(x) for x in point) for point in near['vertices']]
    distance = near_points[0][0]
    require(distance == Fraction(8589935, 2147483648), 'actual Near plane')
    require(all(point[0] == distance for point in near_points), 'Near planar')
    require({point[1:] for point in near_points} == {(Fraction(0), Fraction(0)), (Fraction(0), Fraction(1)), (Fraction(1), Fraction(0))}, 'Near triangle extent')
    area = distance * distance / 2
    require(area == Fraction(73786983304225, 9223372036854775808), 'independent positive occlusion area')
    events = jsonl(slot / 'audit.jsonl')
    classifications = next(row['target_view_classifications'] for row in events if 'target_view_classifications' in row)
    require(list(classifications) == ['SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK'], 'actual classification order')
    expected = dict(SCENE='back_facing', TOP='edge_on', LEFT='positive_area_occlusion', RIGHT='back_facing', FRONT='edge_on', BACK='edge_on')
    near_triangle = tuple(near_points[index] for index in near['faces'][0])
    canonical = min(near_triangle[index:] + near_triangle[:index] for index in range(3))
    triangle_hash = hashlib.sha256(json.dumps(canonical, default=str, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    for view, rows in classifications.items():
        require(len(rows) == 1, 'one target classification')
        entry = next(iter(rows.values()))
        require(entry['status'] == expected[view] and entry['complete'] is False, 'independent view classification ' + view)
        if view == 'LEFT':
            blocker = entry['first_blocker']
            require(Fraction(blocker['overlap_area_screen_exact']) == area, 'actual area equals independent oracle')
            require(blocker['triangle_geometry_id'] == triangle_hash, 'independent blocker identity')
    require(public['inspection']['counts']['covered'] == 0, 'actual no witness')
    require(public['inspection']['counts']['no_geometric_complete_candidate'] == 1, 'actual finite pool exit')
    columns = public['regions']['columns']
    target_row = dict(zip(columns, public['regions']['rows'][0]))
    require(target_row['source_triangle_index_ranges'] == [[0, 511]], 'M1 source range')
    require(target_row['status'] == 'unknown' and target_row['complete_witness_pixel_index'] is None, 'unknown remains truthful')
    proof = read(HERE / 'ACTUAL_A_PERIPHERAL_REVIEW.json')
    require(proof['passed_checked_scope'] is True, 'independent runtime quality')
    quality_pins = pins(proof['input_pins'])
    require(proof['normalizer_sha256'] == sha(HERE / 'quality_normalize.py'), 'independent final checker version')
    numeric = read(HERE / 'NUMERIC_A_01.json')
    executed = [row for row in numeric['records'] if row['executed']]
    require(len(executed) == 16 and all(row['passed'] for row in executed) and len(numeric['records']) == 37, 'A numeric pass and unrun split')
    require(numeric['host_source_sha256'] == sha(ROOT / 'human_eye_plugin/blender_host.py'), 'numeric installed source')
    interface = read(HERE / 'INTERFACE_QUALITY_02.json')
    require(interface['passed'] and len(interface['records']) == 9, 'final checker interface')
    require(interface['adapter_sha256'] == proof['normalizer_sha256'], 'interface actual checker parity')
    require(read(HERE / 'PRODUCT_A_PURE_CHECKS_R2.json')['passed'] is True, 'A pure checks')
    require(read(HERE / 'PRODUCT_A_EXISTING_PURE_CHECKS_R2.json')['success'] is True, 'existing pure checks')
    runtime_review = read(HERE / 'RUNTIME_REVIEW.json')
    require(runtime_review['passed'] is True and not runtime_review['failed_checks'], 'runtime review')
    runtime_pins = pins(runtime_review['input_pins'])
    product_review = read(HERE / 'PRODUCT_A_REVIEW.json')
    require(product_review['passed_checked_scope'] is True, 'product review')
    product_pins = pins(product_review['source_pins'])
    return {'independent_actual_quality_inputs_verified': quality_pins, 'actual_target_area': str(signed_area),
            'independent_occlusion_area': str(area), 'actual_blocker_identity': triangle_hash,
            'actual_target_supported_regions': 1, 'actual_target_complete_witnesses': 0,
            'A_numeric_passed': 16, 'B_numeric_not_run': 21, 'final_quality_interface_passed': 9,
            'runtime_review_checks': runtime_review['check_count'], 'runtime_review_inputs_verified': runtime_pins,
            'product_review_checks': len(product_review['checks']), 'product_review_inputs_verified': product_pins}


def verify_budget_archive():
    claims = [read(path) for path in (RUNTIME / 'budget/claims').glob('*.json')]
    startups = 0
    rasters = 0
    for claim in claims:
        settled = read(RUNTIME / 'budget/settlements' / (claim['token'] + '.json'))
        require(settled['claim_sha256'] == sha(RUNTIME / 'budget/claims' / (claim['token'] + '.json')), 'budget settlement source')
        if claim['kind'] == 'Blender_start':
            startups += 1
            require(settled['spawn_status'] == 'spawned' and settled['pid'], 'known owned startup')
        else:
            require(claim['phase'] == 'qualification' and settled['actual_attempts'] == 1, 'one actual qualification raster')
            rasters += settled['actual_attempts']
    require(startups == 3 and rasters == 1 and len(claims) == 4, 'all attempts retained')
    archive = read(HERE / 'RUNTIME_ARCHIVE.json')
    total = 0
    for row in archive['files']:
        require(sha(row['original_path']) == sha(HERE / row['archive_path']) == row['sha256'], 'runtime copy bytes')
        require(Path(row['original_path']).stat().st_size == row['bytes'], 'runtime copy size')
        total += row['bytes']
    require(len(archive['files']) == 272 and total == 8507203, 'closed archive denominator')
    return {'actual_owned_Blender_starts': startups, 'actual_qualification_rasters': rasters,
            'actual_formal_rasters': 0, 'runtime_archive_files_verified': len(archive['files']),
            'runtime_archive_bytes': total, 'pending_raster_reservations': 0}


def credential_scan():
    patterns = [re.compile(pattern) for pattern in (
        rb'(?<![A-Za-z0-9])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}',
        rb'gh[pousr]_[A-Za-z0-9]{30,}', rb'github_pat_[A-Za-z0-9_]{40,}',
        rb'AIza[A-Za-z0-9_-]{35}', rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    )]
    files = deliverable_files()
    findings = []
    members = 0
    private = {'auth.json', 'credentials.json', 'token.json', '.env', 'id_rsa', 'id_ed25519'}
    for path in files:
        blob = path.read_bytes()
        if path.name.lower() in private or any(rule.search(blob) for rule in patterns):
            findings.append(str(path.relative_to(ROOT)))
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    members += 1
                    member_blob = archive.read(member)
                    if Path(member.filename).name.lower() in private or any(rule.search(member_blob) for rule in patterns):
                        findings.append(str(path.relative_to(ROOT)) + '!' + member.filename)
    require(not findings, 'credential candidates ' + repr(findings))
    return {'credential_scan_files': len(files), 'credential_scan_container_members': members, 'credential_pattern_candidates': 0}


def verify_git():
    manifest = read(HERE / 'CONTENT_MANIFEST.json')
    expected = {row['path'] for row in manifest['files']} | {(HERE / 'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix()}
    actual = set(subprocess.check_output(['git', 'diff', '--name-only', '--cached', BASELINE], cwd=ROOT).decode().splitlines())
    require(actual == expected, 'exact baseline diff closure')
    index = {}
    for row in subprocess.check_output(['git', 'ls-files', '--stage'], cwd=ROOT).decode().splitlines():
        fields, path = row.split('\t', 1)
        mode, digest, stage = fields.split()
        require(stage == '0', 'unmerged index')
        index[path] = digest
    for path in expected:
        blob = (ROOT / path).read_bytes()
        require(hashlib.sha1(b'blob ' + str(len(blob)).encode() + b'\0' + blob).hexdigest() == index[path], 'Git blob parity ' + path)
    pins(manifest['files'])
    print(json.dumps({'manifest_and_staged_paths': len(expected), 'exact_Git_blob_byte_parity': True}))


def seal():
    require(not (HERE / 'FINAL_AUDIT.json').exists(), 'already sealed')
    checks = verify_sources()
    checks.update(verify_actual())
    checks.update(verify_budget_archive())
    checks.update(credential_scan())
    base = read(HERE / 'BASELINE.json')
    closed = time.perf_counter_ns()
    ledger = {'schema': 'm4-target-final-qualification-ledger-v1', 'disposition': 'not_realized',
              'A_variants': 1, 'B_variants': 0, 'formal_slots': 0, 'actual_owned_Blender_starts': 3,
              'actual_qualification_rasters': 1, 'actual_formal_rasters': 0,
              'registered_analysis_started_ns': base['started_ns'], 'audit_closed_ns': closed,
              'registered_analysis_elapsed_ns': closed - base['started_ns'],
              'scope': 'Registration through final audit, including preparation, agents and coordination. Earlier plan, AL and managed-worktree steps precede registration. Nested timings remain separate.',
              'experimental_model_tokens_and_cost': 'not_run', 'coordinator_reviewer_tokens_and_cost': None}
    dump(HERE / 'QUALIFICATION_LEDGER.json', ledger)
    files = deliverable_files()
    audit = {'schema': 'm4-target-final-root-audit-v1', 'passed_checked_scope': True,
             'disposition': 'not_realized', 'A_product_git': A_GIT, 'baseline_git': BASELINE,
             'B_status': 'not_implemented', 'formal_status': 'not_run',
             'AL_task_registration': 'pending_current_chat_host_binding', 'administrator_review': 'pending',
             'reviewer_associations_disclosed': True,
             'artifacts_sha256': {path.relative_to(HERE).as_posix(): sha(path) for path in files}, **checks}
    dump(HERE / 'FINAL_AUDIT.json', audit)
    paths = [path for path in deliverable_files() if path.name != 'CONTENT_MANIFEST.json']
    paths += [ROOT / path for path in read(HERE / 'SOURCE_FREEZE_A.json')['product_changed_paths']]
    rows = sorted([{'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
                   for path in paths], key=lambda row: row['path'])
    manifest = {'schema': 'm4-target-content-manifest-v1', 'baseline_git': BASELINE,
                'scope': 'New module deliverables and seven A product files. Manifest excludes itself and disposable __pycache__ retained locally after the platform rejected cleanup.',
                'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows), 'files': rows}
    dump(HERE / 'CONTENT_MANIFEST.json', manifest)
    print(json.dumps({'disposition': 'not_realized', **checks, 'content_files': len(rows),
                      'audit_sha256': sha(HERE / 'FINAL_AUDIT.json'), 'manifest_sha256': sha(HERE / 'CONTENT_MANIFEST.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-git', action='store_true')
    args = parser.parse_args()
    if args.verify_git:
        verify_git()
    else:
        seal()
