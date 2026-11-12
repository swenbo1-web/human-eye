"""Small host-side register of actual translation setters, never permission.

The embedding Blender host owns this JSON value on its main thread and keeps
it in one driver namespace. Each registered setter is reserved before entry,
then measured independently of engine receipts. Unknown attempts are retained.
This cannot observe arbitrary UI/add-on writes or an external ABA edit. Even
with every registered event confirmed, physical_meter.complete stays False:
an exclusive gateway must separately prove coverage before any goal-budget use.
There is no persistence across Blender restart, automatic retry or history reset.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import json
import math
import re


SCHEMA_VERSION = 'host-motion-ledger-v1'
MAX_GOALS = 16
MAX_EVENTS = 8
MAX_BYTES = 2 * 1024 * 1024
_HEX = re.compile(r'^[a-f0-9]+$')
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
_LIMITS = {'max_setters':8, 'max_step_translation_m':.001,
           'max_total_translation_m':.008, 'max_duration_s':30.}
_BINDING_KEYS = {'host_epoch', 'document_epoch', 'focal_id', 'reference_id', 'object_instances'}
_RECORD_KEYS = {'binding', 'limits', 'started_monotonic', 'deadline_monotonic',
    'last_seen_monotonic', 'initial_world', 'last_world', 'initial_scene_fingerprint',
    'last_scene_fingerprint', 'closed', 'frozen_reason', 'events'}
_EVENT_KEYS = {'event_id', 'kind', 'state', 'before_world', 'requested_world',
    'after_world', 'before_scene_fingerprint', 'after_scene_fingerprint',
    'reserved_monotonic', 'confirmed_monotonic', 'actual_translation_m'}


class HostMotionError(ValueError):
    pass


class HostMotionStopped(HostMotionError):
    pass


def _number(value, label, *, positive=False):
    try: valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError: valid = False
    if not valid or value < 0 or positive and value == 0:
        raise HostMotionError(label + ' must be finite and nonnegative')
    return float(value)


def _vector(value):
    if type(value) is not list or len(value) != 3:
        raise HostMotionError('world position must contain three plain numbers')
    result=[]
    for item in value:
        try: valid=type(item) in (int,float) and math.isfinite(item)
        except OverflowError: valid=False
        if not valid:raise HostMotionError('world position must contain finite numbers')
        result.append(float(item))
    return result


def _identifier(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise HostMotionError('bounded simple identity required')
    return value


def _fingerprint(value):
    if type(value) is not str or len(value)!=64 or not _HEX.fullmatch(value):
        raise HostMotionError('complete scene SHA256 fingerprint required')
    return value


def _binding(value):
    if type(value) is not dict or set(value)!=_BINDING_KEYS:
        raise HostMotionError('complete host/document/object binding required')
    for key,length in (('host_epoch',32),('document_epoch',64)):
        if type(value[key]) is not str or len(value[key])!=length or not _HEX.fullmatch(value[key]):
            raise HostMotionError('invalid ' + key)
    instances=value['object_instances']
    if type(instances) is not dict or not 2<=len(instances)<=256:
        raise HostMotionError('bounded complete object instances required')
    for key,item in instances.items():
        if any(type(v) is not str or not v or len(v)>256 for v in (key,item)):
            raise HostMotionError('invalid object incarnation')
    if len(set(instances.values()))!=len(instances):
        raise HostMotionError('object incarnations must be unique')
    focal,reference=value['focal_id'],value['reference_id']
    if (type(focal) is not str or type(reference) is not str or focal==reference
            or focal not in instances or reference not in instances):
        raise HostMotionError('bound distinct object pair required')
    return copy.deepcopy(value)


def _limits(value):
    if value is None:value={}
    if type(value) is not dict or set(value)-set(_LIMITS):
        raise HostMotionError('unsupported setter limits')
    result={**_LIMITS,**value}
    if type(result['max_setters']) is not int or not 1<=result['max_setters']<=8:
        raise HostMotionError('max_setters outside 1..8')
    for key in ('max_step_translation_m','max_total_translation_m','max_duration_s'):
        result[key]=_number(result[key],key,positive=True)
        if result[key]>_LIMITS[key]:raise HostMotionError(key+' expands host maximum')
    return result


def _encoded(value):
    def plain(item):
        if type(item) is dict:
            if any(type(key) is not str for key in item):raise HostMotionError('JSON keys must be strings')
            for child in item.values():plain(child)
        elif type(item) is list:
            for child in item:plain(child)
        elif item is None or type(item) in (str,bool):pass
        elif type(item) in (int,float):
            if not math.isfinite(item):raise HostMotionError('nonfinite host ledger')
        else:raise HostMotionError('plain JSON host ledger required')
    try:
        plain(value)
        encoded=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
        if len(encoded)>MAX_BYTES:raise HostMotionError('host ledger capacity exhausted')
        return encoded
    except (ValueError,TypeError,OverflowError,RecursionError) as exc:
        if isinstance(exc,HostMotionError):raise
        raise HostMotionError('invalid host ledger JSON') from exc


def _motion(events):
    return sum((Fraction(e['actual_translation_m']) for e in events if e['state']=='confirmed'),Fraction())


def _floor(value):
    result=float(value)
    return math.nextafter(result,0.) if Fraction(result)>value else result


def validate_ledger(state):
    if state=={}:return
    _encoded(state)
    if (type(state) is not dict or set(state)!={'schema_version','records'}
            or state['schema_version']!=SCHEMA_VERSION or type(state['records']) is not dict
            or len(state['records'])>MAX_GOALS):
        raise HostMotionError('invalid host ledger')
    ids=set();open_goals=0
    for goal_id,record in state['records'].items():
        _identifier(goal_id)
        if type(record) is not dict or set(record)!=_RECORD_KEYS:raise HostMotionError('invalid host goal')
        _binding(record['binding']);limits=_limits(record['limits'])
        if record['limits']!=limits:raise HostMotionError('unnormalized host limits')
        start=_number(record['started_monotonic'],'start')
        deadline=_number(record['deadline_monotonic'],'deadline')
        if deadline!=start+limits['max_duration_s'] or deadline<=start:raise HostMotionError('changed host deadline')
        last=_number(record['last_seen_monotonic'],'last_seen')
        if last<start:raise HostMotionError('host clock moved backwards')
        if type(record['closed']) is not bool:raise HostMotionError('invalid closed flag')
        reason=record['frozen_reason']
        if reason is not None and (type(reason) is not str or not reason or len(reason)>256):
            raise HostMotionError('invalid host freeze reason')
        if record['closed'] and reason is not None:raise HostMotionError('frozen host goal cannot be closed')
        if not record['closed']:open_goals+=1
        current=_vector(record['initial_world']);fingerprint=_fingerprint(record['initial_scene_fingerprint'])
        events=record['events']
        if type(events) is not list or len(events)>limits['max_setters']:raise HostMotionError('invalid bounded host events')
        previous=start;pending=False;prefix_motion=Fraction()
        for event in events:
            if type(event) is not dict or set(event)!=_EVENT_KEYS:raise HostMotionError('invalid host event')
            identity=_identifier(event['event_id'])
            if identity in ids:raise HostMotionError('host event identity reused')
            ids.add(identity)
            if event['kind'] not in ('forward','rollback') or event['state'] not in ('reserved','confirmed','unknown','cancelled_before_entry'):
                raise HostMotionError('invalid host event state')
            if pending and event['kind']!='rollback':raise HostMotionError('unconfirmed host event followed by forward setter')
            before=_vector(event['before_world']);requested=_vector(event['requested_world'])
            before_fp=_fingerprint(event['before_scene_fingerprint'])
            if not pending and (before!=current or before_fp!=fingerprint):raise HostMotionError('host event chain changed')
            if before[:2]!=requested[:2]:raise HostMotionError('only world Z setter scope supported')
            requested_motion=math.dist(before,requested)
            if not math.isfinite(requested_motion) or requested_motion>limits['max_step_translation_m']:
                raise HostMotionError('persisted requested step exceeds its admission cap')
            if prefix_motion+Fraction(requested_motion)>Fraction(limits['max_total_translation_m']):
                raise HostMotionError('persisted requested total exceeds its admission cap')
            if event['kind']=='rollback' and reason is None:raise HostMotionError('rollback lacks freeze')
            reserved=_number(event['reserved_monotonic'],'reserved')
            if reserved<previous or reserved>last:raise HostMotionError('invalid host event time')
            if event['kind']=='forward' and reserved>=record['deadline_monotonic']:raise HostMotionError('forward setter reserved after deadline')
            previous=reserved
            if event['state']=='cancelled_before_entry':
                after=_vector(event['after_world']);after_fp=_fingerprint(event['after_scene_fingerprint'])
                cancelled=_number(event['confirmed_monotonic'],'cancelled')
                if (event['kind']!='forward' or cancelled<reserved or cancelled>last
                        or after!=before or after_fp!=before_fp
                        or type(event['actual_translation_m']) not in (int,float)
                        or event['actual_translation_m']!=0):
                    raise HostMotionError('invalid pre-entry cancellation facts')
                previous=cancelled
            elif event['state']=='confirmed':
                after=_vector(event['after_world']);after_fp=_fingerprint(event['after_scene_fingerprint'])
                confirmed=_number(event['confirmed_monotonic'],'confirmed')
                amount=_number(event['actual_translation_m'],'actual_translation_m')
                if confirmed<reserved or confirmed>last or amount!=math.dist(before,after):
                    raise HostMotionError('host physical event accounting changed')
                if confirmed>=deadline and reason is None:raise HostMotionError('late host event lacks freeze')
                prefix_motion+=Fraction(amount)
                previous=confirmed;current=after;fingerprint=after_fp
            else:
                if any(event[key] is not None for key in ('after_world','after_scene_fingerprint','confirmed_monotonic','actual_translation_m')):
                    raise HostMotionError('unconfirmed setter has confirmed facts')
                pending=True
                if event['state']=='unknown' and reason is None:raise HostMotionError('unknown setter must freeze host goal')
        if _vector(record['last_world'])!=current or _fingerprint(record['last_scene_fingerprint'])!=fingerprint:
            raise HostMotionError('host endpoint cache disagrees with physical events')
        if record['closed'] and pending:raise HostMotionError('pending host goal cannot close')
        if reason is None:
            for event in events:
                if event['state']=='confirmed' and (event['actual_translation_m']>limits['max_step_translation_m']
                        or event['before_world'][:2]!=event['after_world'][:2]
                        or math.dist(event['requested_world'],event['after_world'])>1e-6):
                    raise HostMotionError('out-of-scope event lacks freeze')
            if _motion(events)>Fraction(limits['max_total_translation_m']):raise HostMotionError('over-budget facts lack freeze')
    if open_goals>1:raise HostMotionError('multiple open host goals')


def _freeze(state,record,reason):
    if record['closed']:
        raise HostMotionStopped(str(reason)[:256])
    record['frozen_reason']=str(reason)[:256] or 'unknown_host_outcome'
    try:_encoded(state)
    except HostMotionError:record['frozen_reason']='!'
    raise HostMotionStopped(str(reason)[:256])


def _record(state,goal_id):
    validate_ledger(state);_identifier(goal_id)
    try:return state['records'][goal_id]
    except KeyError as exc:raise HostMotionError('unknown host goal') from exc


def _stamp(state,record,binding,now):
    try:
        if _binding(binding)!=record['binding']:_freeze(state,record,'host_document_or_object_identity_changed')
        instant=_number(now,'host monotonic time')
        if instant<record['last_seen_monotonic']:_freeze(state,record,'host_monotonic_clock_moved_backwards')
    except HostMotionStopped:raise
    except HostMotionError:_freeze(state,record,'host_clock_or_binding_unavailable')
    previous=record['last_seen_monotonic'];record['last_seen_monotonic']=instant
    try:_encoded(state)
    except HostMotionError:
        record['last_seen_monotonic']=previous
        _freeze(state,record,'host_timestamp_capacity_exhausted')
    return instant


def _publish(state,candidate):
    validate_ledger(candidate)
    state.clear();state.update(candidate)


def begin_goal(state,goal_id,*,binding,initial_world,scene_fingerprint,now,limits=None):
    validate_ledger(state);_identifier(goal_id)
    binding=_binding(binding);initial_world=_vector(initial_world);scene_fingerprint=_fingerprint(scene_fingerprint)
    normalized=_limits(limits);instant=_number(now,'host monotonic time')
    records=state.get('records',{})
    if goal_id in records:
        record=records[goal_id]
        if (record['binding']!=binding or record['limits']!=normalized or record['initial_world']!=initial_world
                or record['initial_scene_fingerprint']!=scene_fingerprint):
            _freeze(state,record,'host_goal_identity_payload_conflict')
        _stamp(state,record,binding,instant)
        return snapshot(state,goal_id)
    if any(not record['closed'] for record in records.values()):raise HostMotionStopped('previous_host_goal_requires_review_or_close')
    if any(record['binding']['host_epoch']!=binding['host_epoch'] for record in records.values()):
        raise HostMotionStopped('host_epoch_changed_existing_history_cannot_be_reused')
    if len(records)>=MAX_GOALS:raise HostMotionStopped('host_goal_capacity_exhausted')
    deadline=instant+normalized['max_duration_s']
    if not math.isfinite(deadline) or deadline<=instant:raise HostMotionError('host deadline unrepresentable')
    candidate=copy.deepcopy(state or {'schema_version':SCHEMA_VERSION,'records':{}})
    candidate['records'][goal_id]={'binding':binding,'limits':normalized,
        'started_monotonic':instant,'deadline_monotonic':deadline,'last_seen_monotonic':instant,
        'initial_world':initial_world,'last_world':initial_world[:],
        'initial_scene_fingerprint':scene_fingerprint,'last_scene_fingerprint':scene_fingerprint,
        'closed':False,'frozen_reason':None,'events':[]}
    _publish(state,candidate)
    return snapshot(state,goal_id)


def reserve_setter(state,goal_id,event_id,*,binding,before_world,requested_world,
                   before_scene_fingerprint,now,kind='forward'):
    record=_record(state,goal_id);instant=_stamp(state,record,binding,now);_identifier(event_id)
    before=_vector(before_world);requested=_vector(requested_world);fingerprint=_fingerprint(before_scene_fingerprint)
    if kind not in ('forward','rollback'):raise HostMotionError('unsupported setter kind')
    previous=next((event for event in record['events'] if event['event_id']==event_id),None)
    if previous is not None:
        if any(previous[key]!=value for key,value in {'kind':kind,'before_world':before,
                'requested_world':requested,'before_scene_fingerprint':fingerprint}.items()):
            _freeze(state,record,'host_event_identity_payload_conflict')
        if previous['state'] not in ('confirmed','cancelled_before_entry'):
            _freeze(state,record,'pending_or_unknown_setter_must_not_be_retried')
        return {'fresh_reservation':False,'event_id':event_id,'state':previous['state'],'execution_authority':False}
    if record['closed']:raise HostMotionStopped('host_goal_closed')
    if record['frozen_reason'] is not None and kind!='rollback':raise HostMotionStopped(record['frozen_reason'])
    pending=any(event['state'] not in ('confirmed','cancelled_before_entry') for event in record['events'])
    if pending and kind!='rollback':_freeze(state,record,'previous_setter_unconfirmed')
    if kind=='rollback' and not record['events']:raise HostMotionStopped('rollback_requires_preceding_attempt')
    if instant>=record['deadline_monotonic'] and kind!='rollback':raise HostMotionStopped('host_goal_deadline_exhausted')
    if not pending and (before!=record['last_world'] or fingerprint!=record['last_scene_fingerprint']):
        _freeze(state,record,'external_scene_or_pose_change_observed')
    if len(record['events'])>=record['limits']['max_setters']:raise HostMotionStopped('host_setter_cap_exhausted')
    if before[:2]!=requested[:2]:raise HostMotionStopped('only_world_Z_setters_registered')
    requested_motion=math.dist(before,requested)
    if (not math.isfinite(requested_motion) or requested_motion>record['limits']['max_step_translation_m']
            or _motion(record['events'])+Fraction(requested_motion)>Fraction(record['limits']['max_total_translation_m'])):
        raise HostMotionStopped('host_requested_motion_cap_exceeded')
    candidate=copy.deepcopy(state);target=candidate['records'][goal_id]
    if kind=='rollback' and target['frozen_reason'] is None:
        target['frozen_reason']='rollback_requires_review'
    target['events'].append({'event_id':event_id,'kind':kind,'state':'reserved',
        'before_world':before,'requested_world':requested,'after_world':None,
        'before_scene_fingerprint':fingerprint,'after_scene_fingerprint':None,
        'reserved_monotonic':instant,'confirmed_monotonic':None,'actual_translation_m':None})
    _publish(state,candidate)
    return {'fresh_reservation':True,'event_id':event_id,'state':'reserved','execution_authority':False}


def confirm_setter(state,goal_id,event_id,*,binding,after_world,after_scene_fingerprint,now):
    record=_record(state,goal_id);instant=_stamp(state,record,binding,now)
    after=_vector(after_world);fingerprint=_fingerprint(after_scene_fingerprint)
    event=next((item for item in record['events'] if item['event_id']==event_id),None)
    if event is None:_freeze(state,record,'unreserved_host_setter_confirmation')
    if event['state']=='confirmed':
        if event['after_world']!=after or event['after_scene_fingerprint']!=fingerprint:
            _freeze(state,record,'host_setter_confirmation_conflict')
        return snapshot(state,goal_id)
    if event['state']!='reserved':_freeze(state,record,'unknown_setter_cannot_be_recertified')
    amount=math.dist(event['before_world'],after)
    if not math.isfinite(amount):_freeze(state,record,'host_actual_motion_unrepresentable')
    candidate=copy.deepcopy(state);target=candidate['records'][goal_id]
    item=next(item for item in target['events'] if item['event_id']==event_id)
    item.update(state='confirmed',after_world=after,after_scene_fingerprint=fingerprint,
        confirmed_monotonic=instant,actual_translation_m=amount)
    target.update(last_world=after[:],last_scene_fingerprint=fingerprint)
    reasons=[]
    if amount>target['limits']['max_step_translation_m']:reasons.append('actual_step_cap_exceeded')
    if _motion(target['events'])>Fraction(target['limits']['max_total_translation_m']):reasons.append('actual_total_cap_exceeded')
    if event['before_world'][:2]!=after[:2] or math.dist(event['requested_world'],after)>1e-6:reasons.append('actual_setter_outside_requested_world_Z_scope')
    if instant>=target['deadline_monotonic']:reasons.append('setter_confirmation_after_deadline')
    if item['kind']=='rollback':reasons.append('rollback_requires_review')
    if reasons and target['frozen_reason'] is None:target['frozen_reason']=reasons[0]
    _publish(state,candidate)
    return snapshot(state,goal_id)


def cancel_setter(state,goal_id,event_id,*,binding,now):
    """Keep a reserved identity whose forward setter was never entered.

    The trusted host calls this only after its final native-assignment gate
    refused before entry. It is not an inference from endpoint equality.
    A tombstone consumes its reservation slot, but no setter count or path.
    """
    record=_record(state,goal_id);instant=_stamp(state,record,binding,now)
    event=next((item for item in record['events'] if item['event_id']==event_id),None)
    if event is None:_freeze(state,record,'unreserved_host_setter_cancellation')
    if event['state']=='cancelled_before_entry':return snapshot(state,goal_id)
    if event['state']!='reserved' or event['kind']!='forward':
        _freeze(state,record,'entered_or_unknown_setter_cannot_be_cancelled')
    candidate=copy.deepcopy(state);target=candidate['records'][goal_id]
    item=next(item for item in target['events'] if item['event_id']==event_id)
    item.update(state='cancelled_before_entry',after_world=item['before_world'][:],
        after_scene_fingerprint=item['before_scene_fingerprint'],
        confirmed_monotonic=instant,actual_translation_m=0.)
    _publish(state,candidate)
    return snapshot(state,goal_id)


def mark_unknown(state,goal_id,*,reason='host_setter_outcome_unknown',event_id=None):
    record=_record(state,goal_id)
    if record['closed']:raise HostMotionStopped('host_goal_closed')
    if event_id is not None:
        event=next((item for item in record['events'] if item['event_id']==event_id),None)
        if event is None:raise HostMotionError('unknown host event identity')
        if event['state']=='reserved':event['state']='unknown'
    _freeze(state,record,reason)


def observe_scene(state,goal_id,*,binding,world_position,scene_fingerprint,now):
    record=_record(state,goal_id);_stamp(state,record,binding,now)
    if record['closed']:raise HostMotionStopped('host_goal_closed')
    if (_vector(world_position)!=record['last_world']
            or _fingerprint(scene_fingerprint)!=record['last_scene_fingerprint']):
        _freeze(state,record,'external_scene_or_pose_change_observed')
    return snapshot(state,goal_id)


def end_goal(state,goal_id,*,binding,now):
    record=_record(state,goal_id);_stamp(state,record,binding,now)
    if record['frozen_reason'] is not None or any(e['state'] not in ('confirmed','cancelled_before_entry') for e in record['events']):
        raise HostMotionStopped('unconfirmed_or_frozen_host_goal_cannot_close')
    record['closed']=True
    return snapshot(state,goal_id)


def snapshot(state,goal_id,*,after_event_count=0):
    record=_record(state,goal_id)
    if type(after_event_count) is not int or not 0<=after_event_count<=len(record['events']):
        raise HostMotionError('invalid event cursor')
    confirmed=[event for event in record['events'] if event['state']=='confirmed']
    path=_motion(record['events']);limits=record['limits']
    registered_complete=record['frozen_reason'] is None and all(event['state'] in ('confirmed','cancelled_before_entry') for event in record['events'])
    return {'schema_version':SCHEMA_VERSION,'goal_id':goal_id,'binding':copy.deepcopy(record['binding']),
        'scope':'registered_engine_adapter_setters_only','execution_authority':False,
        'all_channels_complete':False,'goal_budget_eligible':False,
        'external_ABA_detection':False,'cross_blender_restart_recovery':False,
        'registered_events_complete':registered_complete,
        'reserved_event_count':len(record['events']),'unknown_event_count':sum(e['state']=='unknown' for e in record['events']),
        'cancelled_before_entry_count':sum(e['state']=='cancelled_before_entry' for e in record['events']),
        'started_monotonic':record['started_monotonic'],'deadline_monotonic':record['deadline_monotonic'],
        'remaining_duration_s':max(0.,record['deadline_monotonic']-record['last_seen_monotonic']),
        'remaining_setters':limits['max_setters']-len(record['events']),
        'remaining_translation_m':_floor(max(Fraction(),Fraction(limits['max_total_translation_m'])-path)),
        'closed':record['closed'],'frozen_reason':record['frozen_reason'],
        'physical_meter':{'complete':False,'actual_setter_count':len(confirmed),
            'actual_cumulative_translation_m':float(path),
            'step_motions_m':[event['actual_translation_m'] for event in record['events'][after_event_count:] if event['state']=='confirmed'],
            'rollback_count':sum(event['kind']=='rollback' for event in confirmed)}}


__all__=['HostMotionError','HostMotionStopped','begin_goal','reserve_setter','confirm_setter',
         'cancel_setter','mark_unknown','observe_scene','end_goal','snapshot','validate_ledger']
