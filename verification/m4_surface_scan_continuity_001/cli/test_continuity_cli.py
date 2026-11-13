"""Synthetic CLI contract checks. No CLI inference or backend is started."""

import copy
import importlib.util
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("_continuity_cli", HERE / "continuity_cli.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)
THREAD = "11111111-2222-4333-8444-555555555555"
OTHER_THREAD = "99999999-2222-4333-8444-555555555555"
USAGE = {"input_tokens": 100, "cached_input_tokens": 30, "output_tokens": 20,
         "reasoning_output_tokens": 2, "future_provider_field": {"scope": "unconfirmed"}}


def initial_argv():
    return ["codex.exe", "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
            "--strict-config", "--json", "--skip-git-repo-check", "-C", "C:/fixed-work",
            "--color", "never", "-c", 'model_reasoning_effort="medium"',
            "-c", 'mcp_servers.arm_engine={command="python.exe"}',
            "-m", "gpt-6.1-sol", "-o", "C:/turn-final.txt", "-"]


def events():
    return [
        {"perf_ns": 100, "event": {"type": "thread.started", "thread_id": THREAD}},
        {"perf_ns": 200, "event": {"type": "item.completed", "item": {
            "id": "msg1", "type": "agent_message", "text": "当前完整结果"}}},
        {"perf_ns": 300, "event": {"type": "turn.completed", "usage": copy.deepcopy(USAGE)}},
    ]


def summarize(rows=None, turn=1, expected=None, exit_code=0):
    return CLI.summarize_turn(events() if rows is None else rows, episode_id="N工程",
                              turn_index=turn, expected_thread_id=expected, exit_code=exit_code)


class ArgvContract(unittest.TestCase):
    def test_first_turn_persists_and_preserves_every_other_argument(self):
        value = initial_argv()
        before = copy.deepcopy(value)
        actual = CLI.argv_for_turn(value)
        self.assertEqual(actual, [part for part in before if part != "--ephemeral"])
        self.assertEqual(value, before)

    def test_resume_explicit_thread_and_stdin(self):
        actual = CLI.argv_for_turn(initial_argv(), THREAD)
        self.assertEqual(actual[:7], ["codex.exe", "exec", "-C", "C:/fixed-work", "--color", "never", "resume"])
        self.assertEqual(actual[-2:], [THREAD, "-"])
        self.assertNotIn("--last", actual)
        self.assertNotIn("--ephemeral", actual)

    def test_resume_retains_config_and_model(self):
        initial = initial_argv()
        actual = CLI.argv_for_turn(initial, THREAD)
        expected_configs = [initial[index + 1] for index, arg in enumerate(initial) if arg == "-c"]
        actual_configs = [actual[index + 1] for index, arg in enumerate(actual) if arg == "-c"]
        self.assertEqual(actual_configs, expected_configs)
        self.assertEqual(actual[actual.index("-m") + 1], "gpt-6.1-sol")
        self.assertEqual(actual[actual.index("-o") + 1], "C:/turn-final.txt")

    def test_reject_thread_names_last_and_malformed_UUID(self):
        for value in ("--last", "latest", "wrong-id", THREAD.upper()):
            if value == THREAD:
                continue
            with self.subTest(value=value), self.assertRaises(ValueError):
                CLI.argv_for_turn(initial_argv(), value)

    def test_reject_already_resumed_template(self):
        for flag in ("resume", "fork", "--last", "--all"):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                CLI.argv_for_turn(initial_argv()[:-1] + [flag, "-"])

    def test_reject_non_stdin_or_non_exec(self):
        for value in (["codex.exe", "exec", "text"], ["codex.exe", "resume", "-"]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CLI.argv_for_turn(value)


class PublicEvents(unittest.TestCase):
    def test_first_complete_turn_is_content_unscored(self):
        result = summarize()
        self.assertTrue(result["valid_completion"])
        self.assertEqual(result["content_quality"], "unscored")
        self.assertEqual(result["final"], "当前完整结果")

    def test_explicit_resume_matches(self):
        for turn in (2, 3):
            with self.subTest(turn=turn):
                result = summarize(turn=turn, expected=THREAD)
                self.assertTrue(result["valid_completion"])
                self.assertEqual(result["observed_thread_id"], THREAD)

    def test_missing_expected_resume_is_not_allowed(self):
        with self.assertRaisesRegex(ValueError, "resume_binding"):
            summarize(turn=2)

    def test_resume_on_first_turn_is_not_allowed(self):
        with self.assertRaisesRegex(ValueError, "resume_binding"):
            summarize(turn=1, expected=THREAD)

    def test_different_thread_fails_without_replacement(self):
        result = summarize(turn=2, expected=OTHER_THREAD)
        self.assertFalse(result["valid_completion"])
        self.assertTrue(result["final_present"])
        self.assertIn("resume_thread_mismatch", [error["type"] for error in result["errors"]])

    def test_missing_thread_fails(self):
        result = summarize(events()[1:])
        self.assertFalse(result["valid_completion"])
        self.assertTrue(result["final_present"])

    def test_duplicate_thread_events_fail(self):
        rows = events()
        result = summarize([rows[0], *rows])
        self.assertFalse(result["valid_completion"])

    def test_invalid_thread_identity_fails(self):
        rows = events()
        rows[0]["event"]["thread_id"] = "new-session"
        self.assertFalse(summarize(rows)["valid_completion"])

    def test_recovered_error_still_fails_with_present_final(self):
        rows = events()
        error = {"type": "error", "message": "Reconnecting... response body error"}
        rows.insert(1, {"perf_ns": 150, "event": error})
        result = summarize(rows)
        self.assertFalse(result["valid_completion"])
        self.assertTrue(result["final_present"])
        self.assertEqual(result["errors"][0], error)
        self.assertEqual(result["usage_events"], [USAGE])

    def test_turn_failed_is_preserved(self):
        rows = events()
        rows.insert(1, {"event": {"type": "turn.failed", "error": {"message": "failed"}}})
        self.assertEqual(summarize(rows)["execution_state"], "failed")

    def test_missing_final_fails(self):
        rows = [row for row in events() if row["event"]["type"] != "item.completed"]
        result = summarize(rows)
        self.assertFalse(result["valid_completion"])
        self.assertFalse(result["final_present"])

    def test_empty_final_fails(self):
        rows = events()
        rows[1]["event"]["item"]["text"] = "  "
        self.assertFalse(summarize(rows)["final_present"])

    def test_last_public_message_is_final(self):
        rows = events()
        rows.insert(1, {"event": {"type": "item.completed", "item": {
            "id": "preamble", "type": "agent_message", "text": "正在检查"}}})
        result = summarize(rows)
        self.assertEqual(result["final"], "当前完整结果")
        self.assertEqual(len(result["public_messages"]), 2)

    def test_missing_or_duplicate_completed_fails(self):
        for rows in (events()[:-1], events() + [events()[-1]]):
            with self.subTest(count=len(rows)):
                self.assertFalse(summarize(rows)["valid_completion"])

    def test_invalid_known_usage_remains_in_raw_event_and_fails(self):
        for value in (-1, True, 1.5):
            rows = events()
            rows[-1]["event"]["usage"]["input_tokens"] = value
            with self.subTest(value=value):
                result = summarize(rows)
                self.assertFalse(result["valid_completion"])
                self.assertEqual(result["usage_events"][0]["input_tokens"], value)

    def test_missing_usage_fails(self):
        rows = events()
        rows[-1]["event"].pop("usage")
        self.assertFalse(summarize(rows)["valid_completion"])

    def test_exit_nonzero_fails(self):
        self.assertFalse(summarize(exit_code=1)["valid_completion"])

    def test_usage_never_aggregated_or_differenced(self):
        result = summarize()
        self.assertEqual(result["usage_events"], [USAGE])
        self.assertIsNone(result["usage_aggregation"])
        self.assertEqual(result["usage_semantics"], "unconfirmed_turn_or_session_scope")
        self.assertEqual(result["interrupted_stream_usage_coverage"], "unknown")


class AnonymousEpisode(unittest.TestCase):
    def test_three_planned_turns_even_when_none_run(self):
        result = CLI.episode_manifest("N工程", [], "episode_anon")
        self.assertEqual(result["planned_turns"], 3)
        self.assertEqual(result["counts"], {"completed": 0, "failed": 0, "not_run": 3})

    def test_failed_present_final_remains_failed_and_future_slots_remain(self):
        rows = events()
        rows.insert(1, {"event": {"type": "error", "message": "failure with final"}})
        result = CLI.episode_manifest("N工程", [summarize(rows)], "episode_anon")
        self.assertEqual(result["counts"], {"completed": 0, "failed": 1, "not_run": 2})
        self.assertEqual(result["final_present"], 1)

    def test_three_turn_public_slots_keep_order_without_group_or_usage(self):
        records = [summarize(turn=turn, expected=None if turn == 1 else THREAD) for turn in (1, 2, 3)]
        result = CLI.episode_manifest("N工程", records, "episode_anon")
        self.assertEqual([row["turn_label"] for row in result["turns"]], ["BASE", "REPEAT", "EDIT"])
        self.assertEqual(result["counts"], {"completed": 3, "failed": 0, "not_run": 0})
        for row in result["turns"]:
            self.assertNotIn("episode_id", row)
            self.assertNotIn("observed_thread_id", row)
            self.assertNotIn("usage_events", row)

    def test_reject_duplicate_extra_or_wrong_episode(self):
        record = summarize()
        for rows in ([record, record], [dict(record, turn_index=4)], [dict(record, episode_id="C工程")]):
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                CLI.episode_manifest("N工程", rows, "episode_anon")

    def test_reject_wrong_turn_label_or_state(self):
        record = summarize()
        for row in (dict(record, turn_label="EDIT"), dict(record, execution_state="unknown")):
            with self.assertRaises(ValueError):
                CLI.episode_manifest("N工程", [row], "episode_anon")

    def test_error_business_payload_not_scrubbed_by_field_name(self):
        rows = events()
        event = {"type": "error", "message": '{"group":"native","perf_ns":42}'}
        rows.insert(1, {"perf_ns": 150, "event": event})
        result = CLI.episode_manifest("N工程", [summarize(rows)], "episode_anon")
        self.assertEqual(result["turns"][0]["errors"][0], event)


if __name__ == "__main__":
    unittest.main()
