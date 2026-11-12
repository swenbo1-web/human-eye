"""Independent reconstruction and compatibility checks for scan display facts."""

from __future__ import annotations

import copy
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from human_eye_plugin import live_spatial_mcp as mcp


BATCH = ROOT / "verification/m4_surface_scan_consumption_001"
SCHEMA_PYTHON = "C:/Users/Administrator/AppData/Local/uv/cache/archive-v0/_ruafSbD2XWAGOzS/Scripts/python.exe"
SCHEMA_RECORDS = []
SCHEMA_REQUESTS = []
SEALED = []
for cell in ("P1", "P2", "P3"):
    consumer = json.loads((BATCH / "cells" / cell / "CONSUMER.json").read_bytes())
    for attempt in consumer["tool_calls"]:
        item = attempt["item"]
        if item["tool"] != "human_eye_scene_observe":
            continue
        raw = item["result"]["content"][0]["text"]
        value = json.loads(raw)
        if value.get("result_kind") == "surface_scan":
            SEALED.append((cell, value, raw))


def bits(value):
    return struct.pack(">d", value)


def text_result(value, **options):
    wire = mcp._tool_result(value, is_error=False, **options)
    if len(wire["content"]) != 1 or wire["content"][0]["type"] != "text":
        raise AssertionError("Expected one scan text block")
    return wire, json.loads(wire["content"][0]["text"])


def original_facts(original):
    return [
        (row["objects"][0]["id"], row["objects"][0]["name"],
         row["objects"][1]["id"], row["objects"][1]["name"], bits(row["distance_m"]))
        for row in original["matches"]
    ]


def recover_facts(compact):
    """Decode through the published column labels, independently of projection."""
    if not isinstance(compact.get("display_encoding"), str):
        raise AssertionError("Missing versioned display encoding")
    columns = compact["match_columns"]
    if len(columns) != len(set(columns)):
        raise AssertionError("Duplicate match columns")
    required = {"object_a", "object_b", "object_a_ref", "object_b_ref", "distance_m", "distance_mm"}
    if not required.issubset(columns):
        raise AssertionError("Missing facts in compact rows")
    table = compact["objects"]
    facts = []
    for values in compact["matches"]:
        if len(values) != len(columns):
            raise AssertionError("Row length differs from column declaration")
        row = dict(zip(columns, values))
        first, second = row["object_a_ref"], row["object_b_ref"]
        if type(first) is not int or type(second) is not int:
            raise AssertionError("Object references must be integers")
        if not 0 <= first < len(table) or not 0 <= second < len(table):
            raise AssertionError("Object reference is outside the local table")
        a, b = table[first], table[second]
        if row["object_a"] != a["name"] or row["object_b"] != b["name"]:
            raise AssertionError("Readable names disagree with referenced identities")
        if type(row["distance_m"]) not in (int, float) or not math.isfinite(row["distance_m"]):
            raise AssertionError("Raw measurement must remain finite binary64")
        facts.append((a["id"], a["name"], b["id"], b["name"], bits(row["distance_m"])))
    return facts


def recover_metadata(compact):
    annotations = [copy.deepcopy(compact["match_metadata"]) for _ in compact["matches"]]
    seen = set()
    for exceptional in compact["match_exceptions"]:
        index = exceptional["match_index"]
        if type(index) is not int or not 0 <= index < len(annotations) or index in seen:
            raise AssertionError("Invalid or duplicate exception index")
        seen.add(index)
        annotations[index].update(exceptional["metadata"])
    return annotations


def check_projection(test, original, compact):
    test.assertEqual(recover_facts(compact), original_facts(original))
    for key, value in original.items():
        if key != "matches":
            test.assertEqual(compact[key], value, key)
    test.assertEqual(compact["unit"], "m")
    test.assertEqual(len(compact["matches"]), len(original["matches"]))
    original_metadata = [
        {key: value for key, value in row.items()
         if key not in ("objects", "distance_m", "point_a_world", "point_b_world")}
        for row in original["matches"]
    ]
    test.assertEqual(json.dumps(recover_metadata(compact), sort_keys=True),
                     json.dumps(original_metadata, sort_keys=True))


def fixture(distances=(0.0, 0.001)):
    value = copy.deepcopy(SEALED[0][1])
    source = copy.deepcopy(value["matches"][0])
    value["matches"] = []
    for index, distance in enumerate(distances):
        row = copy.deepcopy(source)
        row["objects"] = [dict(id="object-a-" + str(index), name="same_name"),
                          dict(id="object-b-" + str(index), name="same_name")]
        row["distance_m"] = float(distance)
        value["matches"].append(row)
    value["coverage"].update(objects=len(distances) * 2, measured_match=len(distances),
                             measured_nonmatch=0, unknown=0, deferred=0)
    value["delivery"].update(matches_total=len(distances), delivered_matches=len(distances))
    return value


class SurfaceScanProjectionIndependentTests(unittest.TestCase):
    def test_six_sealed_responses_preserve_all_raw_measurements_and_identity(self):
        self.assertEqual(len(SEALED), 6)
        for cell, value, raw in SEALED:
            with self.subTest(cell=cell, trace=value["trace_id"]):
                original = copy.deepcopy(value)
                projected = mcp.project_surface_scan_brief(value)
                self.assertIsNotNone(projected)
                check_projection(self, value, projected)
                _, decoded = text_result(value)
                check_projection(self, value, decoded)
                self.assertEqual(value, original)
                self.assertEqual(len(decoded["matches"]), 71)
                self.assertEqual(decoded["coverage"]["objects"], 24)
                self.assertEqual(len(decoded["objects"]), 22)
                self.assertLessEqual(len(json.dumps(decoded, ensure_ascii=False, separators=(",", ":")).encode()), 10 * 1024)
                self.assertEqual(len(raw.encode()), 34754)

    def test_empty_matches_keep_complete_coverage(self):
        value = fixture(())
        _, projected = text_result(value)
        check_projection(self, value, projected)
        self.assertEqual(projected["objects"], [])
        self.assertEqual(projected["status"], "complete")

    def test_partial_unknown_and_upstream_delivery_truncation_remain_visible(self):
        for status in ("partial", "unknown"):
            with self.subTest(status=status):
                value = fixture()
                value.update(status=status, scope_issues=[dict(reason="unknown instance")],
                             unresolved=[dict(status="unknown", reason="budget", pairs=2)])
                value["coverage"].update(unknown=2, deferred=1, catalog_scope_confirmed=False)
                value["delivery"].update(matches_total=9, delivered_matches=2, complete=False,
                                          reason="surface_scan_delivery_budget")
                _, compact = text_result(value)
                check_projection(self, value, compact)
                self.assertFalse(compact["delivery"]["complete"])
                self.assertEqual(compact["status"], status)

    def test_names_with_unicode_and_duplicate_display_names_recover_by_index(self):
        value = fixture()
        for row in value["matches"]:
            row["objects"][0]["name"] = "蓝色零件 / 同名 🌐"
            row["objects"][1]["name"] = "蓝色零件 / 同名 🌐"
        _, compact = text_result(value)
        check_projection(self, value, compact)
        self.assertEqual(len(compact["objects"]), 4)
        self.assertEqual(len({obj["id"] for obj in compact["objects"]}), 4)

    def test_shared_endpoints_use_one_identity_record(self):
        value = fixture()
        value["matches"][1]["objects"][0] = copy.deepcopy(value["matches"][0]["objects"][0])
        _, compact = text_result(value)
        check_projection(self, value, compact)
        self.assertEqual(len(compact["objects"]), 3)

    def test_integer_measurement_type_and_endpoint_extra_fields_survive(self):
        value = fixture()
        value["matches"][0]["distance_m"] = 1
        value["matches"][0]["objects"][0]["instance"] = dict(known=False, source="future")
        _, compact = text_result(value)
        check_projection(self, value, compact)
        row = dict(zip(compact["match_columns"], compact["matches"][0]))
        self.assertIs(type(row["distance_m"]), int)
        self.assertEqual(compact["objects"][row["object_a_ref"]]["instance"],
                         dict(known=False, source="future"))

    def test_signed_zero_and_threshold_neighbors_keep_binary64_bits(self):
        threshold = 0.002
        values = (-0.0, 0.0, math.nextafter(threshold, 0.0), threshold,
                  math.nextafter(threshold, math.inf))
        original = fixture(values)
        _, compact = text_result(original)
        check_projection(self, original, compact)
        self.assertNotEqual(bits(-0.0), bits(0.0))
        self.assertEqual(len(compact["matches"]), len(values))

    def test_derived_mm_is_finite_and_nonzero_across_binary64_extremes(self):
        values = (-0.0, 0.0, math.ulp(0.0), 1e-320, 1e-200, 0.001,
                  1.23456789012345, 1e300, sys.float_info.max)
        original = fixture(values)
        _, compact = text_result(original)
        check_projection(self, original, compact)
        columns = compact["match_columns"]
        for values in compact["matches"]:
            row = dict(zip(columns, values))
            metres, millimetres = row["distance_m"], row["distance_mm"]
            with self.subTest(metres=metres), localcontext() as context:
                context.prec = 1100
                expected = Decimal.from_float(metres) * Decimal(1000)
                actual = Decimal.from_float(millimetres) if isinstance(millimetres, float) else Decimal(millimetres)
                self.assertTrue(actual.is_finite())
                if metres == 0:
                    self.assertTrue(actual.is_zero())
                    self.assertEqual(actual.is_signed(), math.copysign(1, metres) < 0)
                else:
                    self.assertGreater(actual, 0)
                    rounded = metres * 1000
                    if math.isfinite(rounded):
                        self.assertLessEqual(abs(actual - expected), Decimal.from_float(math.ulp(rounded)))
                    else:
                        self.assertIsInstance(millimetres, str)
                        self.assertLessEqual(abs(actual - expected), abs(expected) * Decimal("1e-15"))

    def test_top_level_future_and_unsupported_facts_are_preserved(self):
        value = fixture()
        value["unsupported_objects"] = [dict(id="external", name="unknown", reason="unsupported")]
        value["future_safety_facts"] = dict(unknown=[False, 0, None, "outside source"])
        _, compact = text_result(value)
        check_projection(self, value, compact)

    def test_explicit_full_matches_old_scan_serialization_exactly(self):
        for _, value, raw in SEALED:
            wire, decoded = text_result(value, response_detail="full")
            self.assertEqual(wire["content"][0]["text"], raw)
            self.assertEqual(decoded, value)
            self.assertNotIn("display_encoding", decoded)

    def test_scan_default_and_brief_share_one_projection(self):
        value = SEALED[0][1]
        implicit, _ = text_result(value)
        explicit, _ = text_result(value, response_detail="brief")
        self.assertEqual(implicit, explicit)

    def test_tool_errors_keep_original_detailed_payload(self):
        value = fixture()
        value.update(status="error", error="source unavailable")
        for detail in (None, "brief", "full"):
            wire = mcp._tool_result(value, is_error=True, response_detail=detail)
            decoded = json.loads(wire["content"][0]["text"])
            self.assertTrue(wire["isError"])
            self.assertEqual(decoded, value)
            self.assertNotIn("display_encoding", decoded)

    def test_projection_exception_and_none_preserve_exact_full(self):
        value = SEALED[0][1]
        full = mcp._tool_result(value, is_error=False, response_detail="full")
        for kwargs in (dict(return_value=None), dict(side_effect=ValueError("projection failure")),
                       dict(return_value={"nonfinite": math.nan})):
            with self.subTest(kwargs=str(kwargs)), patch.object(mcp, "project_surface_scan_brief", **kwargs):
                self.assertEqual(mcp._tool_result(value, is_error=False), full)

    def test_unknown_row_semantics_are_preserved_or_fall_back_to_full(self):
        changes = [dict(witness_status="unknown", witness_reason="publication limit"),
                   dict(method="future-distance-algorithm", uncertainty_m=0.5),
                   dict(future_row_safety=dict(known=False, reason="source boundary"))]
        for changeset in changes:
            with self.subTest(changes=changeset):
                value = fixture()
                value["matches"][0].update(changeset)
                full = mcp._tool_result(value, is_error=False, response_detail="full")
                candidate = mcp.project_surface_scan_brief(value)
                if candidate is None:
                    self.assertEqual(mcp._tool_result(value, is_error=False), full)
                else:
                    check_projection(self, value, candidate)
                    visible = json.dumps(candidate, ensure_ascii=False)
                    for key, expected in changeset.items():
                        self.assertIn(key, visible)
                        self.assertIn(json.dumps(expected, ensure_ascii=False), visible)

    def test_metadata_presence_boolean_zero_signed_zero_and_exceptions_roundtrip(self):
        value = fixture((0.0, 0.001, 0.0015))
        value["matches"][0].update(quality=False, signed=-0.0, witness_status="unknown",
                                    witness_reason="projection budget", future=dict(a=[None, False]))
        value["matches"][1].update(quality=0, signed=0.0, future=dict(a=[None, 0]))
        value["matches"][2].pop("method")
        _, compact = text_result(value)
        check_projection(self, value, compact)
        metadata = recover_metadata(compact)
        self.assertIs(metadata[0]["quality"], False)
        self.assertIs(type(metadata[1]["quality"]), int)
        self.assertNotIn("method", metadata[2])
        self.assertNotEqual(bits(metadata[0]["signed"]), bits(metadata[1]["signed"]))

    def test_reserved_layout_collisions_and_bad_rows_fall_back_to_full(self):
        changes = [lambda value: value.update(display_encoding="future"),
                   lambda value: value["matches"][0].update(distance_m=True),
                   lambda value: value["matches"][0].update(point_a_world=[0, 0]),
                   lambda value: value["matches"][0].update(distance_m=-1),
                   lambda value: value.update(coordinate_frame="unrecognized")]
        for change in changes:
            with self.subTest(change=repr(change)):
                value = fixture()
                change(value)
                self.assertIsNone(mcp.project_surface_scan_brief(value))
                self.assertEqual(mcp._tool_result(value, is_error=False),
                                 mcp._tool_result(value, is_error=False, response_detail="full"))

    def test_detached_projection_cannot_mutate_original_source(self):
        value = fixture()
        value["matches"][0]["future"] = dict(known=False)
        original = copy.deepcopy(value)
        compact = mcp.project_surface_scan_brief(value)
        compact["binding"]["document_epoch"] = "changed"
        compact["objects"][0]["name"] = "changed"
        compact["match_exceptions"][0]["metadata"]["future"]["known"] = True
        compact["matches"][0][0] = "changed"
        self.assertEqual(value, original)

    def test_original_nonfinite_payload_is_rejected(self):
        for number in (math.nan, math.inf, -math.inf):
            with self.subTest(number=number):
                value = fixture((number,))
                with self.assertRaises(ValueError):
                    mcp._tool_result(value, is_error=False)

    def test_independent_decoder_detects_reconstruction_regressions(self):
        original = SEALED[0][1]
        _, good = text_result(original)
        broken = copy.deepcopy(good)
        broken["matches"].pop()
        with self.assertRaises(AssertionError):
            check_projection(self, original, broken)
        broken = copy.deepcopy(good)
        ref = broken["match_columns"].index("object_a_ref")
        broken["matches"][0][ref] = len(broken["objects"])
        with self.assertRaises(AssertionError):
            check_projection(self, original, broken)
        broken = copy.deepcopy(good)
        distance = broken["match_columns"].index("distance_m")
        broken["matches"][0][distance] *= 1000
        with self.assertRaises(AssertionError):
            check_projection(self, original, broken)
        original = fixture()
        original["status"] = "partial"
        _, broken = text_result(original)
        broken["status"] = "complete"
        with self.assertRaises(AssertionError):
            check_projection(self, original, broken)

    def test_non_scan_structured_defaults_remain_old_payload(self):
        for kind in ("task_query", "surface_nearest", "scene_directory"):
            with self.subTest(kind=kind):
                value = dict(result_kind=kind, status="complete", unknown=[0, False, None], future=dict(a=1))
                implicit, body = text_result(value)
                explicit, _ = text_result(value, response_detail="full")
                self.assertEqual(implicit, explicit)
                self.assertEqual(body, value)
                self.assertEqual(implicit["content"][0]["text"], json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))


class StaticScanService:
    def __init__(self, value):
        self.value = value
        self.calls = []
        self.budget_checks = []

    def observe(self, session_id, **kwargs):
        self.calls.append((session_id, copy.deepcopy(kwargs)))
        return copy.deepcopy(self.value)

    def _check_request_budget(self, phase):
        self.budget_checks.append(phase)


class SurfaceScanRoutingIndependentTests(unittest.TestCase):
    def setUp(self):
        self.service = StaticScanService(SEALED[0][1])
        self.server = mcp.LiveSpatialMCPServer(self.service, default_session_id="scan-display-check")

    def call(self, **changes):
        args = dict(query=dict(mode="surface_scan", threshold_m=0.002), **changes)
        return self.server.handle_jsonrpc_message(dict(jsonrpc="2.0", id=8, method="tools/call",
                                                       params=dict(name="human_eye_scene_observe", arguments=args)))["result"]

    def test_actual_default_brief_full_routing_and_internal_call_identity(self):
        responses = [self.call(), self.call(response_detail="brief"), self.call(response_detail="full")]
        self.assertEqual(responses[0], responses[1])
        self.assertIn("display_encoding", json.loads(responses[0]["content"][0]["text"]))
        self.assertEqual(json.loads(responses[2]["content"][0]["text"]), self.service.value)
        self.assertEqual(self.service.calls[0], self.service.calls[1])
        self.assertEqual(self.service.calls[0], self.service.calls[2])
        self.assertNotIn("response_detail", self.service.calls[0][1])
        self.assertEqual(self.service.budget_checks, ["before_task_publication"] * 3)

    def test_schema_conditional_default_and_full_meaning_are_documented(self):
        tools = self.server.handle_jsonrpc_message(dict(jsonrpc="2.0", id=1, method="tools/list"))["result"]["tools"]
        self.assertEqual(len(tools), 5)
        observe = next(row for row in tools if row["name"] == "human_eye_scene_observe")
        schema = observe["inputSchema"]
        cases = [dict(value=dict(query=dict(mode="surface_scan", threshold_m=.002), **detail), valid=True)
                 for detail in ({}, dict(response_detail="brief"), dict(response_detail="full"))]
        cases += [dict(value=dict(query=dict(mode="surface_scan", threshold_m=threshold)), valid=True)
                  for threshold in (0, 1e308)]
        cases += [dict(value=value, valid=False) for value in (
            dict(query=dict(mode="surface_scan", threshold_m=-1)),
            dict(query=dict(mode="surface_scan", threshold_m=1., objects=[])),
            dict(query=dict(mode="surface_scan", threshold_m=1.), include_image=True),
            dict(query=dict(mode="surface_scan", threshold_m=1.), focal_id="a"),
            dict(query=dict(mode="surface_scan")),
            dict(query=dict(mode="surface_scan", threshold_m=.002), response_detail=None),
        )]
        jobs = [dict(name="ordinary_observe", schema=schema, cases=cases),
                dict(name="existing_mesh_surface_query", schema=schema["properties"]["query"],
                     cases=[dict(value=dict(mode="mesh_surface", threshold_m=threshold), valid=False)
                            for threshold in (0, .02)])]
        SCHEMA_REQUESTS.append(dict(jobs=jobs))
        process = subprocess.run([SCHEMA_PYTHON, "-I", "-B", "-X", "utf8", str(Path(__file__).with_name("validate_schema.py"))],
                                 input=json.dumps(dict(jobs=jobs), ensure_ascii=False).encode("utf8"),
                                 capture_output=True, check=True)
        record = json.loads(process.stdout)
        self.assertEqual(record["check_count"], 13)
        SCHEMA_RECORDS.append(record)
        description = observe["description"] + " " + schema["properties"]["response_detail"]["description"]
        for term in ("surface_scan", "brief", "full", "current", "binding"):
            self.assertIn(term, description)

    def test_invalid_detail_is_rejected_before_service(self):
        for detail in (None, True, 0, "short", [], {}):
            with self.subTest(detail=detail):
                self.assertTrue(self.call(response_detail=detail)["isError"])
        self.assertEqual(self.service.calls, [])

    def test_full_is_a_new_observation_and_uses_current_binding(self):
        first = json.loads(self.call()["content"][0]["text"])
        self.service.value["binding"]["scene_revision"] = "changed-current-scene"
        self.service.value["trace_id"] = "fresh-trace"
        second = json.loads(self.call(response_detail="full")["content"][0]["text"])
        self.assertEqual(len(self.service.calls), 2)
        self.assertNotEqual(first["binding"], second["binding"])
        self.assertEqual(second["trace_id"], "fresh-trace")
        self.assertEqual(second, self.service.value)


if __name__ == "__main__":
    unittest.main()
