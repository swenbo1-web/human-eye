"""Seal fixture, tool, scoring and byte-preserving transport identities before qualification."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
ROOT = NS.parents[1]
RUN = Path('D:/he_m4_cross_scale_live_task_formal_001')
RECOVERY_RUN = Path('D:/he_m4_cross_scale_live_task_recovery_001')
ORIGINAL_RUN = Path('D:/he_m4_cross_scale_live_task_001')
ORIGINAL = ROOT / 'verification/m4_cross_scale_live_task_001'
V = ROOT / 'verification'
sys.path.insert(0, str(NS / 'harness'))
from common import BLENDER, PRODUCT_BINDING, SOURCE_SHA, asset_identity, read, save, sha


PINNED = {
    V / 'm4_global_local_qualification_001/fixture/GEOMETRY.json': '34c4ad599c6ead7548b21300315df25808fa274dad9dccafbf3b5808fee56ad8',
    V / 'm4_occluded_scene_transfer_001/inputs/SCENE_GEOMETRY_RATIONAL.json': 'b8e9c63f636a1b1262b377163c9b1519ee9db9e7f5b39297b8ba0c1dc2e2ce74',
    PRODUCT_BINDING: 'eb0ecece262ce0fbbe2b01f041b9e6eab77f0c4810030094c2f590850f51b2e0',
    Path(sys.executable): '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869',
    BLENDER: '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb',
}


def frozen():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or (RUN / 'slots').exists():
        raise ValueError('fresh paired admission and pinned interpreter required')
    prepared = read(NS / 'PREPARED.json')
    if prepared['plan_hash'] != sha(NS / 'inputs/PLAN.md') or prepared['plan_hash'] != '05013f1effc9f0d4ca11c2a4900d8b149bb9aaaae80e2f6f079884796b6d89ae':
        raise ValueError('planning source changed')
    asset, digest = asset_identity()
    asset_record = read(NS / 'fixture/ASSET_BINDING.json')
    truth = read(NS / 'fixture/CURRENT_TRUTH.json')
    if (not truth['passed'] or truth['current_blender_evaluated_readback'] is not True or
            asset_record['counts'] != {'objects': 21, 'vertices': 148, 'triangles': 184}):
        raise ValueError('fixed actual Blender truth required')
    pins = {**PINNED, asset: digest}
    for key in ('readback_before_save', 'readback_after_reload'):
        row = asset_record[key]
        pins[Path(row['path'])] = row['sha256']
    builder = ORIGINAL_RUN / 'fixture_preparation/RESULT.json'
    pins[builder] = '87ca27e54d48f7651c888e1dfff2deec236c12694679524a787d2cf1c99d2178'
    pins.update({Path(row['path']): row['sha256'] for row in asset_record['input_pins']})
    startup = RECOVERY_RUN / 'preflight/installed_handshake_01/PREFLIGHT.json'
    passthrough = ORIGINAL_RUN / 'preflight/ordinary_passthrough_02/PREFLIGHT.json'
    pins[startup] = '9dc222b229774a0269b466a6f5b4b6c3713a5494ecfbf4fcc1969e40d6d98891'
    pins[passthrough] = 'd3ec2b7f42575ee2aa6bb684e6ab3e991151e38d94951f38e6f158821cb4eb2a'
    actual = read(startup)
    if not actual['passed'] or not read(passthrough)['passed'] or actual['schema_sha256'] != sha(NS / 'inputs/PRODUCT_SCHEMA.json'):
        raise ValueError('actual independent preflights did not bind this schema')
    pins.update({Path(row['path']): row['sha256'] for row in actual['additional_runtime_sources']})
    host_replay = RECOVERY_RUN / 'preflight/host-replay_02/PREFLIGHT.json'
    pins[host_replay] = 'd1c74675e5818608734858ddfe104d5f109da784f5dc2d0f29769c6bce47f430'
    replay = read(host_replay)
    if not replay['passed'] or any(replay[field] for field in ('Blender_launches', 'model_launches', 'product_requests', 'raster_attempts')):
        raise ValueError('final generic host replay must pass without live work')
    pins.update({Path(row['path']): row['sha256'] for row in replay['source_pins']})
    scorer_preflight = RECOVERY_RUN / 'preflight/scoring/DETAIL_CONTROLS.json'
    pins[scorer_preflight] = 'c0c76e8329572667c3e3ac4cf18206371ac829598a22e301431d4ac31f7222c5'
    current_score = RUN / 'preflight/scoring/PREFLIGHT_FINAL.json'
    pins[current_score] = '441dba3a5d048a77ef63d96340b097c7478c71fe7ce301d93849638d28f6ed55'
    pins.update({ROOT / name: digest for name, digest in prepared['previous_source_pins'].items()})
    pins[ORIGINAL_RUN / 'ORIGINAL_RUNTIME.zip'] = '619625cb05409ce46be57aa8159df9021ca76375a4df6234866f3f1710169f0d'
    pins[RECOVERY_RUN / 'ORIGINAL_RUNTIME.zip'] = '721a454beadcb5104a6866b50e05f9e7f3335da57767cb6119d4888fbb14bf65'
    previous_cost = V / 'm4_cross_scale_live_task_recovery_001/RUNTIME_REVIEW.json'
    pins[previous_cost] = sha(previous_cost)
    offline_path = NS / 'checks/OFFLINE_EVIDENCE.json'
    offline = read(offline_path)
    pins[offline_path] = sha(offline_path)
    for row in offline['source_pins']:
        f = Path(row['path'])
        if 'bytes' in row and f.stat().st_size != row['bytes']:
            raise ValueError('offline evidence source length changed/' + str(f))
        pins[f] = row['sha256']
    formal_replay = RUN / 'preflight/formal_event_replay_01/PREFLIGHT.json'
    pins[formal_replay] = '20df3aac39819a58bfc0a0b0e96dc200df0c311623800f8ca0a1e4be030e4cf1'
    formal = read(formal_replay)
    if not formal['passed'] or any(formal[field] for field in ('actual_model_runs', 'actual_Blender_processes', 'actual_raster')):
        raise ValueError('real-envelope formal event replay must pass without live calls')
    for replay_case in formal['cases'].values():
        pins.update({Path(row['path']): row['sha256'] for row in replay_case['original_wire_pins']})
    pins.update({Path(row['path']): row['sha256'] for row in formal['formal_execution_sources']})
    for name in ('PROMPT_N.txt', 'PROMPT_P.txt', 'PROMPT_COMMON.txt', 'DIAGNOSTIC_N.json', 'PRODUCT_SCHEMA.json', 'REQUEST.json'):
        if (NS / 'inputs' / name).read_bytes() != (ORIGINAL / 'inputs' / name).read_bytes():
            raise ValueError('common task bytes changed/' + name)
    binding = read(PRODUCT_BINDING)
    if binding['source_sha256'] != SOURCE_SHA or len(binding['source_manifest']) != 143:
        raise ValueError('unchanged installed product required')
    pins.update({Path(binding['install_root']) / row['path']: row['sha256'] for row in binding['source_manifest']})
    dependency_path = V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json'
    dependencies = read(dependency_path)
    pins.update({Path(p): h for p, h in dependencies['files_sha256'].items()})
    sys.path[:0] = [str(NS), binding['dependency_root'], dependencies['dependency_root']]
    from consumer import consumer_adapter
    _, cli, _ = consumer_adapter()
    pins.update({Path(row['path']): row['sha256'] for row in cli['execution_sources']})
    pins[Path(cli['CLI_path'])] = cli['CLI_sha256']
    auth = subprocess.run([cli['CLI_path'], 'login', 'status'], check=True, capture_output=True, timeout=15)
    if b'Logged in using ChatGPT' not in auth.stdout + auth.stderr:
        raise ValueError('fixed local ChatGPT login required')
    reused = ['m4_target_task_consumption_001/native_consumer_audit.py', 'm5_harness_recovery_001/native_tools.py',
              'm4_active_coverage_consumption_001/image_content.py',
              'm4_cross_scale_live_qualification_001/checks/delivery.py',
              'm1_source_region_facts_first_001/checks/CLIENT_BUDGET_REVIEW.json',
              'm1_source_region_facts_first_001/checks/client_budget_replay.py',
              'm4_global_local_qualification_001/oracle/static_oracle.py',
              'm4_global_local_qualification_001/oracle/STATIC_QUALIFICATION.json',
              'm4_global_local_qualification_001/checks/saved_frames_r2.py']
    for stem in ('m4_live_source_region_task_003/harness', 'm4_source_region_display_001/harness',
                 'm4_cross_scale_discovery_001/oracle'):
        reused.extend(str(path.relative_to(V)) for path in (V / stem).rglob('*.py'))
    for f in [dependency_path, *(V / name for name in reused), *NS.rglob('*')]:
        if f.is_file() and f.name not in ('FROZEN.json', 'ADMISSION.json'):
            if f.suffix == '.py':
                ast.parse(f.read_bytes(), filename=str(f))
            pins.setdefault(f.resolve(), sha(f))
    for path, digest in pins.items():
        if sha(path) != digest or path.suffix == '.pyc':
            raise ValueError('pinned input changed/' + str(path))
    by_path = {p.resolve(): digest for p, digest in pins.items()}
    save(NS / 'FROZEN.json', {'schema': 'm4-cross-scale-live-task-formal-v1', 'started_ns': started,
         'completed_ns': time.perf_counter_ns(), 'direct_inputs': [{'path': str(path), 'sha256': by_path[path],
             'bytes': path.stat().st_size} for path in sorted(by_path)],
         'shared_dependency_root': dependencies['dependency_root'], 'slots': ['N1', 'P1'],
         'limits': {'builder': 0, 'owned': 2, 'additional_qualification': 0, 'business_per_slot': 12, 'raster_per_slot': 12, 'raster_total': 24,
                    'models': 2, 'paid_API': 0, 'replacements': 0, 'task_s': 450, 'owned_s': 600},
         'quotas_before_freeze': {'builder': 0, 'owned': 0, 'consumers': 0}, 'fixed_CLI_requested': cli['model'],
         'consumer_execution_source_count': len(cli['execution_sources'])})
    print('Frozen', len(by_path), sha(NS / 'FROZEN.json'))


if __name__ == '__main__':
    frozen()
