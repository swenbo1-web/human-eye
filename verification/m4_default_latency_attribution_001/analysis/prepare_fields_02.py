"""Preserve the frozen analyzer and derive its bounded warm-telemetry fix."""

import ast
import difflib
import hashlib
import json
from pathlib import Path
import types


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
FROZEN_SHA = "ce877249d0cbb85ae3edfa4342af6672ebd25256f64fa9a84e747a6ae53c3dff"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def main():
    destination = HERE / "field_fix_001"
    destination.mkdir(exist_ok=False)
    original_path = HERE / "analyze_saved.py"
    original = original_path.read_bytes()
    assert sha(original) == FROZEN_SHA
    text = original.decode("utf8")
    helper = '''def warm_recorded_work_matches(task, successful_hash_count):
    return successful_hash_count == 0 and task['result_cache_hit'] is True and all(
        task[key] == 0 for key in ('exact_pair_count', 'closed_solid_pair_count', 'surface_pair_count'))


'''
    needle = '''check(label + ":warm_no_hash_or_kernel", row["successful_normalize_hash_spans"] == 0
                          and task["result_cache_hit"] is True and all(task[key] == 0 for key in KERNEL))'''
    replacement = '''check(label + ":warm_no_hash_or_kernel", warm_recorded_work_matches(
                        task, row["successful_normalize_hash_spans"]))'''
    assert text.count(needle) == 1 and text.count("def distribution(values):") == 1
    derived = text.replace("def distribution(values):", helper + "def distribution(values):", 1).replace(needle, replacement, 1)
    row_needle = '''"measurements": measurements, "raw_work": work, "task_work": task,'''
    row_replacement = '''"measurements": measurements, "raw_work": work, "task_work": task,
                    "additional_task_counter_status": {key: 'reported' if key in task else
                        'not_emitted_on_cache_hit' if task['result_cache_hit'] else 'not_emitted'
                        for key in ('pair_calls', 'rank_calls')},'''
    assert derived.count(row_needle) == 1
    derived = derived.replace(row_needle, row_replacement, 1)
    ast.parse(derived)
    derived_path = HERE / "analyze_saved_fields_02.py"
    with derived_path.open("xb") as stream:
        stream.write(derived.encode("utf8"))
    difference = "".join(difflib.unified_diff(text.splitlines(keepends=True), derived.splitlines(keepends=True),
        fromfile="frozen_ce877249/analyze_saved.py", tofile="derived/analyze_saved_fields_02.py"))
    (destination / "SOURCE.diff").write_text(difference, encoding="utf8", newline="\n")
    module = types.ModuleType("_derived_analysis_metadata_check")
    module.__file__ = str(derived_path)
    exec(compile(derived, str(derived_path), "exec", dont_inherit=True), module.__dict__)
    raw_result = (BATCH / "entry/run_01/RESULTS.json").read_bytes()
    actual = json.loads(raw_result)
    warm = actual["cases"][0]["rows"][1]["task_work"]
    assert warm == {"exact_pair_count": 0, "surface_pair_count": 0,
                    "closed_solid_pair_count": 0, "result_cache_hit": True}
    checks = [{"check": "actual_sparse_cache_hit_contract", "passed": module.warm_recorded_work_matches(warm, 0)}]
    for name in ("exact_pair_count", "closed_solid_pair_count", "surface_pair_count"):
        missing = {key: value for key, value in warm.items() if key != name}
        try:
            module.warm_recorded_work_matches(missing, 0)
        except KeyError as error:
            passed = error.args == (name,)
        else:
            passed = False
        checks.append({"check": "missing_required_" + name, "passed": passed, "expected": "KeyError of the exact missing key"})
        checks.append({"check": "nonzero_" + name, "passed": not module.warm_recorded_work_matches(dict(warm, **{name: 1}), 0)})
    checks.append({"check": "cache_miss_is_not_a_warm_hit", "passed": not module.warm_recorded_work_matches(dict(warm, result_cache_hit=False), 0)})
    checks.append({"check": "new_hash_work_is_rejected", "passed": not module.warm_recorded_work_matches(warm, 1)})
    assert all(row["passed"] for row in checks)
    validated = json.loads((BATCH / "entry/run_01/VALIDATED_INPUTS.json").read_bytes())
    contracts = {}
    for version in ("B", "C"):
        install_root = Path(validated["versions"][version]["install_root"])
        records = {}
        for filename, classname, method_name in (("live_service.py", "LiveSpatialService", None),
                                                ("read_context.py", "ReadContext", "result")):
            source_path = install_root / "human_eye_plugin" / filename
            raw = source_path.read_bytes()
            assert sha(raw) == validated["checked_files_sha256"][str(source_path)]
            tree = ast.parse(raw)
            owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == classname)
            methods = [node for node in owner.body if isinstance(node, ast.FunctionDef)]
            if method_name is None:
                method = next(node for node in methods if "work = {'exact_pair_count': 0, 'surface_pair_count': 0, 'closed_solid_pair_count': 0}" in ast.get_source_segment(raw.decode(), node))
            else:
                method = next(node for node in methods if node.name == method_name)
            fragment = ast.get_source_segment(raw.decode(), method) + "\n"
            output = destination / (version + "_" + filename + ".fragment.txt")
            output.write_text(fragment, encoding="utf8", newline="\n")
            records[filename] = {"path": str(source_path), "source_sha256": sha(raw), "method": method.name,
                "first_line": method.lineno, "last_line": method.end_lineno,
                "fragment_path": output.name, "fragment_sha256": sha(fragment.encode())}
        contracts[version] = {"runtime_source_sha256": validated["versions"][version]["source_sha256"], "sources": records}
    assert original_path.read_bytes() == original
    save(destination / "METADATA_REGRESSION.json", {"synthetic_execution": "actual recorded metadata only; no geometry/runtime execution",
        "passed": all(row["passed"] for row in checks), "checks": checks, "check_count": len(checks),
        "actual_task_work": warm, "task_work_origin": "entry/run_01/RESULTS.json /cases/0/rows/1/task_work",
        "entry_result_sha256": sha(raw_result), "product_calls": 0, "Blender_sessions": 0, "consumers": 0})
    save(destination / "SOURCE_CONTRACT.json", {"versions": contracts,
        "interpretation": "Warm result-cache hits emit only the three initialized kernel counts plus result_cache_hit. ReadContext.result returns the cached copy without invoking compute. pair_calls/rank_calls remain absent and are explicitly labelled not_emitted_on_cache_hit; no zero values are invented."})
    save(destination / "DERIVATION.json", {"frozen_source_sha256": FROZEN_SHA, "frozen_source_unchanged": True,
        "derived_source_sha256": sha(derived.encode()), "exact_diff_sha256": sha(difference.encode()),
        "preparer_source_sha256": sha(Path(__file__).read_bytes()),
        "changed_scope": "warm telemetry field shape and explicit absent-counter status; cold five-key check, numeric data and analysis rules preserved"})
    print(json.dumps({"passed": True, "checks": len(checks), "derived_source_sha256": sha(derived.encode())}))


if __name__ == "__main__":
    main()
