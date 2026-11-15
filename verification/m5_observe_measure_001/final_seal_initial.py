"""Seal saved M5 evidence and all six changed product sources without new runs."""

import argparse
from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = Path('D:/he_m5_observe_measure_001').resolve()
BASELINE = 'bc177d231329dac630b4d02a161076b2b9fb50e3'
INITIAL_GIT = '162b523cc727df0d6b975415508296693f6c2cd4'
FINAL_GIT = 'ccb608aa83de4b0e6671da89e0c8f387bd3f800e'
FORMAL_GIT = '31124af898a35dee84504d3101003629bd185ec1'
MAIN_ORDER = ['A1', 'B1', 'B2', 'A2', 'A3', 'B3']
ORDER = MAIN_ORDER + ['A_task_only', 'B_task_only']
QUALIFICATIONS = ['A_qual', 'B_initial_qual', 'B_qual', 'B_state']
PRODUCT_PATHS = {
    'human_eye_plugin/active_observation_host.py', 'human_eye_plugin/auto_router.py',
    'human_eye_plugin/live_service.py', 'human_eye_plugin/live_spatial_mcp.py',
    'human_eye_plugin/query_policy.py', 'human_eye_plugin/task_query.py',
}
FIXED = {
    'BASELINE.json': 'ad3ce09d90ad17fc79dc69654cc4c8dc83601f2280692c9845896e5e01f21959',
    'PLAN.json': '85fd66431d91f36d43c2d6a785e377831469deec8ea93363ebd23058d98f0159',
    'REQUESTS.json': 'ef3ceb0e51a5b6ab1bf902c4d5d3cae92649eae519883feafabde832e2995573',
    'STATE_REQUESTS.json': 'e3c5e4fb9b21611fdb513e840a05aef4601dd82fad48c3679de4dead3d766a31',
    'SOURCE_FREEZE_INITIAL.json': '4a1c67ea60a96b4d1cd411a0361b54c42a16f1ca4b71f4b2522da763eae2f019',
    'SOURCE_FREEZE_FINAL.json': '930da22072355565f5c3f311e82d8d3fa7759e4cf8c9211cdc5d46c478539553',
    'FORMAL_FROZEN.json': '93599e66714e1f8d04f070189ea007b9378a8e80cb7e0504a8765339df2f168a',
    'FORMAL_GATE.json': '4669ae9a1fea5a2b3f3fb1c44d287f368461d7e4de9530b94495fb5998150476',
    'A_RUN_BINDING.json': '2f1a8499a0ad92679c2bd5e8857b75484a5024bf7bce56c7c8d8cee7dbc594b8',
    'build_initial/RUN_BINDING.json': '0fc6eb8c980768c703692976149ca06f93bfacb1c81278b42105d83687bb92da',
    'build_final/RUN_BINDING.json': 'bf799a44ee5f035649d4900a1c20c81213eefd8095d4f0298fd5f1588a4a6cfa',
}
VERSIONS = {
    'A': ('A_RUN_BINDING.json', 'c309d7e4302518cd5f7d1c3966e7c7fa338ea128',
          '776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be',
          'D:/he_m4_target_002/B/product', HERE.parent / 'm4_target_acquisition_002/build_B'),
    'B_initial': ('build_initial/RUN_BINDING.json', INITIAL_GIT,
                  '95e61fa0b44b94b6edfb55e22359bd5d7e748b32bcb7168c3611cf8c7311a311',
                  'D:/he_m5_observe_measure_001/B_initial/product', HERE / 'build_initial'),
    'B': ('build_final/RUN_BINDING.json', FINAL_GIT,
          '7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a',
          'D:/he_m5_observe_measure_001/B/product', HERE / 'build_final'),
}


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def require(value, label):
    if not value:
        raise AssertionError(label)


def dump(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def pins(rows, root=ROOT):
    seen = set()
    for row in rows:
        path = Path(row['path'])
        path = path if path.is_absolute() else root / path
        key = str(path.resolve())
        require(key not in seen, 'duplicate source pin ' + key)
        seen.add(key)
        require(sha(path) == row['sha256'], 'changed source pin ' + key)
        if 'bytes' in row:
            require(path.stat().st_size == row['bytes'], 'changed source size ' + key)
    return len(seen)


def mapping_pins(mapping, root=ROOT):
    return pins([{'path': name, 'sha256': digest} for name, digest in mapping.items()], root)


def files_under(directory, *, namespace=False):
    directory = Path(directory).resolve()
    paths = []
    for current, names, files in os.walk(directory, topdown=True, followlinks=False):
        for name in names + files:
            path = Path(current) / name
            require(not path.is_symlink() and not path.is_junction(), 'unexpected reparse entry')
            path.resolve().relative_to(directory)
        if namespace:
            names[:] = [name for name in names if name != '__pycache__']
        paths.extend(Path(current) / name for name in files)
    return sorted(paths)


def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=ROOT)


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def git_snapshot(commit, paths):
    content = git('archive', commit, '--', *paths)
    with tarfile.open(fileobj=io.BytesIO(content)) as archive:
        return {member.name: archive.extractfile(member).read()
                for member in archive.getmembers() if member.isfile()}


def verify_version(label):
    binding_name, commit, digest, install_name, wheel_folder = VERSIONS[label]
    binding = read(HERE / binding_name)
    require(binding['preparation_git'] == commit and binding['source_sha256'] == digest
            and binding['build_id'] == 'sha256:' + digest
            and Path(binding['install_root']).resolve() == Path(install_name).resolve(),
            'fixed version binding ' + label)
    manifest = binding['source_manifest']
    names = [row['path'] for row in manifest]
    require(len(names) == len(set(names)) == 141, 'exact 141 source names ' + label)
    identity = {name: binding[name] for name in ('base_version', 'implementation_revision')}
    identity['files'] = manifest
    aggregate = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True).encode()).hexdigest()
    require(aggregate == digest, 'version source aggregate ' + label)
    historical = git_snapshot(commit, names)
    require(set(historical) == set(names), 'exact historical source set ' + label)
    for row in manifest:
        require(hashlib.sha256(historical[row['path']]).hexdigest() == row['sha256'],
                'historical source bytes ' + label + '/' + row['path'])
    pins(manifest, Path(install_name))
    if label == 'A':
        baseline = git_snapshot(BASELINE, names)
        require(baseline == historical, 'A historical sources at delivery baseline')
    if label == 'B':
        pins(manifest)
    wheels = list(wheel_folder.glob('*.whl'))
    require(len(wheels) == 1 and sha(wheels[0]) == binding['wheel_sha256'], 'fixed wheel ' + label)
    with zipfile.ZipFile(wheels[0]) as wheel:
        for row in manifest:
            require(hashlib.sha256(wheel.read(row['path'])).hexdigest() == row['sha256'],
                    'wheel source member ' + label + '/' + row['path'])
    if label != 'A':
        phase = 'INITIAL' if label == 'B_initial' else 'FINAL'
        freeze_name = 'SOURCE_FREEZE_' + phase + '.json'
        frozen = read(HERE / freeze_name)
        require(binding['source_freeze_sha256'] == FIXED[freeze_name]
                and frozen['runtime_manifest'] == manifest and frozen['phase'] == phase.lower()
                and frozen['plan_sha256'] == FIXED['PLAN.json']
                and frozen['requests_sha256'] == FIXED['REQUESTS.json']
                and frozen['state_requests_sha256'] == FIXED['STATE_REQUESTS.json'],
                'historical freeze/binding ' + label)
        pins([frozen['A_qualification']])
        require(frozen['source_enumerator']['sha256'] ==
                next(row['sha256'] for row in manifest if row['path'] == frozen['source_enumerator']['path']),
                'frozen source enumerator ' + label)
        name = (HERE / freeze_name).relative_to(ROOT).as_posix()
        require(git_snapshot(commit, [name])[name] == (HERE / freeze_name).read_bytes(),
                'historical freeze document ' + label)
    return {'label': label, 'source141_sha256': digest, 'source_git': commit,
            'source_files': 141, 'binding_sha256': sha(HERE / binding_name),
            'wheel_sha256': binding['wheel_sha256'], 'install_root': install_name,
            'worktree_current_required': label == 'B'}


def verify_sources():
    for name, digest in FIXED.items():
        require(sha(HERE / name) == digest, 'original registration changed ' + name)
    baseline = read(HERE / 'BASELINE.json')
    require(baseline['baseline_git'] == BASELINE and baseline['optimization_attempts'] == 1
            and baseline['outer_retries'] == baseline['replacement_samples'] == 0,
            'registered baseline identity')
    require(len(baseline['protected_old_pins']) == 26, 'exact protected old pins')
    old_members = 0
    for name, digest in baseline['protected_old_pins'].items():
        require(sha(name) == digest, 'protected old evidence changed ' + name)
        if Path(name).name == 'CONTENT_MANIFEST.json':
            old_members += pins(read(name)['files'], Path(name).parents[2])
    for name, digest in baseline['references'].items():
        require(sha(name) == digest and sha(HERE / 'reference' / Path(name).name) == digest,
                'original reference changed')
    versions = [verify_version(label) for label in ('A', 'B_initial', 'B')]
    original = {row['path']: row['sha256'] for row in read(HERE / 'A_RUN_BINDING.json')['source_manifest']}
    initial = read(HERE / 'SOURCE_FREEZE_INITIAL.json')
    final = read(HERE / 'SOURCE_FREEZE_FINAL.json')
    for frozen in (initial, final):
        changed = {row['path'] for row in frozen['runtime_manifest'] if original[row['path']] != row['sha256']}
        require(changed == set(frozen['product_changed_paths']), 'historical changed source list')
    require(set(final['product_changed_paths']) == PRODUCT_PATHS
            and set(initial['product_changed_paths']) == PRODUCT_PATHS - {'human_eye_plugin/active_observation_host.py'},
            'five-source V1 and six-source final contracts')
    registration = read(HERE / 'OPTIMIZATION_REGISTRATION.json')
    initial_manifest = {row['path']: row['sha256'] for row in initial['runtime_manifest']}
    for row in registration['initial_pins']:
        snapshot = ROOT / row['snapshot']
        require(sha(snapshot) == row['sha256'] == initial_manifest[row['path']]
                and snapshot.stat().st_size == row['bytes'], 'retained initial optimization source')
    frozen = read(HERE / 'FORMAL_FROZEN.json')
    require(frozen['candidate_git'] == FINAL_GIT and frozen['product_source141_sha256'] == VERSIONS['B'][2]
            and pins(frozen['files']) == 205, 'formal frozen 205 pins')
    gate = read(HERE / 'FORMAL_GATE.json')
    require(gate['formal_freeze_sha256'] == FIXED['FORMAL_FROZEN.json']
            and gate['formal_order'] == MAIN_ORDER and gate['task_only_controls'] == ORDER[6:], 'formal gate contract')
    pins(gate['harness_pins'])
    pins(gate['qualification_pins'])
    prefix = HERE.relative_to(ROOT).as_posix()
    history = git_snapshot(FORMAL_GIT, [prefix + '/FORMAL_FROZEN.json', prefix + '/FORMAL_GATE.json'])
    for name in ('FORMAL_FROZEN.json', 'FORMAL_GATE.json'):
        require(history[prefix + '/' + name] == (HERE / name).read_bytes(), 'preformal Git document ' + name)
    changed = [name.decode('utf-8') for name in git('diff', '--name-only', '-z', BASELINE).split(b'\0') if name]
    untracked = [name.decode('utf-8') for name in git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if name]
    require(all(name.startswith(prefix + '/') or name in PRODUCT_PATHS for name in changed + untracked),
            'changes outside new namespace and six product sources')
    require({name for name in changed if not name.startswith(prefix + '/')} == PRODUCT_PATHS,
            'exact final product diff')
    return {'protected_old_pins': 26, 'protected_old_manifest_members': old_members,
            'original_reference_pins': len(baseline['references']), 'source_versions': versions,
            'initial_source_snapshot_count': len(registration['initial_pins']),
            'formal_source_pins': 205, 'product_diff_paths': sorted(PRODUCT_PATHS)}


def verify_results():
    quality = read(HERE / 'QUALITY.json')
    require(quality['schema'] == 'm5-formal-independent-quality-v1'
            and quality['main_denominator'] == 6 and quality['task_only_denominator'] == 2
            and [row['label'] for row in quality['slots']] == ORDER
            and len(quality['paired_quality_comparisons']) == 3
            and type(quality['passed_checked_scope']) is bool, 'fixed quality denominator and rows')
    require(sha(HERE / 'QUALITY.json') == sha(HERE / 'FORMAL_QUALITY.json'), 'original quality report bytes')
    pins(quality['input_pins'])
    pins(quality['checker_pins'])
    seal = read(HERE / 'QUALITY_SEAL.json')
    require(seal['quality_sha256'] == sha(HERE / 'QUALITY.json') and seal['cost_unlocked'] is True
            and type(seal['sealed_ns']) is int, 'quality-first seal')
    decision = read(HERE / 'DECISION.json')
    require(decision['schema'] == 'm5-observe-measure-decision-v1'
            and decision['quality_sha256'] == sha(HERE / 'QUALITY.json')
            and decision['quality_seal_sha256'] == sha(HERE / 'QUALITY_SEAL.json')
            and decision['decision_source_sha256'] == sha(HERE / 'cost_decision.py')
            and [row['label'] for row in decision['rows']] == ORDER and len(decision['pairs']) == 3
            and type(decision['passed_frozen_gates']) is bool, 'decision provenance and fixed rows')
    pins(decision['input_pins'])
    checker = read(HERE / 'COST_CHECKER_REVIEW.json')
    require(checker['passed_checked_scope'] is True
            and Path(checker['reviewed_source']['path']).resolve() == (HERE / 'cost_decision.py').resolve()
            and checker['reviewed_source']['sha256'] == decision['decision_source_sha256'], 'cost checker source binding')
    for name, schema in (('RUNTIME_REVIEW.json', 'm5-complete-runtime-review-v1'),
                         ('RUNTIME_COST_CROSSCHECK.json', 'm5-runtime-cost-crosscheck-v1')):
        review = read(HERE / name)
        require(review['schema'] == schema and review['passed_checked_scope'] is True
                and review['qualification_only'] is False, 'complete technical scope ' + name)
        pins(review['input_pins'])
    review = read(HERE / 'RUNTIME_REVIEW.json')
    require(review['actual_slot_count'] == 12 and review['budget']['counts']['starts'] == 12
            and review['budget']['model_consumers'] == review['budget']['paid_API_calls'] == 0,
            'twelve owned slots and zero model/API scope')
    require((HERE / 'REPORT.md').is_file(), 'root final report')
    intent = read(RUNTIME / 'FORMAL_ONCE.json')
    run = read(RUNTIME / 'formal/RUN_RESULT.json')
    require(intent == read(RUNTIME / 'formal/INTENT.json') and intent['schema'] == 'm5-formal-once-v1'
            and intent['gate_sha256'] == FIXED['FORMAL_GATE.json']
            and intent['main_order'] == MAIN_ORDER and intent['task_only_controls'] == ORDER[6:]
            and intent['formal_samples'] == 6 and intent['task_only_samples'] == 2
            and intent['retries'] == intent['replacement_samples'] == intent['model_consumers'] == intent['paid_API_calls'] == 0,
            'one fixed original formal intent')
    require(run['schema'] == 'm5-formal-dispatch-result-v1' and run['all_eight_transport_closed'] is True
            and [row['label'] for row in run['records']] == ORDER and run['dispatched'] == run['completed_records'] == 8
            and run['not_run'] == [] and run['blocker'] is None
            and run['retries'] == run['replacement_samples'] == 0, 'one complete eight-slot batch')
    originals = []
    for label in QUALIFICATIONS + ORDER:
        phase = 'formal' if label in ORDER else 'qualification'
        folder = RUNTIME / ('control' if label == 'B_state' else phase) / label
        result_path, publication_path = folder / 'RESULT.json', folder / 'PUBLICATION.json'
        result, publication = read(result_path), read(publication_path)
        variant = 'A' if label.startswith('A') else 'B_initial' if label == 'B_initial_qual' else 'B'
        require(result['label'] == label and result['phase'] == phase
                and result['source_sha256'] == VERSIONS[variant][2]
                and publication['result_sha256'] == sha(result_path)
                and publication['passed_transport_scope'] is True
                and result['model_calls'] == result['paid_API_calls'] == 0,
                'original current owned result ' + label)
        originals.append({'label': label, 'RESULT_sha256': sha(result_path),
                          'PUBLICATION_sha256': sha(publication_path), 'source_sha256': result['source_sha256']})
    return {'actual_owned_slots': 12, 'formal_main_denominator': 6, 'formal_task_only_denominator': 2,
            'quality_passed_checked_scope': quality['passed_checked_scope'], 'main_quality_passed': quality['main_passed'],
            'task_only_quality_passed': quality['task_only_passed'], 'passed_frozen_business_gates': decision['passed_frozen_gates'],
            'disposition': decision['disposition'], 'original_owned_results': originals,
            'formal_attempts': 1, 'outer_retries': 0, 'replacement_samples': 0, 'model_consumers': 0, 'paid_API_calls': 0}


def verify_budget_archive():
    budget = RUNTIME / 'budget'
    require(read(budget / 'LIMITS.json') == {'Blender_start_attempts': 12, 'qualification_rasters': 36,
            'formal_rasters': 36, 'all_rasters': 72}, 'frozen budget limits')
    claim_paths = sorted((budget / 'claims').glob('*.json'))
    claims = [read(path) for path in claim_paths]
    require(len({row['token'] for row in claims}) == len(claims), 'unique budget tokens')
    require({path.stem for path in (budget / 'settlements').glob('*.json')} == {row['token'] for row in claims},
            'exact settled claims')
    starts, rasters, start_labels = Counter(), Counter(), Counter()
    failed_rasters = 0
    for path, claim in zip(claim_paths, claims):
        require(path.stem == claim['token'] and claim['label'] in QUALIFICATIONS + ORDER
                and claim['phase'] == ('formal' if claim['label'] in ORDER else 'qualification'), 'budget source identity')
        settled = read(budget / 'settlements' / (claim['token'] + '.json'))
        require(settled['token'] == claim['token'] and settled['claim_sha256'] == sha(path), 'budget settlement binding')
        if claim['kind'] == 'Blender_start':
            require(settled['spawn_status'] == 'spawned' and type(settled['pid']) is int and settled['pid'] > 0,
                    'confirmed owned start')
            starts[claim['phase']] += 1
            start_labels[claim['label']] += 1
            continue
        require(claim['kind'] == 'raster_request' and type(claim['reserved_upper_bound']) is int
                and 0 <= claim['reserved_upper_bound'] <= 6, 'raster claim bounds')
        actual = settled['actual_attempts']
        require(type(actual) is int and actual == settled['confirmed_attempts_lower_bound']
                and 0 <= actual <= claim['reserved_upper_bound'], 'actual raster bound and lower count')
        evidence = settled['evidence']
        audit = Path(evidence['audit_path']).resolve()
        require(audit.is_relative_to(RUNTIME), 'original raster evidence location')
        original = audit.read_bytes()
        tail = original[evidence['tail_start_bytes']:evidence['tail_start_bytes'] + evidence['tail_bytes']]
        require(len(tail) == evidence['tail_bytes'] and hashlib.sha256(tail).hexdigest() == evidence['tail_sha256'],
                'original raster evidence bytes')
        events = [json.loads(line) for line in tail.splitlines() if line.strip()]
        events = [row for row in events if row.get('event') == 'active_observation_render_attempt']
        require(events == evidence['render_attempt_events'] and actual == len(events), 'actual raster event count')
        rasters[claim['phase']] += actual
        failed_rasters += settled['outcome'] == 'failed'
    require(starts == {'qualification': 4, 'formal': 8} and start_labels == dict.fromkeys(QUALIFICATIONS + ORDER, 1),
            'twelve starts by exact label')
    require(rasters['qualification'] <= 36 and rasters['formal'] <= 36 and sum(rasters.values()) <= 72,
            'registered phase and total raster bounds')
    archive = read(HERE / 'RUNTIME_ARCHIVE.json')
    require(archive['schema'] == 'm5-observe-measure-runtime-archive-v1'
            and Path(archive['runtime_root']).resolve() == RUNTIME and archive['runtime_exclusions'] == []
            and archive['original_runtime_retained'] is True and archive['all_copies_verified_byte_exact'] is True,
            'whole runtime archive contract')
    mapping_pins(archive['report_pins'], HERE)
    original = {path.relative_to(RUNTIME).as_posix(): path for path in files_under(RUNTIME)}
    require(len(archive['files']) == archive['file_count'] == len(original)
            and {row['relative_path'] for row in archive['files']} == set(original), 'complete runtime archive set')
    targets = set()
    for row in archive['files']:
        source, target = original[row['relative_path']], HERE / row['archive_path']
        require(source.resolve() == Path(row['original_path']).resolve()
                and target.resolve().is_relative_to(HERE / 'runtime_archive')
                and str(target.resolve()) not in targets, 'unique scoped archive mapping')
        targets.add(str(target.resolve()))
        require(source.stat().st_size == target.stat().st_size == row['bytes']
                and sha(source) == sha(target) == row['sha256'], 'original runtime byte parity')
    require(sum(row['bytes'] for row in archive['files']) == archive['bytes']
            and {str(path.resolve()) for path in files_under(HERE / 'runtime_archive')} == targets, 'exact archive closure')
    return {'owned_starts': 12, 'qualification_and_state_rasters': rasters['qualification'],
            'formal_rasters': rasters['formal'], 'total_rasters': sum(rasters.values()),
            'failed_raster_settlements_retained': failed_rasters, 'pending_attempt_reservations': 0,
            'runtime_archive_files': archive['file_count'], 'runtime_archive_bytes': archive['bytes'],
            'original_runtime_retained': True}


def credential_scan():
    patterns = [re.compile(value) for value in (
        rb'(?<![A-Za-z0-9])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}',
        rb'gh[pousr]_[A-Za-z0-9]{30,}', rb'github_pat_[A-Za-z0-9_]{40,}', rb'AIza[A-Za-z0-9_-]{35}',
        rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
        rb'''(?:access_token|refresh_token|id_token)["']?\s*[:=]\s*["'][A-Za-z0-9._~-]{24,}''',
    )]
    private = {'auth.json', 'credentials.json', 'token.json', '.env', 'id_rsa', 'id_ed25519'}
    findings = []
    checked = members = 0

    def inspect(blob, label, filename):
        nonlocal checked, members
        checked += 1
        if Path(filename).name.lower() in private:
            findings.append({'path': label, 'rule': 'private_filename'})
        for index, pattern in enumerate(patterns, 1):
            if pattern.search(blob):
                findings.append({'path': label, 'rule': 'credential_pattern_' + str(index)})
        if zipfile.is_zipfile(io.BytesIO(blob)):
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                for member in archive.infolist():
                    if not member.is_dir():
                        members += 1
                        inspect(archive.read(member), label + '!' + member.filename, member.filename)

    for path in files_under(HERE, namespace=True) + files_under(RUNTIME) + [ROOT / name for name in sorted(PRODUCT_PATHS)]:
        inspect(path.read_bytes(), str(path), path.name)
    require(not findings, 'credential candidates (paths/rules only) ' + json.dumps(findings, ensure_ascii=True))
    return {'credential_scan_items': checked, 'credential_scan_container_members': members,
            'credential_pattern_candidates': 0, 'credential_scan_scope':
            'Original namespace/runtime/product bytes and recursively decoded ZIP members. Pattern scan only. Matching bytes are never printed.'}


def delivery_paths():
    paths = files_under(HERE, namespace=True) + [ROOT / name for name in sorted(PRODUCT_PATHS)]
    return sorted(path for path in paths if path != HERE / 'CONTENT_MANIFEST.json')


def seal():
    for name in ('FINAL_AUDIT.json', 'CONTENT_MANIFEST.json', 'QUALIFICATION_LEDGER.json'):
        require(not (HERE / name).exists(), 'seal outputs are write once')
    checks = verify_sources()
    checks.update(verify_results())
    checks.update(verify_budget_archive())
    checks.update(credential_scan())
    baseline = read(HERE / 'BASELINE.json')
    closed = time.perf_counter_ns()
    dump(HERE / 'QUALIFICATION_LEDGER.json', {'schema': 'm5-observe-measure-ledger-v1',
        'registered_started_ns': baseline['started_ns'], 'audit_closed_ns': closed,
        'registered_analysis_elapsed_ns': closed - baseline['started_ns'],
        'scope': 'Registration through saved-only sealing. Nested preparation, qualification, formal, control and review clocks are recorded separately.',
        'formal_main_tasks': 6, 'task_only_controls': 2, 'owned_sessions': 12,
        'optimization_attempts': 1, 'formal_attempts': 1, 'outer_retries': 0, 'replacement_samples': 0,
        'new_operations_by_sealer': {'Blender_starts': 0, 'rasters': 0, 'model_calls': 0, 'paid_API_calls': 0},
        'coordinator_reviewer_fees': None, 'limits': baseline['limits']})
    dump(HERE / 'FINAL_AUDIT.json', {'schema': 'm5-observe-measure-root-audit-v1',
        'passed_checked_scope': True, 'baseline_git': BASELINE, 'final_product_git': FINAL_GIT,
        'administrator_review': 'pending', 'AL_registration': 'pending_current_chat_host_binding',
        'author_association': 'Sealer author implemented M5 product wiring, its unique optimization and product pure checks. Root and other agents authored the separate controllers and actual evidence reviews.',
        'business_failure_preservation': 'Quality and performance gates retain their actual booleans and disposition. Technical source/terminal audit is required independently.',
        'artifacts_sha256': {path.relative_to(ROOT).as_posix(): sha(path) for path in delivery_paths()}, **checks})
    rows = [{'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
            for path in delivery_paths()]
    dump(HERE / 'CONTENT_MANIFEST.json', {'schema': 'm5-observe-measure-content-manifest-v1',
        'baseline_git': BASELINE, 'scope': 'Entire new namespace and exactly six changed product sources. Self and namespace __pycache__ excluded. Runtime archive has no exclusions.',
        'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows), 'files': rows})
    print(json.dumps({'passed_checked_scope': True, 'content_files': len(rows),
                      'audit_sha256': sha(HERE / 'FINAL_AUDIT.json'), 'manifest_sha256': sha(HERE / 'CONTENT_MANIFEST.json')}))


def verify_git():
    manifest = read(HERE / 'CONTENT_MANIFEST.json')
    pins(manifest['files'])
    expected = {row['path'] for row in manifest['files']} | {(HERE / 'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix()}
    actual = {path.relative_to(ROOT).as_posix() for path in delivery_paths()} | {(HERE / 'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix()}
    require(len(manifest['files']) == manifest['file_count'] and actual == expected, 'exact delivery manifest closure')
    staged = {name.decode('utf-8') for name in git('diff', '--cached', '--name-only', '-z', BASELINE).split(b'\0') if name}
    require(staged == expected, 'exact staged baseline diff closure')
    require(not git('diff', '--name-only', '-z'), 'unstaged changes after seal')
    index = {}
    for row in git('ls-files', '--stage', '-z').split(b'\0'):
        if row:
            fields, path = row.split(b'\t', 1)
            mode, digest, stage = fields.split()
            require(stage == b'0', 'unmerged Git index')
            index[path.decode('utf-8')] = digest.decode('ascii')
    for name in expected:
        require(index.get(name) == git_blob((ROOT / name).read_bytes()), 'exact Git blob parity ' + name)
    print(json.dumps({'manifest_and_staged_paths': len(expected), 'exact_Git_blob_byte_parity': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-git', action='store_true')
    args = parser.parse_args()
    if args.verify_git:
        verify_git()
    else:
        seal()
