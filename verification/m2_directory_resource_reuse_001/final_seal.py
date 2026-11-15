"""Seal this bounded read-only qualification after independent source checks."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASELINE = '8f2a739e789b777358d84a168154bc7c50b929e5'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, label):
    if not condition:
        raise AssertionError(label)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def pins(rows, root):
    for row in rows:
        path = Path(row['path'])
        path = path if path.is_absolute() else root / path
        require(sha(path) == row['sha256'], 'pinned bytes ' + str(path))
        if 'bytes' in row:
            require(path.stat().st_size == row['bytes'], 'pinned size ' + str(path))
    return len(rows)


def directory_packet(value):
    if isinstance(value, dict):
        if value.get('result_kind') == 'scene_directory':
            return value
        for item in value.values():
            found = directory_packet(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = directory_packet(item)
            if found is not None:
                return found
    elif isinstance(value, str) and value.lstrip().startswith('{'):
        try:
            return directory_packet(json.loads(value))
        except ValueError:
            pass
    return None


def root_checks():
    baseline = read(HERE / 'BASELINE.json')
    for path, expected in baseline['protected_old_pins'].items():
        require(sha(path) == expected, 'old protected source ' + path)
    old_root = Path('C:/Users/Administrator/.codex/worktrees/m1-source-face-binding-001/hefe')
    old_manifest = read(old_root / 'verification/m1_source_face_binding_001/CONTENT_MANIFEST.json')
    require(pins(old_manifest['files'], old_root) == 1116, 'M1 sealed denominator')
    binding = read(ROOT / 'verification/m1_source_face_binding_001/build/RUN_BINDING.json')
    require(pins(binding['source_manifest'], ROOT) == 141, 'working source denominator')
    require(pins(binding['source_manifest'], Path(binding['install_root'])) == 141, 'installed source denominator')
    identity = {key: binding[key] for key in ('base_version', 'implementation_revision')}
    identity['files'] = binding['source_manifest']
    aggregate = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    require(aggregate == binding['source_sha256'] == '3748d88b618db7de1347d632f2a68f3ed82a2ebb8a6321586fe756be07ea8148', 'baseline aggregate')
    plan_sha = '19c991d42ac17d0b8e38cfe7286c2c4c28fc4dd554c2e25c29fd52cc41d2cf21'
    require(sha(HERE / 'ADMINISTRATOR_PLAN.md') == plan_sha, 'plan copy')
    root_planning_commit = '81c9f817505278b3ed88329a46a62471b0d364f8'
    for filename, copied in (
        ('M2_DIRECTORY_RESOURCE_REUSE_001_PLAN.md', 'ADMINISTRATOR_PLAN.md'),
        ('M1_M5_PROGRESS_AND_NEXT_PLAN_20261115.md', 'M1_M5_ROUTE.md'),
    ):
        blob = subprocess.check_output(['git', 'show', root_planning_commit + ':docs/' + filename], cwd=ROOT)
        require(blob == (HERE / copied).read_bytes(), 'planning commit source ' + filename)
    m2 = read(HERE / 'M2_TRACE_REVIEW.json')
    m4 = read(HERE / 'M4_TRACE_REVIEW.json')
    source = read(HERE / 'SOURCE_ELIGIBILITY_REVIEW.json')
    context = read(HERE / 'CONTEXT_TRACE_INVENTORY.json')
    framed = read(HERE / 'FRAMED_TX_REVIEW.json')
    m2_pins = pins(m2['source_inventory']['pins'], Path(m2['source_inventory']['root']))
    require(m2_pins == 4702, 'M2 inventory denominator')
    m4_pins = pins(m4['input_files'], ROOT)
    require(m4_pins == 1622, 'M4 input denominator')
    source_pins = pins(source['evidence_pins'], ROOT) + pins(source['source_inventory'], ROOT)
    context_pins = pins(context['files'], ROOT)
    require(context_pins == 2221 and not context['parse_errors'], 'context denominator')
    d = m2['denominators']
    require(d['actual_host_task_sessions'] == 42 == len(m2['cases']), 'M2 sessions')
    require(d['read_business_records'] == 368, 'M2 business reads')
    require(d['product_directory_records'] == 139, 'M2 directory count')
    require(d['product_directory_cache'] == {'miss': 41, 'hit': 98}, 'M2 cache count')
    classifications = dict(d['classification_counts'])
    require(classifications.pop('shutdown') == 1 and sum(classifications.values()) == 368, 'M2 exhaustive classifications')
    require(len(m2['candidates']) == 3 and all(c['record']['packet']['cache_hit'] for c in m2['candidates']), 'post-resource cache candidates')
    require(d['resource_counts_before_first_new_directory'] == [0] * 12, 'cold directory before resource')
    require(d['scripted_freshness_mutation_directory_records'] == 26, 'mutation unknown count')
    prior = ROOT / 'verification/m2_tight_directory_001/correctness'
    for case in ('entry_01', 'entry_02'):
        after = directory_packet(read(prior / case / 'directory_after_full.RESPONSE.json'))
        cold = directory_packet(read(prior / case / 'directory_cold.RESPONSE.json'))
        require(after['cache_hit'] is True and cold['cache_hit'] is False, 'actual MCP directory cache ' + case)
        require(after['capture_state'] == cold['capture_state'], 'actual MCP host state ' + case)
    require((prior / 'typed_01/directory_after_selected.json').read_bytes() == (prior / 'typed_01/directory_hot.json').read_bytes(), 'actual typed cache byte equality')
    live = ROOT / 'verification/m4_active_observation_host_bridge_001'
    actual = live / 'external_archive/run/acceptance_02'
    request = read(actual / 'stdio/rpc_08/TX.bin')
    require(request['id'] == 'old_readonly_regression' and request['params']['arguments']['query'] == {'mode': 'directory'}, 'actual tight directory request')
    protocol = read(live / 'HARNESS_PROTOCOL.json')
    require(protocol['fixed_requests'][-1]['id'] == request['id'], 'predeclared compatibility purpose')
    directory = directory_packet(read(actual / 'stdio/rpc_08/RX.bin'))
    capture = read(actual / 'server/CAPTURE_03.json')
    require(directory['cache_hit'] is False and directory['schema'] == 'human-eye-directory-v1', 'actual directory miss')
    for key in ('instance_id', 'epoch', 'revision'):
        require(directory['capture_state'][key] == capture['capture_state'][key], 'technical host state ' + key)
    require(directory['binding']['host_identity']['object_instances'] == capture['host_identity']['object_instances'], 'technical object incarnation')
    require(directory['binding']['host_source_sha256'] == sha(ROOT / 'human_eye_plugin/blender_host.py'), 'historical current same host file')
    require(m4['technical_reuse_opportunity_count'] == 1 and m4['qualified_natural_task_hits'] == 0, 'M4 qualified gate')
    require(m4['scope']['actual_host_session_denominator_with_directory_observation'] == 26, 'M4 host denominator')
    require(source['conclusion']['qualified_natural_task_hit_count'] == 0 and source['conclusion']['real_host_technical_example_count'] == 1, 'independent source gate')
    require(m2['natural_task_hit_count'] == 0, 'M2 natural gate')
    require(framed['file_count'] == 14 and framed['message_count'] == 79 and framed['tool_call_messages'] == 37, 'framed supplementary denominator')
    require(not framed['errors'] and not framed['explicit_directory_requests'] and not framed['capture_directory_text_occurrences'], 'framed supplementary outcomes')
    require(pins(framed['records'], ROOT) == 14, 'framed source pins')
    require(not Path('D:/he_directory_reuse_001').exists(), 'no experimental runtime created')
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASELINE], cwd=ROOT).decode().splitlines()
    prefix = HERE.relative_to(ROOT).as_posix() + '/'
    require(all(path.startswith(prefix) for path in changed), 'only new namespace tracked changes')
    return {
        'protected_old_pins_verified': len(baseline['protected_old_pins']),
        'old_M1_manifest_files_verified': len(old_manifest['files']),
        'working_product_sources_verified': 141,
        'accepted_isolated_install_sources_verified': 141,
        'M2_source_files_verified': m2_pins,
        'M4_input_files_verified': m4_pins,
        'independent_source_review_pins_verified': source_pins,
        'context_JSON_JSONL_files_verified': context_pins,
        'framed_TX_original_files_verified': 14,
        'actual_raw_cache_and_compatibility_controls_verified': True,
        'planning_commit': root_planning_commit,
        'qualified_natural_task_hits': 0,
        'historical_real_host_technical_examples': 1,
        'product_source_aggregate': aggregate,
    }


def scan_credentials():
    patterns = (
        re.compile(rb'(?<![A-Za-z0-9])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}'),
        re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
        re.compile(rb'github_pat_[A-Za-z0-9_]{40,}'),
        re.compile(rb'AIza[A-Za-z0-9_-]{35}'),
        re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    )
    files = sorted(path for path in HERE.rglob('*') if path.is_file())
    findings = []
    for path in files:
        blob = path.read_bytes()
        if path.name.lower() in {'auth.json', 'credentials.json', '.env', 'token.json'} or any(pattern.search(blob) for pattern in patterns):
            findings.append(str(path.relative_to(ROOT)))
    require(not findings, 'credential pattern candidates ' + repr(findings))
    return {'credential_scan_file_count': len(files), 'credential_pattern_candidates': len(findings)}


def verify_git():
    manifest = read(HERE / 'CONTENT_MANIFEST.json')
    expected = {row['path'] for row in manifest['files']} | {(HERE / 'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix()}
    changed = set(subprocess.check_output(['git', 'diff', '--cached', '--name-only', BASELINE], cwd=ROOT).decode().splitlines())
    require(changed == expected, 'staged baseline path closure')
    index = {}
    for row in subprocess.check_output(['git', 'ls-files', '--stage'], cwd=ROOT).decode().splitlines():
        fields, path = row.split('\t', 1)
        mode, digest, stage = fields.split()
        require(stage == '0', 'unmerged index')
        index[path] = digest
    for path in expected:
        blob = (ROOT / path).read_bytes()
        digest = hashlib.sha1(b'blob ' + str(len(blob)).encode() + b'\0' + blob).hexdigest()
        require(digest == index[path], 'Git blob parity ' + path)
    pins(manifest['files'], ROOT)
    print(json.dumps({'manifest_and_staged_paths': len(expected), 'Git_blob_byte_parity': True}))


def seal():
    require(not (HERE / 'FINAL_AUDIT.json').exists(), 'already sealed')
    checks = root_checks()
    counts = scan_credentials()
    baseline = read(HERE / 'BASELINE.json')
    now = time.monotonic_ns()
    ledger = {
        'schema': 'm2-directory-reuse-qualification-ledger-v1',
        'phase': 'bounded_existing_trace_qualification',
        'actual_owned_Blender_starts': 0, 'qualification_max_owned_Blender_starts': 2,
        'actual_product_observations': 0, 'actual_rasters': 0,
        'actual_experiment_model_consumers': 0, 'actual_paid_experiment_API_calls': 0,
        'actual_product_candidates': 0, 'actual_hot_optimization_attempts': 0,
        'formal_status': 'not_run_no_qualified_natural_sequence', 'actual_formal_slots': 0,
        'experimental_model_tokens_and_cost': 'not_run',
        'coordinator_and_reviewer_model_tokens': None, 'coordinator_and_reviewer_cash': None,
        'complete_human_cost': None, 'experimental_performance_and_memory': None,
        'analysis_registered_ns': baseline['started_ns'], 'qualification_audit_closed_ns': now,
        'registered_analysis_elapsed_ns': now - baseline['started_ns'],
        'time_scope': 'BASELINE registration through final qualification audit. Initial plan reads, delegation and managed worktree setup precede registration. Internal analysis and reviewer durations are nested or unmeasured.',
    }
    dump(HERE / 'QUALIFICATION_LEDGER.json', ledger)
    files = sorted(path for path in HERE.rglob('*') if path.is_file())
    audit = {
        'schema': 'm2-directory-reuse-final-root-audit-v1',
        'baseline_git': BASELINE, 'disposition': 'not_actionable', 'passed': True,
        'scope': 'Qualification evidence and new namespace only. Product files are baseline-identical.',
        'reviewer_associations_disclosed': True,
        'administrator_review': 'pending', 'AL_task_registration': 'pending_current_chat_host_binding',
        'artifacts_sha256': {path.relative_to(HERE).as_posix(): sha(path) for path in files},
        **checks, **counts,
    }
    dump(HERE / 'FINAL_AUDIT.json', audit)
    rows = [
        {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        for path in sorted(HERE.rglob('*')) if path.is_file() and path.name != 'CONTENT_MANIFEST.json'
    ]
    manifest = {'schema': 'm2-directory-reuse-content-manifest-v1', 'baseline_git': BASELINE,
                'scope': 'The new verification namespace only. Manifest excludes itself.',
                'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows), 'files': rows}
    dump(HERE / 'CONTENT_MANIFEST.json', manifest)
    print(json.dumps({'passed': True, **checks, **counts, 'files': len(rows),
                      'audit_sha256': sha(HERE / 'FINAL_AUDIT.json'),
                      'manifest_sha256': sha(HERE / 'CONTENT_MANIFEST.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-git', action='store_true')
    arguments = parser.parse_args()
    if arguments.verify_git:
        verify_git()
    else:
        seal()
