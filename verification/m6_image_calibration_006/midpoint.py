"""One preregistered half-amplitude saved-mesh and render counterexample."""
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import time

import numpy as np


HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6im5/batch'
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005')
WORK = HERE / 'private/midpoint/workers'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
ALPHA = .5
VIEWS = ('forearm_front', 'forearm_side', 'forearm_45')


def write(path, value):
    path.write_bytes((json.dumps(value, indent=2) + '\n').encode())


def identity(path):
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def run_worker(script, job, name):
    job_path = WORK / (name + '_job.json')
    job['receipt_path'] = str(WORK / (name + '_receipt.json'))
    write(job_path, job)
    command = [str(BLENDER), '--factory-startup', '--disable-autoexec', '--background', '--threads', '1',
               job['current_blend'], '--python-exit-code', '23', '--python', str(WORK / script), '--', '--job', str(job_path)]
    started = time.perf_counter()
    result = subprocess.run(command, capture_output=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
    (WORK / (name + '_stdout.bin')).write_bytes(result.stdout)
    (WORK / (name + '_stderr.bin')).write_bytes(result.stderr)
    record = dict(command=command, returncode=result.returncode, wall_s=time.perf_counter() - started,
                  worker=identity(WORK / script), job=identity(job_path))
    write(WORK / (name + '_process.json'), record)
    assert result.returncode == 0, (name, result.stderr.decode(errors='replace'))
    assert Path(job['receipt_path']).exists(), name
    return record


def main():
    started = time.perf_counter()
    WORK.mkdir(parents=True, exist_ok=False)
    worker_files = ('blender_common.py', 'blender_edit.py', 'blender_read.py', 'blender_render.py')
    for name in worker_files:
        shutil.copyfile(BASE / name, WORK / name)
        assert (WORK / name).read_bytes() == (BASE / name).read_bytes()
    state = json.loads((BASE / 'private/sessions/v1_repair_native/session.json').read_bytes())
    payload_sha = state['operations'][0]['payload_sha256']
    candidates = sorted(row['path'] for row in json.loads((BASE / 'MANIFEST.json').read_bytes())['files'] if row['sha256'] == payload_sha)
    assert candidates
    source_payload = BASE / candidates[0]
    with np.load(source_payload) as data:
        ids, values = data['source_ids'], data['displacements_world']
    assert len(ids) == 40
    np.savez_compressed(WORK / 'half_payload.npz', source_ids=ids, displacements_world=ALPHA * values)
    initial_path = BASE / 'private/cases/repair/initial.npz'
    baseline_blend = BASE / 'private/cases/repair/before.blend'
    spec = json.loads((BASE / 'private/cases/repair/spec.json').read_bytes())
    plan = dict(candidate='005/v1/native actual frozen payload', alpha=ALPHA,
                image_metric='Pooled RGB MAE across all three640x640 local views, normalized to initial. No mask, ROI, weights or thresholds.',
                selected_before_new_render=True, source_payload=identity(source_payload), baseline=identity(baseline_blend),
                workers=[identity(WORK / name) for name in worker_files], hidden_target_read_before_image_result=False)
    write(HERE / 'MIDPOINT_PLAN.json', plan)
    common = dict(object_name=spec['object_name'], source_original=spec['source_original'])
    processes = [run_worker('blender_edit.py', dict(common, current_blend=str(baseline_blend),
        expected_input_sha256=identity(baseline_blend)['sha256'], output_blend=str(WORK / 'half.blend'),
        allowed_ids_path=str(initial_path), edit_payload=str(WORK / 'half_payload.npz'), operation_id='root_fixed_half_amplitude'), 'edit')]
    processes.append(run_worker('blender_read.py', dict(common, current_blend=str(WORK / 'half.blend'),
        expected_input_sha256=identity(WORK / 'half.blend')['sha256'], readback_npz=str(WORK / 'readback.npz'),
        scene_signature_json=str(WORK / 'scene.json')), 'read'))
    render_module = (WORK / 'blender_render.py').read_text(encoding='utf8')
    # The three local specifications are copied verbatim from the executed renderer.
    import ast
    tree = ast.parse(render_module)
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'DEFAULT_VIEWS' for target in node.targets))
    specifications = eval(compile(ast.Expression(assignment.value), '<frozen render views>', 'eval'), {'dict': dict})[1:]
    processes.append(run_worker('blender_render.py', dict(common, current_blend=str(WORK / 'half.blend'),
        output_dir=str(WORK / 'images'), views=specifications), 'render'))
    png_reader = runpy.run_path(str(HERE.parent / 'm6_image_correspondence_005_plan/probe.py'))['read_png']
    rows = json.loads((BASE / 'IMAGE_BINDING.json').read_bytes())['images']
    by_role = {row['role']: row for row in rows}
    losses = {name: 0 for name in ('initial', 'half', 'full')}
    sample_count = 0
    for view in VIEWS:
        normal_entry = by_role['normal_' + view]
        current_entry = by_role['current_' + view]
        normal_path = BASE / Path(normal_entry['path']).relative_to(AUTHOR)
        current_path = BASE / Path(current_entry['path']).relative_to(AUTHOR)
        reference = png_reader(normal_path).astype(np.int16)
        paths = dict(initial=current_path, half=WORK / 'images' / (view + '.png'),
                     full=BASE / 'private/results/v1_repair_native/after_views' / (view + '.png'))
        for name, path in paths.items():
            pixels = png_reader(path).astype(np.int16)
            assert pixels.shape == reference.shape
            losses[name] += int(np.abs(pixels - reference).sum())
        sample_count += reference.size
    mae = {name: value / sample_count for name, value in losses.items()}
    image_result = dict(plan=plan, processes=processes, MAE_DN=mae,
                        normalized_to_initial={name: value / mae['initial'] for name, value in mae.items()},
                        sample_count=sample_count, hidden_target_read=False)
    write(HERE / 'MIDPOINT_IMAGE_RESULT.json', image_result)
    # Private scoring starts after actual image measurements have been frozen.
    helpers = runpy.run_path(str(HERE.parent / 'm6_matched_refine_003_review/review.py'))
    with np.load(BASE / 'private/scoring/target.npz') as packet:
        target = {name: packet[name] for name in packet.files}
    with np.load(WORK / 'readback.npz') as packet:
        actual = {name: packet[name] for name in packet.files}
    with np.load(initial_path) as packet:
        initial = {name: packet[name] for name in packet.files}
    support, editable = target['support_ids'], target['I_ids']
    normal_ids = np.setdiff1d(editable, support)
    error = actual['vertices_world'] - target['clean_vertices_world']
    delta = actual['vertices_world'] - initial['vertices_world']
    baseline_error = target['initial_vertices_world'] - target['clean_vertices_world']
    statistics = helpers['statistics']
    support_metrics = statistics(error, support)
    support_reduction = 1 - support_metrics['RMSE_m'] / statistics(baseline_error, support)['RMSE_m']
    normal_misedit = statistics(delta, normal_ids)
    outside = np.setdiff1d(initial['source_ids'], editable)
    np.testing.assert_array_equal(actual['vertices_local'][outside], initial['vertices_local'][outside])
    for name in ('matrix_world', 'source_ids', 'poly_offsets', 'poly_vertices'):
        np.testing.assert_array_equal(actual[name], initial[name])
    quality = dict(support=support_metrics, support_RMSE_reduction_fraction=support_reduction,
                   normal_editable_misedit=normal_misedit,
                   observation=statistics(error, target['F_source_ids']), outside_native_bitwise=True,
                   derived_triangle_arrays_equal=bool(np.array_equal(actual['faces'], initial['faces'])),
                   full_contact_QA='not_run_in_root_targeted_counterexample')
    result = dict(status='completed_one_fixed_midpoint_counterexample', alpha=ALPHA, image_result=image_result,
                  private_quality=quality, new_Blender=3, new_Pro=0, new_training=0, wall_s=time.perf_counter() - started)
    write(HERE / 'MIDPOINT_RESULT.json', result)
    print(json.dumps(dict(alpha=ALPHA, normalized_image_MAE=image_result['normalized_to_initial'], quality=quality,
                         new_Blender=3, new_Pro=0, wall_s=result['wall_s'])))


if __name__ == '__main__':
    main()
