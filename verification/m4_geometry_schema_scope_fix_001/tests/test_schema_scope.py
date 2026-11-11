"""Finite schema/runtime contracts with an independently frozen expectation table."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from human_eye_plugin import live_service, live_spatial_mcp as mcp
from human_eye_plugin.query_policy import validate_query
from verification.arch_read_context_001.test_resident_task import TokenSelectedHost


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = {}
TOOL = "human_eye_spatial_relations"
FACTS = ["closed_solid_relation", "surface_proximity"]
BASE_QUERY = {
    "mode": "task", "target": {"id": "a"}, "candidates": [{"id": "b"}],
    "requested_facts": FACTS,
}
GEOMETRY = {"objects": [{"id": "a"}]}
UNSUPPORTED = "query contains unsupported observation fields"
TASK_FIELDS = "task query requires only mode, objects and requested_facts"
SET_FACTS = "task set requires closed_solid_relation and surface_proximity; optional aabb only"
GEOMETRY_FIELDS = "task geometry requires 1..4 object selectors and optional boolean include_triangles"


def query_case(name, query, old_schema, new_schema, runtime, error=None):
    return {"name": name, "query": query, "baseline_schema_accepts": old_schema,
            "candidate_schema_accepts": new_schema, "runtime_accepts": runtime,
            "runtime_error": error}


def cases():
    task_geometry = dict(BASE_QUERY, geometry=GEOMETRY)
    missing = lambda field: {key: value for key, value in task_geometry.items() if key != field}
    return [
        query_case("original_overview_geometry", {"mode": "overview", "geometry": GEOMETRY}, True, False, False, UNSUPPORTED),
        query_case("original_legacy_AABB_geometry", {"mode": "task", "objects": [{"id": "a"}], "requested_facts": ["aabb"], "geometry": GEOMETRY}, True, False, False, TASK_FIELDS),
        query_case("valid_task_vertices", task_geometry, True, True, True),
        query_case("valid_task_full_AABB", dict(BASE_QUERY, requested_facts=FACTS + ["aabb"], geometry=dict(GEOMETRY, include_triangles=True)), True, True, True),
        query_case("valid_task_without_geometry", BASE_QUERY, True, True, True),
        query_case("legacy_overview_without_geometry", {"mode": "overview"}, True, True, True),
        query_case("default_query_without_geometry", {}, True, True, True),
        query_case("legacy_AABB_without_geometry", {"mode": "task", "objects": [{"id": "a"}], "requested_facts": ["aabb"]}, True, True, True),
        query_case("nearest_geometry_rejected", {"mode": "surface_nearest", "objects": [{"id": "a"}], "geometry": GEOMETRY}, False, False, False, "surface_nearest query accepts only mode and optionally one object selector"),
        query_case("nearest_without_geometry", {"mode": "surface_nearest", "objects": [{"id": "a"}]}, True, True, True),
        query_case("geometry_only_requires_mode_and_bindings", {"geometry": GEOMETRY}, True, False, False, UNSUPPORTED),
        query_case("task_geometry_missing_mode", missing("mode"), False, False, False, UNSUPPORTED),
        query_case("task_geometry_missing_target", missing("target"), False, False, False, TASK_FIELDS),
        query_case("task_geometry_missing_candidates", missing("candidates"), False, False, False, TASK_FIELDS),
        query_case("task_geometry_missing_requested_facts", missing("requested_facts"), False, False, False, TASK_FIELDS),
        query_case("task_geometry_missing_required_fact", dict(task_geometry, requested_facts=["aabb"]), False, False, False, SET_FACTS),
        query_case("task_geometry_mixed_legacy_objects", dict(task_geometry, objects=[{"id": "a"}]), False, False, False, TASK_FIELDS),
        query_case("task_geometry_unsupported_fact", dict(task_geometry, requested_facts=FACTS + ["center_delta"]), False, False, False, SET_FACTS),
        query_case("task_geometry_empty_selection", dict(BASE_QUERY, geometry={"objects": []}), False, False, False, GEOMETRY_FIELDS),
        query_case("task_geometry_nonboolean_triangles", dict(BASE_QUERY, geometry=dict(GEOMETRY, include_triangles=0)), False, False, False, GEOMETRY_FIELDS),
    ]


def outcome(function, value):
    try:
        normalized = function(value)
        return {"accepted": True, "error_type": None, "error": None, "normalized": normalized}
    except ValueError as error:
        return {"accepted": False, "error_type": type(error).__name__, "error": str(error), "normalized": None}


class GeometrySchemaScopeTests(unittest.TestCase):
    def test_generic_twenty_frozen_query_expectations(self):
        records = []
        for case in cases():
            with self.subTest(case=case["name"]):
                original = copy.deepcopy(case["query"])
                old_schema = EVALUATOR(BASELINE_QUERY_SCHEMA, original)
                new_schema = EVALUATOR(mcp._QUERY_SCHEMA, original)
                runtime = outcome(validate_query, original)
                arguments = {"query": copy.deepcopy(original), "include_image": False,
                             "session_id": "schema-scope-offline"}
                generic = outcome(lambda value: mcp._validate_arguments("human_eye_scene_observe", value), arguments)
                self.assertEqual(old_schema, case["baseline_schema_accepts"])
                self.assertEqual(new_schema, case["candidate_schema_accepts"])
                self.assertEqual(runtime["accepted"], case["runtime_accepts"])
                self.assertEqual(generic["accepted"], case["runtime_accepts"])
                self.assertEqual(runtime["error"], case["runtime_error"])
                self.assertEqual(generic["error"], case["runtime_error"])
                self.assertEqual(original, case["query"])
                self.assertEqual(arguments["query"], case["query"])
                records.append({"expected": copy.deepcopy(case), "baseline_schema_accepts": old_schema,
                    "candidate_schema_accepts": new_schema, "actual_validate_query": runtime,
                    "actual_generic_validator": generic, "input_unchanged": True})
        EVIDENCE["generic_cases"] = records

    def test_compact_published_schema_and_validator_three_controls(self):
        self.assertEqual(mcp.SPATIAL_TASK_TOOLS_SCHEMA, BASELINE_COMPACT_SCHEMAS)
        schema = next(tool["inputSchema"] for tool in mcp.SPATIAL_TASK_TOOLS_SCHEMA if tool["name"] == TOOL)
        records = []
        base = {"target": {"id": "a"}, "candidates": [{"id": "b"}]}
        for name, extra in (("OFF", {}), ("vertices", {"geometry": GEOMETRY}),
                ("full", {"geometry": dict(GEOMETRY, include_triangles=True)})):
            with self.subTest(mode=name):
                arguments = copy.deepcopy(dict(base, **extra))
                self.assertTrue(EVALUATOR(schema, arguments))
                self.assertIsNone(mcp._validate_arguments(TOOL, arguments))
                normalized = validate_query(mcp._spatial_task_query(arguments))
                self.assertEqual(normalized["requested_facts"], FACTS)
                self.assertEqual("geometry" in normalized, name != "OFF")
                self.assertEqual(arguments, dict(base, **extra))
                records.append({"mode": name, "arguments": arguments, "schema_accepts": True,
                                "runtime_accepts": True, "normalized": normalized})
        EVIDENCE["compact_validator_controls"] = records

    def test_compact_three_finite_dispatches_use_existing_capture_and_kernels(self):
        with tempfile.TemporaryDirectory(prefix="scope-") as temporary:
            config = Path(temporary) / "config.json"
            config.write_text(json.dumps({"schema_version": "1.0", "enabled": True,
                "project_root": str(ROOT), "state_file": "state.json", "audit_file": "audit.jsonl",
                "quad_size": 64}), encoding="utf8")
            host = TokenSelectedHost()
            service = live_service.LiveSpatialService(config, host=host)
            server = mcp.LiveSpatialMCPServer(service, spatial_task_only=True,
                                             default_session_id="schema-scope-default")
            records = []
            reference = None
            base = {"target": {"id": "a"}, "candidates": [{"id": "b"}]}
            for mode, extra in (("OFF", {}), ("vertices", {"geometry": GEOMETRY}),
                    ("full", {"geometry": dict(GEOMETRY, include_triangles=True)})):
                arguments = copy.deepcopy(dict(base, **extra))
                wire = server._call_tool(TOOL, arguments)
                self.assertFalse(wire["isError"])
                self.assertEqual(len(wire["content"]), 1)
                self.assertEqual(wire["content"][0]["type"], "text")
                body = json.loads(wire["content"][0]["text"])
                self.assertEqual(body["status"], "observed")
                self.assertEqual(body["context"]["runtime_source_sha256"], RUNTIME_SOURCE_SHA256)
                current_core = {key: value for key, value in body.items() if key not in ("trace_id", "geometry")}
                if reference is None:
                    reference = current_core
                    self.assertNotIn("geometry", body)
                else:
                    self.assertEqual(current_core, reference)
                    selected = body["geometry"]["objects"][0]
                    self.assertEqual(selected["object_id"], "a")
                    self.assertEqual(selected["vertices_world"], host.scene["meshes"][0]["vertices"])
                    if mode == "full":
                        self.assertEqual(selected["triangles"], host.scene["meshes"][0]["faces"])
                    else:
                        self.assertNotIn("triangles", selected)
                self.assertEqual(arguments, dict(base, **extra))
                records.append({"mode": mode, "arguments": arguments, "raw_tool_result": wire,
                                "result": body})
            self.assertEqual(len(host.selected_calls), 3)
            self.assertEqual(host.calls, 0)
            self.assertFalse(service.state_path.exists())
            EVIDENCE["finite_dispatch_controls"] = records
            EVIDENCE["finite_dispatch_counts"] = {"selected_captures": 3, "host_writes": host.calls,
                "Blender_sessions": 0, "actual_RPC": 0, "scope": "existing finite memory host and actual product kernels"}

    def test_bounded_evaluator_unknown_keyword_is_explicit_error(self):
        with self.assertRaisesRegex(AssertionError, "unsupported visited schema keyword"):
            EVALUATOR({"unevaluatedProperties": False}, {})
        self.assertTrue(EVALUATOR(True, {}))
        self.assertFalse(EVALUATOR(False, {}))
        EVIDENCE["evaluator_scope"] = {
            "full_JSON_Schema_validator": False,
            "unknown_keyword_policy": "AssertionError before accepting the visited node",
            "source": EVALUATOR_SOURCE,
        }
