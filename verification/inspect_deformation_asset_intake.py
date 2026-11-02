"""Offline GLB skin inventory, independent of Human Eye production readers.

Reports original file facts. It never cleans, decimates, bakes, saves Blender
assets, grants product support, or treats author examples as production data.
"""
import argparse,hashlib,json,math,struct
from pathlib import Path

MAX_FILE=8*1024*1024
MAX_JSON=1024*1024
COMPONENTS={5120:('b',1),5121:('B',1),5122:('h',2),5123:('H',2),5125:('I',4),5126:('f',4)}
ELEMENTS={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}


def require(value,reason):
    if not value:raise ValueError('asset_intake_'+reason)


def parse_glb(blob):
    require(type(blob) is bytes and 20<=len(blob)<=MAX_FILE,'size')
    magic,version,total=struct.unpack_from('<4sII',blob)
    require(magic==b'glTF' and version==2 and total==len(blob),'header')
    offset=12;chunks=[]
    while offset<len(blob):
        require(offset+8<=len(blob),'chunk_header')
        length,kind=struct.unpack_from('<II',blob,offset);offset+=8
        require(length%4==0 and offset+length<=len(blob),'chunk_bounds')
        chunks.append((kind,blob[offset:offset+length]));offset+=length
    require(chunks and chunks[0][0]==0x4e4f534a and len(chunks[0][1])<=MAX_JSON,'json_chunk')
    require(len(chunks)==2 and chunks[1][0]==0x004e4942,'embedded_binary_only')
    doc=json.loads(chunks[0][1].decode('utf8'),parse_constant=lambda s:(_ for _ in ()).throw(ValueError(s)))
    require(type(doc) is dict and doc.get('asset',{}).get('version')=='2.0','gltf_version')
    buffers=doc.get('buffers',[])
    require(type(buffers) is list and len(buffers)==1 and 'uri' not in buffers[0]
        and type(buffers[0].get('byteLength')) is int and 0<=len(chunks[1][1])-buffers[0]['byteLength']<=3,'buffer_binding')
    return doc,chunks[1][1][:buffers[0]['byteLength']]


def accessor_rows(doc,binary,index,*,maximum_rows=20000):
    require(type(index) is int and 0<=index<len(doc['accessors']),'accessor_index')
    a=doc['accessors'][index];count=a.get('count');kind=a.get('type');component=a.get('componentType')
    require(type(count) is int and 0<=count<=maximum_rows and kind in ELEMENTS and component in COMPONENTS,'accessor_shape')
    require('sparse' not in a and type(a.get('bufferView')) is int,'sparse_or_missing_view')
    vi=a['bufferView'];require(0<=vi<len(doc['bufferViews']),'view_index');view=doc['bufferViews'][vi]
    require(view.get('buffer')==0,'view_buffer');code,size=COMPONENTS[component];width=ELEMENTS[kind];element=size*width
    stride=view.get('byteStride',element);view_start=view.get('byteOffset',0);view_size=view['byteLength'];local=a.get('byteOffset',0)
    require(all(type(v) is int and v>=0 for v in (stride,view_start,view_size,local))
        and stride>=element and stride%size==0 and view_start+view_size<=len(binary),'view_bounds')
    require(local+(count-1)*stride+element<=view_size if count else local<=view_size,'accessor_bounds')
    rows=[list(struct.unpack_from('<'+code*width,binary,view_start+local+i*stride)) for i in range(count)]
    require(all(math.isfinite(v) for row in rows for v in row),'nonfinite_accessor')
    if a.get('normalized',False):
        require(component in (5120,5121,5122,5123),'normalization_type')
        denominator={5120:127,5121:255,5122:32767,5123:65535}[component]
        rows=[[max(-1.,v/denominator) if component in (5120,5122) else v/denominator for v in row] for row in rows]
    return rows


def inspect(blob):
    doc,binary=parse_glb(blob);meshes=[]
    for mi,mesh in enumerate(doc.get('meshes',[])):
        primitives=[]
        for pi,primitive in enumerate(mesh['primitives']):
            attributes=primitive.get('attributes',{});require('POSITION' in attributes,'position_attribute')
            position=doc['accessors'][attributes['POSITION']];count=position['count'];mode=primitive.get('mode',4)
            require(mode==4,'nontriangle_primitive')
            if 'indices' in primitive:
                indices=accessor_rows(doc,binary,primitive['indices']);require(all(len(v)==1 and type(v[0]) is int and 0<=v[0]<count for v in indices),'indices')
                index_count=len(indices)
            else:index_count=count
            require(index_count%3==0,'triangle_index_count')
            positive=[];sums=[];unweighted=[];joint_sets=[]
            weight_names=sorted(k for k in attributes if k.startswith('WEIGHTS_'))
            if weight_names:
                sets=[]
                for key in weight_names:
                    joint='JOINTS_'+key.split('_',1)[1];require(joint in attributes,'joint_weight_pair')
                    weights=accessor_rows(doc,binary,attributes[key]);joints=accessor_rows(doc,binary,attributes[joint])
                    require(len(weights)==len(joints)==count and all(len(row)==4 for row in weights+joints),'weight_shape')
                    require(all(v>=0 for row in weights for v in row),'negative_weights');sets.append((weights,joints))
                for i in range(count):
                    active=[(j,w) for weights,joints in sets for j,w in zip(joints[i],weights[i]) if w>0]
                    positive.append(len(active));sums.append(math.fsum(w for _,w in active));joint_sets.extend(j for j,_ in active)
                    if not active:unweighted.append(i)
            primitives.append(dict(primitive=pi,mode=mode,position_accessor=attributes['POSITION'],vertices=count,triangles=index_count//3,
                weight_sets=weight_names,max_positive_influences=max(positive,default=0),unweighted_vertices=unweighted,
                positive_weight_sum_min=min(sums,default=None),positive_weight_sum_max=max(sums,default=None),
                used_joint_indices=sorted(set(joint_sets)),morph_targets=len(primitive.get('targets',[]))))
        meshes.append(dict(mesh=mi,name=mesh.get('name'),primitives=primitives))
    skins=[dict(skin=i,name=s.get('name'),joints=len(s['joints']),joint_node_indices=s['joints'],skeleton=s.get('skeleton')) for i,s in enumerate(doc.get('skins',[]))]
    children={c:i for i,node in enumerate(doc.get('nodes',[])) for c in node.get('children',[])}
    nodes=[dict(node=i,name=n.get('name'),mesh=n.get('mesh'),skin=n.get('skin'),parent=children.get(i),children=n.get('children',[]),
        has_matrix='matrix' in n,translation=n.get('translation',[0,0,0]),rotation=n.get('rotation',[0,0,0,1]),scale=n.get('scale',[1,1,1])) for i,n in enumerate(doc.get('nodes',[]))]
    animations=[dict(animation=i,name=a.get('name'),samplers=len(a['samplers']),channels=len(a['channels']),
        target_nodes=sorted({c['target']['node'] for c in a['channels']}),target_paths=sorted({c['target']['path'] for c in a['channels']})) for i,a in enumerate(doc.get('animations',[]))]
    return dict(schema='external-glb-skin-intake-v1',bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),asset=doc['asset'],
        meshes=meshes,skins=skins,nodes=nodes,animations=animations,extensions_used=doc.get('extensionsUsed',[]),
        extensions_required=doc.get('extensionsRequired',[]),product_support_certified=False,cleanup_performed=False,
        scope='original embedded GLB facts; independent accessor inspection, not a production diagnosis or production-asset qualification')


def native_inventory(path,derived_snapshot=None):
    """Import the untouched GLB only into this disposable background process."""
    import bpy
    require(bpy.app.background and not bpy.data.filepath,'factory_background_only')
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    # These are factory defaults in a NEW process, never user's live objects.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    props=bpy.ops.import_scene.gltf.get_rna_type().properties
    require('merge_vertices' in props,'importer_merge_control')
    bpy.ops.import_scene.gltf(filepath=str(path),merge_vertices=False)
    objects=[]
    for obj in bpy.context.scene.objects:
        row=dict(name=obj.name,type=obj.type,parent=None if obj.parent is None else obj.parent.name,
            matrix_world=[list(v) for v in obj.matrix_world],animation_data=obj.animation_data is not None,
            active_action=None if obj.animation_data is None or obj.animation_data.action is None else obj.animation_data.action.name,
            nla_tracks=0 if obj.animation_data is None else len(obj.animation_data.nla_tracks),
            constraints=len(obj.constraints),drivers=0 if obj.animation_data is None else len(obj.animation_data.drivers),
            bone_custom_shape_users=[dict(rig=rig.name,bone=bone.name) for rig in bpy.context.scene.objects if rig.type=='ARMATURE'
                for bone in rig.pose.bones if bone.custom_shape==obj])
        if obj.type=='ARMATURE':
            row.update(bones=len(obj.data.bones),deform_bones=sum(b.use_deform for b in obj.data.bones),
                pose_position=obj.data.pose_position,bone_constraints=sum(len(b.constraints) for b in obj.pose.bones),
                translated_pose_bones=[b.name for b in obj.pose.bones if any(v!=0 for v in b.location)],
                scaled_pose_bones=[b.name for b in obj.pose.bones if any(v!=1 for v in b.scale)])
        if obj.type=='MESH':
            weights=[[[g.group,g.weight] for g in vertex.groups] for vertex in obj.data.vertices]
            row.update(vertices=len(obj.data.vertices),polygons=len(obj.data.polygons),
                triangles=sum(len(p.vertices)==3 for p in obj.data.polygons),nontriangles=sum(len(p.vertices)!=3 for p in obj.data.polygons),
                edges=len(obj.data.edges),groups=[g.name for g in obj.vertex_groups],max_positive_influences=max([sum(w>0 for _,w in row) for row in weights],default=0),
                unweighted_vertices=sum(not any(w>0 for _,w in row) for row in weights),
                shape_keys=0 if obj.data.shape_keys is None else len(obj.data.shape_keys.key_blocks),
                coordinates_sha256=hashlib.sha256(json.dumps([list(v.co) for v in obj.data.vertices],separators=(',',':')).encode()).hexdigest(),
                topology_sha256=hashlib.sha256(json.dumps([list(p.vertices) for p in obj.data.polygons],separators=(',',':')).encode()).hexdigest(),
                weights_sha256=hashlib.sha256(json.dumps(weights,separators=(',',':')).encode()).hexdigest(),
                modifiers=[dict(name=m.name,type=m.type,object=m.object.name if m.type=='ARMATURE' and m.object else None,
                    vertex_groups=m.use_vertex_groups if m.type=='ARMATURE' else None,
                    bone_envelopes=m.use_bone_envelopes if m.type=='ARMATURE' else None,
                    preserve_volume=m.use_deform_preserve_volume if m.type=='ARMATURE' else None) for m in obj.modifiers])
        objects.append(row)
    if derived_snapshot is not None:
        require(derived_snapshot.is_absolute() and derived_snapshot.resolve()==derived_snapshot
            and not derived_snapshot.exists() and derived_snapshot.suffix=='.blend','new_derived_snapshot')
        bpy.ops.wm.save_as_mainfile(filepath=str(derived_snapshot),check_existing=False)
    require(hashlib.sha256(path.read_bytes()).hexdigest()==before,'original_changed')
    return dict(schema='native-external-asset-intake-v1',input=str(path),input_sha256=before,blender_version=bpy.app.version_string,
        blender_build_hash=bpy.app.build_hash.decode(),background=True,shared_GUI=False,objects=objects,
        import_options=dict(merge_vertices=False),native_import_created_owned_scene=True,geometry_cleanup=False,
        original_modified=False,original_saved=False,blend_saved=derived_snapshot is not None,
        derived_snapshot=None if derived_snapshot is None else str(derived_snapshot),product_runtime_attempted=False,
        frame=bpy.context.scene.frame_current,unit_scale_m=bpy.context.scene.unit_settings.scale_length)


if __name__=='__main__':
    import sys
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--native',action='store_true');p.add_argument('--derived-snapshot',type=Path)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    require(args.input.stat().st_size<=MAX_FILE,'file_budget')
    require(args.native or args.derived_snapshot is None,'derived_requires_native')
    result=native_inventory(args.input,args.derived_snapshot) if args.native else inspect(args.input.read_bytes())
    with args.output.open('x',encoding='utf8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(input=str(args.input),native=args.native,output=str(args.output))))
