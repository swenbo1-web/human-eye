"""Verify immutable evidence and publish this module's final audit and manifest."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import zipfile


HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
PRODUCT = ROOT / 'human_eye_plugin/live_spatial_mcp.py'
BASELINE = '1f3db153d4a46363ed3e64103d495bbc5ee65864'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def verify_pins(pins):
    for path, expected in pins.items():
        require(sha(path) == expected, 'changed pinned path ' + path)
    return len(pins)


def verify_sources():
    frozen = read(HERE / 'FROZEN.json')
    qualification = read(HERE / 'admin/QUALIFICATION_SEAL.json')
    quality = read(HERE / 'admin/QUALITY_SEAL.json')
    baseline = read(HERE / 'BASELINE.json')
    counts = {
        'frozen_inputs_verified': verify_pins(frozen['files_sha256']),
        'qualification_seal_pins_verified': verify_pins(qualification['files_sha256']),
        'quality_seal_pins_verified': verify_pins({row['path']: row['sha256'] for row in quality['inputs']}),
        'old_protected_manifests_verified': verify_pins(baseline['old_protected_manifests']),
    }
    require(len(quality['inputs']) == counts['quality_seal_pins_verified'] == 4526, 'quality pin denominator')
    require(counts['frozen_inputs_verified'] == 2708, 'frozen denominator')
    require(counts['qualification_seal_pins_verified'] == 126, 'qualification denominator')
    require(counts['old_protected_manifests_verified'] == 9, 'protected denominator')
    plan = read(HERE / 'PLAN.json')
    for arm in ('A', 'B'):
        specification = plan['products'][arm]
        require(sha(specification['path']) == specification['sha256'], 'product binding ' + arm)
        binding = read(specification['path'])
        install = Path(binding['install_root'])
        for row in binding['source_manifest']:
            require(sha(install / row['path']) == row['sha256'], 'installed source ' + arm + '/' + row['path'])
        identity = {
            'base_version': binding['base_version'],
            'implementation_revision': binding['implementation_revision'],
            'files': binding['source_manifest'],
        }
        aggregate = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        require(aggregate == binding['source_sha256'], 'source aggregate ' + arm)
        counts[arm + '_installed_sources_verified'] = len(binding['source_manifest'])
        require(counts[arm + '_installed_sources_verified'] == 141, 'source denominator ' + arm)
    for row in read(HERE / 'SOURCE_FREEZE.json')['runtime_manifest']:
        require(sha(ROOT / row['path']) == row['sha256'], 'working product source ' + row['path'])
    require(sha(PRODUCT) == '2be839c39ffcc5bde5fa92d7b028f8f9e5e8ab34d65aed90a51037f1a74503f5', 'product candidate bytes')
    return counts


def verify_archive():
    archive = read(HERE / 'RUNTIME_ARCHIVE.json')
    total = 0
    for row in archive['files']:
        original = Path(row['original_path'])
        copy = HERE / row['archive_path']
        require(sha(original) == sha(copy) == row['sha256'], 'archive bytes ' + row['relative_path'])
        require(original.stat().st_size == copy.stat().st_size == row['bytes'], 'archive size')
        total += row['bytes']
    require(len(archive['files']) == archive['file_count'] == 970, 'archive denominator')
    require(total == archive['bytes'] == 25394343, 'archive bytes total')
    return {'runtime_archive_files_verified': len(archive['files']), 'runtime_archive_bytes': total}


def credential_scan():
    # Preserve evidence bytes. Report only paths and rule names for any candidate.
    patterns = {
        'openai_token': re.compile(rb'(?<![A-Za-z0-9])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}'),
        'github_classic_token': re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
        'github_fine_grained_token': re.compile(rb'github_pat_[A-Za-z0-9_]{40,}'),
        'google_api_key': re.compile(rb'AIza[A-Za-z0-9_-]{35}'),
        'private_key_header': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    }
    private_names = {'auth.json', 'credentials.json', 'token.json', '.env', 'id_rsa', 'id_ed25519'}
    findings = []
    scanned = 0
    container_members = 0
    paths = [PRODUCT] + sorted(path for path in HERE.rglob('*') if path.is_file())
    for path in paths:
        scanned += 1
        relative = path.relative_to(ROOT).as_posix()
        if path.name.lower() in private_names:
            findings.append({'path': relative, 'rule': 'credential_filename'})
        blob = path.read_bytes()
        for name, pattern in patterns.items():
            if pattern.search(blob):
                findings.append({'path': relative, 'rule': name})
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as container:
                for member in container.infolist():
                    container_members += 1
                    if Path(member.filename).name.lower() in private_names:
                        findings.append({'path': relative + '!' + member.filename, 'rule': 'credential_filename'})
                    member_blob = container.read(member)
                    for name, pattern in patterns.items():
                        if pattern.search(member_blob):
                            findings.append({'path': relative + '!' + member.filename, 'rule': name})
    require(not findings, 'credential scan candidates ' + json.dumps(findings))
    return {
        'credential_pattern_scan_matches': len(findings),
        'credential_scan_file_count': scanned,
        'credential_scan_container_member_count': container_members,
        'credential_scan_scope': list(patterns) + ['credential_filenames'],
    }


def verify_git():
    manifest = read(HERE / 'CONTENT_MANIFEST.json')
    expected = {row['path'] for row in manifest['files']}
    expected.add((HERE / 'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix())
    changed = set(subprocess.check_output(['git', 'diff', '--name-only', '--cached', BASELINE], cwd=ROOT).decode().splitlines())
    require(changed == expected, 'staged paths differ from manifest')
    index = {}
    for line in subprocess.check_output(['git', 'ls-files', '--stage'], cwd=ROOT).decode().splitlines():
        info, path = line.split('\t', 1)
        mode, object_id, stage = info.split()
        require(stage == '0', 'unmerged index ' + path)
        index[path] = object_id
    for path in expected:
        blob = (ROOT / path).read_bytes()
        blob_hash = hashlib.sha1(b'blob ' + str(len(blob)).encode() + b'\0' + blob).hexdigest()
        require(index[path] == blob_hash, 'Git blob bytes changed ' + path)
    for row in manifest['files']:
        require(sha(ROOT / row['path']) == row['sha256'], 'manifest changed ' + row['path'])
    print(json.dumps({'staged_paths': len(expected), 'Git_blob_bytes_match': True, 'manifest_paths_match_baseline_diff': True}))


def seal(cost_review):
    require(not (HERE / 'FINAL_AUDIT.json').exists(), 'final audit already exists')
    counts = verify_sources()
    counts.update(verify_archive())
    quality = read(HERE / 'admin/QUALITY.json')
    cost = read(HERE / 'COST.json')
    require(quality['all_six_quality_complete'] and quality['denominator'] == 6, 'six quality gates')
    require(quality['B_actual_source_binding_adoption_count'] == 3, 'binding adoption')
    require(cost['decision']['limited_positive_signal'] is True, 'fixed candidate decision')
    runtime = read(HERE / 'FINAL_RUNTIME_REVIEW.json')
    require(runtime['passed'] is True, 'runtime review')
    semantic = read(HERE / 'admin/SEMANTIC_DATAFLOW_REVIEW.json')
    require(semantic['passed'] is True, 'semantic review')
    review = read(HERE / cost_review)
    require(review['passed'] is True, 'independent cost review')
    counts.update(credential_scan())
    artifacts = [
        'ADMINISTRATOR_PLAN.md', 'PLAN.json', 'FROZEN.json', 'build/RUN_BINDING.json',
        'ENGINEERING_REPORT.json', 'DIRECTED_ACCEPTANCE.json', 'admin/QUALIFICATION.json',
        'admin/QUALIFICATION_SEAL.json', 'admin/NORMALIZED.json', 'admin/QUALITY.json',
        'admin/QUALITY_SEAL.json', 'admin/SEMANTIC_DATAFLOW_REVIEW.json',
        'FINAL_RUNTIME_REVIEW.json', 'PROTOCOL_MATCHER_REVIEW.json', 'COST.json', cost_review,
        'DECISION.json', 'REPORT.md', 'RUNTIME_ARCHIVE.json', 'AL_COMPLETION_CONTEXT.json',
    ]
    audit = {
        'schema': 'source-face-binding-root-final-audit-v1',
        'task': 'M1-SOURCE-FACE-BINDING-001',
        'baseline_git': BASELINE,
        'engineering_git': '91b323d90b814ce2b306e9bb2f51c5964406044c',
        'formal_preparation_git': 'd7ee367251e225a0d280dca68c84b115e166b860',
        'branch': 'codex/m1-source-face-binding-001',
        'passed': True,
        'completion_for_administrator_review': True,
        'administrator_review': 'pending',
        'AL_task_registration': 'pending_current_chat_host_binding',
        'artifacts_sha256': {path: sha(HERE / path) for path in artifacts},
        'first_content_scoring_matrix_invocations': 1,
        'full_final_quality_passed': 6,
        'full_final_quality_denominator': 6,
        'B_actual_binding_adoption': 3,
        'actual_comparison_model_consumers': 6,
        'actual_qualification_model_consumers': 0,
        'actual_qualification_rasters': 6,
        'actual_formal_rasters': 24,
        'actual_batch_rasters': 30,
        'outer_retries': 0,
        'unrun_slots': 0,
        'limited_positive_signal': True,
        'reviewer_associations_disclosed': True,
        'source_scopes': 'New verification namespace and the single product file. Execution sources frozen before qualification/formal; post-run analysis scripts are recorded separately.',
        'before_publication_ns': time.monotonic_ns(),
        **counts,
    }
    dump(HERE / 'FINAL_AUDIT.json', audit)
    files = [PRODUCT] + sorted(path for path in HERE.rglob('*') if path.is_file() and path.name != 'CONTENT_MANIFEST.json')
    rows = [{'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in files]
    rows.sort(key=lambda row: row['path'])
    manifest = {
        'schema': 'source-face-binding-final-content-manifest-v1',
        'baseline_git': BASELINE,
        'scope': 'Exactly the new module namespace plus human_eye_plugin/live_spatial_mcp.py. This manifest excludes itself.',
        'file_count': len(rows),
        'bytes': sum(row['bytes'] for row in rows),
        'files': rows,
    }
    dump(HERE / 'CONTENT_MANIFEST.json', manifest)
    print(json.dumps({'passed': True, **counts, 'content_files': len(rows), 'audit_sha256': sha(HERE / 'FINAL_AUDIT.json'), 'manifest_sha256': sha(HERE / 'CONTENT_MANIFEST.json')}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cost-review', default='COST_REVIEW_R1.json')
    parser.add_argument('--verify-git', action='store_true')
    arguments = parser.parse_args()
    if arguments.verify_git:
        verify_git()
    else:
        seal(arguments.cost_review)


if __name__ == '__main__':
    main()
