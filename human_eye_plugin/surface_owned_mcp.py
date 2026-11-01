"""Opt-in Codex MCP entry for a single fixed reference restore worker.

The stdio client is trusted to present an honest form. Scripted protocol tests
cannot prove a human saw or accepted it. Model arguments are proposals only.
"""
import argparse,copy,json,queue,sys,threading,time,uuid
from . import surface_owned as s
from .owned_task_mcp import valid_id
from .task_episode import approval_decision
from .live_spatial_mcp import _rpc_error,_tool_result,_configure_utf8_stdio

PROTOCOL='2025-06-18'
GOAL='human_eye_owned_reference_restore'
INSPECT='human_eye_owned_reference_inspect'
TOOLS=[dict(name=INSPECT,description='Read this fixed owned single-triangle-mesh scene and intended reference deviations. No movement.',
    annotations=dict(readOnlyHint=True,destructiveHint=False,openWorldHint=False),inputSchema=dict(type='object',properties={},additionalProperties=False)),
    dict(name=GOAL,description='Propose up to eight original vertices to restore to the operator-registered same-index intended reference. '
        'A concrete client approval form and original 30 second window are required. No save or topology editing. Unknown is never retried.',
        annotations=dict(readOnlyHint=False,destructiveHint=True,idempotentHint=False,openWorldHint=False),
        inputSchema=dict(type='object',properties=dict(indices=dict(type='array',items=dict(type='integer',minimum=0,maximum=127),
            minItems=1,maxItems=8,uniqueItems=True)),required=['indices'],additionalProperties=False))]


class SurfaceOwnedMCP:
    def __init__(self,actor,incoming,outgoing):
        self.actor=actor;self.incoming=incoming;self.outgoing=outgoing;self.closed=threading.Event();self.cancelled=threading.Event()
        self.messages=queue.Queue(maxsize=16);self.lock=threading.Lock();self.active_id=None;self.initialized=False
        self.elicitation=False;self.seen={};self.connection_id=uuid.uuid4().hex
        self.cancelled_ids=set();self.state_lock=threading.Lock()

    def emit(self,value):
        text=s.encoded(value).decode()+'\n'
        with self.lock:self.outgoing.write(text);self.outgoing.flush()

    def _read(self):
        try:
            while True:
                line=self.incoming.readline(s.MAX_MESSAGE+1)
                if not line:break
                received=time.perf_counter_ns();value=s.decode(line.encode('utf8'))
                s.require(type(value) is dict and value.get('jsonrpc')=='2.0','rpc_object')
                if value.get('method')=='notifications/cancelled':
                    params=value.get('params')
                    if type(params) is dict and valid_id(params.get('requestId')):
                        with self.state_lock:
                            self.cancelled_ids.add(s.digest(dict(id=params['requestId'])))
                            s.require(len(self.cancelled_ids)<=16,'cancel_history_budget')
                            if type(params['requestId']) is type(self.active_id) and params['requestId']==self.active_id:self.cancelled.set()
                    continue
                self.messages.put_nowait((value,received))
        except Exception:pass
        finally:self.closed.set();self.cancelled.set()

    def next_message(self,deadline=None,*,stop_on_cancel=False):
        while True:
            s.require(not self.closed.is_set(),'mcp_closed')
            s.require(not stop_on_cancel or not self.cancelled.is_set(),'mcp_cancelled')
            remaining=.05 if deadline is None else min(.05,(deadline-time.perf_counter_ns())/1e9)
            s.require(remaining>0,'mcp_original_deadline')
            try:return self.messages.get(timeout=remaining)
            except queue.Empty:continue

    def approve(self,scope):
        if not self.elicitation or self.closed.is_set() or self.cancelled.is_set():return False
        key='surface-approve-'+uuid.uuid4().hex
        message='Approve this exact intended-reference restore in the configured owned Blender process?\n'+json.dumps(dict(scope=scope,
            scope_sha256=s.digest(scope),scene_scope='only mesh object in this dedicated scene',
            input_file_will_not_be_saved=True),ensure_ascii=False,allow_nan=False)
        self.emit(dict(jsonrpc='2.0',id=key,method='elicitation/create',params=dict(message=message,
            requestedSchema=dict(type='object',properties=dict(approve=dict(type='boolean',default=False,title='Approve exact vertices and original budget')),
                required=['approve'],additionalProperties=False))))
        while not self.cancelled.is_set():
            value,_=self.next_message(scope['deadline_ns'],stop_on_cancel=True)
            if 'method' in value:
                if valid_id(value.get('id')):self.emit(_rpc_error(value['id'],-32000,'reference approval is single-flight'))
                continue
            return approval_decision(value,key)=='accept_true'
        return False

    def handle(self,value,received_ns):
        if 'id' not in value:return None
        key=value['id'];method=value.get('method');params=value.get('params',{})
        if not valid_id(key) or type(params) is not dict:return _rpc_error(None,-32600,'Invalid Request')
        if method=='initialize':
            if self.initialized:return _rpc_error(key,-32600,'initialize once')
            self.initialized=True;caps=params.get('capabilities');offered=caps.get('elicitation') if type(caps) is dict else None
            self.elicitation=params.get('protocolVersion') in (PROTOCOL,'2025-11-25','2026-07-28') and type(offered) is dict and (not offered or type(offered.get('form')) is dict)
            return dict(jsonrpc='2.0',id=key,result=dict(protocolVersion=PROTOCOL,capabilities=dict(tools={}),
                serverInfo=dict(name='human-eye-owned-reference-candidate',version='1'),
                _meta=dict(form_elicitation=self.elicitation,actual_Codex_UI_proven=False,limits=s.LIMITS)))
        if not self.initialized:return _rpc_error(key,-32000,'initialize required')
        if method=='ping':return dict(jsonrpc='2.0',id=key,result={})
        if method=='tools/list':return dict(jsonrpc='2.0',id=key,result=dict(tools=copy.deepcopy(TOOLS)))
        if method!='tools/call':return _rpc_error(key,-32601,'Method not found')
        identity=s.digest(dict(id=key));request=s.digest(params)
        if identity in self.seen:
            previous=self.seen[identity]
            if previous['request']!=request:return _rpc_error(key,-32602,'same id with changed arguments')
            return dict(jsonrpc='2.0',id=key,result=_tool_result(dict(status='receipt',event_id=previous['event_id'],
                previous_status=previous['status'],execution_authority=False,retried=False,
                physical_count=None if previous['status']=='unknown' else previous.get('physical_count')),is_error=False))
        if len(self.seen)>=16:return _rpc_error(key,-32000,'connection lifetime tool budget exhausted')
        event_id='surface:'+self.connection_id+':'+identity[:32]
        record=dict(request=request,event_id=event_id,status='received');self.seen[identity]=record
        with self.state_lock:
            self.active_id=key;self.cancelled.set() if identity in self.cancelled_ids else self.cancelled.clear()
        name=params.get('name');arguments=params.get('arguments',{})
        try:
            s.require(not self.closed.is_set() and not self.cancelled.is_set(),'cancelled_before_dispatch')
            s.require(set(params)<= {'name','arguments','_meta'} and type(arguments) is dict,'tool_fields')
            if name==INSPECT:
                s.require(not arguments,'inspect_fields');result=self.actor.inspect()
            elif name==GOAL:
                s.require(self.elicitation,'client_form_not_negotiated');s.require(set(arguments)=={'indices'},'proposal_only')
                selected=s.indices(arguments['indices']);result=self.actor.goal(selected,event_id=event_id,received_ns=received_ns,
                    approve=self.approve,cancelled=lambda:self.closed.is_set() or self.cancelled.is_set())
            else:raise ValueError('owned_surface_unknown_tool')
            record.update(status='finished',physical_count=result.get('physical_RNA_attempts',0))
            result.update(event_id=event_id,delivery='MCP_result_constructed_not_client_consumption',execution_authority=False)
            return dict(jsonrpc='2.0',id=key,result=_tool_result(result,is_error=False))
        except Exception as exc:
            unknown=getattr(self.actor,'poisoned',False)
            record['status']='unknown' if unknown else 'refused_before_dispatch'
            return dict(jsonrpc='2.0',id=key,result=_tool_result(dict(status=record['status'],event_id=event_id,
                reason=str(exc)[:500],physical_count=None if unknown else 0,retried=False,execution_authority=False),is_error=True))
        finally:
            with self.state_lock:self.active_id=None

    def run(self):
        threading.Thread(target=self._read,daemon=True).start()
        try:
            while not self.closed.is_set():
                try:value,received=self.next_message()
                except ValueError:
                    if self.closed.is_set():break
                    raise
                response=self.handle(value,received)
                if response is not None:self.emit(response)
        finally:self.actor.close()


def main():
    from .surface_owned_process import OwnedSurfaceProcess
    p=argparse.ArgumentParser();p.add_argument('--operator-config',required=True);args=p.parse_args()
    _configure_utf8_stdio();actor=OwnedSurfaceProcess(args.operator_config)
    SurfaceOwnedMCP(actor,sys.stdin,sys.stdout).run()


if __name__=='__main__':main()
