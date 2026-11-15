"""Copy the exact fixed saved-state PNGs and bind shared numerical image inputs."""

from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "IMAGE_BINDING.json").exists():
        raise RuntimeError("image_inputs_already_prepared")
    previous = HERE.parent / "m6_degrid_004"
    binding = read(previous / "IMAGE_BINDING.json")
    directory = HERE / "private/consumer_cases/repair"
    images = directory / "images"
    images.mkdir(parents=True, exist_ok=False)
    rows = []
    for source in binding["images"]:
        path = Path(source["path"])
        if identity(path)["sha256"] != source["sha256"]:
            raise ValueError("fixed_PNG_identity_changed")
        destination = images / path.name
        shutil.copyfile(path, destination)
        rows.append(dict(source, path=str(destination)))
    task = read(previous / "private/consumer_cases/repair/task.json")
    task["images"] = [dict(row, path=Path(row["path"]).relative_to(directory).as_posix()) for row in rows]
    task["numerical_image_access"] = "Python provides read_image_pixels(role), image_roles and image_cameras. Read only the matched current/normal image pixels you need. Pixels are uint8 RGB in top-left image coordinates. Camera metadata includes world-to-image projection and camera matrix."
    task["analysis_requirements"] = "Inspect the matched images, identify the indentation and compute a sparse correction from the current data. When fitting a reference surface, exclude the suspected affected region from the actual support. Save fit target IDs, actual support IDs, rank, coverage and estimated amplitudes in a diagnostic NPZ using the documented fit audit schema. Submit the edit and inspect the actual saved-model preview within the fixed budgets."
    task["final_answer"] = "Return concise execution_status, decision_status and supporting observations, active region, actual operation/version and saved/readback references, observed target result and remaining issues. Preserve fitting diagnostics in the audit files."
    write(directory / "task.json", task)
    shutil.copyfile(HERE / "private/cases/repair/initial.npz", directory / "input.npz")
    shutil.copyfile(previous / "CAMERAS.json", HERE / "CAMERAS.json")
    provenance = [dict(label=label,
        receipt=identity(previous / "private/jobs" / label / "receipt.json"),
        run=identity(previous / "private/jobs" / label / "run.json")) for label in binding["render_jobs"]]
    write("IMAGE_BINDING.json", dict(images=rows, count=len(rows), PNG_bytes=sum(row["bytes"] for row in rows),
        same_camera_verified=all(rows[i]["camera"] == rows[i + 4]["camera"] for i in range(4)),
        original_004_binding=identity(previous / "IMAGE_BINDING.json"), reused_saved_geometry_PNGs=True,
        render_provenance=provenance,
        current_saved_blend=read("CASE_BINDING.json")["current_blend"], normal_saved_blend=read("CASE_BINDING.json")["normal_blend"],
        public_task=identity(directory / "task.json"), public_input=identity(directory / "input.npz"),
        actual_Blender_calls=0, actual_Pro_calls=0, wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu,
        hidden_geometry_in_public_packet=False))
    print("eight fixed PNGs copied; shared pixel/camera numerical access described", flush=True)


if __name__ == "__main__":
    main()
