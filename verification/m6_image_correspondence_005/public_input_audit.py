"""Check the actual shared consumer task and bounded public input surface."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from consumer_runner import prompt_for
from image_inputs import image_inputs
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2"), required=True)
    args = parser.parse_args()
    started, cpu = time.perf_counter(), time.process_time()
    directory = HERE / "private/consumer_cases/repair"
    task = read(directory / "task.json")
    rows = image_inputs(directory)
    actual_task = dict(task, images=rows)
    prompt = prompt_for(actual_task, read("PLAN.json")["consumer"])
    if isinstance(prompt, str):
        prompt = prompt.encode("utf8")
    checks = {}
    with np.load(directory / "input.npz", allow_pickle=False) as archive:
        fields = set(archive.files)
        expected = {"vertices", "vertices_world", "vertices_local", "matrix_world", "faces", "source_ids",
            "poly_offsets", "poly_vertices", "triangle_polygon_ids", "F_source_ids", "I_ids", "protected_ids",
            "B0_ids", "B1_ids", "local_edges", "n0"}
        checks["public_array_fields_allowlist"] = fields == expected
        checks["current_source_ID_indexing"] = np.array_equal(archive["source_ids"], np.arange(27304))
        checks["fixed_410_274_domains"] = len(archive["F_source_ids"]) == 410 and len(archive["I_ids"]) == 274
    checks["public_packet_is_actual_damaged_initial"] = identity(directory / "input.npz")["sha256"] == read("CASE_BINDING.json")["public_initial"]["sha256"]
    checks["eight_shared_bound_PNGs"] = len(rows) == 8 and all(rows[i]["camera"] == rows[i + 4]["camera"] for i in range(4))
    forbidden = ("2026111604", "8192", "4096", "noise_array", "noise_seed", "clean_vertices_world", "support_ids", "private/scoring", "source_original", "m6_degrid_004")
    text = prompt.decode("utf8").lower()
    checks["task_prompt_construction_and_truth_absent"] = all(value not in text for value in forbidden)
    checks["shared_pixel_and_camera_entrypoints_documented"] = all(name in text for name in ("read_image_pixels", "image_cameras", "save_fit_diagnostics"))
    states = [read(path) for path in (HERE / "private/sessions").glob(args.stage + "_repair_*/session.json")]
    checks["stage_pair_unmodified"] = len(states) == 2 and all(row["version"] == 0 and not row["operations"] for row in states)
    result = dict(cycle_id="M6-IMAGE-CORRESPONDENCE-005", stage=args.stage,
        status="pass" if all(checks.values()) else "fail", checks=checks, passed=sum(checks.values()), total=len(checks),
        prompt_SHA256=hashlib.sha256(prompt).hexdigest(), prompt_UTF8_bytes=len(prompt),
        public_task=identity(directory / "task.json"), public_packet=identity(directory / "input.npz"),
        scope="Actual prompt, current-only public packet and shared bound image metadata. Private controller, scorer and file-access audit records are outside the public-input surface.",
        actual_Pro_calls=0, actual_Blender_calls=0, wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu)
    write("CONSUMER_PUBLIC_INPUT_AUDIT_" + args.stage + ".json", result)
    print(json.dumps({key: result[key] for key in ("stage", "status", "passed", "total", "prompt_UTF8_bytes")}))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
