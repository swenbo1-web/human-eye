"""Test-only outside observer around the exact product reader module."""
import argparse,hashlib,importlib.util,json,os,sys
from pathlib import Path
import bpy
sys.dont_write_bytecode=True
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--profile',type=Path,required=True)
p.add_argument('--profile-sha256',required=True);p.add_argument('--module-sha256',required=True);args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
output=Path(os.environ['HUMAN_EYE_RIG_AUDIT_OUTPUT']).resolve()
assert output.is_relative_to((Path(__file__).resolve().parents[2]/'verification/fixes'))
def snapshot():
    mat=lambda value:[[float(x) for x in row] for row in value]
    data=[]
    for obj in sorted(bpy.context.scene.objects,key=lambda v:v.name):
        item=dict(name=obj.name,type=obj.type,matrix=mat(obj.matrix_world),location=list(obj.location),
            euler=list(obj.rotation_euler),quaternion=list(obj.rotation_quaternion),scale=list(obj.scale),
            selected=obj.select_get(),parent=obj.parent.name if obj.parent else None)
        if obj.type=='ARMATURE':
            item['rest']=[dict(name=b.name,parent=b.parent.name if b.parent else None,matrix=mat(b.matrix_local),head=list(b.head_local),tail=list(b.tail_local),
                inherit_rotation=b.use_inherit_rotation,inherit_scale=b.inherit_scale,local_location=b.use_local_location,connected=b.use_connect,
                bbone_segments=b.bbone_segments,selection=getattr(b,'select',None)) for b in obj.data.bones]
            item['pose']=[dict(name=b.name,location=list(b.location),rotation_mode=b.rotation_mode,euler=list(b.rotation_euler),
                quaternion=list(b.rotation_quaternion),axis_angle=list(b.rotation_axis_angle),scale=list(b.scale),basis=mat(b.matrix_basis),
                matrix=mat(b.matrix),head=list(b.head),tail=list(b.tail),constraints=[dict(name=c.name,type=c.type,influence=c.influence,mute=c.mute) for c in b.constraints]) for b in obj.pose.bones]
            item['pose_position']=obj.data.pose_position
        data.append(item)
    return dict(objects=data,frame=bpy.context.scene.frame_current,subframe=bpy.context.scene.frame_subframe,
        mode=bpy.context.mode,active=bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
        units=bpy.context.scene.unit_settings.scale_length,selection=sorted(v.name for v in bpy.context.selected_objects))
def save(name,value):
    with (output/name).open('x',encoding='utf8') as f:json.dump(value,f,sort_keys=True,allow_nan=False)
bpy.context.view_layer.update();before=snapshot();save('INDEPENDENT_RNA_BEFORE.json',before)
path=args.root/'human_eye_plugin/rig_pose_worker.py';blob=path.read_bytes();spec=importlib.util.spec_from_file_location('_audited_rig_product',path)
module=importlib.util.module_from_spec(spec);exec(compile(blob,str(path),'exec',dont_inherit=True),module.__dict__)
try:module.run(args)
finally:
    after=snapshot();save('INDEPENDENT_RNA_AFTER.json',after)
    save('INDEPENDENT_RNA_RESULT.json',dict(identical=before==after,exact_product_worker_sha256=hashlib.sha256(blob).hexdigest(),
        test_wrapper_used=True,shared_GUI=False))
