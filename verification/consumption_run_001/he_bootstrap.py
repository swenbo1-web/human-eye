"""Exact-byte production launcher with only transparent owned-socket metering.

No profile callbacks, fixture mutations, oracle, task solver or function counters.
Not started in the preparation phase.
"""
import hashlib
import json
from pathlib import Path
import socket
import sys
import time
import types
from types import MappingProxyType

sys.path.insert(0,str(Path(__file__).resolve().parent))
from bridge import Budget


def main(cell_path):
    cell=json.loads(Path(cell_path).read_bytes())
    root=Path(cell['source_root']); out=Path(cell['audit_root'])/'he_socket'
    out.mkdir(exist_ok=False)
    budget=Budget(cell)
    blobs=MappingProxyType({r['path']:(root/r['path']).read_bytes() for r in cell['product_manifest']})
    assert all(hashlib.sha256(blobs[r['path']]).hexdigest()==r['sha256'] for r in cell['product_manifest'])
    path=root/'human_eye_plugin/verified_source_loader.py'
    helper=types.ModuleType('_consumption_verified_source_bootstrap');helper.__file__=str(path)
    sys.modules[helper.__name__]=helper
    exec(compile(blobs['human_eye_plugin/verified_source_loader.py'],str(path),'exec',dont_inherit=True),helper.__dict__)
    guard=helper.install(root,cell['product_manifest'],sources=blobs,bootstrap_module=helper)
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(root/'human_eye_plugin')]
    guard.allow_namespace(package);sys.modules[package.__name__]=package
    from human_eye_plugin import production_server,runtime_identity
    assert runtime_identity.runtime_identity()['source_sha256']==cell['source_sha256']
    assert runtime_identity.check_task_source()['compatible'] and guard.verify_loaded()
    original=socket.socket
    meters=[]
    class Meter(original):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);self.row=None;self.folder=None;self.token=None;self.wire=bytearray()
        def connect_ex(self,address):
            if tuple(address[:2])==(cell['endpoint']['host'],cell['endpoint']['port']):
                self.token=budget.reserve_rpc()
                self.folder=out/str(len(meters)+1).zfill(2);self.folder.mkdir()
                self.row=dict(started_ns=time.perf_counter_ns(),tx_attempted=0,tx_completed=0,rx=0)
                meters.append(self.row)
            return super().connect_ex(address)
        def sendall(self,raw,*args,**kwargs):
            if self.row is not None:
                with (self.folder/'TX.bin').open('ab') as stream:stream.write(raw)
                self.row['tx_attempted']+=len(raw)
            try: result=super().sendall(raw,*args,**kwargs)
            except BaseException:
                if self.row is not None:budget.poison('HE physical send outcome unknown')
                raise
            if self.row is not None:self.row['tx_completed']+=len(raw)
            return result
        def recv(self,*args,**kwargs):
            raw=super().recv(*args,**kwargs)
            if self.row is not None:
                with (self.folder/'RX.bin').open('ab') as stream:stream.write(raw)
                self.row['rx']+=len(raw)
                self.wire.extend(raw)
            return raw
        def close(self):
            try:return super().close()
            finally:
                if self.row is not None:
                    if self.token is not None:
                        try:
                            response=json.loads(self.wire)
                            known=type(response) is dict and response.get('status') in ('success','error')
                            if type(response) is dict and response.get('poisoned') is True:
                                budget.poison('Native worker reported poison')
                        except (ValueError,UnicodeError):known=False
                        budget.complete_rpc(self.token,unknown=not known)
                        self.token=None
                    self.row['closed_ns']=time.perf_counter_ns()
                    (self.folder/'METER.json').write_text(json.dumps(self.row,indent=2)+'\n',encoding='utf8')
    socket.socket=Meter
    started=time.perf_counter_ns();code=None
    try:code=production_server.main(['--config',cell['he_config']])
    finally:
        socket.socket=original
        record=dict(exit_code=code,started_ns=started,ended_ns=time.perf_counter_ns(),sockets=meters,
            source_sha256=cell['source_sha256'],guard_verified=guard.verify_loaded(),
            loaded_generation=runtime_identity.check_task_source(),
            instrumentation='exact source loader and actual owned socket bytes only; no profile/fixture/counters')
        (out/'EXIT.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
    return code


if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
