"""Pure fake-profile checks over the actual owned QA context manager."""

import ast
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


OLD = Path(__file__).resolve().parents[2] / "m4_relation_selected_evidence_001/entry"


class FakeProfileAPI:
    def __init__(self, initial=None):
        self.current = initial
        self.set_calls = []
        self.fail_restore = False
        self.fail_install_after_assignment = False

    def getprofile(self):
        return self.current

    def setprofile(self, callback):
        self.set_calls.append(callback)
        if callback is None and self.fail_restore:
            raise RuntimeError("synthetic_restore_failure")
        self.current = callback
        if callback is not None and self.fail_install_after_assignment:
            raise RuntimeError("synthetic_install_failure_after_assignment")


class ProfileSwitchTests(unittest.TestCase):
    @contextmanager
    def fixture(self, initial=None):
        api = FakeProfileAPI(initial)
        samples = []

        def sample():
            samples.append(len(samples) + 1)
            return {"hosts": [], "totals": {"to_mesh": len(samples)}}

        with patch.object(QA, "sys", api), patch.object(QA, "host_work", side_effect=sample):
            yield api, samples

    def test_ON_uses_original_callback_and_restores_initial_none(self):
        event = {}
        with self.fixture() as (api, samples):
            with QA.rpc_scope(3, True, {}, event, previous_profile_enabled=False):
                callback = api.current
                self.assertTrue(callable(callback))
                frame = SimpleNamespace(f_code=SimpleNamespace(co_name="capture_task_scene", co_filename="D:/synthetic/blender_host.py"))
                callback(frame, "call", None)
                callback(frame, "c_call", SimpleNamespace(__name__="to_mesh"))
                callback(frame, "c_return", SimpleNamespace(__name__="to_mesh"))
                callback(frame, "c_exception", SimpleNamespace(__name__="calc_loop_triangles"))
            self.assertIsNone(api.current)
            self.assertEqual(len(samples), 2)
            self.assertEqual(len(api.set_calls), 2)
        work = event["qa_work"]
        self.assertEqual(work["python_calls"], {"capture_task_scene": 1})
        self.assertEqual(work["C_calls"], {"to_mesh": 1})
        self.assertEqual(work["C_returns"], {"to_mesh": 1})
        self.assertEqual(work["C_exceptions"], {"calc_loop_triangles": 1})
        self.assertEqual(work["host_residency_delta"]["to_mesh"], 1)
        self.assertTrue(work["profile_restored_to_initial"])
        self.assertEqual(work["errors"], [])
        EVIDENCE["ON"] = work

    def test_OFF_keeps_both_host_samples_and_marks_callback_counts_uncollected(self):
        event = {}
        with self.fixture() as (api, samples):
            with QA.rpc_scope(4, False, {}, event, previous_profile_enabled=True):
                self.assertIsNone(api.current)
            self.assertEqual(api.set_calls, [])
            self.assertEqual(len(samples), 2)
        work = event["qa_work"]
        for name in ("python_calls", "C_calls", "C_returns", "C_exceptions"):
            self.assertIsNone(work[name])
        self.assertEqual(work["callback_counts_status"], "not_collected")
        self.assertEqual(work["host_residency_delta"]["to_mesh"], 1)
        self.assertTrue(work["profile_restored_to_initial"])
        self.assertEqual(work["errors"], [])
        EVIDENCE["OFF"] = work

    def test_initial_foreign_profile_rejects_without_clearing_it(self):
        foreign = object()
        for enabled in (False, True):
            with self.subTest(enabled=enabled), self.fixture(foreign) as (api, samples):
                event = {}
                entered = False
                with self.assertRaises(QA.QAProfileStateError):
                    with QA.rpc_scope(1, enabled, {}, event):
                        entered = True
                self.assertFalse(entered)
                self.assertIs(api.current, foreign)
                self.assertEqual(api.set_calls, [])
                self.assertTrue(event["qa_work"]["profile_initial_present"])
                self.assertTrue(event["qa_work"]["errors"])
                EVIDENCE["initial_foreign_" + str(enabled)] = event["qa_work"]

    def test_operation_exception_still_restores_profile_in_finally(self):
        event = {}
        with self.fixture() as (api, samples):
            with self.assertRaisesRegex(ValueError, "synthetic_operation_failure"):
                with QA.rpc_scope(7, True, {}, event):
                    raise ValueError("synthetic_operation_failure")
            self.assertIsNone(api.current)
            self.assertEqual(len(samples), 2)
        self.assertTrue(event["qa_work"]["profile_restored_to_initial"])
        self.assertEqual(event["qa_work"]["errors"], [])
        EVIDENCE["operation_exception"] = event["qa_work"]

    def test_callback_exception_is_recorded_and_scope_stops_after_restoration(self):
        event = {}
        with self.fixture() as (api, samples):
            with self.assertRaises(QA.QAProfileStateError):
                with QA.rpc_scope(8, True, {}, event):
                    callback = api.current
                    frame = SimpleNamespace(f_code=SimpleNamespace(co_name="capture_task_scene", co_filename="D:/synthetic/blender_host.py"))
                    with patch.object(QA, "Path", side_effect=RuntimeError("synthetic_callback_failure")):
                        callback(frame, "call", None)
            self.assertIsNone(api.current)
            self.assertEqual(len(samples), 2)
        self.assertTrue(event["qa_work"]["profile_restored_to_initial"])
        self.assertTrue(event["qa_work"]["errors"])
        self.assertIn("synthetic_callback_failure", str(event["qa_work"]["errors"]))
        EVIDENCE["callback_exception"] = event["qa_work"]

    def test_foreign_replacement_and_disappeared_callback_stop(self):
        foreign = object()
        for replacement, label in ((foreign, "foreign"), (None, "disappeared")):
            with self.subTest(replacement=label), self.fixture() as (api, samples):
                event = {}
                with self.assertRaises(QA.QAProfileStateError):
                    with QA.rpc_scope(9, True, {}, event):
                        api.current = replacement
                self.assertIs(api.current, replacement)
                self.assertEqual(len(api.set_calls), 1)
                self.assertTrue(event["qa_work"]["errors"])
                EVIDENCE["replaced_" + label] = event["qa_work"]

    def test_restore_API_failure_is_recorded_and_stops(self):
        event = {}
        with self.fixture() as (api, samples):
            with self.assertRaises(QA.QAProfileStateError):
                with QA.rpc_scope(10, True, {}, event):
                    api.fail_restore = True
            self.assertIsNotNone(api.current)
        self.assertFalse(event["qa_work"]["profile_restored_to_initial"])
        self.assertIn("synthetic_restore_failure", str(event["qa_work"]["errors"]))
        EVIDENCE["restore_exception"] = event["qa_work"]

    def test_before_sampling_failure_keeps_attached_state_and_finally(self):
        event = {}
        with self.fixture() as (api, samples):
            after = {"hosts": [], "totals": {}}
            with patch.object(QA, "host_work", side_effect=[RuntimeError("synthetic_before_probe_failure"), after]):
                with self.assertRaises(QA.QAProfileStateError):
                    with QA.rpc_scope(11, True, {}, event):
                        self.fail("failed before sampling must prevent operation")
            self.assertIsNone(api.current)
            self.assertEqual(api.set_calls, [])
        work = event["qa_work"]
        self.assertIsNone(work["before"])
        self.assertEqual(work["after"], after)
        self.assertTrue(work["profile_restored_to_initial"])
        self.assertIn("synthetic_before_probe_failure", str(work["errors"]))
        EVIDENCE["before_sampling_exception"] = work

    def test_installation_exception_after_assignment_still_restores(self):
        event = {}
        with self.fixture() as (api, samples):
            api.fail_install_after_assignment = True
            with self.assertRaises(QA.QAProfileStateError):
                with QA.rpc_scope(12, True, {}, event):
                    self.fail("failed installation must prevent operation")
            self.assertIsNone(api.current)
            self.assertEqual(len(api.set_calls), 2)
        self.assertTrue(event["qa_work"]["profile_restored_to_initial"])
        self.assertIn("synthetic_install_failure_after_assignment", str(event["qa_work"]["errors"]))
        EVIDENCE["installation_exception"] = event["qa_work"]

    def test_after_sampling_failure_occurs_after_profile_restoration_and_stops(self):
        event = {}
        with self.fixture() as (api, samples):
            before = {"hosts": [], "totals": {}}
            with patch.object(QA, "host_work", side_effect=[before, RuntimeError("synthetic_after_probe_failure")]):
                with self.assertRaises(QA.QAProfileStateError):
                    with QA.rpc_scope(13, True, {}, event):
                        self.assertIsNotNone(api.current)
            self.assertIsNone(api.current)
        self.assertTrue(event["qa_work"]["profile_restored_to_initial"])
        self.assertIn("synthetic_after_probe_failure", str(event["qa_work"]["errors"]))
        EVIDENCE["after_sampling_exception"] = event["qa_work"]

    def test_frozen_schedule_and_saved_summary_have_ten_nonempty_pairs_per_session(self):
        self.assertEqual([case["version"] for case in SCHEDULE["sessions"]], ["B", "C", "C", "B"])
        synthetic_sessions = []
        for ordinal, case in enumerate(SCHEDULE["sessions"], 1):
            business = case["business"]
            self.assertEqual(len(business), 22)
            self.assertEqual([row["phase"] for row in business[:2]], ["cold", "warmup"])
            self.assertTrue(all(row["phase"] == "warm" for row in business[2:]))
            previous = None
            rows = []
            for sequence, row in enumerate(business, 1):
                self.assertEqual(row["sequence"], sequence)
                self.assertIs(row["previous_profile_enabled"], previous)
                if sequence < 3:
                    self.assertFalse(row["profile_enabled"])
                previous = row["profile_enabled"]
                value = sequence * 100 + (10 if previous else 0) + (1 if case["version"] == "C" else 0)
                rows.append({**row, "label": row["request_id"],
                             "measurements": {field: value for field in ANALYZER.MEASURES}})
            self.assertEqual(case["close"]["sequence"], 23)
            self.assertFalse(case["close"]["profile_enabled"])
            self.assertIs(case["close"]["previous_profile_enabled"], previous)
            for pair in range(1, 11):
                selected = [row for row in business if row["pair_index"] == pair]
                self.assertEqual([row["pair_position"] for row in selected], [1, 2])
                first_on = ordinal <= 2
                first = first_on if pair % 2 else not first_on
                self.assertEqual([row["profile_enabled"] for row in selected], [first, not first])
            summary = ANALYZER.summarize_session(rows)
            for mode in ("ON", "OFF"):
                self.assertEqual(summary[mode]["entry_elapsed_ns"]["count"], 10)
                for position in ("1", "2"):
                    self.assertEqual(summary["position"][mode][position]["entry_elapsed_ns"]["count"], 5)
                self.assertEqual(sum(item["entry_elapsed_ns"]["count"] for item in summary["previous_profile"][mode].values()), 10)
            self.assertEqual(len(summary["pair_differences"]), 10)
            self.assertEqual(summary["paired_ON_minus_OFF"]["entry_elapsed_ns"]["count"], 10)
            synthetic_sessions.append({"case": case, "role": ANALYZER.VERSION_ROLE[case["version"]], "summary": summary})
        version = ANALYZER.version_comparisons(synthetic_sessions)
        self.assertEqual(version["actual_session_counts"], {"baseline": 2, "candidate": 2})
        for block in version["matched_blocks"]:
            for contrast in block["contrasts"].values():
                self.assertEqual(contrast, {"C_minus_B_ON": 1, "C_minus_B_OFF": 1, "interaction": 0})
        EVIDENCE["synthetic_schedule_and_summary"] = {"synthetic": True, "sessions": 4,
            "business_calls_per_session": 22, "warm_calls_per_session": 20,
            "pairs_per_session": 10, "ON_per_session": 10, "OFF_per_session": 10,
            "version_session_counts": version["actual_session_counts"],
            "synthetic_contrast": "all matched mode differences are one synthetic unit, interaction zero"}

    def test_static_protection_fingerprint_timer_and_cleanup_remain(self):
        old_tree = ast.parse((OLD / "qa_native.py").read_bytes())
        new_tree = ast.parse(NATIVE_SOURCE)
        old_functions = {node.name: node for node in old_tree.body if isinstance(node, ast.FunctionDef)}
        new_functions = {node.name: node for node in new_tree.body if isinstance(node, ast.FunctionDef)}
        protected = ("check", "protected_files_intact", "_read_request", "_scene_state", "_scene_fingerprint", "_scan_pngs")
        for name in protected:
            self.assertEqual(ast.dump(old_functions[name], include_attributes=False), ast.dump(new_functions[name], include_attributes=False))
        old_session = next(node for node in old_tree.body if isinstance(node, ast.ClassDef) and node.name == "NativeSession")
        new_session = next(node for node in new_tree.body if isinstance(node, ast.ClassDef) and node.name == "NativeSession")
        for name in ("close", "_kill", "_check_startup_sources"):
            old = next(node for node in old_session.body if isinstance(node, ast.FunctionDef) and node.name == name)
            new = next(node for node in new_session.body if isinstance(node, ast.FunctionDef) and node.name == name)
            self.assertEqual(ast.dump(old, include_attributes=False), ast.dump(new, include_attributes=False))
        current_worker = ast.unparse(new_functions["worker"])
        for text in ("terminal_geometry_and_file_checks_passed", "elapsed_ns", "WORKER_CLOSED.json", "watchdog_cleanup"):
            self.assertIn(text, current_worker)
        self.assertTrue(any(isinstance(node, ast.With) and any(isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute) and item.context_expr.func.attr == "rpc_scope"
            for item in node.items) for node in ast.walk(new_functions["worker"])))
        EVIDENCE["static_preserved"] = {"same_function_AST": list(protected) + ["NativeSession.close", "NativeSession._kill", "NativeSession._check_startup_sources"],
            "worker_scope": "actual rpc_scope context present alongside original terminal, timer and watchdog cleanup markers"}
