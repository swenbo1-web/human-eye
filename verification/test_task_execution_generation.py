"""Task generation contract tests with actual guarded subprocesses.

The small source trees exercise loader and identity semantics. They do not
qualify an installed release or replace the complete controlled-entry replay.
Service tests use explicit unit-test source responses to check routing only.
Readonly task checks cover bound object identity. Global module-origin audit
belongs to explicit full diagnostics and actual guarded execution.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ROOT_MODULES = (
    "human_eye_hook.py",
    "human_eye_foveated_renderer.py",
    "native_3d_spatial_scratchpad.py",
    "module_2_low_token_mcp_scene_bridge.py",
    "module_3_1_mcp_protocol_ipc_engine.py",
    "module_3_2_vlm_grounding_closed_loop_agent.py",
    "module_3_3_closed_loop_control_engine.py",
)


class TaskExecutionGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="he-task-generation-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.files = {name: b"# Guard protocol fixture.\n" for name in ROOT_MODULES}
        self.files.update({
            "human_eye_plugin/__init__.py": b"",
            "human_eye_module1_operators/__init__.py": b"",
            "human_eye_plugin/direct.py": b"VALUE='original'\n",
            "human_eye_plugin/lazy.py": b"VALUE='unloaded'\n",
        })
        for name in ("runtime_identity.py", "verified_source_loader.py"):
            relative = "human_eye_plugin/" + name
            self.files[relative] = (ROOT / relative).read_bytes()
        for relative, blob in self.files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
        (self.root / "pyproject.toml").write_text("# Source fixture.\n", encoding="utf-8")
        self.manifest = [{"path": name, "sha256": hashlib.sha256(blob).hexdigest()}
                         for name, blob in sorted(self.files.items())]

    def child(self, body, *, before_import="", install_guard=True):
        loader = self.root / "human_eye_plugin/verified_source_loader.py"
        script = "\n".join([
            "import hashlib, importlib, json, os, sys, types",
            "from pathlib import Path",
            "from types import MappingProxyType",
            "from unittest.mock import patch",
            "root = Path(" + repr(str(self.root)) + ")",
            "manifest = json.loads(" + repr(json.dumps(self.manifest)) + ")",
            "loader_path = root / 'human_eye_plugin/verified_source_loader.py'",
            "loader_bytes = loader_path.read_bytes()",
            "assert hashlib.sha256(loader_bytes).hexdigest() == "
                + repr(hashlib.sha256(loader.read_bytes()).hexdigest()),
            "helper = types.ModuleType('_task_guard_bootstrap')",
            "helper.__file__ = str(loader_path)",
            "sys.modules[helper.__name__] = helper",
            "exec(compile(loader_bytes, str(loader_path), 'exec', dont_inherit=True), helper.__dict__)",
            "guard = helper.install(root, manifest, bootstrap_module=helper)"
                if install_guard else "guard = None",
            textwrap.dedent(before_import),
            "sys.path.insert(0, str(root))",
            "identity = importlib.import_module('human_eye_plugin.runtime_identity')",
            "loaded_build = identity.runtime_identity()['build_id']",
            textwrap.dedent("""
                def generation():
                    result = identity.check_task_source()
                    assert result['compatible'] is True, result
                    assert result['check_complete'] is True, result
                    assert result['status'] == 'loaded_generation', result
                    assert result['disk_status'] == 'disk_not_checked', result
                    assert result['source_check_scope'] == 'bound_generation_identity', result
                    assert result['loaded_build_id'] == loaded_build, result
                    assert result['disk_build_id'] is None, result
                    return result

                def unverified():
                    with patch.object(identity, '_capture_source_identity',
                                      side_effect=AssertionError('invalid guard fell back to disk')):
                        result = identity.check_task_source()
                    assert result['compatible'] is False, result
                    assert result['check_complete'] is False, result
                    assert result['status'] == 'unavailable', result
                    assert result['source_check_scope'] == 'bound_generation_identity', result
                    assert result['reasons'] == ['runtime_executed_source_unverified'], result
                    return result
            """),
            textwrap.dedent(body),
        ])
        result = subprocess.run([sys.executable, "-I", "-B", "-c", script],
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"UNVERIFIED_PYC_EXECUTED", result.stderr)
        return result

    def test_task_checks_bound_identity_without_global_audit_or_disk_reads(self):
        self.child("""
            original_code = type(guard).verify_loaded.__code__
            calls = []
            def profile(frame, event, argument):
                if event == 'call' and frame.f_code is original_code:
                    calls.append(frame.f_code)
            sys.setprofile(profile)
            try:
                with patch.object(Path, 'read_bytes', side_effect=AssertionError('warm disk scan')), \
                     patch.object(helper, '_resolve_source_origin', side_effect=AssertionError('task global origin scan')):
                    generation()
                    generation()
            finally:
                sys.setprofile(None)
            assert len(calls) == 0, len(calls)
        """)

    def test_loaded_source_edit_keeps_old_execution_and_explicit_diagnosis_detects_it(self):
        self.child("""
            direct = importlib.import_module('human_eye_plugin.direct')
            path = root / 'human_eye_plugin/direct.py'
            path.write_bytes(b"VALUE='tampered'\\n")
            generation()
            assert direct.VALUE == 'original'
            drift = identity.check_source_drift()
            assert drift['compatible'] is False and drift['status'] == 'changed', drift
            assert drift['changed_files'] == ['human_eye_plugin/direct.py'], drift
            assert identity.runtime_identity()['build_id'] == loaded_build
        """)

    def test_loaded_source_deletion_is_not_a_fresh_disk_claim(self):
        self.child("""
            importlib.import_module('human_eye_plugin.direct')
            (root / 'human_eye_plugin/direct.py').unlink()
            generation()
            drift = identity.check_source_drift()
            assert drift['compatible'] is False and drift['status'] == 'changed', drift
            assert drift['removed_files'] == ['human_eye_plugin/direct.py'], drift
        """)

    def test_unrelated_added_source_does_not_refresh_loaded_generation(self):
        self.child("""
            (root / 'human_eye_plugin/unrelated.py').write_text('# Added source.\\n', encoding='utf-8')
            generation()
            drift = identity.check_source_drift()
            assert drift['compatible'] is False and drift['status'] == 'changed', drift
            assert drift['added_files'] == ['human_eye_plugin/unrelated.py'], drift
        """)

    def test_first_lazy_same_size_same_mtime_change_is_rejected(self):
        self.child("""
            path = root / 'human_eye_plugin/lazy.py'
            original = path.read_bytes()
            metadata = path.stat()
            path.write_bytes(original.replace(b'unloaded', b'tampered'))
            os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
            assert path.stat().st_size == metadata.st_size
            assert path.stat().st_mtime_ns == metadata.st_mtime_ns
            generation()
            try:
                importlib.import_module('human_eye_plugin.lazy')
            except helper.SourceBindingError as error:
                assert str(error) == 'verified_source_changed:human_eye_plugin/lazy.py', str(error)
            else:
                raise AssertionError('changed lazy source executed')
            assert 'human_eye_plugin.lazy' not in sys.modules
        """)

    def test_alias_reexecution_after_drift_keeps_original_byte_check(self):
        self.child("""
            path = root / 'human_eye_plugin/direct.py'
            module = types.ModuleType('_task_verified_alias')
            module.__file__ = str(path)
            sys.modules[module.__name__] = module
            helper.exec_verified(module, path)
            generation()
            metadata = path.stat()
            path.write_bytes(path.read_bytes().replace(b'original', b'tampered'))
            os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
            generation()
            try:
                helper.exec_verified(module, path)
            except helper.SourceBindingError as error:
                assert str(error) == 'verified_source_changed:human_eye_plugin/direct.py', str(error)
            else:
                raise AssertionError('changed alias source executed')
            assert module.VALUE == 'original'
        """)

    def test_worker_launch_does_not_inherit_task_read_permission(self):
        self.child("""
            worker_loader = importlib.import_module('human_eye_plugin.verified_source_loader')
            importlib.import_module('human_eye_plugin.direct')
            path = root / 'human_eye_plugin/direct.py'
            path.write_bytes(b"VALUE='tampered'\\n")
            generation()
            try:
                worker_loader.worker_arguments(root, path)
            except worker_loader.SourceBindingError as error:
                assert str(error) == 'verified_source_parent_drift', str(error)
            else:
                raise AssertionError('worker accepted changed parent source')
        """)

    def test_no_guard_sdk_still_scans_and_rejects_changed_disk(self):
        self.child("""
            reads = []
            original_read = Path.read_bytes
            def reading(path):
                reads.append(path.relative_to(root).as_posix())
                return original_read(path)
            with patch.object(Path, 'read_bytes', reading):
                result = identity.check_task_source()
            assert result['compatible'] is True and result['status'] == 'unchanged', result
            assert 'source_check_scope' not in result, result
            assert set(reads) == {row['path'] for row in manifest}
            assert len(reads) == len(manifest)
            (root / 'human_eye_plugin/direct.py').write_bytes(b"VALUE='changed'\\n")
            result = identity.check_task_source()
            assert result['compatible'] is False and result['status'] == 'changed', result
            assert 'source_check_scope' not in result, result
            assert result['changed_files'] == ['human_eye_plugin/direct.py'], result
        """, install_guard=False)

    def test_guard_removed_after_binding_cannot_fall_back(self):
        self.child("sys.meta_path.remove(guard)\nunverified()")

    def test_guard_replaced_by_same_class_cannot_fall_back(self):
        self.child("""
            replacement = helper.SourceGuard(root, guard.sources)
            sys.meta_path[sys.meta_path.index(guard)] = replacement
            unverified()
        """)

    def test_immutable_mapping_replaced_with_equal_bytes_is_rejected(self):
        self.child("guard.sources = MappingProxyType(dict(guard.sources))\nunverified()")

    def test_bound_method_replacement_is_rejected(self):
        self.child("guard.verify_loaded = lambda: True\nunverified()")

    def test_class_method_replacement_is_rejected(self):
        self.child("type(guard).verify_loaded = lambda self: True\nunverified()")

    def test_bootstrap_loader_module_replacement_is_rejected(self):
        self.child("sys.modules[helper.__name__] = types.ModuleType(helper.__name__)\nunverified()")

    def test_owned_identity_module_replacement_is_rejected(self):
        self.child("""
            replacement = types.ModuleType('human_eye_plugin.runtime_identity')
            replacement.__file__ = identity.__file__
            sys.modules[replacement.__name__] = replacement
            result = unverified()
            assert 'verified_source_preloaded_module:human_eye_plugin.runtime_identity' in result.get('error', ''), result
        """)

    def test_unwitnessed_external_alias_is_audited_only_by_explicit_full_check(self):
        self.child("""
            module = types.ModuleType('_task_unverified_alias')
            module.__file__ = str(root / 'human_eye_plugin/direct.py')
            sys.modules[module.__name__] = module
            generation()
            result = identity.check_source_drift()
            assert result['compatible'] is False and result['status'] == 'unavailable', result
            assert result['reasons'] == ['runtime_executed_source_unverified'], result
            assert 'verified_source_preloaded_module:_task_unverified_alias' in result.get('error', ''), result
        """)

    def test_namespace_mutation_is_outside_task_scope_and_explicit_audit_rejects_it(self):
        self.child("""
            namespace = types.ModuleType('human_eye_plugin')
            namespace.__path__ = [str(root / 'human_eye_plugin')]
            guard.allow_namespace(namespace)
            sys.modules[namespace.__name__] = namespace
            generation()
            namespace.__file__ = []
            generation()
            try:
                guard.verify_loaded()
            except TypeError:
                pass
            else:
                raise AssertionError('explicit audit accepted malformed namespace origin')
        """)

    def test_guard_manifest_mismatch_at_initial_binding_is_rejected(self):
        self.child("unverified()", before_import="""
            changed = dict(guard.sources)
            changed['human_eye_plugin/direct.py'] = b"VALUE='different'\\n"
            guard.sources = MappingProxyType(changed)
        """)

    def test_duplicate_guard_at_initial_binding_is_rejected(self):
        self.child("unverified()", before_import="sys.meta_path.insert(0, guard)")

    def test_external_class_verifier_at_initial_binding_is_rejected(self):
        self.child("""
            module = types.ModuleType('human_eye_plugin.unverified')
            module.__file__ = str(root / 'human_eye_plugin/direct.py')
            sys.modules[module.__name__] = module
            result = unverified()
            assert result['error'] == 'ValueError: runtime_source_verifier_unverified', result
        """, before_import="type(guard).verify_loaded = lambda self: True")

    def test_unverified_finder_at_initial_binding_cannot_become_sdk(self):
        self.child("unverified()", install_guard=False, before_import="""
            class UnverifiedFinder:
                protocol = 'human-eye-verified-source-v1'
                root = root
                sources = MappingProxyType({row['path']: (root / row['path']).read_bytes() for row in manifest})
                def find_spec(self, fullname, path=None, target=None):
                    return None
                def verify_loaded(self):
                    return True
            sys.meta_path.insert(0, UnverifiedFinder())
        """)

    def test_foreign_root_guard_at_initial_binding_cannot_become_sdk(self):
        self.child("unverified()", install_guard=False, before_import="""
            class ForeignFinder:
                protocol = 'human-eye-verified-source-v1'
                root = root / 'other-root'
                def find_spec(self, fullname, path=None, target=None):
                    return None
                def verify_loaded(self):
                    return True
            sys.meta_path.insert(0, ForeignFinder())
        """)

    def test_late_guard_does_not_promote_sdk_import(self):
        self.child("""
            finder = types.SimpleNamespace(protocol='human-eye-verified-source-v1', root=root)
            sys.meta_path.insert(0, finder)
            unverified()
        """, install_guard=False)

    def test_valid_timestamp_bytecode_marker_does_not_execute(self):
        self.child("""
            import py_compile
            import struct
            path = root / 'human_eye_plugin/direct.py'
            original = path.read_bytes()
            metadata = path.stat()
            path.write_bytes(original + b"raise RuntimeError('UNVERIFIED_PYC_EXECUTED')\\n")
            cache = Path(py_compile.compile(str(path), doraise=True))
            raw = cache.read_bytes()
            header = struct.pack('<II', int(metadata.st_mtime) & 0xffffffff, len(original))
            cache.write_bytes(raw[:8] + header + raw[16:])
            path.write_bytes(original)
            os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
            direct = importlib.import_module('human_eye_plugin.direct')
            assert direct.VALUE == 'original'
            generation()
        """)


class TaskExecutionGenerationRoutingTests(unittest.TestCase):
    def setUp(self):
        from human_eye_plugin.live_service import LiveSpatialService
        from verification.test_live_service import SelfLockingHost

        self.temporary = tempfile.TemporaryDirectory(prefix="he-task-generation-routing-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        config = self.folder / "live.json"
        config.write_text(json.dumps({"schema_version": "1.0", "enabled": True,
            "project_root": str(ROOT), "state_file": "state.json",
            "audit_file": "events.jsonl", "quad_size": 64}), encoding="utf-8")
        self.host = SelfLockingHost()
        self.service = LiveSpatialService(config, host=self.host, production_mode=True)
        self.query = {"mode": "task", "objects": [{"name": "part"}], "requested_facts": ["aabb"]}
        self.generation = {"compatible": True, "check_complete": True,
            "status": "loaded_generation", "disk_status": "disk_not_checked", "reasons": [],
            "source_check_scope": "bound_generation_identity",
            "loaded_build_id": self.service.describe_runtime()["build_id"], "disk_build_id": None}

    def test_only_task_uses_loaded_generation_and_preserves_fresh_scene(self):
        with patch("human_eye_plugin.live_service.check_task_source", return_value=self.generation) as task_check, \
             patch("human_eye_plugin.live_service.check_source_drift", side_effect=AssertionError("task disk scan")):
            first = self.service.observe("s", query=self.query, include_image=False)
            self.host.scene["revision"] = "new-scene"
            self.host.scene["meshes"][1]["object_id"] = "replacement"
            second = self.service.observe("s", query=self.query, include_image=False)
        self.assertEqual(task_check.call_count, 2)
        self.assertEqual(self.host.captures, 2)
        self.assertEqual(first["binding"]["source_status"], "loaded_generation")
        self.assertEqual(first["binding"]["disk_status"], "disk_not_checked")
        self.assertEqual(first["binding"]["source_check_scope"], "bound_generation_identity")
        self.assertEqual(second["binding"]["source_check_scope"], "bound_generation_identity")
        self.assertEqual(second["binding"]["objects"][0]["object_id"], "replacement")
        self.assertNotEqual(first["binding"]["scene_fingerprint"], second["binding"]["scene_fingerprint"])
        self.assertEqual(second["binding"]["scene_revision"], "new-scene")
        self.assertFalse(second["execution_authority"])
        self.assertEqual(self.host.calls, 0)

    def test_source_failure_prevents_capture_and_has_no_disk_fallback(self):
        failure = {**self.generation, "compatible": False, "check_complete": False,
                   "status": "unavailable", "reasons": ["runtime_executed_source_unverified"]}
        with patch("human_eye_plugin.live_service.check_task_source", return_value=failure), \
             patch("human_eye_plugin.live_service.check_source_drift", side_effect=AssertionError("invalid guard fallback")):
            result = self.service.observe("s", query=self.query, include_image=False)
        self.assertEqual(result["status"], "implementation_mismatch")
        self.assertEqual(result["reason_codes"], ["runtime_executed_source_unverified"])
        self.assertEqual(self.host.captures, 0)
        self.assertFalse(result["allow_action"])

    def test_legacy_observation_and_write_preview_keep_disk_gate(self):
        failure = {"compatible": False, "check_complete": True, "status": "changed",
                   "reasons": ["runtime_source_changed_restart_required"]}
        action = {"focal_id": "part", "reference_id": "base", "translation": [0, 0, 0.01]}
        with patch("human_eye_plugin.live_service.check_task_source", side_effect=AssertionError("legacy generation path")), \
             patch("human_eye_plugin.live_service.check_source_drift", return_value=failure) as disk_check:
            observed = self.service.observe("s", include_image=False)
            preview = self.service.preview_action("s", action)
            written = self.service.transform("s", action)
        self.assertEqual(disk_check.call_count, 3)
        for result in (observed, preview, written):
            self.assertEqual(result["status"], "implementation_mismatch")
            self.assertEqual(result["reason_codes"], ["runtime_source_changed_restart_required"])
        self.assertEqual(self.host.captures, 0)
        self.assertEqual(self.host.calls, 0)

    def test_task_bridge_check_still_refuses_mismatched_host_source(self):
        from human_eye_plugin.blender_mcp_host import BlenderMCPHost

        source = self.folder / "blender_host.py"
        source.write_text("# Wrong bridge source.\n", encoding="utf-8")
        host = object.__new__(BlenderMCPHost)
        host.source = source
        self.service.host = host
        with patch("human_eye_plugin.live_service.check_task_source", return_value=self.generation):
            result = self.service.observe("s", query=self.query, include_image=False)
        self.assertEqual(result["status"], "implementation_mismatch")
        self.assertEqual(result["reason_codes"], ["host_bridge_source_mismatch"])

    def test_sdk_task_binding_keeps_ordinary_disk_scope(self):
        result = self.service.observe("s", query=self.query, include_image=False)
        self.assertEqual(result["status"], "observed")
        self.assertNotIn("source_status", result["binding"])
        self.assertNotIn("disk_status", result["binding"])
        self.assertNotIn("source_check_scope", result["binding"])
        self.assertFalse(result["execution_authority"])


if __name__ == "__main__":
    unittest.main()
