"""Offline checks using frozen engineering receipts and synthetic marker packets."""

import copy
import io
import importlib.util
import math
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_continuity as check


class ContinuityQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prior = check.ROOT / "verification/m4_surface_scan_compact_facts_001/engineering/run_01"
        cls.prior = prior
        cls.old = json.loads((prior / "RESULTS.json").read_bytes())
        cls.audit = [json.loads(line) for line in (prior / "audit.jsonl").read_bytes().splitlines()]
        cls.source = {state: json.loads((prior / (state.lower() + "_ACTUAL_SNAPSHOT.json")).read_bytes()) for state in ("BASE", "EDIT")}

    def fixture(self, turn="BASE"):
        label = {"BASE": "base_default", "REPEAT": "base_brief", "EDIT": "edit_default"}[turn]
        row = copy.deepcopy(next(row for row in self.old["business"] if row["state"] == label))
        request = row["request"]
        # Only the REPEAT unit fixture is synthetic. Its historical brief result
        # is byte-identical in facts to default; no new request is executed here.
        request["params"]["arguments"].pop("response_detail", None)
        state = "EDIT" if turn == "EDIT" else "BASE"
        return [row["body"], copy.deepcopy(self.audit), row["work_events"], copy.deepcopy(self.source[state]), turn, request]

    def verify(self, *args):
        # The old REPEAT record is synthetic only at its default request flag.
        # Actual capture bytes and retained resources still come from its wire.
        host = args[2][0] if args[2] else self.fixture()[2][0]
        captured = check.read_capture(self.prior / "native", host)
        return check.verify_c_turn(*args, capture=captured)

    def marker_rows(self):
        rows = []
        for state in ("BASE", "BASE", "EDIT"):
            reference = check.fixed_json(check.QUAL / (state + "_SNAPSHOT.json"), check.SNAPSHOT_SHA[state])
            objects = sorted(reference["objects"], key=lambda row: row["name"])
            rows.append({"marker_token": "continuity-engineering-N-001", "marker_generation": 1,
                         "pid": 1234, "namespace_id": 5678, "unit_scale": reference["scale_length"],
                         "objects": [{"name": obj["name"], "session_uid": index,
                                      "matrix_world": copy.deepcopy(obj["matrix_world"])}
                                     for index, obj in enumerate(objects, 100)]})
        return rows

    def test_actual_historical_default_receipts_match_truth(self):
        for turn in ("BASE", "EDIT"):
            with self.subTest(turn=turn):
                result = self.verify(*self.fixture(turn))
                self.assertEqual(result["matches"], check.EXPECTED_MATCHES[turn])
                self.assertEqual(result["new_kernel_calls"], check.EXPECTED_KERNELS[turn])

    def real_owner(self):
        folder = check.ROOT / "verification/m4_surface_scan_continuity_001/episodes/C"
        row = json.loads((folder / "TURN_BASE.json").read_bytes())
        initial = json.loads((folder / "owner/INITIAL.json").read_bytes())
        return folder, row, initial

    def runner(self):
        path = Path(__file__).parents[1] / "engineering/run_candidate.py"
        spec = importlib.util.spec_from_file_location("_fix1_actual_engineering_entry", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_original_owner_failure_and_actual_runner_interface_fix(self):
        folder, row, initial = self.real_owner()
        reference = check.fixed_json(check.QUAL / "BASE_SNAPSHOT.json", check.SNAPSHOT_SHA["BASE"])
        with self.assertRaisesRegex(AssertionError, "actual geometry or source fields differ from qualified state"):
            check.previous_verifier().bind_snapshot(initial, reference)
        runner = self.runner()
        for filename in ("INITIAL.json", "FINAL.json"):
            source = json.loads((folder / "owner" / filename).read_bytes())
            result = runner.verify_business(copy.deepcopy(row), folder, source, check)
            self.assertEqual(result["matches"], 71)
            self.assertEqual(result["new_kernel_calls"], 112)
            self.assertEqual(result["capture_report"]["transmitted_resources_this_capture"], 24)
            self.assertFalse(result["source_report"]["rich_source_metadata_verified"])
            self.assertTrue(result["source_report"]["missing_rich_top_fields"])
        original = json.loads((folder / "RESULTS.json").read_bytes())
        self.assertFalse(original["passed_before_publication"])
        self.assertEqual(original["execution_counts"], {"planned": 3, "attempted": 1, "completed": 0, "failed": 1, "not_run": 2})

    def test_narrow_snapshot_exact_types_shapes_and_values(self):
        _, _, original = self.real_owner()
        reference = check.fixed_json(check.QUAL / "BASE_SNAPSHOT.json", check.SNAPSHOT_SHA["BASE"])
        cases = [
            ("unit_bool", "source_finite_float_unit"),
            ("unit_nan", "source_finite_float_unit"),
            ("unit_changed", "source_unit_matches_reference"),
            ("missing_object", "source_complete_24_objects"),
            ("duplicate_object", "source_unique_sorted_object_names"),
            ("extra_field", "actual geometry or source fields differ"),
            ("missing_field", "source_object_geometry_fields"),
            ("vertex_bool", "source_finite_float_vertices"),
            ("vertex_int", "source_finite_float_vertices"),
            ("vertex_nan", "source_finite_float_vertices"),
            ("vertex_inf", "source_finite_float_vertices"),
            ("vertex_shape", "source_vertex_shape"),
            ("vertex_changed", "source_geometry_matches:Obj_001:vertices_local"),
            ("face_bool", "source_integer_face_indices"),
            ("face_float", "source_integer_face_indices"),
            ("face_negative", "source_integer_face_indices"),
            ("face_range", "source_integer_face_indices"),
            ("face_changed", "source_geometry_matches:Obj_001:faces"),
            ("matrix_shape", "source_matrix_shape"),
            ("matrix_bool", "source_finite_float_matrix"),
            ("matrix_int", "source_finite_float_matrix"),
            ("matrix_nan", "source_finite_float_matrix"),
            ("matrix_inf", "source_finite_float_matrix"),
            ("matrix_changed", "source_geometry_matches:Obj_001:matrix_world"),
        ]
        for name, reason in cases:
            source = copy.deepcopy(original)
            obj = source["objects"][0]
            if name == "unit_bool":
                source["unit_scale_m"] = True
            elif name == "unit_nan":
                source["unit_scale_m"] = math.nan
            elif name == "unit_changed":
                source["unit_scale_m"] = .001
            elif name == "missing_object":
                source["objects"].pop()
            elif name == "duplicate_object":
                source["objects"][1] = copy.deepcopy(obj)
            elif name == "extra_field":
                source["unexpected"] = True
            elif name == "missing_field":
                del obj["faces"]
            elif name == "vertex_bool":
                obj["vertices_local"][0][0] = True
            elif name == "vertex_int":
                obj["vertices_local"][0][0] = 0
            elif name == "vertex_nan":
                obj["vertices_local"][0][0] = math.nan
            elif name == "vertex_inf":
                obj["vertices_local"][0][0] = math.inf
            elif name == "vertex_shape":
                obj["vertices_local"][0].pop()
            elif name == "vertex_changed":
                obj["vertices_local"][0][0] += .001
            elif name == "face_bool":
                obj["faces"][0][0] = True
            elif name == "face_float":
                obj["faces"][0][0] = 0.
            elif name == "face_negative":
                obj["faces"][0][0] = -1
            elif name == "face_range":
                obj["faces"][0][0] = len(obj["vertices_local"])
            elif name == "face_changed":
                obj["faces"][0] = list(reversed(obj["faces"][0]))
            elif name == "matrix_shape":
                obj["matrix_world"].pop()
            elif name == "matrix_bool":
                obj["matrix_world"][0][0] = True
            elif name == "matrix_int":
                obj["matrix_world"][0][0] = 1
            elif name == "matrix_nan":
                obj["matrix_world"][0][0] = math.nan
            elif name == "matrix_inf":
                obj["matrix_world"][0][0] = math.inf
            elif name == "matrix_changed":
                obj["matrix_world"][0][0] += .001
            with self.subTest(case=name), self.assertRaisesRegex(AssertionError, reason):
                check.bind_source_snapshot(source, reference)

    def test_rich_contract_preserved(self):
        reference = check.fixed_json(check.QUAL / "BASE_SNAPSHOT.json", check.SNAPSHOT_SHA["BASE"])
        self.assertTrue(check.bind_source_snapshot(reference, reference)["rich_source_metadata_verified"])
        source = copy.deepcopy(reference)
        source["objects"][0]["parent"] = "changed"
        with self.assertRaisesRegex(AssertionError, "actual geometry or source fields differ"):
            check.bind_source_snapshot(source, reference)

    def test_actual_capture_binding_and_retained_repeat_resources(self):
        for turn, expected_new in (("BASE", 24), ("REPEAT", 0), ("EDIT", 0)):
            report = self.verify(*self.fixture(turn))
            self.assertEqual(report["capture_report"]["transmitted_resources_this_capture"], expected_new)
            self.assertEqual(report["capture_report"]["resolved_resource_count"], 24)
            self.assertFalse(report["capture_report"]["rich_source_metadata_verified"])

    def test_wire_history_missing_or_foreign_resources_rejected(self):
        fixture = self.fixture("REPEAT")
        host = fixture[2][0]
        wire = self.prior / "native/WIRE"
        original_read = Path.read_bytes
        index_path = wire / "INDEX.json"
        original_index = json.loads(original_read(index_path))
        current = host["sequence"]
        # Retained resources must come from this worker's earlier capture.
        limited_index = [row for row in original_index if row["sequence"] == current]
        def without_prior_history(path):
            if path == index_path:
                return json.dumps(limited_index).encode("utf8")
            return original_read(path)
        with patch.object(Path, "read_bytes", without_prior_history):
            missing = check.read_capture(self.prior / "native", host)
        with self.assertRaisesRegex(AssertionError, "capture_resolved_resource_reference"):
            check.verify_c_turn(*fixture, capture=missing)

        response_path = wire / str(current).zfill(3) / "RESPONSE.bin"
        response = json.loads(original_read(response_path))
        stdout = response["result"]["result"]
        prefix = "HUMAN_EYE_BLENDER_MCP:"
        envelope = json.loads(next(line[len(prefix):] for line in stdout.splitlines() if line.startswith(prefix)))
        envelope["result"]["capture"]["binding"]["host_identity"]["document_epoch"] = "foreign-document"
        response["result"]["result"] = prefix + json.dumps(envelope, ensure_ascii=False) + "\n"
        response_raw = json.dumps(response, ensure_ascii=False).encode("utf8")
        changed_index = copy.deepcopy(original_index)
        next(row for row in changed_index if row["sequence"] == current)["response_attempted_bytes"] = len(response_raw)
        def substituted_read(path):
            if path == index_path:
                return json.dumps(changed_index).encode("utf8")
            if path == response_path:
                return response_raw
            return original_read(path)
        with patch.object(Path, "read_bytes", substituted_read):
            with self.assertRaisesRegex(AssertionError, "capture_history_same_host_document"):
                check.read_capture(self.prior / "native", host)

    def test_capture_source_and_geometry_tampering(self):
        fixture = self.fixture()
        original = check.read_capture(self.prior / "native", fixture[2][0])
        cases = [
            ("event", "capture_host_event_binding"),
            ("script", "capture_host_event_binding"),
            ("frame", "capture_fixed_frame"),
            ("unit", "capture_unit_scale"),
            ("document", "capture_document_binding"),
            ("directory", "capture_directory_binding"),
            ("source", "capture_fixed_host_source"),
            ("coverage", "capture_all_24_object_coverage"),
            ("unsupported", "capture_host_supported_sources"),
            ("mesh_duplicate", "capture_mesh_identity"),
            ("resource_missing", "capture_resolved_resource_reference"),
            ("vertex", "capture_geometry_matches:"),
            ("matrix", "capture_geometry_matches:"),
            ("scale", "capture_mesh_unit_scale"),
            ("live", "capture_live_resource_set"),
        ]
        for name, reason in cases:
            capture = copy.deepcopy(original)
            binding = capture["delta"]["capture"]["binding"]
            mesh = capture["delta"]["capture"]["capture"]["meshes"][0]
            if name == "event":
                capture["sequence"] += 1
            elif name == "script":
                capture["script_sha256"] = "changed"
            elif name == "frame":
                binding["frame"] = True
            elif name == "unit":
                binding["scale_length"] = True
            elif name == "document":
                binding["host_identity"]["document_epoch"] = "changed"
            elif name == "directory":
                binding["directory_sha256"] = "changed"
            elif name == "source":
                binding["host_source_sha256"] = "changed"
            elif name == "coverage":
                capture["delta"]["capture"]["coverage"].pop()
            elif name == "unsupported":
                capture["delta"]["capture"]["coverage"][0]["source_status"] = "unsupported"
            elif name == "mesh_duplicate":
                capture["delta"]["capture"]["capture"]["meshes"][1] = copy.deepcopy(mesh)
            elif name == "resource_missing":
                capture["retained_resources"] = []
            elif name == "vertex":
                capture["retained_resources"][0]["vertices_local"][0][0] += .001
            elif name == "matrix":
                mesh["_scene_resource"]["matrix"][0][0] += .001
            elif name == "scale":
                mesh["_scene_resource"]["scale"] = True
            elif name == "live":
                capture["delta"]["live_resources"].pop()
            with self.subTest(case=name), self.assertRaisesRegex(AssertionError, reason):
                check.verify_c_turn(*fixture, capture=capture)

    def test_synthetic_repeat_sequence_contract(self):
        reports = [self.verify(*self.fixture(turn)) for turn in check.TURNS]
        self.assertTrue(check.verify_c_sequence(reports)["passed"])

    def test_raw_fact_and_actual_source_tampering_rejected(self):
        fixture = self.fixture()
        fixture[0]["matches"][0][4] = .009
        fixture[0]["matches"][0][5] = 9.0
        with self.assertRaises(AssertionError):
            self.verify(*fixture)
        fixture = self.fixture()
        fixture[3]["objects"][0]["matrix_world"][2][3] += .001
        with self.assertRaisesRegex(AssertionError, "actual geometry or source fields differ"):
            self.verify(*fixture)

    def test_request_negative_reasons(self):
        mutations = [
            ("wrong_tool", "ordinary_observe_tool"),
            ("explicit_brief", "default_response_detail_required"),
            ("image", "zero_image_request"),
            ("threshold", "fixed_surface_scan_query"),
            ("missing_session", "nonempty_session_id"),
        ]
        for name, reason in mutations:
            with self.subTest(case=name):
                fixture = self.fixture()
                params = fixture[-1]["params"]
                if name == "wrong_tool":
                    params["name"] = "other_tool"
                elif name == "explicit_brief":
                    params["arguments"]["response_detail"] = "brief"
                elif name == "image":
                    params["arguments"]["include_image"] = True
                elif name == "threshold":
                    params["arguments"]["query"]["threshold_m"] = .003
                else:
                    del params["arguments"]["session_id"]
                with self.assertRaisesRegex(AssertionError, reason):
                    self.verify(*fixture)

    def test_duplicate_audit_and_wrong_capture_count(self):
        for event in ("observe", "request_trace"):
            fixture = self.fixture()
            fixture[1].append(copy.deepcopy(next(row for row in fixture[1] if row.get("event") == event and row.get("trace_id") == fixture[0]["trace_id"])))
            with self.subTest(event=event), self.assertRaisesRegex(AssertionError, "unique_request_observe_and_trace"):
                self.verify(*fixture)
        for count in (0, 2):
            fixture = self.fixture()
            fixture[2] = fixture[2] * count
            with self.subTest(count=count), self.assertRaisesRegex(AssertionError, "exactly_one_host_capture"):
                self.verify(*fixture)

    def test_host_protection_negative_reasons(self):
        mutations = [
            ("status", "failed", "host_capture_completed"),
            ("script_error", {"message": "failed"}, "host_capture_completed"),
            ("terminal_geometry_and_file_checks_passed", False, "host_terminal_protection"),
            ("changed_or_new_PNG_files", ["new.png"], "no_PNG_created"),
            ("render_events_after", 1, "no_render_event"),
        ]
        for field, value, reason in mutations:
            fixture = self.fixture()
            fixture[2][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(AssertionError, reason):
                self.verify(*fixture)

    def test_wrong_trace_or_kernel_reasons(self):
        for field in ("capture", "image", "kernel"):
            fixture = self.fixture()
            trace = next(row["trace"] for row in fixture[1] if row.get("event") == "request_trace" and row.get("trace_id") == fixture[0]["trace_id"])
            reason = "one_completed_capture_span"
            if field == "capture":
                trace["spans"] = [span for span in trace["spans"] if span["name"] != "host.capture"]
            elif field == "image":
                trace["annotations"]["mcp_native_image_block_count"] = 1
                reason = "zero_delivered_images"
            else:
                observed = next(row for row in fixture[1] if row.get("event") == "observe" and row.get("trace_id") == fixture[0]["trace_id"])
                observed["task_work"]["kernel_calls"] = 111
                reason = "registered_new_kernel_count"
            with self.subTest(field=field), self.assertRaisesRegex(AssertionError, reason):
                self.verify(*fixture)

    def test_c_sequence_mismatches_rejected(self):
        reports = [self.verify(*self.fixture(turn)) for turn in check.TURNS]
        mutations = [
            ("session_id", "different", "same_C_session"),
            ("runtime_pid", -1, "same_C_runtime"),
            ("trace_id", reports[0]["trace_id"], "distinct_C_request_traces"),
        ]
        for field, value, reason in mutations:
            rows = copy.deepcopy(reports)
            rows[1][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(AssertionError, reason):
                check.verify_c_sequence(rows)
        rows = copy.deepcopy(reports)
        rows[1]["binding"]["scene_revision"] = "changed"
        with self.assertRaisesRegex(AssertionError, "unchanged_state_binding_equal"):
            check.verify_c_sequence(rows)
        rows = copy.deepcopy(reports)
        rows[2]["binding"] = copy.deepcopy(rows[1]["binding"])
        with self.assertRaisesRegex(AssertionError, "edited_state_binding_invalidates"):
            check.verify_c_sequence(rows)

    def test_native_marker_packet_and_qualified_float_pose(self):
        rows = self.marker_rows()
        self.assertTrue(check.verify_n_sequence(rows)["passed"])
        z = next(obj for obj in rows[2]["objects"] if obj["name"] == "Obj_008")["matrix_world"][2][3]
        self.assertEqual(z, -.000750000006519258)
        self.assertNotEqual(z, -.00075)

    def test_native_wrong_marker_pose_identity_and_units_rejected(self):
        mutations = [
            ("marker", "N_marker_token"), ("generation", "N_marker_generation"),
            ("process", "same_N_process"), ("namespace", "same_N_namespace"),
            ("unit", "N_unit_scale"), ("identity", "N_identity_survives_EDIT"),
            ("stale_pose", "N_frozen_current_pose:Obj_008"),
            ("decimal_pose", "N_frozen_current_pose:Obj_008"),
            ("extra_field", "N_marker_exact_fields"),
        ]
        for name, reason in mutations:
            rows = self.marker_rows()
            if name == "marker":
                rows[1]["marker_token"] = "other"
            elif name == "generation":
                rows[1]["marker_generation"] = 2
            elif name == "process":
                rows[2]["pid"] = 999
            elif name == "namespace":
                rows[2]["namespace_id"] = 999
            elif name == "unit":
                rows[2]["unit_scale"] = .001
            elif name == "identity":
                rows[2]["objects"][0]["session_uid"] = 999
            elif name in ("stale_pose", "decimal_pose"):
                obj = next(obj for obj in rows[2]["objects"] if obj["name"] == "Obj_008")
                obj["matrix_world"][2][3] = 0. if name == "stale_pose" else -.00075
            else:
                rows[2]["unexpected"] = True
            with self.subTest(case=name), self.assertRaisesRegex(AssertionError, reason):
                check.verify_n_sequence(rows)


def main():
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ContinuityQualificationTests)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    output = Path(__file__).resolve().parent
    attempt = len(list(output.glob("OFFLINE_CHECK_*.json"))) + 1
    report = {"schema": "continuity_fix1_qualification_offline_checks_v1", "attempt": attempt,
              "passed": result.wasSuccessful(), "test_methods": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors),
              "new_Blender_product_model_API_runs": 0,
              "fixture_scope": "original C owner INITIAL/FINAL and actual runner qualification path, historical five-observation wire, synthetic REPEAT request and N markers; no new live continuity acceptance"}
    (output / ("OFFLINE_CHECK_%02d.json" % attempt)).write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    (output / ("OFFLINE_CHECK_%02d.txt" % attempt)).write_text(stream.getvalue(), encoding="utf8")
    print(json.dumps(report))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
