"""Render actual saved geometry with frozen local cameras in a disposable scene."""

import argparse
import json
from pathlib import Path
import sys
import time
import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from blender_common import (array_hash, assert_loaded, canonical_hash, execution_metadata, file_identity,
    get_target, mesh_arrays, output_path, write_json)


def unit(vector):
    vector = np.asarray(vector, dtype=np.float64)
    magnitude = float(np.linalg.norm(vector))
    if magnitude <= 0 or not np.isfinite(magnitude):
        raise ValueError("invalid_render_camera_direction")
    return vector / magnitude


def default_spec(job, baseline):
    F = baseline["F_source_ids"].astype(np.int64)
    points = baseline["vertices"][F]
    target = (points.min(axis=0) + points.max(axis=0)) / 2
    normal = unit(np.mean(baseline["n0"][F], axis=0))
    axis = np.eye(3)[int(np.argmin(np.abs(normal)))]
    tangent = unit(np.cross(normal, axis))
    bitangent = unit(np.cross(normal, tangent))
    span = float(np.linalg.norm(np.ptp(points, axis=0))) * 1.35
    return dict(target_world=target.tolist(), span=span,
        view_directions=[unit(normal+.3*tangent+.15*bitangent).tolist(), unit(tangent+.22*normal).tolist(), unit(bitangent+.22*normal).tolist()],
        resolution=[640,640], context_rings=2, samples=12, source="fixed initial current packet, before all edits")


def local_display(current, baseline, context_rings):
    F = baseline["F_source_ids"].astype(np.int64)
    source_lookup = {int(value): index for index,value in enumerate(current["source_ids"])}
    selected = np.zeros(len(current["vertices"]), dtype=bool)
    selected[[source_lookup[int(value)] for value in F]] = True
    initial_faces = baseline["faces"].astype(np.int64)
    edges = np.unique(np.sort(np.concatenate((initial_faces[:,[0,1]], initial_faces[:,[1,2]], initial_faces[:,[2,0]])),axis=1),axis=0)
    for _ in range(context_rings):
        incident = edges[selected[edges].any(axis=1)]
        selected[incident.ravel()] = True
    faces = current["faces"]
    keep = selected[faces].all(axis=1)
    chosen = faces[keep]
    if not len(chosen):
        raise ValueError("render_context_has_no_complete_current_triangles")
    ids, inverse = np.unique(chosen, return_inverse=True)
    return current["vertices"][ids], inverse.reshape(-1,3), current["source_ids"][ids], np.flatnonzero(keep)


def material(style):
    result = bpy.data.materials.new("M6 geometry comparison clay")
    result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = tuple(style["base_color"])
    shader.inputs["Roughness"].default_value = .82
    return result


def add_area_light(name, location, target, energy, size):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    light = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(light)
    light.location = location.tolist()
    light.rotation_euler = Vector((target-location).tolist()).to_track_quat("-Z", "Y").to_euler()
    return light


def main():
    started,cpu = time.perf_counter(),time.process_time()
    parser=argparse.ArgumentParser()
    parser.add_argument("--job",required=True)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    job=json.loads(Path(args.job).read_bytes())
    assert_loaded(job)
    source_file=file_identity(job["current_blend"])
    target=get_target(job)
    current=mesh_arrays(target)
    with np.load(job["base_npz"],allow_pickle=False) as source:
        baseline={name:source[name] for name in source.files}
    spec=job.get("render_spec") or default_spec(job,baseline)
    if isinstance(spec,str):
        spec=json.loads(Path(spec).read_bytes())
    style=spec.get("display_style",dict(version="clay_v2",base_color=[.28,.32,.4,1.],
        key_energy_per_span_squared=16.,fill_energy_per_span_squared=4.,world_strength=.15))
    view_target=np.asarray(spec["target_world"],dtype=np.float64)
    span=float(spec["span"])
    if span<=0 or not np.isfinite(span):
        raise ValueError("render_span_must_be_positive")
    vertices,faces,source_ids,source_face_rows=local_display(current,baseline,int(spec.get("context_rings",2)))
    # A separate display scene uses the reopened object's actual world coordinates.
    # The loaded saved .blend is never saved after camera/material setup.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    mesh=bpy.data.meshes.new("M6 actual readback local triangles")
    mesh.from_pydata(vertices.tolist(),[],faces.tolist())
    mesh.update()
    display=bpy.data.objects.new("Actual saved local geometry",mesh)
    scene.collection.objects.link(display)
    mesh.materials.append(material(style))
    for polygon in mesh.polygons:
        polygon.use_smooth=True
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=int(spec.get("samples",12))
    scene.cycles.use_denoising=False
    scene.cycles.seed=1729
    scene.render.threads_mode="FIXED"
    scene.render.threads=1
    scene.render.resolution_x=int(spec.get("resolution",[640,640])[0])
    scene.render.resolution_y=int(spec.get("resolution",[640,640])[1])
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.film_transparent=False
    scene.view_settings.view_transform="Standard"
    world=bpy.data.worlds.new("M6 comparison world")
    world.use_nodes=True
    world.node_tree.nodes["Background"].inputs["Color"].default_value=(.8,.8,.8,1.)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value=float(style["world_strength"])
    scene.world=world
    camera_data=bpy.data.cameras.new("M6 fixed orthographic camera")
    camera_data.type="ORTHO"
    camera_data.ortho_scale=span
    camera_data.clip_start=span*1e-4
    camera_data.clip_end=span*30
    camera=bpy.data.objects.new("M6 fixed orthographic camera",camera_data)
    scene.collection.objects.link(camera)
    scene.camera=camera
    directory=output_path(job["output_dir"])
    directory.mkdir(parents=True,exist_ok=True)
    images=[]
    for index, direction in enumerate(spec["view_directions"]):
        normal=unit(direction)
        axis=np.eye(3)[int(np.argmin(np.abs(normal)))]
        right=unit(np.cross(normal,axis))
        up=unit(np.cross(right,normal))
        eye=view_target+normal*span*4
        camera.location=eye.tolist()
        camera.rotation_euler=Vector((-normal).tolist()).to_track_quat("-Z","Y").to_euler()
        # Energy follows world span² to give the same exposure at source-native scales.
        key=add_area_light("M6 key",view_target+normal*span*2+right*span*.8+up*span*.7,view_target,float(style["key_energy_per_span_squared"])*span**2,span*1.4)
        fill=add_area_light("M6 fill",view_target+normal*span-right*span*.8-up*span*.3,view_target,float(style["fill_energy_per_span_squared"])*span**2,span*1.8)
        path=output_path(directory/("view_"+str(index+1).zfill(2)+".png"),require_new=True)
        scene.render.filepath=str(path)
        view_started=time.perf_counter()
        bpy.ops.render.render(write_still=True)
        images.append(dict(view_index=index+1,image=file_identity(path),render_wall_s=time.perf_counter()-view_started,
            camera_eye_world=eye.tolist(),camera_target_world=view_target.tolist(),camera_quaternion=list(camera.rotation_euler.to_quaternion()),
            ortho_scale=span,resolution=[scene.render.resolution_x,scene.render.resolution_y]))
        bpy.data.objects.remove(key,do_unlink=True)
        bpy.data.objects.remove(fill,do_unlink=True)
    if file_identity(job["current_blend"])!=source_file:
        raise ValueError("render_changed_saved_blend")
    result=dict(status="rendered_actual_saved_geometry",input_blend=source_file,input_unchanged=True,render_spec=spec,
        render_spec_sha256=canonical_hash(spec),display_style=style,images=images,source_vertex_ids=source_ids.tolist(),source_triangle_rows=source_face_rows.tolist(),
        rendered_world_vertices_sha256=array_hash(vertices),rendered_faces_sha256=array_hash(faces),
        display="neutral clay on actual current loop triangles within initial F plus fixed context rings, smooth shading, no displaced proxy geometry",
        scene_changes_saved=False,execution=execution_metadata(__file__,started,cpu))
    write_json(job["receipt_path"],result)
    print(json.dumps(dict(status=result["status"],image_count=len(images),output_dir=str(directory))))


if __name__=="__main__":
    main()
