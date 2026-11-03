"""Bounded, offline migration qualification in exclusive QA copies only.

The fixed source installations and production configuration are read-only.
This runner never invokes a host, saves an asset, or opens an API credential.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'verification/fixes/20261103_deployment_core_projection'
PYTHON = ROOT / '.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe'
OLD = ROOT / '.human-eye/releases/9.7.2+20261031.dense.focus.r1'
NEW = ROOT / '.human-eye/releases/9.7.2+20261103.safety.source.r1'
CORE = ROOT / '.human-eye/releases/9.7.2+20261103.core.facts.r1'
OLD_BUILD = 'sha256:22fb2523bdbfb68d6e7227ea3df3b4373daa1a76461344bc1755406c5feeec8a'
NEW_BUILD = 'sha256:3fa7dfb05b6796044b2b4d37e2e67e7def8957ce3a471879d2e9b8f142006ef2'
CORE_BUILD = 'sha256:dbeb471f3120bdb133b1ca1669dbbbd525e4679a9ec1949bc67fdba171182c47'
CASES = {
    'cross_fixed_launcher_baseline': 'Unmodified 124 admin rejects the distinct trusted 78 launcher; no writes.',
    'explicit_prior_trust': 'Only canonical explicit entry SHA/build pins, matching prior connector identity, admit cross-release recognition.',
    'retained_history': 'Completed receipts, consumed budgets, current known commits, raw formatting survive forward binding-only migration.',
    'latest_state_reverse': 'Reverse plan reads newest state; additional commits and consumed budgets remain; no state backup restore.',
    'stale_plan': 'State/config/entry change after plan rejects before mutation.',
    'unresolved_state': 'Pending, inflight, quarantine, unfinished goal, unknown schema refuse for their exact intended reasons.',
    'unknown_source': 'Unknown wrapper, wrong prior hash/build, changed binding and unused pins fail closed.',
    'transaction_interleaving': 'Concurrent edits are retained; incomplete rollback retains fence; successful rollback restores only safe binding.',
    'locks': 'Setup and state locks are respected, not deleted or bypassed.',
    'reverse_incompatible': 'Old target refuses new state outside its import/ledger source schema rather than resetting it.',
    'fixed_originals': 'Formal config/hooks/connector/state and both installed releases retain original hashes.',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def record(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def protected_hashes():
    paths = [ROOT/'.codex/config.toml', ROOT/'.codex/hooks.json',
             ROOT/'.human-eye/live-connector.routing-spatial.json',
             ROOT/'.human-eye/live-state.routing-spatial.json']
    for release in (OLD, NEW):
        paths.extend(path for path in release.rglob('*') if path.is_file())
    return {str(path): sha(path.read_bytes()) for path in sorted(set(paths))}


def preregister():
    record(EVIDENCE/'MIGRATION_PREREGISTERED.json', {
        'cases': CASES, 'production_activation_performed': False,
        'source_installs': {'old': str(OLD), 'new': str(NEW)},
        'expected_builds': {'old': OLD_BUILD, 'new': NEW_BUILD},
        'runner_sha256': sha(Path(__file__).read_bytes()),
        'admin_template_sha256': sha((ROOT/'examples/agents/installed_release.py').read_bytes()),
        'protected_before': protected_hashes(),
        'trust_model': 'Explicit operator entry SHA and expected build plus registered connector build; binding alone is not trust.',
        'qa_root': str(EVIDENCE/'MIGRATION_QA'),
        'rollback_rule': 'Replan against latest full state; change binding only; never restore historical state backup.',
    })


def preregister_core():
    binding = json.loads((CORE/'admin/RUNTIME_BINDING.json').read_text(encoding='utf-8'))
    if binding['identity']['build_id'] != CORE_BUILD or len(binding['source_files']) != 125:
        raise ValueError('New core candidate differs from the separately authorized 125-source build')
    record(EVIDENCE/'MIGRATION_CORE_PREREGISTERED.json', {
        'source_install': str(CORE), 'expected_build': CORE_BUILD, 'expected_source_file_count': 125,
        'scope': 'Additional 78-to-125 and latest-state reverse qualification, no repeated 25-case fault matrix.',
        'cases': ['explicit_prior_pin_and_actual_identity', 'readonly_doctor', 'forward_binding_only_and_commits',
                  'stale_reverse_refusal', 'latest_complete_state_reverse_and_budget_preservation', 'old_unknown_schema_refusal'],
        'protected_core_before': {str(path): sha(path.read_bytes()) for path in sorted(CORE.rglob('*')) if path.is_file()},
        'runner_sha256': sha(Path(__file__).read_bytes()), 'admin_template_sha256': sha((ROOT/'examples/agents/installed_release.py').read_bytes()),
        'production_activation_performed': False})


def load_entry(path, expected):
    raw = path.read_bytes()
    if sha(raw) != expected:
        raise ValueError('Entry SHA mismatch')
    spec = importlib.util.spec_from_file_location('_migration_qa_entry', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    proof = module.validate_binding(expected_python=sys.executable)
    registered = json.loads((EVIDENCE/'MIGRATION_PREREGISTERED.json').read_text(encoding='utf-8'))
    if path == CORE/'admin/target_runtime_entry.py':
        anchor = json.loads((EVIDENCE/'MIGRATION_CORE_PREREGISTERED.json').read_text(encoding='utf-8'))['protected_core_before']
        expected_admin = anchor[str(path.with_name('installed_release.py'))]
        expected_binding = anchor[str(path.with_name('RUNTIME_BINDING.json'))]
    elif path in (OLD/'admin/target_runtime_entry.py', NEW/'admin/target_runtime_entry.py'):
        expected_admin = registered['protected_before'][str(path.with_name('installed_release.py'))]
        expected_binding = registered['protected_before'][str(path.with_name('RUNTIME_BINDING.json'))]
    else:
        if not path.resolve().is_relative_to((EVIDENCE/'MIGRATION_QA').resolve()):
            raise ValueError('Unregistered QA bootstrap location')
        anchor = None
        for receipt_path in EVIDENCE.glob('MIGRATION_CANDIDATE_ADMIN_*.json'):
            for value in json.loads(receipt_path.read_text(encoding='utf-8'))['clones'].values():
                if Path(value['entry']) == path:
                    if anchor is not None:
                        raise ValueError('Ambiguous QA candidate trust record')
                    anchor = value
        if anchor is None:
            raise ValueError('QA administration candidate was not registered before execution')
        expected_admin, expected_binding = anchor['admin_sha256'], anchor['binding_sha256']
    if proof['admin_sha256'] != expected_admin or proof['binding_sha256'] != expected_binding:
        raise ValueError('Administration/binding differs from its pre-execution external trust record')
    sys.path.insert(0, proof['module_root'])
    module.verify_imported_runtime(proof)
    return module, proof


def registered_entry_sha(path):
    """Independent entry anchor from the before-edit preregistration, not a receipt."""
    registered = json.loads((EVIDENCE/'MIGRATION_PREREGISTERED.json').read_text(encoding='utf-8'))
    for original in (OLD, NEW):
        if path.parent.parent.name == original.name:
            return registered['protected_before'][str(original/'admin/target_runtime_entry.py')]
    if path.parent.parent.name == CORE.name:
        core = json.loads((EVIDENCE/'MIGRATION_CORE_PREREGISTERED.json').read_text(encoding='utf-8'))
        return core['protected_core_before'][str(CORE/'admin/target_runtime_entry.py')]
    raise ValueError('Bootstrap release is outside the fixed two-source qualification')


def load_admin(entry, proof):
    path = Path(proof['entry']).with_name('installed_release.py')
    raw = path.read_bytes()
    if sha(raw) != proof['admin_sha256']:
        raise ValueError('Admin SHA mismatch')
    spec = importlib.util.spec_from_file_location('_migration_qa_admin', path)
    admin = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = admin
    exec(compile(raw, str(path), 'exec', dont_inherit=True), admin.__dict__)
    admin._FIXED_TARGET_BOOTSTRAP = entry
    return admin


def add_commit(state, identity):
    """Synthetic completed journal; deliberately no host/setter or API calls."""
    import copy
    from human_eye_plugin import goal_journal as journal
    req = {'solver': 'support_plane', 'focal_id': 'part', 'reference_id': 'base',
           'reference_triangle_index': 2, 'direction_world': [0, 0, 1],
           'target_clearance_m': .001, 'clearance_tolerance_m': 1e-6,
           'max_steps': 8, 'max_step_translation_m': .001,
           'max_total_translation_m': .008, 'max_duration_s': 30.}
    domain, now = 'migration-synthetic-clock', 100.
    goal, child, session, segment = [value + identity for value in ('goal-', 'child-', 'session-', 'segment-')]
    journal.create_goal(state, goal, session, clock_domain=domain, now=now)
    req = journal.reserve_segment(state, goal, child, req, clock_domain=domain, now=now)['request']
    journal.mark_dispatched(state, goal, child, session, req, clock_domain=domain, now=now)
    before, after, motion = 'synthetic-before-' + identity, 'synthetic-after-' + identity, .0005
    step = {'step_id': segment + '-step-0', 'step_index': 0, 'state': 'complete',
            'operation_id': segment + '-op-0', 'action': {'focal_id': 'part', 'reference_id': 'base',
            'translation': [0., 0., -motion], 'rotation_euler_deg': [0., 0., 0.]},
            'result': {'status': 'verified', 'executed': True, 'verified': True,
            'execution_verified': True, 'actual_scene_revision': after,
            'goal_evaluation': None, 'task_succeeded': True, 'reason_codes': [],
            'receipt': {'host_execution_verified': True, 'focal_id': 'part',
                        'before_revision': before, 'after_revision': after}}, 'actual_translation_m': motion}
    receipt = {'request_id': child, 'segment_id': segment, 'request': copy.deepcopy(req),
               'steps': [step], 'status': 'satisfied', 'reason_codes': [], 'executed': True,
               'task_succeeded': True, 'actual_total_translation_m': motion,
               'base_revision': before, 'end_revision': after, 'replayed': False,
               'historical_receipt': False}
    fingerprint = sha(json.dumps({'session_id': session, 'request': req}, sort_keys=True,
                                ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode())
    state.setdefault('goal_segments', {'schema_version': '1.0', 'records': {}})['records'][child] = {
        'request_fingerprint': fingerprint, 'parent_goal_id': goal, 'segment_id': segment,
        'session_id': session, 'request': req, 'status': 'satisfied', 'steps': [step],
        'result': receipt, 'base_revision': before, 'end_revision': after}
    journal.confirm_segment(state, goal, child, physical_meter={
        'actual_setter_count': 1, 'actual_cumulative_translation_m': motion,
        'step_motions_m': [motion], 'rollback_count': 0, 'complete': True}, clock_domain=domain, now=102.)
    return journal.snapshot(state, goal, clock_domain=domain, now=102.)


def fixture_worker(entry_path, project):
    entry, proof = load_entry(entry_path, registered_entry_sha(entry_path))
    admin = load_admin(entry, proof)
    config_path = project / '.human-eye/connector.json'
    state_path = project / '.human-eye/state.json'
    identity = admin._target()['identity']
    config = {'schema_version': '1.0', 'enabled': False, 'observe_on_prompt': True,
              'project_root': proof['module_root'], 'state_file': 'state.json', 'audit_file': 'audit.jsonl',
              'quad_size': 64, 'max_sessions': 16, 'readback_atol_m': 1e-6,
              'blender': {'host': '127.0.0.1', 'port': 9876, 'timeout_s': 10},
              'expected_identity': {key: identity[key] for key in admin._PIN_FIELDS}}
    class NoHost:
        def capture_scene(self):
            raise AssertionError('Migration fixture must not capture a host')
        def apply_transform(self, *args, **kwargs):
            raise AssertionError('Migration fixture must not mutate a host')
    from human_eye_plugin.host_runtime import GuardedHostRuntime
    state = {'schema_version': '1.0', 'config_fingerprint': admin._fingerprint(config),
             'runtime': GuardedHostRuntime(NoHost(), quad_size=64, max_sessions=16).export_state(),
             'inflight': None, 'operator_note': '保留历史回执、预算、原始排版；仅合成测试。'}
    budget = add_commit(state, 'before-forward')
    state_raw = b'\xef\xbb\xbf' + json.dumps(state, ensure_ascii=False, indent=3).replace('\n', '\r\n').encode()
    admin._check_state(state_raw, config)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_bytes(admin._encode(config))
    state_path.write_bytes(state_raw)
    server = {'command': proof['dependency_python'], 'args': ['-I', '-B', str(entry_path), 'serve',
              '--config', str(config_path)], 'cwd': str(project), 'enabled': False,
              'startup_timeout_sec': 42, 'tool_timeout_sec': 65, 'env': {'USER_SETTING': 'preserve'}}
    text = '# independent QA third-party settings\r\n[mcp_servers.agent_learning]\r\ncommand = "learning"\r\nenabled = false\r\n\r\n[mcp_servers.human_eye_live]\r\n'
    for key, value in server.items():
        if key != 'env':
            text += key + ' = ' + json.dumps(value, ensure_ascii=False) + '\r\n'
    text += '[mcp_servers.human_eye_live.env]\r\nUSER_SETTING = "preserve"\r\n'
    (project/'.codex').mkdir(parents=True, exist_ok=True)
    (project/'.codex/config.toml').write_bytes(text.encode())
    hooks = {'hooks': {}, 'user_preference': {'disabled': True}}
    for event in admin.EVENTS:
        groups = []
        matchers = [None] if event == 'UserPromptSubmit' else [admin.TRANSFORM_MATCHER, admin.CLEARANCE_SEGMENT_MATCHER]
        for matcher in matchers:
            argv = [proof['dependency_python'], '-I', '-B', str(entry_path), 'hook',
                    '--agent', 'codex', '--event', event, '--config', str(config_path)]
            hook, _ = admin._hook_spec(argv, 'codex', 'windows')
            hook['timeout'] = 81
            group = {'hooks': [{'type': 'command', 'command': 'independent-thirdparty-audit', 'timeout': 4}, hook]}
            if matcher is not None:
                group['matcher'] = matcher
            groups.append(group)
        hooks['hooks'][event] = groups
    (project/'.codex/hooks.json').write_bytes(admin._encode(hooks))
    print(json.dumps({'fixture': 'synthetic_completed_goal', 'budget': budget, 'proof': proof}, ensure_ascii=False))


def baseline():
    project = EVIDENCE/'MIGRATION_QA/baseline'
    if project.exists() and any(project.iterdir()):
        raise ValueError('Baseline project is already populated')
    project.mkdir(parents=True, exist_ok=True)
    fixture = subprocess.run([str(PYTHON), '-I', '-B', str(Path(__file__).resolve()),
                              '--fixture-worker', '--entry', str(OLD/'admin/target_runtime_entry.py'),
                              '--project', str(project)], capture_output=True, text=True, encoding='utf-8', timeout=30)
    if fixture.returncode:
        raise RuntimeError(fixture.stderr)
    command = [str(PYTHON), '-I', '-B', str(NEW/'admin/target_runtime_entry.py'), 'admin', 'plan',
               '--agent', 'codex', '--project', str(project), '--expected-build', NEW_BUILD]
    before = {str(p): sha(p.read_bytes()) for p in project.rglob('*') if p.is_file()}
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=30)
    after = {str(p): sha(p.read_bytes()) for p in project.rglob('*') if p.is_file()}
    payload = {'command': command, 'returncode': result.returncode, 'stdout': result.stdout,
               'stderr': result.stderr, 'qa_unchanged': before == after, 'fixture': json.loads(fixture.stdout)}
    record(EVIDENCE/'MIGRATION_BASELINE.json', payload)
    if result.returncode != 2 or 'Unknown or modified fixed target bootstrap' not in result.stderr or before != after:
        raise AssertionError('Cross-fixed launcher baseline differs from preregistered counterexample')
    print('Baseline reproduced: original 124 admin refuses the fixed 78 launcher without modifying QA files.')


def clone_release(original, owner):
    """New QA administration generation; source/wheel and bootstrap stay fixed."""
    destination = owner/'.human-eye/releases'/original.name
    if not destination.resolve().is_relative_to((EVIDENCE/'MIGRATION_QA').resolve()):
        raise ValueError('QA clone escaped the registered root')
    shutil.copytree(original, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    entry = destination/'admin/target_runtime_entry.py'
    if sha(entry.read_bytes()) != registered_entry_sha(entry):
        raise ValueError('Copied entry differs from its independent preregistered SHA')
    template = (ROOT/'examples/agents/installed_release.py').read_bytes()
    admin, replacements = re.subn(rb'_TARGET_ENTRY_SHA256 = "[a-f0-9]{64}"',
        b'_TARGET_ENTRY_SHA256 = "' + sha(entry.read_bytes()).encode() + b'"', template)
    if replacements != 1:
        raise ValueError('Administration bootstrap pin was not uniquely templated')
    (destination/'admin/installed_release.py').write_bytes(admin)
    binding_path = destination/'admin/RUNTIME_BINDING.json'
    binding = json.loads(binding_path.read_text(encoding='utf-8'))
    binding.update(target_release=str(destination), site_packages=str(destination/'site-packages'),
                   admin_sha256=sha(admin))
    binding_path.write_text(json.dumps(binding, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    return {'release': str(destination), 'entry': str(entry), 'entry_sha256': sha(entry.read_bytes()),
            'admin_sha256': sha(admin), 'binding_sha256': sha(binding_path.read_bytes()),
            'admin_template_sha256': sha(template), 'source_sha256': binding['identity']['source_sha256'],
            'source_file_count': len(binding['source_files']), 'original_release': str(original),
            'original_admin_sha256': sha((original/'admin/installed_release.py').read_bytes()),
            'bootstrap_original_bytes_preserved': entry.read_bytes() == (original/'admin/target_runtime_entry.py').read_bytes(),
            'runtime_files_original_bytes_preserved': all((destination/'site-packages'/item['path']).read_bytes()
                == (original/'site-packages'/item['path']).read_bytes() for item in binding['source_files']),
            'administration_generation': 'explicit-prior-launcher-v1; distinct from original sealed admin'}


def managed_bytes(project):
    return {name: (project/name).read_bytes() for name in
        ('.codex/config.toml', '.codex/hooks.json', '.human-eye/connector.json', '.human-eye/state.json')}


def data_rows(state, admin):
    from human_eye_plugin import goal_journal as journal
    rows = {}
    for goal in state.get('goal_supervision', {}).get('records', {}):
        view = journal.snapshot(state, goal, clock_domain='migration-synthetic-clock', now=102.)
        rows[goal] = {key: view[key] for key in ('journal_status', 'confirmed_steps', 'actual_total_translation_m',
                    'segments_reserved', 'recoveries_used')}
    return rows


def operation_worker(entry_path, project, operation, prior_entry, prior_build):
    import copy
    from unittest.mock import patch
    entry, proof = load_entry(entry_path, registered_entry_sha(entry_path))
    admin = load_admin(entry, proof)
    target = admin._target()
    prior_pin = (str(prior_entry), registered_entry_sha(prior_entry), prior_build)
    state_path, config_path = project/'.human-eye/state.json', project/'.human-eye/connector.json'
    hooks_path, server_path = project/'.codex/hooks.json', project/'.codex/config.toml'
    def plan(pins=None):
        return admin.build_plan('codex', project, expected_build=target['identity']['build_id'],
                                platform='windows', prior_launcher_pins=[prior_pin] if pins is None else pins)
    def state_now():
        return json.loads(state_path.read_text(encoding='utf-8-sig'))
    def write_state(state):
        state_path.write_bytes(b'\xef\xbb\xbf'+json.dumps(state, ensure_ascii=False, indent=3).replace('\n','\r\n').encode())
    def refusal(action, expected):
        before = managed_bytes(project)
        try:
            action()
        except (admin.AgentSetupError, OSError, ValueError, TimeoutError) as exc:
            if expected not in str(exc):
                raise AssertionError('Wrong refusal; expected '+expected+' got '+str(exc)) from exc
            if managed_bytes(project) != before:
                raise AssertionError('Refusal mutated configuration or state')
            return {'expected': expected, 'actual_type': type(exc).__name__, 'actual': str(exc), 'managed_bytes_preserved': True}
        raise AssertionError('Expected refusal did not occur: '+expected)
    results = {'operation': operation, 'target': target, 'prior_pin': prior_pin,
               'physical_host_setters': 0, 'host_reads': 0, 'cases': {}}
    cases = results['cases']
    if operation == 'forward':
        original = managed_bytes(project)
        before = state_now()
        before_budgets = data_rows(before, admin)
        candidate = plan()
        preview = candidate.preview()
        if managed_bytes(project) != original:
            raise AssertionError('Read-only plan wrote managed files')
        applied = candidate.apply(plan_sha256=preview['plan_sha256'])
        after_raw = state_path.read_bytes()
        old_raw = admin._state_binding_bytes(after_raw, preview['state_migration']['new_config_fingerprint'],
                                             preview['state_migration']['old_config_fingerprint'])
        if old_raw != original['.human-eye/state.json']:
            raise AssertionError('Forward changed more than the raw top-level binding')
        after = state_now()
        if data_rows(after, admin) != before_budgets:
            raise AssertionError('Forward reset consumed budgets')
        import tomllib
        old_toml = tomllib.loads(original['.codex/config.toml'].decode())
        new_toml = tomllib.loads(server_path.read_text(encoding='utf-8'))
        if old_toml['mcp_servers']['agent_learning'] != new_toml['mcp_servers']['agent_learning']:
            raise AssertionError('Third-party MCP settings changed')
        hooks_before, hooks_after = [json.loads(value) for value in (original['.codex/hooks.json'], hooks_path.read_bytes())]
        groups = [group for values in hooks_after['hooks'].values() for group in values]
        if len(groups) != 5 or hooks_before['user_preference'] != hooks_after['user_preference']:
            raise AssertionError('Five hook groups or third-party preferences changed')
        if any(group['hooks'][0]['command'] != 'independent-thirdparty-audit' for group in groups):
            raise AssertionError('Third-party hooks changed')
        add_commit(after, 'after-forward')
        write_state(after)
        admin._check_state(state_path.read_bytes(), json.loads(config_path.read_text(encoding='utf-8')))
        cases['fingerprint_only'] = {'raw_bytes_except_binding_preserved': True, 'before_budgets': before_budgets,
                                    'after_new_commit_budgets': data_rows(after, admin), 'five_hook_groups': 5,
                                    'thirdparty_settings_preserved': True}
        results.update(plan=preview, apply=applied, latest_state_sha256=sha(state_path.read_bytes()))
    elif operation == 'reverse':
        original_raw = state_path.read_bytes()
        old_reverse = plan()
        latest = state_now()
        add_commit(latest, 'after-reverse-plan')
        write_state(latest)
        cases['stale_reverse'] = refusal(lambda: old_reverse.apply(plan_sha256=old_reverse.preview()['plan_sha256']),
                                          'Configuration/state changed after planning')
        latest_raw, latest_budgets = state_path.read_bytes(), data_rows(state_now(), admin)
        fresh = plan()
        preview = fresh.preview()
        applied = fresh.apply(plan_sha256=preview['plan_sha256'])
        final_raw = state_path.read_bytes()
        returned = admin._state_binding_bytes(state_path.read_bytes(), preview['state_migration']['new_config_fingerprint'],
                                             preview['state_migration']['old_config_fingerprint'])
        if returned != latest_raw or returned == original_raw:
            raise AssertionError('Rollback did not preserve the latest full state')
        if data_rows(state_now(), admin) != latest_budgets or len(latest_budgets) != 3:
            raise AssertionError('Reverse dropped a commit or refilled budgets')
        incompatible = state_now()
        incompatible['runtime']['schema_version'] = 'future-outside-old-import-contract'
        write_state(incompatible)
        # Current connector already points to old target; this is still a full import check, not a no-op bypass.
        cases['reverse_unknown_runtime_schema'] = refusal(lambda: admin.build_plan('codex', project,
            expected_build=target['identity']['build_id']), 'Target runtime cannot import the existing state')
        # Remove only this negative case's synthetic mutation, using the exact
        # immediately captured successful QA afterimage, never a historical backup.
        state_path.write_bytes(final_raw)
        cases['latest_commits_preserved'] = {'latest_budget_rows': latest_budgets, 'raw_bytes_except_binding_preserved': True,
                                           'historical_state_backup_restored': False}
        results.update(plan=preview, apply=applied)
    elif operation == 'safety':
        pristine_raw, pristine = state_path.read_bytes(), state_now()
        mutations = {
            'inflight': (lambda state: state.update(inflight={'operation_id': 'accepted-not-read-back'}), 'Pending inflight operation'),
            'pending': (lambda state: state['runtime']['router'].update(sessions=[['queue', {'pending': {'operation_id': 'pending'}}]]), 'Pending or malformed router journal'),
            'quarantine': (lambda state: state['runtime'].update(quarantine={'reason': 'unknown-execution', 'last_checked_revision': None}), 'Quarantined or incomplete runtime'),
            'unknown_state_schema': (lambda state: state.update(schema_version='future'), 'Persisted state schema/binding'),
            'unknown_runtime_schema': (lambda state: state['runtime'].update(schema_version='future'), 'Target runtime cannot import the existing state'),
            'unknown_goal_schema': (lambda state: state['goal_segments'].update(schema_version='future'), 'Target cannot validate existing goal ledgers'),
        }
        from human_eye_plugin import goal_journal as journal
        mutations['unfinished_parent'] = (lambda state: journal.create_goal(state, 'new-unresolved-goal', 'unresolved-session',
            clock_domain='migration-synthetic-clock', now=100.), 'Unresolved parent goal blocks activation')
        for name, (change, expected) in mutations.items():
            state = copy.deepcopy(pristine)
            change(state)
            write_state(state)
            cases[name] = refusal(plan, expected)
            state_path.write_bytes(pristine_raw)
        cases['wrong_prior_sha'] = refusal(lambda: plan([(str(prior_entry), 'f'*64, prior_build)]), 'Unknown or modified fixed target bootstrap')
        cases['wrong_prior_build'] = refusal(lambda: plan([(str(prior_entry), prior_pin[1], 'sha256:'+'f'*64)]), 'explicit expected build')
        unused = entry_path.parent.parent.parent/'not-registered/admin/target_runtime_entry.py'
        cases['unused_prior_pin'] = refusal(lambda: plan([prior_pin, (str(unused), prior_pin[1], prior_build)]), 'Unused prior launcher pin')
        old_config_raw = config_path.read_bytes()
        mismatch = json.loads(old_config_raw)
        mismatch['expected_identity']['build_id'] = 'sha256:'+'f'*64
        config_path.write_bytes(admin._encode(mismatch))
        changed = copy.deepcopy(pristine)
        changed['config_fingerprint'] = admin._fingerprint(mismatch)
        write_state(changed)
        cases['external_connector_build_mismatch'] = refusal(plan, 'registered connector identity')
        config_path.write_bytes(old_config_raw)
        state_path.write_bytes(pristine_raw)
        original_server = server_path.read_bytes()
        _, known_server = admin._load_server(original_server, 'codex')
        wrapped = copy.deepcopy(known_server)
        wrapped['args'].extend(['--exec', 'unknown-wrapper'])
        server_path.write_bytes(admin._replace_toml_server(original_server, known_server, wrapped))
        cases['unknown_wrapper'] = refusal(plan, 'Unknown, duplicate or unsafe launcher arguments')
        server_path.write_bytes(original_server)
        stale_binding = plan()
        binding_path = entry_path.with_name('RUNTIME_BINDING.json')
        original_binding = binding_path.read_bytes()
        changed_binding = json.loads(original_binding)
        changed_binding['identity']['implementation_revision'] += '-external-change'
        binding_path.write_text(json.dumps(changed_binding), encoding='utf-8')
        try:
            cases['target_binding_change_after_plan'] = refusal(stale_binding.apply, 'Fixed target binding failed')
        finally:
            # Only the dedicated QA clone's just-injected binding mutation.
            binding_path.write_bytes(original_binding)
        for path in (config_path, hooks_path, state_path):
            stale = plan()
            original = path.read_bytes()
            path.write_bytes(original+b'\n')
            cases['stale_'+path.name] = refusal(stale.apply, 'Configuration/state changed after planning')
            path.write_bytes(original)
        lock = project/'.human-eye/setup.lock'
        lock.write_bytes(b'prior-transaction-owned-by-someone-else')
        cases['existing_setup_lock'] = refusal(lambda: plan().apply(), 'Existing setup lock was preserved')
        if lock.read_bytes() != b'prior-transaction-owned-by-someone-else':
            raise AssertionError('Existing setup lock overwritten')
        lock.unlink()  # Only the sentinel created by this QA case, never a production lock.
        original_state_lock = admin._state_lock
        with original_state_lock(state_path, timeout_s=1):
            locked = plan()
            with patch.object(admin, '_state_lock', lambda path, timeout_s=20: original_state_lock(path, timeout_s=.05)):
                cases['actual_state_lock_contention'] = refusal(locked.apply, 'Timed out waiting for the router state lock')
        if lock.exists():
            raise AssertionError('Failed lock acquisition leaked our setup lock')
        ordinary = plan()
        before = managed_bytes(project)
        atomic = admin._atomic_bytes
        def write_failure(path, raw):
            if path == hooks_path:
                raise OSError('QA injected hook write failure')
            return atomic(path, raw)
        with patch.object(admin, '_atomic_bytes', side_effect=write_failure):
            try:
                ordinary.apply()
            except admin.AgentSetupError as exc:
                if 'rolled_back' not in str(exc):
                    raise
                cases['ordinary_failure_rollback'] = {'actual': str(exc), 'raw_originals_preserved': managed_bytes(project) == before}
            else:
                raise AssertionError('Injected failure was not observed')
        if managed_bytes(project) != before:
            raise AssertionError('Ordinary exception did not restore originals exactly')
        previous_backups = {str(path): sha(path.read_bytes()) for path in (project/'.human-eye/setup-backups').rglob('*') if path.is_file()}
        interrupted = plan()
        def concurrent_failure(path, raw):
            if path == hooks_path:
                server_path.write_bytes(b'# independently edited QA configuration\n')
                raise OSError('QA failure after independent configuration edit')
            return atomic(path, raw)
        with patch.object(admin, '_atomic_bytes', side_effect=concurrent_failure):
            try:
                interrupted.apply()
            except admin.AgentSetupError as exc:
                if 'rollback_incomplete' not in str(exc):
                    raise
                cases['concurrent_edit_rollback_incomplete'] = {'actual': str(exc)}
            else:
                raise AssertionError('Concurrent edit did not stop rollback')
        fenced = state_now()
        if fenced['runtime'] != pristine['runtime'] or fenced['goal_segments'] != pristine['goal_segments']:
            raise AssertionError('Incomplete rollback modified execution history')
        if server_path.read_bytes() != b'# independently edited QA configuration\n':
            raise AssertionError('Independent configuration edit overwritten')
        if fenced['config_fingerprint'] in {pristine['config_fingerprint'], interrupted.preview()['state_migration']['new_config_fingerprint']}:
            raise AssertionError('Incomplete rollback released the transaction fence')
        if any(sha(Path(path).read_bytes()) != digest for path, digest in previous_backups.items()):
            raise AssertionError('Prior transaction evidence changed')
        # A new plan must not be permitted to rebind a fenced state even with explicit connector selection.
        cases['interrupted_fence_replan'] = refusal(lambda: admin.build_plan('codex', project, config_path=config_path,
            expected_build=target['identity']['build_id']), 'Persisted state schema/binding')
        results['fenced_state_sha256'] = sha(state_path.read_bytes())
        results['unresolved_qa_fence_deliberately_retained'] = True
    else:
        raise ValueError('Unknown qualification operation')
    print(json.dumps(results, ensure_ascii=False, allow_nan=False))


def qualify(attempt, core=False):
    if re.fullmatch(r'[0-9]{2}', attempt) is None:
        raise ValueError('Attempt must be two digits')
    owner = EVIDENCE/'MIGRATION_QA'/('attempt'+attempt)
    owner.mkdir(parents=True, exist_ok=False)
    new_install, new_build, new_count = (CORE, CORE_BUILD, 125) if core else (NEW, NEW_BUILD, 124)
    clones = {name: clone_release(original, owner/name) for name, original in (('old', OLD), ('new', new_install))}
    record(EVIDENCE/('MIGRATION_CANDIDATE_ADMIN_'+attempt+'.json'), {'clones': clones,
        'runner_sha256': sha(Path(__file__).read_bytes()), 'scope': 'QA only; distinct administration generation; no default activation'})
    result = {'attempt': attempt, 'clones': clones, 'new_source_profile': 'core125' if core else 'safety124',
              'production_activation_performed': False, 'operations': {}}
    def run(command):
        completed = subprocess.run([str(PYTHON), '-I', '-B', *command], capture_output=True,
                                   text=True, encoding='utf-8', timeout=90)
        if completed.returncode:
            record(EVIDENCE/('MIGRATION_FAILURE_'+attempt+'_'+str(len(result['operations']))+'.json'),
                   {'command': command, 'returncode': completed.returncode, 'stdout': completed.stdout, 'stderr': completed.stderr})
            raise RuntimeError(completed.stderr)
        return json.loads(completed.stdout)
    for name in ('old', 'new'):
        identity = run([clones[name]['entry'], 'identity'])
        expected, count = (OLD_BUILD, 78) if name == 'old' else (new_build, new_count)
        if identity['runtime_identity']['build_id'] != expected or identity['launcher']['source_file_count'] != count:
            raise AssertionError('QA clone changed fixed runtime identity')
        result['operations'][name+'_identity'] = identity
    for name in (('roundtrip',) if core else ('roundtrip', 'safety')):
        project = owner/name
        project.mkdir()
        fixture = run([str(Path(__file__).resolve()), '--fixture-worker', '--entry', str(OLD/'admin/target_runtime_entry.py'), '--project', str(project)])
        result['operations'][name+'_fixture'] = fixture
        if name == 'roundtrip':
            doctor = run([clones['new']['entry'], 'admin', 'doctor', '--agent', 'codex', '--project', str(project),
                '--expected-build', new_build, '--prior-launcher', str(OLD/'admin/target_runtime_entry.py'),
                registered_entry_sha(OLD/'admin/target_runtime_entry.py'), OLD_BUILD])
            result['operations']['actual_doctor_cli'] = doctor
            for op, target, prior, build in [('forward', 'new', str(OLD/'admin/target_runtime_entry.py'), OLD_BUILD),
                                             ('reverse', 'old', clones['new']['entry'], new_build)]:
                value = run([str(Path(__file__).resolve()), '--operation-worker', op, '--entry', clones[target]['entry'],
                             '--project', str(project), '--prior-entry', prior, '--prior-build', build])
                record(EVIDENCE/('MIGRATION_'+op.upper()+'_'+attempt+'.json'), value)
                result['operations'][op] = value
        else:
            value = run([str(Path(__file__).resolve()), '--operation-worker', 'safety', '--entry', clones['new']['entry'],
                         '--project', str(project), '--prior-entry', str(OLD/'admin/target_runtime_entry.py'), '--prior-build', OLD_BUILD])
            record(EVIDENCE/('MIGRATION_SAFETY_'+attempt+'.json'), value)
            result['operations']['safety'] = value
    protected = protected_hashes()
    registered = json.loads((EVIDENCE/'MIGRATION_PREREGISTERED.json').read_text(encoding='utf-8'))['protected_before']
    result['protected_originals_unchanged'] = protected == registered
    if core:
        core_registered = json.loads((EVIDENCE/'MIGRATION_CORE_PREREGISTERED.json').read_text(encoding='utf-8'))['protected_core_before']
        result['protected_core_candidate_unchanged'] = core_registered == {
            str(path): sha(path.read_bytes()) for path in sorted(CORE.rglob('*')) if path.is_file()}
        if not result['protected_core_candidate_unchanged']:
            raise AssertionError('The fixed original 125-source candidate changed')
    if not result['protected_originals_unchanged']:
        result['protected_changes'] = [path for path in protected.keys()|registered.keys() if protected.get(path) != registered.get(path)]
    result['passed'] = result['protected_originals_unchanged']
    record(EVIDENCE/('MIGRATION_QUALIFICATION_'+attempt+'.json'), result)
    if not result['passed']:
        raise AssertionError('Protected originals changed; inspect immutable evidence, do not restore external writes')
    print(json.dumps({'passed': True, 'attempt': attempt, 'source_builds': [OLD_BUILD, new_build],
                      'protected_originals_unchanged': True, 'production_activation_performed': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preregister', action='store_true')
    parser.add_argument('--preregister-core', action='store_true')
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--fixture-worker', action='store_true')
    parser.add_argument('--entry', type=Path)
    parser.add_argument('--project', type=Path)
    parser.add_argument('--qualify', action='store_true')
    parser.add_argument('--core', action='store_true')
    parser.add_argument('--attempt', default='01')
    parser.add_argument('--operation-worker', choices=('forward', 'reverse', 'safety'))
    parser.add_argument('--prior-entry', type=Path)
    parser.add_argument('--prior-build')
    args = parser.parse_args()
    if args.preregister:
        preregister()
        print('Migration cases and protected original SHA values registered.')
    elif args.preregister_core:
        preregister_core()
        print('Separate 125-source core migration profile preregistered.')
    elif args.fixture_worker:
        fixture_worker(args.entry, args.project)
    elif args.baseline:
        baseline()
    elif args.qualify:
        qualify(args.attempt, args.core)
    elif args.operation_worker:
        operation_worker(args.entry, args.project, args.operation_worker, args.prior_entry, args.prior_build)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
