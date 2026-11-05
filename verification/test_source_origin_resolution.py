"""Bounded source-origin equivalence and explicit fallback selection tests.

Mocked namespace/error outputs exercise routing only. Real filesystem cases
and unavailable symlink/permission fixtures are reported separately.
"""

import os
from pathlib import Path, PureWindowsPath
import subprocess
import tempfile
import unittest
from unittest import mock

from human_eye_plugin import verified_source_loader as loader


@unittest.skipUnless(os.name == 'nt' and loader._native_final_path is not None,
                     'Native Windows origin resolver is unavailable')
class SourceOriginResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='he-origin-')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()
        self.file = self.folder / 'CaseFile.py'
        self.file.write_bytes(b'# owned origin fixture\n')
        self.raw = str(self.file)
        self.assertLess(len(self.raw.encode('utf-16-le')), 480)

    def test_ordinary_unicode_spaces_and_reserved_prefixes(self):
        for name in ('CaseFile.py', 'space name.py', '中文_İ_ß_é.py', 'emoji_😀.py', 'CONTEXT.py', 'COM10.py'):
            with self.subTest(name=name):
                self.assertTrue(loader._ordinary_source_path(str(self.folder / name)))

    def test_ambiguous_inputs_use_original_resolver_without_native_attempt(self):
        prefix = str(self.folder) + '\\'
        inputs = ['relative.py', 'C:relative.py', '\\relative.py', 'C:\\',
                  '\\\\server\\share\\file.py', '\\\\?\\C:\\file.py', '\\\\.\\C:\\file.py',
                  'Ā:\\file.py', prefix + '.\\file.py', prefix + '..\\file.py',
                  prefix + '\\file.py', prefix + 'file.py\\', prefix + 'tail.\\file.py',
                  prefix + 'tail \\file.py', prefix + 'file.py:stream', prefix + 'file.py.',
                  prefix + 'file.py ', prefix + 'CON .txt', prefix + 'CONIN$', prefix + 'COM¹.py',
                  prefix + 'LPT².py', prefix + 'COM³ .py', prefix + 'NUL\\file.py',
                  prefix + 'a\x00.py', prefix + 'a\t.py', prefix + 'a\x7f.py', prefix + 'a\x85.py',
                  prefix + 'a<.py', prefix + 'a>.py', prefix + 'a?.py', prefix + 'a*.py',
                  prefix + 'a|.py', prefix + 'a".py', prefix + 'a/b.py', prefix + '\ud800.py']
        sentinel = self.file
        for raw in inputs:
            with self.subTest(raw=raw), mock.patch.object(loader, '_native_final_path') as native, \
                    mock.patch.object(Path, 'resolve', return_value=sentinel) as fallback:
                self.assertFalse(loader._ordinary_source_path(raw))
                self.assertIs(loader._resolve_source_origin(raw), sentinel)
                native.assert_not_called()
                fallback.assert_called_once()

    def test_utf16_length_and_raw_length_boundaries(self):
        prefix = str(self.folder) + '\\'
        unit_count = len(prefix.encode('utf-16-le')) // 2
        allowed = prefix + 'a' * (239 - unit_count)
        boundary = prefix + 'a' * (240 - unit_count)
        astral = prefix + '😀' * ((240 - unit_count) // 2) + 'a' * ((240 - unit_count) % 2)
        self.assertTrue(loader._ordinary_source_path(allowed))
        self.assertFalse(loader._ordinary_source_path(boundary))
        self.assertLess(len(astral), 240)
        self.assertFalse(loader._ordinary_source_path(astral))
        self.assertFalse(loader._ordinary_source_path(prefix + 'a' * 10000))

    def test_special_or_long_canonical_outputs_use_original_fallback(self):
        outputs = [self.raw, '\\\\?\\UNC\\server\\share\\file.py', '\\\\.\\C:\\file.py',
                   '\\\\?\\Volume{00000000-0000-0000-0000-000000000000}\\file.py',
                   '\\\\?\\' + str(self.folder / 'CON .py'), '\\\\?\\' + str(self.folder / 'tail.\\file.py'),
                   '\\\\?\\' + str(self.folder / 'file.py:stream'), '\\\\?\\C:\\' + 'a' * 240,
                   '\\\\?\\C:\\' + '😀' * 130, '\\\\?\\C:\\bad\x85.py', None, b'bytes', self.file]
        for output in outputs:
            with self.subTest(output=output), \
                    mock.patch.object(loader, '_native_final_path', return_value=output) as native, \
                    mock.patch.object(Path, 'resolve', return_value=self.file) as fallback:
                self.assertIs(loader._resolve_source_origin(self.raw), self.file)
                native.assert_called_once_with(self.raw)
                fallback.assert_called_once()

    def test_native_errors_and_original_loop_exception_are_preserved(self):
        for error in (FileNotFoundError('fixture'), PermissionError('fixture'), ValueError('fixture')):
            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(loader, '_native_final_path', side_effect=error), \
                    mock.patch.object(Path, 'resolve', side_effect=RuntimeError('original loop')) as fallback:
                with self.assertRaisesRegex(RuntimeError, 'original loop'):
                    loader._resolve_source_origin(self.raw)
                fallback.assert_called_once()

    def test_missing_native_capability_uses_original_resolver(self):
        with mock.patch.object(loader, '_native_final_path', None), \
                mock.patch.object(Path, 'resolve', return_value=self.file) as fallback:
            self.assertIs(loader._resolve_source_origin(self.raw), self.file)
            fallback.assert_called_once()

    def test_invalid_types_keep_original_constructor_errors(self):
        for value in (None, 1, [], {}, b'bytes'):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    Path(value).resolve()
                with self.assertRaises(TypeError):
                    loader._resolve_source_origin(value)

    def test_pathlike_and_string_subclass_stay_on_original_path(self):
        raw = self.raw
        class CountedPath:
            def __init__(self):
                self.calls = 0
            def __fspath__(self):
                self.calls += 1
                return raw
        class StringSubclass(str):
            pass
        pathlike = CountedPath()
        with mock.patch.object(loader, '_native_final_path', side_effect=AssertionError('unexpected fast path')):
            self.assertEqual(loader._resolve_source_origin(pathlike), Path(self.raw).resolve())
            self.assertEqual(pathlike.calls, 1)
            self.assertEqual(loader._resolve_source_origin(StringSubclass(raw)), Path(raw).resolve())

    def test_existing_files_retain_pathlib_case_and_component_comparisons(self):
        for name in ('CaseFile.py', 'space name.py', '中文_İ_ß_é.py', 'emoji_😀.py', 'control_\x85.py'):
            path = self.folder / name
            path.write_bytes(b'# filename fixture\n')
            with self.subTest(name=name):
                self.assertEqual(loader._resolve_source_origin(str(path)), path.resolve())
        self.assertEqual(loader._resolve_source_origin(self.raw.upper()), self.file.resolve())
        sibling = self.folder.with_name(self.folder.name + '_sibling') / 'CaseFile.py'
        self.assertFalse(loader._resolve_source_origin(str(sibling)).is_relative_to(self.folder))

    def test_each_normal_comparison_uses_one_fresh_native_lookup_and_no_stat(self):
        original = loader._native_final_path
        with mock.patch.object(loader, '_native_final_path', wraps=original) as native, \
                mock.patch.object(Path, 'resolve', side_effect=AssertionError('normal fallback')), \
                mock.patch.object(Path, 'stat', side_effect=AssertionError('normal stat')):
            first = loader._resolve_source_origin(self.raw)
            second = loader._resolve_source_origin(self.raw)
            self.assertEqual(first, second)
            self.assertEqual(native.call_count, 2)

    def test_missing_existing_then_deleted_file_follows_original_fallback(self):
        missing = self.folder / 'missing.py'
        self.assertEqual(loader._resolve_source_origin(str(missing)), missing.resolve())
        self.file.unlink()
        self.assertEqual(loader._resolve_source_origin(self.raw), self.file.resolve())

    def create_junction(self, link, target):
        command = ['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(target)]
        result = subprocess.run(command, capture_output=True, timeout=10)
        if result.returncode:
            self.skipTest('Owned junction creation unavailable')
        self.addCleanup(os.rmdir, link)
        value = os.readlink(link)
        if not value.startswith('\\\\?\\') or PureWindowsPath(value[4:]) != PureWindowsPath(target):
            self.skipTest('Owned junction target could not be verified')

    def test_real_junction_and_target_length_fallback(self):
        base = self.folder / 'long'
        count = 250 - len(str(base).encode('utf-16-le')) // 2 - 2 - len('CaseFile.py')
        target = base / ('a' * count)
        target.mkdir(parents=True)
        (target / 'CaseFile.py').write_bytes(b'# canonical length fixture\n')
        link = self.folder / 'short_link'
        self.create_junction(link, target)
        raw = str(link / 'CaseFile.py')
        canonical = loader._native_final_path(raw)
        self.assertTrue(canonical.startswith('\\\\?\\'))
        self.assertFalse(loader._ordinary_source_path(canonical[4:]))
        expected = Path(raw).resolve()
        original = Path.resolve
        calls = []
        def resolve(path, *args, **kwargs):
            calls.append(str(path))
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, 'resolve', resolve):
            self.assertEqual(loader._resolve_source_origin(raw), expected)
        self.assertEqual(len(calls), 1)

    def test_real_leaf_symlink_when_available(self):
        link = self.folder / 'leaf_link.py'
        try:
            os.symlink(self.file, link)
        except OSError as exc:
            self.skipTest('Leaf symlink privilege unavailable: ' + str(exc))
        self.addCleanup(link.unlink)
        self.assertEqual(loader._resolve_source_origin(str(link)), self.file.resolve())

    @unittest.skip('A verified real filesystem cycle could not be created in finite qualification')
    def test_actual_symlink_loop(self):
        pass

    @unittest.skip('No isolated access-denied principal fixture; routing is covered by explicit units')
    def test_actual_access_denied(self):
        pass

    @unittest.skip('Finite qualification returned no usable 8.3 alias on the current filesystem')
    def test_actual_short_name(self):
        pass


if __name__ == '__main__':
    unittest.main()
