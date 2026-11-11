"""Independent standard-library checks over closed actual-entry records."""

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
ENTRY = BATCH / "entry/run_01"
FROZEN = ROOT / "verification/m4_observation_baseline_001/scoring/source/qual001/admin/world_geometry.json"


def read(path):
    return json.loads(path.read_bytes())


def oracle(row):
    records = [event["qa_work"]["native_supplement_work"]["independent_host_oracle"]
               for event in row["worker_received_events"]
               if event["qa_work"].get("native_supplement_work", {}).get("independent_host_oracle")]
    assert len(records) == 1
    return records[0]


def generation(row):
    hosts = row["worker_received_events"][0]["qa_work"]["after"]["hosts"]
    assert len(hosts) == 1
    return hosts[0]["generation"]


def exact_world(source):
    matrix = [[Fraction(value) for value in axis] for axis in source["matrix_world"]]
    scale = Fraction(source["unit_scale_m"])
    return [[float((sum(matrix[r][c] * Fraction(point[c]) for c in range(3))
                    + matrix[r][3]) * scale) for r in range(3)]
            for point in source["vertices_local"]]


def maximum_coordinate_error(left, right):
    assert len(left) == len(right)
    return max(abs(a - b) for pa, pb in zip(left, right, strict=True)
               for a, b in zip(pa, pb, strict=True))


def main():
    result = read(ENTRY / "RESULTS.json")
    assert result["passed"] and len(result["cases"]) == 7
    frozen = read(FROZEN)
    assert frozen["source_sha256"] == "91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85"
    originals = {item["name"]: item for item in frozen["objects"]}
    patch = read(BATCH / "entry/MUTATION_PATCH.json")
    records = []
    for case in result["cases"]:
        cold = case["rows"][0]
        initial_generation = generation(cold)
        bodies = [row for row in case["rows"] if row["kind"] == "relation"]
        for row in bodies:
            body = row["body"]
            assert body["target"]["name"] == "N16"
            assert [item["name"] for item in body["candidates"]] == ["N13", "N08", "N28"]
            assert body["context"]["selected_count"] == 4
            assert body["context"]["capture_scope"] == "selected_objects"
            assert body["context"]["unit"] == "m" and body["context"]["coordinate_frame"] == "world"
            assert [item["closed_solid_relation"]["value"] for item in body["candidates"]] == ["penetrating", "separated", "separated"]
            if not row["label"].startswith("changed_"):
                assert generation(row) == initial_generation
        for row in case["rows"]:
            if not row.get("oracle_retained"):
                continue
            changed = row["label"] == "changed_oracle"
            binding_row = next(item for item in bodies if item["label"] == "changed_full") if changed else cold
            identities = {item["name"]: item for item in
                          [binding_row["body"]["target"], *binding_row["body"]["candidates"]]}
            geometry = {item["name"]: item for item in row["geometry"]["objects"]}
            for source in oracle(row):
                name = source["name"]
                assert name in ("N16", "N28")
                assert source["instance_id"] == identities[name]["instance_id"]
                assert source["unit_scale_m"] == 1.0
                assert source["triangles"] == originals[name]["triangles"]
                assert geometry[name]["triangles"] == source["triangles"]
                expected_local = originals[name]["local_vertices"]
                if changed and name == patch["target_name"]:
                    expected_local = [list(point) for point in expected_local]
                    for vertex in patch["vertices"]:
                        expected_local[vertex["index"]] = vertex["co"]
                    assert source["data_users"] == [name]
                assert source["vertices_local"] == expected_local
                exact = exact_world(source)
                error = maximum_coordinate_error(exact, geometry[name]["vertices_world"])
                assert error <= 1e-14
                if not changed and not case["case"]["transformed"]:
                    assert source["matrix_world"] == originals[name]["matrix_world"]
                    assert maximum_coordinate_error(exact, originals[name]["world_vertices"]) <= 1e-14
                records.append({"case": case["case"]["id"], "oracle": row["label"], "name": name,
                                "vertices": len(exact), "triangles": len(source["triangles"]),
                                "fraction_world_max_error_m": error,
                                "instance_id_matches_independent_host": True})
        if case["case"]["mutation"]:
            changed_off = next(row for row in bodies if row["label"] == "changed_OFF")
            changed_full = next(row for row in bodies if row["label"] == "changed_full")
            current = generation(changed_off)
            assert current["instance_id"] == initial_generation["instance_id"]
            assert current["epoch"] == initial_generation["epoch"]
            assert current["revision"] > initial_generation["revision"]
            assert generation(changed_full) == current
            for key in ("scene_revision", "scene_fingerprint"):
                assert changed_off["body"]["context"][key] != cold["body"]["context"][key]
                assert changed_full["body"]["context"][key] == changed_off["body"]["context"][key]

    transformed = next(case for case in result["cases"] if case["case"]["transformed"])
    rigid = read(ENTRY / transformed["case"]["id"] / "native/QA_INITIAL_RIGID.json")
    mapping = [[0., -1., 0., .125], [1., 0., 0., -.25], [0., 0., 1., .5], [0., 0., 0., 1.]]
    assert rigid["matrix_left_multiply"] == mapping
    tolerance = rigid["coordinate_readback_tolerance_m"]
    assert tolerance == 1e-6
    matrix_error = 0.
    for name, before in rigid["before"].items():
        expected = [[sum(mapping[r][k] * before[k][c] for k in range(4))
                     for c in range(4)] for r in range(4)]
        error = maximum_coordinate_error(expected, rigid["after"][name])
        matrix_error = max(matrix_error, error)
        assert error <= tolerance
    rigid_world_error = 0.
    for item in transformed["rows"][0]["body"]["geometry"]["objects"]:
        expected = [[-y + .125, x - .25, z + .5]
                    for x, y, z in originals[item["name"]]["world_vertices"]]
        error = maximum_coordinate_error(expected, item["vertices_world"])
        rigid_world_error = max(rigid_world_error, error)
        assert error <= tolerance
    summary = {
        "passed": True, "asset_count": 1, "sessions": 7, "oracle_objects_checked": len(records),
        "records": records, "known_rigid_objects": len(rigid["before"]),
        "known_rigid_matrix_max_error": matrix_error,
        "known_rigid_world_max_error_m": rigid_world_error, "rigid_tolerance_m": tolerance,
        "source_generation_invalidates_old_geometry_and_relation": True,
        "method": "Independent retained host local coordinates, matrices, units and actual loop triangles; Fraction forward transform and frozen asset cross-check.",
        "entry_results_sha256": hashlib.sha256((ENTRY / "RESULTS.json").read_bytes()).hexdigest(),
        "frozen_geometry_sha256": hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
        "new_product_or_Blender_requests": 0,
    }
    with (HERE / "RESULTS.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(summary, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({key: summary[key] for key in ("passed", "sessions", "oracle_objects_checked", "known_rigid_world_max_error_m")}))


if __name__ == "__main__":
    main()
