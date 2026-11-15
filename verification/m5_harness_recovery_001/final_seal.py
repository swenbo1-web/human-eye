"""Seal this bounded recovery chain using its frozen source and saved reviews."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = Path('D:/he_m5_harness_recovery_001').resolve()
BASELINE = 'baf8799d9e1cb411d39da58c28171b00ac76f12f'
FROZEN_GIT = '046e1772959af7c3c297ac2678ac3845ae27abc5'
FIXED = {
    'BASELINE.json': 'bef55ce8dbd7fb7bf7e6bf6b2b9e5e0e2e8a68abd4538d1773ed49a83c88ae45',
    'PLAN.json': '4f60ceb4ec5c6c5dc746df853c87e5a1b9b240fb5d1fe65ba4e3eaa1a7be3cf0',
    'FROZEN.json': 'f8fb8e0c57a061a544e5b868a1216f5b36a9c63358e2e6c5a12a3dd5fd6be79f',
}


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def need(value, reason):
    if not value:
        raise AssertionError(reason)


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def pins(rows):
    paths = set()
    for row in rows:
        path = Path(row['path']).resolve()
        need(str(path) not in paths, 'duplicate pin')
        paths.add(str(path))
        need(sha(path) == row['sha256'] and ('bytes' not in row or path.stat().st_size == row['bytes']), 'changed source ' + str(path))
    return len(paths)


def mapping_pins(mapping):
    return pins([{'path': path, 'sha256': digest} for path, digest in mapping.items()])


def files_under(directory, namespace=False):
    directory = Path(directory).resolve()
    result = []
    for current, names, files in os.walk(directory, topdown=True, followlinks=False):
        for name in names + files:
            path = Path(current) / name
            need(not path.is_symlink() and not path.is_junction(), 'reparse entry')
            path.resolve().relative_to(directory)
        if namespace:
            names[:] = [name for name in names if name != '__pycache__']
        result.extend(Path(current) / name for name in files)
    return sorted(result)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def verify_sources():
    for name, digest in FIXED.items():
        need(sha(HERE / name) == digest, 'frozen registration ' + name)
    baseline = read(HERE / 'BASELINE.json')
    need(baseline['baseline_git'] == BASELINE and baseline['product_changes_allowed'] is False, 'baseline identity')
    need(pins(baseline['protected_direct_seals']) == 5, 'five direct prior seals')
    pins([baseline['candidate'], baseline['asset'], baseline['A_binding'], baseline['B_binding']])
    for pair in baseline['references']:
        pins([pair['original'], pair['copy']])
        need(pair['original']['sha256'] == pair['copy']['sha256'], 'original reference copy')
    frozen = read(HERE / 'FROZEN.json')
    need(pins(frozen['files']) == 68, '68 current source and input pins')
    name = (HERE / 'FROZEN.json').relative_to(ROOT).as_posix()
    need(git('show', FROZEN_GIT + ':' + name) == (HERE / 'FROZEN.json').read_bytes(), 'pre-execution Git freeze')
    prefix = HERE.relative_to(ROOT).as_posix() + '/'
    changed = [row.decode() for row in git('diff', '--name-only', '-z', BASELINE).split(b'\0') if row]
    untracked = [row.decode() for row in git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if row]
    need(all(name.startswith(prefix) for name in changed + untracked), 'source changes outside new namespace')
    return {'frozen_pins': 68, 'prior_direct_seals': 5, 'prior_manifest_members_expanded': 0,
            'candidate_and_asset_pins': 2, 'product_diff_paths': []}


def verify_results():
    qualification = read(HERE / 'QUALIFICATION.json')
    review = read(HERE / 'RUNTIME_REVIEW.json')
    decision = read(HERE / 'DECISION.json')
    need(qualification['schema'] == 'm5-harness-recovery-independent-qualification-v1'
            and qualification['denominator'] == 2
            and [row['group'] for row in qualification['records']] == ['A', 'B'], 'independent two-session scope')
    mapping_pins(qualification['inputs_sha256'])
    need(qualification['checker_sha256'] == sha(HERE / 'check_saved.py')
            and qualification['expectations_sha256'] == sha(HERE / 'EXPECTATIONS.json')
            and qualification['private_full_used_as_outer_delivery'] is False
            and qualification['performance_ranking_performed'] is False
            and qualification['product_benefit_test'] is False, 'qualified source and delivery scope')
    need(review['schema'] == 'm5-harness-recovery-runtime-review-v1'
            and [row['group'] for row in review['sessions']] == ['A', 'B']
            and review['product_or_model_benefit_claim'] is False, 'runtime scope')
    pins(review['input_pins'])
    need(decision['schema'] == 'm5-harness-recovery-decision-v1'
            and type(decision['accepted_harness_recovery']) is bool
            and decision['qualification_sha256'] == sha(HERE / 'QUALIFICATION.json')
            and decision['runtime_review_sha256'] == sha(HERE / 'RUNTIME_REVIEW.json')
            and decision['product_or_model_benefit_claim'] is False, 'decision binding and recovery-only claim')
    pins(decision['input_pins'])
    accepted = decision['accepted_harness_recovery']
    need(not accepted or qualification['passed_checked_scope'] is True and review['passed_checked_scope'] is True,
            'failed review cannot accept recovery')
    budget = review['budget']
    need(0 <= budget['owned_start_attempts'] <= 2
            and 0 <= budget['raster_attempts_actual'] <= budget['raster_attempts_upper'] <= 12
            and budget['consumer_admissions'] == budget['paid_API_calls'] == 0, 'new-batch resource bounds')
    need(not accepted or budget['owned_start_attempts'] == 2 and budget['pending'] == 0,
            'accepted recovery requires confirmed two-session closure')
    original = []
    for group in ('A', 'B'):
        folder = RUNTIME / 'sessions' / group
        result, publication = folder / 'SLOT_RESULT.json', folder / 'SLOT_PUBLICATION.json'
        if not result.is_file() or not publication.is_file():
            need(not accepted, 'accepted recovery needs original result and publication')
            original.append({'group': group, 'result_present': result.is_file(), 'publication_present': publication.is_file()})
            continue
        body, end = read(result), read(publication)
        need(end['result_sha256'] == sha(result) and body['group'] == group, 'original session publication')
        need(body['model_consumers'] == body['paid_API_calls'] == 0
                and body.get('consumer_record') is None and body.get('consumer_envelope_path') is None, 'zero consumer session')
        need(body['source']['product_source141_sha256'] == read(HERE / (group + '_RUN_BINDING.json'))['source_sha256'],
                'fixed installed product identity')
        if accepted:
            need(body['status'] == end['status'] == 'completed' and body['errors'] == [], 'accepted original session state')
            need(body['clocks']['owned_deadline_ns'] == body['clocks']['slot_started_ns'] + 600_000_000_000
                    and body['clocks']['worker_deadline_ns'] == body['clocks']['owned_deadline_ns']
                    and body['clocks']['slot_started_ns'] <= end['slot_result_published_ns'] < body['clocks']['owned_deadline_ns'],
                    'original owned deadline')
            session = next(row for row in review['sessions'] if row['group'] == group)
            need(session['producer_indices'] == [1, None, 2, 3, 4]
                    and session['public_calls'] == 5 and session['outer_tools'] == 4, 'actual recovery sequence')
        original.append({'group': group, 'SLOT_RESULT_sha256': sha(result), 'SLOT_PUBLICATION_sha256': sha(publication),
                         'status': body['status']})
    need((HERE / 'REPORT.md').is_file(), 'root report required')
    return {'accepted_harness_recovery': accepted, 'qualification_passed': qualification['passed_checked_scope'],
            'runtime_review_passed': review['passed_checked_scope'], 'actual_budget': budget,
            'original_sessions': original, 'product_or_model_benefit_claim': False}


def verify_archive():
    archive = read(HERE / 'RUNTIME_ARCHIVE.json')
    need(archive['schema'] == 'm5-harness-recovery-runtime-archive-v1'
            and Path(archive['runtime_root']).resolve() == RUNTIME and archive['runtime_exclusions'] == []
            and archive['original_runtime_retained'] is True and archive['all_copies_verified_byte_exact'] is True,
            'whole original archive')
    mapping_pins({str(HERE / path): digest for path, digest in archive['report_pins'].items()})
    originals = {path.relative_to(RUNTIME).as_posix(): path for path in files_under(RUNTIME)}
    need(len(archive['files']) == archive['file_count'] == len(originals)
            and {row['relative_path'] for row in archive['files']} == set(originals), 'exact original archive set')
    destinations = set()
    for row in archive['files']:
        source, target = originals[row['relative_path']], HERE / row['archive_path']
        need(source.resolve() == Path(row['original_path']).resolve()
                and target.resolve().is_relative_to(HERE / 'runtime_archive')
                and str(target.resolve()) not in destinations, 'unique scoped archive path')
        destinations.add(str(target.resolve()))
        need(source.stat().st_size == target.stat().st_size == row['bytes']
                and sha(source) == sha(target) == row['sha256'], 'original/archive bytes')
    need(sum(row['bytes'] for row in archive['files']) == archive['bytes']
            and {str(path.resolve()) for path in files_under(HERE / 'runtime_archive')} == destinations, 'archive closure')
    return {'runtime_archive_files': archive['file_count'], 'runtime_archive_bytes': archive['bytes']}


def credential_scan():
    patterns = [re.compile(pattern) for pattern in (
        rb'(?<![A-Za-z0-9])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}',
        rb'gh[pousr]_[A-Za-z0-9]{30,}', rb'github_pat_[A-Za-z0-9_]{40,}', rb'AIza[A-Za-z0-9_-]{35}',
        rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
        rb'''(?:access_token|refresh_token|id_token)["']?\s*[:=]\s*["'][A-Za-z0-9._~-]{24,}''')]
    findings, count = [], 0

    def inspect(data, label, name):
        nonlocal count
        count += 1
        if Path(name).name.lower() in {'auth.json', 'credentials.json', 'token.json', '.env', 'id_rsa', 'id_ed25519'}:
            findings.append({'path': label, 'rule': 'private_filename'})
        for index, pattern in enumerate(patterns):
            if pattern.search(data):
                findings.append({'path': label, 'rule': index})
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    if not member.is_dir():
                        inspect(archive.read(member), label + '!' + member.filename, member.filename)

    for path in files_under(HERE, True) + files_under(RUNTIME):
        inspect(path.read_bytes(), str(path), path.name)
    need(not findings, 'credential candidate paths/rules only ' + json.dumps(findings))
    return {'credential_candidates': 0, 'credential_original_and_ZIP_items_checked': count,
            'credential_scope': 'Original bytes and ZIP members, patterns only; no matching secret bytes printed.'}


def delivery_paths():
    return [path for path in files_under(HERE, True) if path != HERE / 'CONTENT_MANIFEST.json']


def seal():
    for name in ('FINAL_AUDIT.json', 'QUALIFICATION_LEDGER.json', 'CONTENT_MANIFEST.json'):
        need(not (HERE / name).exists(), 'write-once seal outputs')
    checked = verify_sources()
    checked.update(verify_results())
    checked.update(verify_archive())
    checked.update(credential_scan())
    baseline = read(HERE / 'BASELINE.json')
    closed = time.perf_counter_ns()
    write(HERE / 'QUALIFICATION_LEDGER.json', {'schema': 'm5-harness-recovery-ledger-v1',
        'registered_started_ns': baseline['started_ns'], 'audit_closed_ns': closed,
        'registered_wall_elapsed_ns': closed - baseline['started_ns'], 'active_work_ns': None,
        'interruption_and_idle_ns': None, 'new_actual_operations_by_sealer': 0,
        'scope': 'Registration through saved-only seal wall time includes the root coordination interruption and later user-resume wait. Active work duration is unmeasured. The two actual recovery clocks retain their original boundaries.',
        'reviewer_provider_usage': None, 'limits': baseline['limits']})
    write(HERE / 'FINAL_AUDIT.json', {'schema': 'm5-harness-recovery-final-audit-v1',
        'passed_checked_scope': True, 'baseline_git': BASELINE, 'administrator_review': 'pending',
        'AL_registration': 'pending_current_chat_host_binding',
        'author_association': 'Sealer author migrated the shared bridge. Another agent authored runtime/candidate migration and its audit; another agent independently audited public/source/image recovery. Root executes actual sessions and decides acceptance.',
        'scope': 'This chain source/archive integrity and the recorded harness acceptance only.',
        'artifacts_sha256': {path.relative_to(ROOT).as_posix(): sha(path) for path in delivery_paths()}, **checked})
    rows = [{'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path), 'bytes': path.stat().st_size}
            for path in delivery_paths()]
    write(HERE / 'CONTENT_MANIFEST.json', {'schema': 'm5-harness-recovery-content-manifest-v1',
        'baseline_git': BASELINE, 'files': rows, 'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows),
        'scope': 'Entire new namespace, excluding self and namespace __pycache__. Raw runtime archive has no exclusions.'})
    print(json.dumps({'passed': True, 'files': len(rows), 'manifest_sha256': sha(HERE / 'CONTENT_MANIFEST.json')}))


def verify_git():
    manifest = read(HERE / 'CONTENT_MANIFEST.json')
    pins([dict(row, path=str(ROOT / row['path'])) for row in manifest['files']])
    expected = {row['path'] for row in manifest['files']} | {(HERE / 'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix()}
    actual = {path.relative_to(ROOT).as_posix() for path in delivery_paths()} | {(HERE / 'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix()}
    need(len(manifest['files']) == manifest['file_count'] and actual == expected, 'exact namespace manifest')
    staged = {row.decode() for row in git('diff', '--cached', '--name-only', '-z', BASELINE).split(b'\0') if row}
    need(staged == expected and not git('diff', '--name-only', '-z'), 'exact staged baseline closure')
    index = {}
    for row in git('ls-files', '--stage', '-z').split(b'\0'):
        if row:
            fields, path = row.split(b'\t', 1)
            mode, digest, stage = fields.split()
            need(stage == b'0', 'unmerged Git index')
            index[path.decode()] = digest.decode()
    for name in expected:
        data = (ROOT / name).read_bytes()
        need(index.get(name) == hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(), 'exact staged blob bytes ' + name)
    print(json.dumps({'paths': len(expected), 'Git_blob_byte_parity': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-git', action='store_true')
    args = parser.parse_args()
    if args.verify_git:
        verify_git()
    else:
        seal()
