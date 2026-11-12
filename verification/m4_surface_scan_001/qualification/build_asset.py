"""Build exactly the frozen base assembly in a private factory Blender."""
import bpy
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent

def main():
    started=time.perf_counter_ns()
    freeze=json.loads((HERE/'GEOMETRY_FREEZE.json').read_bytes())
    output=HERE/'assembly.blend'
    assert not output.exists()
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    bpy.context.scene.unit_settings.system='METRIC'
    bpy.context.scene.unit_settings.length_unit='METERS'
    bpy.context.scene.unit_settings.scale_length=1.
    for row in freeze['parts']:
        mesh=bpy.data.meshes.new(row['name'])
        mesh.from_pydata(row['vertices_m_before_Blender_binary32'],[],row['triangles'])
        mesh.update()
        obj=bpy.data.objects.new(row['name'],mesh)
        bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    assert len(bpy.context.scene.objects)==24
    bpy.ops.wm.save_as_mainfile(filepath=str(output),check_existing=False,compress=False)
    result={'asset_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'freeze_sha256':hashlib.sha256((HERE/'GEOMETRY_FREEZE.json').read_bytes()).hexdigest(),
            'objects':len(bpy.context.scene.objects),'vertices':sum(len(o.data.vertices) for o in bpy.context.scene.objects),
            'triangles':sum(len(o.data.polygons) for o in bpy.context.scene.objects),
            'elapsed_ns':time.perf_counter_ns()-started,'blender_version':bpy.app.version_string}
    with (HERE/'BUILD_RESULT.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result))

if __name__=='__main__':main()
