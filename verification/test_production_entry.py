"""Production selection and identity boundaries without a running Blender."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from human_eye_plugin import production_server
from human_eye_plugin.runtime_identity import runtime_identity, validate_expected_identity


ROOT = Path(__file__).resolve().parents[1]


class ProductionEntryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)

    def write_config(self, path=None):
        config = self.folder / "live.json" if path is None else path
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"schema_version": "1.0", "project_root": str(ROOT),
            "state_file": "state.json", "audit_file": "events.jsonl",
            "blender": {"host": "127.0.0.1", "port": 1, "timeout_s": .1}}), encoding="utf-8")
        return config

    def test_config_precedence_and_current_project_default(self):
        default = self.write_config(self.folder / ".human-eye/live-connector.json")
        environment = self.write_config(self.folder / "environment.json")
        explicit = self.write_config(self.folder / "explicit.json")
        self.assertEqual(production_server.resolve_config(cwd=self.folder, environ={}), default)
        self.assertEqual(production_server.resolve_config(cwd=self.folder,
            environ={"HUMAN_EYE_CONFIG": str(environment)}), environment)
        self.assertEqual(production_server.resolve_config("explicit.json", cwd=self.folder,
            environ={"HUMAN_EYE_CONFIG": str(environment)}), explicit)

    def test_missing_explicit_or_env_path_never_uses_existing_default(self):
        self.write_config(self.folder / ".human-eye/live-connector.json")
        for explicit, environment in [("missing.json", {}),
                (None, {"HUMAN_EYE_CONFIG": "missing.json"})]:
            with self.subTest(explicit=explicit, environment=environment), self.assertRaises(FileNotFoundError):
                production_server.resolve_config(explicit, cwd=self.folder, environ=environment)
        with self.assertRaises(ValueError):
            production_server.resolve_config(cwd=self.folder, environ={"HUMAN_EYE_CONFIG": ""})

    def test_does_not_search_parent_project(self):
        self.write_config(self.folder / ".human-eye/live-connector.json")
        child = self.folder / "other-project"
        child.mkdir()
        with self.assertRaises(FileNotFoundError):
            production_server.resolve_config(cwd=child, environ={})

    def test_missing_config_exits_without_importing_demo_transport(self):
        # Test in a fresh interpreter so the import observation is meaningful.
        source = """import json, sys
from human_eye_plugin.production_server import main
code = main(['--config', sys.argv[1]])
print(json.dumps({'code':code, 'demo_imported':'human_eye_plugin.mcp_server' in sys.modules}))
"""
        process = subprocess.run([sys.executable, "-B", "-c", source, str(self.folder / "missing.json")],
            cwd=ROOT, capture_output=True, text=True,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), {"code": 2, "demo_imported": False})
        self.assertIn("configuration not found", process.stderr)

    def test_invalid_config_exits_without_starting_any_transport(self):
        invalid = self.folder / "invalid.json"
        invalid.write_text("{broken json", encoding="utf-8")
        with patch("human_eye_plugin.live_spatial_mcp.run_stdio_mcp_server") as live, \
                patch.dict(os.environ, {}, clear=True), patch("sys.stderr", new_callable=io.StringIO) as error:
            self.assertEqual(production_server.main(["--config", str(invalid)]), 2)
        live.assert_not_called()
        self.assertIn("Unable to configure", error.getvalue())

    def test_live_launch_enables_production_guards(self):
        config = self.write_config()
        service = object()
        with patch("human_eye_plugin.live_service.LiveSpatialService", return_value=service) as factory, \
                patch("human_eye_plugin.live_spatial_mcp.run_stdio_mcp_server") as serve:
            self.assertEqual(production_server.main(["--config", str(config)]), 0)
        factory.assert_called_once_with(config, production_mode=True)
        serve.assert_called_once_with(service)

    def test_demo_is_only_loaded_by_explicit_flag(self):
        with patch("human_eye_plugin.production_server.run_demo_stdio") as demo, \
                patch("human_eye_plugin.live_service.LiveSpatialService") as live:
            self.assertEqual(production_server.main(["--demo"]), 0)
        demo.assert_called_once_with()
        live.assert_not_called()

    def test_explicit_demo_initialize_reports_synthetic_source_and_no_live_authority(self):
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n"
        process = subprocess.run([sys.executable, "-B", "-m", "human_eye_plugin.production_server", "--demo"],
            input=request, cwd=ROOT, capture_output=True, text=True,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)["result"]
        identity = result["_meta"]["human_eye"]
        self.assertEqual(identity["mode"], "demo")
        self.assertEqual(identity["scene_source"], "legacy_synthetic_demonstration")
        self.assertFalse(identity["production_mode"])
        self.assertFalse(identity["capabilities"]["guarded_rigid_transform"])
        self.assertEqual(identity["capabilities"]["host_connection"], "not_checked")

    def test_demo_notifications_are_silent_and_never_dispatched(self):
        from human_eye_plugin import mcp_server
        incoming = io.StringIO(json.dumps({"jsonrpc": "2.0", "method": "tools/call",
            "params": {"name": "anything"}}) + "\n")
        outgoing = io.StringIO()
        with patch.object(mcp_server, "handle_jsonrpc_message") as dispatch:
            production_server.run_demo_stdio(incoming, outgoing)
        dispatch.assert_not_called()
        self.assertEqual(outgoing.getvalue(), "")

    def test_demo_and_live_configuration_are_mutually_exclusive(self):
        with patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
            production_server.main(["--demo", "--config", "live.json"])
        self.assertEqual(error.exception.code, 2)

    def test_real_initialize_does_not_connect_or_create_live_state(self):
        config = self.write_config()
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n"
        process = subprocess.run([sys.executable, "-B", "-m", "human_eye_plugin.production_server",
            "--config", str(config)], input=request, cwd=ROOT, capture_output=True, text=True,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["result"]["serverInfo"]["name"], "human-eye-live-spatial")
        self.assertFalse((self.folder / "state.json").exists())
        records = [json.loads(line) for line in (self.folder / "events.jsonl").read_text().splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event"], "request_trace")
        self.assertEqual(records[0]["measurement_scope"], "service_constructor_only")
        self.assertIn("module_imports", records[0]["excluded_stages"])
        trace = records[0]["trace"]
        self.assertEqual(trace["operation"], "startup.service_construct")
        self.assertEqual(trace["outcome"], "configured")
        self.assertEqual([item["name"] for item in trace["spans"]], ["startup.service_construct"])
        self.assertEqual(trace["spans"][0]["kind"], "startup")

    def test_startup_trace_failures_never_repeat_or_prevent_service_construction(self):
        config = self.write_config()
        for failure_mode in ("constructor", "enter", "exit", "writer"):
            with self.subTest(failure_mode=failure_mode):
                service = types.SimpleNamespace(record_event=Mock(side_effect=OSError("no audit storage")))
                with patch("human_eye_plugin.live_service.LiveSpatialService", return_value=service) as factory:
                    if failure_mode == "writer":
                        result = production_server.construct_live_service(config)
                    else:
                        from human_eye_plugin.telemetry import RequestTrace
                        target = "human_eye_plugin.telemetry.RequestTrace" if failure_mode == "constructor" else (
                            "human_eye_plugin.telemetry.RequestTrace.__" + failure_mode + "__")
                        # A real exit cleans context before simulating unavailable
                        # telemetry collection, preserving the caller's context.
                        if failure_mode == "exit":
                            original = RequestTrace.__exit__
                            def fail_after_cleanup(trace, *args):
                                original(trace, *args)
                                raise OSError("trace exit failed")
                            replacement = patch(target, new=fail_after_cleanup)
                        else:
                            replacement = patch(target, side_effect=OSError("trace unavailable"))
                        with replacement:
                            result = production_server.construct_live_service(config)
                self.assertIs(result, service)
                factory.assert_called_once_with(config, production_mode=True)

    def test_disconnected_host_returns_live_error_without_demo_scene(self):
        config = self.write_config()
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "human_eye_scene_observe", "arguments": {}}}) + "\n"
        process = subprocess.run([sys.executable, "-B", "-m", "human_eye_plugin.production_server",
            "--config", str(config)], input=request, cwd=ROOT, capture_output=True, text=True,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)["result"]
        self.assertTrue(result["isError"])
        metadata = json.loads(result["content"][0]["text"])
        self.assertEqual(metadata["status"], "error")
        self.assertNotIn("objects", metadata)
        self.assertFalse((self.folder / "state.json").exists())


class RuntimeIdentityTests(unittest.TestCase):
    def test_identity_is_a_defensive_description_without_host_claim(self):
        identity = runtime_identity()
        self.assertEqual(identity["implementation_revision"], "v19-compact-support-plane-discovery-20261028")
        self.assertEqual(identity["source_kind"], "source_checkout")
        self.assertEqual(identity["build_id"], "sha256:" + identity["source_sha256"])
        self.assertEqual(identity["capabilities"]["host_connection"], "not_checked")
        identity["capabilities"]["host_connection"] = "made_up"
        identity["source_files"].clear()
        self.assertEqual(runtime_identity()["capabilities"]["host_connection"], "not_checked")
        self.assertTrue(runtime_identity()["source_files"])

    def test_source_manifest_hash_is_reproducible_and_includes_identity(self):
        identity = runtime_identity()
        paths = [item["path"] for item in identity["source_files"]]
        self.assertEqual(paths, sorted(paths))
        self.assertIn("human_eye_plugin/runtime_identity.py", paths)
        self.assertIn("human_eye_plugin/production_server.py", paths)
        self.assertIn("human_eye_plugin/live_service.py", paths)
        canonical = {"base_version": identity["base_version"],
                     "implementation_revision": identity["implementation_revision"],
                     "files": identity["source_files"]}
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True,
            separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(digest, identity["source_sha256"])

    def test_identity_pins_match_exactly_and_missing_is_explicitly_unpinned(self):
        identity = runtime_identity()
        pins = {key: identity[key] for key in ("build_id", "implementation_revision", "protocol_version")}
        result = validate_expected_identity(pins)
        self.assertTrue(result["compatible"])
        self.assertTrue(result["pins_requested"])
        unpinned = validate_expected_identity(None)
        self.assertTrue(unpinned["compatible"])
        self.assertFalse(unpinned["pins_requested"])
        self.assertEqual(unpinned["authorization"], "identity_comparison_only")

    def test_other_build_version_mode_and_source_kind_are_rejected(self):
        for field in ("build_id", "base_version", "implementation_revision", "source_sha256",
                      "protocol_version", "source_kind", "mode"):
            with self.subTest(field=field):
                result = validate_expected_identity({field: "different"})
                self.assertFalse(result["compatible"])
                self.assertEqual(result["reasons"], ["identity_mismatch:" + field])

    def test_invalid_pins_are_not_silently_ignored(self):
        for pins in ({}, [], {"build_id": ""}, {"build_id": True}, {"accept_any_version": "yes"}):
            with self.subTest(pins=pins), self.assertRaises(ValueError):
                validate_expected_identity(pins)

    def test_existing_process_keeps_snapshot_and_new_loader_sees_changed_source(self):
        # A separate runtime tree avoids changing any actual engine source.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "human_eye_plugin"
            package.mkdir()
            (root / "human_eye_module1_operators").mkdir()
            (root / "pyproject.toml").write_text("# source checkout marker\n")
            for item in runtime_identity()["source_files"]:
                target = root / item["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / item["path"]).read_bytes())
            path = package / "runtime_identity.py"
            def load(name):
                spec = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
            initial = load("identity_initial")
            before = initial.runtime_identity()
            self.assertTrue(initial.check_source_drift()["compatible"])
            changed = package / "production_server.py"
            changed.write_bytes(changed.read_bytes() + b"\n# source change for isolated identity test\n")
            drift = initial.check_source_drift()
            self.assertFalse(drift["compatible"])
            self.assertTrue(drift["check_complete"])
            self.assertEqual(drift["status"], "changed")
            self.assertEqual(drift["changed_files"], ["human_eye_plugin/production_server.py"])
            self.assertEqual(initial.runtime_identity()["build_id"], before["build_id"])
            fresh = load("identity_fresh").runtime_identity()
            self.assertNotEqual(fresh["build_id"], before["build_id"])
            self.assertFalse(initial.validate_expected_identity({"build_id": fresh["build_id"]})["compatible"])
            added = package / "new_runtime_module.py"
            added.write_text("# newly added runtime source\n")
            self.assertEqual(initial.check_source_drift()["added_files"], ["human_eye_plugin/new_runtime_module.py"])
            added.unlink()
            removed = package / "production_server.py"
            removed.unlink()
            self.assertEqual(initial.check_source_drift()["removed_files"], ["human_eye_plugin/production_server.py"])
            mandatory = root / "human_eye_foveated_renderer.py"
            mandatory.unlink()
            failure = initial.check_source_drift()
            self.assertFalse(failure["compatible"])
            self.assertFalse(failure["check_complete"])
            self.assertEqual(failure["status"], "unavailable")
            self.assertEqual(failure["reasons"], ["runtime_source_check_failed"])
            self.assertEqual(initial.runtime_identity()["build_id"], before["build_id"])


class ReleaseScriptAliasTests(unittest.TestCase):
    def test_console_scripts_are_added_only_when_missing_and_are_idempotent(self):
        from verification.build_release_bundle import ensure_console_scripts, tomllib
        for newline in ("\n", "\r\n"):
            for source in ("[project]\nname='example'\n", "[project.scripts]\nother='entry:main'\n"):
                source = source.replace("\n", newline)
                with self.subTest(newline=repr(newline), source=source):
                    result = ensure_console_scripts(source)
                    scripts = tomllib.loads(result)["project"]["scripts"]
                    self.assertEqual(scripts["human-eye-live"], "human_eye_plugin.production_server:main")
                    self.assertEqual(scripts["human-eye-configure"], "human_eye_plugin.agent_setup:main")
                    self.assertEqual(ensure_console_scripts(result), result)

    def test_existing_production_console_entry_is_preserved_without_duplicate_keys(self):
        from verification.build_release_bundle import ensure_console_scripts, tomllib
        source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        result = ensure_console_scripts(source)
        scripts = tomllib.loads(result)["project"]["scripts"]
        self.assertEqual(scripts["human-eye-live"], "human_eye_plugin.production_server:main")
        self.assertEqual(scripts["human-eye-mcp-server"], "human_eye_plugin.production_server:main")
        self.assertEqual(result.count('human-eye-live ='), 1)


if __name__ == "__main__":
    unittest.main()
