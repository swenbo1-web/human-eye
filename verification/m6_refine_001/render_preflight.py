"""Preserve actual-scale v2 reference renders and all earlier render costs."""

import argparse
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from background import run_job
from common import identity, read, write


def render_spec(case_id):
    directory = HERE / "private/reference" / case_id
    spec = dict(read(directory / "render_spec.json"))
    spec["samples"] = 32
    spec["display_style"] = dict(version="clay_v2", base_color=[.28,.32,.4,1.],
        key_energy_per_span_squared=16., fill_energy_per_span_squared=4., world_strength=.15)
    path = directory / "render_spec_v2_16_4.json"
    if path.exists() and read(path) != spec:
        raise ValueError("frozen_render_v2_spec_changed")
    if not path.exists():
        write(path.relative_to(HERE), spec)
    return path, spec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    started, cpu = time.perf_counter(), time.process_time()
    cases = read("SOURCES.json")["cases"]
    jobs = []
    for case in cases:
        case_id = case["case_id"]
        directory = HERE / "private/reference" / case_id
        spec_path, spec = render_spec(case_id)
        if args.preview and case_id != "s02":
            continue
        states = ("after",) if args.preview else ("before", "after")
        for state in states:
            active_spec = dict(spec)
            suffix = "_v2_preview" if args.preview else "_v2"
            if args.preview:
                active_spec["view_directions"] = active_spec["view_directions"][:1]
            label = case_id + "_reference_" + state + "_render" + suffix
            jobs.append(run_job("blender_render.py", dict(case_id=case_id,
                object_name=case["object_name"], base_npz=str(HERE / "private/cases" / case_id / "initial.npz"),
                source_original=case["source_original"], current_blend=str(directory / (state + ".blend")),
                output_dir=str(directory / (state + "_views" + suffix)), render_spec=active_spec), label))
        print(case_id, "v2 preview" if args.preview else "v2 before/after complete", flush=True)
    output = "private/reference/render_v2_preview.json" if args.preview else "RENDER_PREFLIGHT.json"
    result = dict(display_version="clay_v2", status="rendered_actual_saved_geometry",
        renderer=identity(HERE / "blender_render.py"), source=identity(__file__),
        render_specs=[identity(HERE / "private/reference" / case["case_id"] / "render_spec_v2_16_4.json") for case in cases],
        camera_and_geometry_scale_unchanged=True, displacement_scale=1.,
        jobs=jobs, wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu,
        nested_blender_wall_s=sum(job["wall_s"] for job in jobs),
        earlier_render_costs_retained_in="REFERENCE_CONTROL.json",
        earlier_images_preserved=True, original_source_edits=0)
    if not args.preview:
        preview = read("private/reference/render_v2_preview.json")
        middle_preview = read("private/jobs/s02_reference_after_render_v2_preview_mid/run.json")
        control = read("REFERENCE_CONTROL.json")
        result["preview_costs"] = dict(wall_s=preview["wall_s"], nested_blender_wall_s=preview["nested_blender_wall_s"])
        result["middle_preview_costs"] = dict(wall_s=middle_preview["wall_s"], receipt_path=middle_preview["receipt_path"],
            style="16/4 preview completed before root followup arrived, separate attempt retained")
        result["selection"] = "16/4 key/fill, world .15 and clay(.28,.32,.4), 32 samples after review of 80/20 and 8/2"
        result["original_reference_phase_wall_s"] = read("private/processes/reference_control_01.controller.json")["wall_s"]
        result["original_reference_render_nested_wall_s"] = sum(job["wall_s"] for case in control["cases"] for job in case["jobs"] if "render" in job["label"])
        result["image_count"] = sum(len(job["receipt"]["images"]) for job in jobs)
        for case in cases:
            pair = [job["receipt"] for job in jobs if job["job"]["path"].split("/")[-2].startswith(case["case_id"])]
            if len(pair) != 2 or pair[0]["render_spec_sha256"] != pair[1]["render_spec_sha256"]:
                raise ValueError("v2_before_after_camera_or_style_mismatch")
    write(output, result)


if __name__ == "__main__":
    main()
