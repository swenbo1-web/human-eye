"""Native Blender expert baseline. No HE planner, renderer or oracle imports.

This is an engineering preflight, not an unassisted-model experiment. The caller
supplies only scene objects and a public task; private expected data stay outside.
"""
import hashlib
import json
import math
from pathlib import Path
import time


def components(indices, endpoints):
    remaining=set(indices);adjacency={}
    for index in indices:
        for vertex in endpoints[index]:adjacency.setdefault(vertex,[]).append(index)
    groups=[]
    while remaining:
        pending=[min(remaining)];remaining.remove(pending[0]);group=[]
        while pending:
            index=pending.pop();group.append(index)
            for vertex in endpoints[index]:
                for other in adjacency.pop(vertex,[]):
                    if other in remaining:remaining.remove(other);pending.append(other)
        groups.append(sorted(group))
    return groups


def topology(obj):
    import bmesh
    mesh=obj.data;bm=bmesh.new()
    try:
        bm.from_mesh(mesh)
        for table in (bm.verts,bm.edges,bm.faces):table.ensure_lookup_table();table.index_update()
        if (len(bm.verts)!=len(mesh.vertices) or len(bm.edges)!=len(mesh.edges)
            or len(bm.faces)!=len(mesh.polygons)):raise ValueError('native_mapping_unavailable')
        endpoints=[sorted(edge.vertices) for edge in mesh.edges]
        if any(list(vertex.co)!=list(mesh.vertices[i].co) for i,vertex in enumerate(bm.verts)):
            raise ValueError('native_vertex_mapping')
        if any(sorted(v.index for v in edge.verts)!=endpoints[i] for i,edge in enumerate(bm.edges)):
            raise ValueError('native_edge_mapping')
        if any([v.index for v in face.verts]!=list(mesh.polygons[i].vertices) for i,face in enumerate(bm.faces)):
            raise ValueError('native_face_mapping')
        boundary=[e.index for e in bm.edges if e.is_boundary]
        loose=[e.index for e in bm.edges if not e.link_faces]
        isolated=[v.index for v in bm.verts if not v.link_edges]
        groups=components(boundary,endpoints)
        facts=dict(boundary_edges=[[endpoints[i] for i in group] for group in groups],
            loose_edges=[[endpoints[i] for i in group] for group in components(loose,endpoints)],
            isolated_vertices=[[v] for v in isolated])
        adjacent={e.index:[f.index for f in e.link_faces] for e in bm.edges if e.is_boundary}
        return facts,groups,endpoints,adjacent
    finally:bm.free()


def render_native(original, objects, frame, path, check):
    import bpy
    from mathutils import Vector
    check();scene=bpy.data.scenes.new('native_baseline_temporary')
    data=bpy.data.cameras.new('native_baseline_camera');camera=bpy.data.objects.new('native_baseline_camera',data)
    had_result=bpy.data.images.get('Render Result') is not None
    try:
        for obj in objects:scene.collection.objects.link(obj)
        scene.collection.objects.link(camera);scene.camera=camera
        camera.location=frame['location'];camera.rotation_euler=Vector([-v for v in frame['direction']]).to_track_quat('-Z','Y').to_euler()
        data.type='ORTHO';data.ortho_scale=frame['span'];data.clip_start=frame['clip_start'];data.clip_end=frame['clip_end']
        scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=scene.render.resolution_y=384
        scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG'
        scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.color_depth='8'
        scene.view_settings.view_transform='Standard'
        shading=scene.display.shading;shading.light='FLAT';shading.color_type='OBJECT'
        shading.show_shadows=False;shading.show_cavity=False;shading.show_specular_highlight=False
        scene.render.film_transparent=False
        # Rendering evaluates a temporary scene without necessarily updating the
        # original Object.matrix_world. Update its own view layer before reading
        # actual camera RNA; requested frame vectors are not capture evidence.
        scene.view_layers[0].update()
        bpy.ops.render.render(scene=scene.name)
        check();bpy.data.images['Render Result'].save_render(str(path),scene=scene);check()
        return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            resolution=[384,384],camera_matrix=[list(row) for row in camera.matrix_world],
            actual_ortho_scale=float(data.ortho_scale),**frame)
    finally:
        bpy.data.scenes.remove(scene);bpy.data.objects.remove(camera,do_unlink=True);bpy.data.cameras.remove(data)
        if not had_result and bpy.data.images.get('Render Result') is not None:bpy.data.images.remove(bpy.data.images['Render Result'])


def observe(scene, obj, task, output):
    import bpy
    from mathutils import Vector
    started=time.perf_counter_ns();deadline=started+30_000_000_000
    stages={};ray_calls=0
    def check():
        if time.perf_counter_ns()>=deadline:raise ValueError('native_deadline')
    check();mark=time.perf_counter_ns()
    objects=[o for o in scene.objects if o.type=='MESH']
    points={o.name:[o.matrix_world@v.co for v in o.data.vertices] for o in objects}
    all_points=[v for values in points.values() for v in values]
    stages['capture_ms']=(time.perf_counter_ns()-mark)/1e6;mark=time.perf_counter_ns()
    facts,groups,endpoints,adjacent=topology(obj)
    stages['topology_ms']=(time.perf_counter_ns()-mark)/1e6;mark=time.perf_counter_ns()
    result=dict(status='observed',facts=facts,damage='not_inferred',images=[],image_status='no_boundary',
        assurance='native_fact_preflight_not_HE_certificate_parity',candidates=[])
    if groups:
        anchor=Vector(task['anchor_world_bu'])
        def key(group):
            vertices={v for index in group for v in endpoints[index]};values=[points[obj.name][v] for v in vertices]
            center=Vector([(min(v[k] for v in values)+max(v[k] for v in values))/2 for k in range(3)])
            return ((center-anchor).length_squared,max((p-center).length for p in values),min(group))
        primary=min(groups,key=key);vertices={v for index in primary for v in endpoints[index]}
        local=[points[obj.name][v] for v in vertices]
        center=Vector([(min(v[k] for v in local)+max(v[k] for v in local))/2 for k in range(3)])
        normal=Vector((0.,0.,0.))
        for index in {f for edge in primary for f in adjacent[edge]}:
            face=obj.data.polygons[index];a,b,c=[points[obj.name][v] for v in list(face.vertices)[:3]]
            normal+=(b-a).cross(c-a)
        if normal.length<=1e-12:normal=Vector((0.,0.,1.))
        normal.normalize();directions=[]
        neighbours={v:[] for v in vertices}
        for edge in primary:
            a,b=endpoints[edge];neighbours[a].append(b);neighbours[b].append(a)
        if any(len(values)!=2 for values in neighbours.values()):raise ValueError('native_focus_requires_closed_loop')
        cycle=[min(vertices)];previous=None;current=cycle[0]
        while True:
            following=next(v for v in neighbours[current] if v!=previous)
            if following==cycle[0]:break
            if following in cycle:raise ValueError('native_focus_loop_mapping')
            cycle.append(following);previous,current=current,following
        area=Vector((0.,0.,0.))
        for i in range(len(cycle)):
            area+=(points[obj.name][cycle[i-1]]-center).cross(points[obj.name][cycle[i]]-center)/2
        for direction in (normal,-normal,Vector((0.,0.,1.)),Vector((0.,1.,0.))):
            if not any(direction.dot(old)>1-1e-10 for old in directions):directions.append(direction)
        depsgraph=bpy.context.evaluated_depsgraph_get()
        # Twelve source samples at most; native BVH internals are not counted as
        # a claimed number of triangle predicates.
        samples=[(edge,t) for edge in primary for t in (.25,.5,.75)]
        if len(samples)>12:samples=[samples[i*len(samples)//12] for i in range(12)]
        for direction in directions:
            check();rotation=(-direction).to_track_quat('-Z','Y')
            right=rotation@Vector((1.,0.,0.));up=rotation@Vector((0.,1.,0.))
            spans=[max((p-center).dot(a) for p in local)-min((p-center).dot(a) for p in local) for a in (right,up)]
            span=max(spans)*1.25
            if span<=0 or min(spans)/span*384<16 or abs(area.dot(direction))<=span*span*1e-10:continue
            score=0;depths=[(p-center).dot(direction) for p in all_points]
            margin=max(span,max(depths)-min(depths))/8;distance=max(depths)+margin
            def hit(point):
                nonlocal ray_calls
                check();ray_calls+=1
                if ray_calls>96:raise ValueError('native_ray_api_budget')
                answer=scene.ray_cast(depsgraph,point+direction*distance,-direction,distance=distance-min(depths)+2*margin)
                return (answer[4].name,answer[3]) if answer[0] else None
            for edge,t in samples:
                a,b=[points[obj.name][v] for v in endpoints[edge]];delta=b-a
                across=direction.cross(delta)
                if across.length<=1e-12:continue
                across.normalize();point=a*(1-t)+b*t;offset=3*span/384
                left,right_hit=hit(point+across*offset),hit(point-across*offset)
                good=lambda value:value is not None and value[0]==obj.name and value[1] in adjacent[edge]
                score+=int((left is None and good(right_hit)) or (right_hit is None and good(left)))
            result['candidates'].append(dict(direction=list(direction),center=list(center),span=span,
                right=list(right),up=list(up),location=list(center+direction*distance),
                clip_start=margin/4,clip_end=distance-min(depths)+margin,score=score))
        selected=max(result['candidates'],key=lambda frame:frame['score'],default=None)
        result['selected_boundary_edges']=[endpoints[i] for i in primary];result['ray_api_calls']=ray_calls
        result['image_status']='no_useful_native_view'
        stages['focus_ms']=(time.perf_counter_ns()-mark)/1e6;mark=time.perf_counter_ns()
        if selected is not None and selected['score']>=8 and task['include_images']:
            # Overview and detail share the independently chosen direction.
            overview=dict(selected);overview_center=Vector([(min(p[k] for p in all_points)+max(p[k] for p in all_points))/2 for k in range(3)])
            direction=Vector(selected['direction']);axes=[Vector(selected[k]) for k in ('right','up')]
            overview_span=2.5*max(abs((p-overview_center).dot(a)) for p in all_points for a in axes)
            depths=[(p-overview_center).dot(direction) for p in all_points];margin=max(overview_span,max(depths)-min(depths))/8
            distance=max(depths)+margin;overview.update(center=list(overview_center),span=overview_span,
                location=list(overview_center+direction*distance),clip_start=margin/4,clip_end=distance-min(depths)+margin)
            output=Path(output)
            result['images']=[render_native(scene,objects,frame,output/(kind+'.png'),check)
                              for kind,frame in (('overview',overview),('detail',selected))]
            result['image_status']='constructed_not_model_read'
        stages['render_and_png_ms']=(time.perf_counter_ns()-mark)/1e6
    check();result['stages']=stages;result['function_ms']=(time.perf_counter_ns()-started)/1e6
    result['ray_api_calls']=ray_calls
    return result
