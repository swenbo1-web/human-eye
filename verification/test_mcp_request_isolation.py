"""Bounded persistent JSON-RPC input and isolated publication failures.

Actual production/legacy/demo subprocesses use no Blender connection or setter.
"""
import base64,contextlib,io,json,os,random,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from human_eye_plugin import mcp_transport as wire,live_spatial_mcp as live,mcp_server as legacy
from verification.test_live_spatial_mcp import FakeService
ROOT=Path(__file__).resolve().parents[1]
PING={'jsonrpc':'2.0','id':2,'method':'ping'}
STATUS={'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'human_eye_connection_status'}}

def line(value):return json.dumps(value,ensure_ascii=True,allow_nan=False).encode()+b'\n'
def deep(n):return b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":'+b'['*n+b'0'+b']'*n+b'}}\n'
def decoded(value):return [json.loads(raw) for raw in value.splitlines()]


class FramingAndEnvelopeTests(unittest.TestCase):
    def test_maximum_depth_and_quoted_brackets(self):
        # root/params plus 30 arrays is the exact 32-container input boundary.
        self.assertEqual(wire.parse_request(deep(30))['id'],1)
        for raw in (deep(31),deep(5000)):
            with self.subTest(depth=len(raw)),self.assertRaises(wire.RPCInputError):wire.parse_request(raw)
        self.assertEqual(wire.parse_request(line(dict(PING,params={'quoted':'[{'*5000+'\\"'})))['id'],2)

    def test_invalid_ids_and_surrogate_payloads_never_dispatch(self):
        service=FakeService();server=live.LiveSpatialMCPServer(service)
        for rid in (True,1.5,[],{},'\ud800','a'*129,2**53,-2**53):
            with self.subTest(rid=repr(rid)):
                value=server.handle_jsonrpc_message(dict(STATUS,id=rid))
                self.assertEqual(value['error']['code'],-32600);self.assertIsNone(value['id'])
        for req in (dict(STATUS,params={'name':'\udfff'}),dict(STATUS,params={'arguments':{'\ud800':1}})):
            self.assertEqual(server.handle_jsonrpc_message(req)['error']['code'],-32600)
        self.assertEqual(service.calls,[])

    def test_allowed_ids_round_trip_including_unicode(self):
        for rid in (None,'','id','左臂',-(2**53-1),2**53-1):
            with self.subTest(rid=rid):
                value=wire.parse_request(line(dict(PING,id=rid)))
                self.assertEqual(value['id'],rid)
                self.assertEqual(json.loads(wire.encode_response({'jsonrpc':'2.0','id':rid,'result':{}},value))['id'],rid)

    def test_invalid_envelopes_and_inprocess_cycles_are_bounded(self):
        server=live.LiveSpatialMCPServer(FakeService())
        bad=[[],None,{},dict(PING,jsonrpc='1.0'),dict(PING,method=''),dict(PING,method=1)]
        cycle=dict(PING);cycle['params']={'loop':cycle};bad.append(cycle)
        for value in bad:
            with self.subTest(type=type(value).__name__):self.assertEqual(server.handle_jsonrpc_message(value)['error']['code'],-32600)

    def test_duplicate_keys_nonfinite_overflow_and_invalid_utf8(self):
        bad=[b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\n',
            b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":NaN}}\n',
            b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":1e309}}\n',b'\xff\n']
        for raw in bad:
            with self.subTest(raw=raw[:50]),self.assertRaises(wire.RPCInputError):wire.parse_request(raw)

    def test_exact_raw_byte_boundary_and_multibyte_budget(self):
        raw=line(PING);value=b' '*(wire.MAX_INPUT_BYTES-len(raw))+raw
        self.assertEqual(len(value),wire.MAX_INPUT_BYTES);self.assertEqual(wire.parse_request(value),PING)
        with self.assertRaises(wire.RPCInputError):wire.parse_request(b' '+value)
        raw=json.dumps(dict(PING,params={'value':'界'*(wire.MAX_INPUT_BYTES//2)}),ensure_ascii=False)+'\n'
        self.assertLess(len(raw),wire.MAX_INPUT_BYTES)
        with self.assertRaises(wire.RPCInputError):wire.parse_request(raw)

    def test_oversize_frame_drains_only_to_newline_and_keeps_next_request(self):
        # A valid-looking tail inside the rejected frame is never dispatched.
        raw=b'X'*(wire.MAX_INPUT_BYTES+20)+line(dict(PING,id=777))+line(PING)
        values=list(wire.requests(io.BytesIO(raw)))
        self.assertEqual(len(values),2);self.assertEqual(values[0][1]['error']['code'],-32700)
        self.assertEqual(values[1],(PING,None))

    def test_binary_invalid_utf8_then_ping_keeps_framing(self):
        values=list(wire.requests(io.BytesIO(b'\xff\n'+line(PING))))
        self.assertEqual(values[0][1]['error']['code'],-32700);self.assertEqual(values[1],(PING,None))

    def test_notification_cannot_dispatch_any_legacy_or_live_tool(self):
        service=FakeService();server=live.LiveSpatialMCPServer(service);plugin=type('Plugin',(),{'dispatch_tool_call':lambda *_:self.fail('notification dispatched')})()
        value=dict(STATUS);value.pop('id')
        self.assertIsNone(server.handle_jsonrpc_message(value));self.assertIsNone(legacy.handle_jsonrpc_message(value,plugin=plugin));self.assertEqual(service.calls,[])

    def test_legacy_schema_failures_do_not_dispatch(self):
        plugin=type('Plugin',(),{'dispatch_tool_call':lambda *_:self.fail('bad schema dispatched')})()
        for params in ([],None,{'name':4},{'name':'tool','arguments':[]},{'name':'tool','arguments':False}):
            with self.subTest(params=params):self.assertEqual(legacy.handle_jsonrpc_message(dict(STATUS,params=params),plugin=plugin)['error']['code'],-32602)


class PublicationIsolationTests(unittest.TestCase):
    def test_encoder_failures_preserve_unknown_outcome_without_retry_claim(self):
        cycle={};cycle['self']=cycle
        for result in (cycle,{'x':float('nan')},{'x':set()},{'x':'\ud800'}):
            with self.subTest(result_type=type(result).__name__):
                value=json.loads(wire.encode_response({'jsonrpc':'2.0','id':9,'result':result},dict(STATUS,id=9)))
                self.assertEqual(value['error']['code'],-32603);self.assertEqual(value['id'],9)
                self.assertEqual(value['error']['data']['tool_outcome'],'unknown')
                self.assertFalse(value['error']['data']['automatic_retry']);self.assertNotIn('executed',value['error']['data'])

    def test_bad_encoder_response_then_ping_isolated_in_same_loop(self):
        output=io.StringIO();calls=[]
        def handler(req):
            calls.append(req['id'])
            return {'jsonrpc':'2.0','id':req['id'],'result':set()} if req['id']==3 else {'jsonrpc':'2.0','id':req['id'],'result':{}}
        wire.serve(io.BytesIO(line(STATUS)+line(PING)),output,handler)
        values=decoded(output.getvalue());self.assertEqual([v['id'] for v in values],[3,2]);self.assertEqual(values[0]['error']['data']['tool_outcome'],'unknown');self.assertEqual(calls,[3,2])

    def test_dispatch_exception_is_not_retried_and_following_readonly_works(self):
        service=FakeService()
        def fail(*args,**kwargs):service.calls.append(('possibly_applied',));raise RuntimeError('after possible effect')
        service.transform=fail
        request={'jsonrpc':'2.0','id':7,'method':'tools/call','params':{'name':'human_eye_transform','arguments':{'action':{'focal_id':'a','reference_id':'b','translation':[0,0,1]}}}}
        output=io.StringIO();live.run_stdio_mcp_server(service,io.BytesIO(line(request)+line(PING)+line(STATUS)),output)
        values=decoded(output.getvalue());metadata=json.loads(values[0]['result']['content'][0]['text'])
        self.assertEqual(metadata['tool_outcome'],'unknown');self.assertFalse(metadata['automatic_retry'])
        self.assertEqual(service.calls,[('possibly_applied',),('status',)]);self.assertEqual(values[1]['id'],2);self.assertEqual(values[2]['id'],3)

    def test_native_response_larger_than_input_cap_is_not_truncated(self):
        service=FakeService();data=random.Random(0).randbytes(384*384*3);image=Image.frombytes('RGB',(384,384),data);buffer=io.BytesIO();image.save(buffer,format='PNG')
        content={'type':'image','mimeType':'image/png','data':base64.b64encode(buffer.getvalue()).decode('ascii')}
        service.observation['routing']['image']=content
        request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'human_eye_scene_observe'}}
        output=io.StringIO();live.run_stdio_mcp_server(service,io.BytesIO(line(request)+line(PING)),output)
        self.assertGreater(len(output.getvalue()),wire.MAX_INPUT_BYTES)
        values=decoded(output.getvalue());self.assertEqual(values[0]['result']['content'][1],content);self.assertEqual(values[1]['id'],2)

    def test_completed_response_does_not_duplicate_on_trace_exit_failure(self):
        service=FakeService()
        @contextlib.contextmanager
        def scope(*args,**kwargs):yield None;raise RuntimeError('trace exit')
        output=io.StringIO()
        with patch.object(live.LiveSpatialMCPServer,'request_trace',scope):
            live.run_stdio_mcp_server(service,io.BytesIO(line(STATUS)+line(PING)),output)
        values=decoded(output.getvalue());self.assertEqual([v['id'] for v in values],[3,2]);self.assertEqual(service.calls,[('status',)])

    def test_broken_output_stops_dispatch_and_closes_host(self):
        service=FakeService();closed=[];service.host=type('Host',(),{'close':lambda *_:closed.append(True)})()
        class Sink:
            def write(self,raw):raise BrokenPipeError('closed')
            def flush(self):self.fail('write already failed')
        live.run_stdio_mcp_server(service,io.BytesIO(line(STATUS)+line(STATUS)),Sink())
        self.assertEqual(service.calls,[('status',)]);self.assertEqual(closed,[True])

    def test_partial_output_stops_without_retry_or_second_dispatch(self):
        service=FakeService();closed=[];service.host=type('Host',(),{'close':lambda *_:closed.append(True)})()
        class Sink:
            writes=0
            def write(self,raw):self.writes+=1;return len(raw)-1
            def flush(self):raise AssertionError('partial write cannot commit delivery')
        sink=Sink();live.run_stdio_mcp_server(service,io.BytesIO(line(STATUS)+line(STATUS)),sink)
        self.assertEqual(sink.writes,1);self.assertEqual(service.calls,[('status',)]);self.assertEqual(closed,[True])

    def test_eof_closes_host_without_dispatch(self):
        service=FakeService();closed=[];service.host=type('Host',(),{'close':lambda *_:closed.append(True)})()
        live.run_stdio_mcp_server(service,io.BytesIO(),io.StringIO())
        self.assertEqual(service.calls,[]);self.assertEqual(closed,[True])


class ActualPersistentProcessesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name).resolve()
        self.config=self.folder/'config.json';self.config.write_text(json.dumps(dict(schema_version='1.0',project_root=str(ROOT),state_file='state.json',audit_file='events.jsonl',blender=dict(host='127.0.0.1',port=1,timeout_s=.1))),encoding='utf8')

    def run_live(self,raw):
        return subprocess.run([sys.executable,'-B','-m','human_eye_plugin.production_server','--config',str(self.config)],cwd=ROOT,
            input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25,env=dict(os.environ,PYTHONIOENCODING='utf-8'))

    def assert_recovered(self,raw,expected):
        run=self.run_live(raw+line(PING)+line(STATUS));self.assertEqual(run.returncode,0,run.stderr.decode('utf8','replace'))
        values=decoded(run.stdout);self.assertEqual(len(values),3);self.assertEqual(values[0]['error']['code'],expected)
        self.assertEqual(values[1],{'jsonrpc':'2.0','id':2,'result':{}});self.assertEqual(values[2]['id'],3)
        self.assertIn('result',values[2]);self.assertFalse(values[2]['result']['isError']);self.assertNotIn(b'Traceback',run.stderr)
        self.assertFalse((self.folder/'state.json').exists())
        return values

    def test_real_production_recovers_after_deep_5000_input(self):self.assert_recovered(deep(5000),-32700)
    def test_real_production_recovers_after_surrogate_id(self):self.assert_recovered(b'{"jsonrpc":"2.0","id":"\\ud800","method":"ping"}\n',-32600)
    def test_real_production_recovers_after_invalid_utf8(self):self.assert_recovered(b'\xff\n',-32700)
    def test_real_production_recovers_after_oversized_frame(self):self.assert_recovered(b'X'*(wire.MAX_INPUT_BYTES+100)+b'\n',-32700)
    def test_real_production_recovers_after_invalid_schema(self):self.assert_recovered(b'{"jsonrpc":"2.0","id":true,"method":"ping"}\n',-32600)

    def test_real_production_accepts_maximum_valid_frame(self):
        first=line(dict(PING,id=1));first=b' '*(wire.MAX_INPUT_BYTES-len(first))+first
        run=self.run_live(first+line(PING)+line(STATUS));self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual([v['id'] for v in decoded(run.stdout)],[1,2,3])

    def test_actual_legacy_and_demo_preserve_connection_after_bad_requests(self):
        for args in (['-m','human_eye_plugin.mcp_server'],['-m','human_eye_plugin.production_server','--demo']):
            with self.subTest(entry=args):
                run=subprocess.run([sys.executable,'-B',*args],cwd=ROOT,input=deep(5000)+b'{"jsonrpc":"2.0","id":"\\ud800","method":"ping"}\n'+line(PING)+line({'jsonrpc':'2.0','id':3,'method':'tools/list'}),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
                self.assertEqual(run.returncode,0,run.stderr);values=decoded(run.stdout)
                self.assertEqual([v.get('id') for v in values],[None,None,2,3]);self.assertEqual(values[2]['result'],{});self.assertEqual(len(values[3]['result']['tools']),6)

    def test_actual_stdout_pipe_disconnect_exits_and_runs_cleanup(self):
        marker=self.folder/'closed.txt'
        code="""import sys
from pathlib import Path
from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server,_configure_utf8_stdio
from verification.test_live_spatial_mcp import FakeService
_configure_utf8_stdio()
service=FakeService()
service.host=type('Host',(),{'close':lambda self:Path(sys.argv[1]).write_text('closed')})()
run_stdio_mcp_server(service)
"""
        process=subprocess.Popen([sys.executable,'-B','-c',code,str(marker)],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            process.stdout.close();process.stdin.write(line(STATUS));process.stdin.flush();process.stdin.close();process.wait(timeout=20)
            self.assertEqual(marker.read_text(),'closed');self.assertIsNotNone(process.returncode)
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=5)
            if process.stdin and not process.stdin.closed:process.stdin.close()
            if process.stderr:process.stderr.close()


if __name__=='__main__':unittest.main()
