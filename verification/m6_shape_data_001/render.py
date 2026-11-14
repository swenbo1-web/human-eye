"""Render frozen source and normal-control rows from actual local mesh arrays.

All display geometry and generated images stay under this batch's private
directory. Reference coordinates define each fixed camera and supply displacement
annotations. Dataset acceptance never changes the selected rows or observations.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont


SOURCE_ORDER = ("Yanyite", "Richie", "Chipow", "Yunhex")
STRATUM_ORDER = ("natural_concave", "natural_convex", "curvature_change", "source_boundary_near")
STRATUM_LABELS = {
    "natural_concave": "Natural concave surface",
    "natural_convex": "Natural convex surface",
    "curvature_change": "Curvature change",
    "source_boundary_near": "Near source boundary",
}
SAMPLES = (("sample_00", "Normal control"), ("sample_01", "Shallow dent"), ("sample_06", "Heavy dent"))
PANEL_SIZE = (460, 330)
DETAIL_FRAME_HEIGHT_M = .055
SUPERSAMPLING = 2
LIGHT = np.array([-.35, .55, 1.], dtype=np.float64)


def _font(size, bold=False):
    path = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
    if path.exists():
        return ImageFont.truetype(str(path), size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _unit(vector):
    length = float(np.linalg.norm(vector))
    if not np.isfinite(length) or length == 0:
        raise ValueError("invalid_camera_vector")
    return vector / length


def _camera(normal):
    """Use the prior verified renderer's deterministic 45-degree camera rule."""
    normal = _unit(np.asarray(normal, dtype=np.float64))
    up_hint = np.array([0., 0., 1.])
    up = up_hint - np.dot(up_hint, normal) * normal
    if np.linalg.norm(up) < 1e-8:
        up_hint = np.array([0., 1., 0.])
        up = up_hint - np.dot(up_hint, normal) * normal
    up = _unit(up)
    tangent = _unit(np.cross(up, normal))
    view = _unit(normal + tangent)
    right = _unit(np.cross(up, view))
    up = _unit(np.cross(view, right))
    return np.stack((right, up, view))


def _private_path(here, value):
    path = Path(value)
    path = (path if path.is_absolute() else here / path).resolve()
    if not path.is_relative_to(here / "private"):
        raise ValueError("render_geometry_path_outside_batch_private")
    return path


def _record(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _coordinates(path, count=None):
    value = np.load(path, allow_pickle=False)
    if value.ndim != 2 or value.shape[1] != 3 or not np.isfinite(value).all():
        raise ValueError("invalid_render_coordinates")
    if count is not None and len(value) != count:
        raise ValueError("render_coordinate_count_mismatch")
    if value.dtype != np.dtype("float64"):
        raise ValueError("render_coordinates_require_world_float64")
    return value


def _load_row(here, patch, cases):
    folder = _private_path(here, patch["private_directory"])
    reference_path = folder / "reference_local.npy"
    reference = _coordinates(reference_path)
    with np.load(folder / "mapping.npz", allow_pickle=False) as mapping:
        faces = mapping["context_triangles"].copy()
        source_ids = mapping["context_source_ids"].copy()
    with np.load(folder / "graph.npz", allow_pickle=False) as graph:
        allowed_mask = graph["allowed_mask"].copy()
    if faces.ndim != 2 or faces.shape[1] != 3 or not len(faces):
        raise ValueError("invalid_render_triangles")
    if not np.issubdtype(faces.dtype, np.integer) or faces.min() < 0 or faces.max() >= len(reference):
        raise ValueError("render_triangle_index_out_of_range")
    if source_ids.shape != (len(reference),) or allowed_mask.shape != (len(reference),):
        raise ValueError("render_mapping_shape_mismatch")
    center = np.flatnonzero(source_ids == int(patch["center_vertex_id"]))
    if len(center) != 1:
        raise ValueError("render_center_requires_unique_local_mapping")
    center_index = int(center[0])
    basis = _camera(patch["center_normal"])
    origin = reference[center_index].copy()
    states = []
    for sample_id, label in SAMPLES:
        case = cases[(patch["id"], sample_id)]
        observed_record = case["observed"]
        path = _private_path(here, observed_record["path"])
        actual_record = _record(path)
        if any(actual_record[key] != observed_record[key] for key in ("bytes", "sha256")):
            raise ValueError("observed_render_input_hash_mismatch")
        vertices = _coordinates(path, len(reference))
        displacement_m = float(np.linalg.norm(vertices - reference, axis=1).max())
        if not np.isclose(displacement_m, float(case["damage_max_m"]), rtol=1e-10, atol=1e-12):
            raise ValueError("render_displacement_index_mismatch")
        states.append({"id": case["id"], "sample_id": sample_id, "label": label,
                       "vertices": vertices, "observed": actual_record,
                       "accepted": bool(case["accepted"]), "rejection_reasons": case["rejection_reasons"],
                       "quality": case["quality"], "damage_max_m": displacement_m})
    return {"patch": patch, "reference": reference, "faces": faces,
            "allowed_faces": np.all(allowed_mask[faces], axis=1),
            "basis": basis, "origin": origin, "center_local_index": center_index,
            "reference_record": _record(reference_path), "states": states}


def _shared_scale():
    """Use one fixed physical detail window for every panel in both figures."""
    pixels_per_m = PANEL_SIZE[1] / DETAIL_FRAME_HEIGHT_M
    half_frame = np.array(PANEL_SIZE, dtype=np.float64) / (2 * pixels_per_m)
    return float(pixels_per_m), [(-half_frame).tolist(), half_frame.tolist()]


def _raster(row, vertices, pixels_per_m):
    """Orthographic triangle rasterization with barycentric depth buffering."""
    width, height = (value * SUPERSAMPLING for value in PANEL_SIZE)
    transformed = (vertices - row["origin"]) @ row["basis"].T
    screen = transformed.copy()
    scale = pixels_per_m * SUPERSAMPLING
    screen[:, 0] = transformed[:, 0] * scale + width / 2
    screen[:, 1] = height / 2 - transformed[:, 1] * scale
    pixels = np.full((height, width, 3), (247, 249, 250), dtype=np.uint8)
    depth = np.full((height, width), -np.inf)
    light = _unit(LIGHT)
    degenerate = 0
    for ordinal, face in enumerate(row["faces"]):
        points = screen[face]
        x0 = max(0, int(math.floor(points[:, 0].min())))
        x1 = min(width - 1, int(math.ceil(points[:, 0].max())))
        y0 = max(0, int(math.floor(points[:, 1].min())))
        y1 = min(height - 1, int(math.ceil(points[:, 1].max())))
        if x1 < x0 or y1 < y0:
            continue
        a, b, c = points
        denominator = ((b[1] - c[1]) * (a[0] - c[0]) +
                       (c[0] - b[0]) * (a[1] - c[1]))
        if abs(denominator) < 1e-14:
            degenerate += 1
            continue
        normal = np.cross(transformed[face[1]] - transformed[face[0]],
                          transformed[face[2]] - transformed[face[0]])
        length = float(np.linalg.norm(normal))
        if length == 0:
            degenerate += 1
            continue
        yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        xx = xx + .5
        yy = yy + .5
        first = ((b[1] - c[1]) * (xx - c[0]) + (c[0] - b[0]) * (yy - c[1])) / denominator
        second = ((c[1] - a[1]) * (xx - c[0]) + (a[0] - c[0]) * (yy - c[1])) / denominator
        third = 1 - first - second
        z = first * a[2] + second * b[2] + third * c[2]
        visible = (first >= -1e-10) & (second >= -1e-10) & (third >= -1e-10)
        current = depth[y0:y1 + 1, x0:x1 + 1]
        visible &= z > current
        brightness = .26 + .74 * abs(float(np.dot(normal / length, light)))
        base = np.array([83., 163., 177.]) if row["allowed_faces"][ordinal] else np.array([165., 175., 183.])
        color = np.clip(base * brightness, 0, 255).astype(np.uint8)
        pixels[y0:y1 + 1, x0:x1 + 1][visible] = color
        current[visible] = z[visible]
    image = Image.fromarray(pixels).resize(PANEL_SIZE, Image.Resampling.LANCZOS)
    marker = ImageDraw.Draw(image)
    center_x, center_y = (value / 2 for value in PANEL_SIZE)
    marker.line((center_x - 6, center_y, center_x - 3, center_y), fill="#a53521", width=1)
    marker.line((center_x + 3, center_y, center_x + 6, center_y), fill="#a53521", width=1)
    marker.line((center_x, center_y - 6, center_x, center_y - 3), fill="#a53521", width=1)
    marker.line((center_x, center_y + 3, center_x, center_y + 6), fill="#a53521", width=1)
    return image, {"covered_supersampled_pixels": int(np.isfinite(depth).sum()),
                   "edge_on_or_degenerate_triangles_skipped": degenerate}


def _scale_bar(draw, x, y, pixels_per_m):
    # Choose one readable physical length for both figures from the common scale.
    target_m = 100 / pixels_per_m
    exponent = 10 ** math.floor(math.log10(target_m))
    length_m = max(value * exponent for value in (1, 2, 5, 10) if value * exponent <= target_m)
    length_px = length_m * pixels_per_m
    draw.line((x, y, x + length_px, y), fill="#173a49", width=3)
    draw.line((x, y - 5, x, y + 5), fill="#173a49", width=2)
    draw.line((x + length_px, y - 5, x + length_px, y + 5), fill="#173a49", width=2)
    draw.text((x + length_px + 10, y - 10), f"{length_m * 1000:g} mm", font=_font(17), fill="#173a49")
    return {"length_m": length_m, "length_px": length_px}


def _comparison(path, title, rows, pixels_per_m, image_cache):
    margin, gap, header, row_height = 32, 16, 138, 420
    panel_width, panel_height = PANEL_SIZE
    width = 2 * margin + 3 * panel_width + 2 * gap
    height = header + len(rows) * row_height + 60
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 20), title, font=_font(28, True), fill="#102c3a")
    crop_width_mm = panel_width / pixels_per_m * 1000
    crop_height_mm = panel_height / pixels_per_m * 1000
    draw.text((margin, 57), f"Fixed center detail crop {crop_width_mm:.1f} x {crop_height_mm:.1f} mm  |  cross marks reference center",
              font=_font(16), fill="#425969")
    draw.text((margin, 79), "Actual source triangles  |  teal permitted region  |  grey context halo",
              font=_font(16), fill="#425969")
    for column, (sample_id, label) in enumerate(SAMPLES):
        x = margin + column * (panel_width + gap)
        draw.text((x, 104), f"{label}  /  {sample_id}", font=_font(20, True), fill="#173a49")
    for row_index, row in enumerate(rows):
        patch = row["patch"]
        y = header + row_index * row_height
        label = f"{patch['source']}  |  {STRATUM_LABELS[patch['stratum']]}  |  {patch['id']}"
        draw.text((margin, y), label, font=_font(21, True), fill="#173a49")
        for column, state in enumerate(row["states"]):
            x = margin + column * (panel_width + gap)
            key = (patch["id"], state["sample_id"])
            if key not in image_cache:
                image_cache[key] = _raster(row, state["vertices"], pixels_per_m)
            image, raster_stats = image_cache[key]
            state["raster"] = raster_stats
            canvas.paste(image, (x, y + 34))
            status = "ACCEPTED" if state["accepted"] else "REJECTED"
            color = "#425969" if state["accepted"] else "#a53521"
            annotation = f"max displacement {1000 * state['damage_max_m']:.3f} mm  |  {status}"
            draw.text((x, y + panel_height + 44), annotation, font=_font(17, not state["accepted"]), fill=color)
    scale = _scale_bar(draw, margin, height - 30, pixels_per_m)
    draw.text((margin + 230, height - 41),
              f"Shared scale {pixels_per_m:.2f} px/m  |  reference-centered orthographic cameras, 45 degrees oblique",
              font=_font(17), fill="#425969")
    canvas.save(path)
    return {**_record(path), "pixels": [width, height], "scale_bar": scale,
            "selected_patch_ids": [row["patch"]["id"] for row in rows]}


def render_dataset(here):
    """Write two fixed comparison PNGs and render metadata under private/."""
    started, cpu_started = time.perf_counter(), time.process_time()
    here = Path(here).resolve()
    selection_path = here / "PATCH_SELECTION.json"
    index_path = here / "DATASET_INDEX.json"
    selection = json.loads(selection_path.read_bytes())
    dataset = json.loads(index_path.read_bytes())
    patches = selection["patches"]
    source_patches = [next(patch for patch in patches if patch["source"] == source) for source in SOURCE_ORDER]
    stratum_patches = [next(patch for patch in patches if patch["stratum"] == stratum) for stratum in STRATUM_ORDER]
    cases = {}
    for case in dataset["cases"]:
        key = (case["patch_id"], case["id"].rsplit("/", 1)[-1])
        if key in cases:
            raise ValueError("duplicate_dataset_case")
        cases[key] = case
    rows = {}
    for patch in source_patches + stratum_patches:
        if patch["id"] not in rows:
            rows[patch["id"]] = _load_row(here, patch, cases)
    pixels_per_m, frame = _shared_scale()
    private = here / "private"
    image_cache = {}
    outputs = []
    for filename, title, selected in (
        ("SOURCE_COMPARISON.png", "Frozen source comparison", source_patches),
        ("NORMAL_CONTROLS.png", "Frozen normal-control strata", stratum_patches),
    ):
        output = _comparison(private / filename, title, [rows[patch["id"]] for patch in selected],
                             pixels_per_m, image_cache)
        outputs.append(output)
    row_records = []
    for row in rows.values():
        patch = row["patch"]
        row_records.append({"patch_id": patch["id"], "source": patch["source"], "stratum": patch["stratum"],
                            "reference": row["reference_record"], "center_source_vertex_id": patch["center_vertex_id"],
                            "center_local_index": row["center_local_index"], "origin_world_m": row["origin"].tolist(),
                            "basis_right_up_view": row["basis"].tolist(), "context_vertices": len(row["reference"]),
                            "context_triangles": len(row["faces"]), "permitted_triangles": int(row["allowed_faces"].sum()),
                            "states": [{key: value for key, value in state.items() if key != "vertices"}
                                       for state in row["states"]]})
    elapsed, cpu_s = time.perf_counter() - started, time.process_time() - cpu_started
    metadata = {
        "cycle_id": "M6-SHAPE-DATA-001", "selection": _record(selection_path), "dataset_index": _record(index_path),
        "row_selection": "First frozen patch per source and per stratum, independent of generated-case acceptance.",
        "source_order": list(SOURCE_ORDER), "stratum_order": list(STRATUM_ORDER),
        "samples": [sample for sample, _ in SAMPLES], "coordinates": "Actual observed local context arrays in world meters, float64.",
        "renderer": {"projection": "orthographic", "depth_buffer": "float64 per-pixel barycentric triangle depth",
                     "oblique_angle_from_reference_center_normal_deg": 45., "camera_fixed_across_row": True,
                     "pixels_per_m": pixels_per_m, "projection_frame_m": frame, "panel_size_px": list(PANEL_SIZE),
                     "supersampling": SUPERSAMPLING, "light_camera_coordinates": _unit(LIGHT).tolist(),
                     "framing": "Fixed reference-centered physical detail window shared by both figures and every state.",
                     "detail_frame_height_m": DETAIL_FRAME_HEIGHT_M,
                     "context_clipped_at_viewport": True, "scale_independent_of_observations": True,
                     "center_marker": {"reference_camera_xy_m": [0., 0.], "screen_xy_px": [value / 2 for value in PANEL_SIZE],
                                       "arm_extent_px": 6, "open_center_radius_px": 3},
                     "rejected_cases_retained": True, "max_displacement_domain": "All context vertices."},
        "rows": row_records, "outputs": outputs, "wall_s_before_metadata_write": elapsed,
        "cpu_s_before_metadata_write": cpu_s,
    }
    meta_path = private / "RENDER_META.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                         encoding="utf-8", newline="\n")
    return {"outputs": outputs, "meta": _record(meta_path), "unique_patches": len(rows),
            "pixels_per_m": pixels_per_m, "wall_s": time.perf_counter() - started,
            "cpu_s": time.process_time() - cpu_started}


if __name__ == "__main__":
    import sys
    print(json.dumps(render_dataset(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent),
                     indent=2, allow_nan=False))
