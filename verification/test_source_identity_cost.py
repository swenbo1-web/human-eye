"""Source enumeration optimization must retain byte-level drift detection."""
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin import runtime_identity as identity


class SourceIdentityFreshnessTests(unittest.TestCase):
    def test_manifest_matches_original_canonical_algorithm(self):
        root = Path(identity.__file__).resolve().parents[1]
        paths = {root / p for p in identity._ROOT_MODULES}
        for package in ('human_eye_plugin', 'human_eye_module1_operators'):
            paths.update((root/package).glob('*.py'))
        expected = [{'path': p.relative_to(root).as_posix(),
                     'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                    for p in sorted(paths, key=lambda p: p.relative_to(root).as_posix())]
        self.assertEqual(identity._source_manifest(root), expected)

    def test_same_size_and_mtime_rewrite_remains_detectable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'pyproject.toml').write_text('# isolated source checkout')
            for package in ('human_eye_plugin', 'human_eye_module1_operators'):
                (root/package).mkdir()
                (root/package/'__init__.py').write_text('# package')
            for name in identity._ROOT_MODULES:
                (root/name).write_text('# unchanged\n')
            source = root/'human_eye_plugin/runtime_identity.py'
            source.write_bytes(Path(identity.__file__).read_bytes())
            spec = importlib.util.spec_from_file_location('isolated_cost_identity', source)
            loaded = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loaded)
            target = root/identity._ROOT_MODULES[0]
            previous = target.stat()
            target.write_bytes(target.read_bytes().replace(b'unchanged', b'different'))
            os.utime(target, ns=(previous.st_atime_ns, previous.st_mtime_ns))
            self.assertEqual(target.stat().st_size, previous.st_size)
            self.assertEqual(target.stat().st_mtime_ns, previous.st_mtime_ns)
            result = loaded.check_source_drift()
            self.assertFalse(result['compatible'])
            self.assertEqual(result['changed_files'], [identity._ROOT_MODULES[0]])
            with patch.object(Path, 'read_bytes', side_effect=PermissionError('injected read failure')):
                result = loaded.check_source_drift()
            self.assertFalse(result['compatible'])
            self.assertFalse(result['check_complete'])


if __name__ == '__main__':
    unittest.main()
