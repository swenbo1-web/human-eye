"""Verification observers around existing production/owned MCP launchers."""
import argparse
from collections import Counter
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

HERE=Path(__file__).resolve().parent
ROOT=Path(os.environ['EXPERT_RUNTIME_ROOT']).resolve()
sys.path.insert(0,str(ROOT))
from human_eye_plugin import live_spatial_mcp as mcp
from human_eye_plugin.blender_mcp_host import BlenderMCPHost
from human_eye_plugin.runtime_identity import runtime_identity

def difference(after,before):return {key:after[key]-before.get(key,0) for key in after if after[key]!=before.get(key,0)}

class Wire:
    def __init__(self,folder):self.folder,self.lock,self.counts=folder,threading.Lock(),Counter()
    def record(self,name,data):
        with self.lock:
            with (self.folder/name).open('ab') as stream:stream.write(data)
            self.counts[name]+=len(data)

class SocketObserver:
    def __init__(self,sock,wire):self.sock,self.wire=sock,wire
    def sendall(self,data,*a,**kw):
        result=self.sock.sendall(data,*a,**kw);self.wire.record('mcp_tx.bin',data);return result
    def recv(self,*a,**kw):
        data=self.sock.recv(*a,**kw);self.wire.record('mcp_rx.bin',data);return data
    def __getattr__(self,name):return getattr(self.sock,name)
    def __enter__(self):return self
    def __exit__(self,*a):self.sock.close()

class BinaryTee(io.BufferedIOBase):
    def __init__(self,stream,wire,name):super().__init__();self.stream,self.wire,self.name=stream,wire,name
    def readable(self):return self.stream.readable()
    def writable(self):return self.stream.writable()
    def seekable(self):return False
    def fileno(self):return self.stream.fileno()
    def read(self,size=-1):
        data=self.stream.read(size);self.wire.record(self.name,data);return data
    def read1(self,size=-1):
        data=self.stream.read1(size);self.wire.record(self.name,data);return data
    def readinto(self,buffer):
        count=self.stream.readinto(buffer)
        if count:self.wire.record(self.name,bytes(memoryview(buffer)[:count]))
        return count
    def write(self,data):
        count=self.stream.write(data)
        if count:self.wire.record(self.name,bytes(memoryview(data)[:count]))
        return count
    def flush(self):
        if not self.stream.closed:return self.stream.flush()
    def close(self):
        if not self.closed:super().close();self.stream.close()

def observe_text(stream,wire,name):
    encoding,errors=stream.encoding,stream.errors;line_buffering,write_through=stream.line_buffering,stream.write_through
    return io.TextIOWrapper(BinaryTee(stream.detach(),wire,name),encoding=encoding,errors=errors,newline=None,
        line_buffering=line_buffering,write_through=write_through)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('shared','owned','owned_task'),required=True)
    parser.add_argument('--config',required=True);parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--spec',type=Path,required=True);parser.add_argument('--blender');parser.add_argument('--scene')
    args=parser.parse_args();mcp._configure_utf8_stdio();folder=args.directory.resolve();folder.mkdir(parents=True,exist_ok=True)
    wire=Wire(folder)
    def emit(value):
        with (folder/'metrics.jsonl').open('a',encoding='utf8') as stream:stream.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')
    emit(dict(event='startup',identity=runtime_identity(mode='live'),mode=args.mode,
        scope='instrumented existing launcher; no profiler; wire copy and lightweight wrapper overhead included; oracle only in separate post-response control'))
    original_connect=BlenderMCPHost._connect
    BlenderMCPHost._connect=lambda self,deadline:SocketObserver(original_connect(self,deadline),wire)
    original_popen=subprocess.Popen
    def popen(command,*a,**kw):
        command=list(command)
        if args.mode!='shared' and Path(command[0]).resolve()==Path(args.blender).resolve():
            index=command.index('--python-expr');expression=command[index+1]
            command[index:index]=['--python',str(HERE/'qa_observer.py')]
            assert command[command.index('--python-expr')+1]==expression
            env=dict(os.environ if kw.get('env') is None else kw['env'])
            env.update(EXPERT_QA_DIRECTORY=str(folder),EXPERT_QA_SPEC=str(args.spec.resolve()));kw['env']=env
            emit(dict(event='default_worker_launch',command=command,worker_path_override=False,expression_unchanged=True))
            process=original_popen(command,*a,**kw)
            process.stdin=observe_text(process.stdin,wire,'owned_tx.bin');process.stdout=observe_text(process.stdout,wire,'owned_rx.bin')
            return process
        return original_popen(command,*a,**kw)
    subprocess.Popen=popen
    original_call=mcp.LiveSpatialMCPServer._call_tool
    def measured(self,name,arguments,**kw):
        assert sys.getprofile() is None
        transport=wire.counts.copy();started=time.perf_counter_ns()
        try:return original_call(self,name,arguments,**kw)
        finally:emit(dict(event='tool',request_id=kw.get('mcp_request_id'),name=name,arguments=arguments,
            dispatch_content_ms=(time.perf_counter_ns()-started)/1e6,profile_none=sys.getprofile() is None,
            transport_bytes=difference(wire.counts,transport)))
    mcp.LiveSpatialMCPServer._call_tool=measured
    original_handle=mcp.LiveSpatialMCPServer.handle_jsonrpc_message
    def handle(self,request):
        if request.get('method')!='qa/control':return original_handle(self,request)
        assert args.mode!='shared'
        value=dict(id=request['id'],params=request['params']);path=folder/'control.json'
        assert not path.exists();path.write_text(json.dumps(value),encoding='utf8')
        started=time.perf_counter_ns();capabilities=self.service.host._request('capabilities',{})
        assert not path.exists(),'Observer failed to drain main-thread control'
        events=[json.loads(line) for line in (folder/'blender_events.jsonl').read_text(encoding='utf8').splitlines()]
        applied=next(row for row in reversed(events) if row.get('event')=='control' and row.get('id')==request['id'])
        emit(dict(event='control',id=request['id'],params=request['params'],duration_ms=(time.perf_counter_ns()-started)/1e6,
            scope='verification-only control + existing capabilities RPC outside tool metrics'))
        return dict(jsonrpc='2.0',id=request['id'],result=applied['result'])
    mcp.LiveSpatialMCPServer.handle_jsonrpc_message=handle
    assert sys.getprofile() is None
    try:
        if args.mode=='shared':
            from human_eye_plugin.production_server import main as launch
            return launch(['--config',args.config])
        if args.mode=='owned_task':
            from human_eye_plugin.owned_task_mcp import main as launch
            return launch(['--config',args.config,'--blender',args.blender,'--scene',args.scene])
        from human_eye_plugin.blender_process import BlenderProcessHost
        from human_eye_plugin.live_service import LiveSpatialService
        with BlenderProcessHost(args.blender,args.scene,timeout=30.) as host:
            service=LiveSpatialService(args.config,host=host,production_mode=True)
            mcp.run_stdio_mcp_server(service)
        return 0
    finally:
        emit(dict(event='exit',transport_bytes=dict(wire.counts),profile_none=sys.getprofile() is None))

if __name__=='__main__':raise SystemExit(main())
