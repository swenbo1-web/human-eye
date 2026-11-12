"""Independently decode five frozen engineering responses without product imports."""

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
BATCH = HERE.parents[1]
ROOT = BATCH.parents[1]
RUN = BATCH / "engineering/run_01"
QUAL = ROOT / "verification/m4_surface_scan_001/qualification"
SOURCE = "4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6"
LABELS = ("base_default", "base_brief", "base_full", "edit_default", "edit_full")
TRUTH_HASHES = {"BASE": "a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7",
                "EDIT": "ccbc66e4071dd3fc8f7fc4c7195e29a6a5a58db39fa1e0a86457b2a8929b1e91"}
SNAPSHOT_HASHES = {"BASE": "f8a578f78004a21e611c76d47506c5290f6015e7343e67b3b094a9e54da9884b",
                   "EDIT": "beb4e441b1898c6aedbe633828b1a93948f1d5be172ded9e1a884c8bdebffd80"}
SOURCES = {}
CHECKS = 0


def check(condition, reason):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(reason)


def read_bytes(path):
    data = path.read_bytes()
    SOURCES[path.relative_to(ROOT).as_posix()] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    return data


def read(path):
    return json.loads(read_bytes(path))


def exact(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def bits(value):
    return struct.pack(">d", value).hex()


def q(value):
    return Fraction(int(value["numerator"]), int(value["denominator"]))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def point_triangle_squared(point, triangle):
    """Exact plane projection and three segment bounds over rational coordinates."""
    a, b, c = triangle
    edge, other, offset = sub(b, a), sub(c, a), sub(point, a)
    uu, uv, vv = dot(edge, edge), dot(edge, other), dot(other, other)
    determinant = uu * vv - uv * uv
    candidates = []
    if determinant:
        du, dv = dot(offset, edge), dot(offset, other)
        u, v = (du * vv - dv * uv) / determinant, (dv * uu - du * uv) / determinant
        if u >= 0 and v >= 0 and u + v <= 1:
            residual = tuple(offset[i] - u * edge[i] - v * other[i] for i in range(3))
            candidates.append(dot(residual, residual))
    for start, end in ((a, b), (b, c), (c, a)):
        direction, relative = sub(end, start), sub(point, start)
        denominator = dot(direction, direction)
        t = min(Fraction(1), max(Fraction(0), dot(relative, direction) / denominator)) if denominator else Fraction(0)
        residual = tuple(relative[i] - t * direction[i] for i in range(3))
        candidates.append(dot(residual, residual))
    return min(candidates)


def decode(body):
    if "display_encoding" not in body:
        return body["matches"]
    check(body["display_encoding"] == "surface-scan-task-table-v1", "display revision")
    check(body["object_table_scope"] == "matched_endpoints_only", "endpoint table scope")
    columns = body["match_columns"]
    check(columns == ["object_a", "object_b", "object_a_ref", "object_b_ref", "distance_m", "distance_mm"], "columns")
    check(len({obj["id"] for obj in body["objects"]}) == len(body["objects"]), "table identity uniqueness")
    annotations = [dict(body["match_metadata"]) for _ in body["matches"]]
    seen = set()
    for row in body["match_exceptions"]:
        i = row["match_index"]
        check(type(i) is int and 0 <= i < len(annotations) and i not in seen, "metadata index")
        seen.add(i)
        annotations[i].update(row["metadata"])
    restored = []
    for index, values in enumerate(body["matches"]):
        check(len(values) == len(columns), "row length")
        row = dict(zip(columns, values))
        objects = []
        for name_key, ref_key in (("object_a", "object_a_ref"), ("object_b", "object_b_ref")):
            reference = row[ref_key]
            check(type(reference) is int and 0 <= reference < len(body["objects"]), "valid object index")
            obj = body["objects"][reference]
            check(obj["name"] == row[name_key], "readable endpoint identity")
            objects.append(obj)
        check(bits(row["distance_mm"]) == bits(row["distance_m"] * 1000), "derived mm conversion")
        restored.append(dict(objects=objects, distance_m=row["distance_m"], **annotations[index]))
    return restored


def ordered_facts(rows):
    return [(row["objects"], bits(row["distance_m"]),
             {k: value for k, value in row.items() if k not in ("objects", "distance_m", "point_a_world", "point_b_world")})
            for row in rows]


def main():
    truths, meshes = {}, {}
    for state in ("BASE", "EDIT"):
        path = QUAL / (state + "_TRUTH.json")
        truth = read(path)
        check(hashlib.sha256(path.read_bytes()).hexdigest() == TRUTH_HASHES[state], "frozen truth " + state)
        check(truth["snapshot_sha256"] == SNAPSHOT_HASHES[state], "truth snapshot binding")
        expected_snapshot = read(QUAL / (state + "_SNAPSHOT.json"))
        actual_snapshot = read(RUN / (state.lower() + "_ACTUAL_SNAPSHOT.json"))
        for key in (set(expected_snapshot) - {"blend_filepath", "pid"}):
            check(exact(expected_snapshot[key]) == exact(actual_snapshot[key]), "full actual snapshot " + state + " " + key)
        truths[state] = {tuple(sorted((row["object_a"], row["object_b"]))): row for row in truth["pairs"]}
        threshold2 = Fraction.from_float(.002) ** 2
        for pair, row in truths[state].items():
            check((q(row["exact_squared_distance_m2"]) <= threshold2) is row["matches_threshold"], "exact threshold membership")
        check(sum(row["matches_threshold"] for row in truths[state].values()) == (71 if state == "BASE" else 72), "truth match count")
        meshes[state] = {
            obj["name"]: [tuple(tuple(Fraction.from_float(component) for component in obj["vertices_world"][i])
                                       for i in face) for face in obj["triangles"]]
            for obj in actual_snapshot["objects"]
        }

    results = read(RUN / "RESULTS.json")
    check([row["state"] for row in results["business"]] == list(LABELS), "all five business rows")
    rpc_files = {}
    for path in sorted((RUN / "product").glob("[0-9][0-9][0-9]/TX.bin")):
        request = json.loads(read_bytes(path))
        response_path = path.with_name("RX.bin")
        if response_path.exists():
            rpc_files[request.get("id")] = (request, json.loads(read_bytes(response_path)))
    audit = [json.loads(line) for line in read_bytes(RUN / "audit.jsonl").splitlines()]
    private_observes = [row for row in audit if row.get("event") == "observe"]
    check(len(private_observes) == 5, "private observation denominator")
    packets, rows = {}, []
    tolerance = Fraction(1, 10**10)
    for index, label in enumerate(LABELS):
        receipt = read(RUN / (label + "_RESPONSE_RECEIPT.json"))
        raw_request, raw_response = rpc_files[label]
        check(raw_request == receipt["request"], "actual request binding " + label)
        check(raw_response == receipt["response"], "actual raw response binding " + label)
        check(raw_response["result"]["isError"] is False, "business result usable")
        text = raw_response["result"]["content"][0]["text"]
        body = json.loads(text)
        check(body == receipt["body"], "receipt body binding")
        check(len(text.encode("utf8")) == receipt["business_text_utf8_bytes"], "actual complete body bytes")
        state = receipt["truth_state"]
        match_rows = decode(body)
        packets[label] = (body, match_rows)
        check(body["status"] == "complete" and body["coverage"]["unknown"] == body["coverage"]["deferred"] == 0,
              "complete measured scope")
        check(body["scope_issues"] == body["unresolved"] == body["unsupported_objects"] == [], "no omitted unknowns")
        check(body["scope"] == "all_scene_mesh_triangle_surfaces" and body["unit"] == "m"
              and body["coordinate_frame"] == "world" and body["execution_authority"] is False, "scope and authority")
        check(body["binding"]["runtime_source_sha256"] == SOURCE, "candidate identity in actual response")
        check(body["delivery"]["matches_total"] == body["delivery"]["delivered_matches"] == len(match_rows)
              and body["delivery"]["complete"] is True, "full original delivery")
        check(body["coverage"]["objects"] == 24 and body["coverage"]["total_pairs"] == 276
              and body["coverage"]["catalog_scope_confirmed"] is True, "whole scene scope counts")
        check(sum(body["coverage"][name] for name in ("bound_excluded", "measured_match", "measured_nonmatch", "unknown", "deferred")) == 276,
              "complete coverage partition")
        check(body["coverage"]["measured_match"] == len(match_rows), "match coverage agrees with visible rows")
        actual_pairs = [tuple(sorted(obj["name"] for obj in row["objects"])) for row in match_rows]
        expected_pairs = {pair for pair, row in truths[state].items() if row["matches_threshold"]}
        check(len(set(actual_pairs)) == len(actual_pairs) and set(actual_pairs) == expected_pairs, "complete exact member set")
        private = private_observes[index]["task_work"]
        check(private["kernel_calls"] == [112, 0, 0, 10, 0][index], "new kernel count")
        private_distances = {tuple(row["object_ids"]): row["distance_m"] for row in private["dispositions"]
                             if row["status"] == "measured_match"}
        witness_points = 0
        for pair, row in zip(actual_pairs, match_rows):
            distance = row["distance_m"]
            check(type(distance) is float and math.isfinite(distance) and distance >= 0, "finite raw distance")
            exact_distance = Fraction.from_float(distance)
            squared = q(truths[state][pair]["exact_squared_distance_m2"])
            check(max(Fraction(0), exact_distance - tolerance)**2 <= squared <= (exact_distance + tolerance)**2,
                  "independent exact truth distance")
            ids = tuple(obj["id"] for obj in row["objects"])
            check(bits(distance) == bits(private_distances[ids]), "display raw measurement bits")
            if label.endswith("full"):
                check(row["witness_status"] == "measured" and row["method"] == "exact_binary64_triangle_surface_hulls_v3", "full witness metadata")
                points = []
                for endpoint, key in zip(row["objects"], ("point_a_world", "point_b_world")):
                    point = tuple(Fraction.from_float(component) for component in row[key])
                    check(any(point_triangle_squared(point, tri) <= tolerance**2 for tri in meshes[state][endpoint["name"]]),
                          "full witness on current triangle surface")
                    points.append(point)
                    witness_points += 1
                vector = sub(points[0], points[1])
                check(max(Fraction(0), exact_distance - tolerance)**2 <= dot(vector, vector) <= (exact_distance + tolerance)**2,
                      "full witness separation")
        if label.endswith("full"):
            check("display_encoding" not in body and all(type(row) is dict for row in body["matches"]), "old detailed shape")
            check(json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(",", ":")) == text, "old full serializer exact encoding")
        else:
            check(len(text.encode("utf8")) <= 10 * 1024, "compact full body budget")
        rows.append(dict(label=label, matches=len(match_rows), body_bytes=len(text.encode("utf8")),
                         raw_distance_bit_checks=len(match_rows), independent_truth_checks=len(match_rows),
                         full_surface_witness_points_verified=witness_points, binding=body["binding"],
                         trace_id=body["trace_id"]))

    for labels in (("base_default", "base_brief", "base_full"), ("edit_default", "edit_full")):
        full_body, full_rows = packets[labels[-1]]
        for label in labels[:-1]:
            compact, decoded = packets[label]
            check(ordered_facts(decoded) == ordered_facts(full_rows), "same-state original facts order and bits")
            for key, value in full_body.items():
                if key not in ("matches", "trace_id"):
                    check(exact(compact[key]) == exact(value), "same-state top-level " + key)
    base, edit = packets["base_full"][0], packets["edit_full"][0]
    old_consumer = read(ROOT / "verification/m4_surface_scan_consumption_001/cells/P1/CONSUMER.json")
    old_base = json.loads(old_consumer["tool_calls"][0]["item"]["result"]["content"][0]["text"])
    check({key for key in base} == {key for key in old_base}, "old detailed BASE keys")
    for key in set(old_base) - {"binding", "trace_id"}:
        check(exact(base[key]) == exact(old_base[key]), "old detailed BASE field " + key)
    for key in ("scene_revision", "scene_fingerprint", "directory_sha256"):
        check(base["binding"][key] != edit["binding"][key], "pose invalidates " + key)
    for key in ("document_epoch", "runtime_source_sha256", "host_source_sha256"):
        check(base["binding"][key] == edit["binding"][key], "preserved identity " + key)
    check(len({row["trace_id"] for row in rows}) == 5, "distinct current observations")
    record = dict(schema="surface_scan_compact_independent_engineering_quality_v1", status="pass", checks=CHECKS,
                  candidate_commit="452b44d2dcf231d6675bef54e568db0431a29261", candidate_source_sha256=SOURCE,
                  rows=rows, matched_rows_verified=sum(row["matches"] for row in rows),
                  new_Blender_product_model_API_runs=0, source_files=SOURCES,
                  witness_tolerance_m="1e-10", oracle="frozen exact binary64 rational truth; squared interval checks",
                  old_detailed_BASE_packet_equal_except_current_binding_and_trace=True,
                  limitations=["No new geometric all-pair oracle run, only frozen independent truth reused.",
                               "Current raw transport responses attest delivery to engineering controller, model input remains unmeasured.",
                               "Engineering quality does not establish token or complete model task benefit."])
    (HERE / "QUALITY_RESULT.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(dict(status=record["status"], checks=CHECKS, rows=5,
                         matched_rows=record["matched_rows_verified"], witnesses=sum(row["full_surface_witness_points_verified"] for row in rows),
                         body_bytes=[row["body_bytes"] for row in rows])))


if __name__ == "__main__":
    main()
