"""Exact pooled RGB error for three matched local PNG views."""

import hashlib
from pathlib import Path
import time

from common import identity
from image_inputs import read_png_rgb
import numpy as np


VIEW_NAMES = ("forearm_front", "forearm_side", "forearm_45")
RGB_SAMPLE_COUNT = 3 * 640 * 640 * 3


class PNGCache:
    """A caller-owned cache keyed by verified PNG bytes."""

    def __init__(self):
        self.arrays = {}

    @property
    def resident_bytes(self):
        return sum(value.nbytes for value in self.arrays.values())


def _by_view(rows):
    selected = {}
    for row in rows:
        role = row.get("role", row.get("name", ""))
        matches = [view for view in VIEW_NAMES if role == view or role.endswith("_" + view)]
        if not matches:
            continue
        view = matches[0]
        if view in selected:
            raise ValueError("duplicate_local_image_view_" + view)
        if "camera" not in row:
            raise ValueError("matched_image_camera_metadata_required")
        selected[view] = row
    if set(selected) != set(VIEW_NAMES):
        raise ValueError("exact_three_local_image_views_required")
    return selected


def _read(row, cache):
    started, cpu = time.perf_counter(), time.process_time()
    path = Path(row["path"]).resolve()
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if len(raw) != row["bytes"] or sha != row["sha256"]:
        raise ValueError("bound_image_bytes_or_SHA256_changed")
    key = (sha, len(raw))
    cache_hit = cache is not None and key in cache.arrays
    if cache_hit:
        pixels = cache.arrays[key]
    else:
        pixels = read_png_rgb(raw)
        if pixels.shape != (640, 640, 3) or pixels.dtype != np.uint8:
            raise ValueError("calibration_requires_640_square_uint8_RGB")
        pixels.setflags(write=False)
        if cache is not None:
            cache.arrays[key] = pixels
    return pixels, dict(path=str(path), sha256=sha, PNG_bytes=len(raw), cache_hit=cache_hit,
        decoded_RGB_bytes=pixels.nbytes, decoded_this_request=not cache_hit,
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu)


def measure_images(reference_rows, candidate_rows, *, output_dir=None, cache=None):
    """Measure all RGB samples with integer accumulation and optional raw RGB output."""
    started, cpu = time.perf_counter(), time.process_time()
    references, candidates = _by_view(reference_rows), _by_view(candidate_rows)
    per_view, reads, arrays, bound_images = [], [], {}, []
    for view in VIEW_NAMES:
        reference, candidate = references[view], candidates[view]
        if reference["camera"] != candidate["camera"]:
            raise ValueError("reference_candidate_camera_mismatch_" + view)
        normal_pixels, normal_read = _read(reference, cache)
        current_pixels, current_read = _read(candidate, cache)
        reads.extend((dict(normal_read, role="reference_" + view), dict(current_read, role="candidate_" + view)))
        difference = np.abs(current_pixels.astype(np.int16) - normal_pixels.astype(np.int16))
        absolute_sum = int(difference.sum(dtype=np.int64))
        count = int(difference.size)
        per_view.append(dict(view=view, absolute_error_sum=absolute_sum, sample_count=count,
            MAE_DN=absolute_sum / count))
        arrays["reference_" + view] = normal_pixels
        arrays["candidate_" + view] = current_pixels
        bound_images.append(dict(view=view, reference=dict(reference), candidate=dict(candidate)))
    total = sum(row["absolute_error_sum"] for row in per_view)
    sample_count = sum(row["sample_count"] for row in per_view)
    if sample_count != RGB_SAMPLE_COUNT:
        raise ValueError("fixed_calibration_RGB_sample_count_changed")
    rgb_artifact = None
    serialization_wall, serialization_cpu = 0., 0.
    if output_dir is not None:
        directory = Path(output_dir).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        save_started, save_cpu = time.perf_counter(), time.process_time()
        path = directory / "RGB.npz"
        np.savez_compressed(path, **arrays)
        rgb_artifact = identity(path)
        serialization_wall, serialization_cpu = time.perf_counter() - save_started, time.process_time() - save_cpu
    return dict(status="pass", metric="pooled_mean_absolute_RGB_difference_DN",
        absolute_error_sum=total, sample_count=sample_count, pooled_MAE_DN=total / sample_count,
        per_view=per_view, bound_images=bound_images, decoded_RGB_npz=rgb_artifact,
        decode_costs=dict(reads=reads, PNG_read_calls=len(reads), cold_decodes=sum(row["decoded_this_request"] for row in reads),
            cache_hits=sum(row["cache_hit"] for row in reads), PNG_bytes_read=sum(row["PNG_bytes"] for row in reads),
            cold_decoded_RGB_bytes=sum(row["decoded_RGB_bytes"] for row in reads if row["decoded_this_request"]),
            wall_s=sum(row["wall_s"] for row in reads), CPU_s=sum(row["CPU_s"] for row in reads),
            loaded_RGB_array_bytes=sum(value.nbytes for value in arrays.values()),
            cache_resident_RGB_bytes=cache.resident_bytes if cache is not None else 0),
        RGB_serialization_wall_s=serialization_wall, RGB_serialization_CPU_s=serialization_cpu,
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        selector_inputs="All RGB samples of the three matched local PNG pairs and their camera/byte identities")


def evaluate_images(reference_rows, candidate_rows, baseline_rows=None, output_dir=None, *, cache=None):
    result = measure_images(reference_rows, candidate_rows, output_dir=output_dir, cache=cache)
    if baseline_rows is not None:
        baseline = measure_images(reference_rows, baseline_rows, cache=cache)
        result["baseline_absolute_error_sum"] = baseline["absolute_error_sum"]
        result["normalized_to_initial"] = (result["absolute_error_sum"] / baseline["absolute_error_sum"]
            if baseline["absolute_error_sum"] else None)
        result["baseline_measurement"] = baseline
    return result
