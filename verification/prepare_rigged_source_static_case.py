"""Author one NEW fixed-frame QA copy; never a production reader command."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def static_data(bpy):
    meshes=[dict(name=m.name_full,vertices=[list(v.co) for v in m.vertices],triangles=[list(p.vertices) for p in m.polygons],
        weights=[[[g.group,g.weight] for g in v.groups] for v in m.vertices]) for m in sorted(bpy.data.meshes,key=lambda v:v.name_full)]
    rigs=[dict(name=a.name_full,bones=[dict(name=b.name,parent=b.parent.name if b.parent else None,
        rest=[list(r) for r in b.matrix_local],deform=b.use_deform,envelope=b.use_envelope_multiply,
        inheritance=[b.use_inherit_rotation,b.inherit_scale,b.use_local_location]) for b in a.bones]) for a in sorted(bpy.data.armatures,key=lambda v:v.name_full)]
    actions=[]
    for action in sorted(bpy.data.actions,key=lambda v:v.name_full):
        layers=[]
        for layer in action.layers:
            strips=[]
            for strip in layer.strips:
                bags=[]
                for bag in strip.channelbags:
                    curves=[]
                    for curve in bag.fcurves:
                        curves.append(dict(path=curve.data_path,index=curve.array_index,extrapolation=curve.extrapolation,
                            keys=[dict(co=list(k.co),left=list(k.handle_left),right=list(k.handle_right),interpolation=k.interpolation,
                                easing=k.easing,handles=[k.handle_left_type,k.handle_right_type]) for k in curve.keyframe_points]))
                    bags.append(dict(slot=bag.slot_handle,curves=curves))
                strips.append(dict(type=strip.type,bags=bags))
            layers.append(dict(name=layer.name,strips=strips))
        actions.append(dict(name=action.name_full,slots=[dict(handle=s.handle,identifier=s.identifier) for s in action.slots],layers=layers))
    return dict(meshes=meshes,rigs=rigs,actions=actions)


def main(args):
    import bpy
    source=Path(bpy.data.filepath).resolve();output=args.output
    assert bpy.app.background and source.is_file() and output.is_absolute() and output.resolve()==output
    assert output.is_relative_to(ROOT/'verification/fixes') and output.suffix=='.blend' and not output.exists() and source!=output
    assert args.frame==25 and bpy.context.scene.frame_current==1 and bpy.context.scene.frame_subframe==0
    prior=hashlib.sha256(source.read_bytes()).hexdigest();before=static_data(bpy);output.parent.mkdir(exist_ok=False)
    # This test-author operation is intentionally outside the read-only probe.
    # No geometry, weights, curves, bone channels or parent data are assigned.
    bpy.context.scene.frame_set(args.frame,subframe=0.)
    assert static_data(bpy)==before
    bpy.ops.wm.save_as_mainfile(filepath=str(output),check_existing=True)
    assert static_data(bpy)==before and hashlib.sha256(source.read_bytes()).hexdigest()==prior
    result=dict(schema='authored-heldout-fixed-frame-v1',input=str(source),input_sha256=prior,output=str(output),
        output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),frame=dict(number=args.frame,subframe=0.),
        original_unchanged=True,static_assets_before_sha256=digest(before),static_assets_after_sha256=digest(static_data(bpy)),
        geometry_weights_rest_actions_unchanged=True,test_author_sets_frame_once=True,test_author_saves_new_file=True,
        product_frame_command=False,shared_GUI=False)
    with output.with_suffix('.author.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--frame',type=int,required=True)
    main(parser.parse_args(sys.argv[sys.argv.index('--')+1:]))
