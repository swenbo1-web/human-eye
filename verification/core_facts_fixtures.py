"""Small static LBS islands for independently preregistered core-fact checks.

This is QA authoring, never production source admission. Run with a factory
headless Blender; only the explicitly provided new output directory is written.
"""
import argparse,copy,json,struct,sys
from pathlib import Path


def recipe(case):
    points=[];triangles=[];weights=[]
    def face(coords,kind='normal'):
        base=len(points);points.extend(coords);triangles.append([base,base+1,base+2])
        weights.extend([None]*3 if kind=='unknown' else [0,1 if kind=='stretch' else 0,0])
        if kind=='outer':weights[-1]=2
    counts={'outer_dominates_mixed18':(18,4,1),'omitted_extremum8':(8,4,0),
        'empty_core':(0,0,3),'all_unknown_core3':(3,3,2),
        'closed_boundary_contacts':(2,0,2),'mixed_analytic3':(3,1,1)}
    if case not in counts:raise ValueError('unregistered core fixture')
    n,unknown,outside=counts[case];edge=.03125
    for i in range(n):
        if case=='closed_boundary_contacts':
            face([[.25,0,0],[.5,.1,0],[.5,-.1,0]] if i==0 else [[.25,-.1,0],[.25,.1,0],[.5,0,0]])
            continue
        x=-.125+(i%5)*.0625;y=-.125+(i//5)*.0625
        kind='unknown' if (i<unknown if case!='mixed_analytic3' else i==2) else 'normal'
        if (case=='omitted_extremum8' and i==7) or (case=='mixed_analytic3' and i==1):kind='stretch'
        face([[x,y,0],[x+edge,y,0],[x,y+edge,0]],kind)
    for i in range(outside):
        x=1.125+i*.0625
        face([[x,0,0],[x+edge,0,0],[x,edge,0]],'outer' if case=='outer_dominates_mixed18' else 'normal')
    return dict(vertices=points,triangles=triangles,weight_bones=weights,core_faces=n)


def analytic_expectation(registration,case):
    """Read analytic truth from the frozen authoring contract, never a report.

    The recipe is a separate QA input construction. Its full geometry is not
    reconstructed from the production report's four detail rows.
    """
    records=[c for c in registration['cases'] if c['case']==case]
    if len(records)!=1:raise ValueError('registered_fixture_identity')
    record=records[0];data=recipe(case);count=record['core_faces']
    if type(count) is not int or count!=data['core_faces']:
        raise ValueError('registered_fixture_core_count')
    states=copy.deepcopy(record['expected_core_counts'])
    if (set(states)!={'measured','collapsed','unknown'} or
            any(type(v) is not int or v<0 for v in states.values()) or sum(states.values())!=count):
        raise ValueError('registered_fixture_states')
    metrics=('max_principal_stretch','min_principal_stretch','min_area_ratio','max_area_ratio')
    extrema=record.get('expected_core_extrema',dict.fromkeys(metrics,1.))
    if extrema is None:extrema=dict.fromkeys(metrics,None)
    if set(extrema)!=set(metrics):raise ValueError('registered_fixture_extrema')
    reasons=({record.get('expected_unknown_reason','unweighted_vertex_source'):states['unknown']}
             if states['unknown'] else {})
    facts=dict(core_status='empty' if count==0 else 'partial' if states['unknown'] else 'observed',
        core_triangle_count=count,core_states=states,core_unknown_reasons=reasons,core_extrema=copy.deepcopy(extrema))
    return dict(facts=facts,members=list(range(count)),recipe=data)


def verify_fixture_inputs(packet,registration,case):
    """Bind a labelled heldout to every frozen authoring vertex and weight.

    This uses the input recipe and known translations, not any production
    metric or membership output. Blender stores mesh coordinates as binary32.
    """
    expected=analytic_expectation(registration,case)['recipe']
    raw=packet['inputs'];mesh=raw['mesh'];current=packet['evaluated']
    if raw['frame']!={'number':1,'subframe':0.0} or raw['unit_scale_m']!=registration['scene_units_m']:
        raise ValueError('registered_fixture_frame_units')
    if mesh['name']!='Cylinder' or raw['rig']['name']!='Armature':raise ValueError('registered_fixture_roles')
    if mesh['triangles']!=expected['triangles'] or current['triangles']!=expected['triangles']:
        raise ValueError('registered_fixture_topology')
    f32=lambda value:struct.unpack('f',struct.pack('f',value))[0]
    points=[[f32(v) for v in point] for point in expected['vertices']]
    if mesh['vertices']!=points:raise ValueError('registered_fixture_original_coordinates')
    if mesh['groups']!=['CoreAnchor','LocalShift','OuterShift']:raise ValueError('registered_fixture_groups')
    weights=[[] if bone is None else [[bone,1.0]] for bone in expected['weight_bones']]
    if mesh['weights']!=weights:raise ValueError('registered_fixture_weights')
    deformed=[]
    for point,bone in zip(points,expected['weight_bones']):
        deformed.append([f32(v+(.03125 if bone==1 and axis==0 else 1. if bone==2 and axis==1 else 0.))
                         for axis,v in enumerate(point)])
    if current['vertices']!=deformed:raise ValueError('registered_fixture_evaluated_coordinates')
    identity=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
    if current['mesh_matrix_world']!=identity or current['rig_matrix_world']!=identity:
        raise ValueError('registered_fixture_world_matrices')


def build(case,directory):
    import bpy
    directory=Path(directory).resolve();directory.mkdir(exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
    data=recipe(case);mesh=bpy.data.meshes.new('CoreFactsMesh');mesh.from_pydata(data['vertices'],[],data['triangles']);mesh.update()
    obj=bpy.data.objects.new('Cylinder',mesh);scene.collection.objects.link(obj)
    arm=bpy.data.armatures.new('CoreFactsRig');rig=bpy.data.objects.new('Armature',arm);scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
    for name in ('CoreAnchor','LocalShift','OuterShift'):
        b=arm.edit_bones.new(name);b.head=(0,0,0);b.tail=(0,1,0);b.roll=0.
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.pose.bones['LocalShift'].location=(.03125,0,0);rig.pose.bones['OuterShift'].location=(0,1,0)
    groups=[obj.vertex_groups.new(name=name) for name in ('CoreAnchor','LocalShift','OuterShift')]
    for i,bone in enumerate(data['weight_bones']):
        if bone is not None:groups[bone].add([i],1.,'REPLACE')
    mod=obj.modifiers.new('Armature','ARMATURE');mod.object=rig;mod.use_vertex_groups=True;mod.use_bone_envelopes=False;mod.use_deform_preserve_volume=False
    scene.frame_set(1);bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(directory/'fixture.blend'))
    (directory/'RECIPE.json').write_text(json.dumps(dict(case=case,**data),indent=2),encoding='utf8')


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--registration',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv);registration=json.loads(args.registration.read_bytes());args.output.mkdir(exist_ok=False)
    for c in registration['cases']:build(c['case'],args.output/c['case'])
    return 0


if __name__=='__main__':raise SystemExit(main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None))
