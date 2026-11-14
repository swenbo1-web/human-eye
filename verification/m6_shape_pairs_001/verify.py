"""Independent label, metric, stationarity and exported-geometry readback."""
import os
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time
import traceback

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def metric(values):
    values = sorted(values)
    position = .95 * (len(values) - 1)
    low = math.floor(position)
    p95 = values[low] + (position - low) * (values[min(low + 1, len(values) - 1)] - values[low])
    return math.sqrt(math.fsum(value * value for value in values) / len(values)), p95, values[-1]


def stationarity(observed, repaired, faces, free, rows, columns):
    """Independent edge aggregation with cosine-law cotangents; no solve."""
    incident = faces[np.any(np.isin(faces, rows), axis=1)]
    points = observed[incident]
    area2 = np.linalg.norm(np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]), axis=1)
    masses = np.zeros(len(observed))
    weights = {}
    for local in range(3):
        first, second = (local + 1) % 3, (local + 2) % 3
        side1 = np.sum((points[:, first] - points[:, local])**2, axis=1)
        side2 = np.sum((points[:, second] - points[:, local])**2, axis=1)
        opposite = np.sum((points[:, first] - points[:, second])**2, axis=1)
        cotangents = (side1 + side2 - opposite) / (2 * area2)
        np.add.at(masses, incident[:, local], area2 / 6)
        for face, cotangent in zip(incident, cotangents):
            key = tuple(sorted((int(face[first]), int(face[second]))))
            weights[key] = weights.get(key, 0.) + float(cotangent) / 2
    row_map, column_map = {i: n for n, i in enumerate(rows)}, {i: n for n, i in enumerate(columns)}
    matrix = np.zeros((len(rows), len(columns)))
    for (a, b), weight in weights.items():
        for index, neighbor in ((a, b), (b, a)):
            if index in row_map:
                matrix[row_map[index], column_map[index]] += weight
                matrix[row_map[index], column_map[neighbor]] -= weight
    matrix /= np.sqrt(masses[rows, None])
    free_columns = [column_map[i] for i in free]
    fixed = [i for i in columns if i not in set(free)]
    left = matrix[:, free_columns]
    residual = matrix @ repaired[columns]
    fixed_part = matrix[:, [column_map[i] for i in fixed]] @ observed[fixed]
    return float(np.linalg.norm(left.T @ residual) / max(np.linalg.norm(left.T @ fixed_part), np.finfo(float).tiny))


def browser_check(private):
    executable = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    if not executable.exists():
        return {"status": "not_run", "reason": "isolated_headless_browser_unavailable"}
    profile = (private / "browser_profile_qa").resolve()
    assert profile.is_relative_to(HERE.resolve()) and profile.parent == private.resolve() and profile.name == "browser_profile_qa"
    assert not profile.exists()
    screenshot = private / "VIEWER_BROWSER.png"
    command = [str(executable), "--headless=new", "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
               "--disable-sync", "--disable-component-update", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
               "--allow-file-access-from-files", "--user-data-dir=" + str(profile), "--window-size=1280,900",
               "--virtual-time-budget=4000", "--screenshot=" + str(screenshot), "--dump-dom", (private / "VIEWER.html").as_uri()]
    started = time.perf_counter()
    outcome = {"command": command, "manual_pointer_interaction": "not_tested"}
    try:
        process = subprocess.run(command, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        (private / "BROWSER_DOM.html").write_bytes(process.stdout)
        (private / "BROWSER.stderr.log").write_bytes(process.stderr)
        dom = process.stdout.decode("utf8", errors="replace")
        success = process.returncode == 0 and '<option value="13"' in dom and 'ROI RMSE 0.000 mm' in dom and screenshot.exists()
        outcome.update(status="initialized_and_drawn" if success else "limited", exit_code=process.returncode,
                       screenshot=str(screenshot), options_initialized=dom.count("<option"), initial_metric_present='ROI RMSE 0.000 mm' in dom)
    except subprocess.TimeoutExpired as exc:
        outcome.update(status="timeout", error=str(exc))
    outcome["wall_s"] = time.perf_counter() - started
    try:
        if profile.exists():
            assert profile.resolve().is_relative_to(HERE.resolve()) and profile.name == "browser_profile_qa"
            shutil.rmtree(profile)
        outcome["temporary_profile_removed"] = True
    except OSError as exc:
        outcome["temporary_profile_removed"] = False
        outcome["temporary_profile_cleanup_error"] = str(exc)
    return outcome


def main():
    started = time.perf_counter()
    private = HERE / "private"
    output = {"status": "running", "checks": []}
    def check(name, value):
        output["checks"].append({"name": name, "passed": bool(value)})
        if not value:
            raise AssertionError(name)
    try:
        result = json.loads((HERE / "RESULTS.json").read_bytes())
        labels = json.loads((private / "LABELS.json").read_bytes())
        plan = json.loads((HERE / "CASE_PLAN.json").read_bytes())
        reference = np.load(labels["reference_npy"], allow_pickle=False)
        faces = np.load(private / "triangles.npy", allow_pickle=False)
        region = labels["region_ids"]
        local = {index: i for i, index in enumerate(region)}
        inside = faces[np.all(np.isin(faces, region), axis=1)]
        edge_counts, neighbors = {}, [set() for _ in reference]
        for face in faces:
            for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
                neighbors[a].add(int(b)); neighbors[b].add(int(a))
        for face in inside:
            for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
                edge = tuple(sorted((int(a), int(b)))); edge_counts[edge] = edge_counts.get(edge, 0) + 1
        boundary = sorted({i for edge, count in edge_counts.items() if count == 1 for i in edge})
        free = sorted(set(region) - set(boundary))
        rows = sorted(set(free) | {j for i in free for j in neighbors[i]})
        columns = sorted(set(rows) | {j for i in rows for j in neighbors[i]})
        graph = np.full((len(region), len(region)), np.inf)
        for a, b in edge_counts:
            graph[local[a], local[b]] = graph[local[b], local[a]] = np.linalg.norm(reference[a] - reference[b])
        distances = np.full(len(region), np.inf); distances[local[24205]] = 0.
        visited = np.zeros(len(region), dtype=bool)
        for _ in region:
            index = int(np.argmin(np.where(visited, np.inf, distances)))
            check("finite independent graph traversal", np.isfinite(distances[index]))
            visited[index] = True
            distances = np.minimum(distances, distances[index] + graph[index])
        depth = min(distances[local[i]] for i in boundary)
        incident = faces[np.any(faces == 24205, axis=1)]
        normal = np.cross(reference[incident[:, 1]] - reference[incident[:, 0]], reference[incident[:, 2]] - reference[incident[:, 0]]).sum(axis=0)
        normal /= np.linalg.norm(normal)
        check("independent D and center normal", abs(depth - labels["distance_to_boundary_m"]) < 1e-14 and np.allclose(normal, labels["center_normal"], rtol=0, atol=1e-15))
        check("topological free/row/context sizes", [len(free), len(rows), len(columns)] == [338, 403, 480] and boundary == labels["boundary_ids"])
        obj_expected = {}
        gradients = []
        for case, row in zip(labels["cases"], result["cases"]):
            abnormal = np.load(case["abnormal_npy"], allow_pickle=False)
            repaired = np.load(private / f"{case['id']}_repaired.npy", allow_pickle=False)
            expected = reference.copy()
            support = []
            if case["radius_m"] is not None:
                radius, amplitude = case["radius_ratio"] * depth, case["amplitude_ratio"] * case["radius_ratio"] * depth
                for index in free:
                    distance = distances[local[index]]
                    if distance < radius:
                        expected[index] -= amplitude * (1 - (distance / radius)**2)**2 * normal
                        support.append(index)
            check(case["id"] + " independently regenerated labels", np.allclose(abnormal, expected, rtol=0, atol=1e-16) and support == case["true_support_ids"])
            check(case["id"] + " inverse displacement label", np.array_equal(np.load(case["inverse_displacement_npy"]), reference - abnormal))
            for title, coordinates, metric_key, ids in (("no_op_region", abnormal, "no_op_region_error", region), ("repair_region", repaired, "repaired_region_error", region),
                                                        ("no_op_support", abnormal, "no_op_support_error", support), ("repair_support", repaired, "repaired_support_error", support)):
                if ids:
                    values = metric([math.dist(reference[i], coordinates[i]) for i in ids])
                    check(case["id"] + " scalar " + title, all(abs(row[metric_key][name] - value) < 1e-12 for name, value in zip(("rmse_m", "p95_m", "max_m"), values)))
            check(case["id"] + " exact boundary and external", np.array_equal(repaired[boundary], reference[boundary]) and np.array_equal(repaired[[i for i in range(len(reference)) if i not in set(region)]], reference[[i for i in range(len(reference)) if i not in set(region)]]))
            residual = stationarity(abnormal, repaired, faces, free, rows, columns)
            gradients.append({"id": case["id"], "independent_normal_equation_relative_residual": residual})
            check(case["id"] + " independently assembled stationarity", residual < 1e-9)
            for stage in ("damage_contact", "repair_contact"):
                facts = json.loads(Path(row[stage]["private_facts"]["path"]).read_bytes())
                check(case["id"] + stage + " complete contact readback", facts["scope_complete"] and facts["contact_complete"] and not facts["new_pairs"] and facts["contact_ok"] is True)
            obj_expected[row["private_outputs"][2]["path"]] = abnormal
            obj_expected[row["private_outputs"][3]["path"]] = repaired
        for path, expected in obj_expected.items():
            parsed_vertices, parsed_faces = [], []
            for line in Path(path).read_text(encoding="utf8").splitlines():
                if line.startswith("v "):parsed_vertices.append([float(value) for value in line.split()[1:]])
                elif line.startswith("f "):parsed_faces.append([int(value) - 1 for value in line.split()[1:]])
            check("OBJ roundtrip " + Path(path).name, np.array_equal(np.asarray(parsed_vertices), expected) and np.array_equal(np.asarray(parsed_faces), faces))
        for name in ("generate.py", "method.py"):
            check("frozen algorithm/generator " + name, hashlib.sha256((HERE / name).read_bytes()).hexdigest() == plan["script_sha256"][name])
        for entry in result["source_inputs"]:
            data = Path(entry["path"]).read_bytes()
            check("old input preserved " + entry["path"], len(data) == entry["bytes"] and hashlib.sha256(data).hexdigest() == entry["sha256"])
        output.update(status="passed", independent_stationarity=gradients, obj_copies_checked=len(obj_expected),
                      algorithm_solves_during_verification=0, browser=browser_check(private))
    except Exception as exc:
        output.update(status="failed", error=str(exc), traceback=traceback.format_exc())
        print(traceback.format_exc())
    output["wall_s_before_publication"] = time.perf_counter() - started
    (HERE / "VERIFICATION.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"status": output["status"], "checks": len(output["checks"]), "wall_s": output["wall_s_before_publication"], "browser": output.get("browser", {}).get("status")}))
    return 0 if output["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
