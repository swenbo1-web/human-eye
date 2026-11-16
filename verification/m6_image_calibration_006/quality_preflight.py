"""Verify exact image loss, independent PNG decoding and fixed midpoint order."""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from image_inputs import read_png_rgb
from image_metric import PNGCache, measure_images, VIEW_NAMES, RGB_SAMPLE_COUNT


def main():
    started, cpu = time.perf_counter(), time.process_time()
    source = read("SOURCE_BINDING.json")
    midpoint = read("MIDPOINT_SOURCE_BINDING.json")
    normal_rows = source["images"]["normal"]
    current_rows = source["images"]["current"]
    directory = HERE / "private/image_metric_preflight"
    directory.mkdir(parents=True, exist_ok=True)
    cache = PNGCache()
    initial = measure_images(normal_rows, current_rows, output_dir=directory / "initial", cache=cache)
    again = measure_images(normal_rows, current_rows, cache=cache)
    checks = dict(fixed_sample_count=initial["sample_count"] == RGB_SAMPLE_COUNT,
        integer_absolute_sum=type(initial["absolute_error_sum"]) is int,
        initial_cold_six_decodes=initial["decode_costs"]["cold_decodes"] == 6,
        same_bytes_warm_six_hits=again["decode_costs"]["cache_hits"] == 6,
        warm_loss_exact=initial["absolute_error_sum"] == again["absolute_error_sum"])
    old = HERE.parent / "m6_image_correspondence_005"
    midpoint_dir = Path(midpoint["source_directory"]) / "private/midpoint/workers/images"
    image_results = {"initial": initial}
    for label, folder in (("half", midpoint_dir), ("full", old / "private/results/v1_repair_native/after_views")):
        rows = []
        for view in VIEW_NAMES:
            template = next(row for row in current_rows if row["role"].endswith(view))
            path = folder / (view + ".png")
            descriptor = identity(path)
            descriptor["path"] = str(path.resolve())
            rows.append(dict(template, **descriptor))
        image_results[label] = measure_images(normal_rows, rows, output_dir=directory / label, cache=cache)
    expected = read("MIDPOINT_IMAGE_RESULT.json")
    for label, result in image_results.items():
        checks[label + "_MAE_matches_fixed_root_result"] = result["pooled_MAE_DN"] == expected["MAE_DN"][label]
        ratio = result["absolute_error_sum"] / initial["absolute_error_sum"]
        checks[label + "_normalized_matches_fixed_root_result"] = abs(ratio - expected["normalized_to_initial"][label]) <= 1e-15
    checks["fixed_three_sample_image_order"] = (image_results["half"]["absolute_error_sum"] < image_results["full"]["absolute_error_sum"] < initial["absolute_error_sum"])
    corrupt = bytearray(Path(normal_rows[0]["path"]).read_bytes())
    corrupt[45] ^= 1
    try:
        read_png_rgb(bytes(corrupt))
    except ValueError:
        checks["corrupt_PNG_CRC_rejected"] = True
    else:
        checks["corrupt_PNG_CRC_rejected"] = False
    changed = copy.deepcopy(current_rows)
    changed[0]["camera"]["pixel_convention"] = "invalid"
    try:
        measure_images(normal_rows, changed)
    except ValueError:
        checks["mismatched_camera_rejected"] = True
    else:
        checks["mismatched_camera_rejected"] = False
    wrong = copy.deepcopy(current_rows)
    wrong[0]["sha256"] = "0" * 64
    try:
        measure_images(normal_rows, wrong, cache=cache)
    except ValueError:
        checks["changed_image_identity_rejected_even_when_cached"] = True
    else:
        checks["changed_image_identity_rejected_even_when_cached"] = False
    pillow_code = """import hashlib, json, sys
from PIL import Image
rows = json.loads(sys.stdin.read())
result = []
for row in rows:
    with Image.open(row['path']) as image:
        pixels = image.convert('RGB')
        result.append(dict(path=row['path'], size=list(pixels.size), sha256=hashlib.sha256(pixels.tobytes()).hexdigest()))
print(json.dumps(result))
"""
    pillow_python = Path("C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe")
    pillow_started = time.perf_counter()
    result = subprocess.run([str(pillow_python), "-I", "-B", "-X", "utf8", "-c", pillow_code],
        input=json.dumps(normal_rows + current_rows).encode(), capture_output=True, check=True)
    pillow_wall = time.perf_counter() - pillow_started
    (directory / "PILLOW_STDOUT.json").write_bytes(result.stdout)
    (directory / "PILLOW_STDERR.bin").write_bytes(result.stderr)
    for index, row in enumerate(json.loads(result.stdout)):
        raw = Path(row["path"]).read_bytes()
        pixels = read_png_rgb(raw)
        checks["Pillow_RGB_matches_" + str(index)] = hashlib.sha256(pixels.tobytes()).hexdigest() == row["sha256"] and list(pixels.shape[:2][::-1]) == row["size"]
    summary = dict(cycle_id="M6-IMAGE-CALIBRATION-006", status="pass" if all(checks.values()) else "fail",
        checks=checks, passed=sum(checks.values()), total=len(checks), image_results=image_results,
        Pillow_helper_wall_s=pillow_wall, hidden_target_or_labels_read=False,
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        actual_Blender_calls=0, actual_Pro_calls=0, training=0,
        source_identities=[identity(HERE / name) for name in ("image_metric.py", "image_inputs.py", "quality_preflight.py")])
    write("IMAGE_METRIC_PREFLIGHT.json", summary)
    print({key: summary[key] for key in ("status", "passed", "total", "wall_s")})
    if summary["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
