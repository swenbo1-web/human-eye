"""Check both product arms' new path isolation without opening an owner."""
import argparse
import importlib.util
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
EXTERNAL = Path('D:/he_source_face_001')
PREVIOUS = Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_occluded_scene_transfer_001')
SHARED = Path('D:/he_occluded_transfer_001/shared_dependencies')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arm', choices=['A','B'], required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(SHARED))
    sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
    spec = importlib.util.spec_from_file_location('_m1_native_isolation', HERE / 'native_tools.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    owner = module.ObservationSession.__new__(module.ObservationSession)
    owner.output = HERE / 'offline_interface' / ('isolation_' + args.arm)
    owner.output.mkdir(parents=True, exist_ok=False)
    plan = json.loads((HERE / 'PLAN.json').read_bytes())
    binding = json.loads(Path(plan['products'][args.arm]['path']).read_bytes())
    owner.product_root = Path(binding['install_root']).resolve()
    owner.source_inputs = dict(scene_path=str(PREVIOUS / 'inputs/SCENE_GEOMETRY_RATIONAL.json'),
        cameras_path=str(PREVIOUS / 'inputs/CAMERAS.json'))
    owner.budget_root = EXTERNAL / 'raster_budget'
    owner._private_paths = {HERE / ('inputs/SOURCES_' + args.arm + '.json'), PREVIOUS / 'inputs/CAPTURE_REPLAY.json'}
    owner._consumer_running = False
    owner._budget_io = False
    owner.audit = dict(forbidden_old_writes=0, forbidden_old_evidence_reads=0,
        old_write_attempts=[], old_evidence_read_attempts=[], forbidden_product_calls=[])
    owner.install_audit()
    checks = {}
    with owner.consumer_scope():
        from shapely.geometry import Polygon
        checks['actual_common_Polygon_operation'] = Polygon([(0,0),(2,0),(2,2),(0,2)]).area == 4
        path = owner.output / 'OWN.txt'
        path.write_text('owner', encoding='utf-8')
        checks['own_output_allowed'] = path.read_text(encoding='utf-8') == 'owner'
        for name, path in [
            ('old_answer_read_blocked', PREVIOUS / 'admin/NORMALIZED.json'),
            ('old_runtime_read_blocked', Path('D:/he_occluded_transfer_001/formal/P1/o/OBSERVATIONS.json')),
            ('new_qualification_read_blocked', EXTERNAL / 'preparation/Q01/QA/o/OBSERVATIONS.json'),
            ('other_arm_read_blocked', EXTERNAL / 'formal/B3/o/OBSERVATIONS.json'),
            ('private_truth_read_blocked', HERE / 'admin/TRUTH.json')]:
            try:
                path.read_bytes()
            except PermissionError:
                checks[name] = True
            else:
                checks[name] = False
        try:
            (SHARED / 'consumer_write.txt').write_bytes(b'forbidden')
        except PermissionError:
            checks['shared_dependency_write_blocked'] = True
        else:
            checks['shared_dependency_write_blocked'] = False
        checks['common_source_geometry_read_allowed'] = bool(Path(owner.source_inputs['scene_path']).read_bytes())
    assert all(checks.values()), checks
    print(json.dumps(dict(arm=args.arm, checks=checks, passed=True,
        actual_observation_sessions=0, model_calls=0, raster_calls=0, audit=owner.audit)))


if __name__ == '__main__':
    main()
