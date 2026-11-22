"""Derive only the requested capture scope from an actual archived full-scene readback."""

from copy import deepcopy
from hashlib import sha256
import json


TARGET = 'M16'
REFERENCES = ('M19','M14')


def digest(value):
    return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
                             separators=(',',':'),allow_nan=False).encode()).hexdigest()


def build_selected_capture(complete_capture,reference):
    """Keep the real mesh arrays and version, assigning the two-object replay scope."""
    original = complete_capture['host_identity']
    if (reference not in REFERENCES or original['capture_scope']!='complete_scene_meshes'
            or complete_capture['unit']!='m' or complete_capture['coordinate_frame']!='world'):
        raise ValueError('current_complete_archived_capture_and_registered_pair_required')
    names = (TARGET,reference)
    source = {row['name']:row for row in complete_capture['meshes']}
    if len(source)!=len(complete_capture['meshes']) or len(source)!=21:
        raise ValueError('complete_archived_object_roster_ambiguous')
    rows = sorted((deepcopy(source[name]) for name in names),key=lambda row:row['object_id'])
    for i,row in enumerate(rows,1):
        row['mark_label'] = f'#B{i:04d}'
    selectors = [{'name':name} for name in names]
    selections = {'selectors':selectors,'bindings':[{'object_id':source[name]['object_id'],'name':name}
                   for name in names],'pair_reason':None,'candidate_count':len(source)}
    ids = {row['object_id'] for row in rows}
    host = {**deepcopy(original),'capture_scope':'selected_objects',
            'object_instances':{key:value for key,value in original['object_instances'].items() if key in ids}}
    if host['object_instances'].keys()!=ids:
        raise ValueError('each_replayed_selected_source_requires_current_instance_identity')
    result = {'unit':'m','coordinate_frame':'world','source':complete_capture['source'],'meshes':rows,
              'capture_scope':'selected_objects','host_identity':host,'task_selection':selections}
    result['revision'] = 'blender:'+digest({'scene':result,'scale_length':1.0})
    snapshot = complete_capture.get('display_snapshot')
    if snapshot is not None:
        sidecar = {key:deepcopy(value) for key,value in snapshot.items() if key not in ('objects','sha256')}
        sidecar['objects'] = [deepcopy(row) for row in snapshot['objects'] if row['host_id'] in ids]
        sidecar['sha256'] = digest(sidecar)
        result['display_snapshot'] = sidecar
    result['capture_state'] = {**deepcopy(complete_capture['capture_state']),
                               'selection_key':digest(['task',selectors])}
    return result
