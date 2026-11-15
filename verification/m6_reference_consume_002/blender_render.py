"""Render the complete saved character in frozen front, side and oblique views."""

import argparse
import json
from pathlib import Path
import sys
import time
import bpy
import numpy as np
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from blender_common import assert_loaded, execution_metadata, file_identity, get_target, mesh_arrays, output_path, write_json, array_hash

DEFAULT_VIEWS = [
    dict(name="whole_front", location=[2.,0.,.5], target=[0.,0.,.5], ortho_scale=1.07, resolution=[480,800]),
    dict(name="forearm_front", location=[2.,.155,.565], target=[0.,.155,.565], ortho_scale=.285, resolution=[640,640]),
    dict(name="forearm_side", location=[0.,2.,.565], target=[0.,.155,.565], ortho_scale=.285, resolution=[640,640]),
    dict(name="forearm_45", location=[1.4142135623730951,1.5692135623730952,.565], target=[0.,.155,.565], ortho_scale=.285, resolution=[640,640]),
]


def projection(scene, camera, point):
    value = world_to_camera_view(scene, camera, Vector(point))
    return np.array([value.x*scene.render.resolution_x, (1-value.y)*scene.render.resolution_y], dtype=float)


def main():
    started, cpu = time.perf_counter(), time.process_time()
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    job = json.loads(Path(args.job).read_bytes())
    assert_loaded(job)
    blend_before = file_identity(job["current_blend"])
    source_before = file_identity(job["source_original"])
    target = get_target(job)
    arrays = mesh_arrays(target)
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            obj.hide_render = obj != target
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 1
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "SINGLE"
    scene.display.shading.single_color = (.65,.65,.65)
    scene.display.shading.background_type = "WORLD"
    scene.world.color = (.8,.8,.8)
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    camera_data = bpy.data.cameras.new("reference_refinement_frozen_camera")
    camera = bpy.data.objects.new("reference_refinement_frozen_camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "ORTHO"
    directory = output_path(job["output_dir"])
    directory.mkdir(parents=True, exist_ok=False)
    views = job.get("views", DEFAULT_VIEWS)
    rows = []
    for specification in views:
        camera.location = specification["location"]
        camera.rotation_euler = (Vector(specification["target"])-camera.location).to_track_quat("-Z", "Y").to_euler()
        camera_data.ortho_scale = specification["ortho_scale"]
        scene.render.resolution_x, scene.render.resolution_y = specification["resolution"]
        scene.render.resolution_percentage = 100
        scene.render.pixel_aspect_x = 1.
        scene.render.pixel_aspect_y = 1.
        bpy.context.view_layer.update()
        origin = projection(scene,camera,[0.,0.,0.])
        basis = np.column_stack([projection(scene,camera,point)-origin for point in np.eye(3)])
        destination = directory / (specification["name"] + ".png")
        scene.render.filepath = str(destination)
        render_started = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        rows.append(dict(specification=specification, image=file_identity(destination), render_wall_s=time.perf_counter()-render_started,
            camera_matrix_world=[list(row) for row in camera.matrix_world],
            world_to_image_affine_2_by_3=basis.tolist(), world_to_image_offset=origin.tolist(),
            pixel_convention="continuous top-left pixel-edge coordinates; x in[0,width],y in[0,height]",
            geometry="complete current target mesh, scene camera/material/shading changes never saved"))
    if file_identity(job["current_blend"]) != blend_before or file_identity(job["source_original"]) != source_before:
        raise ValueError("render_changed_saved_or_original_blend")
    write_json(job["receipt_path"], dict(status="rendered_actual_saved_full_character", current_blend=blend_before,
        source_original=source_before, views=rows, vertices_world_sha256=array_hash(arrays["vertices_world"]),
        native_coordinates_sha256=array_hash(arrays["vertices_local"]), actual_loop_triangles_sha256=array_hash(arrays["faces"]),
        geometry_scale=1., displacement_scale=1., scene_changes_saved=False, execution=execution_metadata(__file__,started,cpu)))
    print(json.dumps(dict(status="rendered_actual_saved_full_character", images=len(rows))), flush=True)


if __name__ == "__main__":
    main()
