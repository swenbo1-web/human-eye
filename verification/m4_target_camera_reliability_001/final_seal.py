"""Seal one camera-reliability candidate and its bounded qualification."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = Path('D:/he_m4_camera_001')
BASELINE = '03eb4e2971891dfe0160972cbcf974e3dcf1a21c'
CANDIDATE = '691f7b78ed89ccf30df47847fc1e99ad51a1dc64'
SLOTS = ('OLD_extreme', 'NEW_extreme', 'OLD_origin', 'NEW_origin',
         'OLD_peripheral', 'NEW_peripheral')


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


def pins(rows, root=ROOT):
    for row in rows:
        path = Path(row['path'])
        path = path if path.is_absolute() else root / path
        require(sha(path) == row['sha256'], 'changed bytes ' + str(path))
        if 'bytes' in row:
            require(path.stat().st_size == row['bytes'], 'changed size ' + str(path))
    return len(rows)


def deliverable_files():
    return sorted(path for path in HERE.rglob('*')
                  if path.is_file() and '__pycache__' not in path.parts)


def verify_sources():
    base = read(HERE / 'BASELINE.json')
    old_manifest_entries = 0
    for path, expected in base['protected_old_pins'].items():
        require(sha(path) == expected, 'protected old evidence ' + path)
        if Path(path).name == 'CONTENT_MANIFEST.json':
            old_manifest_entries += pins(read(path)['files'], Path(path).parents[2])
    for path, expected in base['original_reference_pins'].items():
        require(sha(path) == expected, 'original reference ' + path)
    require(sha(HERE / 'M4_TARGET_CAMERA_RELIABILITY_001_PLAN.md') == base['plan_sha256'], 'plan pin')
    require(sha(HERE / 'INPUTS.json') == 'c10f7231091db360bf1fdb962ad916fba731df7cd94dfa3c5f5ff88e6cff4004', 'fixed inputs')
    freeze = read(HERE / 'INPUT_FREEZE.json')
    require(freeze['production_still_identical_to_baseline'] is True, 'inputs frozen before edits')
    pins(freeze['numeric_source_pins'])
    require(sha(HERE / 'OLD_REPRO.json') == freeze['old_repro_sha256'], 'original reproduction')
    require(sha(HERE / 'SOURCE_FREEZE.json') == 'bad3ad09e7614af541e8b95ba0c16eb498c6729f21af4c49d31993ca45094948', 'candidate freeze')
    binding = read(HERE / 'build/RUN_BINDING.json')
    require(binding['preparation_git'] == CANDIDATE, 'candidate Git binding')
    require(pins(binding['source_manifest']) == 141, 'working source count')
    require(pins(binding['source_manifest'], Path(binding['install_root'])) == 141, 'installed source count')
    require(read(HERE / 'SOURCE_FREEZE.json')['runtime_manifest'] == binding['source_manifest'], 'freeze install parity')
    identity = {key: binding[key] for key in ('base_version', 'implementation_revision')}
    identity['files'] = binding['source_manifest']
    aggregate = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    require(aggregate == binding['source_sha256'] == '9f2c5ca150f968841b64f4d4eda89313069453853c877ba21b6a262999e29a61', 'source aggregate')
    tree = {}
    for row in subprocess.check_output(['git', 'ls-tree', '-r', CANDIDATE], cwd=ROOT).decode().splitlines():
        fields, path = row.split('\t', 1)
        tree[path] = fields.split()[2]
    for row in binding['source_manifest']:
        blob = (ROOT / row['path']).read_bytes()
        require(tree[row['path']] == hashlib.sha1(b'blob ' + str(len(blob)).encode() + b'\0' + blob).hexdigest(), 'committed source ' + row['path'])
    wheel = next((HERE / 'build').glob('*.whl'))
    require(sha(wheel) == binding['wheel_sha256'], 'wheel bytes')
    with zipfile.ZipFile(wheel) as container:
        for row in binding['source_manifest']:
            require(hashlib.sha256(container.read(row['path'])).hexdigest() == row['sha256'], 'wheel source ' + row['path'])
    old = read(ROOT / 'verification/m4_target_acquisition_001/build_A/RUN_BINDING.json')
    require(pins(old['source_manifest'], Path(old['install_root'])) == 141, 'old install unchanged')
    require(pins(read(HERE / 'fixtures/INPUT_PLAN.json')['source_pins']) > 0, 'fixture source pins')
    assets = read(RUNTIME / 'assets_01/ASSETS.json')
    for asset in assets['inputs']:
        require(sha(asset['asset']) == asset['asset_sha256'], 'asset bytes')
        require(sha(asset['geometry']) == asset['geometry_sha256'], 'asset geometry bytes')
    return dict(candidate_sources_Git_wheel_worktree_install=141, old_install_sources=141,
                protected_old_pins=len(base['protected_old_pins']), old_manifest_entries=old_manifest_entries,
                original_reference_pins=len(base['original_reference_pins']), fixed_assets=len(assets['inputs']))


def verify_qualification():
    results = {}
    for name in SLOTS:
        folder = RUNTIME / 'controls' / name
        result = read(folder / 'RESULT.json')
        require(result['passed'] is True and not result['errors'], 'control errors ' + name)
        require(result['MCP_runtime_exit']['confirmed'] and result['MCP_runtime_exit']['exit_code'] == 0, 'MCP held exit ' + name)
        require(result['stdio_close']['confirmed'] and result['stdio_close']['process_handle_closed'], 'stdio held close ' + name)
        require(result['native_close']['exit_code'] == 0 and result['native_close']['process_reaped'], 'Blender held exit ' + name)
        require(read(folder / 'RUNTIME_PROOF.json')['confirmed'] is True, 'runtime provenance ' + name)
        results[name] = read(folder / 'PUBLIC_01.json')
    extreme = results['NEW_extreme']
    require(extreme['status'] == 'unknown' and extreme['reason'] == 'active_observation_target_camera_numeric_insufficient', 'explicit numeric unknown')
    require(extreme['observation_status'] == 'numeric_insufficient' and extreme['automatic_retry'] is False, 'numeric unknown semantics')
    require(all(key not in extreme for key in ('facts', 'frames', 'binding', 'result_kind')), 'no fabricated primary capture')
    for variant in ('OLD', 'NEW'):
        origin = results[variant + '_origin']
        peripheral = results[variant + '_peripheral']
        require(origin['facts']['inspection']['counts']['covered'] == 1 and len(origin['frames']) == 2, 'origin witness ' + variant)
        require(peripheral['facts']['inspection']['counts']['covered'] == 0, 'peripheral unknown ' + variant)
        require(next(iter(peripheral['target_view_classifications']['LEFT'].values()))['status'] == 'positive_area_occlusion', 'real occlusion ' + variant)
    require(next(iter(results['OLD_extreme']['target_view_classifications']['LEFT'].values()))['status'] == 'outside_frustum', 'old failure reproduced')
    for asset in ('origin', 'peripheral'):
        old_frames = results['OLD_' + asset]['frames']
        new_frames = results['NEW_' + asset]['frames']
        require([(row['frame_identity'], row['arrays_sha256']) for row in old_frames] ==
                [(row['frame_identity'], row['arrays_sha256']) for row in new_frames], 'old new producer parity ' + asset)
    for name in ('CANDIDATE_NUMERIC_SOURCE_01.json', 'CANDIDATE_NUMERIC_INSTALLED_01.json'):
        result = read(HERE / name)
        require(result['passed'] and result['case_count'] == 6, 'six numeric inputs ' + name)
    replay = read(HERE / 'PRIOR_384_REPLAY_01.json')
    require(replay['passed_checked_scope'] and replay['case_count'] == 384, 'frozen grid replay')
    require(replay['counts']['new'] == dict(accepted=273, accepted_exact_xy_clipped=0,
            accepted_execution_xyz_unreliable=0, numeric_insufficient=111, unexpected_error=0), 'grid dispositions')
    require(sha(HERE / 'MICRO_CAMERA_01.json') == '0f31024b15eefe84f9374e2244ed01237ae7222b77482a700d0a2517f5a4e8b2', 'single frozen micro')
    for name in ('TARGET_PUBLIC_PURE.json', 'CACHE_SOURCE_PREDICTION_PURE.json'):
        require(read(HERE / name)['passed'] is True, 'pure ' + name)
    require(read(HERE / 'LEGACY_FULL_PURE.json')['success'] is True, 'legacy pure')
    installed = read(HERE / 'INSTALLED_PURE_R1.json')
    require(installed['passed_checked_scope'] is True
            and installed['source_installation_parity_count'] == 141, 'isolated installed pure R1')
    for name in ('ACTUAL_CAMERA_REVIEW.json', 'FINAL_PRODUCT_REVIEW.json', 'RUNTIME_REVIEW.json'):
        report = read(HERE / name)
        require(report.get('passed_checked_scope', report.get('passed')) is True, 'independent review ' + name)
    frames = read(HERE / 'FRAME_IDENTITY_REVIEW.json')
    require(frames['passed_checked_scope'] and frames['frame_count'] == 7
            and frames['actual_review_sha256'] == sha(HERE / 'ACTUAL_CAMERA_REVIEW.json'), 'producer identity chain')
    return dict(closed_actual_controls=6, origin_complete_witnesses_old_new=[1, 1],
                extreme_capability_restored=False, extreme_numeric_unknown=True,
                peripheral_covered_old_new=[0, 0], frozen_grid_reliable_fit=273,
                frozen_grid_numeric_unknown=111, accepted_exact_xy_clipped=0,
                pure_source_cases=6, pure_install_cases=6)


def verify_archive_budget():
    starts = rasters = 0
    claims = list((RUNTIME / 'budget/claims').glob('*.json'))
    for path in claims:
        claim = read(path)
        settled = read(RUNTIME / 'budget/settlements' / (claim['token'] + '.json'))
        require(settled['claim_sha256'] == sha(path), 'settlement pin')
        if claim['kind'] == 'Blender_start':
            starts += 1
            require(settled['spawn_status'] == 'spawned' and settled['pid'], 'known owned startup')
        else:
            require(claim['phase'] == 'qualification' and settled['actual_attempts'] is not None, 'settled raster')
            rasters += settled['actual_attempts']
    require(starts == 7 and rasters == 7 and len(claims) == 13, 'all attempts accounted')
    archive = read(HERE / 'RUNTIME_ARCHIVE.json')
    for row in archive['files']:
        require(sha(row['original_path']) == sha(HERE / row['archive_path']) == row['sha256'], 'archive byte parity')
        require(Path(row['original_path']).stat().st_size == row['bytes'], 'archive size')
    return dict(owned_Blender_starts=starts, raster_attempts=rasters, formal_rasters=0,
                pending_raster_reservations=0, experimental_model_calls=0, paid_experiment_calls=0,
                runtime_archive_files=archive['file_count'], runtime_archive_bytes=archive['bytes'])


def credential_scan():
    patterns = [re.compile(pattern) for pattern in (
        rb'(?<![A-Za-z0-9])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}',
        rb'gh[pousr]_[A-Za-z0-9]{30,}', rb'github_pat_[A-Za-z0-9_]{40,}',
        rb'AIza[A-Za-z0-9_-]{35}', rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    )]
    findings = []
    members = 0
    private = {'auth.json', 'credentials.json', 'token.json', '.env', 'id_rsa', 'id_ed25519'}
    files = deliverable_files()
    for path in files:
        blob = path.read_bytes()
        if path.name.lower() in private or any(rule.search(blob) for rule in patterns):
            findings.append(str(path.relative_to(ROOT)))
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    members += 1
                    if (Path(member.filename).name.lower() in private
                            or any(rule.search(archive.read(member)) for rule in patterns)):
                        findings.append(str(path.relative_to(ROOT)) + '!' + member.filename)
    require(not findings, 'credential candidates ' + repr(findings))
    return dict(credential_scan_files=len(files), credential_scan_container_members=members,
                credential_pattern_candidates=0)


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
    print(json.dumps(dict(manifest_and_staged_paths=len(expected), exact_Git_blob_byte_parity=True)))


def seal():
    require(not (HERE / 'FINAL_AUDIT.json').exists(), 'already sealed')
    checks = verify_sources()
    checks.update(verify_qualification())
    checks.update(verify_archive_budget())
    checks.update(credential_scan())
    base = read(HERE / 'BASELINE.json')
    closed = time.perf_counter_ns()
    dump(HERE / 'QUALIFICATION_LEDGER.json', dict(schema='m4-target-camera-ledger-v1',
         disposition='bounded_reliability_repair_ready_for_review', candidate_count=1,
         budget_starts=10, actual_starts=7, budget_rasters=36, actual_rasters=7,
         formal_slots=0, experimental_model_calls=0, experimental_paid_API_calls=0,
         registered_analysis_started_ns=base['started_ns'], audit_closed_ns=closed,
         registered_analysis_elapsed_ns=closed - base['started_ns'],
         scope='Registration through sealing, including agents, preparation, coordination and original controls. Nested stages remain separate.',
         coordinator_reviewer_tokens_and_cost=None))
    dump(HERE / 'FINAL_AUDIT.json', dict(schema='m4-target-camera-root-audit-v1',
         passed_checked_scope=True, baseline_git=BASELINE, candidate_git=CANDIDATE,
         disposition='bounded_reliability_repair_ready_for_review', administrator_review='pending',
         AL_task_registration='pending_current_chat_host_binding', reviewer_associations_disclosed=True,
         old_A01_runtime_exit='unknown_preserved', old_cleanup_policy_rejection='preserved_no_bypass',
         artifacts_sha256={path.relative_to(HERE).as_posix(): sha(path) for path in deliverable_files()}, **checks))
    paths = [path for path in deliverable_files() if path.name != 'CONTENT_MANIFEST.json']
    paths += [ROOT / path for path in read(HERE / 'SOURCE_FREEZE.json')['product_changed_paths']]
    rows = sorted([dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=sha(path))
                   for path in paths], key=lambda row: row['path'])
    dump(HERE / 'CONTENT_MANIFEST.json', dict(schema='m4-target-camera-content-manifest-v1',
         baseline_git=BASELINE, scope='New batch namespace plus two product files. Manifest excludes itself and disposable local __pycache__.',
         file_count=len(rows), bytes=sum(row['bytes'] for row in rows), files=rows))
    print(json.dumps(dict(content_files=len(rows), audit_sha256=sha(HERE / 'FINAL_AUDIT.json'),
                         manifest_sha256=sha(HERE / 'CONTENT_MANIFEST.json'), **checks)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-git', action='store_true')
    args = parser.parse_args()
    if args.verify_git:
        verify_git()
    else:
        seal()
