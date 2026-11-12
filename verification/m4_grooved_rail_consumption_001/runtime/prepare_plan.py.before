"""Bind existing installation, actual input and thin adapters without consumers."""

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
CYCLE = 'M4-SPATIAL-FACT-CONSUMPTION-001'
SOURCE = '2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    assert not (BATCH / 'STARTED.json').exists()
    ready = read(BATCH / 'installations/P_READY.json')
    assert ready['commit'] == 'e836e03f4b3821f869c72ac3e50df5204f28b50f'
    assert ready['source_sha256'] == SOURCE and ready['source_count'] == 137
    frozen = read(ROOT / 'verification/m3_sufficient_separation_001/CANDIDATE_FREEZE.json')
    for row in frozen['manifest']:
        assert sha(ROOT / row['path']) == sha(Path(ready['install_root']) / row['path']) == row['sha256']
    assert sha(Path(ready['entry'])) == ready['launcher_sha256']
    assert sha(Path(ready['release']) / 'admin/RUNTIME_BINDING.json') == ready['binding_sha256']
    previous = ROOT / 'verification/m3_sufficient_separation_001/entry/run_01'
    session = read(previous / 'native/SESSION.json')
    assert Path(session['asset_copy']).resolve() == (previous / 'native/input.blend').resolve()
    assert sha(previous / 'native/input.blend') == sha(BATCH / 'input/scene.blend') == session['asset_sha256']
    assert session['asset_sha256'] == '27f197a8cc312832382ae06cb633cbf846f20a1a22797909a15dfda8513ade46'
    assert sha(BATCH / 'scoring/ACTUAL_SNAPSHOT.json') == sha(previous / 'ACTUAL_SNAPSHOT.json')
    listed = read(previous / 'TOOLS.json')['result']['tools']
    observe = [tool for tool in listed if tool['name'] == 'human_eye_scene_observe']
    assert read(BATCH / 'schemas/P_PUBLIC_TOOLS.json') == observe and len(observe) == 1
    base = ROOT / 'verification/native_plugin_complex_003/actor.py'
    tree = ast.parse(base.read_bytes())
    native = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'NATIVE' for target in node.targets)))
    assert read(BATCH / 'schemas/COMMON_NATIVE.json') == native
    save(BATCH / 'schemas/N_CONSUMER_TOOLS.json', [native])
    save(BATCH / 'schemas/P_CONSUMER_TOOLS.json', [native, observe[0]])
    source_binding = {
        'source_count': 137, 'source_sha256': SOURCE, 'source_manifest': frozen['manifest'],
        'installation_ready_sha256': sha(BATCH / 'installations/P_READY.json'),
        'actual_asset_copy': str(previous / 'native/input.blend'), 'session_sha256': sha(previous / 'native/SESSION.json'),
        'asset_sha256': session['asset_sha256'], 'snapshot_sha256': sha(BATCH / 'scoring/ACTUAL_SNAPSHOT.json'),
        'previous_actual_tools_list': str(previous / 'TOOLS.json'),
        'previous_actual_tools_list_sha256': sha(previous / 'TOOLS.json'),
        'common_native_schema_unchanged': True, 'observe_declaration_unchanged': True,
        'models': 0, 'Blender_sessions': 0, 'installation_rebuilt': False,
    }
    save(BATCH / 'preflight/SOURCE_BINDING.json', source_binding)
    protected = [Path('C:/Users/Administrator/.codex/config.toml'), Path('D:/hefe/.codex/config.toml'),
                 ROOT / 'pyproject.toml', previous / 'native/input.blend',
                 ROOT / 'verification/spatial_task_qualification_001/assets/G508_control.blend']
    save(BATCH / 'preflight/PROTECTED_BEFORE.json', {str(path): sha(path) if path.is_file() else None for path in protected})
    save(BATCH / 'BENEFIT_CONTRACT.json', {
        'quality_before_cost': True, 'all_six_retained': True, 'full_correct_per_arm_required': 3,
        'useful_benefit': 'P median full-cell time <=N and P cumulative actual input+output tokens <=N, at least one improves >=10%',
        'usage': 'final cumulative per cell; deduplicate request-level data and exclude overlapping cached/reasoning subitems',
        'missing_usage_or_failed_or_not_run': 'main useful-benefit gate cannot pass',
        'unmeasured': ['fees unless exposed', 'resolved model/effort unless exposed', 'provider request count unless exposed'],
    })
    save(BATCH / 'MECHANISM_CLASSIFICATION.json', {
        'criterion': 'at least two of three P consumers naturally request spatial_relation plus surface_proximity, use it correctly, and avoid recomputing the same fully answered facts natively',
        'separate_from_quality': True, 'categories': ['directory_or_identity', 'new_information', 'unresolved_verification', 'recompute_already_complete_facts'],
        'evaluation_after_anonymous_quality_sealed': True,
    })
    cli = Path('C:/Users/Administrator/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe')
    external_paths = [cli, base, ROOT / 'verification/native_plugin_complex_003/reused/accepted_native.py',
                      ROOT / 'verification/native_plugin_complex_003/reused/stdio_attach.py',
                      ROOT / 'verification/m1_task_entry_001_eval/preflight_client.py',
                      Path(ready['entry']), Path(ready['release']) / 'admin/installed_release.py',
                      Path(ready['release']) / 'admin/RUNTIME_BINDING.json']
    inputs = {
        'scene': 'input/scene.blend', 'scene_sha256': sha(BATCH / 'input/scene.blend'),
        'prompt': 'input/PROMPT.txt', 'prompt_sha256': sha(BATCH / 'input/PROMPT.txt'),
        'image': None, 'image_bytes': 0, 'image_sha256': None,
    }
    materials = [{'path': 'scoring/' + name, 'sha256': sha(BATCH / 'scoring' / name), 'public_name': name}
                 for name in ('SCORING_CONTRACT.json', 'ACTUAL_SNAPSHOT.json', 'TRUTH.json')]
    plan = {
        'cycle_id': CYCLE, 'batch': CYCLE, 'logical_denominator': 6, 'per_arm': 3,
        'image_count': 0, 'new_images': 0, 'tool_images': 0, 'inputs': inputs,
        'sequence': read(BATCH / 'SEQUENCE.json')['sequence'],
        'arms': {'N': {'actor_group': 'N', 'installation_profile': 'P', 'source_sha256': None},
                 'P': {'actor_group': 'P', 'installation_profile': 'P', 'source_sha256': SOURCE}},
        'installations': {'P': ready}, 'installation_ready': ready,
        'tasks': {'T1': {'asset': inputs['scene'], 'asset_sha256': inputs['scene_sha256'],
                        'snapshot': 'scoring/ACTUAL_SNAPSHOT.json',
                        'snapshot_sha256': sha(BATCH / 'scoring/ACTUAL_SNAPSHOT.json')}},
        'model': 'gpt-6.1-sol', 'requested_effort': 'medium', 'resolved_effort': None,
        'resolved_model': None, 'quality_before_cost': True,
        'max_session_seconds': 450, 'total_cell_seconds': 570, 'actor_startup_seconds': 40,
        'tool_attempts': 32, 'physical_RPC_limit': 128, 'tool_timeout_s': 30,
        'tool_response_bytes': 1048576, 'code_bytes': 262144,
        'quality_materials': materials,
        'private_anonymous_map_sha256': sha(BATCH / 'private/ANON_MAP.json'),
        'CLI_sha256': sha(cli), 'actor_sha256': sha(HERE / 'actor.py'),
        'consumer_transport_sha256': sha(HERE / 'consumer_transport.py'),
        'preflight_driver_sha256': sha(HERE / 'driver.py'),
        'quality_handoff_script_sha256': sha(HERE / 'pack_quality.py'),
        'source_count': 137, 'fixed_product_commit': ready['commit'], 'candidate_source_sha256': SOURCE,
        'root_plan_sha256': sha(BATCH / 'ROOT_PLAN.md'),
        'external_input_sha256': {str(path.resolve()): sha(path) for path in external_paths},
        'dispatch_input_sha256': {},
        'authorization': 'parent plan includes preparation and frozen six formal slots, no separate approval',
        'blinding_scope': 'cost and group labels masked; business content can reveal route',
        'isolation_scope': 'same trusted native Python audit boundary, empty workspaces, CLI hooks/rules/memory/tools disabled as frozen; no OS-level Python sandbox claim',
        'smoke_sessions': 0, 'smoke_decision': 'offline bridge tests plus prior same-byte ordinary MCP evidence cover the changed forwarding and declaration',
        'prepared_utc': datetime.now(timezone.utc).isoformat(),
    }
    for relative in ('ROOT_PLAN.md', 'WORK_ORDER.json', 'BENEFIT_CONTRACT.json', 'MECHANISM_CLASSIFICATION.json',
                     'SEQUENCE.json', 'private/ANON_MAP.json', 'installations/P_READY.json',
                     'preflight/SOURCE_BINDING.json', 'input/PROMPT.txt', 'input/scene.blend',
                     'schemas/COMMON_NATIVE.json', 'schemas/P_PUBLIC_TOOLS.json',
                     'schemas/N_CONSUMER_TOOLS.json', 'schemas/P_CONSUMER_TOOLS.json',
                     'scoring/SCORING_CONTRACT.json', 'scoring/ACTUAL_SNAPSHOT.json', 'scoring/TRUTH.json',
                     'runtime/actor.py', 'runtime/consumer_transport.py', 'runtime/driver.py',
                     'runtime/pack_quality.py', 'runtime/run_formal.py', 'runtime/prepare_plan.py'):
        plan['dispatch_input_sha256'][relative] = sha(BATCH / relative)
    save(BATCH / 'PLAN.json', plan)
    print(json.dumps({'prepared_slots': 6, 'product_rebuilt': False, 'model_consumers': 0, 'Blender_sessions': 0}))


if __name__ == '__main__':
    main()
