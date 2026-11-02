"""Test-only original/evaluated RNA observer; optional fixed weight-change actor."""
import argparse,hashlib,importlib.util,json,os,sys
from pathlib import Path
import bpy
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from verification.run_rig_evaluation_preflight import outside_observer
p=argparse.ArgumentParser()
for name in ('root','profile'):p.add_argument('--'+name,type=Path,required=True)
for name in ('profile-sha256','module-sha256','math-sha256'):p.add_argument('--'+name,required=True)
p.add_argument('--deadline-ns',type=int,required=True);args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
output=Path(os.environ['HUMAN_EYE_SKIN_AUDIT_OUTPUT']).resolve();assert output.is_relative_to(ROOT/'verification/fixes')
def save(name,value):
    with (output/name).open('x',encoding='utf8') as f:json.dump(value,f,sort_keys=True,allow_nan=False)
def snapshot():
    graph=bpy.context.evaluated_depsgraph_get();meshes=[]
    for obj in sorted(bpy.context.scene.objects,key=lambda v:v.name):
        if obj.type!='MESH':continue
        ev=obj.evaluated_get(graph);original=obj.data;result=ev.data
        def data(m):return dict(vertices=[list(v.co) for v in m.vertices],faces=[list(p.vertices) for p in m.polygons],edges=[list(e.vertices) for e in m.edges],
            marker_ids=[v.value for v in m.attributes['he_oracle_vertex_id'].data] if 'he_oracle_vertex_id' in m.attributes else None)
        modifiers=[]
        for m in obj.modifiers:
            values={}
            for prop in m.bl_rna.properties:
                if prop.identifier=='rna_type' or prop.is_readonly:continue
                item=getattr(m,prop.identifier)
                if prop.type=='POINTER':values[prop.identifier]=None if item is None else dict(name=item.name_full,instance=str(item.session_uid))
                elif prop.type in ('BOOLEAN','INT','FLOAT','STRING','ENUM'):values[prop.identifier]=item
            modifiers.append(dict(type=m.type,settings=values))
        meshes.append(dict(name=obj.name,instance=str(obj.session_uid),data_instance=str(obj.data.session_uid),original=data(original),evaluated=data(result),
            groups=[g.name for g in obj.vertex_groups],weights=[[[g.group,g.weight] for g in v.groups] for v in original.vertices],modifiers=modifiers,
            shape_keys=original.shape_keys is not None,object_evaluated=ev.is_evaluated,mesh_data_evaluated=result.is_evaluated))
    return dict(objects=outside_observer(bpy),meshes=meshes,main_mesh_count=len(bpy.data.meshes),main_armature_count=len(bpy.data.armatures),
        armature_bone_flags=[dict(name=obj.name,bones=[dict(name=b.name,use_deform=b.use_deform,use_envelope_multiply=b.use_envelope_multiply,
            envelope_distance=b.envelope_distance,head_radius=b.head_radius,tail_radius=b.tail_radius) for b in obj.data.bones])
            for obj in sorted(bpy.context.scene.objects,key=lambda v:v.name) if obj.type=='ARMATURE'])
before=snapshot();save('INDEPENDENT_BEFORE.json',before)
mutation=os.environ.get('HUMAN_EYE_SKIN_MUTATE_WEIGHTS')=='1';original_stdin=sys.stdin
if mutation:
    assert Path(bpy.data.filepath).resolve().is_relative_to(ROOT/'verification/fixes')
    class Buffer:
        reads=0
        def readline(self,*values):
            if self.reads==1:
                obj=bpy.context.scene.objects['Skin'];obj.vertex_groups['bone_000'].add([0],.25,'REPLACE');obj.vertex_groups['bone_001'].add([0],.75,'REPLACE')
                obj.update_tag();bpy.context.view_layer.update();save('TEST_ACTOR_CHANGE.json',dict(weights=[.25,.75],saved=False,product_setter=False))
            self.reads+=1;return original_stdin.buffer.readline(*values)
    class Input:
        buffer=Buffer()
    sys.stdin=Input()
path=args.root/'human_eye_plugin/skin_source_worker.py';blob=path.read_bytes();spec=importlib.util.spec_from_file_location('_audited_skin_worker',path)
module=importlib.util.module_from_spec(spec);exec(compile(blob,str(path),'exec',dont_inherit=True),module.__dict__)
try:module.run(args)
finally:
    sys.stdin=original_stdin;after=snapshot();save('INDEPENDENT_AFTER.json',after)
    save('INDEPENDENT_RESULT.json',dict(identical=before==after,test_wrapper_used=True,test_actor_mutates_weights=mutation,
        exact_product_worker_sha256=hashlib.sha256(blob).hexdigest(),shared_GUI=False))
