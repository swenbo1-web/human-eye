"""Saved-asset-only qualification. All geometry comes from actual world points."""

from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import math
import struct
import time
import traceback

from exact_geometry import (
    add, audit_body, blend, cross, dot, hull_planes, point_in_solid,
    polygon_membership, root_interval, scale, sub, triangle_distance,
    triangle_intersection,
)


OUT = Path(__file__).resolve().parent
BATCH = OUT.parent
NAMES = ("Target", "Part_A", "Part_B", "Part_C")
SOURCE_FILES = [
    BATCH / "spec" / "PLAN.md", BATCH / "spec" / "DESIGN.md", BATCH / "FREEZE.json",
    BATCH / "asset" / "ACTUAL_SNAPSHOT.json", BATCH / "asset" / "grooved_rail.blend",
    BATCH / "asset" / "build_assets.py", BATCH / "asset" / "export_snapshot.py",
    OUT / "exact_geometry.py", Path(__file__),
]


def frozen_local_design():
    """Reconstruct the frozen private specification without loading asset code."""
    contour = [(F(x), F(z)) for x, z in (("0", "0"), ("40", "0"), ("22.4", "13.2"),
                                        ("14", "2"), ("1.2", "11.6"), ("9.6", "22.8"), ("0", "30"))]
    points = {"Target": [(x, F(y), z) for y in (-20, 20) for x, z in contour]}
    cap = [(0, 1, 3), (1, 2, 3), (0, 3, 4), (0, 4, 6), (4, 5, 6)]
    target_faces = cap + [tuple(i + 7 for i in reversed(face)) for face in cap]
    for i in range(7):
        j = (i + 1) % 7
        target_faces.extend(((i, i + 7, j + 7), (i, j + 7, j)))
    points["Part_A"] = [
        ((4 * F(s) + 3 * F(h)) / 5, F(y), (-3 * F(s) + 4 * F(h)) / 5)
        for s, y, h in (("2", "2", "15.25"), ("0", "-2", "20.25"),
                        ("4", "-2", "20.25"), ("2", "8", "20.25"))
    ]
    normal, tangent = (F(-3, 5), F(0), F(-4, 5)), (F(4, 5), F(0), F(-3, 5))
    q = add((F(0), F(5), F(0)), scale(normal, F(11, 4)))
    points["Part_B"] = [add(q, scale(tangent, F(sign * 6))) for sign in (1, -1)]
    points["Part_B"] += [
        add(add(q, scale(normal, F(8))), (F(0), F(sign * 6), F(0))) for sign in (1, -1)
    ]
    points["Part_C"] = [tuple(F(v) for v in row) for row in (
        ("10", "28.5", "2"), ("16", "36.5", "-2"), ("4", "36.5", "-2"), ("10", "36.5", "10"))]
    faces = {"Target": target_faces}
    for name in NAMES[1:]:
        a, b, c, d = points[name]
        determinant = dot(sub(b, a), cross(sub(c, a), sub(d, a)))
        tetra = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
        faces[name] = tetra if determinant > 0 else [tuple(reversed(t)) for t in tetra]
    return points, faces


def binary32(value):
    return struct.unpack("f", struct.pack("f", float(value)))[0]


def cyclic(face):
    face = tuple(face)
    return min(face, face[1:] + face[:1], face[2:] + face[:2])


def validate_input(snapshot):
    objects = {o["name"]: o for o in snapshot["objects"]}
    expected_points, expected_faces = frozen_local_design()
    checks, residuals = [], []

    def check(name, passed, detail=None):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    check("exact_object_names", set(objects) == set(NAMES) and len(snapshot["objects"]) == 4)
    check("metres_world_local_millimetres", snapshot["unit"] == "m"
          and snapshot["coordinate_frame"] == "world" and snapshot["local_coordinate_unit"] == "mm"
          and snapshot["scale_length"] == snapshot["unit_scale_m"] == 1)
    matrices = []
    for name in NAMES:
        obj = objects[name]
        matrix = obj["matrix_world"]
        matrices.append(matrix)
        expected = [[binary32(x) for x in v] for v in expected_points[name]]
        check(name + ".frozen_local_binary32", obj["vertices_local"] == expected)
        check(name + ".frozen_oriented_triangles", Counter(cyclic(t) for t in obj["triangles"])
              == Counter(cyclic(t) for t in expected_faces[name]))
        check(name + ".complete_faces_equal_triangles", obj["faces"] == obj["triangles"])
        check(name + ".static_explicit_mesh", obj["type"] == "MESH" and not obj["modifiers"]
              and not obj["constraints"] and not obj["animation_present"]
              and not obj["shape_keys_present"] and obj["parent"] is None)
        check(name + ".no_answer_attributes", not obj["object_custom_properties"]
              and not obj["mesh_custom_properties"] and not obj["material_names"])
        recomputed = [
            [((matrix[r][0] * p[0] + matrix[r][1] * p[1]) + matrix[r][2] * p[2]) + matrix[r][3]
             for r in range(3)] for p in obj["vertices_local"]
        ]
        check(name + ".actual_world_binary64_evaluation", recomputed == obj["vertices_world"])
        residual = max(
            abs(F(world[r]) - (sum((F(matrix[r][c]) * F(local[c]) for c in range(3)), F(0))
                               + F(matrix[r][3])))
            for local, world in zip(obj["vertices_local"], obj["vertices_world"], strict=True)
            for r in range(3)
        )
        residuals.append({"object": name, "max_binary64_evaluation_residual_m": residual})
    check("shared_actual_matrix", all(m == matrices[0] for m in matrices))
    matrix = matrices[0]
    ideal = ((-10, 2, 11), (10, -5, 10), (5, 14, 2))
    linear_error = max(abs(F(matrix[r][c]) - F(ideal[r][c], 15000)) for r in range(3) for c in range(3))
    translation_error = max(abs(F(matrix[r][3]) - F((120, -80, 240)[r], 1000)) for r in range(3))
    check("fixed_pose_binary32_representation", linear_error < F(1, 10**9)
          and translation_error < F(1, 10**7) and matrix[3] == [0, 0, 0, 1],
          {"actual_linear_max_error": linear_error, "actual_translation_max_error_m": translation_error,
           "representation_check_bounds": [F(1, 10**9), F(1, 10**7)],
           "bounds_used_for_geometry": False})
    check("actual_26_vertices_36_triangles", sum(len(o["vertices_world"]) for o in objects.values()) == 26
          and sum(len(o["triangles"]) for o in objects.values()) == 36)
    return objects, checks, residuals


def crosscheck_features(objects, vertices, pairs):
    local = [tuple(F(v) for v in p) for p in objects["Target"]["vertices_local"]]
    polygon = [(v[0], v[2]) for v in local[:7]]
    groove = [polygon[i] for i in (2, 3, 4, 5)]
    section = [
        {"vertex_id": i, "actual_local_mm": p,
         "material_polygon": polygon_membership((p[0], p[2]), polygon),
         "groove_polygon": polygon_membership((p[0], p[2]), groove),
         "strictly_between_caps": local[0][1] < p[1] < local[7][1]}
        for i, row in enumerate(objects["Part_A"]["vertices_local"])
        for p in [tuple(F(v) for v in row)]
    ]
    planes = hull_planes(vertices["Target"])
    for plane in planes:
        normal, offset = plane["outward_plane_integer"][:3], plane["outward_plane_integer"][3]
        values = [dot(normal, point) + offset for point in vertices["Part_A"]]
        plane["Part_A_vertex_values"] = values
        plane["all_A_vertices_strictly_inside"] = max(values) < 0
    features, selected = {}, {}
    for name in NAMES[1:]:
        matches = []
        for witness in pairs[name]["global_minimum_candidates"]:
            ta, tb = witness["target_vertex_ids"], witness["candidate_vertex_ids"]
            ba, bb = witness["barycentric_target"], witness["barycentric_candidate"]
            candidate_ids = [tb[i] for i, weight in enumerate(bb) if weight]
            target_ids = [ta[i] for i, weight in enumerate(ba) if weight]
            if name == "Part_A":
                match = candidate_ids == [0] and min(ba) > 0 and set(ta) <= {3, 4, 10, 11}
            elif name == "Part_B":
                match = (witness["kind"] == "nonparallel_edge_interiors"
                         and set(target_ids) == {0, 7} and set(candidate_ids) == {0, 1}
                         and 0 < witness["parameters"]["target_parameter"] < 1
                         and 0 < witness["parameters"]["candidate_parameter"] < 1)
            else:
                match = candidate_ids == [0] and min(ba) > 0 and all(i >= 7 for i in ta)
            if match:
                matches.append(witness)
        features[name] = {"passed": bool(matches), "matching_global_minimum_count": len(matches)}
        if matches:
            witness = matches[0]
            selected[name] = witness
            point = blend([local[v] for v in witness["target_vertex_ids"]], witness["barycentric_target"])
            features[name]["target_actual_local_mm_from_barycentrics"] = point
            features[name]["actual_xz_material_membership"] = polygon_membership((point[0], point[2]), polygon)
            if name == "Part_C":
                features[name]["passed"] &= (features[name]["actual_xz_material_membership"] == "inside"
                                             and point[1] == local[7][1])
    return {
        "A_actual_section": {
            "passed": all(p["material_polygon"] == "outside" and p["groove_polygon"] == "inside"
                          and p["strictly_between_caps"] for p in section),
            "vertices": section,
            "scope": "Actual local contour cross-check. Primary material classification uses actual-world rational ray parity.",
        },
        "A_inside_actual_Target_convex_hull": {
            "passed": all(p["all_A_vertices_strictly_inside"] for p in planes),
            "support_triplets_examined": math.comb(14, 3), "outward_planes": planes,
        },
        "nearest_features": features,
    }, selected


def algorithm_checks():
    def points(rows):
        return [tuple(F(v) for v in row) for row in rows]

    base = points(((0, 0, 0), (4, 0, 0), (0, 4, 0)))
    checks = [
        {"check": "coplanar_nested_triangles", "passed": len(triangle_intersection(
            base, points(((1, 1, 0), (2, 1, 0), (1, 2, 0))))) == 3},
        {"check": "coplanar_disjoint", "passed": not triangle_intersection(
            base, points(((5, 5, 0), (6, 5, 0), (5, 6, 0))))},
        {"check": "noncoplanar_crossing", "passed": bool(triangle_intersection(
            base, points(((1, 1, -1), (1, 1, 1), (2, 1, 0)))))},
        {"check": "parallel_separated", "passed": not triangle_intersection(
            base, points(((0, 0, 1), (4, 0, 1), (0, 4, 1))))},
    ]
    face = triangle_distance(base, points(((1, 1, 2), (2, 1, 3), (1, 2, 3))), [])
    checks.append({"check": "vertex_face_square_4", "passed": face["squared_distance_m2"] == 4})
    left = points(((-2, 0, 0), (2, 0, 0), (0, -3, -3)))
    right = points(((0, -2, 1), (0, 2, 1), (3, 0, 4)))
    edge = triangle_distance(left, right, triangle_intersection(left, right))
    checks.append({"check": "skew_edge_interiors_square_1",
                   "passed": edge["squared_distance_m2"] == 1
                   and any(w["kind"] == "nonparallel_edge_interiors" for w in edge["minimum_candidates"])})
    tetra = points(((0, 0, 0), (4, 0, 0), (0, 4, 0), (0, 0, 4)))
    faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    for point, status in [((1, 1, 1), "inside"), ((5, 5, 5), "outside"), ((0, 0, 0), "boundary")]:
        checks.append({"check": "tetra_ray_" + status, "passed": point_in_solid(
            tuple(F(v) for v in point), tetra, faces)["status"] == status})
    bound = root_interval(F(2))
    checks.append({"check": "irrational_root_exact_bound",
                   "passed": bound["lower_exact_m"] ** 2 < 2 < bound["upper_exact_m"] ** 2})
    return checks


def solve_pairs(vertices, faces):
    pairs = {}
    for name in NAMES[1:]:
        certificates, all_global, contacts_all = [], [], []
        minimum = None
        for ti, target_face in enumerate(faces["Target"]):
            left = [vertices["Target"][v] for v in target_face]
            for ci, candidate_face in enumerate(faces[name]):
                right = [vertices[name][v] for v in candidate_face]
                contacts = triangle_intersection(left, right)
                distance = triangle_distance(left, right, contacts)
                for witness in distance["minimum_candidates"]:
                    witness.update({"target_triangle_id": ti, "candidate_triangle_id": ci,
                                    "target_vertex_ids": target_face, "candidate_vertex_ids": candidate_face})
                if minimum is None or distance["squared_distance_m2"] < minimum:
                    minimum, all_global = distance["squared_distance_m2"], list(distance["minimum_candidates"])
                elif distance["squared_distance_m2"] == minimum:
                    all_global.extend(distance["minimum_candidates"])
                certificates.append({"target_triangle_id": ti, "candidate_triangle_id": ci,
                                     "intersection_endpoints": contacts, **distance})
                if contacts:
                    contacts_all.append({"target_triangle_id": ti, "candidate_triangle_id": ci, "points": contacts})
        target_in_candidate = [
            {"query_vertex_id": i, **point_in_solid(p, vertices[name], faces[name])}
            for i, p in enumerate(vertices["Target"])
        ]
        candidate_in_target = [
            {"query_vertex_id": i, **point_in_solid(p, vertices["Target"], faces["Target"])}
            for i, p in enumerate(vertices[name])
        ]
        contained = any(p["status"] == "inside" for p in target_in_candidate + candidate_in_target)
        relation = "boundary_intersection" if contacts_all else "containment" if contained else "separated"
        pairs[name] = {
            "target": "Target", "candidate": name, "solid_relation": relation,
            "triangle_pairs_checked": len(certificates), "triangle_pair_certificates": certificates,
            "boundary_intersections": contacts_all,
            "target_vertices_in_candidate_ray_parity": target_in_candidate,
            "candidate_vertices_in_target_ray_parity": candidate_in_target,
            "exact_squared_distance_m2": minimum, "sqrt_interval": root_interval(minimum),
            "global_minimum_candidates": all_global, "at_least_4mm": minimum >= F("0.004") ** 2,
        }
    return pairs


def encode(value):
    if isinstance(value, F):
        return {"numerator": str(value.numerator), "denominator": str(value.denominator)}
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [encode(v) for v in value]
    return value


def manifest():
    return [{"path": p.resolve().as_posix(), "bytes": p.stat().st_size,
             "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in SOURCE_FILES]


def publish(result):
    truth_path = OUT / "TRUTH.json"
    truth_path.write_text(json.dumps(encode(result), ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "SOURCES.json").write_text(json.dumps({"files": result.get("source_manifest", manifest())},
                                               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# 凹槽导轨资产的独立资格核验", "",
        f"资格结论为 **{result['qualification_status']}**。", "",
        "仅对已保存资产进行标准库离线分析。几何判断使用实际 binary64 世界坐标的 Fraction，零产品、Blender 和模型运行。名义间隙仅在实际求解结束后交叉核查。", "",
    ]
    if "exception" in result:
        lines += ["## 未完成或失败原因", "", result["exception"], ""]
    if "body_checks" in result:
        lines += ["## 实测闭壳", "", "| 对象 | 点 | 三角 | 边 | 自身三角对 | 检查 |",
                  "|---|---:|---:|---:|---:|---|"]
        for name, body in result["body_checks"].items():
            lines.append(f"| {name} | {body['vertices']} | {body['triangles']} | {body['edges']} | {body['self_triangle_pairs_checked']} | {'通过' if body['passed'] else '失败'} |")
        lines += ["", "自体检查仅允许交集落在合法共享拓扑顶点或边，非法额外交叠拒绝。互体 288 个三角对独立计数，含共面相交。包含关系另用双方全部顶点的有理射线奇偶检查，保留方向、命中三角、参数及避退化记录。", ""]
    if "pair_results" in result:
        lines += ["## 实际真值", "", "| 对象对 | 关系 | 间隙毫米 | 至少 4 毫米 | 最近特征 |",
                  "|---|---|---:|---|---|"]
        for name, pair in result["pair_results"].items():
            feature = result["crosschecks"]["nearest_features"][name]
            lines.append(f"| Target / {name} | {pair['solid_relation']} | {pair['sqrt_interval']['display_mm']} | {'是' if pair['at_least_4mm'] else '否'} | {'通过' if feature['passed'] else '失败'} |")
        lines += ["", f"限定三个候选的最近者为 {', '.join(result['nearest_candidates'])}。每个三角对保存精确距离平方、全部同值最小候选、三角 ID、重心和边参数。", "",
                  "平方根采用整数平方根构造 70 位小数外向区间，并将最终 Decimal 两端重新转为 Fraction，验证 lo² ≤ min_sq ≤ hi²。", "",
                  "A 通过全部实际支撑三元组核实在 Target 凸包内，同时以实际局部凹截面核槽空域。材料分离的主证据为实际世界几何的相交及有理射线检查。A 须保持槽底面内点，B 须保持非平行边的严格内点，C 须保持端盖实际材料内点。", "",
                  "矩阵和顶点未吸附回理想值。实际矩阵的 binary32 表示变化以及世界 binary64 求值残差独立保留。局部截面属于交叉核查，未替代世界全集距离和实体判定。", ""]
    lines += ["## 资格检查", ""]
    for check in result.get("qualification_checks", []):
        lines.append(f"- {'PASS' if check['passed'] else 'FAIL'} {check['check']}")
    lines += ["", f"离线分析窗口为 {result['analysis_elapsed_ns']/1e6:.3f} 毫秒，文件发布窗口另存 RUNS.jsonl。此处是资格制备成本。", "",
              f"[完整真值与证书]({truth_path.as_posix()}) [独立算法]({(OUT/'exact_geometry.py').as_posix()}) [离线入口]({Path(__file__).resolve().as_posix()}) [来源 SHA]({(OUT/'SOURCES.json').as_posix()})", ""]
    (OUT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    started = time.perf_counter_ns()
    result = {
        "schema": "m4-grooved-rail-independent-exact-oracle-v1", "qualification_status": "incomplete",
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "started_ns": started,
        "authority": "Qualification only, no product, Blender or consumer execution.",
        "fraction_source": "Fraction(float) of exported actual binary64 world coordinates",
        "timings": [],
    }
    try:
        before = manifest()
        freeze = json.loads((BATCH / "FREEZE.json").read_text(encoding="utf-8-sig"))
        for item in freeze["specifications"]:
            if item["copy"] in ("spec/PLAN.md", "spec/DESIGN.md"):
                assert hashlib.sha256((BATCH / item["copy"]).read_bytes()).hexdigest() == item["sha256"]
        assert freeze["consumer_allowance"] == freeze["product_pretest_allowance"] == 0
        snapshot_path = BATCH / "asset" / "ACTUAL_SNAPSHOT.json"
        result["actual_snapshot_sha256"] = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
        objects, input_checks, residuals = validate_input(snapshot)
        result["input_checks"], result["binary64_evaluation_residuals"] = input_checks, residuals
        result["algorithm_checks"] = algorithm_checks()
        stage = time.perf_counter_ns()
        result["timings"].append({"stage": "input_and_synthetic_checks", "elapsed_ns": stage - started})
        vertices = {name: [tuple(F(v) for v in p) for p in objects[name]["vertices_world"]] for name in NAMES}
        faces = {name: [tuple(t) for t in objects[name]["triangles"]] for name in NAMES}
        bodies = {name: audit_body(name, vertices[name], faces[name]) for name in NAMES}
        result["body_checks"] = bodies
        end = time.perf_counter_ns()
        result["timings"].append({"stage": "294_body_self_pairs_and_topology", "elapsed_ns": end - stage})
        stage = end
        if not all(body["passed"] for body in bodies.values()):
            raise ValueError("actual_body_closed_shell_qualification_failed")
        pairs = solve_pairs(vertices, faces)
        result["pair_results"] = pairs
        end = time.perf_counter_ns()
        result["timings"].append({"stage": "288_interbody_pairs_and_bidirectional_parity", "elapsed_ns": end - stage})
        stage = end
        crosschecks, selected = crosscheck_features(objects, vertices, pairs)
        result["crosschecks"] = crosschecks
        for name, witness in selected.items():
            pairs[name]["selected_feature_witness"] = witness
            pairs[name]["selected_world_coordinates_binary64_display"] = {
                "target": [float(v) for v in witness["point_target"]],
                "candidate": [float(v) for v in witness["point_candidate"]],
            }
        nominal = {"Part_A": F("0.00525"), "Part_B": F("0.00275"), "Part_C": F("0.0085")}
        result["nominal_crosscheck_only"] = {
            name: {"nominal_distance_m": value, "actual_within_1e_minus_6_m":
                   (value - F(1, 10**6)) ** 2 <= pairs[name]["exact_squared_distance_m2"] <= (value + F(1, 10**6)) ** 2}
            for name, value in nominal.items()
        }
        best = min(pair["exact_squared_distance_m2"] for pair in pairs.values())
        result["nearest_candidates"] = [name for name, pair in pairs.items() if pair["exact_squared_distance_m2"] == best]
        counts = {
            "objects": len(objects), "vertices": sum(len(v) for v in vertices.values()),
            "triangles": sum(len(f) for f in faces.values()),
            "interbody_triangle_pairs": sum(p["triangle_pairs_checked"] for p in pairs.values()),
            "self_triangle_pairs": sum(b["self_triangle_pairs_checked"] for b in bodies.values()),
            "bidirectional_vertex_parity_queries": sum(len(p["target_vertices_in_candidate_ray_parity"])
                                                       + len(p["candidate_vertices_in_target_ray_parity"]) for p in pairs.values()),
        }
        result["counts"] = counts
        checks = [
            {"check": "all_input_design_checks", "passed": all(c["passed"] for c in input_checks)},
            {"check": "algorithm_synthetic_checks", "passed": all(c["passed"] for c in result["algorithm_checks"])},
            {"check": "four_valid_closed_shells", "passed": all(b["passed"] for b in bodies.values())},
            {"check": "288_interbody_and_294_self_pairs", "passed": counts["interbody_triangle_pairs"] == 288 and counts["self_triangle_pairs"] == 294},
            {"check": "three_material_pairs_separated", "passed": all(p["solid_relation"] == "separated" for p in pairs.values())},
            {"check": "A_in_actual_hull_and_groove_void", "passed": crosschecks["A_actual_section"]["passed"] and crosschecks["A_inside_actual_Target_convex_hull"]["passed"]},
            {"check": "A_vertex_floor_face_interior", "passed": crosschecks["nearest_features"]["Part_A"]["passed"]},
            {"check": "B_nonparallel_edge_interiors", "passed": crosschecks["nearest_features"]["Part_B"]["passed"]},
            {"check": "C_endcap_actual_material", "passed": crosschecks["nearest_features"]["Part_C"]["passed"]},
            {"check": "nominal_crosscheck_within_1e_minus_6_m", "passed": all(p["actual_within_1e_minus_6_m"] for p in result["nominal_crosscheck_only"].values())},
            {"check": "threshold_yes_no_yes", "passed": [pairs[n]["at_least_4mm"] for n in NAMES[1:]] == [True, False, True]},
            {"check": "unique_nearest_Part_B", "passed": result["nearest_candidates"] == ["Part_B"]},
            {"check": "input_hashes_unchanged", "passed": before == manifest()},
        ]
        result["qualification_checks"] = checks
        result["qualification_status"] = "passed" if all(c["passed"] for c in checks) else "failed"
        result["source_manifest"] = before
        end = time.perf_counter_ns()
        result["timings"].append({"stage": "actual_hull_features_and_qualification", "elapsed_ns": end - stage})
    except Exception as error:
        result["exception"] = f"{type(error).__name__} {error}"
        result["traceback"] = traceback.format_exc()
        result["qualification_status"] = "failed" if isinstance(error, (ValueError, AssertionError, KeyError)) else "incomplete"
    result["analysis_ended_ns"] = time.perf_counter_ns()
    result["analysis_elapsed_ns"] = result["analysis_ended_ns"] - started
    publish(result)
    ended = time.perf_counter_ns()
    receipt = {
        "started_ns": started, "analysis_ended_ns": result["analysis_ended_ns"],
        "publication_ended_ns": ended, "elapsed_through_publication_ns": ended - started,
        "qualification_status": result["qualification_status"], "exception": result.get("exception"),
        "traceback": result.get("traceback"), "counts": result.get("counts"),
        "truth_sha256": hashlib.sha256((OUT / "TRUTH.json").read_bytes()).hexdigest(),
        "entry_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "geometry_sha256": hashlib.sha256((OUT / "exact_geometry.py").read_bytes()).hexdigest(),
    }
    with (OUT / "RUNS.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(receipt, ensure_ascii=False) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
