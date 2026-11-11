"""Bounded schema and actual runtime checks over one guarded source snapshot.

The old schema is extracted from exact frozen Git bytes. Runtime validators are
executed from the candidate. Their unchanged source is independently checked.
This does not rerun the old runtime or implement complete JSON Schema.
"""

import argparse
import ast
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import traceback
import types
from types import MappingProxyType
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REFERENCE = Path("D:/hefe/verification/fixes/20261111_m4_relation_selected_review/code/check_geometry_schema_scope.py")
TEST = HERE / "tests/test_schema_scope.py"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def canonical(blobs):
    tree = ast.parse(blobs["human_eye_plugin/runtime_identity.py"])
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in ("BASE_VERSION", "IMPLEMENTATION_REVISION")}
    manifest = [{"path": path, "sha256": sha(raw)} for path, raw in sorted(blobs.items())]
    payload = {"base_version": constants["BASE_VERSION"],
               "implementation_revision": constants["IMPLEMENTATION_REVISION"], "files": manifest}
    return sha(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()), manifest


def assignment(tree, name):
    return next(node for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))


def extract_baseline_schemas(tree, mcp):
    environment = {"copy": copy, "SELECTOR_SCHEMA": mcp.SELECTOR_SCHEMA,
        "TASK_FACTS": mcp.TASK_FACTS, "MAX_VISUAL_LABEL_IDS": mcp.MAX_VISUAL_LABEL_IDS,
        "NATIVE_VISUAL_SCHEMA": mcp.NATIVE_VISUAL_SCHEMA,
        "SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA": mcp.SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA}
    names = ("_ID_SCHEMA", "_VECTOR_SCHEMA", "_TASK_GEOMETRY_SCHEMA", "_QUERY_SCHEMA", "SPATIAL_TASK_TOOLS_SCHEMA")
    for name in names:
        expression = ast.Expression(assignment(tree, name).value)
        environment[name] = eval(compile(expression, "frozen-baseline-schema-expression", "eval"), environment)
    return environment["_QUERY_SCHEMA"], environment["SPATIAL_TASK_TOOLS_SCHEMA"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    destination = HERE / arguments.output
    if destination.parent.resolve() != HERE.resolve() or destination.name in (".", ".."):
        raise ValueError("output must be one new immediate child of the batch")
    destination.mkdir(exist_ok=False)
    work_raw = (HERE / "WORK_ORDER.json").read_bytes()
    work = json.loads(work_raw)
    diff_raw = (HERE / "SOURCE_DIFF.json").read_bytes()
    diff = json.loads(diff_raw)
    blobs = {row["path"]: (ROOT / row["path"]).read_bytes() for row in diff["manifest"]}
    digest, manifest = canonical(blobs)
    assert manifest == diff["manifest"]
    assert len(blobs) == 137 and digest == diff["source_sha256"]
    original = subprocess.run(["git", "-C", str(ROOT), "show",
        work["baseline_commit"] + ":human_eye_plugin/live_spatial_mcp.py"], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, shell=False).stdout
    assert sha(original) == diff["source_file_before_sha256"]
    candidate = blobs["human_eye_plugin/live_spatial_mcp.py"]
    assert sha(candidate) == diff["source_file_after_sha256"]
    old_tree, new_tree = ast.parse(original), ast.parse(candidate)
    new_query = assignment(new_tree, "_QUERY_SCHEMA").value
    all_of = next(value for key, value in zip(new_query.keys, new_query.values)
                  if isinstance(key, ast.Constant) and key.value == "allOf")
    removed_condition = ast.literal_eval(all_of.elts.pop())
    expected_condition = {"if": {"required": ["geometry"]},
        "then": {"required": ["mode", "target", "candidates"], "properties": {"mode": {"const": "task"}}}}
    assert removed_condition == expected_condition
    assert ast.dump(old_tree, include_attributes=False) == ast.dump(new_tree, include_attributes=False)
    unchanged_validators = {}
    for name in ("_validate_arguments", "_spatial_task_query", "_surface_nearest_task_query"):
        old = next(node for node in old_tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
        new = next(node for node in new_tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
        unchanged_validators[name] = {
            "AST_equal": ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False),
            "source_bytes_equal": ast.get_source_segment(original.decode(), old) == ast.get_source_segment(candidate.decode(), new),
        }
        assert all(unchanged_validators[name].values())

    reference_raw = REFERENCE.read_bytes()
    reference_tree = ast.parse(reference_raw)
    evaluate_function = next(node for node in reference_tree.body if isinstance(node, ast.FunctionDef) and node.name == "accepts")
    evaluate_scope = {"json": json, "VISITED": set()}
    extracted_tree = ast.Module(body=[evaluate_function], type_ignores=[])
    exec(compile(extracted_tree, str(REFERENCE) + ":accepts-only", "exec"), evaluate_scope)
    extracted_source = ast.unparse(extracted_tree) + "\n"
    (destination / "BOUNDED_EVALUATOR.py").write_text(extracted_source, encoding="utf8", newline="\n")
    (destination / "BASELINE_MCP.py").write_bytes(original)
    evaluator_source = {"path": str(REFERENCE), "file_sha256": sha(reference_raw),
        "function_AST_sha256": sha(ast.dump(evaluate_function, include_attributes=False).encode()),
        "extracted_source_sha256": sha(extracted_source.encode()),
        "scope": "accepts function only; original bootstrap, hardcoded loader and output code were never executed"}

    engine = destination / "e"
    for relative, raw in blobs.items():
        path = engine / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    temporary = destination / "t"
    temporary.mkdir()
    assert temporary.resolve().is_relative_to(destination.resolve())
    tempfile.tempdir = str(temporary)
    os.environ.update(TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    sys.dont_write_bytecode = True
    loader = "human_eye_plugin/verified_source_loader.py"
    helper = types.ModuleType("_human_eye_verified_source_bootstrap")
    helper.__file__ = str(engine / loader)
    sys.modules[helper.__name__] = helper
    exec(compile(blobs[loader], helper.__file__, "exec", dont_inherit=True), helper.__dict__)
    guard = helper.install(engine.resolve(), manifest, sources=MappingProxyType(blobs), bootstrap_module=helper)
    namespace = types.ModuleType("human_eye_plugin")
    namespace.__path__ = [str(engine / "human_eye_plugin")]
    guard.allow_namespace(namespace)
    sys.modules[namespace.__name__] = namespace
    sys.path.insert(0, str(ROOT))
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("external process/network/signal")
        raise AssertionError(attempts[-1])

    stdout, stderr, test_log = io.StringIO(), io.StringIO(), io.StringIO()
    result, error, evidence, identity = None, None, {}, {}
    fixture_hashes = {}
    test_raw = TEST.read_bytes()
    try:
        with ExitStack() as stack, redirect_stdout(stdout), redirect_stderr(stderr):
            for name in ("Popen", "run", "call", "check_call", "check_output"):
                stack.enter_context(patch.object(subprocess, name, side_effect=forbidden))
            for name in ("system", "kill"):
                stack.enter_context(patch.object(os, name, side_effect=forbidden))
            for name in ("socket", "create_connection"):
                stack.enter_context(patch.object(socket, name, side_effect=forbidden))
            from human_eye_plugin import live_spatial_mcp as mcp
            from human_eye_plugin.runtime_identity import runtime_identity
            identity = runtime_identity()
            assert identity["source_sha256"] == digest and identity["source_kind"] == "unregistered_runtime"
            baseline_query, baseline_compact = extract_baseline_schemas(old_tree, mcp)
            assert baseline_query == {**mcp._QUERY_SCHEMA, "allOf": mcp._QUERY_SCHEMA["allOf"][:-1]}
            save(destination / "BASELINE_QUERY_SCHEMA.json", baseline_query)
            save(destination / "CANDIDATE_QUERY_SCHEMA.json", mcp._QUERY_SCHEMA)
            save(destination / "BASELINE_COMPACT_SCHEMAS.json", baseline_compact)
            save(destination / "CANDIDATE_COMPACT_SCHEMAS.json", mcp.SPATIAL_TASK_TOOLS_SCHEMA)
            module = types.ModuleType("_geometry_schema_scope_tests")
            module.__file__ = str(TEST)
            module.EVALUATOR = evaluate_scope["accepts"]
            module.EVALUATOR_SOURCE = evaluator_source
            module.BASELINE_QUERY_SCHEMA = baseline_query
            module.BASELINE_COMPACT_SCHEMAS = baseline_compact
            module.RUNTIME_SOURCE_SHA256 = digest
            sys.modules[module.__name__] = module
            exec(compile(test_raw, str(TEST), "exec", dont_inherit=True), module.__dict__)
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.GeometrySchemaScopeTests)
            result = unittest.TextTestRunner(stream=test_log, verbosity=2).run(suite)
            evidence = module.EVIDENCE
    except BaseException:
        error = traceback.format_exc()
    for name, content in (("STDOUT.txt", stdout.getvalue()), ("STDERR.txt", stderr.getvalue()), ("TESTS.txt", test_log.getvalue())):
        (destination / name).write_text(content, encoding="utf8", newline="\n")
    if error:
        (destination / "RUNNER_EXCEPTION.txt").write_text(error, encoding="utf8", newline="\n")
    loaded = guard.verify_loaded()
    current_unchanged = all((ROOT / relative).read_bytes() == raw for relative, raw in blobs.items())
    snapshot_unchanged = all((engine / relative).read_bytes() == raw for relative, raw in blobs.items())
    inputs_unchanged = (HERE / "WORK_ORDER.json").read_bytes() == work_raw and (HERE / "SOURCE_DIFF.json").read_bytes() == diff_raw
    tests_unchanged = TEST.read_bytes() == test_raw
    reference_unchanged = REFERENCE.read_bytes() == reference_raw
    for name, module in list(sys.modules.items()):
        path = getattr(module, "__file__", None)
        if name.startswith("verification.") and path and Path(path).is_file():
            fixture_hashes[str(Path(path).resolve())] = sha(Path(path).read_bytes())
    failures = [] if result is None else [{"test": test.id(), "traceback": failure} for test, failure in result.failures]
    errors = [] if result is None else [{"test": test.id(), "traceback": failure} for test, failure in result.errors]
    passed = bool(result and result.wasSuccessful() and not error and not attempts and loaded
                  and current_unchanged and snapshot_unchanged and inputs_unchanged and tests_unchanged and reference_unchanged)
    summary = {"cycle_id": work["cycle_id"], "passed": passed, "test_methods": 0 if result is None else result.testsRun,
        "generic_fixed_query_cases": len(evidence.get("generic_cases", [])),
        "compact_schema_validator_controls": len(evidence.get("compact_validator_controls", [])),
        "finite_compact_dispatches": len(evidence.get("finite_dispatch_controls", [])),
        "failures": failures, "errors": errors, "runner_exception": error,
        "baseline_runtime_reexecuted": False,
        "runtime_comparison_basis": "Exact baseline validator source/AST equals current; actual calls execute current guarded source.",
        "runtime_source_sha256": digest, "source_count": len(blobs), "source_kind": identity.get("source_kind"),
        "guard_verify_loaded": loaded, "current_137_unchanged": current_unchanged,
        "snapshot_137_unchanged": snapshot_unchanged, "frozen_inputs_unchanged": inputs_unchanged,
        "test_source_unchanged": tests_unchanged, "reference_source_unchanged": reference_unchanged,
        "visited_schema_keywords": sorted(evaluate_scope["VISITED"]),
        "full_JSON_Schema_validator": False, "external_operation_attempts": attempts,
        "model_consumers": 0, "product_business_processes": 0, "Blender_sessions": 0,
        "images": 0, "paid_API_calls": 0, "performance_measurements": 0}
    save(destination / "RESULTS.json", summary)
    save(destination / "EVIDENCE.json", evidence)
    save(destination / "EXECUTION_IDENTITY.json", {
        "manifest": manifest, "canonical_source_sha256": digest, "baseline_commit": work["baseline_commit"],
        "baseline_runtime_commit": work["baseline_runtime_commit"], "baseline_MCP_sha256": sha(original),
        "candidate_MCP_sha256": sha(candidate), "unchanged_validator_checks": unchanged_validators,
        "all_other_module_AST_equal": True, "only_appended_condition": removed_condition,
        "bounded_evaluator": evaluator_source, "fixture_sha256": fixture_hashes,
        "work_order_sha256": sha(work_raw), "source_diff_sha256": sha(diff_raw),
        "test_source_sha256": sha(test_raw), "runner_sha256": sha(Path(__file__).read_bytes()),
        "scope": "One guarded source snapshot. QA modules are outside its root. This is offline qualification, without installation or runtime performance retesting.",
    })
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
