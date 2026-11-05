"""RB-B frozen protocol. Launch with Python and --blender PATH."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
SIDES = (100, 300)
STEPS = ("vertices", "modifier", "transform", "unchanged", "appearance", "units", "topology", "mixed")
VARIANTS = ("baseline", "candidate")
WARMUPS = 5
SAMPLES = 31
PROCESSES = 3
THREAD_ENV = dict.fromkeys(
    ("BLIS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
     "VECLIB_MAXIMUM_THREADS"), "1"
)


def readonly(array):
    return np.asarray(memoryview(array).toreadonly())


class DirectBuffers:
    """Reusable staging and owned output arrays for the temporary-mesh baseline."""

    def __init__(self, mesh):
        shape = (len(mesh.vertices), 3)
        self.raw = np.empty(shape, dtype=np.float32)
        self.local = np.empty(shape, dtype=np.float64)
        self.world = np.empty_like(self.local)
        self.matrix = np.empty((4, 4), dtype=np.float64)
        self.linear = self.matrix[:3, :3].T
        self.translation = self.matrix[:3, 3]
        mesh.calc_loop_triangles()
        faces = mesh.loop_triangles
        triangles = np.empty((len(faces), 3), dtype=np.int32)
        polygons = np.empty(len(faces), dtype=np.int32)
        faces.foreach_get("vertices", triangles.ravel())
        faces.foreach_get("polygon_index", polygons)
        self.triangle_polygons = readonly(polygons)
        self.view = ResidentMesh(
            readonly(self.local), readonly(self.world), readonly(triangles), readonly(self.matrix), None
        )

    def read_appearance(self, evaluated, mesh):
        slots = tuple(
            (slot.name, tuple(material.diffuse_color)) if (material := slot.material) else None
            for slot in evaluated.material_slots
        )
        polygon_materials = np.empty(len(mesh.polygons), dtype=np.int32)
        mesh.polygons.foreach_get("material_index", polygon_materials)
        appearance = BlenderAppearance(
            tuple(evaluated.color), slots, readonly(polygon_materials), self.triangle_polygons
        )
        self.view = ResidentMesh(
            self.view.local_m, self.view.world_m, self.view.triangles,
            self.view.world_from_local, appearance,
        )


class DirectBaseline:
    """Read each needed evaluated geometry state through Blender's to_mesh()."""

    def __init__(self):
        self.entries = {}

    def capture(self, key, obj, graph, scale, changes=0):
        entry = self.entries.get(key)
        rebuild = entry is None or changes & MeshChange.TOPOLOGY
        if not rebuild and not changes:
            return entry.view
        vertices = rebuild or changes & MeshChange.VERTICES
        appearance = rebuild or changes & MeshChange.APPEARANCE
        read_mesh = vertices or appearance
        evaluated = obj.evaluated_get(graph)
        if read_mesh:
            mesh = evaluated.to_mesh()
            try:
                if rebuild:
                    entry = DirectBuffers(mesh)
                if vertices:
                    mesh.vertices.foreach_get("co", entry.raw.ravel())
                if appearance:
                    entry.read_appearance(evaluated, mesh)
            finally:
                evaluated.to_mesh_clear()
        local = vertices or changes & MeshChange.UNITS
        transform = rebuild or changes & (MeshChange.TRANSFORM | MeshChange.UNITS)
        if local:
            np.multiply(entry.raw, scale, dtype=np.float64, out=entry.local)
        if transform:
            entry.matrix[:] = evaluated.matrix_world
            entry.translation[:] *= scale
        if local or transform:
            np.matmul(entry.local, entry.linear, out=entry.world)
            entry.world += entry.translation
        if rebuild:
            self.entries[key] = entry
        return entry.view


def grid_input(side, offset, flipped=False):
    axis = np.linspace(-0.8, 0.8, side)
    x, y = np.meshgrid(axis, axis)
    z = 0.07 * np.sin(3.4 * x + offset) * np.cos(3.1 * y - offset)
    vertices = np.column_stack((x.ravel(), y.ravel(), z.ravel()))
    cells = np.arange(side * side).reshape(side, side)[:-1, :-1].ravel()
    triangles = np.empty((2 * len(cells), 3), dtype=np.int32)
    if flipped:
        triangles[0::2] = np.column_stack((cells, cells + 1, cells + side))
        triangles[1::2] = np.column_stack((cells + 1, cells + side + 1, cells + side))
    else:
        triangles[0::2] = np.column_stack((cells, cells + 1, cells + side + 1))
        triangles[1::2] = np.column_stack((cells, cells + side + 1, cells + side))
    return vertices, triangles


def make_mesh(name, vertices, triangles, materials):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, (), triangles)
    for material in materials:
        mesh.materials.append(material)
    mesh.update()
    return mesh


@dataclass(slots=True)
class GridObject:
    obj: object
    meshes: tuple
    grown_mesh: object
    coordinates: tuple
    coordinate_uploads: tuple
    polygon_uploads: tuple
    grown_polygon_uploads: tuple
    transforms: tuple
    colors: tuple
    materials: tuple
    diffuse_colors: tuple
    modifier: object


class Fixture:
    """Two actual Blender objects with two states per input and alternate diagonals."""

    def __init__(self, side, rng):
        self.scene = bpy.context.scene
        self.scene.unit_settings.system = "METRIC"
        self.scales = (0.23, 2.7)
        self.strengths = (-0.034, 0.087)
        self.objects = tuple(self.make_object(side, i, rng) for i in range(2))

    def make_object(self, side, i, rng):
        name = f"grid_{i}"
        offset = rng.uniform(-1, 1)
        raw, faces = grid_input(side, offset)
        _, flipped = grid_input(side, offset, flipped=True)
        grown, grown_faces = grid_input(side + 1, offset)
        lifted = raw.copy()
        lifted[:, 0] += 0.01
        lifted[:, 1] -= 0.007
        lifted[:, 2] += 0.025 + 0.014 * np.sin(4.2 * raw[:, 0])
        materials = tuple(bpy.data.materials.new(f"{name}_mat{j}") for j in range(2))
        meshes = (
            make_mesh(f"{name}_forward", raw, faces, materials),
            make_mesh(f"{name}_flipped", raw, flipped, materials),
        )
        grown_mesh = make_mesh(f"{name}_grown", grown, grown_faces, materials)
        obj = bpy.data.objects.new(name, meshes[0])
        self.scene.collection.objects.link(obj)
        modifier = None
        if i == 0:
            modifier = obj.modifiers.new("z displacement", "DISPLACE")
            modifier.direction = "Z"
            modifier.mid_level = 0.0
        transforms = tuple(
            (tuple(rng.uniform(-0.6, 0.6, 3) + [0.8 * i, 0.1, 0.2]),
             tuple(rng.uniform(-0.9, 0.9, 3)),
             (-0.72 if i else 0.89, 1.02 + 0.15 * phase, 0.93 + 0.3 * i))
            for phase in range(2)
        )
        colors = tuple(tuple(rng.uniform(0.1, 0.9, 4)) for _ in range(2))
        diffuse = tuple(tuple(rng.uniform(0.1, 0.9, 4)) for _ in range(2))
        polygon_indices = np.arange(len(faces), dtype=np.int32) % 2
        grown_indices = np.arange(len(grown_faces), dtype=np.int32) % 2
        return GridObject(
            obj, meshes, grown_mesh, (raw, lifted), (raw.astype(np.float32).ravel(), lifted.astype(np.float32).ravel()),
            (polygon_indices, 1 - polygon_indices), (grown_indices, 1 - grown_indices),
            transforms, colors, materials, diffuse, modifier,
        )

    @staticmethod
    def write_vertices(mesh, item, phase):
        mesh.vertices.foreach_set("co", item.coordinate_uploads[phase])
        mesh.update()

    @staticmethod
    def write_transform(item, phase):
        location, rotation, scale = item.transforms[phase]
        item.obj.location = location
        item.obj.rotation_euler = rotation
        item.obj.scale = scale

    @staticmethod
    def write_material_indices(mesh, indices):
        mesh.polygons.foreach_set("material_index", indices)
        mesh.update()

    def write_appearance(self, item, phase):
        item.obj.color = item.colors[phase]
        for j, material in enumerate(item.materials):
            material.diffuse_color = item.diffuse_colors[(phase + j) % 2]
        self.write_material_indices(item.obj.data, item.polygon_uploads[phase])

    def prepare(self, bridge, phase):
        prev = 1 - phase
        self.scene.unit_settings.scale_length = self.scales[prev]
        for item in self.objects:
            item.obj.data = item.meshes[prev]
            self.write_vertices(item.obj.data, item, prev)
            self.write_transform(item, prev)
            self.write_appearance(item, prev)
            if item.modifier is not None:
                item.modifier.strength = self.strengths[prev]
        self.capture(bridge, (0, 0))

    def apply(self, step, phase):
        prev = 1 - phase
        if step == "vertices":
            for item in self.objects:
                self.write_vertices(item.obj.data, item, phase)
            return (MeshChange.VERTICES,) * 2
        if step == "modifier":
            self.objects[0].modifier.strength = self.strengths[phase]
            return (MeshChange.VERTICES, MeshChange.NONE)
        if step == "transform":
            for item in self.objects:
                self.write_transform(item, phase)
            return (MeshChange.TRANSFORM,) * 2
        if step == "unchanged":
            return (MeshChange.NONE,) * 2
        if step == "appearance":
            for item in self.objects:
                self.write_appearance(item, phase)
            return (MeshChange.APPEARANCE,) * 2
        if step == "units":
            self.scene.unit_settings.scale_length = self.scales[phase]
            return (MeshChange.UNITS,) * 2
        if step == "topology":
            for item in self.objects:
                mesh = item.meshes[phase]
                self.write_vertices(mesh, item, phase)
                self.write_material_indices(mesh, item.polygon_uploads[phase])
                item.obj.data = mesh
            return (MeshChange.TOPOLOGY,) * 2
        if step == "mixed":
            for item in self.objects:
                self.write_vertices(item.obj.data, item, prev)
                self.write_transform(item, prev)
                self.write_appearance(item, prev)
            return (MeshChange.VERTICES | MeshChange.TRANSFORM | MeshChange.APPEARANCE,) * 2
        raise ValueError(step)

    def capture(self, bridge, flags):
        graph = bpy.context.evaluated_depsgraph_get()
        scale = self.scene.unit_settings.scale_length
        return tuple(
            bridge.capture(i, item.obj, graph, scale, changes)
            for i, (item, changes) in enumerate(zip(self.objects, flags))
        )

    def analytic_errors(self, views, step, phase):
        """Unquantized grid + analytic displacement and Euler XYZ transform."""
        prev = 1 - phase
        vertices_phase = prev if step == "mixed" else phase
        mod_phase = prev if step == "vertices" else phase
        transform_phase = prev if step in ("vertices", "modifier", "mixed") else phase
        unit_phase = phase if step in ("units", "topology", "mixed") else prev
        scale_length = self.scales[unit_phase]
        maxima = {"local_m": 0.0, "world_m": 0.0, "world_from_local": 0.0}
        for item, view in zip(self.objects, views):
            raw = item.coordinates[vertices_phase].copy()
            if item.modifier is not None:
                raw[:, 2] += self.strengths[mod_phase]
            local = raw * scale_length
            location, angles, scaling = item.transforms[transform_phase]
            cx, cy, cz = np.cos(angles)
            sx, sy, sz = np.sin(angles)
            rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
            ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
            rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
            matrix = np.eye(4)
            matrix[:3, :3] = rz @ ry @ rx @ np.diag(scaling)
            matrix[:3, 3] = np.array(location) * scale_length
            world = local @ matrix[:3, :3].T + matrix[:3, 3]
            for key, expected in (("local_m", local), ("world_m", world), ("world_from_local", matrix)):
                maxima[key] = max(maxima[key], float(np.max(np.abs(getattr(view, key) - expected))))
        return maxima


def verify(fixture):
    results = {}
    for label, factory in zip(VARIANTS, (DirectBaseline, BlenderResidentBridge)):
        native_errors = {}
        analytic_errors = {}
        for phase in (0, 1):
            bridge = factory()
            fixture.prepare(bridge, phase)
            for step in STEPS:
                views = fixture.capture(bridge, fixture.apply(step, phase))
                graph = bpy.context.evaluated_depsgraph_get()
                scale = fixture.scene.unit_settings.scale_length
                for item, view in zip(fixture.objects, views):
                    oracle = native_oracle(item.obj, graph, scale)
                    for field, error in assert_matches_oracle(view, oracle).items():
                        native_errors[field] = max(native_errors.get(field, 0.0), error)
                for field, error in fixture.analytic_errors(views, step, phase).items():
                    analytic_errors[field] = max(analytic_errors.get(field, 0.0), error)
        results[label] = {"native_max_abs": native_errors, "unquantized_max_abs": analytic_errors}
    return results


def measure(fixture, worker):
    results = {label: {"warmups": [], "samples": []} for label in VARIANTS}
    for trial in range(WARMUPS + SAMPLES):
        phase = (trial // 2) % 2
        order = VARIANTS if (trial + worker) % 2 == 0 else VARIANTS[::-1]
        for label in order:
            bridge = DirectBaseline() if label == "baseline" else BlenderResidentBridge()
            fixture.prepare(bridge, phase)
            timings = {}
            for step in STEPS:
                flags = fixture.apply(step, phase)
                started = perf_counter_ns()
                fixture.capture(bridge, flags)
                timings[step] = perf_counter_ns() - started
            key = "warmups" if trial < WARMUPS else "samples"
            results[label][key].append({
                "trial": trial, "phase": phase, "ran_first": order[0] == label,
                "step_ns": timings, "sequence_ns": sum(timings.values()),
            })
    return results


def measure_resize(fixture, worker):
    results = {label: [] for label in VARIANTS}
    flags = (MeshChange.TOPOLOGY,) * 2
    for trial in range(6):
        phase = (trial // 2) % 2
        order = VARIANTS if (trial + worker) % 2 == 0 else VARIANTS[::-1]
        for label in order:
            bridge = DirectBaseline() if label == "baseline" else BlenderResidentBridge()
            fixture.prepare(bridge, phase)
            row = {}
            for name in ("grow", "shrink"):
                for item in fixture.objects:
                    if name == "grow":
                        mesh = item.grown_mesh
                        indices = item.grown_polygon_uploads[1 - phase]
                    else:
                        mesh = item.meshes[1 - phase]
                        indices = item.polygon_uploads[1 - phase]
                    fixture.write_material_indices(mesh, indices)
                    item.obj.data = mesh
                started = perf_counter_ns()
                fixture.capture(bridge, flags)
                row[name] = perf_counter_ns() - started
            if trial:
                results[label].append(row)
    return results


def copy_counts(side):
    """Observable transfer and output writes for the two objects in a step."""
    vertex_count = side * side
    face_count = 2 * (side - 1) ** 2
    # Counts of objects with coordinates, local, world, transform, appearance writes.
    flags_by_step = {
        "vertices": (2, 2, 2, 0, 0),
        "modifier": (1, 1, 1, 0, 0),
        "transform": (0, 0, 2, 2, 0),
        "unchanged": (0, 0, 0, 0, 0),
        "appearance": (0, 0, 0, 0, 2),
        "units": (0, 2, 2, 2, 0),
        "topology": (2, 2, 2, 2, 2),
        "mixed": (2, 2, 2, 2, 2),
    }
    counts = {}
    for step, (rna, local, world, matrix, appearance) in flags_by_step.items():
        topology = 2 if step == "topology" else 0
        triangle_indices = topology * face_count * 3 * 4
        triangle_polygons = topology * face_count * 4
        polygon_materials = appearance * face_count * 4
        counts[step] = {
            "both": {
                "rna_into_owned_coordinate_staging_float32_bytes": rna * vertex_count * 3 * 4,
                "conversion_input_float32_bytes": local * vertex_count * 3 * 4,
                "conversion_into_owned_local_float64_bytes": local * vertex_count * 3 * 8,
                "owned_world_float64_bytes_unique": world * vertex_count * 3 * 8,
                "owned_world_float64_bytes_matmul_plus_translation": world * vertex_count * 3 * 8 * 2,
                "owned_matrix_float64_bytes_unique": matrix * 4 * 4 * 8,
                "matrix_float64_translation_rewrite_bytes": matrix * 3 * 8,
                "rna_into_owned_triangle_indices_int32_bytes": triangle_indices,
                "rna_into_owned_polygon_material_int32_bytes": polygon_materials,
                "appearance_objects_with_color_and_two_slot_descriptors": appearance,
            },
            "baseline": {
                "rna_into_owned_triangle_polygon_int32_bytes": triangle_polygons,
                "generated_triangle_polygon_int32_bytes": 0,
                "to_mesh_calls": max(rna, appearance),
            },
            "candidate": {
                "rna_into_owned_triangle_polygon_int32_bytes": 0,
                "generated_triangle_polygon_int32_bytes": triangle_polygons,
                "to_mesh_calls": 0,
            },
        }
    return counts


def run_worker(args):
    global bpy, np, BlenderAppearance, BlenderResidentBridge, MeshChange, ResidentMesh
    global native_oracle, assert_matches_oracle
    import bpy
    import numpy as np

    sys.path.insert(0, str(ROOT))

    from human_eye_fast.blender_resident_bridge import BlenderAppearance, BlenderResidentBridge, MeshChange
    from human_eye_fast.resident_bridge import ResidentMesh
    from verification.test_blender_resident_bridge import assert_matches_oracle, native_oracle

    if any(os.environ.get(name) != value for name, value in THREAD_ENV.items()):
        raise RuntimeError("Set BLAS thread environment through the Python launcher.")
    rng = np.random.default_rng(args.seed)
    output = {
        "worker": args.worker,
        "pid": os.getpid(),
        "seed": args.seed,
        "blender": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode("ascii"),
        "blender_binary": bpy.app.binary_path,
        "numpy": np.__version__,
        "python": sys.version,
        "platform": platform.platform(),
        "cpu": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER"),
        "logical_cpu_count": os.cpu_count(),
        "thread_environment": {name: os.environ.get(name) for name in THREAD_ENV},
        "numpy_blas": getattr(np.__config__, "CONFIG", {}).get("Build Dependencies", {}).get("blas"),
        "meshes": {},
    }
    for side in SIDES:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        fixture = Fixture(side, rng)
        print(f"RB-B worker {args.worker}: verifying {side}x{side}", flush=True)
        verified = verify(fixture)
        print(f"RB-B worker {args.worker}: verified {side}x{side}: {verified}", flush=True)
        result = {
            "vertices_per_object": side ** 2,
            "triangles_per_object": 2 * (side - 1) ** 2,
            "objects": 2,
            "correctness": verified,
            "copy_bytes_per_step": copy_counts(side),
            "copy_bytes_per_resize": {
                "grow": copy_counts(side + 1)["topology"],
                "shrink": copy_counts(side)["topology"],
            },
        }
        if not args.verify_only:
            result["timings_ns"] = measure(fixture, args.worker)
            result["resize_timings_ns"] = measure_resize(fixture, args.worker)
        output["meshes"][str(side)] = result
        save_json(args.output, output)
    return 0


def percentile_95(values):
    ordered = sorted(values)
    rank = 0.95 * (len(ordered) - 1)
    index = int(rank)
    return ordered[index] + (rank - index) * (ordered[index + 1] - ordered[index])


def summarize(workers):
    output = {}
    for side in map(str, SIDES):
        records = [worker["meshes"][side] for worker in workers]
        samples = [record["timings_ns"] for record in records]
        medians = [
            {label: statistics.median(row["sequence_ns"] for row in sample[label]["samples"]) for label in VARIANTS}
            for sample in samples
        ]
        ratios = [row["candidate"] / row["baseline"] for row in medians]
        p95 = {
            label: percentile_95(
                row["sequence_ns"] for sample in samples for row in sample[label]["samples"]
            )
            for label in VARIANTS
        }
        p95_ratio = p95["candidate"] / p95["baseline"]
        output[side] = {
            "process_sequence_medians_ns": medians,
            "process_median_ratios": ratios,
            "pooled_sequence_p95_ns": p95,
            "pooled_p95_ratio": p95_ratio,
            "process_median_gate": 0.80,
            "pooled_p95_gate": 1.20,
            "passed": all(ratio <= 0.80 for ratio in ratios) and p95_ratio <= 1.20,
            "step_pooled_medians_ns": {
                step: {
                    label: statistics.median(
                        row["step_ns"][step] for sample in samples for row in sample[label]["samples"]
                    )
                    for label in VARIANTS
                }
                for step in STEPS
            },
            "resize_pooled_medians_ns": {
                name: {
                    label: statistics.median(
                        row[name] for record in records for row in record["resize_timings_ns"][label]
                    )
                    for label in VARIANTS
                }
                for name in ("grow", "shrink")
            },
        }
    return output


def save_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path)
    parser.add_argument("--seed", type=int, default=31871)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/rb_b/author.json")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--worker", type=int, choices=range(PROCESSES), help=argparse.SUPPRESS)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None)
    if args.worker is not None:
        return run_worker(args)
    if args.blender is None:
        parser.error("--blender is required")
    args.output = args.output.resolve()
    commands = []
    workers = []
    for worker in range(1 if args.verify_only else PROCESSES):
        path = args.output.with_name(f"{args.output.stem}.process-{worker}.json")
        command = [
            str(args.blender.resolve()), "--background", "--factory-startup", "--python-exit-code", "2",
            "--python", str(SCRIPT), "--", "--worker", str(worker), "--seed", str(args.seed),
            "--output", str(path),
        ]
        if args.verify_only:
            command.append("--verify-only")
        commands.append(command)
        subprocess.run(command, cwd=ROOT, env=os.environ | THREAD_ENV | {"PYTHONDONTWRITEBYTECODE": "1"}, check=True)
        workers.append(json.loads(path.read_text(encoding="utf-8")))
    summary = {} if args.verify_only else summarize(workers)
    save_json(args.output, {
        "seed": args.seed,
        "commands": commands,
        "warmups_per_variant_per_size": WARMUPS,
        "samples_per_variant_per_size": SAMPLES,
        "step_order": STEPS,
        "timing_boundary": "Each step starts after the Blender input writes and includes context.evaluated_depsgraph_get(), both captures and returned descriptors.",
        "p95": "Linear percentile over the pooled complete sequence times.",
        "copy_count_boundary": "Observable NumPy writes and temporary mesh calls; Blender internal copies and allocation sizes are unknown. Python metadata heap sizes are unmeasured.",
        "workers": workers,
        "summary": summary,
    })
    print(json.dumps({"output": str(args.output), "summary": summary}, indent=2), flush=True)
    # Blender treats a top-level SystemExit as a Python script failure, even with code zero.
    return int(any(not scale["passed"] for scale in summary.values()))


if __name__ == "__main__":
    status = main()
    if "--" not in sys.argv:
        raise SystemExit(status)
