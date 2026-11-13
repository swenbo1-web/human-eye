"""Offline checks using frozen engineering receipts and synthetic marker packets."""

import copy
import io
import json
from pathlib import Path
import sys
import unittest

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
                result = check.verify_c_turn(*self.fixture(turn))
                self.assertEqual(result["matches"], check.EXPECTED_MATCHES[turn])
                self.assertEqual(result["new_kernel_calls"], check.EXPECTED_KERNELS[turn])

    def test_synthetic_repeat_sequence_contract(self):
        reports = [check.verify_c_turn(*self.fixture(turn)) for turn in check.TURNS]
        self.assertTrue(check.verify_c_sequence(reports)["passed"])

    def test_raw_fact_and_actual_source_tampering_rejected(self):
        fixture = self.fixture()
        fixture[0]["matches"][0][4] = .009
        fixture[0]["matches"][0][5] = 9.0
        with self.assertRaises(AssertionError):
            check.verify_c_turn(*fixture)
        fixture = self.fixture()
        fixture[3]["objects"][0]["matrix_world"][2][3] += .001
        with self.assertRaisesRegex(AssertionError, "actual geometry or source fields differ"):
            check.verify_c_turn(*fixture)

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
                    check.verify_c_turn(*fixture)

    def test_duplicate_audit_and_wrong_capture_count(self):
        for event in ("observe", "request_trace"):
            fixture = self.fixture()
            fixture[1].append(copy.deepcopy(next(row for row in fixture[1] if row.get("event") == event and row.get("trace_id") == fixture[0]["trace_id"])))
            with self.subTest(event=event), self.assertRaisesRegex(AssertionError, "unique_request_observe_and_trace"):
                check.verify_c_turn(*fixture)
        for count in (0, 2):
            fixture = self.fixture()
            fixture[2] = fixture[2] * count
            with self.subTest(count=count), self.assertRaisesRegex(AssertionError, "exactly_one_host_capture"):
                check.verify_c_turn(*fixture)

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
                check.verify_c_turn(*fixture)

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
                check.verify_c_turn(*fixture)

    def test_c_sequence_mismatches_rejected(self):
        reports = [check.verify_c_turn(*self.fixture(turn)) for turn in check.TURNS]
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
    report = {"schema": "continuity_qualification_offline_checks_v1", "attempt": attempt,
              "passed": result.wasSuccessful(), "test_methods": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors),
              "new_Blender_product_model_API_runs": 0,
              "fixture_scope": "existing five-observation evidence plus synthetic REPEAT request and N marker packets; no live continuity acceptance"}
    (output / ("OFFLINE_CHECK_%02d.json" % attempt)).write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    (output / ("OFFLINE_CHECK_%02d.txt" % attempt)).write_text(stream.getvalue(), encoding="utf8")
    print(json.dumps(report))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
