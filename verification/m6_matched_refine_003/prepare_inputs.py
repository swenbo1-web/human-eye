"""Render the fixed normal target and current damage with identical cameras."""

from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from background import run_job


VIEWS = [
    dict(name="whole_front", location=[2., 0., .5], target=[0., 0., .5], ortho_scale=1.07, resolution=[480, 800]),
    dict(name="forearm_front", location=[2., .155, .565], target=[0., .155, .565], ortho_scale=.285, resolution=[640, 640]),
    dict(name="forearm_side", location=[0., 2., .565], target=[0., .155, .565], ortho_scale=.285, resolution=[640, 640]),
    dict(name="forearm_45", location=[1.4142135623730951, 1.5692135623730952, .565],
         target=[0., .155, .565], ortho_scale=.285, resolution=[640, 640]),
]


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "IMAGE_BINDING.json").exists():
        raise RuntimeError("image_inputs_already_prepared")
    case = HERE / "private/cases/matched"
    directory = HERE / "private/consumer_cases/matched"
    directory.mkdir(parents=True, exist_ok=False)
    images = directory / "images"
    images.mkdir(exist_ok=False)
    spec = read(case / "spec.json")
    inputs = [
        ("normal", HERE / "private/construction/normal.blend"),
        ("current", case / "before.blend"),
    ]
    rows, renders = [], []
    for role, blend in inputs:
        output = HERE / "private/input_renders" / role
        record = run_job("blender_render.py", {
            "current_blend": str(blend), "source_original": spec["source_original"],
            "object_name": spec["object_name"], "output_dir": str(output), "views": VIEWS,
        }, "input_" + role + "_render")
        renders.append(record)
        for view in record["receipt"]["views"]:
            name = role + "_" + view["specification"]["name"]
            destination = images / (name + ".png")
            shutil.copyfile(view["image"]["path"], destination)
            rows.append({
                "index": len(rows) + 1, "role": name,
                "path": str(destination), "bytes": identity(destination)["bytes"],
                "sha256": identity(destination)["sha256"], "mimeType": "image/png",
                "width": view["specification"]["resolution"][0],
                "height": view["specification"]["resolution"][1],
                "camera": {key: view[key] for key in ("specification", "camera_matrix_world",
                    "world_to_image_affine_2_by_3", "world_to_image_offset", "pixel_convention")},
            })
    for normal, current in zip(rows[:4], rows[4:]):
        if normal["camera"] != current["camera"]:
            raise ValueError("normal_and_current_camera_mismatch")
    task = {
        "task_id": "matched",
        "intent": "Repair the local indentation in the designated forearm region so that the current model matches the supplied normal reference PNGs.",
        "images": rows,
        "image_delivery": "The images tool returns all eight actual PNGs. Normal reference and current damage use identical pose, orthographic camera, scale, lighting and material. Geometry display scale is one.",
        "observed_region": "Image-right, model-positive-Y forearm. F is the broad task region. Choose an active correction and transition within I using the images and current geometry.",
        "domains": {"task_points": 410, "editable_points": 274,
                    "source_ID_contract": "Source IDs equal rows of the full mesh. F/I/protected arrays are in the current geometry packet."},
        "edit_budget": {"max_operation_displacement_m": spec["max_operation_displacement_m"],
                        "max_cumulative_displacement_m": spec["max_cumulative_displacement_m"]},
        "preservation": "Keep all protected native vertex coordinates, topology, UVs, materials, matrix and other objects. Use smooth transitions inside I and inspect saved-model technical quality.",
        "analysis_requirements": "Inspect the images, identify the local indentation, compute a justified sparse correction from current data, submit it, and independently read the actual saved model. You can inspect and correct within the fixed tool and displacement budgets.",
        "final_answer": "Return a concise decision, visual evidence, active-region reference, actual operation/version, saved model and independent readback, observed result and remaining issues. Detailed arrays and metrics remain in the audit files.",
        "scope": "This is a synthetic local restoration to a normal rendered target. Numerical variables expose current damaged geometry and its initial state. The target reference is supplied as PNG images.",
    }
    write((directory / "task.json").relative_to(HERE), task)
    shutil.copyfile(case / "initial.npz", directory / "input.npz")
    write("CAMERAS.json", {"views": VIEWS, "shared_by_normal_current_and_results": True,
                           "geometry_scale": 1., "displacement_scale": 1.})
    write("IMAGE_BINDING.json", {
        "images": rows, "count": len(rows), "PNG_bytes": sum(row["bytes"] for row in rows),
        "same_camera_verified": True, "render_jobs": [row["label"] for row in renders],
        "public_task": identity(directory / "task.json"), "public_input": identity(directory / "input.npz"),
        "wall_s": time.perf_counter() - started, "cpu_s": time.process_time() - cpu,
        "hidden_geometry_in_public_packet": False,
    })
    print("eight matched normal/current PNG inputs and damaged-only packet prepared", flush=True)


if __name__ == "__main__":
    main()
