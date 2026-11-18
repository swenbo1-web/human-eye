"""Freeze the registered input, tools, runtime sources and limits before either slot."""

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (ASSET, ASSET_SHA256, BASELINE, BLENDER, CLI, DISPLAY, EXTERNAL, HERE,
                    NS, ORIGINAL_POSE_SOURCE, PLAN_COMMIT, PLAN_SHA, PRIOR, SOURCE_SHA, read, save, sha)


def prepare():
    started = time.perf_counter_ns()
    EXTERNAL.mkdir(exist_ok=False)
    save(NS / 'PREPARATION_STARTED.json', {'started_ns': started, 'workspace_branch_base': BASELINE})
    raw = subprocess.check_output(['git', '-C', 'D:/hefe', 'show',
                                   PLAN_COMMIT + ':docs/M4_LIVE_SOURCE_REGION_TASK_001_PLAN.md'])
    if hashlib.sha256(raw).hexdigest() != PLAN_SHA:
        raise ValueError('fixed_plan_hash_mismatch')
    (NS / 'inputs/PLAN.md').write_bytes(raw)
    region_path = DISPLAY / 'inputs/ARM_REGION.json'
    region_sha = sha(region_path)
    if region_sha != 'a203e27a45387170d6682cbf93de73f98d7c2042024c513f888c55f336c2cef1':
        raise ValueError('frozen_zone_source_changed')
    region = read(region_path)
    indices = region['source_triangle_ids']
    if len(indices) != 748 or indices != sorted(set(indices)):
        raise ValueError('fixed_748_source_triangle_selection_required')
    selector = {'name': region['object_name']}
    host_key = json.dumps(['', region['object_name']], ensure_ascii=False, separators=(',', ':')).encode()
    save(NS / 'inputs/REGION.json', {'object': selector, 'object_name': region['object_name'],
        'object_id': 'blender:' + hashlib.sha256(host_key).hexdigest(), 'reference': {'name': 'Cube'},
        'source_triangle_ids': indices, 'index_domain': 'zero_based_object_local_current_evaluated_capture_triangle_rows'})
    if sha(ASSET) != ASSET_SHA256:
        raise ValueError('original_asset_changed')
    binding = read(NS / 'PRODUCT_RUN_BINDING.json')
    if (len(binding['source_manifest']) != 143 or binding['source_sha256'] != SOURCE_SHA or
            binding['preparation_git'] != '08a5f3b29283270c97b6d9d6e217bbee6ca7bfc1'):
        raise ValueError('fixed_isolated_product_required')
    save(NS / 'PREPARED.json', {'started_ns': started, 'closed_ns': time.perf_counter_ns(),
        'plan_commit': PLAN_COMMIT, 'plan_sha256': PLAN_SHA, 'selection_origin': str(region_path),
        'selection_origin_sha256': region_sha, 'selection_normalized_sha256': sha(NS / 'inputs/REGION.json'),
        'asset_path': str(ASSET), 'asset_sha256': ASSET_SHA256,
        'conversation_id': os.environ.get('CODEX_THREAD_ID'),
        'agent_learning_registration': 'pending_current_tool_unavailable', 'agent_learning_task_writes': 0,
        'actual_consumer_launches': 0, 'actual_Blender_launches': 0})


def freeze():
    started = time.perf_counter_ns()
    prepared = read(NS / 'PREPARED.json')
    tracked = [p for p in NS.rglob('*') if p.is_file() and p.suffix != '.pyc']
    external = [ASSET, BLENDER, CLI, Path(sys.executable), ORIGINAL_POSE_SOURCE, Path(prepared['selection_origin']),
                *[NS.parents[1] / 'verification/m4_target_task_consumption_001' / name
                  for name in ('native_consumer_audit.py', 'native_tools.py')],
                *[DISPLAY / 'harness' / name for name in ('state_owned_native.py', 'reused/process_proof.py',
                    'reused/stdio_checks.py', 'reused/wire_meter.py')]]
    roles = ('inputs/PROMPT.txt', 'inputs/REGION.json', 'inputs/CAMERA.json', 'inputs/PRODUCT_SCHEMA.json')
    for name in roles:
        if not (NS / name).is_file():
            raise ValueError('required_frozen_input_missing/' + name)
    for path in tracked:
        if path.suffix == '.py':
            ast.parse(path.read_bytes(), filename=str(path))
    binding = read(NS / 'PRODUCT_RUN_BINDING.json')
    installed = Path(binding['install_root'])
    for row in binding['source_manifest']:
        path = installed / row['path']
        if sha(path) != row['sha256']:
            raise ValueError('installed_product_source_mismatch/' + row['path'])
        external.append(path)
    dependency = Path(binding['dependency_root'])
    shared_manifest = NS.parents[1] / 'verification/m5_harness_recovery_001/SHARED_DEPENDENCY.json'
    shared = read(shared_manifest)
    for name, expected in shared['files_sha256'].items():
        path = Path(name)
        if sha(path) != expected:
            raise ValueError('shared_dependency_changed/' + str(path))
        external.append(path)
    sys.path.insert(0, shared['dependency_root'])
    sys.path.insert(0, str(dependency))
    sys.path.insert(0, str(NS))
    import numpy
    import PIL
    import shapely
    from shapely.geometry import box
    if not Path(shapely.__file__).resolve().is_relative_to(Path(shared['dependency_root']).resolve()) or box(0, 0, 1, 1).area != 1:
        raise ValueError('shared_geometry_dependency_smoke_failed')
    from consumer_adapter import consumer_adapter
    _, adapter = consumer_adapter()
    for row in adapter['execution_sources']:
        path = Path(row['path'])
        if sha(path) != row['sha256'] or path.stat().st_size != row['bytes']:
            raise ValueError('recursive_consumer_source_changed/' + str(path))
        external.append(path)
    for package in ('numpy', 'PIL', 'shapely', 'scipy'):
        path = dependency / package / '__init__.py'
        if path.exists():
            external.append(path)
    preflight = read(PRIOR / 'CLI_PREFLIGHT.json')
    if sha(CLI) != preflight['CLI_sha256']:
        raise ValueError('fixed_cli_binary_changed')
    version = subprocess.run([str(CLI), '--version'], capture_output=True, timeout=15, check=True)
    login = subprocess.run([str(CLI), 'login', 'status'], capture_output=True, timeout=15, check=True)
    if b'0.152.1' not in version.stdout or b'ChatGPT' not in login.stdout + login.stderr:
        raise ValueError('fixed_cli_version_and_ChatGPT_login_required')
    pins = [{'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
            for path in sorted({path.resolve() for path in tracked + external})]
    save(NS / 'FROZEN_R1.json', {'schema': 'live-source-region-experiment-freeze-v1',
         'started_ns': started, 'closed_ns': time.perf_counter_ns(), 'direct_inputs': pins,
         'slots': ['N1', 'P1'], 'limits': {'real_consumers': 2, 'owned_Blender': 2, 'tools_per_slot': 12,
                                           'raster_per_slot': 4, 'task_seconds': 450, 'owned_seconds': 600},
         'original_freeze_sha256': sha(NS / 'FROZEN.json'), 'applies_to': ['P1'],
         'existing_owned_Blender_starts': 1, 'inference_started': 0,
         'shared_dependency_root': shared['dependency_root'],
         'libraries': {s.__name__: s.__version__ for s in (numpy, PIL, shapely)},
         'profile': ['0.152.1', 'gpt-6.1-sol', 'medium', 'default'],
         'CLI_version_stdout_sha256': hashlib.sha256(version.stdout).hexdigest(),
         'login_status_chatgpt': True, 'consumer_execution_sources': adapter['execution_sources']})
    print(json.dumps({'pins': len(pins), 'freeze_sha256': sha(NS / 'FROZEN_R1.json'), 'inference_started': 0}))


if __name__ == '__main__':
    {'prepare': prepare, 'freeze': freeze}[sys.argv[1]]()
