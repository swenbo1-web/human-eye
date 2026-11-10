"""Construct only the newly frozen T1 asset in an owned background Blender."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import bpy
from mathutils import Matrix

HERE = Path(__file__).resolve().parent
SPEC_SHA = "b54110358c37dc7be1f47a201ef14b12156923f53729a723874ab902645a4ce2"


def need(value, reason):
    if not value:
        raise ValueError("T1_generate_" + reason)


def write(path, value):
    with path.open("xb") as stream:
        stream.write((json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())


def prism(outline, z0, z1, caps):
    count = len(outline)
    vertices = [tuple(map(F, (x, y, z))) for z in (z0, z1) for x, y in outline]
    triangles = [(c, b, a) for a, b, c in caps] + [(a + count, b + count, c + count) for a, b, c in caps]
    for index in range(count):
        following = (index + 1) % count
        triangles.extend(((index, following, following + count), (index, following + count, index + count)))
    return vertices, triangles


def refine(vertices, triangles):
    vertices = list(vertices)
    midpoints = {}

    def midpoint(a, b):
        edge = tuple(sorted((a, b)))
        if edge not in midpoints:
            midpoints[edge] = len(vertices)
            vertices.append(tuple((vertices[a][axis] + vertices[b][axis]) / 2 for axis in range(3)))
        return midpoints[edge]

    result = []
    for a, b, c in triangles:
        ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
        result.extend(((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)))
    return vertices, result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = args.output.resolve()
    need(output.parent == HERE and output.is_dir(), "exclusive_workspace")
    asset = output / "scene.blend"
    need(not asset.exists(), "asset_already_exists")
    raw = (HERE / "SPEC.FROZEN.json").read_bytes()
    need(hashlib.sha256(raw).hexdigest() == SPEC_SHA, "spec_pin")
    spec = json.loads(raw)
    need(not any(name.startswith(("human_eye_plugin", "human_eye_module1_operators")) for name in sys.modules), "product_import")
    rng = random.Random(spec["seed"])
    names = list(spec["neutral_names_before_shuffle"])
    rng.shuffle(names)
    need(dict(zip(spec["roles_in_seed_order"], names)) == spec["names"], "seed_names")
    order = list(spec["roles_in_seed_order"])
    rng.shuffle(order)
    need(order == spec["creation_order"], "seed_creation_order")
    prompt_order = spec["roles_in_seed_order"][1:]
    rng.shuffle(prompt_order)
    need(prompt_order == spec["prompt_candidate_order"], "seed_prompt_order")
    started = time.perf_counter_ns()
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = spec["unit_scale_m"]
    scale = F(*spec["coordinate_scale_m"])
    rotation = spec["common_rigid_rotation_rows"]
    translation = spec["common_translation_assembly_units"]
    records = []
    for role in order:
        if role == "target":
            vertices, faces = prism(spec["target_outline_ccw"], *spec["target_z_bounds"], spec["target_cap_triangles_ccw"])
            origin = [F(0)] * 3
        else:
            box = spec["candidate_boxes"][role]
            lower, upper = box["lower"], box["upper"]
            outline = [(lower[0], lower[1]), (upper[0], lower[1]), (upper[0], upper[1]), (lower[0], upper[1])]
            vertices, faces = prism(outline, lower[2], upper[2], [(0, 1, 2), (0, 2, 3)])
            origin = [(F(lower[axis]) + F(upper[axis])) / 2 for axis in range(3)]
        vertices, faces = refine(vertices, faces)
        expected = spec["expected_mesh_counts"][role]
        need(len(vertices) == expected["vertices"] and len(faces) == expected["triangles"], "pre_registered_mesh_counts")
        name = spec["names"][role]
        mesh = bpy.data.meshes.new("Mesh_" + name)
        local = [tuple(float((vertex[axis] - origin[axis]) * scale) for axis in range(3)) for vertex in vertices]
        mesh.from_pydata(local, [], faces)
        mesh.update(calc_edges=True)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        matrix = [list(row) + [float((F(translation[index]) + sum(F(row[axis]) * origin[axis] for axis in range(3))) * scale)]
                  for index, row in enumerate(rotation)] + [[0, 0, 0, 1]]
        obj.matrix_world = Matrix(matrix)
        need([list(row) for row in obj.matrix_world] == matrix, "exact_rigid_matrix_readback")
        need([list(vertex.co) for vertex in mesh.vertices] == [list(vertex) for vertex in local], "exact_vertex_readback")
        need([list(poly.vertices) for poly in mesh.polygons] == [list(face) for face in faces], "triangle_readback")
        records.append({"name": name, "vertices": len(vertices), "triangles": len(faces), "matrix_world": matrix})
    need(len(bpy.context.scene.objects) == 4, "four_objects")
    bpy.ops.wm.save_as_mainfile(filepath=str(asset), check_existing=False)
    need(asset.is_file() and asset.stat().st_size <= spec["preparation_limits"]["asset_max_bytes"], "asset_bytes")
    write(output / "GENERATION.json", {"schema": "T1-asset-generation-v1", "spec_sha256": SPEC_SHA,
        "asset": str(asset), "asset_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
        "asset_bytes": asset.stat().st_size, "blender_version": bpy.app.version_string,
        "python_version": sys.version, "creation_order": [record["name"] for record in records],
        "objects": records, "elapsed_ns": time.perf_counter_ns() - started,
        "creation_only_save_calls": 1, "original_assets_opened": 0,
        "production_calls": 0, "model_calls": 0, "shared_GUI_access": False})


if __name__ == "__main__":
    main()
