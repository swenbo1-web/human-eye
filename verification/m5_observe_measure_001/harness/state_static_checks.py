"""No-live import, original asset geometry and state cleanup mocks."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_state


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


native = load_module('_m5_state_pure_native', HERE / 'state_owned_native.py')


class Matrix:
    def __init__(self, values):
        self.values = [list(row) for row in values]

    def __iter__(self):
        return iter(self.values)

    def __matmul__(self, point):
        return [sum(self.values[i][j] * point[j] for j in range(3)) + self.values[i][3]
                for i in range(3)]


def fixture():
    geometry_path = Path('D:/he_m4_target_002/assets_01/main.GEOMETRY.json')
    geometry = json.loads(geometry_path.read_bytes())
    objects = []
    for source in geometry['objects']:
        data = SimpleNamespace(materials=[],
            vertices=[SimpleNamespace(co=list(point)) for point in source['vertices_local']],
            edges=[], polygons=[])
        obj = SimpleNamespace(name=source['name'], type='MESH', parent=None,
            matrix_world=Matrix(native.M5_IDENTITY), data=data,
            hide_render=False, hide_viewport=False, hide_get=lambda: False)
        objects.append(obj)
    scene = SimpleNamespace(unit_settings=SimpleNamespace(scale_length=1.), frame_current=1, frame_subframe=0.)
    bpy = SimpleNamespace(data=SimpleNamespace(objects=objects),
        context=SimpleNamespace(scene=scene, view_layer=SimpleNamespace(update=lambda: None)))
    return bpy, geometry_path


class FakeNative:
    def __init__(self, owner):
        self.owner = owner

    def m5_matrix_step(self, operation):
        self.owner.calls.append(operation)
        return dict(response=dict(result=dict(test_matrix_setters=1)))


class FakeSession:
    instances = []
    fail_stage = None
    root = None

    def __init__(self, binding, output, ledger, phase, label, helper_path):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.errors, self.calls = [], []
        self.native = FakeNative(self)
        self.closed = False
        self.__class__.instances.append(self)

    def start(self):
        self.calls.append('start')
        if self.fail_stage == 'start':
            raise ValueError('mock_start_failure')

    def business(self, messages, label):
        self.calls.append(label)
        if label == self.fail_stage:
            raise ValueError('mock_public_failure')
        if len(messages) != 1 or messages[0]['id'] != 'm5_' + label:
            raise ValueError('mock_unique_id')

    def close(self):
        self.calls.append('close')
        self.closed = True
        return dict(passed_transport_scope=not self.errors, errors=self.errors)


def main():
    out = HERE.parent / 'STATE_STATIC_CHECKS'
    out.mkdir(exist_ok=False)
    results = []

    def check(name, condition):
        results.append(dict(name=name, passed=bool(condition)))
        if not condition:
            raise ValueError(name)

    for path in (HERE / 'state_owned_native.py', HERE / 'run_state.py'):
        ast.parse(path.read_text())
    registered = run_state.requests()
    check('five registered state RPCs unique IDs', len(registered) == 5
          and len({message['id'] for _, message in registered}) == 5)
    check('only one explicit full response', [label for label, message in registered
          if message['params']['arguments'].get('response_detail') == 'full'] == ['initial_main_full'])
    check('missing request fixed Far11 only',
          registered[2][1]['params']['arguments']['query']['task_query']['objects']
          == [{'name': 'M4_Far_00'}, {'name': 'M4_Far_11'}])
    old_mathutils = sys.modules.get('mathutils')
    sys.modules['mathutils'] = SimpleNamespace(Matrix=Matrix)
    try:
        bpy, geometry_path = fixture()
        initial = native._scene_fingerprint(bpy)
        moved = native._apply_m5_matrix(bpy, 1)
        check('original asset293 points exact +X .25', moved['vertex_count'] == 293
              and moved['world_after'] == [[p[0]+.25, p[1], p[2]] for p in moved['world_before']])
        check('one fixed matrix setter and no product setter', moved['test_matrix_setters'] == 1
              and moved['product_setters'] == 0 and moved['source_asset_saved'] is False)
        restored = native._apply_m5_matrix(bpy, 2)
        check('all fourteen object terminal state restored', len(bpy.data.objects) == 14
              and restored['after_fingerprint'] == initial and native._scene_fingerprint(bpy) == initial)
        try:
            native._apply_m5_matrix(bpy, 2)
        except ValueError as error:
            check('wrong before matrix rejected with expected reason', str(error) == 'visual004_native_m5_matrix_before')
        else:
            raise ValueError('wrong matrix was accepted')
        check('wrong matrix leaves full scene untouched', native._scene_fingerprint(bpy) == initial)
        bpy, _ = fixture()
        other = next(obj for obj in bpy.data.objects if obj.name == 'M4_Near')
        bpy.context.view_layer.update = lambda: setattr(other, 'hide_render', True)
        try:
            native._apply_m5_matrix(bpy, 1)
        except ValueError as error:
            check('unexpected other-object mutation rejected', str(error) == 'visual004_native_m5_full_scene_matrix_readback')
        else:
            raise ValueError('other mutation was accepted')
    finally:
        if old_mathutils is None:
            del sys.modules['mathutils']
        else:
            sys.modules['mathutils'] = old_mathutils
    expected = ['start', 'initial_main_brief', 'initial_main_full', 'initial_missing_brief',
                'qa_m5_matrix_move', 'matrix_changed_main_brief', 'qa_m5_matrix_restore',
                'restored_main_brief', 'close']
    result = run_state.run('unused', out / 'success', 'unused', session_class=FakeSession)
    check('single-session fixed full state sequence', FakeSession.instances[-1].calls == expected
          and result['passed_transport_scope'] and result['state_control']['actual_fixture_matrix_setters'] == 2)
    FakeSession.fail_stage = 'matrix_changed_main_brief'
    result = run_state.run('unused', out / 'changed_failure', 'unused', session_class=FakeSession)
    failed = FakeSession.instances[-1]
    check('changed-state public failure still performs one restore and closes', failed.closed
          and failed.calls.count('qa_m5_matrix_restore') == 1 and not result['passed_transport_scope'])
    FakeSession.fail_stage = 'start'
    result = run_state.run('unused', out / 'start_failure', 'unused', session_class=FakeSession)
    check('startup error still reaches close without fixture setter', FakeSession.instances[-1].calls == ['start', 'close']
          and not result['passed_transport_scope'])
    FakeSession.fail_stage = None
    original_save = run_state.save
    run_state.save = lambda *args, **kwargs: (_ for _ in ()).throw(OSError('mock_state_publication_failure'))
    try:
        try:
            run_state.run('unused', out / 'publication_failure', 'unused', session_class=FakeSession)
        except OSError as error:
            check('control publication error still closes owned session', str(error) == 'mock_state_publication_failure'
                  and FakeSession.instances[-1].closed)
        else:
            raise ValueError('publication error was hidden')
    finally:
        run_state.save = original_save
    paths = [Path(__file__), HERE / 'state_owned_native.py', HERE / 'run_state.py',
             HERE / 'run_case.py', HERE.parent / 'STATE_REQUESTS.json', geometry_path]
    pins = [dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
            for path in paths]
    report = dict(schema='m5-state-static-checks-v1', passed=True, checks=results, input_pins=pins,
                  actual_Blender_starts=0, actual_MCP_starts=0, actual_rasters=0,
                  mock_geometry_scope='Original frozen14 objects3478 local points, original target293 points. Fake matrix arithmetic models exact binary translation; actual Blender readback remains required.')
    path = out / 'RESULT.json'
    path.write_text(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(dict(passed=True, checks=len(results), path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
