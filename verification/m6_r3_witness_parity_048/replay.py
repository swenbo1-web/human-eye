"""Run the untouched A/C surface kernels against the frozen cases, then bind witness diagnostics."""
from collections import Counter
from fractions import Fraction
from pathlib import Path
from time import monotonic_ns, process_time_ns
from types import SimpleNamespace
import argparse
import json
import subprocess
import sys
import traceback

from freeze import HERE, RAW, check, read, ref, save

PUBLIC_FIELDS = (
    "measurement_valid", "reason", "distance_m", "point_a_world", "point_b_world",
    "witness_status", "witness_reason", "direction_a_to_b", "direction_status",
    "direction_reason", "method", "topology", "_exact_distance_sq",
)


def semantic(result):
    fields = {name: result[name] for name in PUBLIC_FIELDS if name in result}
    key = fields.get("_exact_distance_sq")
    if key is not None:
        numerator, denominator, exponent = key
        fields["_exact_distance_sq"] = str(Fraction(numerator, denominator) * Fraction(2)**exponent)
    return fields


def exact_encoding(value):
    if isinstance(value, Fraction):
        return str(value)
    if type(value) in (tuple, list):
        return [exact_encoding(x) for x in value]
    return value


def load_inputs(frozen):
    geometry = read(check(frozen["g60_material"]["NATIVE_GEOMETRY.json"]))["objects"]
    meshes = {name: {"name": name, "vertices_world": item["vertices_world_m"], "faces": item["triangles"]}
              for name, item in geometry.items()}
    cases = {}
    for case in frozen["g60_cases"]:
        args = case["kernel_args"]
        names = case["ordered_names"]
        cases[case["id"]] = ("g60", [meshes[name] for name in names], case["ordered_object_ids"], args)
    family = read(check(frozen["family"]["geometry"]))
    cases["closed-044"] = ("family", [family["left"], family["right"]],
                           [family[side]["object_id"] for side in ("left", "right")], {"retain_exact_rank": True})
    controls = read(check(frozen["controls"]))
    for case in controls["inputs"]:
        # Each case supplies the explicit ordered endpoints, independently of truth.
        cases[case["id"]] = ("control", [case["left"], case["right"]],
                             [case["left"]["name"], case["right"]["name"]], {"retain_exact_rank": True})
    return cases


def bound_runtime(frozen, arm):
    item = frozen["runtime"][arm]
    sys.path.insert(0, item["site"])
    from human_eye_plugin import surface_proximity, task_query
    from human_eye_plugin.runtime_identity import runtime_identity
    import numpy as np

    identity = runtime_identity(mode="live")
    assert identity['source_sha256'] == item['identity']['source_sha256']
    assert identity['distribution_version'] == item['identity']['distribution_version']
    assert Path(surface_proximity.__file__).resolve() == check(item["source"]["surface_proximity.py"])
    assert Path(task_query.__file__).resolve() == check(item["source"]["task_query.py"])
    assert [surface_proximity.MAX_FACES, surface_proximity.MAX_NARROW_PHASE_PAIRS,
            surface_proximity.MAX_WORK_UNITS] == [4096, 16384, 1179648]
    return surface_proximity, task_query, np, identity


def observe(runtime, family, endpoints, object_ids, args, diagnostic, seconds, trace):
    kernel, query, np, _ = runtime
    left, right = [SimpleNamespace(name=row["name"], object_id=oid,
                                  vertices=np.array(row["vertices_world"], dtype=np.float64),
                                  faces=np.array(row["faces"], dtype=np.int32))
                   for row, oid in zip(endpoints, object_ids)]
    observed = {}
    metrics, checkpoints = {}, Counter()
    captures = []
    profile_codes = {
        kernel._nearest_tree.__code__: "tree",
        kernel._nearest_linear.__code__: "linear",
        kernel._witness.__code__: "witness",
    }
    if trace:
        profile_codes.update({
            kernel._nearest_pair.__code__: "narrow_pair",
            kernel.measure_surface_proximity.__code__: "outer",
        })
    started, cpu = monotonic_ns(), process_time_ns()
    deadline = started + seconds * 10**9

    def checkpoint(stage):
        checkpoints[stage] += 1
        if monotonic_ns() >= deadline:
            raise TimeoutError(stage)

    def profile(frame, event, value):
        if event != "return":
            return
        kind = profile_codes.get(frame.f_code)
        if kind is None or value is None:
            return
        scope = frame.f_locals
        if kind in ("tree", "linear"):
            observed["search"] = kind
            observed["winner_native_rows"] = exact_encoding(scope["witness_pair"])
            observed["descriptor_kind"] = value[2][0]
            if trace:
                observed["descriptor"] = exact_encoding(value[2])
        elif kind == "witness":
            observed["integer_frame_witness"] = exact_encoding(value)
        elif kind == "narrow_pair":
            a, b = scope["left"], scope["right"]
            captures.append({"native_rows": [trace_rows[0].get(id(a)), trace_rows[1].get(id(b))],
                             "strict_rank": exact_encoding(value[:2]), "descriptor": exact_encoding(value[2]),
                             "previous_rank": exact_encoding(scope["best"][:2]) if scope["best"] else None})
        elif kind == "outer":
            observed["final_relative_descriptor"] = exact_encoding(scope.get("descriptor"))

    settings = dict(args)
    receipt = {"family": family, "inputs": [list(left.faces.shape), list(right.faces.shape)]}
    holder = {}
    trace_rows = [{}, {}]
    if diagnostic:
        settings.update(retain_witness_triangles=True, _prepared_holder=holder)
    if trace:
        for code in (kernel._nearest_linear.__code__, kernel._nearest_tree.__code__):
            profile_codes[code] = "linear" if code == kernel._nearest_linear.__code__ else "tree"

        def trace_profile(frame, event, value):
            if event == "call" and profile_codes.get(frame.f_code) in ("linear", "tree"):
                for index, side in enumerate(frame.f_locals["prepared"]):
                    trace_rows[index].update({id(item): row for row, item in enumerate(side)})
            else:
                profile(frame, event, value)
    try:
        if diagnostic:
            sys.setprofile(trace_profile if trace else profile)
        try:
            result = kernel.measure_surface_proximity(left, right, checkpoint, diagnostics=metrics, **settings)
        finally:
            if diagnostic:
                sys.setprofile(None)
        checkpoint("048_receipt_after_original_complete")
        receipt.update(status="returned", result=result, semantic=semantic(result),
                       public_fact=query._surface_proximity_fact(result))
        if diagnostic and "witness_points" in holder:
            _, _, origin, factor, _ = holder["pair"]
            points = holder["witness_points"]
            observed["exact_world_witness"] = [
                [str(Fraction(base) + Fraction(value) / factor) for base, value in zip(origin, point)]
                for point in points]
        if diagnostic:
            receipt["witness"] = observed
            if trace:
                receipt["narrow_candidate_returns"] = captures
    except Exception:
        receipt.update(status="execution_error", traceback=traceback.format_exc())
    receipt.update(wall_ns=monotonic_ns()-started, cpu_ns=process_time_ns()-cpu,
                   checkpoint_counts=dict(checkpoints))
    return receipt


def worker(freeze_path, arm):
    frozen = read(freeze_path)
    assert check(frozen["replay"]) == Path(__file__).resolve()
    inputs = load_inputs(frozen)
    start = monotonic_ns()
    runtime = bound_runtime(frozen, arm)
    print(json.dumps({"status": "ready", "arm": arm, "source": runtime[3]["source_sha256"],
                      "numpy": runtime[2].__version__, "pid": __import__("os").getpid(),
                      "import_and_bind_ns": monotonic_ns()-start}), flush=True)
    for line in sys.stdin:
        action = json.loads(line)
        if action.get("exit"):
            break
        case_id = action["id"]
        args = inputs[case_id]
        result = observe(runtime, *args, action["diagnostic"], frozen["limits"]["pair_deadline_s"],
                         action.get("trace", False))
        print(json.dumps(result, allow_nan=False), flush=True)


def ask(process, case_id, *, diagnostic=False, trace=False):
    process.stdin.write(json.dumps({"id": case_id, "diagnostic": diagnostic, "trace": trace}) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    assert line, f"EOF from offline interpreter {process.pid}: {process.poll()}"
    return json.loads(line)


def difference(left, right):
    return {key: {"A": left.get(key), "C": right.get(key)}
            for key in sorted(set(left) | set(right)) if (key in left) != (key in right)
            or json.dumps(left.get(key), sort_keys=True) != json.dumps(right.get(key), sort_keys=True)}


def divergence(ordinary, diagnostic):
    for arm in "AC":
        if any(rows[arm]["status"] != "returned" for rows in (ordinary, diagnostic)):
            return "execution_failure", {"arm": arm}
        changed = difference(ordinary[arm]["semantic"], diagnostic[arm]["semantic"])
        if changed:
            return "diagnostic_not_bound_to_original", {"arm": arm, "fields": changed}
    public = difference(ordinary["A"]["semantic"], ordinary["C"]["semantic"])
    if public:
        return "normal_output_difference", public
    include = ("winner_native_rows", "exact_world_witness")
    a = {key: diagnostic["A"]["witness"].get(key) for key in include}
    c = {key: diagnostic["C"]["witness"].get(key) for key in include}
    changed = difference(a, c)
    if changed:
        return "exact_native_witness_difference", changed
    return None, {}


def close(procs, logs):
    outcome = {}
    for arm, proc in procs.items():
        stopped = monotonic_ns()
        forced = False
        try:
            if proc.poll() is None:
                try:
                    proc.stdin.write('{"exit":true}\n')
                    proc.stdin.flush()
                except BrokenPipeError:
                    pass
            proc.stdin.close()
            try:
                returncode = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                returncode = proc.wait(timeout=5)
                forced = True
            proc.stdout.close()
            outcome[arm] = {"pid": proc.pid, "exit": returncode, "forced": forced,
                            "close_ns": monotonic_ns()-stopped}
        finally:
            logs[arm].close()
    return outcome


def run(freeze_path, out):
    started = monotonic_ns()
    frozen = read(freeze_path)
    assert check(frozen["replay"]) == Path(__file__).resolve()
    assert out.resolve().is_relative_to(RAW.resolve()) and not out.exists()
    inputs = load_inputs(frozen)
    out.mkdir()
    processes, logs, ready = {}, {}, {}
    report = {"freeze": ref(freeze_path), "paired_cases": [], "planned": list(inputs),
              "first_difference": None, "status": "running"}
    try:
        for arm in "AC":
            logs[arm] = (out / f"{arm}.stderr.log").open("x", encoding="utf-8")
            command = [sys.executable, "-E", "-s", "-B", "-X", "utf8",
                       __file__, "worker", str(freeze_path), arm]
            proc = processes[arm] = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=logs[arm],
                text=True, encoding="utf-8")
            line = proc.stdout.readline()
            assert line, f"{arm} import did not reach ready"
            ready[arm] = json.loads(line)
        for case_id in inputs:
            rows = {arm: ask(processes[arm], case_id) for arm in "AC"}
            ordinary_ref = save(out / case_id / "ORDINARY.json", rows)
            diagnostic = {arm: ask(processes[arm], case_id, diagnostic=True) for arm in "AC"}
            diag_ref = save(out / case_id / "DIAGNOSTIC.json", diagnostic)
            pair_record = {"case": case_id, "normal": ordinary_ref, "diagnostic": diag_ref}
            report["paired_cases"].append(pair_record)
            status, changes = divergence(rows, diagnostic)
            if status:
                report["first_difference"] = {"case": case_id, "classification": status, "changes": changes}
                if status in ("normal_output_difference", "exact_native_witness_difference"):
                    trace = {arm: ask(processes[arm], case_id, diagnostic=True, trace=True) for arm in "AC"}
                    pair_record["same_input_trace"] = save(out / case_id / "FIRST_TRACE.json", trace)
                break
        report["status"] = "stopped_at_difference" if report["first_difference"] else "paired_replay_complete"
    except Exception:
        report.update(status="execution_failed", traceback=traceback.format_exc())
    finally:
        report["processes"] = ready
        report["closeout"] = close(processes, logs)
        report["not_run"] = list(inputs)[len(report["paired_cases"]):]
        report["elapsed_with_import_and_close_ns"] = monotonic_ns()-started
        print(save(out / "REPLAY.json", report))
    return int(report["status"] == "execution_failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("worker", "run"))
    parser.add_argument("freeze", type=Path)
    parser.add_argument("arm_or_attempt")
    params = parser.parse_args()
    if params.mode == "worker":
        worker(params.freeze, params.arm_or_attempt)
    else:
        raise SystemExit(run(params.freeze, RAW / params.arm_or_attempt))

