"""Archive this batch's original bytes and seal only its direct evidence."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = Path('D:/he_m4_global_local_001')
BASELINE = 'c041d4f038f72215aa4107a26fcbfd36aa53dd31'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def files_under(directory):
    paths = []
    for current, directories, files in os.walk(directory, followlinks=False):
        for name in directories + files:
            path = Path(current) / name
            if path.is_symlink() or path.is_junction():
                raise ValueError('reparse_entry/' + str(path))
            path.resolve().relative_to(directory.resolve())
        paths.extend(Path(current) / name for name in files)
    return sorted(paths)


def runtime_snapshot():
    return [(path.relative_to(RUNTIME).as_posix(), path.stat().st_size, sha(path)) for path in files_under(RUNTIME)]


def archive():
    before = runtime_snapshot()
    destination = HERE / 'runtime_archive'
    destination.mkdir(exist_ok=False)
    rows = []
    for index, (relative, size, digest) in enumerate(before, 1):
        original = RUNTIME / relative
        target = destination / ('f' + str(index).zfill(6) + '_' + original.name[:110])
        with original.open('rb') as incoming, target.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if target.stat().st_size != size or sha(target) != digest or original.read_bytes() != target.read_bytes():
            raise ValueError('runtime_archive_changed/' + relative)
        rows.append(dict(relative=relative, archive=target.relative_to(HERE).as_posix(), bytes=size, sha256=digest))
    if runtime_snapshot() != before:
        raise ValueError('runtime_changed_during_archive')
    result = dict(schema='m4-global-local-runtime-archive-v1', runtime_root=str(RUNTIME), files=rows,
                  file_count=len(rows), bytes=sum(row['bytes'] for row in rows), runtime_exclusions=[],
                  original_runtime_retained=True, all_copies_verified_byte_exact=True)
    save(HERE / 'RUNTIME_ARCHIVE.json', result)
    print(json.dumps(dict(files=len(rows), bytes=result['bytes'], exclusions=0)))


def scan(raw, name, findings):
    patterns = (rb'\b(?:sk-proj-|sk-)[A-Za-z0-9_-]{24,}', rb'\bgh[pousr]_[A-Za-z0-9]{25,}',
                rb'\bgithub_pat_[A-Za-z0-9_]{30,}', rb'\bya29\.[A-Za-z0-9_-]{25,}',
                rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
    if any(re.search(pattern, raw) for pattern in patterns):
        findings.append(name)
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
            for member in zipped.infolist():
                if not member.is_dir():
                    scan(zipped.read(member), name + '!' + member.filename, findings)


def seal():
    frozen = read(HERE / 'FROZEN.json')
    for row in frozen['files']:
        path = HERE / row['relative']
        if sha(path) != row['sha256'] or path.stat().st_size != row['bytes']:
            raise ValueError('frozen_source_changed/' + row['relative'])
    preparation = read(HERE / 'PREEXEC_GIT.json')
    prefix = HERE.relative_to(ROOT).as_posix() + '/'
    committed = subprocess.check_output(['git', 'show', preparation['git'] + ':' + prefix + 'FROZEN.json'], cwd=ROOT)
    if committed != (HERE / 'FROZEN.json').read_bytes():
        raise ValueError('preexecution_git_freeze')
    decision = read(HERE / 'DECISION.json')
    review = read(HERE / 'RUNTIME_REVIEW.json')
    expected = decision['independent_geometry_passed'] and decision['saved_frame_passed'] and review['passed_checked_scope']
    if decision['accepted_qualification'] != expected:
        raise ValueError('decision_review_conjunction')
    for name, digest in decision['report_pins'].items():
        if sha(HERE / name) != digest:
            raise ValueError('decision_report_changed/' + name)
    if not (HERE / 'REPORT.md').is_file():
        raise ValueError('root_report_required')
    baseline = read(HERE / 'BASELINE.json')
    for row in baseline['protected_direct_seals']:
        if sha(row['path']) != row['sha256']:
            raise ValueError('direct_prior_seal_changed')
    archive_record = read(HERE / 'RUNTIME_ARCHIVE.json')
    original = runtime_snapshot()
    if [(row['relative'], row['bytes'], row['sha256']) for row in archive_record['files']] != original:
        raise ValueError('original_archive_set_changed')
    for row in archive_record['files']:
        if sha(HERE / row['archive']) != row['sha256']:
            raise ValueError('archived_original_changed')
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASELINE], cwd=ROOT, text=True).splitlines()
    if any(not path.startswith(prefix) for path in changed):
        raise ValueError('changes_outside_qualification_namespace')
    findings = []
    current = files_under(HERE)
    for path in current:
        scan(path.read_bytes(), str(path), findings)
    if findings:
        raise ValueError('credential_pattern_detected/' + repr(findings))
    result = dict(schema='m4-global-local-final-audit-v1', passed=True, frozen_files=len(frozen['files']),
                  prior_direct_seals=len(baseline['protected_direct_seals']), prior_manifest_members_expanded=0,
                  runtime_files=len(original), runtime_bytes=archive_record['bytes'], runtime_exclusions=[],
                  product_diff_paths=[], credential_scan_files=len(current), credential_findings=[],
                  pending_administrator_review=True)
    save(HERE / 'FINAL_AUDIT.json', result)
    entries = []
    for path in files_under(HERE):
        entries.append(dict(relative=path.relative_to(HERE).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    save(HERE / 'CONTENT_MANIFEST.json', dict(schema='m4-global-local-content-manifest-v1', files=entries,
        member_count=len(entries), excludes_self_only=True))
    print(json.dumps(dict(sealed=True, content_members=len(entries), runtime_files=len(original))))


def verify_git():
    manifest = read(HERE / 'CONTENT_MANIFEST.json')
    expected = {row['relative'] for row in manifest['files']} | {'CONTENT_MANIFEST.json'}
    prefix = HERE.relative_to(ROOT).as_posix() + '/'
    tracked = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', 'HEAD', '--', prefix], cwd=ROOT, text=True).splitlines()
    if {path[len(prefix):] for path in tracked} != expected:
        raise ValueError('committed_namespace_member_set')
    for relative in sorted(expected):
        actual = subprocess.check_output(['git', 'show', 'HEAD:' + prefix + relative], cwd=ROOT)
        if actual != (HERE / relative).read_bytes():
            raise ValueError('committed_blob_bytes/' + relative)
    print(json.dumps(dict(git_exact_members=len(expected), passed=True)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('archive', 'seal', 'verify-git'))
    action = parser.parse_args().operation
    {'archive': archive, 'seal': seal, 'verify-git': verify_git}[action]()
