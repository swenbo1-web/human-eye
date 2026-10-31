"""Local release metadata, launch and privacy contracts without building a ZIP."""
import ast
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import zipfile

from verification.build_local_test_bundle import (
    ROOT, DEFAULT_TESTS, EVIDENCE_ROOT, EXPECTED_IMPLEMENTATION_REVISION, INSTALLED_TEST_EXCLUSIONS, SMOKE_SOURCE, audit_engine_wheel,
    adapt_installed_test_source, child_environment, new_release_identity, plan, public_evidence, readme,
    release_project, runtime_files, validate_public_text,
)


class LocalTestBundleTests(unittest.TestCase):
    def test_unique_versions_and_names_include_rigid_frame_scope(self):
        first = new_release_identity()
        second = new_release_identity()
        self.assertNotEqual(first, second)
        for version, name in (first, second):
            self.assertIn("20261023.rigid.frame", version)
            self.assertIn("20261023.rigid.frame", name)
            self.assertTrue(version.startswith("9.7.2+"))
        with self.assertRaises(ValueError):
            new_release_identity("../escape")
        self.assertTrue(new_release_identity("001.check")[0].endswith(".1.check"))

    def test_generated_project_keeps_production_default_and_dependency_declarations(self):
        source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        original = tomllib.loads(source)
        generated = tomllib.loads(release_project(source, "9.7.2+20261023.adaptive.perception.test"))
        self.assertEqual(generated["project"]["scripts"]["human-eye-mcp-server"],
                         "human_eye_plugin.production_server:main")
        self.assertEqual(generated["project"]["dependencies"], original["project"]["dependencies"])
        self.assertEqual(generated["project"]["requires-python"], ">=3.11")
        self.assertEqual(generated["project"]["version"], "9.7.2+20261023.adaptive.perception.test")

    def test_legacy_default_is_not_silently_published_as_production(self):
        source = (ROOT / "pyproject.toml").read_text(encoding="utf-8").replace(
            'human-eye-mcp-server = "human_eye_plugin.production_server:main"',
            'human-eye-mcp-server = "human_eye_plugin.mcp_server:run_stdio_mcp_server"')
        with self.assertRaises(ValueError):
            release_project(source, "9.7.2+20261023.adaptive.perception.test")

    def test_bundle_evidence_removes_machine_locations_but_keeps_proof_relationship(self):
        stage = ROOT / "artifacts/stage-test"
        source = {"module": str(stage / "isolated_venv/Lib/site-packages/human_eye_plugin/__init__.py"),
                  "checkout": ROOT.as_posix(), "passed": True}
        result = public_evidence(source, stage)
        self.assertTrue(result["passed"])
        self.assertIn("<BUILD_WORKDIR>", result["module"])
        self.assertIn("site-packages", result["module"])
        self.assertNotIn(str(ROOT), str(result))
        self.assertEqual(result["checkout"], "<SOURCE_CHECKOUT>")

    def test_default_plan_has_no_mutation_or_upload(self):
        result = plan(suffix="contract.test")
        self.assertEqual(result["mode"], "read_only_plan")
        self.assertTrue(result["build_requires_explicit_flag"])
        self.assertEqual(result["uploads_performed"], 0)
        self.assertIn("--config", result["default_entry"])
        self.assertIn("20261023_field_validation", result["evidence_root"])
        self.assertTrue(result["synthetic_render_png_retained"])

    def test_embedded_install_smoke_compiles_and_does_not_dispatch_models(self):
        tree = ast.parse(SMOKE_SOURCE)
        self.assertTrue(tree.body)
        self.assertIn("is_relative_to(installed)", SMOKE_SOURCE)
        self.assertIn("all_required_expectations_met", SMOKE_SOURCE)
        self.assertIn("'model_api_calls':0", SMOKE_SOURCE)
        self.assertIn("'synthetic_visual':synthetic_visual", SMOKE_SOURCE)
        self.assertIn("'engine_record_integrity'", SMOKE_SOURCE)

    def test_pip_environment_cannot_redirect_install_into_user_paths(self):
        with patch.dict(os.environ, {"PIP_TARGET": "outside-user-path", "PIP_PREFIX": "outside-user-prefix",
                                     "PYTHONPATH": "checkout-path", "HUMAN_EYE_CONFIG": "user-state"}):
            result = child_environment()
        for key in ("PIP_TARGET", "PIP_PREFIX", "PYTHONPATH", "HUMAN_EYE_CONFIG"):
            self.assertNotIn(key, result)
        self.assertEqual(result["PIP_CONFIG_FILE"], os.devnull)

    def test_batch1_query_visual_delivery_tests_are_mandatory_install_regressions(self):
        required = {'test_flow_result_contract', 'test_partial_observation', 'test_task_intent',
            'test_hook_intent', 'test_live_hooks', 'test_query_policy', 'test_observation_queries',
            'test_visual_readability', 'test_delivery_pipeline', 'test_attention_raster', 'test_scene_rendering',
            'test_hook_setup_events', 'test_hook_bootstrap', 'test_observation_reuse', 'test_deferred_q4',
            'test_cache_accounting', 'test_prepared_render_inputs', 'test_contact_section'}
        self.assertTrue(required.issubset(DEFAULT_TESTS))
        self.assertFalse(any('blind' in name for name in DEFAULT_TESTS))
        self.assertEqual(len(DEFAULT_TESTS), len(set(DEFAULT_TESTS)))

    def test_public_text_rejects_real_account_and_checkout_paths(self):
        validate_public_text('<BUILD_WORKDIR>/Lib/site-packages; ../source', label='portable')
        for value in (str(ROOT), ROOT.as_posix().swapcase(), str(Path.home())):
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, 'account/workspace'):
                validate_public_text(value, label='negative privacy control')

    def test_rigid_frame_plan_writes_only_new_phase_and_requires_current_implementation(self):
        result = plan(suffix='metadata.only')
        self.assertEqual(EVIDENCE_ROOT, ROOT / 'verification/fixes/20261023_field_validation/extreme_01/repair_02')
        self.assertEqual(EXPECTED_IMPLEMENTATION_REVISION, 'v1-rigid-frame-20261023')
        self.assertEqual(result['required_implementation_revision'], EXPECTED_IMPLEMENTATION_REVISION)
        self.assertEqual(len(DEFAULT_TESTS), 40)
        self.assertIn('test_extreme_engine_boundaries', DEFAULT_TESTS)
        _, files = runtime_files()
        self.assertIn('human_eye_hook.py', files)
        self.assertIn('human_eye_plugin/contact_section.py', files)
        self.assertIn('human_eye_plugin/rigid_frame.py', files)
        self.assertFalse(any('fixes/' in path or 'blind_test/' in path for path in files))

    def test_contact_section_readme_is_explicit_opt_in_and_not_natural_visibility(self):
        text = readme('9.7.2+20261023.adaptive.perception.test',
            {'base_version':'9.7.2','implementation_revision':'current-runtime'}, 'engine.whl', [])
        self.assertIn('query.visual_diagnostic="contact_section"', text)
        self.assertIn('默认查询不附加剖面', text)
        self.assertIn('不是自然视角、真实可见空缝', text)
        self.assertNotIn('65.92%', text)

    def test_historical_fixture_exclusion_is_explicit_and_narrow(self):
        self.assertEqual(len(INSTALLED_TEST_EXCLUSIONS), 1)
        name, reason = next(iter(INSTALLED_TEST_EXCLUSIONS.items()))
        self.assertIn('test_real_blender_tiny_yaw_snapshot', name)
        self.assertIn('sealed historical Blender snapshot', reason)
        self.assertEqual(plan(suffix='selection.test')['installed_test_exclusions'], INSTALLED_TEST_EXCLUSIONS)
        self.assertIn("'explicit_exclusions':excluded", SMOKE_SOURCE)

    def test_standalone_host_fixture_adaptation_points_only_at_installed_host(self):
        original = 'MODULE_PATH = Path(__file__).resolve().parents[1] / "human_eye_plugin" / "blender_host.py"'
        source = 'from pathlib import Path\n' + original + '\n'
        adapted = adapt_installed_test_source('test_blender_host_contracts.py', source)
        ast.parse(adapted)
        self.assertNotIn(original, adapted)
        self.assertIn('MODULE_PATH = Path(_installed_fixture_host.__file__).resolve()', adapted)
        self.assertIn('assert MODULE_PATH.is_relative_to', adapted)
        self.assertIn('get_path("purelib")', adapted)
        self.assertEqual(adapt_installed_test_source('test_other.py', source), source)
        self.assertIn("'fixture_adaptations'", SMOKE_SOURCE)

    def test_changed_standalone_host_fixture_loader_requires_explicit_review(self):
        with self.assertRaisesRegex(RuntimeError, 'test loader changed'):
            adapt_installed_test_source('test_blender_host_contracts.py', 'MODULE_PATH = "somewhere_else"\n')

    def test_hook_fixture_uses_installed_root_and_refuses_unreviewed_loader(self):
        source = 'ENTRY = Path(bootstrap.__file__).resolve()\nROOT = ENTRY.parent\n'
        result = adapt_installed_test_source('test_hook_bootstrap.py', source)
        ast.parse(result)
        self.assertIn('ENTRY = Path(bootstrap.__file__).resolve()', result)
        self.assertIn('assert ROOT.is_relative_to', result)
        with self.assertRaisesRegex(RuntimeError, 'test root changed'):
            adapt_installed_test_source('test_hook_bootstrap.py', 'ROOT = "unknown"\n')

    def wheel_fixture(self, folder, *, extra_python=False, production_entry=True, hook_entry=True):
        source = folder / 'source'
        relative = 'human_eye_plugin/example.py'
        content = {relative: 'VALUE = 1\n', 'human_eye_plugin/plugin.json': '{}\n',
                   'human_eye_plugin/mcp_config.json': '{}\n'}
        for name, text in content.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8', newline='\n')
        wheel = folder / 'example.whl'
        with zipfile.ZipFile(wheel, 'w') as archive:
            for name in content:
                archive.writestr(name, (source / name).read_bytes())
            if extra_python:
                archive.writestr('undeclared.py', 'UNEXPECTED = True\n')
            archive.writestr('example.dist-info/METADATA',
                'Version: 9.7.2+test\r\nRequires-Dist: numpy>=2\r\nRequires-Dist: Pillow>=10\r\n')
            entry = 'human_eye_plugin.production_server:main' if production_entry else 'human_eye_plugin.mcp_server:main'
            hook = 'human_eye_hook:main' if hook_entry else 'human_eye_plugin.live_hooks:main'
            archive.writestr('example.dist-info/entry_points.txt',
                '[console_scripts]\nhuman-eye-mcp-server = '+entry+'\nhuman-eye-live = '+entry+'\nhuman-eye-hook = '+hook+'\n')
        return source, wheel, [relative]

    def test_wheel_audit_binds_runtime_data_and_production_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, wheel, files = self.wheel_fixture(Path(temporary))
            proof = audit_engine_wheel(wheel, source, files, '9.7.2+test')
            self.assertTrue(proof['passed'])
            self.assertEqual(proof['source_data_files'], 2)
            (source / 'human_eye_plugin/plugin.json').write_text('{"changed":true}\n', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'source/data'):
                audit_engine_wheel(wheel, source, files, '9.7.2+test')

    def test_wheel_audit_rejects_undeclared_module_and_legacy_entry(self):
        for options in ({'extra_python': True}, {'production_entry': False}, {'hook_entry': False}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temporary:
                source, wheel, files = self.wheel_fixture(Path(temporary), **options)
                with self.assertRaises(RuntimeError):
                    audit_engine_wheel(wheel, source, files, '9.7.2+test')

    def test_readme_does_not_advertise_old_runtime_benchmark_as_current_gain(self):
        text = readme('9.7.2+20261023.adaptive.perception.test',
            {'base_version':'9.7.2','implementation_revision':'current-runtime'}, 'engine.whl', [])
        self.assertIn('adaptive.perception', text)
        self.assertNotIn('59–77%', text)
        self.assertIn('validation/synthetic_near_gap.png', text)
        self.assertIn('未连接Blender', text)


if __name__ == "__main__":
    unittest.main()
