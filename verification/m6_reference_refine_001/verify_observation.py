"""Independent edge-section checks and actual read-only focus correspondence."""

import importlib.util
from pathlib import Path
import sys
import time
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import read, write, identity
import numpy as np


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def main():
    started, cpu = time.perf_counter(), time.process_time()
    observation = read("OBSERVATION.json")
    annotation = read("ANNOTATION_DRAFT.json")
    with np.load(HERE / "private/cases/s01/observation.npz", allow_pickle=False) as source:
        arrays = {key:source[key] for key in source.files}
    with np.load(HERE / "private/cases/s01/baseline_readback.npz", allow_pickle=False) as source:
        baseline = {key:source[key] for key in source.files}
    vertices, faces, F = arrays["vertices"], arrays["faces"], arrays["F_source_ids"]
    projection = annotation["source_projection"]
    pixels = vertices @ np.asarray(projection["affine_2_by_3"]).T + projection["offset"]
    E, W = (np.array(observation["primary_anchors"]["model"][key]) for key in ("E", "W"))
    length = float(np.linalg.norm(W-E))
    tangent = (W-E)/length
    outward = np.array([tangent[1], -tangent[0]])
    axial = (pixels-E) @ tangent / length
    radial = (pixels-E) @ outward / length
    chosen_faces = faces[np.isin(faces,F).all(axis=1)]
    edges = np.unique(np.sort(np.concatenate((chosen_faces[:,[0,1]],chosen_faces[:,[1,2]],chosen_faces[:,[2,0]])),axis=1),axis=0)
    checks, measured = {}, []
    for row in observation["primary_stations"]:
        station = row["t"]
        a, b = edges[:,0], edges[:,1]
        crossing = (np.minimum(axial[a],axial[b]) <= station) & (np.maximum(axial[a],axial[b]) >= station) & (axial[a] != axial[b])
        a, b = a[crossing], b[crossing]
        fraction = (station-axial[a])/(axial[b]-axial[a])
        values = radial[a] + fraction*(radial[b]-radial[a])
        outer, inner = float(values.max()), float(values.min())
        checks["independent_outer_"+str(station)] = abs(outer-row["model_outer"]) < 1e-10
        checks["independent_width_"+str(station)] = abs(outer-inner-row["model_width"]) < 1e-10
        measured.append(dict(t=station, outer=outer, inner=inner, width=outer-inner, intersected_forearm_edges=len(values)))
    for key in ("vertices", "vertices_local", "matrix_world", "source_ids", "faces", "poly_offsets", "poly_vertices"):
        checks["observation_baseline_bitwise_"+key] = arrays[key].dtype == baseline[key].dtype and arrays[key].shape == baseline[key].shape and arrays[key].tobytes() == baseline[key].tobytes()
    checks["zero_editable_points"] = len(arrays["I_ids"]) == 0
    checks["all_source_points_protected"] = np.array_equal(arrays["protected_ids"], np.arange(len(vertices)))
    checks["no_edited_geometry"] = bool(np.array_equal(arrays["vertices_local"], baseline["vertices_local"]))
    input_binding = read("INPUT_BINDING.json")
    checks["original_art_bytes_preserved"] = identity(Path(input_binding["inputs"][0]["path"]))["sha256"] == input_binding["inputs"][0]["sha256"]
    checks["model_copy_matches_contract"] = identity(HERE / "private/results/corresponding_model.blend")["sha256"] == "614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d"
    facts_directory = HERE / "private/observation_facts"
    facts_directory.mkdir(parents=True, exist_ok=False)
    packet = facts_directory / "g.npz"
    np.savez_compressed(packet, vertices=vertices, faces=faces, F_source_ids=F)
    write(facts_directory / "INPUT_INDEX.json", dict(cases=[dict(alias="forearm_observed",input=dict(path="g.npz",sha256=identity(packet)["sha256"]))]))
    interfaces = module("_reference_readonly_focus", HERE.parent / "m6_task_perception_001/interfaces.py")
    prototype = interfaces.TaskPerception(facts_directory)
    focus = prototype.focus("forearm_observed", F, F, request="Observe the explicitly corresponding forearm, with all source vertices protected under the annotation-uncertainty branch.")
    resolved = prototype.resolve(focus["target"]["reference"], include_geometry=True)
    checks["actual_focus_target_source_ids"] = resolved["source_ids"] == F.tolist()
    checks["actual_focus_positions"] = np.array_equal(np.asarray(resolved["current_positions_native"]), vertices[F])
    # The reused primitive names its input coordinate space native. This packet
    # contains the actual saved object's world coordinates and has that binding.
    coordinate_binding = dict(coordinate_space="Blender_world", unit="m", packet=identity(packet), all_source_vertices_protected=True,
        editable_source_ids=[], source_coordinate_note="positions supplied to reused geometry facts are independently exported world coordinates")
    write(facts_directory / "FOCUS.json", dict(result=focus, coordinate_binding=coordinate_binding))
    write(facts_directory / "RESOLVED_TARGET.json", dict(result=resolved, coordinate_binding=coordinate_binding))
    write("private/annotation/INDEPENDENT_EDGE_MEASUREMENTS.json", measured)
    report = dict(status="pass" if all(checks.values()) else "fail", checks=checks, passed=sum(checks.values()), total=len(checks),
        actual_focus_calls=1, actual_resolve_calls=1, network_model_inferences=0, actual_Pro_sessions=0,
        changed_vertices=0, affected_faces=0, new_intersection_status="geometry byte identity, no changed affected domain",
        wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu,
        used_source_id_count=len(F), independent_method="Cut all edges of the connected source forearm region at fixed EW stations and compare global radial extrema to triangle-union projection measurements",
        private_evidence=[identity(facts_directory / "FOCUS.json"),identity(facts_directory / "RESOLVED_TARGET.json"),identity(HERE / "private/annotation/INDEPENDENT_EDGE_MEASUREMENTS.json")])
    write("OBSERVATION_VERIFICATION.json",report)
    print(report["status"],report["passed"],report["total"])
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
