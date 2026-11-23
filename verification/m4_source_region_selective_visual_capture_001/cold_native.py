"""Reuse the owned Blender launcher with a non-geometry pre-request guard."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
RETAINED = HERE.parent/'m4_global_local_qualification_001/harness/reused/owned_native.py'
METER = RETAINED.with_name('wire_meter.py')


def cheap_fingerprint(bpy):
    """Only load-time RNA identities, display flags, counts, and raw transforms."""
    scene, layer = bpy.context.scene, bpy.context.view_layer
    rows = []
    for obj in scene.objects:
        data = obj.data
        rows.append([obj.name_full, obj.type, int(obj.session_uid),
                     None if data is None else [data.name_full, int(data.session_uid)],
                     bool(obj.hide_render), bool(obj.hide_viewport), bool(obj.hide_get(view_layer=layer)),
                     tuple(tuple(float(c) for c in row) for row in obj.matrix_world),
                     [len(data.vertices), len(data.edges), len(data.polygons)] if obj.type == 'MESH' else None])
    state = [scene.name_full, int(scene.session_uid), int(scene.frame_current), float(scene.frame_subframe),
             scene.unit_settings.system, float(scene.unit_settings.scale_length), layer.name, rows]
    encoded = json.dumps(state, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def retained_scope():
    original = RETAINED.read_text(encoding='utf8')
    anchor = "Path(__file__).with_name('wire_meter.py')"
    if original.count(anchor) != 1:
        raise ValueError('retained_meter_location_changed')
    original = original.replace(anchor, 'Path('+repr(str(METER))+')')
    tree = ast.parse(original, filename=str(RETAINED))
    main = [stmt for stmt in tree.body if isinstance(stmt, ast.If)
            and ast.unparse(stmt.test) == "__name__ == '__main__'"]
    if len(main) != 1:
        raise ValueError('retained_worker_entry_changed')
    tree.body.remove(main[0])
    scope = {'__name__': '_m4_owned_cold_native', '__file__': str(Path(__file__).resolve())}
    exec(compile(tree, str(RETAINED), 'exec'), scope)
    scope['_scene_fingerprint'] = cheap_fingerprint
    return scope


retained = retained_scope()
NativeSession = retained['NativeSession']


if __name__ == '__main__':
    position = sys.argv.index('--')
    args = sys.argv[position+1:]
    if len(args) != 2 or args[0] != '--worker':
        raise ValueError('owned_worker_entry_required')
    path = Path(args[1]).resolve(strict=True)
    config = retained['load'](path)
    if 'qa_vertex_patch' in config or config['max_calls'] != 3 or path.parent.name != 'native':
        raise ValueError('read_only_two_calls_then_truth_required')
    begun = time.perf_counter_ns()
    retained['save'](path.parent/'COLD_POLICY.json', {
        'guard_scope': 'loaded scene RNA names/IDs/frame/unit/visibility/raw transforms and len-only original mesh counts',
        'geometry_array_reads_in_guards': 0, 'evaluated_depsgraph_or_to_mesh_in_guards': 0,
        'pid': __import__('os').getpid(), 'started_ns': begun,
    })
    retained['worker'](path)
