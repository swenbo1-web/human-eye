"""Bound reuse of the accepted CLI loop, result matcher and held-handle route.

Importing this module starts no actor, CLI, model or renderer. The preparation
and formal entry points explicitly select their phase. Original code objects
receive private globals snapshots; archived modules remain unchanged.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import types


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXTERNAL = Path('D:/he_loc_001')
ACCEPTED = ROOT / 'verification/m4_active_coverage_consumption_002'
CONTRACT = ROOT / 'verification/m4_consumer_error_contract_001'
ANCHORS = ROOT / 'verification/m4_active_observation_region_anchors_001'
BASE = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
BASE_SHA256 = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
SOURCE_SHA256 = '96d7da8c50680a73f251496406c9f0bbbf6b38bd4dfe848c931e45f094343b76'
SEQUENCE = [('N1', 'N'), ('P1', 'P'), ('P2', 'P'), ('N2', 'N'), ('N3', 'N'), ('P3', 'P')]
TOOLS = {'N': frozenset({'execute_python', 'scene_data', 'render_views', 'read_images'}),
         'P': frozenset({'execute_python', 'scene_data', 'render_views', 'read_images', 'active_observation'})}


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value, exclusive=False):
    with Path(path).open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def clone(function, replacements):
    namespace = dict(function.__globals__)
    namespace.update(replacements)
    result = types.FunctionType(function.__code__, namespace, function.__name__,
                                function.__defaults__, function.__closure__)
    result.__kwdefaults__ = None if function.__kwdefaults__ is None else dict(function.__kwdefaults__)
    return result


def input_checks(plan):
    if [(row['slot'], row['group']) for row in plan['sequence']] != SEQUENCE:
        raise ValueError('fixed_six_fresh_slot_order')
    if (plan['route_deadline_seconds'], plan['max_tool_calls'], plan['max_render_attempts']) != (450, 12, 6):
        raise ValueError('fixed_route_limits')
    if (plan['preparation_render_cap'], plan['formal_render_cap'], plan['total_new_render_cap']) != (8, 36, 44):
        raise ValueError('fixed_attempt_caps')
    if (plan['requested_model'], plan['requested_reasoning_effort'], plan['requested_service_tier']) != ('gpt-6.1-sol', 'medium', 'default'):
        raise ValueError('accepted_common_model_profile')
    prompt = Path(plan['inputs']['prompt']).resolve()
    manifest_path = Path(plan['inputs']['input_manifest']).resolve()
    if not prompt.is_relative_to(HERE) or not manifest_path.is_relative_to(HERE):
        raise ValueError('new_namespace_inputs_required')
    manifest = read(manifest_path)
    if manifest['schema'] != 'region-localization-consumption-001-inputs-v1':
        raise ValueError('registered_localization_input_schema')
    sources = {str(prompt): sha(prompt), str(manifest_path): sha(manifest_path)}
    if sources[str(prompt)] != plan['expected_prompt_sha256']:
        raise ValueError('frozen_shared_prompt_required')
    for name in ('capture', 'scene', 'cameras', 'product_binding'):
        specification = manifest[name]
        path = (Path(specification['path']) if 'path' in specification
                else manifest_path.parent / specification['file']).resolve()
        if sha(path) != specification['sha256']:
            raise ValueError('registered_common_input_changed_' + name)
        sources[str(path)] = specification['sha256']
    budget = manifest['budget_contract']
    if (Path(budget['external_root']).resolve() != EXTERNAL
            or Path(budget['preparation_root']).resolve() != EXTERNAL / 'preparation'
            or Path(budget['formal_root']).resolve() != EXTERNAL / 'formal'
            or Path(budget['ledger_root']).resolve() != EXTERNAL / 'raster_budget'
            or (budget['preparation_cap'], budget['formal_cap'], budget['total_cap'], budget['per_slot_cap']) != (8, 36, 44, 6)
            or manifest['public_surface_color_rgb'] != [180, 190, 205]):
        raise ValueError('frozen_shared_render_budget_and_color')
    binding_path = Path(manifest['product_binding']['path']).resolve()
    binding = read(binding_path)
    if binding['source_sha256'] != SOURCE_SHA256 or Path(binding['install_root']).resolve() != Path('D:/he_anchor_001/product'):
        raise ValueError('accepted_installed_product_binding')
    if sha(BASE) != BASE_SHA256:
        raise ValueError('actual_base_executable_changed')
    return prompt.read_bytes(), manifest_path, sources


def source_file_list(plan):
    """Return the inherited exact dependency closure plus this batch's sources."""
    inherited = read(ROOT / 'verification/m4_active_coverage_consumption_001/FROZEN.json')['runtime_sources']
    sources = dict(inherited)
    accepted_sources = read(CONTRACT / 'FROZEN.json')['files_sha256']
    for name in ('driver.py', 'consumer.py', 'result_contract.py'):
        path = str((CONTRACT / name).resolve())
        sources[path] = accepted_sources[path]
    for path in [HERE / name for name in ('launcher.py', 'bootstrap.py', 'fake_cli.py',
                                         'run_preparation.py', 'run_formal.py', 'bridge.py', 'native_tools.py')]:
        sources[str(path.resolve())] = sha(path)
    for path in (ACCEPTED / 'launcher.py', ACCEPTED / 'FROZEN.json', CONTRACT / 'FROZEN.json',
                 ANCHORS / 'build/RUN_BINDING.json', ANCHORS / 'verified_bootstrap.py', HERE / 'PLAN.json'):
        sources[str(path.resolve())] = sha(path)
    sources.update(input_checks(plan)[2])
    binding = read(ANCHORS / 'build/RUN_BINDING.json')
    for row in binding['source_manifest']:
        path = Path(binding['install_root']) / row['path']
        if sha(path) != row['sha256']:
            raise ValueError('accepted_product_file_changed:' + row['path'])
        sources[str(path.resolve())] = row['sha256']
    for path in Path(binding['install_root']).glob('*.dist-info/*'):
        if path.is_file():
            sources[str(path.resolve())] = sha(path)
    dependencies = read(ANCHORS / 'preparation/ENVIRONMENT.json')
    for row in dependencies['dependencies']:
        sources[str(Path(row['path']).resolve())] = row['sha256']
    sources[str((ANCHORS / 'preparation/ENVIRONMENT.json').resolve())] = sha(ANCHORS / 'preparation/ENVIRONMENT.json')
    for path, wanted in sources.items():
        if sha(path) != wanted:
            raise ValueError('execution_dependency_changed:' + path)
    return sources


def verify_frozen(filename, required_sources=None):
    path = HERE / filename
    frozen = read(path)
    if required_sources is not None and any(frozen['files_sha256'].get(name) != wanted
                                            for name, wanted in required_sources.items()):
        raise ValueError('required_execution_source_missing_from_freeze')
    for name, wanted in frozen['files_sha256'].items():
        if sha(name) != wanted:
            raise ValueError('frozen_source_changed:' + name)
    return frozen


def connect(plan, phase):
    if phase not in ('preparation', 'formal'):
        raise ValueError('explicit_execution_phase_required')
    candidate = load('_localization_accepted_result_driver', CONTRACT / 'driver.py')
    original_consumer = candidate.consumer.legacy
    original_launch = candidate.legacy.launch
    manifest_path = Path(plan['inputs']['input_manifest']).resolve()
    manifest = read(manifest_path)
    product = manifest['product_binding']
    verified = ANCHORS / 'verified_bootstrap.py'

    def python_command(entry, arguments):
        if Path(entry).resolve() != (HERE / 'actor.py').resolve():
            raise ValueError('only_registered_bridge_entry')
        config_path = Path(arguments[arguments.index('--config') + 1])
        config = read(config_path)
        config.update(phase=phase, budget_root=manifest['budget_contract']['ledger_root'],
                      whole_render_cap=44, phase_render_cap=8 if phase == 'preparation' else 36,
                      runtime_binding={'binding': product,
                                       'verified_bootstrap': {'path': str(verified), 'sha256': sha(verified)}})
        save(config_path, config)
        return [str(BASE), '-I', '-B', '-X', 'utf8', str(HERE / 'bootstrap.py'),
                str(HERE / 'bridge.py'), *[str(value) for value in arguments]]

    launch = types.SimpleNamespace(BASE=BASE, BASE_SHA256=BASE_SHA256,
                                   python_command=python_command, stop_process=original_launch.stop_process)

    def initial_argv(python, cell_path, work, final, group):
        cell = read(cell_path)
        config = original_consumer.previous.settings()
        config['mcp_servers.arm_engine'] = {
            'command': str(python),
            'args': ['-I', '-B', str(original_consumer.previous.ATTACH_PATH), '--endpoint', cell['endpoint'],
                     '--kind', 'native', '--audit', str(Path(cell_path).parent / 'attachments')],
            'cwd': str(work), 'required': True, 'startup_timeout_sec': 60, 'tool_timeout_sec': 450,
            'tools': {name: {'approval_mode': 'approve'} for name in sorted(TOOLS[group])}}
        interface = read(original_consumer.CONTINUITY / 'cli/CLI_INTERFACE.json')
        if sha(interface['executable']) != interface['executable_sha256']:
            raise ValueError('accepted_actual_CLI_changed')
        argv = [interface['executable'], 'exec', '--ignore-user-config', '--ignore-rules', '--strict-config',
                '--json', '--skip-git-repo-check', '-C', str(work), '--color', 'never']
        for key, value in config.items():
            argv.extend(['-c', key + '=' + original_consumer.previous.toml(value)])
        return argv + ['-m', plan['requested_model'], '-o', str(final), '-']

    consumer = types.SimpleNamespace(**vars(candidate.consumer))
    consumer.consume_turn = clone(candidate.consumer.consume_turn,
                                   {'initial_argv': initial_argv, 'TOOLS_BY_GROUP': TOOLS, 'launch': launch})
    consumer.launch = launch
    common = clone(candidate.common_image_faults, {'consumer': consumer})
    route = clone(candidate.run_route, {'HERE': HERE, 'input_checks': input_checks,
                                       'consumer': consumer, 'launch': launch, 'common_image_faults': common})
    batch = clone(candidate.run_batch, {'run_route': route})
    checks = {'route_code_reused': route.__code__ is candidate.run_route.__code__,
              'consume_code_reused': consumer.consume_turn.__code__ is candidate.consumer.consume_turn.__code__,
              'batch_code_reused': batch.__code__ is candidate.run_batch.__code__,
              'route_to_consumer': route.__globals__['consumer'] is consumer,
              'consume_to_unified_archive': consumer.consume_turn.__globals__['archive_turn'] is candidate.consumer.archive_turn,
              'common_to_same_matcher': common.__globals__['consumer'].result_contract is consumer.result_contract,
              'legacy_route_consumer_untouched': candidate.legacy.run_route.__globals__['consumer'] is candidate.legacy.consumer,
              'legacy_consume_archive_untouched': candidate.consumer.legacy.consume_turn.__globals__['archive_turn'] is candidate.consumer.legacy.archive_turn}
    if not all(checks.values()):
        raise ValueError('accepted_private_pointer_chain')
    return types.SimpleNamespace(run_route=route, run_batch=batch, consumer=consumer,
                                 pointers=checks, candidate=candidate, phase=phase)


def local_checks(row, group):
    record = read(Path(row['consumer_output']) / 'CONSUMER.json')
    contracts = record['archive']['result_contracts']
    fixture = read(Path(row['consumer_output']) / 'LOCAL_FIXTURE.json')
    expected_images = 1 if group == 'N' else 3
    checks = {'outer': row['outer_valid_completion'] is True, 'safe': record['safe_to_continue'] is True,
              'three_tools': len(record['tool_calls']) == 3,
              'unified_error_recovery_image': [item['classification'] for item in contracts] == ['tool_error', 'success', 'success'] and all(item['matched'] for item in contracts),
              'actual_render_attempts': row['new_renders'] == expected_images,
              'actual_image_construction': row['owner_metrics']['constructed_image_blocks'] == expected_images,
              'actual_CLI_images': record['public_image_count'] == expected_images,
              'fixture_normal_EOF': fixture['passed'] is True and fixture['normal_EOF_requested'] is True,
              'held_runtime_exit0': record['runtime_exit']['confirmed'] is True and record['runtime_exit']['exit_code'] == 0,
              'stdio_EOF': record['bridge_cleanup']['confirmed'] is True,
              'no_provider': fixture['new_model_provider_Blender_calls'] == 0}
    return {'passed': all(checks.values()), 'checks': checks}


def run_local(plan, group):
    source_before = source_file_list(plan)
    verify_frozen('PREP_FROZEN.json', source_before)
    root = EXTERNAL / 'preparation'
    root.mkdir(parents=True, exist_ok=True)
    attempt = 1
    requalification = None
    while (root / (group + str(attempt))).exists():
        prior_path = root / (group + str(attempt)) / 'LOCAL_RESULT.json'
        prior = read(prior_path)
        if prior['passed'] and prior['execution_sources_sha256'] == source_before:
            raise ValueError('passed_preparation_cannot_be_repeated')
        if prior['passed']:
            requalification = {
                'reason': 'necessary requalification after wiring source repair',
                'prior_result_path': str(prior_path), 'prior_result_sha256': sha(prior_path)}
        attempt += 1
    if attempt > 2:
        raise ValueError('preparation_group_attempt_cap')
    folder = root / (group + str(attempt))
    folder.mkdir(exist_ok=False)
    driver = connect(plan, 'preparation')
    began = time.perf_counter_ns()
    row = driver.run_route('LOCAL_' + group + str(attempt), group, plan, folder,
                           local_cli={'command': [str(BASE), '-I', '-B', str(HERE / 'fake_cli.py')],
                                      'script_sha256': sha(HERE / 'fake_cli.py')})
    try:
        validation = local_checks(row, group)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        validation = {'passed': False, 'checks': {}, 'error': {'type': type(error).__name__, 'message': str(error)}}
    unchanged = source_before == source_file_list(plan)
    verify_frozen('PREP_FROZEN.json', source_before)
    result = {'schema': 'region-localization-preparation-v1', 'group': group, 'attempt': attempt,
              'passed': validation['passed'] and unchanged, 'checks': validation,
              'transport_and_runtime_only': True, 'full_pair_geometry_pixel_qualification': 'separate saved-data check required before formal',
              'route': row, 'execution_sources_sha256': source_before, 'source_unchanged': unchanged,
              'requalification': requalification,
              'pointer_chain': driver.pointers, 'started_ns': began,
              'before_publication_ns': time.perf_counter_ns(), 'new_model_sessions': 0}
    save(folder / 'LOCAL_RESULT.json', result, exclusive=True)
    return result


def require_preparation(plan):
    sources = source_file_list(plan)
    selected = []
    for group in ('N', 'P'):
        paths = [EXTERNAL / 'preparation' / (group + str(n)) / 'LOCAL_RESULT.json' for n in (1, 2)]
        present = [path for path in paths if path.exists()]
        if not present:
            raise ValueError('both_preparation_groups_required')
        result = read(present[-1])
        if result['passed'] is not True or result['execution_sources_sha256'] != sources:
            raise ValueError('preparation_source_or_transport_not_qualified_' + group)
        selected.append({'group': group, 'path': str(present[-1]), 'sha256': sha(present[-1]), 'attempts': len(present)})
    qualification = HERE / 'PREPARATION_QUALIFICATION.json'
    pair = read(qualification)
    if pair.get('passed') is not True or pair.get('local_results') != selected:
        raise ValueError('saved_geometry_pixel_source_pair_qualification_required')
    return {'local_results': selected, 'qualification_path': str(qualification), 'qualification_sha256': sha(qualification)}


def run_formal(plan, preparation_git):
    began = time.perf_counter_ns()
    sources = source_file_list(plan)
    verify_frozen('FROZEN.json', sources)
    current = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    if current.returncode or current.stdout.strip() != preparation_git:
        raise ValueError('fixed_preparation_commit_required')
    if plan.get('model_consumer_enabled') is not True:
        raise ValueError('formal_model_flag_required')
    preparation = require_preparation(plan)
    runtime = Path(plan['runtime_root']).resolve()
    if runtime != EXTERNAL / 'formal':
        raise ValueError('new_external_formal_directory_required')
    runtime.mkdir(parents=True, exist_ok=False)
    save(HERE / 'FORMAL_STARTED.json', {'started_ns': time.perf_counter_ns(), 'preparation_git': preparation_git,
         'freeze_sha256': sha(HERE / 'FROZEN.json'), 'preparation': preparation}, exclusive=True)
    driver = connect(plan, 'formal')
    result = driver.run_batch(plan, runtime)
    verify_frozen('FROZEN.json', sources)
    if sources != source_file_list(plan):
        raise ValueError('source_changed_during_formal_batch')
    save(runtime / 'LAUNCH_RESULT.json', {'schema': 'region-localization-launch-v1',
         'preparation_git': preparation_git, 'freeze_sha256': sha(HERE / 'FROZEN.json'),
         'source_unchanged': True, 'pointer_chain': driver.pointers, 'actual_routes': result['actual_routes'],
         'preparation': preparation, 'before_publication_ns': time.perf_counter_ns()}, exclusive=True)
    closed = time.perf_counter_ns()
    save(runtime / 'LAUNCH_TIMING.json', {'started_ns': began, 'launch_result_closed_ns': closed,
         'elapsed_ns': closed - began,
         'scope': 'Main launch call through qualification, fixed batch, source readback and launch-result publication. Interpreter import and this final timing receipt publication are outside this clock.'}, exclusive=True)
    return result
