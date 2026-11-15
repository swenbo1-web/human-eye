"""Independent fixed-source and in-memory M5 integration checks, without rendering."""
import ast
import copy
import hashlib
import json
import math
from contextlib import nullcontext
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
RUN = Path('D:/he_m5_observe_measure_001')
FIXED = '14c8c6b8206dcaecc373bc9aa895cda1d622eee3'
sys.path.insert(0, str(ROOT))
sys.path.append('D:/he_anchor_001/venv/Lib/site-packages')

from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.task_query import task_result
from human_eye_plugin.query_policy import validate_query
from human_eye_plugin.read_context import ReadContext
from human_eye_plugin import active_observation_host as observation
from human_eye_plugin.active_observation import geometry, fingerprint
from human_eye_plugin.active_observation_images import _meshes_from_objects

checks = []
def check(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)

def rejects(name, call, substring):
    try:
        call()
    except (ValueError, KeyError) as exc:
        check(name, substring in str(exc))
    else:
        check(name, False)

def read(path):
    return json.loads(Path(path).read_bytes())

for name in ('live_service', 'active_observation_host', 'auto_router',
             'task_query', 'query_policy', 'live_spatial_mcp'):
    path = 'human_eye_plugin/' + name + '.py'
    blob = subprocess.check_output(['git', 'show', FIXED + ':' + path], cwd=ROOT)
    check('fixed_source_' + name, blob == (ROOT / path).read_bytes())

capture = read(RUN / 'formal/B1/CAPTURE_001.json')
saved = read(RUN / 'formal/B1/producer/call_001/SERVICE_RESULT.json')
base_query = {'mode': 'task', 'objects': [{'name':'M4_Far_00'}, {'name':'M4_Near'}],
              'requested_facts': ['surface_proximity']}
base_capture_hash = hashlib.sha256(json.dumps(capture, sort_keys=True).encode()).hexdigest()
objects, triangles, scene_id = geometry(observation.scene_from_capture(capture))
ids = tuple(mesh.object_id for mesh in _meshes_from_objects(objects))
check('generated_ids_are_geometry_aliases', all(value.startswith('geometry:') for value in ids))

directory = capture['observation_target']['scene_directory']
full_identity = capture['observation_target']['full_scene_identity']
far11 = next(row for row in directory if row['name'] == 'M4_Far_11')
frozen = read('D:/hefe/verification/fixes/20261115_m4_selective_002_plan/FROZEN_GEOMETRY.json')
if 'objects' not in frozen:
    raise AssertionError('expected root frozen world geometry')
from fractions import Fraction
frozen_far = next(row for row in frozen['objects'] if row['name'] == 'M4_Far_11')
far_mesh = {'object_id':far11['object_id'], 'name':far11['name'], 'mark_label':'#extra',
    'vertices': [[float(Fraction(x)) for x in point] for point in frozen_far['world_vertices_m']],
    'faces': frozen_far['triangles']}

class Host:
    timeout_s = 30
    def __init__(self):
        self.calls = []
        self.mutation = lambda value: None
    def capture_task_scene(self, selectors):
        self.calls.append(copy.deepcopy(selectors))
        packet = {'unit':'m','coordinate_frame':'world','source':'blender',
            'revision':'supplement:fixed','capture_scope':'selected_objects',
            'capture_state':copy.deepcopy(capture['capture_state']), 'meshes':[copy.deepcopy(far_mesh)],
            'host_identity': {'schema_version':'1.0','document_epoch':full_identity['document_epoch'],
                'capture_scope':'selected_objects','object_instances':{
                    far11['object_id']:full_identity['object_instances'][far11['object_id']]}},
            'task_selection': {'selectors':copy.deepcopy(selectors), 'bindings':[
                {'object_id':far11['object_id'],'name':far11['name']}], 'pair_reason':None,
                'candidate_count':len(directory)}}
        packet['capture_state']['selection_key'] = 'supplement-different-selection'
        self.mutation(packet)
        return packet
    def capture_active_observation(self, selector, deadline, max_bytes):
        return copy.deepcopy(capture)

host = Host()
service = object.__new__(LiveSpatialService)
service.host = host
service._check_request_budget = lambda stage: 30
view, sources, work = service._prepare_observation_task_view(capture, base_query)
view = service._observation_task_view(view, sources, work, base_query, saved['binding'], ids)
check('present_objects_no_supplement', not host.calls and work['supplemental_capture_calls'] == 0)
check('parent_capture_unchanged', hashlib.sha256(json.dumps(capture, sort_keys=True).encode()).hexdigest() == base_capture_hash)
check('derived_scope_and_no_action', view['capture_scope'] == 'observation_task_objects' and view['execution_authority'] is False)
check('derived_generation_same', all(view['capture_state'][key] == capture['capture_state'][key]
                                   for key in ('instance_id','epoch','revision')))
check('derived_selection_is_distinct', view['capture_state']['selection_key'] != capture['capture_state']['selection_key'])
for source in sources:
    mesh = next(m for m in capture['meshes'] if m['object_id'] == source['object_id'])
    ordered = json.dumps({'vertices':mesh['vertices'],'faces':mesh['faces']},
                        sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    check('source_ordered_hash_' + mesh['name'], source['ordered_geometry_sha256'] == hashlib.sha256(ordered).hexdigest())
    check('source_full_face_range_' + mesh['name'], source['source_triangle_index_ranges'] == [[0,len(mesh['faces'])-1]])
    check('source_real_instance_' + mesh['name'], source['instance_id'] == full_identity['object_instances'][mesh['object_id']])
    check('source_geometry_alias_' + mesh['name'], source['geometry_id'] == ids[source['observation_object_index']])

normalized, meshes, fp = _validated_scene(view, _observation_task_capture=True, _annotate_scene=False)
result = task_result(normalized, meshes, fp, base_query, ReadContext().scene_cache, lambda stage:None)
distance = result['facts']['surface_proximity']['value']['distance_m']
check('independent_main_distance', distance == float(Fraction(2138893713,2147483648)))
check('main_direction', result['facts']['surface_proximity']['value']['nearest_witness']['direction_a_to_b'] == [-1.,0.,0.])
check('task_binding_real_ids', [r['object_id'] for r in result['binding']['objects']] == [
      next(m['object_id'] for m in capture['meshes'] if m['name'] == name) for name in ('M4_Far_00','M4_Near')])
rejects('old_task_capture_rejects_derived_scope', lambda:_validated_scene(view,_task_capture=True), 'capture_scope')
rejects('generic_capture_rejects_derived_scope', lambda:_validated_scene(view), 'capture_scope')

bad_parent = copy.deepcopy(saved['binding'])
bad_parent['objects'][sources[0]['observation_object_index']]['instance_id'] = 'replaced'
rejects('finalize_rejects_instance_replacement', lambda:service._observation_task_view(
    copy.deepcopy(view),copy.deepcopy(sources),dict(work),base_query,bad_parent,ids), 'geometry_mapping_mismatch')
rejects('finalize_rejects_missing_geometry_ids', lambda:service._observation_task_view(
    copy.deepcopy(view),copy.deepcopy(sources),dict(work),base_query,saved['binding'],ids[:-1]), 'geometry_mapping_mismatch')

missing_query = copy.deepcopy(base_query)
missing_query['objects'][1] = {'name':'M4_Far_11'}
mv, ms, mw = service._prepare_observation_task_view(capture, missing_query)
service._observation_task_view(mv, ms, mw, missing_query, saved['binding'], ids)
check('supplement_only_missing_real_object', host.calls == [[{'id':far11['object_id']}]])
missing_source = next(s for s in ms if s['object_id'] == far11['object_id'])
check('supplement_has_no_image_alias', missing_source['observation_object_index'] is None and missing_source['geometry_id'] is None)
mn, mm, mf = _validated_scene(mv, _observation_task_capture=True, _annotate_scene=False)
measurement = task_result(mn,mm,mf,missing_query,ReadContext().scene_cache,lambda stage:None)
check('independent_missing_distance', math.isclose(measurement['facts']['surface_proximity']['value']['distance_m'],math.sqrt(101),rel_tol=1e-15))

mutations = [
 ('revision',lambda p:p['capture_state'].update(revision=p['capture_state']['revision']+1),'generation_changed'),
 ('epoch',lambda p:p['capture_state'].update(epoch=p['capture_state']['epoch']+1),'generation_changed'),
 ('instance',lambda p:p['capture_state'].update(instance_id='new-host'),'generation_changed'),
 ('missing_generation',lambda p:p.pop('capture_state'),'generation_unavailable'),
 ('document',lambda p:p['host_identity'].update(document_epoch='0'*64),'document_epoch_changed'),
 ('object_instance',lambda p:p['host_identity']['object_instances'].update({far11['object_id']:'changed'}),'instance_changed'),
 ('selector',lambda p:p['task_selection'].update(selectors=[{'name':'M4_Far_11'}]),'selection_mismatch'),
 ('name',lambda p:p['meshes'][0].update(name='replacement'),'Task binding'),
]
for label, mutation, error in mutations:
    host.mutation = mutation
    rejects('supplement_rejects_' + label, lambda:service._prepare_observation_task_view(capture,missing_query),error)
host.mutation = lambda p:None

for query in [base_query, {'mode':'task','objects':[{'name':'missing'}],'requested_facts':['aabb']}]:
    val = validate_query({'mode':'active_observation','objects':[{'name':'M4_Far_00'}],'task_query':query})
    check('public_nested_query_valid_' + query['requested_facts'][0],val['task_query'] == query)
for label, q in [
 ('extra',{'mode':'active_observation','unexpected':1}),
 ('nested_wrong_mode',{'mode':'active_observation','task_query':{'mode':'directory','objects':[],'requested_facts':[]}}),
 ('too_many_visual_targets',{'mode':'active_observation','objects':[{'name':'a'},{'name':'b'}]}),
 ('nested_geometry_extra',{'mode':'active_observation','task_query':dict(base_query,geometry={})}),
]:
    rejects('query_rejects_' + label,lambda:validate_query(q),'active_observation')

# Exercise real service cache and M3 with a saved observation result as an image-free stand-in.
# The observer is replaced, so no function can construct a new frame in these controls.
service.config = {'enabled':True}
service.state_path = HERE / 'pure_state.json'
service._read_context = ReadContext()
service._read_source_identity = lambda:(None,None)
service._bind_read_result = lambda result,check:None
service._observation_scope = lambda:nullcontext()
service.record_event = lambda *args,**kwargs:None
observer_calls = []
def saved_observer(current,output_directory,*,include_image,construction_callback,check_budget,_geometry_ids_callback):
    observer_calls.append(include_image)
    _geometry_ids_callback(ids)
    response = copy.deepcopy(saved)
    response.pop('task_result',None)
    response['work'].pop('task_query',None)
    for name in ('task_source_prepare','task_source_finalize','task_measurement'):
        response['stages'].pop(name,None)
    return response

with patch.object(observation,'observe_capture',side_effect=saved_observer):
    cold = service._observe_active_observation('pure',include_image=False,selector={'name':'M4_Far_00'},task_query=base_query)
    warm = service._observe_active_observation('pure',include_image=False,selector={'name':'M4_Far_00'},task_query=base_query)
    ordinary = service._observe_active_observation('pure',include_image=False,selector={'name':'M4_Far_00'})
check('cached_observer_computes_once',observer_calls == [False])
check('cached_measurement_is_same',cold['task_result']['facts'] == warm['task_result']['facts'])
check('warm_measurement_cache_hit',warm['work']['task_query']['result_cache_hit'])
check('ordinary_observation_has_no_task_result','task_result' not in ordinary)
check('result_cache_keeps_private_tuple',all('geometry_ids' not in json.dumps(value)
    for value in (cold,warm,ordinary)))
check('whole_object_scope_explicit',cold['task_result']['binding']['observation_source']['measurement_scope'] == 'whole_objects')

from human_eye_plugin.live_spatial_mcp import project_active_observation_brief
brief = project_active_observation_brief(cold)
check('public_brief_delivers_task',brief is not None and brief['task_result']['facts'] == cold['task_result']['facts'])
for field in ('parent_binding_sha256','parent_source_binding_sha256','parent_capture_scope'):
    modified = copy.deepcopy(cold)
    modified['task_result']['binding']['observation_source'][field] = 'wrong'
    check('brief_rejects_wrong_' + field,project_active_observation_brief(modified) is None)

result = {'status':'pass','checks':len(checks),'fixed_git':FIXED,
          'new_Blender':0,'new_raster':0,'new_models':0,
          'scope':'Pure helpers and real-service/cache/M3 with saved observer stand-in; no live host or new frames.',
          'checks_detail':checks}
(HERE/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='checks_detail'},ensure_ascii=False))
