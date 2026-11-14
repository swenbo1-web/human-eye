"""Render actual worst-case triangles with shared row cameras and edge units."""

import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def _records(value):
    return value.get("cases", []) if isinstance(value, dict) else value


def _private_path(here, value):
    path = Path(value).resolve()
    allowed_roots = (here / "private", here.parent / "m6_shape_data_001" / "private")
    if not any(path.is_relative_to(root.resolve()) for root in allowed_roots):
        raise ValueError("render_geometry_must_remain_in_a_batch_private_directory")
    return path


def _coordinates(here, path):
    vertices = np.load(_private_path(here, path), allow_pickle=False)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or vertices.dtype != np.float64:
        raise ValueError("render_requires_binary64_context_vertices")
    if not np.isfinite(vertices).all():
        raise ValueError("nonfinite_render_vertices")
    return vertices


def _select_worst(model_cases):
    groups = (
        ("Development worst support", lambda row: row["purpose"] == "development_train_pool"
         and not row["normal_control"]),
        ("Validation center worst support", lambda row: row["purpose"] == "validation"
         and row["position_group"] == "center" and not row["normal_control"]),
        ("Validation offcenter worst support", lambda row: row["purpose"] == "validation"
         and row["position_group"] == "offcenter" and not row["normal_control"]),
        ("Normal-control worst normal change", lambda row: row["normal_control"]),
    )
    selected, missing = [], []
    for title, keep in groups:
        eligible = [row for row in model_cases if keep(row)]
        if title.startswith("Normal"):
            score = lambda row: row["errors"]["N"]["max_over_scale"]
        else:
            score = lambda row: row["support_rmse_ratio_to_noop"]
        eligible = [row for row in eligible if score(row) is not None]
        if not eligible:
            missing.append(title)
            continue
        winner = min(eligible, key=lambda row: (-score(row), row["id"]))
        selected.append((title, winner, score(winner)))
    return selected, missing


def _load_row(here, title, record, score, baselines, renderer):
    if record["purpose"] == "reserved_test":
        raise ValueError("reserved_test_rendering_is_locked_for_this_batch")
    reference = _coordinates(here, record["reference_path"])
    observed = _coordinates(here, record["observed_path"])
    model_vertices = _coordinates(here, record["candidate_path"])
    mls_record = baselines[(record["id"], "mls")]
    mls_vertices = _coordinates(here, mls_record["candidate_path"])
    with np.load(_private_path(here, record["mapping_path"]), allow_pickle=False) as mapping:
        faces = mapping["context_triangles"].copy()
    with np.load(_private_path(here, record["graph_path"]), allow_pickle=False) as graph:
        allowed = graph["allowed_mask"].copy()
        edges = graph["edge_index"].copy()
    if faces.ndim != 2 or faces.shape[1] != 3 or not len(faces):
        raise ValueError("invalid_render_triangles")
    if faces.min() < 0 or faces.max() >= len(reference):
        raise ValueError("render_triangle_index_out_of_range")
    if any(value.shape != reference.shape for value in (observed, model_vertices, mls_vertices)):
        raise ValueError("comparison_vertex_count_mismatch")
    allowed_faces = np.all(allowed[faces], axis=1)
    cross = np.cross(reference[faces[:, 1]] - reference[faces[:, 0]],
                     reference[faces[:, 2]] - reference[faces[:, 0]])
    normal = cross[allowed_faces].sum(axis=0)
    if np.linalg.norm(normal) < 1e-15:
        normal = cross[np.argmax(np.linalg.norm(cross, axis=1))]
    basis = renderer._camera(normal)
    first, second = edges
    inside_edges = allowed[first] & allowed[second]
    edge_mean = float(np.linalg.norm(observed[second[inside_edges]]
                                    - observed[first[inside_edges]], axis=1).mean())
    if not np.isfinite(edge_mean) or edge_mean <= 0:
        raise ValueError("invalid_render_observed_mean_allowed_edge")
    origin = reference[allowed].mean(axis=0)
    vertices = [(value - origin) / edge_mean
                for value in (reference, observed, mls_vertices, model_vertices)]
    return {"title": title, "record": record, "score": score,
            "faces": faces, "allowed_faces": allowed_faces, "basis": basis,
            "origin": np.zeros(3), "vertices": vertices,
            "reference_origin_native": origin.tolist(), "display_mean_edge_native": edge_mean,
            "metrics": [None, baselines.get((record["id"], "no_op")), mls_record, record]}


def render_worst(here, results_path):
    """Render four frozen result selections using saved candidates, without inference.

    Inputs contain ``model_cases`` and ``baseline_cases``. Baseline records may
    be flat method records or per-case records containing ``no_op`` and ``mls``.
    Run with the existing base Python, which already supplies Pillow.
    """
    started, cpu_started = time.perf_counter(), time.process_time()
    here = Path(here).resolve()
    results_path = Path(results_path).resolve()
    result_bytes = results_path.read_bytes()
    results = json.loads(result_bytes)
    model_cases = _records(results["model_cases"])
    baselines = {}
    for row in _records(results["baseline_cases"]):
        if "method" in row:
            baselines[(row["id"], row["method"])] = row
        else:
            for method in ("no_op", "mls"):
                if method in row:
                    baselines[(row[method]["id"], method)] = row[method]
    spec = importlib.util.spec_from_file_location(
        "m6_frozen_triangle_renderer", here.parent / "m6_shape_data_001" / "render.py"
    )
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    selections, missing = _select_worst(model_cases)
    if not selections:
        raise ValueError("no_eligible_worst_case_results")
    rows = [_load_row(here, title, record, score, baselines, renderer)
            for title, record, score in selections]
    panel_width, panel_height = renderer.PANEL_SIZE
    half_width = half_height = 0.0
    for row in rows:
        for vertices in row["vertices"]:
            transformed = vertices @ row["basis"].T
            half_width = max(half_width, float(np.abs(transformed[:, 0]).max()))
            half_height = max(half_height, float(np.abs(transformed[:, 1]).max()))
    pixels_per_edge = min(panel_width / (2.16 * max(half_width, 1e-12)),
                          panel_height / (2.16 * max(half_height, 1e-12)))
    margin, gap, header, row_height, footer = 24, 14, 128, 416, 68
    width = 2 * margin + 4 * panel_width + 3 * gap
    height = header + len(rows) * row_height + footer
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 17), "Worst first-round cases", font=renderer._font(28, True), fill="#173344")
    draw.text((margin, 55),
              "Actual mesh triangles  |  shared cameras across each row  |  display coordinates in local mean-edge units",
              font=renderer._font(17), fill="#465b68")
    for index, name in enumerate(("Reference", "No-op", "MLS", "Model")):
        draw.text((margin + index * (panel_width + gap), 91), name,
                  font=renderer._font(21, True), fill="#173344")
    row_records = []
    for row_index, row in enumerate(rows):
        record = row["record"]
        y = header + row_index * row_height
        descriptor = row["title"] + "  |  " + record["id"]
        if not record["normal_control"]:
            descriptor += ("  |  r/D " + str(record["radius_ratio"])
                           + "  a/r " + str(record["amplitude_ratio"]))
        draw.text((margin, y), descriptor, font=renderer._font(18, True), fill="#173344")
        panel_records = []
        for index, vertices in enumerate(row["vertices"]):
            image, raster = renderer._raster(row, vertices, pixels_per_edge)
            x = margin + index * (panel_width + gap)
            canvas.paste(image, (x, y + 30))
            metrics = row["metrics"][index]
            if record["normal_control"]:
                value = 0.0 if index == 0 else (
                    record["no_op_errors"]["N"]["max_over_scale"] if metrics is None
                    else metrics["errors"]["N"]["max_over_scale"]
                )
                annotation = f"N max / observed median edge  {value:.5g}"
            else:
                value = 0.0 if index == 0 else (
                    record["no_op_errors"]["S"]["rmse_over_scale"] if metrics is None
                    else metrics["errors"]["S"]["rmse_over_scale"]
                )
                annotation = f"S RMSE / observed median edge  {value:.5g}"
            draw.text((x, y + panel_height + 38), annotation,
                      font=renderer._font(16), fill="#465b68")
            panel_records.append(raster)
        row_records.append({"selection": row["title"], "case_id": record["id"],
                            "selection_score": row["score"], "unit": record["unit"],
                            "reference_origin_native": row["reference_origin_native"],
                            "display_mean_edge_native": row["display_mean_edge_native"],
                            "basis_right_up_view": row["basis"].tolist(),
                            "context_triangles": len(row["faces"]), "panels": panel_records})
    bar_edges = 5.0
    bar_x, bar_y = margin, height - 26
    draw.line((bar_x, bar_y, bar_x + bar_edges * pixels_per_edge, bar_y), fill="#173344", width=3)
    draw.text((bar_x + bar_edges * pixels_per_edge + 12, bar_y - 11),
              "5 local mean edges  |  teal allowed region, gray context",
              font=renderer._font(17), fill="#465b68")
    render_folder = here / "private" / "renders" / results_path.stem
    output = render_folder / "WORST_COMPARISON.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    metadata = {"cycle_id": "M6-SHAPE-TRAIN-001", "results_path": str(results_path),
                "results_sha256": hashlib.sha256(result_bytes).hexdigest(),
                "image_path": str(output), "pixels": [width, height], "rows": row_records,
                "missing_selection_groups": missing,
                "selection_rule": "maximum model support RMSE/no-op RMSE in each damaged group; maximum N error/observed median edge for normal controls; lexicographic case ID breaks ties",
                "display_units": "one observed mean allowed-edge length per selected case",
                "metric_units": "one observed context median edge length per selected case",
                "pixels_per_display_edge": pixels_per_edge,
                "camera_fixed_across_each_row": True,
                "common_frame_across_all_rows_and_methods": True,
                "frame_includes_all_saved_comparison_vertices": True,
                "renderer": "reused frozen barycentric depth-buffered triangle rasterizer",
                "public_validation_inference_calls": 0, "reserved_test_observations_loaded": 0,
                "wall_s": time.perf_counter() - started, "cpu_s": time.process_time() - cpu_started}
    metadata_path = render_folder / "WORST_RENDER_META.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {"image_path": str(output), "metadata_path": str(metadata_path),
            "row_count": len(rows), "missing_selection_groups": missing,
            "wall_s": time.perf_counter() - started, "cpu_s": time.process_time() - cpu_started}


if __name__ == "__main__":
    import sys

    print(json.dumps(render_worst(Path(__file__).resolve().parent, sys.argv[1]), indent=2))
