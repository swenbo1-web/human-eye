"""Exercise the new runtime path boundary without starting an observation."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
EXTERNAL = Path('D:/he_occluded_transfer_001')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--group', choices=['N', 'P'], required=True)
    group = parser.parse_args().group
    sys.path.insert(0, str(EXTERNAL/'shared_dependencies'))
    sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
    spec = importlib.util.spec_from_file_location('_transfer_isolation_native', HERE/'native_tools.py')
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    session = native.ObservationSession.__new__(native.ObservationSession)
    session.output = HERE/'offline_interface'/('isolation_'+group)
    session.output.mkdir(parents=True, exist_ok=False)
    session.product_root = Path('D:/he_view_reuse_001/product')
    session.source_inputs = dict(scene_path=str(HERE/'inputs/SCENE_GEOMETRY_RATIONAL.json'),
                                cameras_path=str(HERE/'inputs/CAMERAS.json'))
    session.budget_root = EXTERNAL/'raster_budget'
    session._private_paths = {HERE/'inputs/CAPTURE_REPLAY.json', HERE/'inputs/SOURCES.json'}
    session._consumer_running = False
    session._budget_io = False
    session.audit = dict(forbidden_old_writes=0, forbidden_old_evidence_reads=0,
        old_write_attempts=[], old_evidence_read_attempts=[], forbidden_product_calls=[])
    session.install_audit()
    checks = {}
    with session.consumer_scope():
        from shapely.geometry import Polygon
        checks['shared_Polygon_import_and_operation'] = Polygon([(0,0),(2,0),(2,2),(0,2)]).area == 4
        own = session.output/'OWN.txt'
        own.write_text('own_output', encoding='utf-8')
        checks['own_output_allowed'] = own.read_text(encoding='utf-8') == 'own_output'
        for name, path in (
            ('qualification_read_blocked', EXTERNAL/'preparation/QN/o/OBSERVATIONS.json'),
            ('other_slot_read_blocked', EXTERNAL/'formal/P3/o/OBSERVATIONS.json'),
            ('private_truth_read_blocked', HERE/'admin/TRUTH.json')):
            try:
                path.read_bytes()
            except PermissionError:
                checks[name] = True
            else:
                checks[name] = False
        try:
            (EXTERNAL/'shared_dependencies/consumer_write.txt').write_bytes(b'forbidden')
        except PermissionError:
            checks['shared_dependency_write_blocked'] = True
        else:
            checks['shared_dependency_write_blocked'] = False
    assert all(checks.values()), checks
    print(json.dumps(dict(group=group,checks=checks,passed=True,actual_observation_sessions=0,
        new_rasters=0,model_calls=0,audit=session.audit),ensure_ascii=False))


if __name__ == '__main__':
    main()
