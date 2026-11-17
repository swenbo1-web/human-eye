"""Pin the accepted product and adapt owned evidence tooling for one real asset."""

import hashlib
import json
from pathlib import Path
import shutil
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'verification/m4_m5_source_region_001'
RUNTIME = Path('D:/he_m4_real_asset_region_001')
ASSET = Path('D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend')
ASSET_SHA = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
M6 = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_real_data_001/private')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def main():
    assert sha(ASSET) == ASSET_SHA
    RUNTIME.mkdir(exist_ok=False)
    (HERE / 'harness/reused').mkdir(parents=True, exist_ok=True)
    (HERE / 'inputs').mkdir(exist_ok=False)
    (HERE / 'public_schema').mkdir(exist_ok=False)
    copied = []
    names = ['budget.py', 'owned_runtime.py', 'mcp_entry.py', 'state_owned_native.py',
             'reused/owned_native.py', 'reused/process_proof.py', 'reused/stdio_checks.py',
             'reused/verified_bootstrap.py', 'reused/wire_meter.py']
    for name in names:
        source = OLD / 'harness' / name
        target = HERE / 'harness' / name
        shutil.copyfile(source, target)
        copied.append({'source': str(source), 'source_sha256': sha(source), 'target': str(target)})
    for name in ['reused/owned_native.py', 'state_owned_native.py']:
        path = HERE / 'harness' / name
        text = path.read_text(encoding='utf8').replace("    bpy.context.scene.render.filepath=str(renders_directory/'default.png')\n", '')
        path.write_text(text, encoding='utf8', newline='\n')
    for name in ['R1_RUN_BINDING.json', 'SHARED_DEPENDENCY.json']:
        shutil.copyfile(OLD / name, HERE / name)
    shutil.copyfile(OLD / 'public_schema/R1_scene_observe.json', HERE / 'public_schema/R1_scene_observe.json')
    source_inputs = [M6 / 'ARM_REGION.json', M6 / 'capture_02/raw_selected.json',
                     M6 / 'capture_02/evaluated_selected.json',
                     Path('D:/hefe/verification/fixes/20261117_source_region_review/next/REAL_ASSET_PREFLIGHT.json'),
                     Path('D:/hefe/docs/M4_REAL_ASSET_REGION_QUALIFICATION_001_PLAN.md')]
    for source in source_inputs:
        target_name = source.name
        shutil.copyfile(source, HERE / 'inputs' / target_name)
    runtime = HERE / 'harness/owned_runtime.py'
    text = runtime.read_text(encoding='utf8')
    text = text.replace("EXTERNAL = Path('D:/he_m4_m5_source_region_001')", "EXTERNAL = Path('D:/he_m4_real_asset_region_001')")
    text = text.replace("ASSET = EXTERNAL / 'fixture/main.blend'", 'ASSET = Path(' + repr(str(ASSET)) + ')')
    text = text.replace("json.loads((NAMESPACE/'fixture/ASSET_BINDING.json').read_bytes())['asset_sha256']", repr(ASSET_SHA))
    text = text.replace('group not in ("R0", "R0F", "R1")', 'group != "R1"')
    runtime.write_text(text, encoding='utf8', newline='\n')
    budget = HERE / 'harness/budget.py'
    budget.write_text(budget.read_text(encoding='utf8').replace('"Blender_start_attempts": 8, "all_rasters": 24',
                      '"Blender_start_attempts": 2, "all_rasters": 4'), encoding='utf8', newline='\n')
    state = HERE / 'harness/state_owned_native.py'
    text = state.read_text(encoding='utf8').replace('b9cf3671bc8cd5b88ed23118f229a6e753eda40802d35a3ad297961e0a9edcf9', ASSET_SHA)
    text = text.replace('Obj_07', '0135bbc4-c6c7-4003-a402-6f2e0283497d')
    matrix = json.loads((M6 / 'capture_02/raw_selected.json').read_bytes())['matrix_world']
    translated = [row[:] for row in matrix]
    translated[0][3] += .25
    text = text.replace('M5_IDENTITY=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]', 'M5_IDENTITY=' + repr(matrix))
    text = text.replace('M5_TRANSLATED=[[1.,0.,0.,.25],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]', 'M5_TRANSLATED=' + repr(translated))
    text = text.replace('need(world_after==expected_world,"m5_world_points_readback")',
                        'need(all(abs(a-b)<=3e-8 for p,q in zip(world_after,expected_world) for a,b in zip(p,q)),"m5_world_points_readback")')
    state.write_text(text, encoding='utf8', newline='\n')
    pins = []
    for source in source_inputs + [OLD / 'CONTENT_MANIFEST.json', OLD / 'DECISION.json', OLD / 'R1_RUN_BINDING.json']:
        pins.append({'path': str(source), 'bytes': source.stat().st_size, 'sha256': sha(source)})
    save(HERE / 'BASELINE.json', {'task': 'M4-REAL-ASSET-REGION-QUALIFICATION-001',
        'baseline_git': 'de884a2a44557fb3d01407c5e7c2883cc4aa749c',
        'product_git': '2292c3d79e9996fb29b0c3351102998923113d56',
        'source_sha256': '8d8d3d60e99b5e039e6711c168f95d648124e96eea03b0a061b2796c5a690600',
        'direct_pins': pins, 'reused_harness': copied, 'asset': {'path': str(ASSET), 'sha256': ASSET_SHA},
        'limits': {'owned': 2, 'rasters': 4, 'preparation_Blender': 0, 'models': 0, 'public_s': 30, 'owned_s': 600},
        'registered_ns': time.perf_counter_ns(), 'product_changes': 0, 'default_install_changes': 0,
        'agent_learning': {'task_writes': 0, 'status': 'pending_no_current_context_handle'}})


if __name__ == '__main__':
    main()
