"""Explicit owned MCP goal entry with client elicitation, never prompt approval.

The stdio owner is trusted to present the form honestly. This module is not a
sandbox against that owner or arbitrary same-account Python. It is opt-in and
does not change the default shared Blender transport or its four tools.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import queue
import sys
import threading
import time
import uuid

from .goal_budget import GoalBudgetLimits
from .task_authority import ClearanceTaskSpec,TaskApproval,TrustedTaskAuthority
from .task_entry import TrustedTaskEntry
from .task_episode import TaskEpisode,approval_decision,task_event_id
from .live_spatial_mcp import (LiveSpatialMCPServer,LIVE_MCP_TOOLS_SCHEMA,
                               _rpc_error,_tool_result,_configure_utf8_stdio)

PROTOCOL='2025-06-18'
MAX_INPUT=256*1024
MAX_CALLS=16
READ_TOOLS={'human_eye_connection_status','human_eye_scene_observe'}
GOAL_TOOL={
    'name':'human_eye_owned_clearance_goal',
    'description':('Propose one finite original-support clearance goal for this configured owned Blender copy. '
        'Requires an explicit client elicitation form response bound to the frozen scene and original budget. '
        'Model arguments never approve execution. Returns one final review receipt; unknown is never retried.'),
    'annotations':{'readOnlyHint':False,'destructiveHint':True,'idempotentHint':False,'openWorldHint':False},
    'inputSchema':{'type':'object','properties':{
        'focal_id':{'type':'string','minLength':1,'maxLength':128},
        'reference_id':{'type':'string','minLength':1,'maxLength':128},
        'target_clearance_m':{'type':'number','exclusiveMinimum':0,'maximum':1},
        'clearance_tolerance_m':{'type':'number','minimum':0,'maximum':1e-5},
        'reference_triangle_index':{'type':'integer','minimum':0,'maximum':999999},
        'direction_world':{'type':'array','items':{'type':'number'},'minItems':3,'maxItems':3},
        'limits':{'type':'object','properties':{
            'max_steps':{'type':'integer','minimum':1,'maximum':8},
            'max_segments':{'type':'integer','minimum':1,'maximum':3},
            'max_recoveries':{'type':'integer','minimum':0,'maximum':2},
            'max_step_translation_m':{'type':'number','exclusiveMinimum':0,'maximum':.001},
            'max_total_translation_m':{'type':'number','exclusiveMinimum':0,'maximum':.008},
            'max_duration_s':{'type':'number','exclusiveMinimum':0,'maximum':30}},'additionalProperties':False}},
        'required':['focal_id','reference_id'],'additionalProperties':False}}


def proposal(arguments):
    allowed=set(GOAL_TOOL['inputSchema']['properties'])
    if type(arguments) is not dict or set(arguments)-allowed:raise ValueError('proposal_fields_only_no_authorization')
    values=copy.deepcopy(arguments)
    if 'limits' in values:
        if type(values['limits']) is not dict:raise ValueError('limits_object_required')
        values['limits']=GoalBudgetLimits(**values['limits'])
        if values['limits'].max_duration_s>30.:raise ValueError('owned_goal_form_window_max_30s')
    if 'direction_world' in values:
        if type(values['direction_world']) is not list:raise ValueError('direction_array_required')
        values['direction_world']=tuple(values['direction_world'])
    return ClearanceTaskSpec(**values)


def valid_id(value):
    return type(value) is str and 0<len(value)<=128 or type(value) is int and 0<=value<2**53


class OwnedTaskMCP:
    """Single-flight goal entry. Only the transport can deliver an approval."""
    def __init__(self,config_path,host,incoming,outgoing):
        self.incoming=incoming;self.outgoing=outgoing
        self.messages=queue.Queue(maxsize=16);self.output_lock=threading.Lock();self.active_lock=threading.Lock()
        self.closed=threading.Event();self.active=None;self.initialized=False;self.elicitation=False
        self.seen={};self.nonce=uuid.uuid4().hex;self.reader=None;self.episode=None;self.episodes={}
        self.authority=TrustedTaskAuthority('owned-mcp-'+self.nonce,self._approve)
        self.entry=TrustedTaskEntry(config_path,host,self.authority)
        self.live=LiveSpatialMCPServer(self.entry.service)

    def emit(self,value):
        raw=json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n'
        with self.output_lock:self.outgoing.write(raw);self.outgoing.flush()

    def stop_active(self):
        with self.active_lock:
            active=self.active
            if active is None:return
            active['cancelled'].set();key=active.get('registration_id')
        if key is not None:self.entry.revoke(key)

    def _read(self):
        try:
            while True:
                raw=self.incoming.readline(MAX_INPUT+1)
                if not raw:break
                if len(raw)>MAX_INPUT or len(raw.encode('utf8'))>MAX_INPUT:raise ValueError('MCP_input_budget')
                if not raw.strip():continue
                received=time.perf_counter()
                value=json.loads(raw,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
                if type(value) is not dict or value.get('jsonrpc')!='2.0':raise ValueError('MCP_request_object_required')
                with self.active_lock:active=self.active
                if value.get('method')=='notifications/cancelled':
                    params=value.get('params')
                    if active is not None and type(params) is dict and type(params.get('requestId')) is type(active['request_id']) and params['requestId']==active['request_id']:
                        self.stop_active()
                    continue
                self.messages.put_nowait((value,received))
        except Exception:
            # Input failure cannot renew a goal or silently lose cancellation.
            pass
        finally:
            self.closed.set();self.stop_active()

    def next_message(self,deadline=None,*,cancelled=None):
        while True:
            if self.closed.is_set():raise ValueError('MCP_connection_closed_or_input_failure')
            if cancelled is not None and cancelled.is_set():raise ValueError('MCP_request_cancelled')
            remaining=.1 if deadline is None else min(.1,deadline-time.perf_counter())
            if remaining<=0:raise ValueError('MCP_original_window_expired')
            try:return self.messages.get(timeout=remaining)
            except queue.Empty:continue

    def _approve(self,spec,scope):
        active=self.active
        if not self.elicitation or active is None or active['cancelled'].is_set():return None
        elicitation_id='he-approve-'+uuid.uuid4().hex
        binding=hashlib.sha256(json.dumps(dict(spec=spec.to_dict(),scope=scope),sort_keys=True,
            separators=(',',':'),allow_nan=False).encode('utf8')).hexdigest()
        message=('Human Eye owned Blender copy only. Approve this exact finite world-Z clearance task?\n'
            +json.dumps(dict(task=spec.to_dict(),scope=scope,proposal_sha256=binding,
                deadline_monotonic=active['deadline'],input_file_will_not_be_saved=True),sort_keys=True,allow_nan=False))
        if self.episode is not None:self.episode.bind(spec.to_dict(),scope,elicitation_id)
        self.emit(dict(jsonrpc='2.0',id=elicitation_id,method='elicitation/create',params=dict(message=message,
            requestedSchema=dict(type='object',properties=dict(approve=dict(type='boolean',default=False,
                title='Approve this exact task and budget')),required=['approve']))))
        while not active['cancelled'].is_set():
            value,_=self.next_message(active['deadline'],cancelled=active['cancelled'])
            if 'method' in value:
                # No nested command, second initialize or competing tool call
                # may change the pending proposal or its client capability.
                if valid_id(value.get('id')):self.emit(_rpc_error(value['id'],-32000,'owned goal approval is single-flight'))
                continue
            decision=approval_decision(value,elicitation_id)
            if self.episode is not None:self.episode.response(value,decision)
            if decision=='wrong_id':raise ValueError('MCP_unexpected_approval_response')
            if decision!='accept_true':return None
            if time.perf_counter()>=active['deadline'] or active['cancelled'].is_set() or self.closed.is_set():return None
            return TaskApproval(active['event_id'],elicitation_id)
        return None

    def _goal(self,request_id,arguments,received):
        if not self.elicitation:raise ValueError('client_form_elicitation_not_negotiated')
        spec=proposal(arguments)
        if self.episode is not None:self.episode.proposed(spec.to_dict())
        active=dict(request_id=request_id,event_id=task_event_id(self.nonce,request_id),cancelled=threading.Event(),
            deadline=received+spec.limits.max_duration_s,registration_id=None)
        with self.active_lock:self.active=active
        try:
            if self.closed.is_set():raise ValueError('MCP_connection_closed_before_registration')
            admission=self.entry.register(spec,received_monotonic=received)
            key=admission['registration_id']
            with self.active_lock:active['registration_id']=key
            if active['cancelled'].is_set() or self.closed.is_set():self.entry.revoke(key)
            if self.episode is not None:self.episode.admitted(admission)
            self._execution_started=True
            if self.episode is not None:self.episode.execution_started()
            result=self.entry.execute(key)
            if 'review_event' in result:
                result['review_event']['delivery']='MCP_result_constructed_not_client_consumption_proof'
            result['admission']=admission
            result['approval_source']='negotiated_stdio_client_elicitation_not_model_arguments'
            return _tool_result(result,is_error=False)
        finally:
            with self.active_lock:self.active=None

    def handle(self,req,*,received_monotonic=None):
        if 'id' not in req:return None
        request_id=req['id'];method=req.get('method');params=req.get('params',{})
        if not valid_id(request_id) or type(method) is not str or type(params) is not dict:
            return _rpc_error(None,-32600,'Invalid Request')
        if method=='initialize':
            if self.initialized:return _rpc_error(request_id,-32600,'initialize once per connection')
            self.initialized=True
            requested=params.get('protocolVersion');caps=params.get('capabilities')
            modern=requested in (PROTOCOL,'2025-11-25','2026-07-28')
            offered=caps.get('elicitation') if type(caps) is dict else None
            self.elicitation=(modern and type(offered) is dict and (not offered or type(offered.get('form')) is dict))
            response=self.live.handle_jsonrpc_message(req)
            if modern:response['result']['protocolVersion']=PROTOCOL
            response['result'].setdefault('capabilities',{})['resources']={}
            response['result']['serverInfo']['name']='human-eye-owned-task-candidate'
            response['result']['_meta']['owned_goal_entry']=dict(explicit_opt_in=True,form_elicitation=self.elicitation,
                trust_boundary='stdio_owner',wire_protocol=response['result']['protocolVersion'],default_Codex_UI_proven=False)
            return response
        if not self.initialized:return _rpc_error(request_id,-32000,'initialize required')
        if method=='resources/list':
            return dict(jsonrpc='2.0',id=request_id,result=dict(resources=[
                dict(uri=uri,name='Frozen Human Eye task episode',mimeType='application/json',
                    description='Historical evidence only; not execution authority or current scene')
                for uri in self.episodes]))
        if method=='resources/read':
            uri=params.get('uri')
            if type(uri) is not str or uri not in self.episodes:
                return _rpc_error(request_id,-32602,'Unknown episode resource in this connection')
            return dict(jsonrpc='2.0',id=request_id,result=dict(contents=[
                dict(uri=uri,mimeType='application/json',text=json.dumps(self.episodes[uri],allow_nan=False))]))
        if method=='tools/list':
            tools=[copy.deepcopy(t) for t in LIVE_MCP_TOOLS_SCHEMA if t['name'] in READ_TOOLS]+[copy.deepcopy(GOAL_TOOL)]
            return dict(jsonrpc='2.0',id=request_id,result=dict(tools=tools))
        if method=='tools/call' and params.get('name')==GOAL_TOOL['name']:
            key=(type(request_id).__name__,str(request_id))
            if key in self.seen:return _rpc_error(request_id,-32000,'duplicate call id cannot reexecute')
            if len(self.seen)>=MAX_CALLS:return _rpc_error(request_id,-32000,'owned goal call capacity reached')
            self.seen[key]=True
            self._execution_started=False
            received=time.perf_counter() if received_monotonic is None else received_monotonic
            self.episode=None
            try:
                self.episode=TaskEpisode(self.nonce,request_id,params.get('arguments',{}),received)
                result=self._goal(request_id,params.get('arguments',{}),received)
            except Exception as exc:
                # register() cannot dispatch. Once execute() begins it owns
                # unknown/known physical accounting and catches its exceptions.
                result=_tool_result(dict(status='goal_not_admitted_or_review_required',reason_codes=[str(exc)[:256]],
                    executed=None if self._execution_started else False,
                    new_setter_count=None if self._execution_started else 0,
                    execution_authority=False,retry_authorized=False),is_error=True)
            if self.episode is not None:
                public=json.loads(result['content'][0]['text'])
                try:
                    episode=self.episode.finish(public,time.perf_counter())
                    uri='human-eye-episode://'+self.nonce+'/'+episode['sha256']
                    self.episodes[uri]=episode
                    public['task_episode_ref']=dict(uri=uri,sha256=episode['sha256'],
                        outcome=episode['derived']['outcome'],training_positive=False,
                        human_UI_verified=False,durability='connection_memory_only')
                except Exception as exc:
                    # Recording cannot turn a reconciled action into zero or
                    # grant a retry. Preserve the actual execution receipt.
                    public['task_episode_unavailable']=type(exc).__name__
                finally:self.episode=None
                result=_tool_result(public,is_error=result.get('isError',False))
            return dict(jsonrpc='2.0',id=request_id,result=result)
        if method=='tools/call' and params.get('name') not in READ_TOOLS:
            return _rpc_error(request_id,-32601,'owned entry requires goal elicitation; legacy writes unavailable')
        return self.live.handle_jsonrpc_message(req)

    def run(self):
        self.reader=threading.Thread(target=self._read,name='human-eye-owned-MCP-input',daemon=True);self.reader.start()
        try:
            while True:
                req,received=self.next_message()
                if 'method' not in req:raise ValueError('unsolicited_client_response')
                response=self.handle(req,received_monotonic=received)
                if response is not None:self.emit(response)
        except (ValueError,BrokenPipeError,OSError):
            self.stop_active()


def main(argv=None):
    _configure_utf8_stdio();p=argparse.ArgumentParser(description='Opt-in owned Human Eye task MCP candidate')
    p.add_argument('--config',type=Path,required=True);p.add_argument('--blender',type=Path,required=True)
    p.add_argument('--scene',type=Path,required=True);args=p.parse_args(argv)
    from .blender_process import BlenderProcessHost
    with BlenderProcessHost(args.blender,args.scene) as host:
        OwnedTaskMCP(args.config,host,sys.stdin,sys.stdout).run()


if __name__=='__main__':main()
