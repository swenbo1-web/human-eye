"""Compare actual two-stage calibration coordinates, pixels, losses and choices."""

import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from calibration_score import checked_path
from evaluate import packet


def exact_arrays(first_path, second_path):
    first, second = packet(first_path), packet(second_path)
    return dict(fields_equal=set(first) == set(second), arrays={key: key in second and
        first[key].dtype == second[key].dtype and first[key].shape == second[key].shape and
        first[key].tobytes() == second[key].tobytes() for key in first})


def main():
    started, cpu = time.perf_counter(), time.process_time()
    source = read("SOURCE_BINDING.json")
    checks, candidates, pairs = {}, [], []
    for proposal in source["proposals"]:
        proposal_id = proposal["proposal_id"]
        first = read("CALIBRATION_v1_" + proposal_id + ".json")
        second = read("CALIBRATION_v2_" + proposal_id + ".json")
        checks[proposal_id + " fixed_alpha_sets"] = [row["alpha"] for row in first["candidates"]] == [row["alpha"] for row in second["candidates"]] == [0., .5, 1.]
        checks[proposal_id + " selected_alpha"] = first["selected_alpha"] == second["selected_alpha"]
        for left, right in zip(first["candidates"], second["candidates"]):
            alpha = left["alpha"]
            prefix = proposal_id + " alpha" + str(alpha)
            native = exact_arrays(checked_path(left["readback"]), checked_path(right["readback"]))
            payload = exact_arrays(checked_path(left["payload"]), checked_path(right["payload"]))
            checks[prefix + " alpha"] = alpha == right["alpha"]
            checks[prefix + " readback_fields"] = native["fields_equal"] and all(native["arrays"].values())
            checks[prefix + " payload"] = payload["fields_equal"] and all(payload["arrays"].values())
            checks[prefix + " integer_image_loss"] = left["image"]["absolute_error_sum"] == right["image"]["absolute_error_sum"]
            checks[prefix + " sample_count"] = left["image"]["sample_count"] == right["image"]["sample_count"] == 3686400
            checks[prefix + " normalized_loss"] = left["normalized_to_initial"] == right["normalized_to_initial"]
            checks[prefix + " technical_status"] = left["technical_status"] == right["technical_status"]
            by_view = {row["role"]: row for row in right["images"]}
            for image in left["images"]:
                other = by_view[image["role"]]
                checks[prefix + " camera " + image["role"]] = image["camera"] == other["camera"]
                pairs.append(dict(name=prefix + " " + image["role"], first=str(checked_path(image)), second=str(checked_path(other))))
            candidates.append(dict(proposal_id=proposal_id, alpha=alpha, native_arrays=native, payload_arrays=payload,
                first_saved=left["saved_blend"], second_saved=right["saved_blend"]))
    midpoint = read("MIDPOINT_SOURCE_BINDING.json")
    midpoint_dir = Path(midpoint["source_directory"]) / "private/midpoint/workers"
    first_native = read("CALIBRATION_v1_v1_native.json")
    half = next(row for row in first_native["candidates"] if row["alpha"] == .5)
    midpoint_native = exact_arrays(checked_path(half["readback"]), midpoint_dir / "readback.npz")
    checks["root_midpoint_native_arrays"] = midpoint_native["fields_equal"] and all(midpoint_native["arrays"].values())
    for image in half["images"]:
        view = image["role"].removeprefix("current_")
        pairs.append(dict(name="root_midpoint " + view, first=str(checked_path(image)), second=str(midpoint_dir / "images" / (view + ".png"))))
    code = """import hashlib, json, sys
from PIL import Image
results = []
for pair in json.loads(sys.stdin.read()):
    with Image.open(pair['first']) as first:
        first_rgba = first.convert('RGBA')
    with Image.open(pair['second']) as second:
        second_rgba = second.convert('RGBA')
    first_bytes, second_bytes = first_rgba.tobytes(), second_rgba.tobytes()
    results.append(dict(name=pair['name'], first=pair['first'], second=pair['second'],
        first_RGBA_SHA256=hashlib.sha256(first_bytes).hexdigest(), second_RGBA_SHA256=hashlib.sha256(second_bytes).hexdigest(),
        RGBA_equal=first_rgba.size == second_rgba.size and first_bytes == second_bytes))
print(json.dumps(results))
"""
    python = Path("C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe")
    process = subprocess.run([str(python), "-I", "-B", "-X", "utf8", "-c", code],
        input=json.dumps(pairs).encode(), capture_output=True, check=True)
    output = HERE / "private/comparison"
    output.mkdir(parents=True, exist_ok=True)
    (output / "PILLOW_RGBA.json").write_bytes(process.stdout)
    (output / "PILLOW_RGBA.stderr").write_bytes(process.stderr)
    rgba = json.loads(process.stdout)
    for row in rgba:
        checks[row["name"] + " RGBA"] = row["RGBA_equal"]
    result = dict(cycle_id="M6-IMAGE-CALIBRATION-006", status="pass" if all(checks.values()) else "fail",
        checks=checks, passed=sum(checks.values()), total=len(checks), candidates=candidates, pixel_pairs=rgba,
        root_midpoint_native_arrays=midpoint_native, root_midpoint_source=identity(HERE / "MIDPOINT_SOURCE_BINDING.json"),
        actual_Pro_calls=0, actual_Blender_calls=0, wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        comparison_scope="Decoded RGBA, complete native/world readback arrays and payload arrays. Saved-file identity metadata is retained separately.")
    write("CALIBRATION_COMPARISON.json", result)
    print({key: result[key] for key in ("status", "passed", "total", "wall_s")})
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
