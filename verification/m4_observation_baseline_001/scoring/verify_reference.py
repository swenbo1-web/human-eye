"""Replay historical independent geometry certificates without any product.

Only pure functions from byte-pinned historical QA are executed. Their mains
are not called: QUAL001's old nearest-rail target rule is expressly superseded
by QUAL002's three public predicates. No Blender/image/model is started.
"""
from collections import defaultdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import time
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
OLD2 = Path("D:/hefe/verification/fixes/20261103_spatial_perception_qual002")
OLD1 = OLD2.parent / "20261103_spatial_perception_qual001"
sha = lambda raw: hashlib.sha256(raw).hexdigest()
SOURCES = (
    (OLD2, "admin/INPUT_FREEZE.json", "qual002/admin/INPUT_FREEZE.json"),
    (OLD2, "admin/PROPOSED_PROTOCOL.json", "qual002/admin/PROPOSED_PROTOCOL.json"),
    (OLD2, "admin/offline_scorer.py", "qual002/admin/offline_scorer.py"),
    (OLD2, "oracle/ORACLE_PRIVATE.json", "qual002/oracle/ORACLE_PRIVATE.json"),
    (OLD2, "oracle/TARGET_CANDIDATE_CERTIFICATE.json", "qual002/oracle/TARGET_CANDIDATE_CERTIFICATE.json"),
    (OLD2, "oracle/target_definition.py", "qual002/oracle/target_definition.py"),
    (OLD1, "oracle/CERTIFICATES_PRIVATE.json", "qual001/oracle/CERTIFICATES_PRIVATE.json"),
    (OLD1, "oracle/certify.py", "qual001/oracle/certify.py"),
    (OLD1, "admin/world_geometry.json", "qual001/admin/world_geometry.json"),
)


def put(path, value, raw=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = value if raw else (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(blob)


def exact(value):
    return F(int(value["numerator"]), int(value["denominator"]))


def module(name, path, blob):
    result = types.ModuleType(name)
    result.__file__ = str(path)
    exec(compile(blob, str(path), "exec", dont_inherit=True), result.__dict__)
    return result


def main():
    started = time.perf_counter_ns()
    deadline = started + 60 * 10**9
    raw = {new: (home / old).read_bytes() for home, old, new in SOURCES}
    freeze = json.loads(raw["qual002/admin/INPUT_FREEZE.json"])
    target_cert = json.loads(raw["qual002/oracle/TARGET_CANDIDATE_CERTIFICATE.json"])
    pair_cert = json.loads(raw["qual001/oracle/CERTIFICATES_PRIVATE.json"])
    old_oracle = json.loads(raw["qual002/oracle/ORACLE_PRIVATE.json"])
    assert sha(raw["qual002/oracle/ORACLE_PRIVATE.json"]) == freeze["oracle_bindings"]["ORACLE_PRIVATE.json"]
    assert sha(raw["qual002/oracle/TARGET_CANDIDATE_CERTIFICATE.json"]) == freeze["oracle_bindings"]["TARGET_CANDIDATE_CERTIFICATE.json"]
    assert sha(raw["qual001/oracle/CERTIFICATES_PRIVATE.json"]) == freeze["oracle_bindings"]["previous_exact_geometry_certificate"]
    assert sha(raw["qual001/admin/world_geometry.json"]) == pair_cert["world_geometry_sha256"] == target_cert["source"]["world_geometry_sha256"]
    assert sha(raw["qual001/oracle/certify.py"]) == pair_cert["oracle_source_sha256"]
    assert sha(raw["qual002/oracle/target_definition.py"]) == target_cert["source"]["oracle_implementation_sha256"]
    assert sha((ROOT / "input/scene.blend").read_bytes()) == old_oracle["source_binding"]["scene_sha256"]
    for name, blob in raw.items():
        put(ROOT / "scoring/source" / name, blob, raw=True)
    put(ROOT / "scoring/SOURCE_BINDING.json", {"schema": "M4-independent-reference-source-binding-v1",
        "before_geometry_replay": True, "own_script_sha256": sha(Path(__file__).read_bytes()),
        "files": [{"path": "scoring/source/" + name, "sha256": sha(blob), "bytes": len(blob)} for name, blob in raw.items()],
        "old_target_rule_not_reused": "QUAL001 target_uniqueness used nearest-rail ranking and is not the current task; only its geometry/pair certificates are reused",
        "geometry_replay_kind": "historical independent QA pure functions, not a second independent algorithm and not a product source"})
    qa = module("historical_exact_geometry_functions", ROOT / "scoring/source/qual001/oracle/certify.py", raw["qual001/oracle/certify.py"])
    predicates = module("historical_public_predicate_functions", ROOT / "scoring/source/qual002/oracle/target_definition.py", raw["qual002/oracle/target_definition.py"])
    geometry = json.loads(raw["qual001/admin/world_geometry.json"])
    assert geometry["source_sha256"] == old_oracle["source_binding"]["scene_sha256"]
    rows = geometry["objects"]
    by_id = {row["object_id"]: row for row in rows}
    catalog = json.loads((ROOT / "input/CATALOG.json").read_bytes())
    assert len(rows) == len(by_id) == 28 and set(by_id) == {row["object_id"] for row in catalog["objects"]}
    groups = defaultdict(list)
    for row in rows:
        row["_vertices"] = [tuple(F(value) for value in point) for point in row["world_vertices"]]
        row["_bounds"] = [(min(point[axis] for point in row["_vertices"]), max(point[axis] for point in row["_vertices"])) for axis in range(3)]
        row["_center"] = tuple((a + b) / 2 for a, b in row["_bounds"])
        groups[row["data"]].append(row)
    frame_groups = [group for group in groups.values() if len(group) == 4 and all(predicates.hollow_profile(row, 1) for row in group)]
    rail_groups = [group for group in groups.values() if len(group) == 2 and all(predicates.hollow_profile(row, 0) for row in group)]
    assert len(frame_groups) == len(rail_groups) == 1
    frames = frame_groups[0]
    assert len({predicates.shape_commit(row) for row in frames}) == 1
    rails = sorted(rail_groups[0], key=lambda row: row["_center"][2])
    meshes = {identifier: qa.object_mesh(row) for identifier, row in by_id.items()}
    beams, pipes, convex = [], [], []
    for row in rows:
        widths = [b - a for a, b in row["_bounds"]]
        levels = [len({point[axis] for point in row["_vertices"]}) for axis in range(3)]
        if levels == [2, 2, 2] and len(row["_vertices"]) == 8 and len(row["triangles"]) == 12 and widths[0] >= 10 * max(widths[1:]):
            qa.manifold(meshes[row["object_id"]]); beams.append(row)
        if levels[2] == 2 and widths[2] > 4 * max(widths[:2]):
            caps = [{(p[0], p[1]) for p in row["_vertices"] if p[2] == level} for level in sorted({p[2] for p in row["_vertices"]})]
            if len(caps[0]) == 12 and caps[0] == caps[1]:
                radii = [(x - row["_center"][0])**2 + (y - row["_center"][1])**2 for x, y in caps[0]]
                if min(radii) > 0 and max(radii) <= min(radii) * F(101, 100):
                    qa.manifold(meshes[row["object_id"]]); pipes.append(row)
        try:
            convex.append(qa.certify_convex_extrusion(meshes[row["object_id"]]))
        except ValueError:
            pass
    assert len(beams) == len(pipes) == 2
    beam = min(beams, key=lambda row: row["_center"][1])
    middle_z = sum(row["_center"][2] for row in rails) / 2
    rear_y = beam["_bounds"][1][1]
    pipe_mid = tuple(sum(row["_center"][axis] for row in pipes) / 2 for axis in (0, 1))
    constants = target_cert["predicate_constants"]
    assert middle_z == exact(constants["lower_upper_rail_Z_midplane_m"])
    assert rear_y == exact(constants["front_crossbeam_rear_surface_Y_m"])
    assert pipe_mid == tuple(map(exact, constants["dual_pipe_axis_XY_midpoint_m"]))
    evaluations, pass_sets = [], [set(), set(), set()]
    for row in sorted(frames, key=lambda row: row["object_id"]):
        center = row["_center"]
        distance2 = sum((center[axis] - pipe_mid[axis])**2 for axis in (0, 1))
        flags = [center[2] < middle_z, center[1] > rear_y, distance2 <= F(7, 10)**2]
        for index, flag in enumerate(flags):
            if flag: pass_sets[index].add(row["object_id"])
        evaluations.append({"object_id": row["object_id"], "three_conditions": flags,
            "center_world_m": list(map(float, center)), "pipe_XY_distance_squared_fraction_m2": str(distance2)})
    selected = set.intersection(*pass_sets)
    assert selected == set(target_cert["full_intersection"]) and len(selected) == 1
    assert all(len(set.intersection(*(pass_sets[j] for j in range(3) if j != i))) == 2 for i in range(3))
    target_id = next(iter(selected))
    target = qa.certify_ring(meshes[target_id])
    bounds, center = by_id[target_id]["_bounds"], by_id[target_id]["_center"]
    width, height = bounds[0][1] - bounds[0][0], bounds[2][1] - bounds[2][0]
    short = [item for item in convex if len(item["polygon"]) == 4
        and item["mesh"]["bounds"][0][1] - item["mesh"]["bounds"][0][0] < width / 2
        and (item["mesh"]["bounds"][0][1] - item["mesh"]["bounds"][0][0]) * F(3, 2) < item["mesh"]["bounds"][2][1] - item["mesh"]["bounds"][2][0] < height
        and max(item["interval"][0], bounds[1][0]) < min(item["interval"][1], bounds[1][1])
        and bounds[2][0] < qa.midpoint(item["mesh"]["bounds"])[2] < bounds[2][1]
        and abs(qa.midpoint(item["mesh"]["bounds"])[0] - center[0]) < width]
    right = [item for item in short if qa.midpoint(item["mesh"]["bounds"])[0] > center[0]]
    left = [item for item in short if qa.midpoint(item["mesh"]["bounds"])[0] < bounds[0][0]]
    xl, yl, zl = target["levels"]
    probe = [item for item in convex if len(item["polygon"]) == 12 and item["interval"][0] < yl[0] and item["interval"][1] > yl[1]
             and all(xl[1] < point[0] < xl[2] and zl[1] < point[1] < zl[2] for point in item["polygon"])]
    assert len(right) == len(left) == len(probe) == 1
    roles = [("near_right_upright_separator", right[0]), ("left_short_locator_block", left[0]), ("through_opening_probe_rod", probe[0])]
    relations = []
    for role, neighbor in roles:
        result = qa.relation(target, neighbor)
        result["neighbor_role"] = role
        old = next(item for item in pair_cert["relations"] if item["neighbor_role"] == role)
        assert result == old
        if result["strict_interior_witness"] is None:
            candidates = []
            for cell in target["cells"]:
                candidates.extend(qa.segment_distance2(a, b, c, d) for a, b in zip(cell, cell[1:] + cell[:1]) for c, d in zip(neighbor["polygon"], neighbor["polygon"][1:] + neighbor["polygon"][:1]))
            _, a, b = min(candidates, key=lambda item: item[0])
            y = (max(yl[0], neighbor["interval"][0]) + min(yl[1], neighbor["interval"][1])) / 2
            points = [(a[0], y, a[1]), (b[0], y, b[1])]
            for mesh, point in ((target["mesh"], points[0]), (neighbor["mesh"], points[1])):
                assert any(qa.point_on_triangle(point, [mesh["vertices"][i] for i in face]) for face in mesh["triangles"])
            assert qa.dot(qa.sub(*points), qa.sub(*points)) == exact(result["minimum_distance_squared_m2"])
            result["attaining_original_surface_witness_points_world_m"] = [list(map(float, point)) for point in points]
        relations.append(result)
    assert all((home / old).read_bytes() == raw[new] for home, old, new in SOURCES)
    assert time.perf_counter_ns() < deadline
    assert not any(name.startswith(("human_eye_plugin", "human_eye_module1_operators")) for name in sys.modules)
    truth = {"schema": "M4-observation-independent-truth-v1", "cycle_id": "M4-OBSERVATION-BASELINE-001",
        "source_scene_sha256": geometry["source_sha256"], "source_world_geometry_sha256": sha(raw["qual001/admin/world_geometry.json"]),
        "target_id": target_id, "candidate_evaluations": evaluations, "target_predicate_reference_ids": {
            "lower_rail": rails[0]["object_id"], "upper_rail": rails[1]["object_id"], "front_beam": beam["object_id"], "pipes": [row["object_id"] for row in pipes]},
        "relations": relations, "contact_tolerance_m": 0.00025,
        "method": "pure historical independent Fraction boundary/prism/ray certificates replayed, target selected only by QUAL002 public predicates",
        "not_a_second_independent_algorithm": True,
        "current_Blender_reexport": "not performed by this input/scoring subtask; root's read-only preflight must bind actual copy geometry to frozen source",
        "new_assets": 0, "new_images": 0, "product_calls": 0, "model_consumers": 0}
    put(ROOT / "scoring/TRUTH.json", truth)
    put(ROOT / "scoring/REFERENCE_REPLAY.json", {"passed": True, "source_hashes_checked": True,
        "all_original_sources_unchanged": True, "target_conjunction_unique": True,
        "all_three_predicates_necessary": True, "three_roles_unique": True, "relations_match_original_exact_certificates": True,
        "strict_common_interior_witness_original_ray_checked": True, "separated_witnesses_on_original_triangles": True,
        "elapsed_ns": time.perf_counter_ns() - started, "original_deadline_ns": deadline,
        "new_assets": 0, "new_images": 0, "product_calls": 0, "model_consumers": 0})
    assert time.perf_counter_ns() < deadline
    print(json.dumps({"passed": True, "target_id": target_id, "roles": [{"id": row["neighbor_id"], "relation": row["classification"]} for row in relations]}))


if __name__ == "__main__":
    main()
