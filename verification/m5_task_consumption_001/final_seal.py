"""Seal one fixed M5 consumer batch, retaining failed and unrun evidence."""

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
RUNTIME = Path('D:/he_m5_task_consume_001').resolve()
BASELINE = '14c8c6b8206dcaecc373bc9aa895cda1d622eee3'
FORMAL_GIT = '99c5ba3ebcd62cbb94174a06e0a419912257bc91'
ORDER = ['A1','B1','B2','A2','A3','B3']
QUALIFICATIONS = ['A_qual','B_qual']
PRODUCT_PATHS = set()
FIXED = {
    'BASELINE.json':'841e23fabc2d40fa3295d877d2c3302793edfa41a65dc7cbf68799e4f9929d39',
    'PLAN.json':'d8d664635dd7f815325da0c08ff8a536c9b84d576b008b32e5cf347a24213542',
    'FROZEN.json':'197cc12022db062b78c8a5f44fd347c21851810d663abc3d616d0d5e88c692b0',
}
VERSIONS = {
    'A': ('c309d7e4302518cd5f7d1c3966e7c7fa338ea128',
          '776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be',
          'D:/he_m4_target_002/B/product', HERE.with_name('m4_target_acquisition_002')/'build_B'),
    'B': ('ccb608aa83de4b0e6671da89e0c8f387bd3f800e',
          '7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a',
          'D:/he_m5_observe_measure_001/B/product', HERE.with_name('m5_observe_measure_001')/'build_final'),
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


def verify_versions():
    rows = []
    baseline = read(HERE / 'BASELINE.json')
    for group, (commit, digest, install, wheel_directory) in VERSIONS.items():
        name = group + '_RUN_BINDING.json'
        binding = read(HERE / name)
        require(sha(HERE / name) == baseline['bindings_sha256'][group]
                and binding['preparation_git'] == commit and binding['source_sha256'] == digest
                and Path(binding['install_root']).resolve() == Path(install).resolve(), 'version binding ' + group)
        manifest = binding['source_manifest']
        names = [row['path'] for row in manifest]
        require(len(names) == len(set(names)) == 141, 'exact source count ' + group)
        identity = {name: binding[name] for name in ('base_version', 'implementation_revision')}
        identity['files'] = manifest
        require(hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'),
                ensure_ascii=True).encode()).hexdigest() == digest, 'source aggregate ' + group)
        historical = git_snapshot(commit, names)
        require(set(historical) == set(names), 'historical source closure ' + group)
        for row in manifest:
            require(hashlib.sha256(historical[row['path']]).hexdigest() == row['sha256'], 'historical source bytes ' + group)
        pins(manifest, Path(install))
        if group == 'B':
            pins(manifest)
            require(git_snapshot(BASELINE, names) == historical, 'baseline B product unchanged')
        wheels = list(wheel_directory.glob('*.whl'))
        require(len(wheels) == 1 and sha(wheels[0]) == binding['wheel_sha256'], 'fixed wheel ' + group)
        with zipfile.ZipFile(wheels[0]) as wheel:
            for row in manifest:
                require(hashlib.sha256(wheel.read(row['path'])).hexdigest() == row['sha256'], 'wheel member ' + group)
        rows.append({'group': group, 'git': commit, 'source141_sha256': digest,
            'source_count': 141, 'wheel_sha256': binding['wheel_sha256'], 'install_root': install,
            'worktree_match_required': group == 'B'})
    return rows


def verify_sources():
    for name, digest in FIXED.items():
        require(sha(HERE / name) == digest, 'fixed registration changed ' + name)
    baseline = read(HERE / 'BASELINE.json')
    require(baseline['baseline_git'] == BASELINE and baseline['production_changes_allowed'] is False
            and len(baseline['protected_old_pins']) == 29, 'fixed namespace and history contract')
    old_members = 0
    for name, digest in baseline['protected_old_pins'].items():
        require(sha(name) == digest, 'old protected bytes changed ' + name)
        if Path(name).name == 'CONTENT_MANIFEST.json':
            old_members += pins(read(name)['files'], Path(name).parents[2])
    for name, digest in baseline['references'].items():
        require(sha(name) == digest and sha(HERE / 'reference' / Path(name).name) == digest, 'original reference changed')
    frozen = read(HERE / 'FROZEN.json')
    require(pins(frozen['files']) == 928, 'formal frozen 928 current source pins')
    name = (HERE / 'FROZEN.json').relative_to(ROOT).as_posix()
    require(git_snapshot(FORMAL_GIT, [name])[name] == (HERE / 'FROZEN.json').read_bytes(), 'historical preformal freeze')
    versions = verify_versions()
    prefix = HERE.relative_to(ROOT).as_posix() + '/'
    changed = [row.decode() for row in git('diff', '--name-only', '-z', BASELINE).split(b'\0') if row]
    untracked = [row.decode() for row in git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if row]
    require(all(name.startswith(prefix) for name in changed + untracked), 'changes outside sole namespace')
    return {'protected_old_pins': 29, 'protected_old_manifest_members': old_members,
            'reference_count': len(baseline['references']), 'frozen_source_pins': 928,
            'source_versions': versions, 'product_diff_paths': []}


def optional_json(path):
    if not path.is_file():
        return None, 'missing'
    try:
        return read(path), None
    except (ValueError, UnicodeError) as error:
        return None, type(error).__name__


def verify_results():
    quality = read(HERE / 'QUALITY.json')
    require(quality['schema'] == 'm5-task-consumption-quality-v1' and quality['denominator'] == 6
            and quality['cost_analysis_performed'] is False
            and [row['slot_id'] for row in quality['slots']] == ORDER, 'fixed six quality denominator')
    mapping_pins(quality['inputs_sha256'])
    seal = read(HERE / 'QUALITY_SEAL.json')
    require(seal['quality_sha256'] == sha(HERE / 'QUALITY.json') and seal['cost_unlocked'] is True
            and type(seal['sealed_ns']) is int, 'quality-first source seal')
    pins(seal['source_pins'])
    decision = read(HERE / 'DECISION.json')
    require(decision['schema'] == 'm5-task-consumption-decision-v1'
            and decision['quality_sha256'] == sha(HERE / 'QUALITY.json')
            and decision['quality_seal_sha256'] == sha(HERE / 'QUALITY_SEAL.json')
            and decision['decision_source_sha256'] == sha(HERE / 'cost_decision.py')
            and [row['slot_id'] for row in decision['rows']] == ORDER
            and type(decision['passed_frozen_gates']) is bool, 'decision source and fixed rows')
    pins(decision['input_pins'])
    checker = read(HERE / 'COST_CHECKER_REVIEW.json')
    require(checker['passed_checked_scope'] is True
            and checker['reviewed_source']['sha256'] == decision['decision_source_sha256'], 'cost checker source binding')
    review = read(HERE / 'RUNTIME_REVIEW.json')
    require(review['schema'] == 'm5-task-runtime-review-v1' and review['qualification_only'] is False
            and type(review['passed_checked_scope']) is bool, 'complete runtime review scope')
    pins(review['input_pins'])
    require(review['passed_checked_scope'] is True or decision['passed_frozen_gates'] is False,
            'failed runtime audit cannot accept candidate')
    run = read(RUNTIME / 'RUN_RESULT.json')
    intent = read(RUNTIME / 'FORMAL_STARTED.json')
    require([row['slot_id'] for row in run['records']] == ORDER and run['planned_slots'] == 6
            and 0 <= run['actual_consumers'] <= run['consumer_attempts'] <= 6
            and run['formal_batch_attempts'] == 1
            and run['outer_retries'] == run['replacement_samples'] == 0, 'original single fixed batch')
    require(review['formal_dispatch'] == run, 'audited entire failed/unrun dispatch')
    require(run['plan_sha256'] == intent['plan_sha256'] == FIXED['PLAN.json']
            and run['frozen_sha256'] == intent['freeze_sha256'] == FIXED['FROZEN.json']
            and intent['formal_attempts'] == 1 and intent['outer_retries'] == intent['replacement_samples'] == 0,
            'original formal start contract')
    require(run['actual_consumers'] == 6 or decision['passed_frozen_gates'] is False,
            'incomplete consumer denominator cannot pass candidate gates')
    audit_paths = {str(Path(row['path']).resolve()) for row in review['input_pins']}
    answers = []
    for record in run['records']:
        slot = record['slot_id']
        folder = RUNTIME / 'formal' / slot
        for name, key in (('SLOT_RESULT.json', 'result_sha256'), ('SLOT_PUBLICATION.json', 'publication_sha256')):
            path = folder / name
            if path.is_file():
                require(str(path.resolve()) in audit_paths, 'original slot file audited ' + slot + '/' + name)
                if record.get(key) is not None:
                    require(sha(path) == record[key], 'original dispatch hash ' + slot + '/' + name)
        consumer, error = optional_json(folder / 'consumer/CONSUMER.json')
        public = folder / 'consumer/PUBLIC_FINAL.txt'
        final = consumer.get('final') if type(consumer) is dict else None
        if type(final) is str and public.is_file():
            require(public.read_bytes() == final.encode('utf-8'), 'original final answer bytes ' + slot)
        answers.append({'slot_id': slot, 'execution_state': record['status'],
            'consumer_record_state': error, 'final_text_in_consumer': type(final) is str,
            'public_final_present': public.is_file(), 'public_final_sha256': sha(public) if public.is_file() else None})
    require((HERE / 'REPORT.md').is_file(), 'root final report required')
    stopped = verify_operator_stop(run, decision)
    return {'formal_denominator': 6, 'actual_consumers': run['actual_consumers'],
            'consumer_attempts': run['consumer_attempts'], 'formal_attempts': 1, 'replacement_samples': 0,
            'quality_complete': quality['all_six_quality_complete'],
            'B_actual_joint_fact_adoption_count': quality['B_actual_joint_fact_adoption_count'],
            'A_batch_adoption_count': quality['A_batch_adoption_count'],
            'runtime_review_passed_checked_scope': review['passed_checked_scope'],
            'passed_frozen_business_gates': decision['passed_frozen_gates'],
            'disposition': decision['disposition'], 'original_answers': answers, **stopped}


def verify_operator_stop(run, decision):
    stop_path = RUNTIME / 'ROOT_OPERATOR_STOP.json'
    stopped = RUNTIME / 'formal/B3'
    copy_path = stopped / 'ROOT_OPERATOR_STOP.json'
    stop = read(stop_path)
    require(stop['schema'] == 'm5-task-root-operator-stop-v1'
            and stop['stopped_before_slot'] == 'B3'
            and stop['product_or_frozen_source_changed'] is False
            and stop_path.read_bytes() == copy_path.read_bytes(), 'original operator stop and exact boundary copy')
    mapping_pins(stop['source_sha256'], RUNTIME)
    require(run['actual_consumers'] == run['consumer_attempts'] == 5
            and decision['passed_frozen_gates'] is False, 'interfered five-consumer batch is not a positive signal')
    row = next(row for row in run['records'] if row['slot_id'] == 'B3')
    require(row['status'] == 'failed' and row.get('result_path') is None and row.get('publication_path') is None,
            'stopped B3 remains original dispatch failure')
    for name in ('SLOT_RESULT.json', 'SLOT_PUBLICATION.json', 'CONSUMER_START.json',
                 'consumer/CONSUMER.json', 'consumer/PUBLIC_FINAL.txt', 'native/SPAWN.json', 'mcp/SPAWN.json'):
        require(not (stopped / name).exists(), 'no fabricated B3 process or answer ' + name)
    for path in (RUNTIME / 'budget/claims').glob('*.json'):
        require(read(path)['label'] != 'B3', 'no actual B3 budget admission')
    diagnosis_path = HERE / 'A1_ARCHIVE_CORRELATION_DIAGNOSIS.json'
    diagnosis = read(diagnosis_path)
    require(diagnosis['schema'] == 'm5-A1-archive-correlation-diagnosis-v1', 'original harness interference diagnosis')
    pins(diagnosis['input_pins'])
    responses = {row['id']: row for row in diagnosis['actual_public_requests']}
    for rid, tool in (('observe-3', 'tool_02'), ('observe-4', 'tool_04')):
        original = responses[rid]['actual_response_pin']
        pins([original])
        inner = read(original['path'])
        outer = read(RUNTIME / 'formal/A1/owner' / tool / 'RESPONSE.json')
        require(inner['id'] == rid and inner['result']['isError'] is False
                and outer['result']['isError'] is True
                and 'same_producer_archive_receipt_missing' in json.dumps(outer),
                'actual valid product reply replaced by harness error ' + rid)
    return {'operator_stop_present': True, 'operator_stop_sha256': sha(stop_path),
            'stopped_unstarted_slot': 'B3', 'harness_interference_diagnosis_sha256': sha(diagnosis_path),
            'workflow_positive_signal_permitted': False}


def verify_budget_archive():
    budget = RUNTIME / 'budget'
    claims = {path.stem: (path, read(path)) for path in sorted((budget / 'claims').glob('*.json'))}
    require(claims, 'budget originals required')
    counters, business, rasters, consumers = Counter(), Counter(), Counter(), Counter()
    unconfirmed = []
    known_settlements = set()
    for token, (path, claim) in claims.items():
        label, phase = claim['label'], claim['phase']
        require(claim['token'] == token and label in QUALIFICATIONS + ORDER
                and phase == ('formal' if label in ORDER else 'qualification')
                and claim['reserved_upper_bound'] == 1, 'current unit claim source')
        settled_path = budget / 'settlements' / (token + '.json')
        settled = read(settled_path) if settled_path.is_file() else None
        if settled is not None:
            known_settlements.add(token)
            require(settled['token'] == token and settled['claim_sha256'] == sha(path), 'original settlement source')
        kind = claim['kind']
        require(kind in ('business_tool', 'consumer_task', 'Blender_start', 'raster_attempt'), 'registered claim kind')
        if kind == 'business_tool':
            business[label] += 1
        elif kind == 'consumer_task':
            require(phase == 'formal', 'consumer only in formal phase')
            consumers[label] += 1
        elif kind == 'Blender_start':
            counters['starts'] += 1
            counters[phase + '_starts'] += 1
            if settled is None or settled.get('spawn_status') != 'spawned':
                unconfirmed.append({'token': token, 'kind': kind, 'label': label, 'state': settled})
        else:
            actual = None if settled is None else settled['actual_attempts']
            lower = 0 if settled is None else settled['confirmed_attempts_lower_bound']
            require(type(lower) is int and 0 <= lower <= 1
                    and (actual is None or type(actual) is int and lower <= actual <= 1), 'raster actual/lower/upper')
            counters[phase + '_raster_actual'] += lower if actual is None else actual
            counters[phase + '_raster_upper'] += 1 if actual is None else actual
            rasters[label] += 1 if actual is None else actual
            if actual is None:
                unconfirmed.append({'token': token, 'kind': kind, 'label': label, 'state': settled})
    require({path.stem for path in (budget / 'settlements').glob('*.json')} == known_settlements,
            'no orphan settlement files')
    require(counters['starts'] <= 8 and counters['qualification_starts'] <= 2 and counters['formal_starts'] <= 6
            and counters['qualification_raster_upper'] <= 12 and counters['formal_raster_upper'] <= 36
            and counters['qualification_raster_upper'] + counters['formal_raster_upper'] <= 48
            and all(value <= 6 for value in rasters.values()) and all(value <= 12 for value in business.values())
            and sum(consumers.values()) <= 6 and all(value <= 1 for value in consumers.values()), 'fixed resource bounds')
    archive = read(HERE / 'RUNTIME_ARCHIVE.json')
    require(archive['schema'] == 'm5-task-consumption-runtime-archive-v1'
            and Path(archive['runtime_root']).resolve() == RUNTIME and archive['runtime_exclusions'] == []
            and archive['original_runtime_retained'] is True and archive['all_copies_verified_byte_exact'] is True,
            'whole original runtime archive')
    mapping_pins(archive['report_pins'], HERE)
    originals = {path.relative_to(RUNTIME).as_posix(): path for path in files_under(RUNTIME)}
    require(len(archive['files']) == archive['file_count'] == len(originals)
            and {row['relative_path'] for row in archive['files']} == set(originals), 'all runtime originals covered')
    targets = set()
    for row in archive['files']:
        source, target = originals[row['relative_path']], HERE / row['archive_path']
        require(source.resolve() == Path(row['original_path']).resolve()
                and target.resolve().is_relative_to(HERE / 'runtime_archive')
                and str(target.resolve()) not in targets, 'unique archive paths')
        targets.add(str(target.resolve()))
        require(source.stat().st_size == target.stat().st_size == row['bytes']
                and sha(source) == sha(target) == row['sha256'], 'archive original-byte parity')
    require({str(path.resolve()) for path in files_under(HERE / 'runtime_archive')} == targets
            and sum(row['bytes'] for row in archive['files']) == archive['bytes'], 'exact archive closure')
    return {'budget_counters': dict(counters), 'business_admissions_by_slot': dict(business),
            'consumer_admissions_by_slot': dict(consumers), 'unconfirmed_original_attempts': unconfirmed,
            'budget_count_scope': 'raster_actual retains the confirmed lower bound for unknown attempts; raster_upper retains the unit reservation.',
            'runtime_archive_files': archive['file_count'], 'runtime_archive_bytes': archive['bytes']}


def delivery_paths():
    return [path for path in files_under(HERE, namespace=True) if path != HERE / 'CONTENT_MANIFEST.json']


def seal():
    for name in ('FINAL_AUDIT.json', 'QUALIFICATION_LEDGER.json', 'CONTENT_MANIFEST.json'):
        require(not (HERE / name).exists(), 'seal outputs are write once')
    checks = verify_sources()
    checks.update(verify_results())
    checks.update(verify_budget_archive())
    checks.update(credential_scan())
    require(not checks['unconfirmed_original_attempts'] or checks['passed_frozen_business_gates'] is False,
            'unknown original attempts cannot pass candidate gates')
    baseline = read(HERE / 'BASELINE.json')
    closed = time.perf_counter_ns()
    dump(HERE / 'QUALIFICATION_LEDGER.json', {'schema': 'm5-task-consumption-ledger-v1',
        'registered_started_ns': baseline['started_ns'], 'audit_closed_ns': closed,
        'registered_analysis_elapsed_ns': closed - baseline['started_ns'], 'formal_attempts': 1,
        'formal_denominator': 6, 'actual_consumers': checks['actual_consumers'], 'outer_retries': 0,
        'replacement_samples': 0, 'limits': baseline['limits'], 'reviewer_provider_usage': None,
        'scope': 'Registration through saved-only seal. Preparation, qualifications, formal tasks and reviews retain their distinct nested clocks.',
        'new_Blender_MCP_raster_model_paid_calls_by_sealer': 0})
    dump(HERE / 'FINAL_AUDIT.json', {'schema': 'm5-task-consumption-root-audit-v1',
        'passed_checked_scope': True, 'baseline_git': BASELINE, 'administrator_review': 'pending',
        'AL_registration': 'pending_current_chat_host_binding',
        'seal_scope': 'Saved-source and byte/manifest integrity. Execution, task success, adoption and positive-signal gates retain their actual values separately.',
        'author_association': 'This sealer author implemented the shared task bridge and independent cost-source checker. The lifecycle controller, runtime audit and recovery candidate share one agent author. A separate agent authored quality scoring and normalization. Root authored input freezes, the operator stop, independent semantic review and cost decision. Administrator independent acceptance remains pending.',
        'artifacts_sha256': {path.relative_to(ROOT).as_posix(): sha(path) for path in delivery_paths()}, **checks})
    rows = [{'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path), 'bytes': path.stat().st_size}
            for path in delivery_paths()]
    dump(HERE / 'CONTENT_MANIFEST.json', {'schema': 'm5-task-consumption-content-manifest-v1',
        'baseline_git': BASELINE, 'scope': 'Whole new namespace, excluding only this manifest and namespace __pycache__. Original runtime archive has no exclusions.',
        'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows), 'files': rows})
    print(json.dumps({'passed_checked_scope': True, 'files': len(rows),
        'audit_sha256': sha(HERE / 'FINAL_AUDIT.json'), 'manifest_sha256': sha(HERE / 'CONTENT_MANIFEST.json')}))


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
