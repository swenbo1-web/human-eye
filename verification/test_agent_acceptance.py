"""Evidence must not turn local payloads or manual hooks into live acceptance."""
import json
from pathlib import Path
import tempfile
import unittest

from verification.agent_acceptance import (
    codex_host_records, hook_evidence, native_payload_check, registration,
    route_corpus, tool_coverage,
)


class AgentAcceptanceEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def write_lines(self, name, rows):
        path = self.folder / name
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path

    @staticmethod
    def host_message(role="developer", host_kind=True):
        content = {"human_eye_live": "observed", "session_id": "codex:session",
            "observation": json.dumps({"scene_revision": "r1"}),
            "delivery": "text_only_hook_no_native_image"}
        return {"type": "response_item", "payload": {"role": role,
            "content": [{"type": "input_text", "text": json.dumps(content)}],
            "internal_chat_message_metadata_passthrough": {"turn_id": "turn1",
                "content_item_kinds": ["hooks.additional_context"] if host_kind else []}}}

    @staticmethod
    def hook(**overrides):
        return {"event": "host_hook", "hook_event": "UserPromptSubmit", "turn_id": "turn1",
                "session_id": "codex:session", "scene_revision": "r1",
                "invocation_source": "hook_command", **overrides}

    def test_same_png_is_prepared_in_all_formats_without_claiming_remote_delivery(self):
        result = native_payload_check()
        self.assertEqual(len(result["rows"]), 5)
        for row in result["rows"]:
            self.assertTrue(row["same_bytes"])
            self.assertEqual(row["decoded_sha256"], result["fixture_sha256"])
            self.assertEqual(row["model_consumed_image"], "unknown")
            self.assertEqual(row["remote_send"], "not_performed")

    def test_copied_user_or_assistant_text_is_never_an_actual_hook(self):
        path = self.write_lines("host.jsonl", [self.host_message("user"),
            self.host_message("assistant"), self.host_message(host_kind=False)])
        self.assertEqual(codex_host_records(path)["hook_deliveries"], [])

    def test_current_dict_observation_is_read_without_claiming_new_revision(self):
        row = self.host_message()
        value = json.loads(row['payload']['content'][0]['text'])
        value['observation'] = json.loads(value['observation'])
        row['payload']['content'][0]['text'] = json.dumps(value)
        result = codex_host_records(self.write_lines('host-current.jsonl', [row]))
        self.assertEqual(len(result['hook_deliveries']), 1)
        self.assertEqual(result['hook_deliveries'][0]['scene_revision'], 'r1')
        self.assertIsNone(result['hook_deliveries'][0]['implementation_revision'])

    def test_manual_probe_cannot_be_upgraded_by_a_matching_host_record(self):
        host = codex_host_records(self.write_lines("host.jsonl", [self.host_message()]))
        audit = self.write_lines("audit.jsonl", [self.hook(invocation_source="manual_probe")])
        result = hook_evidence(audit, host)
        self.assertEqual(result["manual_probes_excluded"], 1)
        self.assertEqual(result["correlated_prompt_events"], [])
        self.assertEqual(result["current_revision_activation"], "unknown")

    def test_actual_prompt_match_requires_turn_session_and_revision(self):
        host = codex_host_records(self.write_lines("host.jsonl", [self.host_message()]))
        audit = self.write_lines("audit.jsonl", [self.hook(turn_id="another"),
            self.hook(session_id="codex:other"), self.hook(scene_revision="old"), self.hook(turn_id=None)])
        self.assertEqual(hook_evidence(audit, host)["correlated_prompt_events"], [])

    def test_historical_host_match_never_proves_new_version_execution_or_readback(self):
        host = codex_host_records(self.write_lines("host.jsonl", [self.host_message()]))
        audit = self.write_lines("audit.jsonl", [self.hook()])
        result = hook_evidence(audit, host)
        self.assertEqual(len(result["correlated_prompt_events"]), 1)
        self.assertEqual(result["prompt_activation"], "historical_host_correlated")
        self.assertEqual(result["current_revision_activation"], "unknown")
        self.assertEqual(result["independent_readback"], "not_run_in_current_host")
        self.assertEqual(result["inner_execution_gate"], "not_run_in_current_host")

    def test_repeated_audit_rows_do_not_multiply_one_actual_host_delivery(self):
        host = codex_host_records(self.write_lines("host.jsonl", [self.host_message()]))
        audit = self.write_lines("audit.jsonl", [self.hook(), self.hook(), self.hook()])
        result = hook_evidence(audit, host)
        self.assertEqual(len(result["correlated_prompt_events"]), 1)
        self.assertEqual(result["duplicate_audit_candidates"], 2)

    def test_unknown_or_bypass_tools_do_not_inherit_inner_gate_coverage(self):
        registration_result = {"hook_groups": [{"event": "PreToolUse",
            "matcher": "^mcp__human_eye_live__human_eye_transform$"}]}
        result = tool_coverage(registration_result, ["mcp__human_eye_live__human_eye_transform",
            "mcp__blender__execute_blender_code", "future_tool"], inventory_source="unit_fixture")
        self.assertTrue(result["rows"][0]["pre_hook_match"])
        for row in result["rows"][1:]:
            self.assertFalse(row["pre_hook_match"])
            self.assertEqual(row["inner_gate"], "unverified_or_bypass")
        self.assertFalse(result["inventory_is_complete"])

    def test_config_presence_does_not_claim_host_loaded_and_does_not_modify_project(self):
        (self.folder / ".codex").mkdir()
        path = self.folder / ".codex/config.toml"
        path.write_text('[mcp_servers.human_eye_live]\ncommand="python"\n'
            'args=["-m","human_eye_plugin.mcp_server"]\n', encoding="utf-8")
        before = path.read_bytes()
        result = registration(self.folder, "codex")
        self.assertEqual(result["server_registration"], "registered_in_project_config")
        self.assertFalse(result["recognized_live_launcher"])
        self.assertEqual(result["host_loaded"], "unknown")
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.folder / ".human-eye").exists())

    def test_duplicate_corpus_ids_fail_before_any_routing(self):
        path = self.folder / "corpus.json"
        path.write_text(json.dumps({"rows": [{"id": "duplicate"}] * 100}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "100 distinct"):
            route_corpus(path)


if __name__ == "__main__":
    unittest.main()
