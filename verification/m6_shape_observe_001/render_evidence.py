"""Render actual witness and opposite-label neighbor observation/reference pairs."""

import time
BOOT_WALL = time.perf_counter()
BOOT_CPU = time.process_time()

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import cases, load_case


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def own_resources():
    spec = importlib.util.spec_from_file_location("_observe_evidence_metrics", HERE.parent / "m6_shape_opt_001/process_runner.py")
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return monitor.process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def source_record(sample, local_index, renderer):
    source_id = int(sample["mapping"]["context_source_ids"][local_index])
    normal_case = dict(sample["case"])
    normal_case["id"] = sample["case"]["patch_id"] + "/sample_00"
    normal_case["sample_name"] = "sample_00"
    normal = load_case(normal_case)
    index = int(np.flatnonzero(normal["mapping"]["context_source_ids"] == source_id)[0])
    faces = sample["mapping"]["context_triangles"]
    allowed = sample["graph"]["allowed_mask"]
    origin = normal["observed"][index].copy()
    scale = float(sample["scale"])
    basis = renderer._camera(normal["inputs"]["normals"][index])
    vertices = [(sample["observed"] - origin) / scale,
                (normal["observed"] - origin) / scale]
    return {"case_id": sample["case"]["id"], "source_vertex_id": source_id,
            "local_index": int(local_index), "reference_case_id": normal_case["id"],
            "support_label": bool(sample["labels"]["damaged_mask"][local_index]),
            "frozen_score": float(sample["p"][local_index]),
            "target_norm_over_observed_scale": float(np.linalg.norm(sample["target_float64"][local_index])),
            "signed_laplacian_observed": float(sample["inputs"]["node_features"][local_index, 1]),
            "signed_laplacian_reference": float(normal["inputs"]["node_features"][index, 1]),
            "observed_scale_native": scale,
            "reference_origin_native": origin.tolist(),
            "camera_basis": basis.tolist(), "vertices": vertices,
            "faces": faces, "allowed_faces": np.all(allowed[faces], axis=1),
            "basis": basis, "origin": np.zeros(3),
            "observed_path": str(sample["folder"] / "observed" / (sample["sample_name"] + ".npy")),
            "reference_path": str(normal["folder"] / "observed/sample_00.npy"),
            "observed_sha256": sha256(sample["folder"] / "observed" / (sample["sample_name"] + ".npy")),
            "reference_sha256": sha256(normal["folder"] / "observed/sample_00.npy")}


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    evidence = json.loads((HERE / "EVIDENCE_PLAN.json").read_bytes())["evidence"]
    retrieval_path = HERE / "WITNESS_RETRIEVAL.json"
    retrieval = json.loads(retrieval_path.read_bytes())
    witness_rows = retrieval["evidence"]
    lookup = {row["evidence_id"]: row for row in witness_rows}
    case_lookup = {case["id"]: case for case in cases()}
    spec = importlib.util.spec_from_file_location("_observe_saved_triangle_renderer", HERE.parent / "m6_shape_data_001/render.py")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    rows = []
    read_started = time.perf_counter()
    for witness in evidence:
        sample = load_case(case_lookup[witness["case_id"]])
        query = source_record(sample, witness["local_index"], renderer)
        pairs = [query]
        neighbors = {}
        for descriptor in ("R0", "R1"):
            result = lookup[witness["evidence_id"]]["methods"][descriptor]
            opposite = result["nearest_opposite"]
            if opposite is None:
                pairs.append(None)
                neighbors[descriptor] = {"status": "no_opposite_label_in_five_neighbors"}
                continue
            neighbor_case = opposite["case_id"]
            neighbor = load_case(case_lookup[neighbor_case])
            source_id = int(opposite["source_vertex_id"])
            local = int(np.flatnonzero(neighbor["mapping"]["context_source_ids"] == source_id)[0])
            if bool(neighbor["labels"]["damaged_mask"][local]) == query["support_label"]:
                raise ValueError("neighbor_label_is_not_opposite_to_witness")
            pair = source_record(neighbor, local, renderer)
            pair["retrieval_distance"] = opposite["distance"]
            pairs.append(pair)
            neighbors[descriptor] = {"status": "opposite_label_in_five_neighbors", "neighbor": opposite}
        rows.append({"evidence": witness, "pairs": pairs, "neighbor_checks": neighbors})
    array_read_s = time.perf_counter() - read_started
    panel_width, panel_height = renderer.PANEL_SIZE
    max_x = max_y = 0.0
    for row in rows:
        for pair in row["pairs"]:
            if pair is None:
                continue
            for vertices in pair["vertices"]:
                projected = vertices @ pair["basis"].T
                max_x = max(max_x, float(np.abs(projected[:, 0]).max()))
                max_y = max(max_y, float(np.abs(projected[:, 1]).max()))
    pixels_per_edge = min(panel_width / (2.16 * max(max_x, 1e-12)),
                          panel_height / (2.16 * max(max_y, 1e-12)))
    margin, gap, header, row_height = 24, 12, 135, 440
    width = margin * 2 + 6 * panel_width + 5 * gap
    height = header + len(rows) * row_height + 84
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 15), "Six preselected geometry witnesses", font=renderer._font(29, True), fill="#173344")
    draw.text((margin, 57), "Actual triangles | point-centered, reference-normal-aligned views | common observed-edge display scale",
              font=renderer._font(18), fill="#465b68")
    columns = ("Witness observed", "Witness unperturbed", "R0 opposite observed", "R0 opposite unperturbed",
               "R1 opposite observed", "R1 opposite unperturbed")
    for index, title in enumerate(columns):
        draw.text((margin + index * (panel_width + gap), 99), title,
                  font=renderer._font(19, True), fill="#173344")
    render_started = time.perf_counter()
    metadata_rows = []
    for row_number, row in enumerate(rows):
        witness = row["evidence"]
        y = header + row_number * row_height
        title = (witness["evidence_id"] + " | " + witness["case_id"]
                 + " | source vertex " + str(witness["source_vertex_id"]))
        draw.text((margin, y), title, font=renderer._font(20, True), fill="#173344")
        panel_records = []
        for pair_number, pair in enumerate(row["pairs"]):
            for state_number in (0, 1):
                column = pair_number * 2 + state_number
                x = margin + column * (panel_width + gap)
                if pair is None:
                    image = Image.new("RGB", (panel_width, panel_height), (247, 249, 250))
                    ImageDraw.Draw(image).text((22, 110), "No opposite label in five neighbors", font=renderer._font(21), fill="#465b68")
                    raster = None
                    caption = "Fixed five-neighbor result"
                else:
                    image, raster = renderer._raster(pair, pair["vertices"][state_number], pixels_per_edge)
                    caption = ("y=" + str(int(pair["support_label"])) + "  p=" + format(pair["frozen_score"], ".4f")
                               + "  displacement=" + format(pair["target_norm_over_observed_scale"], ".4g") + " edges") if state_number == 0 else "Unperturbed pair at the same source vertex"
                canvas.paste(image, (x, y + 34))
                draw.text((x, y + 372), caption, font=renderer._font(16), fill="#465b68")
                if pair is not None:
                    draw.text((x, y + 396), pair["case_id"] + "  vertex " + str(pair["source_vertex_id"]),
                              font=renderer._font(15), fill="#465b68")
                    panel_records.append({"column": columns[column], "case_id": pair["case_id"],
                                          "source_vertex_id": pair["source_vertex_id"], "state": state_number,
                                          "raster": raster})
        public_pairs = []
        for pair in row["pairs"]:
            public_pairs.append(None if pair is None else {key: value for key, value in pair.items()
                                if key not in ("vertices", "faces", "allowed_faces", "basis", "origin")})
        metadata_rows.append({"evidence_id": witness["evidence_id"], "pairs": public_pairs,
                              "neighbor_checks": row["neighbor_checks"], "panels": panel_records})
    y = height - 49
    length = 5 * pixels_per_edge
    draw.line((margin, y, margin + length, y), fill="#173a49", width=3)
    draw.text((margin + length + 12, y - 11),
              "5 observed median edges | red cross at reference vertex | teal allowed region, gray context",
              font=renderer._font(18), fill="#465b68")
    folder = HERE / "private/evidence"
    folder.mkdir(parents=True, exist_ok=True)
    image_path = folder / "EVIDENCE_COMPARISON.png"
    canvas.save(image_path)
    metadata = {"cycle_id": "M6-SHAPE-OBSERVE-001", "status": "rendered_actual_geometry",
                "evidence_plan_sha256": sha256(HERE / "EVIDENCE_PLAN.json"),
                "witness_retrieval_sha256": sha256(retrieval_path),
                "image_path": str(image_path), "image_sha256": sha256(image_path),
                "pixels": [width, height], "rows": metadata_rows,
                "pixels_per_observed_median_edge": pixels_per_edge,
                "shared_scale_all_panels": True, "identical_camera_within_each_observation_reference_pair": True,
                "cross_source_camera": "same point-centered 45-degree projection relative to each pair reference normal; native frame matrices are recorded per pair",
                "all_saved_context_included_in_shared_frame": True,
                "reference_role": "unperturbed synthetic counterpart, artistic adequacy unestablished",
                "interpretation_limit": "Opposite labels among five geometric neighbors are examples of descriptor confusion; these examples do not establish identical full inputs or absence of recoverable information.",
                "new_model_forward_calls": 0, "Bunny_arrays_loaded": 0,
                "timings": {"geometry_read_prepare_wall_s": array_read_s,
                            "raster_and_save_wall_s": time.perf_counter() - render_started,
                            "main_wall_s": time.perf_counter() - started, "main_cpu_s": time.process_time() - cpu_started,
                            "bootstrap_wall_s": time.perf_counter() - BOOT_WALL,
                            "bootstrap_cpu_s": time.process_time() - BOOT_CPU},
                "own_process_at_end": own_resources()}
    (folder / "EVIDENCE_RENDER_META.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    public = {key: value for key, value in metadata.items() if key != "rows"}
    public["rows"] = [{"evidence_id": row["evidence_id"], "neighbor_checks": row["neighbor_checks"],
                       "pairs": [None if pair is None else {key: pair[key] for key in
                                  ("case_id", "reference_case_id", "source_vertex_id", "support_label", "frozen_score",
                                   "target_norm_over_observed_scale", "signed_laplacian_observed", "signed_laplacian_reference")}
                                 for pair in row["pairs"]]} for row in metadata_rows]
    public["metadata_path"] = str(folder / "EVIDENCE_RENDER_META.json")
    public["metadata_sha256"] = sha256(folder / "EVIDENCE_RENDER_META.json")
    (HERE / "GEOMETRY_EVIDENCE.json").write_text(json.dumps(public, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"image_path": str(image_path), "rows": len(rows), "wall_s": metadata["timings"]["main_wall_s"]}))


if __name__ == "__main__":
    main()
