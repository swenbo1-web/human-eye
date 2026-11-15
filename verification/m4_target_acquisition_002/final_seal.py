"""Seal one fixed selective-acquisition candidate and its original evidence."""

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
RUNTIME = Path('D:/he_m4_target_002')
BASELINE = '4f8c41f89c9b40b3f310cf3f8e8b711bf09864a6'
CANDIDATE = 'c309d7e4302518cd5f7d1c3966e7c7fa338ea128'

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


def verify_sources():
    base = read(HERE / 'BASELINE.json')
    old_members = 0
    for path, expected in base['protected_old_pins'].items():
        require(sha(path) == expected, 'old protected evidence ' + path)
        if Path(path).name == 'CONTENT_MANIFEST.json':
            old_members += pins(read(path)['files'], Path(path).parents[2])
    for path, expected in base['references'].items():
        require(sha(path) == expected, 'original fixed reference ' + path)
        require(sha(HERE / 'reference' / Path(path).name) == expected, 'reference copy ' + path)
    require(sha(HERE / 'PREREGISTRATION.json') ==
            '5013cc3402410dab014bff5b54c2c342f2146aa7c282332fb291174af920167e', 'preregistration')
    require(sha(HERE / 'SOURCE_FREEZE_B.json') ==
            '9a23c0ae010d20e2447f0e049ff5869d15df65c3da3e374ec99fc027ef9919e4', 'B source freeze')
    a = read(HERE / 'A_RUN_BINDING.json')
    b = read(HERE / 'build_B/RUN_BINDING.json')
    require(a['source_sha256'] == base['A_source141_sha256'], 'accepted A identity')
    require(pins(a['source_manifest'], Path(a['install_root'])) == 141, 'accepted A install')
    require(b['source_sha256'] == '776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be'
            and b['preparation_git'] == CANDIDATE, 'frozen B identity')
    require(pins(b['source_manifest']) == pins(b['source_manifest'], Path(b['install_root'])) == 141, 'B worktree install')
    frozen = read(HERE / 'SOURCE_FREEZE_B.json')
    require(frozen['runtime_manifest'] == b['source_manifest']
            and frozen['product_changed_paths'] == ['human_eye_plugin/blender_host.py'], 'one product file')
    identity = {key: b[key] for key in ('base_version', 'implementation_revision')}
    identity['files'] = b['source_manifest']
    aggregate = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    require(aggregate == b['source_sha256'], 'source aggregate')
    for commit, binding in ((BASELINE, a), (CANDIDATE, b)):
        tree = {}
        for row in subprocess.check_output(['git', 'ls-tree', '-r', commit], cwd=ROOT).decode().splitlines():
            fields, path = row.split('\t', 1)
            tree[path] = fields.split()[2]
        for row in binding['source_manifest']:
            blob = (Path(binding['install_root']) / row['path']).read_bytes()
            require(tree[row['path']] == hashlib.sha1(b'blob ' + str(len(blob)).encode() + b'\0' + blob).hexdigest(), 'Git source ' + row['path'])
    wheel = next((HERE / 'build_B').glob('*.whl'))
    require(sha(wheel) == b['wheel_sha256'] ==
            'aefa75ab15aa47632ecb16f6a59af207186e2b66ced9a5baa2253ec55eb36486', 'B wheel')
    with zipfile.ZipFile(wheel) as archive:
        for row in b['source_manifest']:
            require(hashlib.sha256(archive.read(row['path'])).hexdigest() == row['sha256'], 'B wheel source')
    gate = read(HERE / 'FORMAL_GATE.json')
    pins(gate['qualification_evidence_pins'])
    for name, expected in gate['harness_sha256'].items():
        require(sha(HERE / 'harness' / name) == expected, 'frozen harness ' + name)
    intent = read(RUNTIME / 'formal/INTENT.json')
    require(intent == read(RUNTIME / 'FORMAL_ONCE.json'), 'single formal intent')
    pins(intent['harness_sources'])
    for asset in read(RUNTIME / 'assets_01/ASSETS.json')['inputs']:
        require(sha(asset['asset']) == asset['asset_sha256'], 'asset file')
        require(sha(asset['geometry']) == asset['geometry_sha256'], 'asset readback')
    return dict(A_sources_verified=141, B_sources_Git_worktree_wheel_install=141,
                protected_old_pins=len(base['protected_old_pins']), protected_old_manifest_members=old_members,
                original_reference_pins=len(base['references']), formal_harness_sources=len(intent['harness_sources']))


def verify_results():
    decision = read(HERE / 'DECISION.json')
    require(decision['decision_source_sha256'] == sha(HERE / 'cost_decision.py'), 'root decision version')
    pins(decision['input_pins'])
    checker = read(HERE / 'COST_CHECKER_REVIEW_R1.json')
    require(checker['passed_checked_scope'] and checker['reviewed_source']['sha256'] == sha(HERE / 'cost_decision.py'), 'independent grader review')
    for name in ('A_QUALIFICATION_R1.json', 'B_QUALIFICATION.json', 'B_INSTALLED_PURE.json',
                 'B_PRODUCT_SOURCE_REVIEW.json', 'LEGACY_REGRESSION_R1.json', 'CACHE_REVIEW.json',
                 'RUNTIME_REVIEW.json'):
        result = read(HERE / name)
        require(result.get('passed_checked_scope', result.get('passed')) is True, 'quality ' + name)
    require(read(RUNTIME / 'formal/RESULT.json')['retries'] == 0, 'zero retries')
    slots = read(HERE / 'PREREGISTRATION.json')['formal_schedule']
    for row in slots:
        path = RUNTIME / 'formal' / row['label'] / 'RESULT.json'
        result = read(path)
        require(result['passed'] and not result['errors'], 'closed actual slot')
        require(result['MCP_runtime_exit']['confirmed'] and result['MCP_runtime_exit']['exit_code'] == 0, 'MCP retained exit')
        require(result['native_close']['process_reaped'] and result['native_close']['exit_code'] == 0, 'Blender held exit')
    return dict(disposition=decision['disposition'], passed_frozen_gates=decision['passed_frozen_gates'],
                formal_quality_passed=decision['quality_passed'], formal_slots=len(slots),
                formal_repetitions=1, replacement_samples=0,
                main_business_ratio=decision['gates']['main']['business_ratio_median'],
                main_session_ratio=decision['gates']['main']['session_ratio_median'],
                control_business_ratio=decision['gates']['target_only']['business_ratio_median'])


def verify_budget_archive():
    starts = qualification = formal = 0
    claims = list((RUNTIME / 'budget/claims').glob('*.json'))
    for path in claims:
        claim = read(path)
        settled = read(RUNTIME / 'budget/settlements' / (claim['token'] + '.json'))
        require(settled['claim_sha256'] == sha(path), 'budget source')
        if claim['kind'] == 'Blender_start':
            starts += 1
            require(settled['spawn_status'] == 'spawned' and settled['pid'], 'known owned start')
        else:
            require(type(settled['actual_attempts']) is int, 'settled raster attempt')
            if claim['phase'] == 'qualification':
                qualification += settled['actual_attempts']
            else:
                formal += settled['actual_attempts']
    require(starts == 19 and qualification == 10 and formal == 18 and len(claims) == 39, 'all actual attempts')
    archive = read(HERE / 'RUNTIME_ARCHIVE.json')
    for row in archive['files']:
        require(sha(row['original_path']) == sha(HERE / row['archive_path']) == row['sha256'], 'archive original bytes')
        require(Path(row['original_path']).stat().st_size == row['bytes'], 'archive original size')
    return dict(owned_Blender_starts=starts, qualification_rasters=qualification, formal_rasters=formal,
                total_rasters=qualification + formal, pending_reservations=0,
                runtime_archive_files=archive['file_count'], runtime_archive_bytes=archive['bytes'],
                experimental_models=0, paid_experiment_APIs=0)


def seal():
    require(not (HERE / 'FINAL_AUDIT.json').exists(), 'already sealed')
    checks = verify_sources()
    checks.update(verify_results())
    checks.update(verify_budget_archive())
    checks.update(credential_scan())
    base = read(HERE / 'BASELINE.json')
    closed = time.perf_counter_ns()
    dump(HERE / 'QUALIFICATION_LEDGER.json', dict(schema='m4-target-acquisition-002-ledger-v1',
         started_ns=base['started_ns'], audit_closed_ns=closed,
         registered_analysis_elapsed_ns=closed - base['started_ns'],
         scope='Registration through sealing including agents, preparation, qualification, fixed formal and saved-only reviews. Earlier plan/AL/worktree setup precede registration. Nested stages remain separate.',
         B_candidate_directions=1, formal_repetitions=1, retries=0, replacement_samples=0,
         experimental_models=0, experimental_paid_APIs=0, coordinator_reviewer_cost=None,
         limits=base['limits']))
    dump(HERE / 'FINAL_AUDIT.json', dict(schema='m4-target-acquisition-002-root-audit-v1',
         passed_checked_scope=True, baseline_git=BASELINE, B_product_git=CANDIDATE,
         administrator_review='pending', AL_task_registration='pending_current_chat_host_binding',
         reviewer_associations_disclosed=True, old_A01_runtime_exit='unknown_preserved',
         old_cleanup_policy_rejection='preserved_without_bypass',
         artifacts_sha256={path.relative_to(HERE).as_posix(): sha(path) for path in deliverable_files()}, **checks))
    paths = [path for path in deliverable_files() if path.name != 'CONTENT_MANIFEST.json']
    paths += [ROOT / path for path in read(HERE / 'SOURCE_FREEZE_B.json')['product_changed_paths']]
    rows = sorted([dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=sha(path))
                   for path in paths], key=lambda row: row['path'])
    dump(HERE / 'CONTENT_MANIFEST.json', dict(schema='m4-target-acquisition-002-content-manifest-v1',
         baseline_git=BASELINE, scope='New batch namespace and one B product file. Self and disposable __pycache__ excluded.',
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
