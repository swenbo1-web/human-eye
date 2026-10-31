"""Opt-in actual RNA tests; no approximation of the renderer's setter logic."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path

BLENDER=os.environ.get('HUMAN_EYE_TEST_BLENDER')

@unittest.skipUnless(BLENDER and Path(BLENDER).is_file(),'Set HUMAN_EYE_TEST_BLENDER for real Blender RNA integration')
class PNGStateRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        root=Path(__file__).resolve().parents[1];folder=Path(cls.temp.name)
        with (folder/'stdout.log').open('wb') as out,(folder/'stderr.log').open('wb') as err:
            process=subprocess.Popen([BLENDER,'--factory-startup','--disable-autoexec','--background',
                '--python-expr','import sys;sys.dont_write_bytecode=True','--python',
                str(root/'verification/blender_png_state_probe.py'),'--',str(root),str(folder)],
                stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:process.wait(timeout=60.)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5.);raise
        if not (folder/'RESULT.json').exists():raise AssertionError((folder/'stderr.log').read_text(encoding='utf8'))
        cls.result=json.loads((folder/'RESULT.json').read_text(encoding='utf8'))
        cls.returncode=process.returncode

    def test_factory_png_keeps_uninitialized_name_and_repeat_restores_all_state(self):
        rows=[r for r in self.result['rows'] if r['profile']=='default_png']
        self.assertEqual(len(rows),3)
        for row in rows:
            with self.subTest(view=row['view']):
                self.assertIsNone(row['error']);self.assertTrue(row['image_returned'])
                self.assertTrue(row['empty_name_before']);self.assertTrue(row['empty_name_after'])
                self.assertTrue(row['full_state_equal']);self.assertTrue(row['repeat_full_state_equal'])
                self.assertTrue(row['geometry_equal']);self.assertTrue(row['writer_stores_absent'])

    def test_initialized_and_non_png_formats_restore_without_changing_geometry(self):
        rows=[r for r in self.result['rows'] if r['profile']!='default_png']
        self.assertEqual(len(rows),9)
        for row in rows:
            with self.subTest(profile=row['profile'],view=row['view']):
                self.assertIsNone(row['error']);self.assertTrue(row['full_state_equal'])
                self.assertTrue(row['geometry_equal']);self.assertTrue(row['png_384'])
                self.assertEqual(row['format_before'],row['format_after']);self.assertTrue(row['writer_stores_absent'])
        self.assertTrue(self.result['input_SHA_unchanged']);self.assertEqual(self.returncode,0)

if __name__=='__main__':unittest.main()
