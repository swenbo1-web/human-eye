"""Source-checkout setup stays local, reviewable and reversible."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from human_eye_plugin import agent_setup as setup


ROOT = Path(__file__).resolve().parents[1]


class AgentSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="human eye setup ")
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project 中文 ' % & ! $"
        self.project.mkdir()
        self.project = self.project.resolve()

    def plan(self, agent="codex", **kwargs):
        return setup.build_setup_plan(agent, self.project, **{"engine_root": ROOT, **kwargs})

    def put(self, relative, value):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else setup._encode(value))
        return path

    def connector(self):
        plan = self.plan("mcp")
        return copy.deepcopy(next(c for c in plan.changes if c.path.name == "live-connector.json").owned_configuration)

    def write_state(self, config, **changes):
        state = {"schema_version": "1.0", "config_fingerprint": setup._fingerprint(config),
                 "runtime": {"retained_authority": True}, "inflight": None}
        state.update(changes)
        return self.put(".human-eye/live-state.json", state)

    def test_dry_run_does_not_create_directories_or_files(self):
        before = sorted(self.project.rglob("*"))
        plan = self.plan()
        preview = plan.preview()
        self.assertEqual(sorted(self.project.rglob("*")), before)
        self.assertFalse(preview["applied"])
        self.assertEqual(len(preview["changes"]), 3)
        self.assertEqual(preview["activation"], "host_trust_review_required")

    def test_fresh_connector_binds_engine_source_and_project_local_state(self):
        config = self.connector()
        self.assertEqual(Path(config["project_root"]), ROOT)
        self.assertNotEqual(Path(config["project_root"]), self.project)
        self.assertEqual(config["state_file"], "live-state.json")
        self.assertEqual(config["blender"]["host"], "127.0.0.1")
        self.assertEqual(config["blender"]["port"], 9876)

    def test_codex_preserves_original_toml_bytes_and_disabled_agent_learning(self):
        original = b'# retained comment\r\n[mcp_servers.agent_learning]\r\nenabled = false\r\ncommand = "learning"\r\n'
        path = self.put(".codex/config.toml", original)
        result = self.plan().apply()
        self.assertTrue(path.read_bytes().startswith(original))
        self.assertIn(b"enabled = false", path.read_bytes())
        self.assertTrue(result["applied"])
        manifest = json.loads(Path(result["backup_manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "applied")
        backup = Path(result["backup_manifest"]).parent / "files/.codex/config.toml"
        self.assertEqual(backup.read_bytes(), original)

    def test_repeated_apply_is_byte_identical_and_creates_no_extra_backup(self):
        for agent in ("codex", "claude", "mcp"):
            with self.subTest(agent=agent):
                self.plan(agent).apply()
                before = {str(p): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
                plan = self.plan(agent)
                self.assertEqual(plan.changes, [])
                self.assertIsNone(plan.apply()["backup_manifest"])
                self.assertEqual(before, {str(p): p.read_bytes() for p in self.project.rglob("*") if p.is_file()})

    def test_claude_merges_other_hooks_permissions_and_mcp(self):
        settings = {"permissions": {"deny": ["Read(secret)"]}, "hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "echo retained", "timeout": 7}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "echo stop"}]}]}}
        mcp = {"mcpServers": {"other": {"command": "other", "env": {"KEY": "do-not-print"}}}, "custom": True}
        self.put(".claude/settings.json", settings)
        self.put(".mcp.json", mcp)
        plan = self.plan("claude")
        self.assertNotIn("do-not-print", json.dumps(plan.preview()))
        plan.apply()
        actual = json.loads((self.project / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(actual["permissions"], settings["permissions"])
        self.assertEqual(actual["hooks"]["Stop"], settings["hooks"]["Stop"])
        self.assertEqual(actual["hooks"]["UserPromptSubmit"][0], settings["hooks"]["UserPromptSubmit"][0])
        direct = actual["hooks"]["UserPromptSubmit"][1]["hooks"][0]
        self.assertEqual(direct["command"], str(Path(sys.executable).resolve()))
        self.assertEqual(direct["args"][-2:], ["--config", (self.project / ".human-eye/live-connector.json").as_posix()])
        self.assertEqual(json.loads((self.project / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["other"], mcp["mcpServers"]["other"])

    def test_mcp_is_explicitly_passive_and_has_no_hook_files(self):
        result = self.plan("mcp").apply()
        self.assertEqual(result["activation"], "passive_mcp_only")
        self.assertIsNone(result["hook_argv"])
        self.assertFalse((self.project / ".codex").exists())
        self.assertFalse((self.project / ".claude").exists())
        value = json.loads((self.project / ".human-eye/mcp-client.json").read_text(encoding="utf-8"))
        self.assertEqual(value["mcpServers"]["human_eye_live"]["args"][1], (ROOT / "examples/agents/live_entry.py").as_posix())

    def test_conflicting_codex_server_fails_without_any_write(self):
        path = self.put(".codex/config.toml", b'[mcp_servers.human_eye_live]\ncommand = "wrong"\n')
        before = path.read_bytes()
        with self.assertRaisesRegex(setup.AgentSetupError, "Conflicting"):
            self.plan()
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.project / ".human-eye").exists())

    def test_conflicting_claude_and_generic_servers_are_preserved(self):
        for agent, relative in (("claude", ".mcp.json"), ("mcp", ".human-eye/mcp-client.json")):
            with self.subTest(agent=agent):
                path = self.put(relative, {"mcpServers": {"human_eye_live": {"command": "wrong"}}})
                before = path.read_bytes()
                with self.assertRaisesRegex(setup.AgentSetupError, "Conflicting"):
                    self.plan(agent)
                self.assertEqual(path.read_bytes(), before)

    def test_existing_connector_bytes_disabled_flag_and_state_are_preserved(self):
        config = self.connector()
        config["enabled"] = False
        config["observe_on_prompt"] = False
        config["quad_size"] = 128
        path = self.put(".human-eye/live-connector.json", json.dumps(config, indent=4).encode())
        state = self.write_state(config)
        before, state_before = path.read_bytes(), state.read_bytes()
        self.plan("claude").apply()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(state.read_bytes(), state_before)

    def test_legacy_relative_engine_root_preserved(self):
        # Simulate an engine checkout different from the configured project.
        config = self.connector()
        engine = self.project.parent / "engine"
        (engine / "examples/agents").mkdir(parents=True)
        (engine / "human_eye_plugin").mkdir()
        (engine / "examples/agents/live_entry.py").write_bytes(b"# source entry")
        (engine / "human_eye_plugin/live_service.py").write_bytes(b"# source module")
        config["project_root"] = os.path.relpath(engine, self.project / ".human-eye")
        path = self.put(".human-eye/live-connector.json", config)
        before = path.read_bytes()
        self.plan("mcp", engine_root=engine).apply()
        self.assertEqual(path.read_bytes(), before)

    def test_invalid_connector_authority_boundaries_fail(self):
        variants = [
            {"project_root": str(self.project)}, {"state_file": "../../outside-state.json"},
            {"audit_file": "../.codex/config.toml"}, {"state_file": "live-connector.json"},
            {"audit_file": "live-state.json"}, {"blender": {"host": "remote.example"}},
            {"blender": {"host": "127.0.0.1", "port": True}}, {"enabled": "true"},
            {"quad_size": True}, {"readback_atol_m": 0}, {"state_file": "setup-backups/state"},
            {"state_file": "mcp-client.json"}, {"audit_file": "mcp-client.json"},
            {"audit_file": "live-state.json.lock"}, {"state_file": "live-events.jsonl.lock"}]
        config = self.connector()
        for changes in variants:
            with self.subTest(changes=changes):
                self.put(".human-eye/live-connector.json", {**config, **changes})
                with self.assertRaises(setup.AgentSetupError):
                    self.plan()

    def test_mismatched_or_inflight_state_is_never_reset(self):
        config = self.connector()
        self.put(".human-eye/live-connector.json", config)
        for state_changes in ({"config_fingerprint": "wrong"}, {"inflight": {"operation_id": "pending"}}, {"runtime": None}):
            with self.subTest(state_changes=state_changes):
                state_path = self.write_state(config, **state_changes)
                before = state_path.read_bytes()
                with self.assertRaises(setup.AgentSetupError):
                    self.plan()
                self.assertEqual(state_path.read_bytes(), before)

    def test_changed_preview_is_not_applied(self):
        plan = self.plan()
        path = self.put(".codex/config.toml", b"# concurrent edit\n")
        with self.assertRaisesRegex(setup.AgentSetupError, "changed after planning"):
            plan.apply()
        self.assertEqual(path.read_bytes(), b"# concurrent edit\n")
        self.assertFalse((self.project / ".human-eye/live-connector.json").exists())

    def test_unchanged_connector_is_also_guarded_after_preview(self):
        self.plan("mcp").apply()
        plan = self.plan("claude")
        path = self.project / ".human-eye/live-connector.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["enabled"] = False
        path.write_bytes(setup._encode(config))
        with self.assertRaisesRegex(setup.AgentSetupError, "changed after planning"):
            plan.apply()
        self.assertFalse((self.project / ".mcp.json").exists())

    def test_new_pending_operation_after_preview_refuses_apply(self):
        self.plan("mcp").apply()
        plan = self.plan("claude")
        config = json.loads((self.project / ".human-eye/live-connector.json").read_text(encoding="utf-8"))
        self.write_state(config, inflight={"operation_id": "pending"})
        with self.assertRaisesRegex(setup.AgentSetupError, "pending"):
            plan.apply()

    def test_multi_file_failure_restores_every_written_configuration(self):
        original = b"# retain exactly\r\n[mcp_servers.agent_learning]\r\nenabled = false\r\n"
        toml_path = self.put(".codex/config.toml", original)
        plan = self.plan()
        actual_write = setup._atomic_bytes
        failed = False

        def write(path, content):
            nonlocal failed
            if path == self.project / ".codex/hooks.json" and not failed:
                failed = True
                raise OSError("injected write failure")
            actual_write(path, content)

        with mock.patch.object(setup, "_atomic_bytes", side_effect=write):
            with self.assertRaisesRegex(setup.AgentSetupError, "rolled_back"):
                plan.apply()
        self.assertEqual(toml_path.read_bytes(), original)
        self.assertFalse((self.project / ".human-eye/live-connector.json").exists())
        self.assertFalse((self.project / ".codex/hooks.json").exists())
        self.assertFalse((self.project / ".human-eye/setup.lock").exists())
        manifest_path = next((self.project / ".human-eye/setup-backups").glob("*/manifest.json"))
        self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8"))["status"], "rolled_back")

    def test_lock_prevents_parallel_apply(self):
        plan = self.plan()
        self.put(".human-eye/setup.lock", b"busy")
        with self.assertRaisesRegex(setup.AgentSetupError, "Another project setup"):
            plan.apply()
        self.assertEqual((self.project / ".human-eye/setup.lock").read_bytes(), b"busy")

    def test_linked_configuration_and_backup_directories_refuse_escape(self):
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        for relative in (".codex", ".human-eye/setup-backups"):
            with self.subTest(relative=relative):
                link = self.project / relative
                link.parent.mkdir(parents=True, exist_ok=True)
                try:
                    link.symlink_to(outside, target_is_directory=True)
                except OSError as exc:
                    if os.name == "nt":
                        import _winapi
                        _winapi.CreateJunction(str(outside), str(link))
                    else:
                        self.skipTest("Directory symlinks unavailable: " + str(exc))
                try:
                    with self.assertRaises(setup.AgentSetupError):
                        self.plan().apply()
                    self.assertEqual(list(outside.iterdir()), [])
                    self.assertFalse((self.project / ".human-eye/setup.lock").exists())
                finally:
                    if hasattr(link, "is_junction") and link.is_junction():
                        link.rmdir()
                    else:
                        link.unlink()

    def test_windows_literal_encoded_command_is_reviewable_with_special_paths(self):
        argv = ["C:/some 中文 ' % & ! $ ` folder/python.exe", "-B", "D:/源 ' % & ! $ `/live_entry.py", "hook",
                "--agent", "codex", "--config", "D:/project 中文 ' % & ! $ `/config.json"]
        spec, source = setup._hook_spec(argv, "codex", "windows")
        decoded = base64.b64decode(spec["command"].split()[-1]).decode("utf-16-le")
        self.assertEqual(decoded, source)
        self.assertEqual(setup._command_argv(spec, "windows"), argv)
        self.assertTrue(source.endswith("; exit $LASTEXITCODE"))
        self.assertIn("-NoProfile -NonInteractive", spec["command"])
        self.assertNotIn("ExecutionPolicy", spec["command"])

    def test_posix_uses_literal_shell_quoting(self):
        argv = ["/tmp/space ' % & ! $ ` /python", "-B", "/tmp/源 ' & /entry.py", "hook"]
        spec, script = setup._hook_spec(argv, "codex", "posix")
        self.assertEqual(shlex.split(spec["command"]), argv)
        self.assertIsNone(script)

    def test_compatible_legacy_plain_hook_is_preserved(self):
        # Root's existing working hook predates the encoded Windows launcher.
        project = Path(self.temporary.name) / "plain"
        project.mkdir()
        argv = [str(Path(sys.executable).resolve()), "-B", (ROOT / "examples/agents/live_entry.py").as_posix(),
                "hook", "--agent", "codex", "--config", (project / ".human-eye/live-connector.json").as_posix()]
        command = argv[0] + ' -B "' + argv[2] + '" hook --agent codex --config "' + argv[-1] + '"'
        legacy = {"hooks": {event: [{**({"matcher": setup.TRANSFORM_MATCHER} if event != "UserPromptSubmit" else {}),
            "hooks": [{"type": "command", "command": command, "timeout": 30}]}]
            for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse")}}
        path = project / ".codex/hooks.json"
        path.parent.mkdir()
        path.write_bytes(setup._encode(legacy))
        before = path.read_bytes()
        setup.build_setup_plan("codex", project, engine_root=ROOT, platform="windows").apply()
        actual = json.loads(path.read_bytes())
        for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse"):
            self.assertEqual(actual["hooks"][event][0], legacy["hooks"][event][0])
            if event != "UserPromptSubmit":
                self.assertEqual(len(actual["hooks"][event]), 2)
                self.assertEqual(actual["hooks"][event][1]["matcher"], setup.CLEARANCE_SEGMENT_MATCHER)
        updated = path.read_bytes()
        self.assertNotEqual(updated, before)
        self.assertEqual(setup.build_setup_plan("codex", project, engine_root=ROOT,
                                              platform="windows").changes, [])
        self.assertEqual(path.read_bytes(), updated)

    def test_conflicting_own_hook_is_not_overwritten(self):
        self.plan("claude").apply()
        path = self.project / ".claude/settings.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["hooks"]["UserPromptSubmit"][0]["hooks"][0]["args"][-1] = "different-config.json"
        path.write_bytes(setup._encode(value))
        before = path.read_bytes()
        with self.assertRaisesRegex(setup.AgentSetupError, "Conflicting"):
            self.plan("claude")
        self.assertEqual(path.read_bytes(), before)

    def test_duplicate_own_hooks_require_review(self):
        self.plan("claude").apply()
        path = self.project / ".claude/settings.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["hooks"]["UserPromptSubmit"] *= 2
        path.write_bytes(setup._encode(value))
        with self.assertRaisesRegex(setup.AgentSetupError, "Duplicate"):
            self.plan("claude")

    def test_encoded_unknown_wrapper_cannot_hide_conflicting_own_hook(self):
        self.plan().apply()
        path = self.project / ".codex/hooks.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        hook = value["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        source = "& 'wrong-python' 'live_entry.py' hook; Write-Output extra"
        hook["command"] = "powershell.exe -EncodedCommand " + base64.b64encode(source.encode("utf-16-le")).decode()
        path.write_bytes(setup._encode(value))
        with self.assertRaisesRegex(setup.AgentSetupError, "Conflicting"):
            self.plan()

    def test_json_duplicate_keys_and_invalid_toml_fail_without_writes(self):
        path = self.put(".mcp.json", b'{"mcpServers": {}, "mcpServers": {}}')
        with self.assertRaisesRegex(setup.AgentSetupError, "Duplicate"):
            self.plan("claude")
        path.unlink()
        self.put(".codex/config.toml", b"[broken\n")
        with self.assertRaises(setup.AgentSetupError):
            self.plan()
        self.assertFalse((self.project / ".human-eye").exists())

    def test_python_310_fallback_fresh_and_canonical_idempotence(self):
        with mock.patch.object(setup, "tomllib", None):
            self.plan().apply()
            self.assertEqual(self.plan().changes, [])
        other = self.project / ".codex/config.toml"
        other.write_bytes(b"[mcp_servers.other]\ncommand = 'other'\n")
        with mock.patch.object(setup, "tomllib", None):
            with self.assertRaisesRegex(setup.AgentSetupError, "Python 3.11"):
                self.plan()

    def test_invalid_project_interpreter_engine_and_newline_paths_fail(self):
        variants = [dict(project=self.project / "missing"), dict(python_path=self.project / "missing.exe"),
                    dict(engine_root=self.project), dict(project=str(self.project) + "\n")]
        for changes in variants:
            with self.subTest(changes=changes):
                options = {"project": self.project, "engine_root": ROOT, **changes}
                with self.assertRaises(setup.AgentSetupError):
                    setup.build_setup_plan("codex", **options)

    def test_source_entry_cli_runs_outside_checkout_and_defaults_to_dryrun(self):
        proc = subprocess.run([sys.executable, "-B", str(ROOT / "examples/agents/configure.py"),
            "--agent", "mcp", "--project", str(self.project)], cwd=self.temporary.name,
            text=True, encoding="utf-8", capture_output=True, timeout=10, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        value = json.loads(proc.stdout)
        self.assertFalse(value["applied"])
        self.assertEqual(value["engine_root"], str(ROOT))
        self.assertEqual(list(self.project.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
