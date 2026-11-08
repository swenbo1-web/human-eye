"""Exactly three same-byte constructor mocks; no child/server/consumer run."""
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

HERE=Path(__file__).resolve().parent;OUT=HERE/sys.argv[1];OUT.mkdir(exist_ok=False)
raw=(HERE/'bridge.py').read_bytes();digest=hashlib.sha256(raw).hexdigest()
bridge=types.ModuleType('_child_receipt_frozen_bridge');bridge.__file__=str(HERE/'bridge.py')
sys.modules[bridge.__name__]=bridge
exec(compile(raw,str(HERE/'bridge.py'),'exec',dont_inherit=True),bridge.__dict__)
EVIDENCE=[]

class Child:
    def __init__(self):
        self.pid=999;self.stdin=io.BytesIO();self.stdout=io.BytesIO();self.returncode=None;self.waits=0;self.kills=0
    def wait(self,timeout=None):self.waits+=1;self.returncode=0;return 0
    def kill(self):self.kills+=1;self.returncode=-9
    def poll(self):return self.returncode

class ReceiptChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-receipt-');self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name);self.child=Child()
        self.cell=dict(he_argv=['synthetic-never-launched'],he_cwd=str(self.folder))
    def proof(self,case):
        exit_path=self.folder/'HE_CHILD_EXIT.json'
        evidence=dict(case=case,wait_calls=self.child.waits,kill_calls=self.child.kills,
            returncode=self.child.returncode,started_receipt=(self.folder/'HE_CHILD_STARTED.json').exists(),
            exit_receipt=json.loads(exit_path.read_bytes()) if exit_path.exists() else None)
        EVIDENCE.append(evidence)
        self.assertEqual(self.child.waits,1);self.assertEqual(self.child.kills,0);self.assertEqual(self.child.returncode,0)
        self.assertTrue(evidence['exit_receipt']['reaped'])
        return evidence
    def test_started_receipt_write_failure_closes_owned_child(self):
        original=Path.write_bytes
        def write(path,data):
            if path.name=='HE_CHILD_STARTED.json':raise OSError('synthetic STARTED write failure')
            return original(path,data)
        with patch.object(bridge.subprocess,'Popen',return_value=self.child),patch.object(Path,'write_bytes',write), \
                patch.object(bridge,'reader',return_value=queue.Queue()) as reader:
            with self.assertRaisesRegex(OSError,'STARTED write failure'):
                bridge.HE(self.cell,object(),self.folder)
        reader.assert_not_called();self.assertFalse(self.proof('started_write_failure')['started_receipt'])
    def test_reader_failure_control_closes_owned_child(self):
        with patch.object(bridge.subprocess,'Popen',return_value=self.child), \
                patch.object(bridge,'reader',side_effect=RuntimeError('synthetic reader failure')):
            with self.assertRaisesRegex(RuntimeError,'reader failure'):
                bridge.HE(self.cell,object(),self.folder)
        self.assertTrue(self.proof('reader_failure_control')['started_receipt'])
    def test_normal_initialization_and_close_keep_receipts(self):
        incoming=queue.Queue()
        with patch.object(bridge.subprocess,'Popen',return_value=self.child),patch.object(bridge,'reader',return_value=incoming):
            relay=bridge.HE(self.cell,object(),self.folder)
            self.assertIs(relay.incoming,incoming);receipt=relay.close()
        self.assertTrue(receipt['reaped']);self.assertTrue(self.proof('normal_init_close')['started_receipt'])

started=datetime.now(timezone.utc).isoformat()
with (OUT/'TESTS.raw.txt').open('w',encoding='utf8') as log:
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReceiptChecks))
unchanged=(HERE/'bridge.py').read_bytes()==raw
record=dict(started_utc=started,ended_utc=datetime.now(timezone.utc).isoformat(),methods=result.testsRun,
    failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped),passed=result.wasSuccessful() and unchanged,
    bridge_sha256=digest,candidate_unchanged=unchanged,execution='compile exact frozen bridge bytes; Popen and reader mocked',
    cases=EVIDENCE,actual_processes=0,consumers=0,Blender=0,MCP_services=0,RPC=0,API=0,product_imports=0)
(OUT/'RESULTS.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
with zipfile.ZipFile(OUT/'EXECUTED_BYTES.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('bridge.py',raw);archive.writestr('check_receipt.py',Path(__file__).read_bytes())
print(json.dumps(dict(methods=result.testsRun,passed=record['passed'],bridge_sha256=digest,actual_processes=0)))
raise SystemExit(0 if record['passed'] else 1)
