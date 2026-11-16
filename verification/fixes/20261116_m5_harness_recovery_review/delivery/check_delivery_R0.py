"""Independent saved recovery delivery and producer-correlation checks."""
import ast
import base64
import copy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NS = AUTHOR / 'verification/m5_harness_recovery_001'
RUN = Path('D:/he_m5_harness_recovery_001/sessions')
OLD = AUTHOR / 'verification/m5_task_consumption_001/recovery_candidate/owned_runtime.py'
NEW = NS / 'harness/owned_runtime.py'
checks = 0

def check(value, name):
    global checks
    if not value:
        raise AssertionError(name)
    checks += 1

def read(path):
    return json.loads(Path(path).read_bytes())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def jsonl(path):
    return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()]

def function(tree, name):
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)

def same_public_subset(public, private, name):
    if isinstance(public, dict):
        check(isinstance(private, dict), name + '/object')
        for key, value in public.items():
            check(key in private, name + '/' + key + '/present')
            same_public_subset(value, private[key], name + '/' + key)
    else:
        check(public == private, name)

check(sha(OLD) == '371049158c7370a0e29e30992e5b1fe2cd6d6ba726688e77017ca44c27f94318', 'fixed original candidate')
check(sha(NEW) == 'b658da7d89e833cd90dfa65aad95516fc9a98b5936174e940da074ec8ab77810', 'fixed migrated runtime')
oldtree, newtree = ast.parse(OLD.read_text()), ast.parse(NEW.read_text())
for name in ('correlate_archive', 'public_request'):
    check(ast.dump(function(oldtree, name), include_attributes=False) == ast.dump(function(newtree, name), include_attributes=False), 'same core AST/' + name)
assign = {n.targets[0].id: ast.unparse(n.value) for n in newtree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
check(assign['HERE'] == 'Path(__file__).resolve().parent', 'new source-relative HERE')
check(assign['NAMESPACE'] == 'HERE.parent', 'new source-relative namespace')
check(ast.literal_eval(next(n.value.args[0] for n in newtree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'EXTERNAL')) == 'D:/he_m5_harness_recovery_001', 'new external root')
env = {'Path': Path, 'json': json, 'hashlib': hashlib}
exec(compile(ast.Module(body=[function(newtree, 'digest'), function(newtree, 'correlate_archive')], type_ignores=[]), str(NEW), 'exec'), env)
correlate = env['correlate_archive']

frozen_path = Path('D:/hefe/verification/fixes/20261115_m4_selective_002_plan/FROZEN_GEOMETRY.json')
check(sha(frozen_path) == 'decdcc1532f31ceb5c75203705ba5b533520f7a525fa8c6ea0391ba3a1fa36da', 'fixed world geometry')
frozen = {row['name']: {'vertices': [[float(F(x)) for x in p] for p in row['world_vertices_m']], 'faces': row['triangles']} for row in read(frozen_path)['objects']}
near_x = F(frozen['M4_Near']['vertices'][0][0])
expected_distance = F(1) - near_x

def measurement(task, label):
    check(task['result_kind'] == 'task_query' and task['schema_version'] == 'task-query-v3', label + '/task schema')
    check(task['unit'] == 'm' and task['coordinate_frame'] == 'world' and task['pair_order'] == 'A_to_B', label + '/coordinates')
    fact = task['facts']['surface_proximity']
    check(fact['status'] == fact['witness_status'] == fact['direction_status'] == 'measured', label + '/measured')
    value = fact['value']
    check(F(value['distance_m']) == expected_distance, label + '/exact minimum')
    witness = value['nearest_witness']
    a, b = [F(x) for x in witness['a']], [F(x) for x in witness['b']]
    check(a[0] == 1 and 0 <= a[1] <= 1 and 0 <= a[2] <= 1, label + '/target plane and square')
    check(b[0] == near_x and b[1] >= 0 and b[2] >= 0 and b[1]+b[2] <= 1, label + '/near triangle')
    check(a[1:] == b[1:] and a[0]-b[0] == expected_distance, label + '/witness reaches support lower bound')
    check(witness['direction_a_to_b'] == [-1, 0, 0], label + '/direction')
    check([x['name'] for x in task['binding']['objects']] == ['M4_Far_00', 'M4_Near'], label + '/whole object pair')

def world_captures(slot):
    resources, captures = {}, []
    for folder in sorted((slot / 'native/WIRE').iterdir()):
        if not folder.is_dir():
            continue
        response = read(folder / 'RESPONSE.bin')
        body = response.get('result', {}).get('result')
        if not isinstance(body, str) or not body.startswith('HUMAN_EYE_BLENDER_MCP:'):
            continue
        packet = json.loads(body.split(':', 1)[1])['result']
        if packet.get('schema') != 'human-eye-scene-delta-v1':
            continue
        resources.update((r['id'], r) for r in packet['resources'])
        capture = copy.deepcopy(packet['capture'])
        for mesh in capture['meshes']:
            ref = mesh.pop('_scene_resource')
            resource = resources[ref['id']]
            check(resource['revision'] == ref['revision'], 'actual resource version')
            matrix, scale = ref['matrix'], ref['scale']
            vertices = [[(sum(matrix[k][i]*p[i] for i in range(3))+matrix[k][3])*scale for k in range(3)] for p in resource['vertices_local']]
            mesh['vertices'], mesh['faces'] = vertices, resource['faces']
            check(vertices == frozen[mesh['name']]['vertices'], 'actual source vertices/' + mesh['name'])
            check(mesh['faces'] == frozen[mesh['name']]['faces'], 'actual source triangles/' + mesh['name'])
        captures.append(capture)
    check(len(captures) == 4, 'four actual captures')
    return captures

def check_image(slot, private, response, outer_images):
    frame = private['frames'][0]
    check(len(private['frames']) == 1 and frame['view_name'] == 'SCENE', 'one actual scene frame')
    check(sha(frame['image_path']) == frame['image_sha256'] and sha(frame['arrays_path']) == frame['arrays_sha256'], 'current producer bytes')
    png = Path(frame['image_path']).read_bytes()
    images = [b for b in response['result']['content'] if b['type'] == 'image']
    check(len(images) == 1 and base64.b64decode(images[0]['data'], validate=True) == png, 'actual RPC image')
    check(len(outer_images) == 1 and base64.b64decode(outer_images[0]['data'], validate=True) == png, 'actual outer image')
    with np.load(frame['arrays_path'], allow_pickle=False) as stored:
        arrays = {k: stored[k] for k in stored.files}
    check(np.array_equal(np.asarray(Image.open(frame['image_path'])), arrays['color']), 'PNG and RGB')
    check(frame['host_binding_sha256'] == private['binding']['binding_sha256'] and frame['source_revision'] == private['binding']['scene_revision'], 'current frame parent binding')
    objects = sorted(private['binding']['objects'], key=lambda r:r['object_index'])
    names = [o['object_name'] for o in objects]
    counts = [len(frozen[name]['faces']) for name in names]
    offsets = np.cumsum([0]+counts)
    check(arrays['face_patch_offsets'].tolist() == offsets.tolist(), 'actual source face offsets')
    valid = arrays['triangle_ids'] >= 0
    check(np.array_equal(valid, arrays['owners'] >= 0), 'foreground owner/source parity')
    ids = arrays['triangle_ids'][valid]
    check(np.all((ids >= 0)&(ids < offsets[-1])), 'source IDs in actual range')
    check(np.array_equal(np.searchsorted(offsets[1:], ids, side='right'), arrays['owners'][valid]), 'all source IDs to object')
    target = names.index('M4_Far_00')
    mask = (arrays['owners'] == target)&(arrays['triangle_ids'] >= offsets[target]+512)&(arrays['triangle_ids'] <= offsets[target]+513)
    contrast = np.zeros(mask.shape, dtype=bool)
    for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
        ys,ye=max(0,-dy),min(512,512-dy)
        xs,xe=max(0,-dx),min(512,512-dx)
        src=(slice(ys,ye),slice(xs,xe)); dst=(slice(ys+dy,ye+dy),slice(xs+dx,xe+dx))
        delta=arrays['color'][src].astype(np.int32)-arrays['color'][dst].astype(np.int32)
        contrast[src] |= mask[src]&~mask[dst]&(np.sum(delta*delta,axis=2)>=24**2)
    check(int(np.count_nonzero(mask)) == 17131 and int(np.count_nonzero(contrast)) == 538, 'independent witness readability')
    return frame

results=[]
for group in ('A', 'B'):
    slot=RUN/group
    requests=jsonl(slot/'PUBLIC_REQUESTS.jsonl')
    check(len(requests)==5, group+'/five public requests')
    check([r['producer_archive_index'] for r in requests] == [1,None,2,3,4], group+'/saved independent indexes')
    captures=world_captures(slot)
    tools=read(slot/'owner/TOOLS.json')['tools']
    check(len(tools)==4 and all(x['name']=='execute_python' and not x['is_error'] and x['error'] is None for x in tools), group+'/four outer Python calls')
    check([x['internal_public_call_indices'] for x in tools] == [[1,2],[3],[4],[5]], group+'/outer actual public request mapping')
    outer_marks=[]; outer_images={}
    receipts=read(slot/'recovery_calls/RECOVERY_CALLS.json')['requests']
    check(len(receipts)==6, group+'/two metadata and four ordinary calls')
    for i in range(3,7):
        folder=slot/'recovery_calls'/('rpc_'+str(i).zfill(2))
        tx,rx=(folder/'TCP_TX.bin').read_bytes(),(folder/'TCP_RX.bin').read_bytes()
        receipt=receipts[i-1]
        check(hashlib.sha256(tx).hexdigest()==receipt['TX_sha256'] and hashlib.sha256(rx).hexdigest()==receipt['RX_sha256'], group+'/outer raw hashes')
        sent,got=json.loads(tx),json.loads(rx)
        check(sent['args']['message']['params']['name']=='execute_python' and got['ok'] is True, group+'/ordinary bridge endpoint')
        response=got['result']['result']
        check(response.get('isError',False) is False, group+'/outer delivery success')
        wrapped=json.loads(next(b['text'] for b in response['content'] if b['type']=='text'))
        check(wrapped['error'] is None and wrapped['stderr']=='', group+'/ordinary Python result')
        marks=[json.loads(line.split(':',1)[1]) for line in wrapped['stdout'].splitlines() if line.startswith('M5_RECOVERY_PUBLIC:')]
        check(len(marks)==(2 if i==3 else 1), group+'/marker count')
        outer_marks.extend(marks)
        outer_images[i]=[b for b in response['content'] if b['type']=='image']
    check(len(outer_marks)==5, group+'/five actual markers')
    publics=[]; producers=[]; indexes=[]
    for i,(request,mark) in enumerate(zip(requests,outer_marks),1):
        call=slot/'product_calls'/('call_'+str(i).zfill(3))
        raw_request,raw_response=read(call/'REQUEST.json'),read(call/'RESPONSE.json')
        check(raw_request==request['request'] and raw_response==request['response'], group+'/retained actual request and response')
        check(read(request['actual_TX_path'])==raw_request and read(request['actual_RX_path'])==raw_response, group+'/public MCP raw bodies')
        check(sha(request['actual_TX_path'])==request['actual_TX_sha256'] and sha(request['actual_RX_path'])==request['actual_RX_sha256'], group+'/public MCP raw hashes')
        before,after=(call/'ARCHIVE_BEFORE.bin').read_bytes(),(call/'ARCHIVE_AFTER.bin').read_bytes()
        check(hashlib.sha256(before).hexdigest()==request['archive_before_sha256'] and hashlib.sha256(after).hexdigest()==request['archive_after_sha256'], group+'/exact original index snapshots')
        is_error=raw_response['result']['isError']
        check(is_error is (i==2), group+'/original error flag')
        public=json.loads(next(b['text'] for b in raw_response['result']['content'] if b['type']=='text'))
        check(mark['public_result']==public and mark['isError'] is is_error, group+'/unchanged outer public JSON and captured flag')
        entry=correlate(before,after,request['started_ns'],request['closed_ns'],is_error,slot/'product_full')
        indexes.append(None if entry is None else entry['index'])
        check(entry==request.get('producer_archive'), group+'/independently associated producer')
        check('post_reply_binding_error' not in request, group+'/no reply binding failure')
        private=read(entry['path']) if entry else None
        if private is not None:
            if private['result_kind']=='task_query':
                check(public==private, group+'/task original JSON equality')
            else:
                same_public_subset(public['binding'],private['binding'],group+'/observation current public binding')
                for row in public['regions']['rows']:
                    pub=dict(zip(public['regions']['columns'],row))
                    orig=next(r for r in private['facts']['regions'] if r['roi_id']==pub['roi_id'])
                    for key in ('object_index','status','reason','center_world_m','front_direction_world','half_edge_u_world_m','half_edge_v_world_m'):
                        check(pub[key]==orig[key], group+'/actual region projection/'+key)
                if 'task_result' in private:
                    check(public['task_result']==private['task_result'], group+'/joint original task projection')
        else:
            check(i==2 and before==after and public['status']=='error', group+'/pre-service refusal no archive')
        publics.append(public);producers.append(private)
    check(indexes==[1,None,2,3,4], group+'/reconstructed producer sequence')
    for index in (2,3):
        measurement(publics[index], group+'/recovered task')
    check(publics[2]['status']=='observed' and publics[3]['status']=='partial', group+'/observed and partial preserved')
    relation=publics[3]['facts']['closed_solid_relation']
    check(relation['status']=='unknown' and relation['value'] is None and relation['reason']=='closed_solid_too_few_faces', group+'/unknown payload preserved')
    first=check_image(slot,producers[0],requests[0]['response'],outer_images[3])
    last=check_image(slot,producers[4],requests[4]['response'],outer_images[6])
    check(first['image_ref']==last['image_ref'] and first['arrays_sha256']==last['arrays_sha256'], group+'/same current cached frame')
    check(publics[4]['image_delivery']['frame_reuses']==1 and publics[4]['image_delivery']['new_raster_attempts']==0, group+'/cached construction counters')
    if group=='B':
        measurement(publics[4]['task_result'],'B/joint task')
        source=publics[4]['task_result']['binding']['observation_source']
        check(source['parent_binding_sha256']==publics[4]['binding']['binding_sha256'] and source['measurement_scope']=='whole_objects', 'B/current joint source')
        check({o['source_triangle_count'] for o in source['objects']}=={1,514}, 'B/full source face ranges')
    # Reuse real snapshots as two minimal pure failure controls, with no new producer.
    r=requests[2]; c=slot/'product_calls/call_003'
    b=(c/'ARCHIVE_BEFORE.bin').read_bytes();a=(c/'ARCHIVE_AFTER.bin').read_bytes()
    for bad,name in ((b,'missing append'),(b'!'+a,'prefix changed')):
        try:
            correlate(b,bad,r['started_ns'],r['closed_ns'],False,slot/'product_full')
        except (ValueError,json.JSONDecodeError):
            check(True,group+'/pure negative/'+name)
        else:
            check(False,group+'/pure negative/'+name)
    results.append({'group':group,'public_request_count':5,'outer_python_calls':4,'producer_indices':indexes,'isError':[False,True,False,False,False],'actual_captures':len(captures),'unchanged_public_markers':5,'actual_frames_constructed':1,'frame_reused':True})

out={'status':'passed','checks':checks,'sessions':results,'fixed_git':'c041d4f038f72215aa4107a26fcbfd36aa53dd31','new_Blender':0,'new_raster':0,'new_MCP':0,'new_model':0,'scope':'Saved actual delivery, current producer geometry/images and extracted correlation function only.'}
(OUT/'RESULT.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({k:v for k,v in out.items() if k!='sessions'},ensure_ascii=False))
