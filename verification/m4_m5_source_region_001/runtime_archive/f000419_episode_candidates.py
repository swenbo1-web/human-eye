"""Disabled-by-default bounded shadow retrieval after hard provenance filters.

No learned weights, execution authority, restored grants, or fallback writes.
Factory/scripted events cannot qualify as independently verified training data.
"""
import copy,math


class CandidateIndex:
    def __init__(self):self._entries={};self._revoked=set()

    def add(self,value):
        keys={'candidate_id','source_event','asset_family','task_family','operator_revision','schema','source_kind',
            'verified_independent','training_positive','features','constraints','proposal','provenance'}
        if type(value) is not dict or set(value)!=keys:raise ValueError('candidate_fields')
        for k in keys-{'verified_independent','training_positive','features','constraints','proposal'}:
            if type(value[k]) is not str or not 1<=len(value[k])<=256:raise ValueError('candidate_identity')
        if value['verified_independent'] is not True or value['training_positive'] is not True or value['source_kind']!='independent_verified':
            raise ValueError('candidate_unqualified_evidence')
        f=value['features']
        if type(f) is not list or not 1<=len(f)<=16 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1e6 for x in f):raise ValueError('candidate_features')
        if type(value['constraints']) is not dict or type(value['proposal']) is not dict:raise ValueError('candidate_payload')
        if (set(value['proposal'])!={'operator','initial_guess'} or type(value['proposal']['operator']) is not str
            or not 1<=len(value['proposal']['operator'])<=128 or type(value['proposal']['initial_guess']) is not list
            or len(value['proposal']['initial_guess'])>16 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1e6 for x in value['proposal']['initial_guess'])):raise ValueError('candidate_proposal_no_authority')
        import json
        if len(json.dumps(value,allow_nan=False).encode())>8192:raise ValueError('candidate_byte_budget')
        if len(self._entries)>=64 or value['candidate_id'] in self._entries or any(v['source_event']==value['source_event'] for v in self._entries.values()):
            raise ValueError('candidate_duplicate_or_full')
        self._entries[value['candidate_id']]=copy.deepcopy(value)

    def revoke(self,candidate_id):
        if candidate_id not in self._entries:raise ValueError('candidate_unknown')
        self._revoked.add(candidate_id)

    def shadow(self,*,task_family,operator_revision,schema,constraints,features,excluded_asset_families=()):
        if type(features) is not list or not 1<=len(features)<=16 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1e6 for x in features):raise ValueError('candidate_query_features')
        rows=[]
        for key,value in self._entries.items():
            # Every discrete support/safety/provenance filter precedes distance.
            if (key in self._revoked or value['task_family']!=task_family or value['operator_revision']!=operator_revision or value['schema']!=schema
                or value['constraints']!=constraints or value['asset_family'] in excluded_asset_families or len(value['features'])!=len(features)):continue
            distance=sum((a-b)**2 for a,b in zip(features,value['features']))
            rows.append((distance,key,value))
        rows.sort(key=lambda row:(row[0],row[1]))
        return dict(status='shadow_only' if rows else 'no_qualified_match',execution_authority=False,learning_enabled=False,
            requires_fresh_observation=True,requires_new_admission=True,automatic_fallback='deterministic_current_solver',
            candidates=[dict(candidate_id=key,distance=d,source_event=v['source_event'],asset_family=v['asset_family'],
                provenance=v['provenance'],proposal=copy.deepcopy(v['proposal'])) for d,key,v in rows[:3]])
