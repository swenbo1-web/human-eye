"""Trusted local registration and one-use owned execution; no model JSON API."""
from __future__ import annotations
import copy,hashlib,json,threading,time
from dataclasses import replace
from pathlib import Path
from . import task_authority as a,goal_journal as journal
from .goal_scheduler import OwnedGoalScheduler,_digest,_json
from .goal_supervision import owned_host_counter,owned_clock_domain
from .goal_continuation import inspect_current_clearance


class TaskEntryError(ValueError):pass


def need(condition,reason):
    if not condition:raise TaskEntryError(reason)


class _TaskHandoff:
    """Process-local, one-use bridge; never reconstructed from a receipt."""
    def __init__(self,*args,**kwargs):raise TaskEntryError('private_task_handoff_required')

    @classmethod
    def _mint(cls,entry,live):
        value=object.__new__(cls);value.entry=entry;value.live=live;value.used=False
        return value

    def take(self,scheduler):
        with self.entry._cancel_lock:
            need(scheduler is self.entry._scheduler and self.live.get('handoff') is self
                and self.entry._live.get(self.live['grant'].key) is self.live and not self.used,
                'task_handoff_foreign_or_consumed')
            self.used=True
        self.check()
        record=self.entry._record(self.live['grant'].key,require_unstarted=True)
        need(record['grant']==self.entry.authority.verify(self.live['grant']),'task_handoff_binding_changed')
        return self.live['grant'],copy.deepcopy(self.live['initial']),self.live['resolved']

    def check(self):
        with self.entry._cancel_lock:
            need(self.live.get('handoff') is self and self.live.get('phase')=='executing'
                and not self.live['revoked'].is_set(),'task_entry_revoked')
            p=self.entry.authority.verify(self.live['grant'])
            counter=self.entry._check(started=p['issued_monotonic'],duration=self.live['resolved'].limits.max_duration_s,
                process=self.live['process'])
            need(owned_clock_domain(p['scope']['host_identity']['document_epoch'],counter)==p['scope']['clock_domain'],
                'task_entry_clock_domain_changed')

    def commit_guard(self,value):
        # No connector lock reentry or host RPC. This is the logical commit
        # boundary, not preemption of bytes/assignments already in flight.
        try:
            self.check()
            p=self.entry.authority.verify(self.live['grant'])
            record=value.get('goal_authorizations',{}).get('records',{}).get(p['key'])
            parent=value.get('goal_supervision',{}).get('records',{}).get(p['goal_id'])
            need(type(record) is dict and record['status']=='active' and record['grant']==p
                and type(parent) is dict and parent['status'] in ('active','pending'),'task_entry_commit_binding_changed')
        except Exception as exc:return ('registered_commit_denied:'+str(exc))[:256]
        return None


class TrustedTaskEntry:
    """Reuse the existing ledger; only this live instance retains a capability.

    The embedding authenticates TaskApproval. Receipt JSON grants no right to
    execute. Only execute() on the original live entry can consume the grant;
    the old scheduler.run does not reactivate a recorded event.
    """
    def __init__(self,config_path,host,authority):
        need(type(authority) is a.TrustedTaskAuthority,'trusted_task_authority_required')
        self._config=Path(config_path).resolve();self._config_raw=self._read_config()
        self._scheduler=OwnedGoalScheduler(config_path,host,authority)
        self.service=self._scheduler.service;self.host=host;self.authority=authority
        need(self._read_config()==self._config_raw,'task_entry_config_changed_during_construction')
        need(_json(self.service.config)==_json(json.loads(self._config_raw.decode('utf8'))),
             'task_entry_loaded_config_binding_changed')
        self._config_sha=hashlib.sha256(self._config_raw).hexdigest()
        self._build=self.service.describe_runtime()['build_id']
        self._lock=threading.RLock();self._cancel_lock=threading.Lock();self._live={};self._failed=set()

    def _read_config(self):
        with self._config.open('rb') as f:raw=f.read(65537)
        need(len(raw)<=65536,'task_entry_config_budget')
        return raw

    def _check(self,*,started=None,duration=None,process=None):
        need(self._read_config()==self._config_raw,'task_entry_config_changed')
        need(self.service.config.get('enabled',True),'connector_disabled')
        need(self.service._identity_rejection() is None and self.service.describe_runtime()['build_id']==self._build,
             'task_entry_source_changed')
        if started is not None:need(started<=time.perf_counter()<started+duration,'task_entry_original_window_expired')
        counter=owned_host_counter(self.host)
        if process is not None:need(self.host._process is process,'task_entry_process_changed')
        return counter

    def _record(self,key,*,require_unstarted=False):
        need(type(key) is str and len(key)==64 and all(c in '0123456789abcdef' for c in key),'task_entry_key')
        with self.service._locked() as (value,runtime):
            record=value.get('goal_authorizations',{}).get('records',{}).get(key)
            need(type(record) is dict and record['grant']['issuer_id']==self.authority.issuer_id,'task_entry_wrong_issuer_or_key')
            if require_unstarted:
                from .goal_execution import unfinished_segment
                parent=value.get('goal_supervision',{}).get('records',{}).get(record['grant']['goal_id'])
                need(record['status']=='active' and type(parent) is dict and parent['status']=='active'
                    and not parent['children'] and not value.get('inflight') and not runtime.status['quarantined']
                    and not unfinished_segment(value),'task_entry_not_unstarted_or_blocked')
            return copy.deepcopy(record)

    def _receipt(self,record,*,status=None,current=False,persistence='committed'):
        p=record['grant'];live=self._live.get(p['key'])
        available=(live is not None and live.get('phase','registered')=='registered'
                   and not live['revoked'].is_set() and record['status']=='active'
                   and p['key'] not in self._failed and time.perf_counter()<p['deadline_monotonic'])
        return dict(schema='trusted-local-task-entry-v1',status=status or ('registered' if available else 'review_required'),
            registration_id=p['key'],goal_id=p['goal_id'],session_id=p['session_id'],issuer_id=p['issuer_id'],event_id=p['event_id'],
            authorization_id=p['authorization_id'],durable_status=record['status'],reason=record['reason'],
            original_started_monotonic=p['issued_monotonic'],original_deadline_monotonic=p['deadline_monotonic'],
            limits=copy.deepcopy(p['spec']['limits']),scope=copy.deepcopy(p['scope']),
            config_fingerprint=self.service.config_fingerprint,config_sha256=p['scope'].get('connector_config_sha256'),
            live_registration_available=available,current_scene_revalidated=current,persistence=persistence,
            task_succeeded=None,executed=False,new_setter_count=0,execution_authority=False,retry_authorized=False,
            execution_phase='registered_not_dispatched')

    def _freeze(self,key,reason,*,revoked=False):
        live=self._live.get(key)
        if live is not None:live['revoked'].set()
        self._failed.add(key)
        with self.service._locked() as (value,runtime):
            record=value.get('goal_authorizations',{}).get('records',{}).get(key)
            need(type(record) is dict and record['grant']['issuer_id']==self.authority.issuer_id,'task_entry_wrong_issuer_or_key')
            if record['status'] in ('reserved','active'):
                parent=value.get('goal_supervision',{}).get('records',{}).get(record['grant']['goal_id'])
                if parent is not None:parent.update(status='frozen',reason=reason)
                a.set_authorization_state(value,key,'stopped' if revoked else 'frozen',reason=reason,
                    result=dict(status='revoked' if revoked else 'review_required',execution_authority=False,retry_authorized=False,
                        executed=False,new_setter_count=0,task_succeeded=None))
                self.service._save(value,runtime)
            return copy.deepcopy(value['goal_authorizations']['records'][key])

    def register(self,spec):
        """Receive and freeze an approved task without opening a motion goal."""
        started=time.perf_counter()
        need(type(spec) is a.ClearanceTaskSpec,'typed_task_spec_required_not_JSON')
        # Revalidate and detach the frozen proposal before any callback/host work.
        a._limits(spec.limits);proposal=replace(spec)
        with self._lock:
            grant=None;claimed=False
            try:
                duration=proposal.limits.max_duration_s
                counter=self._check(started=started,duration=duration);process=self.host._process
                initial=self._scheduler._capture()
                selector=self._scheduler._discover(proposal,initial,'local-entry-discovery')
                resolved=replace(proposal,reference_triangle_index=selector['reference_triangle_index'])
                native=inspect_current_clearance(initial,self._scheduler._policy(resolved,self._build))
                need(native['decision']!='stop','task_entry_initial_native_review_failed')
                scope=dict(engine_build_id=self._build,process_id=process.pid,host_identity=initial['capture']['host_identity'],
                    reference_triangle_index=resolved.reference_triangle_index,initial_capture_sha256=_digest(initial['capture']),
                    initial_native_sha256=_digest(initial['native_scene']),
                    clock_domain=owned_clock_domain(initial['capture']['host_identity']['document_epoch'],counter),
                    connector_config_sha256=self._config_sha)
                grant=self.authority.issue(resolved,scope,received_monotonic=started)
                need(grant.key not in self._failed,'task_entry_prior_failure_requires_review')
                if grant.key in self._live:
                    if self._live[grant.key].get('phase','registered')!='registered':
                        return self._history(grant.key)
                    self._record(grant.key,require_unstarted=True)
                self._check(started=started,duration=duration,process=process)
                need(_json(self._scheduler._capture())==_json(initial),'task_entry_scene_changed_after_approval')
                outcome=self._scheduler._claim(grant);claimed=outcome['fresh_claim']
                record=self._record(grant.key,require_unstarted=claimed)
                if not claimed:
                    original=record['grant'];same_snapshot=all(original['scope'][k]==scope[k] for k in
                        ('initial_capture_sha256','initial_native_sha256'))
                    if not same_snapshot:
                        record=self._freeze(grant.key,'task_entry_duplicate_snapshot_changed')
                    receipt=self._receipt(record);receipt.update(duplicate_event=True,current_scene_revalidated=False)
                    return receipt
                self._check(started=started,duration=duration,process=process)
                need(record['grant']==grant.payload() and record['status']=='active','task_entry_committed_binding_changed')
                with self._cancel_lock:
                    self._live[grant.key]=dict(grant=grant,initial=copy.deepcopy(initial),resolved=resolved,
                        process=process,revoked=threading.Event(),phase='registered')
                return self._receipt(record,current=True)
            except Exception as exc:
                # No capability escapes a failed/unknown commit. A possibly
                # committed index remains blocking; never automatically retry.
                if grant is not None:
                    self._failed.add(grant.key)
                    if grant.key in self._live:self._live[grant.key]['revoked'].set()
                    try:
                        record=self._freeze(grant.key,'task_entry_registration_failed:'+type(exc).__name__)
                        receipt=self._receipt(record,status='review_required');receipt['error']=str(exc)[:256]
                        return receipt
                    except Exception:pass
                raise TaskEntryError('task_entry_registration_unavailable:'+str(exc)) from exc

    def snapshot(self,key):
        """Freshly check only this process's live registration; history is inert."""
        with self._lock:
            live=self._live.get(key) if type(key) is str else None
            if live is not None and live.get('phase','registered')!='registered':return self._history(key)
            try:record=self._record(key,require_unstarted=live is not None and not live['revoked'].is_set())
            except Exception:
                if live is not None:live['revoked'].set();self._failed.add(key)
                raise
            if live is None or live['revoked'].is_set() or record['status']!='active':
                return self._receipt(record)
            try:
                p=self.authority.verify(live['grant'])
                need(p==record['grant'],'task_entry_persisted_binding_changed')
                counter=self._check(started=p['issued_monotonic'],duration=live['resolved'].limits.max_duration_s,process=live['process'])
                need(owned_clock_domain(p['scope']['host_identity']['document_epoch'],counter)==p['scope']['clock_domain'],
                     'task_entry_clock_domain_changed')
                need(_json(self._scheduler._capture())==_json(live['initial']),'task_entry_scene_changed')
                self._check(started=p['issued_monotonic'],duration=live['resolved'].limits.max_duration_s,process=live['process'])
                return self._receipt(record,current=True)
            except Exception as exc:
                try:record=self._freeze(key,'task_entry_recheck_failed:'+type(exc).__name__)
                except Exception:
                    live['revoked'].set();self._failed.add(key)
                    receipt=self._receipt(record,status='review_required',persistence='unknown');receipt['error']=str(exc)[:256]
                    return receipt
                receipt=self._receipt(record,status='review_required');receipt['error']=str(exc)[:256]
                return receipt

    def _history(self,key):
        live=self._live.get(key)
        if live is not None and live.get('result') is not None:
            result=copy.deepcopy(live['result'])
            result.update(historical_receipt=True,replayed=True,current_scene_revalidated=False,
                executed_this_call=False,new_setter_count=0,execution_authority=False,retry_authorized=False)
            if 'review_event' in result:result['review_event']['historical']=True
            return result
        if live is not None and live.get('phase')=='executing':
            # Do not contend with an in-flight connector transaction just to
            # acknowledge another caller. No physical outcome is known here.
            p=live['grant'].payload()
            return dict(status='execution_in_progress',registration_id=key,goal_id=p['goal_id'],
                original_deadline_monotonic=p['deadline_monotonic'],execution_authority=False,
                retry_authorized=False,executed_this_call=False,new_setter_count=0,
                task_succeeded=None,current_scene_revalidated=False)
        record=self._record(key)
        result=self._receipt(record);result.update(historical_receipt=True,replayed=True)
        return result

    def execute(self,key):
        """Consume the original live registration once; never reapprove/reset."""
        with self._lock:
            live=self._live.get(key) if type(key) is str else None
            if live is None or live.get('phase','registered')!='registered':return self._history(key)
            receipt=self.snapshot(key)
            if not receipt['live_registration_available']:return receipt
            with self._cancel_lock:
                if live['revoked'].is_set():return self._receipt(self._record(key))
                live['phase']='executing';handoff=_TaskHandoff._mint(self,live);live['handoff']=handoff
        # Never hold the entry lock across execution: revoke must be able to
        # flag cancellation while the existing kernel awaits a host receipt.
        try:result=self._scheduler.run_registered(handoff)
        except Exception as exc:
            # An embedding/transport exception may follow physical execution;
            # do not fabricate zero movement or reopen the consumed entry.
            reason=('registered_executor_unavailable:'+type(exc).__name__)[:256]
            result=dict(status='review_required',task_succeeded=False,executed_this_call=None,
                new_setter_count=None,execution_authority=False,retry_authorized=False,
                execution_phase='executor_outcome_unknown',reason_codes=[reason],
                review_event=dict(schema='owned-task-review-v1',event_id=key+':review',kind='review_required',
                    historical=False,execution_authority=False,retry_authorized=False))
            result=self._scheduler._record_stop(live['grant'],result,reason)
        with self._lock:
            live['result']=copy.deepcopy(result);live['phase']='finished';live['revoked'].set()
        return result

    def revoke(self,key):
        """Stops eligibility first; never a rollback, eviction or budget reset."""
        with self._cancel_lock:
            live=self._live.get(key) if type(key) is str else None
            if live is not None:live['revoked'].set()
        with self._lock:
            live=self._live.get(key) if type(key) is str else None
            if live is not None:live['revoked'].set();self._failed.add(key)
            if live is not None and live.get('phase')=='executing':
                result=self._history(key)
                result.update(status='revocation_requested',persistence='pending_executor_stop')
                return result
            record=self._record(key)
            try:record=self._freeze(key,'task_entry_revoked',revoked=True)
            except Exception as exc:
                receipt=self._receipt(record,status='review_required',persistence='unknown');receipt['error']=str(exc)[:256]
                return receipt
            return self._receipt(record,status='revoked')


__all__=['TrustedTaskEntry','TaskEntryError']
