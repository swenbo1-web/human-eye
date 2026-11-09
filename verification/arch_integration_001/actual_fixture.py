"""Isolated extension of the accepted fixture; no production API is added."""
import importlib.util
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / 'verification/arch_resident_001/blender_fixture.py'
spec = importlib.util.spec_from_file_location('integration_fixture_base', path)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
original = base.control

def native_snapshot():
    # All fixture objects are independent meshes with no modifiers. Read RNA
    # directly, without the host, engine meshes, delta decoder or solver.
    rows = []
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        if obj.modifiers or obj.constraints or obj.parent:
            raise ValueError('oracle fixture must remain independent plain meshes')
        rows.append({'name': obj.name, 'vertices': [list(obj.matrix_world @ v.co) for v in obj.data.vertices],
                     'faces': [list(p.vertices) for p in obj.data.polygons],
                     'color': list(obj.color), 'location': list(obj.location)})
    return {'scene': bpy.context.scene.name, 'frame': bpy.context.scene.frame_current,
            'scale': bpy.context.scene.unit_settings.scale_length, 'meshes': rows,
            'basis': 'independent direct bpy RNA world coordinates; fixture has no modifiers/constraints/parent'}

def control(value):
    if value['op'] == 'native_snapshot':
        return native_snapshot()
    if value['op'] == 'save_copy':
        bpy.ops.wm.save_as_mainfile(filepath=value['path'], copy=True)
        return {'ok': True}
    return original(value)

base.control = control
if __name__ == '__main__':
    base.main()
