"""Exact-byte packaging, archive integrity and private-file exclusion."""
from pathlib import Path
import hashlib,io,json,tempfile,unittest,zipfile
from unittest.mock import patch
from verification.build_candidate_release import wheel_bytes,verify_wheel,safe_name


class CandidateReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        (self.root/'human_eye_plugin').mkdir();(self.root/'module.py').write_bytes(b'x=1\r\n')
        for name in ('plugin.json','mcp_config.json'):(self.root/'human_eye_plugin'/name).write_text('{}',encoding='utf8')
        self.manifest=[dict(path='module.py',sha256=hashlib.sha256(b'x=1\r\n').hexdigest())]
        self.project=dict(name='human-eye-spatial-plugin',**{'requires-python':'>=3.10'},dependencies=['numpy>=2.0'],scripts={'human-eye-live':'human_eye_plugin.production_server:main'})

    def wheel(self):return wheel_bytes(self.root,self.manifest,self.project,'9.7.2+20261101.test.rc1')

    def test_deterministic_bytes_records_and_crlf_preserved(self):
        name,raw=self.wheel();self.assertTrue(name.endswith('-py3-none-any.whl'));self.assertEqual(raw,self.wheel()[1])
        self.assertTrue(verify_wheel(raw)['all_hashes_verified'])
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(archive.read('module.py'),b'x=1\r\n')
            metadata=archive.read(next(n for n in archive.namelist() if n.endswith('/METADATA'))).decode()
            self.assertIn('Version: 9.7.2+20261101.test.rc1',metadata)

    def test_private_files_and_unlisted_modules_are_excluded(self):
        (self.root/'secret.env').write_text('private');(self.root/'private.py').write_text('private')
        with zipfile.ZipFile(io.BytesIO(self.wheel()[1])) as archive:
            self.assertNotIn('secret.env',archive.namelist());self.assertNotIn('private.py',archive.namelist())

    def test_changed_source_duplicate_manifest_and_path_escape_refused(self):
        (self.root/'module.py').write_bytes(b'x=2\n')
        with self.assertRaisesRegex(ValueError,'source_changed'):self.wheel()
        (self.root/'module.py').write_bytes(b'x=1\r\n');self.manifest*=2
        with self.assertRaisesRegex(ValueError,'manifest_order'):self.wheel()
        for name in ('../secret','/secret','D:/secret','a\\b','a/../b'):
            with self.subTest(name=name),self.assertRaises(ValueError):safe_name(name)

    def test_corrupted_payload_missing_record_and_duplicate_archive_refused(self):
        name,raw=self.wheel()
        with zipfile.ZipFile(io.BytesIO(raw)) as original:
            members={n:original.read(n) for n in original.namelist()}
        for mutation in ('payload','record','duplicate'):
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w') as archive:
                for n,v in members.items():
                    if mutation=='record' and n.endswith('/RECORD'):continue
                    archive.writestr(n,b'x=0' if mutation=='payload' and n=='module.py' else v)
                if mutation=='duplicate':
                    import warnings
                    with warnings.catch_warnings():warnings.simplefilter('ignore');archive.writestr('module.py',b'x=1')
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):verify_wheel(output.getvalue())

    def test_version_injection_refused(self):
        for version in ('bad-version','9.7.2\nOther: injected','9.7.2/../../bad'):
            with self.subTest(version=version),self.assertRaises(ValueError):wheel_bytes(self.root,self.manifest,self.project,version)


if __name__=='__main__':unittest.main()
