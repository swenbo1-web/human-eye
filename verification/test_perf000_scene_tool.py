"""Thin tool projection fixtures: no Blender, model call or task solver."""
import contextlib,io,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from verification import perf000_scene_tool as t


class SceneToolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def call(self,operation,result,**kwargs):
        reply=dict(ok=True,operation_succeeded=not bool(result.get('script_error')),result=result,
            original_deadline_ns=time.perf_counter_ns()+10**9)
        out=io.StringIO();err=io.StringIO()
        with patch.object(t,'client',return_value=reply) as client,contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=operation(self.root,**kwargs)
        folder=next((self.root/'perf000_calls').iterdir())
        self.assertEqual(json.loads((folder/'REPLY.json').read_bytes()),reply)
        self.assertFalse(json.loads((folder/'AUDIT.json').read_bytes())['actual_image_delivery'])
        return code,out.getvalue(),err.getvalue(),client.call_args.args[1]
    def test_native_code_and_full_stdout_are_unchanged_without_request_file_input(self):
        code,out,err,request=self.call(t.native,dict(stdout='原文\n\n',stderr='',script_error=None),code='value=17;print(value)')
        self.assertEqual((code,out,err),(0,'原文\n\n',''));self.assertEqual(request['args'],dict(code='value=17;print(value)'))
        self.assertTrue(request['request_id'].startswith('perf000-'));self.assertEqual(request['operation'],'native_run')
    def test_native_failure_preserves_stdout_stderr_and_actual_error(self):
        error=dict(type='ValueError',message='authored error',traceback='full authored traceback')
        code,out,err,_=self.call(t.native,dict(stdout='before\n',stderr='warning\n',script_error=error),code='raise ValueError()')
        self.assertEqual(code,1);self.assertEqual(out,'before\n');self.assertTrue(err.startswith('warning\n'))
        self.assertEqual(json.loads(err[len('warning\n'):]),error)
    def test_product_full_metadata_text_is_printed_once_and_images_disabled(self):
        text='{"object_ids":["opaque"],"metadata":{"full":"原始文本"}}'
        code,out,err,request=self.call(t.observe,dict(mcp_text=[text],mcp_is_error=False,rpc_error=None),
            focal_id='opaque',reference_id='reference',query=dict(mode='exact_pairs'))
        self.assertEqual((code,out,err),(0,text+'\n',''))
        self.assertEqual(request['args']['arguments'],dict(include_image=False,focal_id='opaque',reference_id='reference',query=dict(mode='exact_pairs')))
    def test_image_request_is_unavailable_and_never_sends_broker_call(self):
        out=io.StringIO();err=io.StringIO()
        with patch.object(t,'client') as client,contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=t.observe(self.root,include_image=True)
        self.assertEqual(code,1);self.assertEqual(out.getvalue(),'');self.assertIn('UNAVAILABLE',err.getvalue());client.assert_not_called()
    def test_expired_reply_is_private_and_not_printed_as_success(self):
        reply=dict(ok=True,operation_succeeded=True,original_deadline_ns=time.perf_counter_ns()-1,
            result=dict(stdout='late success',stderr='',script_error=None))
        out=io.StringIO();err=io.StringIO()
        with patch.object(t,'client',return_value=reply),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            self.assertEqual(t.native(self.root,'print(1)'),1)
        self.assertEqual(out.getvalue(),'');self.assertIn('original_deadline',err.getvalue())
        audit=json.loads(next((self.root/'perf000_calls').glob('*/AUDIT.json')).read_bytes())
        self.assertTrue(audit['delivery_rejected']);self.assertIn('original_deadline',audit['error']['message'])
    def test_CLI_accepts_ordinary_script_without_model_request_management(self):
        script=self.root/'ordinary.py';script.write_text("print('普通代码')",encoding='utf8')
        reply=dict(ok=True,operation_succeeded=True,original_deadline_ns=time.perf_counter_ns()+10**9,
            result=dict(stdout='普通代码\n',stderr='',script_error=None))
        out=io.StringIO()
        with patch.object(t,'client',return_value=reply) as client,contextlib.redirect_stdout(out):
            self.assertEqual(t.main(['native','--workspace',str(self.root),'--script',str(script)]),0)
        self.assertEqual(out.getvalue(),'普通代码\n');self.assertEqual(client.call_args.args[1]['args']['code'],"print('普通代码')")


if __name__=='__main__':unittest.main()
