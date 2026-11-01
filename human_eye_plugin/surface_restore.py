"""Owned same-index patch restore kernel, separate from every rigid grant.

Trusted embedding supplies exclusive capture/setter callbacks and its approval
decision. No model tool or serialized object can restore this live capability.
Unknown readback quarantines the instance; it never retries or renews a budget.
"""
import copy,time,threading,os,json,uuid
from pathlib import Path
from . import mesh_structure as raw,surface_geometry as g
from .surface_reference import ReferenceRegistry,preview_restore


class RestoreJournal:
    """16 lifetime slots; crash recovery is read-only, never new authority.

    File fsync + atomic replacement preserves a pending intent before each
    setter. This is not a filesystem/power-loss or same-account adversary proof.
    The OS lock releases on process death; any unfinished slot then freezes
    execution, instead of treating a released lock as a fresh budget.
    """
    def __init__(self,root):
        self.root=Path(root);g.require(self.root.is_absolute() and self.root.resolve()==self.root and self.root.is_dir(),'restore_journal_root')
        self._fd=os.open(str(self.root/'.lock'),os.O_CREAT|os.O_RDWR,0o600);self._active={};self.poisoned=False
        try:
            if os.name=='nt':
                import msvcrt
                os.lseek(self._fd,0,0);msvcrt.locking(self._fd,msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self._fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.history=self.inspect(self.root)
            self.poisoned=self.history['unknown']
        except BaseException:os.close(self._fd);self._fd=None;raise

    def close(self):
        if self._fd is not None:os.close(self._fd);self._fd=None

    @staticmethod
    def inspect(root):
        root=Path(root);rows=[];unknown=False;entries=[]
        with os.scandir(root) as scan:
            for item in scan:
                entries.append(item.name)
                g.require(len(entries)<=17,'restore_journal_entry_budget')
        g.require(all(x=='.lock' or x in {'slot-%02d'%i for i in range(16)} for x in entries),'restore_journal_namespace')
        for name in sorted(x for x in entries if x!='.lock'):
            folder=root/name;record=None;reason=None
            try:
                g.require(folder.is_dir() and folder.resolve()==folder,'restore_journal_slot')
                with os.scandir(folder) as scan:
                    names=[]
                    for item in scan:
                        names.append(item.name);g.require(len(names)<=3,'restore_journal_slot_budget')
                g.require(names==['RECORD.json'],'restore_journal_incomplete_publication')
                with (folder/'RECORD.json').open('rb') as f:blob=f.read(65537)
                g.require(len(blob)<=65536,'restore_journal_record_budget')
                def unique(pairs):
                    result={}
                    for k,v in pairs:g.require(k not in result,'restore_journal_duplicate_key');result[k]=v
                    return result
                def reject(_):raise ValueError('restore_journal_nonfinite')
                record=json.loads(blob,object_pairs_hook=unique,parse_constant=reject)
                g.require(type(record) is dict and set(record)=={'payload','sha256'} and g.digest(record['payload'])==record['sha256'],'restore_journal_checksum')
                record=record['payload'];g.require(record['schema']=='owned-reference-restore-journal-v1' and record['stage']=='finished'
                    and type(record.get('result')) is dict and record['result'].get('unknown') is False
                    and type(record['result'].get('setter_attempts')) is int and 0<=record['result']['setter_attempts']<=128
                    and record['result'].get('status') in ('completed','failed_checkpoint_restored','refused_before_dispatch'),
                    'restore_journal_unfinished_or_unknown')
                if record['result']['setter_attempts']:
                    scope=record.get('scope');g.require(type(scope) is dict and scope.get('schema')=='owned-reference-patch-restore-v1'
                        and scope.get('event_id')==record['event_id'] and type(scope.get('maximum_setter_attempts')) is int
                        and record['result']['setter_attempts']<=scope['maximum_setter_attempts']<=128,'restore_journal_scope_binding')
            except Exception as exc:unknown=True;reason=str(exc)[:160]
            rows.append(dict(slot=name,event_id=record.get('event_id') if type(record) is dict else None,
                result=record.get('result') if reason is None else None,unknown=reason is not None,
                scope=record.get('scope') if reason is None else None,
                setter_count=None if reason else record['result']['setter_attempts'],reason=reason,execution_authority=False))
        return dict(rows=rows,unknown=unknown,execution_authority=False,restart_can_dispatch=False)

    def _publish(self,ticket,payload):
        g.require(self._fd is not None and not self.poisoned and ticket in self._active,'restore_journal_live_writer')
        slot=self._active[ticket];blob=g.encoded(dict(payload=payload,sha256=g.digest(payload)));g.require(len(blob)<=65536,'restore_journal_record_budget')
        temporary=slot/('.pending-'+uuid.uuid4().hex)
        try:
            with temporary.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
            os.replace(temporary,slot/'RECORD.json')
        except BaseException:self.poisoned=True;raise
        finally:
            if temporary.exists():temporary.unlink()

    def begin(self,event_id):
        g.require(not self.poisoned and self._fd is not None,'restore_journal_unknown_or_closed')
        history=self.inspect(self.root);g.require(not history['unknown'] and all(x['event_id']!=event_id for x in history['rows']),'restore_journal_reused_or_unknown')
        slot=self.root/('slot-%02d'%len(history['rows']));g.require(len(history['rows'])<16 and not slot.exists(),'restore_journal_lifetime_budget')
        slot.mkdir(exist_ok=False);ticket=object();self._active[ticket]=slot
        self.update(ticket,event_id,'preparing');return ticket

    def update(self,ticket,event_id,stage,**fields):
        self._publish(ticket,dict(schema='owned-reference-restore-journal-v1',event_id=event_id,stage=stage,**fields))


class RestoreController:
    def __init__(self,registry,*,journal,capture,set_vertex,approve,clock=time.perf_counter_ns):
        g.require(type(registry) is ReferenceRegistry and all(callable(x) for x in (capture,set_vertex,approve,clock)),'restore_trusted_callbacks')
        g.require(type(journal) is RestoreJournal,'restore_durable_journal_required');self.journal=journal
        self.registry=registry;self.capture=capture;self.set_vertex=set_vertex;self.approve=approve;self.clock=clock
        self._events=set();self.quarantined=journal.poisoned;self._gate=threading.Lock()

    def restore(self,reference_ref,indices,*,event_id,duration_ns=5_000_000_000,max_displacement_m=.001):
        g.require(self._gate.acquire(blocking=False),'restore_busy')
        self._ticket=None;self._write_intent=False;self._scope=None
        try:
            result=self._restore(reference_ref,indices,event_id=event_id,duration_ns=duration_ns,max_displacement_m=max_displacement_m)
            try:
                self.journal.update(self._ticket,event_id,'finished',scope=self._scope,result=result)
                if result['unknown']:self.journal.poisoned=True
            except Exception:
                self.quarantined=True;result.update(status='unknown_journal_commit',unknown=True,quarantined=True,physical_count_complete=False)
            return result
        except Exception as exc:
            if self._ticket is not None and not self._write_intent:
                try:self.journal.update(self._ticket,event_id,'finished',scope=self._scope,result=dict(status='refused_before_dispatch',unknown=False,setter_attempts=0,reason=str(exc)[:160]))
                except Exception:self.quarantined=True
            elif self._write_intent:self.quarantined=True
            raise
        finally:self._gate.release()

    def _restore(self,reference_ref,indices,*,event_id,duration_ns,max_displacement_m):
        received=self.clock();g.require(type(event_id) is str and 1<=len(event_id)<=128,'restore_event')
        g.require(not self.quarantined and event_id not in self._events and len(self._events)<16,'restore_reused_or_quarantined')
        g.require(type(duration_ns) is int and 0<duration_ns<=30_000_000_000,'restore_duration')
        self._events.add(event_id);self._ticket=self.journal.begin(event_id)
        deadline=received+duration_ns;attempts=0;confirmed=0;rollback=0
        def check():g.require(self.clock()<deadline,'restore_original_deadline')
        def budget():check();return raw.WorkBudget(deadline_ns=deadline,clock=self.clock)
        original=self.capture();check();binding=self.registry.resolve(reference_ref,original)
        # Blender may change a nonplanar n-gon's tessellation after a vertex
        # edit. A frozen triangle packet cannot certify that future surface.
        # This first write domain therefore admits original triangles only.
        g.require(all(len(p)==3 for p in original['raw']['polygons'])
            and binding['triangles']==original['raw']['polygons']
            and binding['polygon_indices']==list(range(len(original['raw']['polygons']))),'restore_original_triangles_required')
        proposal=preview_restore(binding,original,indices,budget=budget(),max_displacement_m=max_displacement_m)
        predicted=copy.deepcopy(original['raw'])
        for i,p in zip(proposal['indices'],proposal['proposed_local_vertices']):predicted['vertices'][i]=p[:]
        def contacts(value):
            prepared=dict(original,raw=value)
            report=g.analyze(prepared,binding['triangles'],binding['polygon_indices'],budget=budget(),near_m=0)
            g.require(report['scan_complete'] and not report['degenerate_triangles_total'] and report['omitted']==0,'restore_incomplete_contact_check')
            return {(tuple(sorted(r['triangles'])),r['kind'],r['relation']) for r in report['regions']}
        g.require(not contacts(predicted)-contacts(original['raw']),'restore_new_contact')
        scope=dict(schema='owned-reference-patch-restore-v1',event_id=event_id,source=original['source'],
            reference_source=binding['reference']['source'],indices=proposal['indices'],
            proposed_raw_sha256=g.digest(predicted),max_displacement_m=max_displacement_m,
            maximum_setter_attempts=2*len(indices),deadline_ns=deadline,received_ns=received,
            semantic_target=binding['intent']['semantic_target'])
        self._scope=copy.deepcopy(scope);self.journal.update(self._ticket,event_id,'prepared',scope=scope)
        answer=self.approve(copy.deepcopy(scope));check()
        g.require(type(answer) is dict and set(answer)=={'approved','scope_sha256'} and answer['approved'] is True
            and answer['scope_sha256']==g.digest(scope),'restore_approval_scope')
        expected=copy.deepcopy(original['raw']);changed=[];failure=None;uncertain=False;protection_failure=False
        identity={k:original['source'][k] for k in ('object_id','object_instance','document_epoch')}
        def read():
            snapshot=self.capture();self.registry.resolve(reference_ref,snapshot)
            g.require(all(snapshot['source'][k]==v for k,v in identity.items()),'restore_incarnation_changed')
            return snapshot['raw']
        def result(status):return dict(schema=scope['schema'],event_id=event_id,status=status,
            setter_attempts=attempts,confirmed_changed_setters=confirmed,rollback_setters=rollback,
            physical_count_complete=not uncertain,unknown=uncertain,quarantined=self.quarantined,
            protected_vertices_unchanged=not protection_failure if not uncertain else None,
            final_raw_sha256=g.digest(expected) if not uncertain else None,
            execution_authority=False,reusable_grant=False,reason=failure)
        try:
            g.require(read()==expected,'restore_external_change_before_first_write')
            for i,p in zip(proposal['indices'],proposal['proposed_local_vertices']):
                check();g.require(read()==expected,'restore_external_change')
                if expected['vertices'][i]==p:continue
                before=copy.deepcopy(expected);candidate=copy.deepcopy(expected);candidate['vertices'][i]=p[:]
                self.journal.update(self._ticket,event_id,'setter_pending',scope=scope,next_attempt=attempts+1,
                    confirmed_forward=confirmed,confirmed_rollback=rollback,prior_raw_sha256=g.digest(expected))
                self._write_intent=True;check();self.registry.resolve(reference_ref,original);attempts+=1
                try:self.set_vertex(i,p[:])
                except Exception as exc:failure='setter_exception:'+str(exc)[:100]
                try:observed=read()
                except Exception:
                    uncertain=True;raise
                if observed==candidate:
                    expected=candidate;confirmed+=1;changed.append(i)
                elif observed==before:expected=before
                else:
                    protection_failure=True;uncertain=True;raise ValueError('restore_unexpected_postwrite_state')
                self.journal.update(self._ticket,event_id,'readback',scope=scope,setter_attempts=attempts,
                    confirmed_forward=confirmed,confirmed_rollback=rollback,raw_sha256=g.digest(expected))
                if failure:raise ValueError(failure)
                g.require(observed==candidate,'restore_setter_no_effect')
            g.require(read()==predicted,'restore_final_readback')
            return result('completed')
        except Exception as exc:
            failure=failure or str(exc)[:160]
            if self.journal.poisoned:uncertain=True
            if not uncertain:
                try:
                    # Recovery is part of the original finite attempt budget.
                    # Do not overwrite another actor's changes or write after
                    # expiry, even in the name of recovery.
                    for i in reversed(changed):
                        check();g.require(read()==expected,'restore_changed_before_recovery')
                        g.require(attempts+1<=scope['maximum_setter_attempts'],'restore_attempt_budget')
                        candidate=copy.deepcopy(expected);candidate['vertices'][i]=original['raw']['vertices'][i][:]
                        self.journal.update(self._ticket,event_id,'recovery_pending',scope=scope,next_attempt=attempts+1,
                            confirmed_forward=confirmed,confirmed_rollback=rollback,prior_raw_sha256=g.digest(expected))
                        check();self.registry.resolve(reference_ref,original);attempts+=1
                        error=None
                        try:self.set_vertex(i,candidate['vertices'][i][:])
                        except Exception as exc:error=exc
                        observed=read()
                        if observed==candidate:expected=candidate;rollback+=1
                        else:raise ValueError('restore_recovery_readback')
                        if error:raise ValueError('restore_recovery_setter_exception')
                    g.require(read()==original['raw'],'restore_checkpoint_readback')
                except Exception:
                    uncertain=True
            self.quarantined=uncertain
            return result('unknown_quarantined' if uncertain else 'failed_checkpoint_restored')
