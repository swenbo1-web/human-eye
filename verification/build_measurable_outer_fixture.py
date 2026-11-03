"""Author one preregistered static QA scene in a new headless Blender copy.

Never a product source-admission path. Evaluated vertices are produced by LBS,
not copied from the independently registered expected-current coordinates.
"""
import argparse,hashlib,json,sys
from pathlib import Path


def build(registration,expected_sha256,output):
    import bpy
    raw=Path(registration).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('fixture_registration_changed')
    r=json.loads(raw)
    if r['schema']!='measurable-outer-core-fixture-v1':raise ValueError('fixture_schema')
    output=Path(output)
    if not output.is_absolute() or output.resolve()!=output:raise ValueError('fixture_output_path')
    output.mkdir(exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=r['unit_scale_m']
    mesh=bpy.data.meshes.new('MeasuredOuterMesh');mesh.from_pydata(r['vertices'],[],r['triangles']);mesh.update();mesh.calc_loop_triangles()
    obj=bpy.data.objects.new(r['mesh_name'],mesh);scene.collection.objects.link(obj)
    arm=bpy.data.armatures.new('MeasuredOuterRig');rig=bpy.data.objects.new(r['rig_name'],arm);scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
    for row in r['bones']:
        if row['parent'] is not None:raise ValueError('fixture_only_root_bones')
        bone=arm.edit_bones.new(row['name']);bone.head=row['head'];bone.tail=row['tail'];bone.roll=row['roll']
    bpy.ops.object.mode_set(mode='OBJECT')
    for row in r['bones']:rig.pose.bones[row['name']].location=row['pose_location']
    groups=[obj.vertex_groups.new(name=name) for name in r['groups']]
    for index,bone in enumerate(r['weight_bones']):
        if bone is not None:groups[bone].add([index],1.,'REPLACE')
    modifier=obj.modifiers.new('Armature','ARMATURE');modifier.object=rig
    modifier.use_vertex_groups=True;modifier.use_bone_envelopes=False;modifier.use_deform_preserve_volume=False
    frame=r['frame'];scene.frame_set(frame['number'],subframe=frame['subframe']);bpy.context.view_layer.update()
    # QA authoring ends here. Subsequent product readers have no save/setter API.
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'fixture.blend'))
    (output/'AUTHORING.json').write_text(json.dumps(dict(case_id=r['case_id'],registration_sha256=expected_sha256,
        source='own procedural static LBS QA fixture',vertex_count=len(r['vertices']),triangle_count=len(r['triangles']),
        expected_vertices_were_not_written_as_evaluated_mesh=True,shared_GUI_used=False),indent=2),encoding='utf8')


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--registration',type=Path,required=True);p.add_argument('--registration-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv);build(a.registration,a.registration_sha256,a.output);return 0


if __name__=='__main__':raise SystemExit(main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None))
