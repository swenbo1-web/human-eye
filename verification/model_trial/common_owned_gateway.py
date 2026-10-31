"""Separate A2/C2 common native gateway, with no provider or model permission API.

The owner creates one typed intent, one fixed process and one episode. Both
arms see identical native schemas; only C2 also has the no-argument automatic
task entry. Runtime-side episode accounting covers every physical setter.
"""
from __future__ import annotations
import base64,copy,hashlib,json,math,struct,threading,time,zlib
from dataclasses import replace
from fractions import Fraction

# Runtime owns the mature PNG/frustum validators; retain legacy private names.
from human_eye_plugin.native_observation import (
    _require, _json, _digest, _finite, _vector, _public_native_png, _public_query, _validate_private_render_state, _validated_render_audit, _near, _points, _center, _dot, _feature_width, _validate_multiscale_plan, _validate_multiscale_frustum)

from .deadline import EpisodeDeadline,DeadlineExceeded
from .owned_goal_adapter import OwnedTaskIntent,OwnedGoalEpisode
from .tools import _NATIVE,validate_schema,sanitize_result,ToolRejected,UnconfirmedToolOutcome

PROTOCOL='owned-common-native-v1-20261031'
READONLY_EVIDENCE_PROTOCOL='owned-readonly-native-evidence-v1-20261031'
RENDER_AUDIT_PROTOCOL='owned-native-render-audit-v1-20261031'
MULTISCALE_PROTOCOL='owned-native-multiscale-v1-20261031'
MULTISCALE_NAME='native_look_multiscale'
_MULTISCALE={'name':MULTISCALE_NAME,'description':
    'Observe the current registered focal object with a native 384px overview and, only when geometric size/gain '
    'and a bounded central-ray check justify it, one additional 384px local window. All scene assets remain in '
    'the render and depth range. Public framing states the intentional crop and one-sample visibility limits. '
    'At most two images per call; the original episode deadline is not renewed. This is not an episode-wide image-slot limit.',
    'inputSchema':copy.deepcopy(_NATIVE[1]['inputSchema'])}
_MAX_MULTISCALE_PNG_BYTES=16*1024*1024
AUTO_NAME='human_eye_run_registered_task'
_AUTO={'name':AUTO_NAME,'description':
    'Run the owner-registered task within this original episode and its remaining shared physical budget. '
    'No task, object, event, authority, deadline, or budget may be supplied. A historical result does not verify the current scene.',
    'inputSchema':{'type':'object','properties':{},'additionalProperties':False}}
_OBJECT_KEYS=('object_id','name','local_vertices','world_vertices','faces','matrix','color')
_RENDER_STATE_SCOPE='render-helper-assigned-and-implicitly-dependent-scalars-camera-assets-selection'






















class CommonOwnedGateway:
    """Trusted owner bridge. No public handle grants arbitrary Python rights."""
    def __init__(self,arm,config_path,host,*,task,initial_evidence,deadline,expected_build_id,issuer_id):
        from human_eye_plugin.auto_router import _validated_scene
        from human_eye_plugin.goal_supervision import owned_host_counter
        from human_eye_plugin.runtime_identity import runtime_identity,check_source_drift
        _require(arm in ('A2','C2'),'new_common_arm_required')
        _require(type(task) is OwnedTaskIntent,'exact_owner_intent_required')
        _require(type(deadline) is EpisodeDeadline and deadline.clock is time.perf_counter
            and deadline.watchdog_active,'original_perf_counter_watchdog_required')
        deadline.check();counter=owned_host_counter(host)
        identity=runtime_identity(mode='live')
        _require(identity['build_id']==expected_build_id and identity['source_kind']=='installed_distribution'
            and check_source_drift()['compatible'],'candidate_installed_runtime_required')
        caps=host.capabilities()
        _require(caps.get('common_native_protocol')==PROTOCOL and caps.get('common_native_clock')==counter,
                 'common_fixed_worker_protocol_required')
        _require(caps.get('native_render_audit_protocol')==RENDER_AUDIT_PROTOCOL,
                 'owner_native_render_audit_protocol_required')
        if task.read_only:
            _require(caps.get('readonly_native_evidence_protocol')==READONLY_EVIDENCE_PROTOCOL,
                     'owner_readonly_native_evidence_protocol_required')
        _require(type(initial_evidence) is dict and {'capture','native_scene'}<=set(initial_evidence),
                 'original_owner_evidence_required')
        capture=_validated_scene(initial_evidence['capture'])[0]
        initial={'capture':capture,'native_scene':copy.deepcopy(initial_evidence['native_scene'])}
        _json(initial)
        self.arm=arm;self._host=host;self._process=host._process;self._pid=self._process.pid
        self._task=OwnedTaskIntent(task.spec,task.event_id,task.authorization_id,task.read_only)
        self._initial=copy.deepcopy(initial);self._deadline=deadline
        self._deadline_ns=int(Fraction(deadline.expires_at)*1_000_000_000)
        self._config_path=config_path;self._build=expected_build_id;self._issuer=issuer_id
        self._lock=threading.RLock();self._revoked=threading.Event();self._closed=False;self._poisoned=False
        self._binding=None;self._events=[];self._render_audits=[];self._render_failures=[];self._auto=None;self._auto_result=None;self._auto_attempted=False
        self._multiscale_audits=[]
        self._private_exception=None;self._kill_requested=False;self._kill_error=None;self._unregister=None
        self._original_window=deadline.snapshot();self._last_status=None
        self._multiscale_enabled=(caps.get('native_multiscale_protocol')==MULTISCALE_PROTOCOL
            and all(callable(getattr(host,name,None)) for name in ('native_look_multiscale','last_native_multiscale_audit')))
        self._schemas=copy.deepcopy(_NATIVE+([_MULTISCALE] if self._multiscale_enabled else [])+([] if arm=='A2' else [_AUTO]))
        self._by_name={v['name']:v['inputSchema'] for v in self._schemas}
        self._limits={'max_setters':self._task.spec.limits.max_steps,
            'max_step_translation_m':self._task.spec.limits.max_step_translation_m,
            'max_total_translation_m':self._task.spec.limits.max_total_translation_m}
        self._unregister=deadline.add_expiry_callback(self._expire_owned)
        try:
            self._check()
            # Initial owner data must still be the actual worker scene.
            fresh=host.capture_readonly_evidence() if self._task.read_only else host.capture_evidence()
            if self._task.read_only:
                coherence=fresh.get('coherence',{}) if type(fresh) is dict else {}
                _require(type(coherence) is dict and coherence.get('read_only_evidence') is True
                    and coherence.get('read_only_evidence_protocol')==READONLY_EVIDENCE_PROTOCOL
                    and coherence.get('execution_authority') is False, 'typed_readonly_native_evidence_required')
            _require(_json(fresh['native_scene'])==_json(initial['native_scene'])
                and _json(_validated_scene(fresh['capture'])[0])==_json(capture),'initial_owner_scene_changed')
            report=host.begin_owned_episode(deadline.episode_id,self._task.spec.focal_id,self._task.spec.reference_id,
                self._deadline_ns,read_only=self._task.read_only,limits=copy.deepcopy(self._limits))
            self._validate_status(report,initial=True)
            self._initial_public=_public_query(host.native_scene_query())
            self._check()
        except BaseException:
            if self._unregister is not None:self._unregister();self._unregister=None
            raise

    @property
    def bound_deadline(self):return self._deadline
    @property
    def deadline_enforced(self):
        return (not self._closed and not self._revoked.is_set() and self._deadline.watchdog_active
            and self._host.is_alive and self._host._process is self._process and self._process.pid==self._pid)
    @property
    def uncertain_outcome(self):return self._poisoned or self._revoked.is_set()
    def bind_deadline(self,budget):
        _require(budget is self._deadline,'common_episode_deadline_cannot_be_replaced');self._check();return self
    def tool_schemas(self):return copy.deepcopy(self._schemas)
    @property
    def schemas(self):return self.tool_schemas()
    def public_registration(self):
        return {'task':copy.deepcopy(self._task.spec.to_dict()),'read_only':self._task.read_only,
            'shared_limits':copy.deepcopy(self._limits),'length_unit':'m','public_task_constraints':True}

    def _expire_owned(self):
        self._revoked.set();self._poisoned=True;self._host._poisoned=True
        if self._process.pid==self._pid and self._process.poll() is None:
            try:self._kill_requested=True;self._process.kill()
            except OSError as exc:self._kill_error=type(exc).__name__
    def _check(self):
        if self._closed or self._poisoned or self._revoked.is_set():
            raise UnconfirmedToolOutcome('common episode admission revoked; no later native or automatic action')
        self._deadline.check()
        _require(self._deadline.watchdog_active and self._host.is_alive and self._host._process is self._process
            and self._process.pid==self._pid,'original_common_owned_process_unavailable')

    def _validate_status(self,report,*,initial=False):
        try:return self._validate_status_value(report,initial=initial)
        except UnconfirmedToolOutcome:
            self._poisoned=True;raise
        except Exception:
            self._poisoned=True
            raise UnconfirmedToolOutcome('malformed common physical accounting; all channels stopped') from None

    def _validate_status_value(self,report,*,initial=False):
        from human_eye_plugin.host_motion_ledger import _binding
        _require(type(report) is dict and report.get('schema_version')=='owned-episode-ledger-v1'
            and report.get('protocol')==PROTOCOL,'complete_common_episode_report_required')
        _require(report.get('episode_id')==self._deadline.episode_id and report.get('deadline_ns')==self._deadline_ns
            and report.get('limits')==self._limits and report.get('read_only') is self._task.read_only,
            'original_common_episode_changed')
        binding=_binding(report.get('binding'))
        wanted=self._initial['capture']['host_identity']
        _require(binding['document_epoch']==wanted['document_epoch'] and binding['object_instances']==wanted['object_instances']
            and binding['focal_id']==self._task.spec.focal_id and binding['reference_id']==self._task.spec.reference_id,
            'common_episode_original_binding_changed')
        if self._binding is None:self._binding=copy.deepcopy(binding)
        else:_require(binding==self._binding,'common_episode_original_binding_changed')
        coverage=report.get('coverage',{})
        _require(coverage.get('protocol')==PROTOCOL and type(coverage.get('process_id')) is int
            and coverage['process_id']==self._pid and coverage.get('generic_code_execution') is False
            and coverage.get('ui_attached') is False
            and coverage.get('scope')=='all_legal_setters_of_this_owned_typed_worker'
            and coverage.get('external_process_or_modified_worker_proof') is False,
            'common_episode_fixed_worker_coverage_required')
        count=report.get('actual_setter_count');reserved=report.get('reserved_event_count')
        remaining=report.get('remaining_setters');path=report.get('actual_cumulative_translation_m')
        remaining_path=report.get('remaining_translation_m')
        unknown=report.get('unknown_event_count')
        _require(type(unknown) is int and 0<=unknown<=self._limits['max_setters']
            and report.get('closed') is False and report.get('execution_authority') is False,
            'common_episode_completion_flags_invalid')
        _require(all(type(v) is int and 0<=v<=self._limits['max_setters'] for v in (count,reserved,remaining))
            and count<=reserved and reserved+remaining==self._limits['max_setters'], 'common_episode_setter_accounting_invalid')
        _require(_finite(path) and _finite(remaining_path) and path>=0 and remaining_path>=0
            and path<=self._limits['max_total_translation_m'] and remaining_path<=self._limits['max_total_translation_m'],
            'common_episode_path_accounting_invalid')
        if report.get('frozen_reason') is not None or unknown!=0:
            self._poisoned=True
            raise UnconfirmedToolOutcome('common physical episode requires review; all channels stopped')
        _require(report.get('registered_events_complete') is True and report.get('all_channels_complete') is True,
            'common_episode_incomplete_trace')
        events=report.get('events')
        _require(type(events) is list and len(events)==reserved,'common_episode_full_trace_required')
        expected_native=report.get('initial_native');_public_query(expected_native)
        _require(_json(expected_native)==_json(self._initial['native_scene']),'common_episode_initial_native_changed')
        exact_path=Fraction();confirmed=0
        for index,event in enumerate(events,1):
            _require(type(event) is dict and event.get('index')==index
                and type(event.get('index')) is int and event.get('kind') in ('forward','rollback')
                and event.get('state') in ('confirmed','cancelled_before_entry'), 'common_episode_event_invalid')
            _require(type(event.get('reserved_ns')) is int and type(event.get('confirmed_ns')) is int
                and 0<=event['reserved_ns']<=event['confirmed_ns'],'common_episode_event_time_invalid')
            before=event.get('before_native');after=event.get('after_native')
            _public_query(before);_public_query(after)
            _require(_json(before)==_json(expected_native),'common_episode_native_chain_changed')
            focal=binding['focal_id']
            old=next(v for v in before['objects'] if v['object_id']==focal)
            new=next(v for v in after['objects'] if v['object_id']==focal)
            motion=math.dist([old['matrix'][i][3] for i in range(3)],[new['matrix'][i][3] for i in range(3)])
            amount=event.get('actual_translation_m')
            _require(_finite(amount) and 0<=amount<=self._limits['max_step_translation_m']
                and amount==motion,'common_episode_actual_motion_invalid')
            if event['state']=='cancelled_before_entry':
                _require(amount==0 and _json(after)==_json(before),'common_episode_cancelled_entry_changed')
            else:confirmed+=1;exact_path+=Fraction(amount)
            expected_native=after
        _require(confirmed==count and float(exact_path)==path
            and exact_path<=Fraction(self._limits['max_total_translation_m']), 'common_episode_path_trace_disagrees')
        exact_remaining=Fraction(self._limits['max_total_translation_m'])-exact_path
        floored=float(exact_remaining)
        if Fraction(floored)>exact_remaining:floored=math.nextafter(floored,0.)
        _require(remaining_path==floored and _json(report.get('last_native'))==_json(expected_native),
                 'common_episode_remaining_or_endpoint_disagrees')
        if initial:_require(count==reserved==0 and path==0,'common_episode_not_fresh_zero')
        self._last_status=copy.deepcopy(report);return copy.deepcopy(report)
    def _status(self):
        try:return self._validate_status(self._host.owned_episode_status())
        except Exception:
            self._poisoned=True;raise

    def _capture_native_render_audit(self, view):
        """Accept actual restored owner evidence before releasing a public image."""
        try:
            mesh_names=[obj['name'] for obj in self._initial['native_scene']['objects']]
            previous=self._render_audits[-1]['sequence'] if self._render_audits else 0
            self._render_audits.append(_validated_render_audit(self._host.last_native_render_audit(),view,mesh_names,previous))
        except Exception as exc:
            self._poisoned=True
            self._private_exception={'type':type(exc).__name__,'message':str(exc)}
            raise UnconfirmedToolOutcome('native render restoration evidence unconfirmed; all channels stopped') from None

    def _read_multiscale(self,view):
        """Stage the complete image/audit bundle; caller commits after final checks."""
        before=_public_query(self._host.native_scene_query())
        raw=self._host.native_look_multiscale(view)
        bundle=self._host.last_native_multiscale_audit()
        after=_public_query(self._host.native_scene_query())
        _require(_json(before)==_json(after),'multiscale_scene_revision_changed')
        _require(type(raw) is dict and set(raw)=={'overview','detail','plan'},'multiscale_response_fields')
        plan=_validate_multiscale_plan(raw['plan'],before,view,self._task.spec.focal_id)
        keys={'schema_version','protocol','status','view','sequence','native_revision_before','native_revision_after',
            'plan','frames','error','execution_authority'}
        _require(type(bundle) is dict and set(bundle)==keys and bundle['schema_version']=='native-multiscale-audit-v1'
            and bundle['protocol']==MULTISCALE_PROTOCOL and bundle['status']=='completed' and bundle['view']==view
            and type(bundle['sequence']) is int and bundle['sequence']>0
            and (not self._multiscale_audits or bundle['sequence']>self._multiscale_audits[-1]['sequence'])
            and bundle['native_revision_before']==bundle['native_revision_after']==before['revision']
            and _json(bundle['plan'])==_json(plan) and bundle['error'] is None
            and bundle['execution_authority'] is False,'multiscale_bundle_audit_invalid')
        frames=bundle['frames'];count=plan['image_count']
        _require(type(frames) is list and len(frames)==count and (raw['detail'] is not None)==plan['detail_included'],
            'multiscale_bundle_frame_count')
        mesh_names=[obj['name'] for obj in before['objects']]
        previous=self._render_audits[-1]['sequence'] if self._render_audits else 0
        staged=[];pictures={};total_bytes=0
        for index,kind in enumerate(('overview','detail')[:count]):
            record=frames[index];image=raw[kind]
            _require(type(record) is dict and set(record)=={'kind','png_sha256','render_audit','frustum'}
                and record['kind']==kind,'multiscale_frame_audit_fields')
            audit=_validated_render_audit(record['render_audit'],view,mesh_names,previous)
            if staged:_require(audit['sequence']==previous+1,'multiscale_frame_audits_not_consecutive')
            if staged:_require(_json(audit['before'])==_json(staged[0]['before']),'multiscale_between_frames_state_changed')
            previous=audit['sequence'];staged.append(audit)
            _validate_multiscale_frustum(record['frustum'],plan[kind],before,view,kind)
            _require(type(image) is dict and image.get('mime_type')=='image/png'
                and type(image.get('width')) is int and type(image.get('height')) is int
                and image['width']==image['height']==384 and image.get('view')==view
                and type(image.get('image_base64')) is str
                and len(image['image_base64'])<=4*((8*1024*1024+2)//3),'multiscale_image_fields')
            png=base64.b64decode(image['image_base64'],validate=True);total_bytes+=len(png)
            _require(len(png)<=8*1024*1024 and total_bytes<=_MAX_MULTISCALE_PNG_BYTES
                and record['png_sha256']==hashlib.sha256(png).hexdigest(),'multiscale_image_hash_or_budget')
            public_png=_public_native_png(png)
            _require(struct.unpack('>II',public_png[16:24])==(384,384),'multiscale_native_png_shape')
            pictures[kind]={key:copy.deepcopy(image[key]) for key in ('mime_type','image_base64','width','height','view')}
            pictures[kind]['image_base64']=base64.b64encode(public_png).decode('ascii')
        return {'overview':pictures['overview'],'detail':pictures.get('detail'),'plan':plan},staged,copy.deepcopy(bundle)

    def _known_native_refusal(self,exc):
        from human_eye_plugin.blender_process import HostRemoteError
        return (type(exc) is HostRemoteError and exc.error.get('type')=='EpisodePrewriteRefused'
            and exc.error.get('mutation_uncertain') is False and exc.error.get('known_preentry_refusal') is True
            and exc.error.get('executed') is False)

    def _native_one(self,arguments):
        before=_public_query(self._host.native_scene_query())
        if arguments['expected_revision']!=before['revision']:
            return {'applied':False,'executed':False,'status':'rejected_before_mutation','reason':'stale_native_revision'}
        try:
            self._host.native_transform(arguments['object_id'],arguments['delta_world_m'],arguments['expected_revision'])
        except Exception as exc:
            if self._known_native_refusal(exc):
                self._status()
                return {'applied':False,'executed':False,'status':'rejected_before_mutation','reason':'known_native_preentry_refusal'}
            self._poisoned=True
            raise UnconfirmedToolOutcome('native write outcome unconfirmed; no later actions') from None
        self._status();after=_public_query(self._host.native_scene_query())
        old=next(v for v in before['objects'] if v['object_id']==arguments['object_id'])
        new=next(v for v in after['objects'] if v['object_id']==arguments['object_id'])
        delta=[new['matrix'][i][3]-old['matrix'][i][3] for i in range(3)]
        return {'applied':True,'object_id':arguments['object_id'],'revision':after['revision'],'delta_world_m':delta,'scene':after}

    def call(self,name,arguments):
        with self._lock:
            self._check()
            if name not in self._by_name:raise ToolRejected('tool outside the common arm whitelist')
            validate_schema(arguments,self._by_name[name]);args=copy.deepcopy(arguments);started=time.perf_counter()
            self._status()
            pending_multiscale=None
            try:
                if name==AUTO_NAME:return self.run_registered_task()
                if name=='native_scene_query':value=_public_query(self._host.native_scene_query())
                elif name=='native_look':
                    raw=self._host.native_look(args.get('view','SCENE'))
                    self._capture_native_render_audit(args.get('view','SCENE'))
                    _require(type(raw) is dict and raw.get('mime_type')=='image/png' and raw.get('width')==raw.get('height')==384,
                        'common_native_image_invalid')
                    png=base64.b64decode(raw['image_base64'],validate=True)
                    png=_public_native_png(png)
                    _require(struct.unpack('>II',png[16:24])==(384,384),'common_native_png_invalid')
                    value={k:raw[k] for k in ('mime_type','image_base64','width','height','view')}
                    value['image_base64']=base64.b64encode(png).decode('ascii')
                elif name==MULTISCALE_NAME:
                    value,staged,bundle=self._read_multiscale(args.get('view','SCENE'))
                    pending_multiscale=(staged,bundle)
                elif name=='native_compute':
                    from .common_compute import run_common_compute
                    value=run_common_compute(args['code'],_public_query(self._host.native_scene_query()),self._deadline)
                    value=sanitize_result(value)
                else:
                    if 'actions' in args:
                        current=args['expected_revision'];results=[];stopped=False
                        for action in args['actions']:
                            part=self._native_one({**action,'expected_revision':current});results.append(part)
                            if part.get('applied') is not True:stopped=True;break
                            current=part['revision']
                        value={'results':results,'stopped':stopped,'revision':current}
                    else:value=self._native_one(args)
                self._check();self._status()
                if pending_multiscale is not None:
                    self._render_audits.extend(pending_multiscale[0]);self._multiscale_audits.append(pending_multiscale[1])
                self._events.append({'name':name,'arguments':args,'started':started,
                    'elapsed_s':time.perf_counter()-started,'public_result':copy.deepcopy(value)})
                return value
            except Exception as exc:
                if name in ('native_look',MULTISCALE_NAME):
                    self._poisoned=True
                    self._private_exception={'type':type(exc).__name__,'message':str(exc)}
                    failure={'error':copy.deepcopy(self._private_exception),'audit':None}
                    if self._host.is_alive:
                        try:
                            read=self._host.last_native_multiscale_audit if name==MULTISCALE_NAME else self._host.last_native_render_audit
                            failure['audit']=copy.deepcopy(read())
                        except Exception as audit_exc:failure['audit_error']={'type':type(audit_exc).__name__,'message':str(audit_exc)}
                    self._render_failures.append(failure)
                    raise UnconfirmedToolOutcome('native render result or restoration unconfirmed; all channels stopped') from None
                if isinstance(exc,(UnconfirmedToolOutcome,DeadlineExceeded)) or not self._host.is_alive:
                    self._poisoned=True
                elif name in ('native_scene_query','native_look') and isinstance(exc,(ValueError,KeyError,TypeError,struct.error)):
                    self._poisoned=True
                self._private_exception={'type':type(exc).__name__,'message':str(exc)}
                raise

    def run_registered_task(self):
        with self._lock:
            self._check()
            if self.arm!='C2':raise ToolRejected('native arm has no automatic task capability')
            if self._auto_attempted:
                result=copy.deepcopy(self._auto_result)
                result.update(historical_receipt=True,executed_this_call=False,new_setter_count_this_call=0,
                    current_scene_revalidated=False)
                return result
            self._auto_attempted=True
            self._auto_result={'status':'unknown','task_succeeded':False,'executed_this_call':None,
                'new_setter_count_this_call':None,'historical_receipt':False,'execution_authority':False,
                'retry_authorized':False,'formal_eligible':False,'common_native_parity':False,'provider_requests':0}
            try:self._run_auto_once()
            except Exception as exc:
                self._poisoned=True
                self._private_exception={'type':type(exc).__name__,'message':str(exc)}
                self._auto_result={'status':'unknown','task_succeeded':False,'executed_this_call':None,
                    'new_setter_count_this_call':None,'historical_receipt':False,'execution_authority':False,
                    'retry_authorized':False,'formal_eligible':False,'common_native_parity':False,'provider_requests':0}
            return copy.deepcopy(self._auto_result)

    def _run_auto_once(self):
        status=self._status()
        if self._task.read_only:
            self._auto_result={'status':'refused','task_succeeded':False,'executed_this_call':False,
                'new_setter_count_this_call':0,'historical_receipt':False,'execution_authority':False,
                'retry_authorized':False,'formal_eligible':False,'common_native_parity':False,'provider_requests':0}
            return
        if status['remaining_setters']<1 or status['remaining_translation_m']<=0:
            self._auto_result={'status':'review_required','task_succeeded':False,'executed_this_call':False,
                'new_setter_count_this_call':0,'historical_receipt':False,'execution_authority':False,
                'retry_authorized':False,'formal_eligible':False,'common_native_parity':False,'provider_requests':0}
            return
        original=self._task.spec.limits
        bounded=replace(original,max_steps=min(original.max_steps,status['remaining_setters']),
            max_step_translation_m=min(original.max_step_translation_m,status['remaining_translation_m']),
            max_total_translation_m=min(original.max_total_translation_m,status['remaining_translation_m']),
            max_duration_s=min(original.max_duration_s,self._deadline.remaining()))
        intent=OwnedTaskIntent(replace(self._task.spec,limits=bounded),self._task.event_id,self._task.authorization_id)
        fresh=self._host.capture_evidence();self._check()
        self._auto=OwnedGoalEpisode(self._config_path,self._host,task=intent,initial_evidence=fresh,
            deadline=self._deadline,expected_build_id=self._build,issuer_id=self._issuer)
        self._auto_result=self._auto.run()
        if self._auto.uncertain_outcome or self._auto_result.get('status') in ('unknown','expired','review_required'):
            self._poisoned=True
        else:self._status()

    def private_snapshot(self):
        with self._lock:
            status=copy.deepcopy(self._last_status)
            if self._host.is_alive:
                try:status=copy.deepcopy(self._host.owned_episode_status())
                except Exception:pass
            return {'schema_version':'common-owned-gateway-private-v1','arm':self.arm,
                'registered_task':{'spec':self._task.spec.to_dict(),'event_id':self._task.event_id,
                    'authorization_id':self._task.authorization_id,'read_only':self._task.read_only},
                'initial_evidence':copy.deepcopy(self._initial),'initial_public_query':copy.deepcopy(self._initial_public),
                'original_episode_window':copy.deepcopy(self._original_window),'current_deadline':self._deadline.snapshot(),
                'episode_status':status,'public_calls':copy.deepcopy(self._events),'poisoned':self._poisoned,
                'native_render_audits':copy.deepcopy(self._render_audits),
                'native_multiscale_audits':copy.deepcopy(self._multiscale_audits),
                'native_render_failures':copy.deepcopy(self._render_failures),
                'automatic_attempted':self._auto_attempted,'automatic_private':None if self._auto is None else self._auto.private_snapshot(),
                'automatic_public':copy.deepcopy(self._auto_result),'private_exception':copy.deepcopy(self._private_exception),
                'kill_requested':self._kill_requested,'kill_error':self._kill_error,
                'formal_eligible':False,'common_native_parity':False,'provider_requests':0}
    def close(self):
        with self._lock:
            _require(self._process.poll() is not None,'owned_process_must_be_reaped_before_common_close')
            self._closed=True
            if self._auto is not None:self._auto.close()
            if self._unregister is not None:self._unregister();self._unregister=None

__all__=['CommonOwnedGateway','AUTO_NAME','PROTOCOL','MULTISCALE_NAME','MULTISCALE_PROTOCOL']
