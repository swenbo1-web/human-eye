"""Record one narrow CPU attempt without replaying accepted historical matrices."""
import hashlib
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
SOURCE_TESTS = [
    'test_selected_402_vertices_and_800_faces_do_not_expand_200000_vertex_asset',
    'test_pose_and_frame_update_reuse_prepared_static_and_return_current_source',
    'test_dirty_notification_without_static_change_does_not_reprepare',
    'test_rest_weights_and_topology_changes_each_rebuild_preparation',
    'test_undo_and_load_reset_source_and_static_even_for_identical_geometry',
    'test_inflight_source_change_does_not_publish_partial_preparation',
]


def main():
    label = sys.argv[1]
    folder = OUT / label
    folder.mkdir(exist_ok=False)
    from human_eye_plugin.runtime_identity import runtime_identity
    identity = runtime_identity()
    (folder / 'identity_before.json').write_text(json.dumps(identity, indent=2) + '\n', encoding='utf8')
    executing = [OUT / 'test_entry_opt.py', OUT / 'run_cpu.py',
        ROOT / 'verification/arch_expert_entry_001/test_entry.py',
        ROOT / 'verification/m6_arm_source_001/test_arm_source.py']
    for path in executing:
        (folder / (path.parent.name + '_' + path.name + '.txt')).write_bytes(path.read_bytes())
    (folder / 'product.patch').write_bytes(subprocess.check_output(['git', 'diff', '27785b3', '--',
        'human_eye_plugin/blender_host.py', 'human_eye_plugin/arm_twist_source.py'], cwd=ROOT))
    (folder / 'old_arm_twist_source.py.txt').write_bytes(subprocess.check_output(['git', 'show',
        'c5116e30024ed12825aea6119c0f5172e6b9b46d:human_eye_plugin/arm_twist_source.py'], cwd=ROOT))
    names = ['verification.arch_expert_entry_opt_001.test_entry_opt',
             'verification.arch_expert_entry_001.test_entry']
    names += ['verification.m6_arm_source_001.test_arm_source.ArmSourceTests.' + name for name in SOURCE_TESTS]
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in names)
    def cases(value):
        for item in value:
            if isinstance(item, unittest.TestSuite):
                yield from cases(item)
            else:
                yield item.id()
    methods = list(cases(suite))
    if len(methods) != 27 or len(set(methods)) != 27:
        raise AssertionError(('Expected exactly 7 new + 14 entry + 6 source methods', methods))
    (folder / 'methods.json').write_text(json.dumps(methods, indent=2) + '\n', encoding='utf8')
    stream = io.StringIO()
    assert sys.getprofile() is None, 'CPU group must start without profiling'
    started = time.perf_counter_ns()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    duration = (time.perf_counter_ns() - started) / 1e6
    (folder / 'unittest.log').write_text(stream.getvalue(), encoding='utf8')
    after = runtime_identity()
    (folder / 'identity_after.json').write_text(json.dumps(after, indent=2) + '\n', encoding='utf8')
    unchanged = identity == after and all(hashlib.sha256((ROOT / row['path']).read_bytes()).hexdigest() == row['sha256']
        for row in identity['source_files'])
    observations = importlib.import_module('verification.arch_expert_entry_opt_001.test_entry_opt').OBSERVATIONS
    record = dict(passed=result.wasSuccessful() and unchanged, tests=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        duration_ms=duration, source_sha256=identity['source_sha256'], source_members=len(identity['source_files']),
        source_unchanged=unchanged, methods=methods, observations=observations,
        failed_methods=[str(case) for case, _ in result.failures + result.errors],
        actual_blender=False, sys_profile_enabled=False, historical_matrix_replayed=False)
    (folder / 'RESULTS.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in record.items() if key not in ('methods', 'observations')}))
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
