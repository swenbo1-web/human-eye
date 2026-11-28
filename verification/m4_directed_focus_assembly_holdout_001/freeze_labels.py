"""Freeze held-out task-face truth from archived historical request and capture bytes."""

import argparse
import ast
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile

PLAN_SHA256 = '30c6e127ff5c484e7b6bfc28aecd3b8ef106affdccde7553e5c6a9de49cee7ea'
SLOT = 'slots/P1'
DOMAIN = 'zero_based_object_local_current_evaluated_capture_triangle_rows'
ASSETS = {
    'rail': ('m4_rail_source_region_product_native_001', 'a374e3dcde0334991a63c15d594604c068b0b614',
             'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce',
             (('M19', 'M14'), ('M21', 'M13'))),
    'assembly': ('m4_assembly_cross_asset_product_native_001', '4bc6b7d6da32a4204f57465f4311723e0836faff',
                 '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85',
                 (('N19', 'N14'), ('N25', 'N07'))),
}
PREFIX = 'HUMAN_EYE_BLENDER_MCP:'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return {'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}


def canonical(value):
    """JSON retains binary64 round-trip values, including the sign of zero."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(',', ':')).encode('utf8')


class Archive:
    def __init__(self, root, spec, repo):
        name, commit, _, _ = spec
        self.root = (root / ('he_' + name)).resolve(strict=True)
        self.record = subprocess.check_output(
            ['git', '-C', str(repo), 'show', f'{commit}:verification/{name}/RESULT.json'])
        result = json.loads(self.record)
        evidence = result.get('raw_archive') or result['raw_local_archive']
        pin = evidence.get('archive', evidence)
        self.path = self.root/'sealed/ORIGINAL_RUNTIME.zip'
        self.zip_pin = digest(self.path.read_bytes())
        require(self.zip_pin == {k: pin[k] for k in ('bytes', 'sha256')}, 'historical_zip_pin_changed')
        index = (self.root/'sealed/RAW_INDEX.json').read_bytes()
        self.index_pin = digest(index)
        if 'index' in evidence:
            require(self.index_pin == {k: evidence['index'][k] for k in ('bytes', 'sha256')},
                    'historical_index_pin_changed')
        self.index = json.loads(index)
        require(self.zip_pin == {k: self.index['archive'][k] for k in ('bytes', 'sha256')},
                'historical_index_zip_binding_changed')
        self.member_count = evidence.get('member_count', evidence.get('members'))
        self.used = {}

    def __enter__(self):
        self.archive = ZipFile(self.path)
        try:
            members = self.archive.namelist()
            require(len(members) == self.index['member_count'] == self.member_count
                    and len(set(members)) == len(members)
                    and set(members) == self.index['members'].keys(), 'historical_zip_member_set_changed')
            return self
        except BaseException:
            self.archive.close()
            raise

    def __exit__(self, *_):
        self.archive.close()

    def take(self, name):
        path = (self.root/name).resolve(strict=True)
        require(path.is_relative_to(self.root) and path.relative_to(self.root).as_posix() == name,
                'historical_member_not_canonical')
        raw = path.read_bytes()
        pin = digest(raw)
        require(pin == self.index['members'][name] and raw == self.archive.read(name),
                'historical_member_mismatch/' + name)
        self.used[name] = pin
        return raw

    def load(self, name):
        return json.loads(self.take(name))

    def pin(self, name):
        return {'path': (self.root/name).as_posix(), **self.used[name]}


def historical_capture(run, position, meter, native_index, resources):
    n = position + 1
    stem = f'{SLOT}/native/WIRE/{n:03d}'
    tx, rx = (run.take(stem+'/'+name) for name in ('REQUEST.bin', 'RESPONSE.bin'))
    request, response = map(json.loads, (tx, rx))
    stdout = response['result']['result']
    require(response['status']=='success' and response['result']['executed'] is True
            and stdout.startswith(PREFIX) and stdout.endswith('\n'),
            'historical_host_rpc_not_complete')
    host = json.loads(stdout[len(PREFIX):])
    code = ast.parse(request['params']['code'])
    literal, = [row.value for row in code.body if isinstance(row, ast.Assign)
                and [ast.unparse(target) for target in row.targets] == ['_request']]
    require(isinstance(literal, ast.Call) and ast.unparse(literal.func)=='_json.loads'
            and len(literal.args)==1, 'historical_native_command_literal_changed')
    sent = json.loads(ast.literal_eval(literal.args[0]))
    wire = native_index[n]
    require(request['type']=='execute_code' and sent['command']==meter['command']=='capture'
            and sent['id']==host['id']==meter['host_request_id'] and meter['outcome']=='success'
            and wire['response_sendall_completed']
            and len(tx)==wire['request_bytes']==meter['request_bytes']
            and len(rx)==wire['response_attempted_bytes'],
            'historical_native_rpc_not_bound_to_query')
    payload = host['result']
    require(payload['schema']=='human-eye-scene-delta-v1', 'historical_scene_capture_schema_changed')
    for resource in payload['resources']:
        resources[(resource['id'], resource['revision'])] = resource
    return payload['capture']


def world_geometry(capture, terminal, cache):
    source = terminal['source']
    rows = terminal['objects']
    displays = capture['display_snapshot']
    require(capture['coordinate_frame']=='world' and capture['unit']=='m'
            and source['source_index_domain']==DOMAIN and
            displays['view_layer']=={'name':source['view_layer'],'instance_id':source['view_layer_id']},
            'historical_current_layer_or_frame_domain_changed')
    mesh_list = capture['meshes']
    require([row['object_id'] for row in rows]==[mesh['object_id'] for mesh in mesh_list],
            'historical_independent_terminal_mesh_order_changed')
    visible = {row['host_id']: row for row in displays['objects']}
    require(len(visible)==len(rows), 'historical_display_roster_changed')
    for mesh, record in zip(mesh_list, rows, strict=True):
        row = mesh['_scene_resource']
        resource = cache[row['id'],row['revision']]
        geometry = record['evaluated']
        matrix, scale = row['matrix'], row['scale']
        points = resource['vertices_local']
        faces = resource['faces']
        require(mesh['name']==record['name'] and canonical(matrix)==canonical(record['matrix_world'])
                and scale==source['scale_length'] and canonical(points)==canonical(geometry['vertices'])
                and faces==geometry['triangles'], 'historical_vertex_or_source_row_order_changed/'+record['name'])
        world = [[(sum(matrix[i][j]*v[j] for j in range(3))+matrix[i][3])*scale for i in range(3)] for v in points]
        require(canonical(world)==canonical(geometry['vertices_world_m']),
                'historical_world_transform_changed/'+record['name'])
        display = visible[record['object_id']]
        require(display['instance_id']==record['instance_id'] and display['visible_get'] is record['visible_get']
                and all(display[k] is record['display'][k] for k in ('hide_get','hide_viewport','hide_render')),
                'historical_instance_or_display_changed/'+record['name'])
    return rows


def selected_indices(vertices, triangles, box):
    low, high = ([Fraction(v) for v in box[end]] for end in ('min', 'max'))
    require(len(low)==len(high)==3 and all(a<=b for a,b in zip(low,high,strict=True)), 'bad_historical_closed_box')
    points = [[Fraction(v) for v in row] for row in vertices]
    inside = [all(lo<=v<=hi for lo,v,hi in zip(low,vertex,high,strict=True)) for vertex in points]
    require(all(len(face)==3 and all(type(i) is int and 0<=i<len(points) for i in face) for face in triangles),
            'historical_triangle_source_indices_invalid')
    indices = [i for i, face in enumerate(triangles) if all(inside[j] for j in face)]

    def nondegenerate(i):
        a, b, c = [points[j] for j in triangles[i]]
        u, v = [[y-x for x,y in zip(a,row,strict=True)] for row in (b,c)]
        return any(u[j]*v[k]-u[k]*v[j] for j,k in ((0,1),(1,2),(2,0)))

    eligible = [i for i in indices if nondegenerate(i)]
    require(eligible, 'historical_closed_box_has_no_nondegenerate_source_row')
    return indices, min(eligible)


def asset_labels(key, archive, repo):
    spec = ASSETS[key]
    _, commit, asset_sha256, identities = spec
    with Archive(archive, spec, repo) as run:
        asset, initial, terminal = (
            SLOT+'/'+name for name in ('native/input.blend','initial_capture/TERMINAL_SOURCE.json','TERMINAL_SOURCE.json'))
        require(digest(run.take(asset))['sha256']==asset_sha256,'wrong_historical_asset')
        before, end = run.load(initial), run.load(terminal)
        close = run.load(f'{SLOT}/SLOT_RESULT.json')
        pub = run.load(f'{SLOT}/SLOT_PUBLICATION.json')
        process = run.load(f'{SLOT}/mcp/HELD_CLOSE.json')
        require(close['status']==pub['status']=='completed'
                and close['closure_verification']['passed'] and close['independent_before_after']['passed']
                and close['asset_sha256']==before['source']['asset_sha256']==end['source']['asset_sha256']==asset_sha256
                and canonical(before['objects'])==canonical(end['objects'])
                and close['terminal_source']['sha256']==run.used[terminal]['sha256']
                and close['initial_source']['sha256']==run.used[initial]['sha256']
                and pub['result_sha256']==run.used[f'{SLOT}/SLOT_RESULT.json']['sha256']
                and process['confirmed'] and process['production_eof_and_exit_verified'] and process['exit_code']==0,
                'historical_capture_before_after_or_closure_changed')

        native_index = {row['sequence']:row for row in run.load(f'{SLOT}/native/WIRE/INDEX.json')}
        meter = run.load(f'{SLOT}/mcp_io/REAL_HOST_STAGES.json')['requests']
        journal = [json.loads(line) for line in run.take(f'{SLOT}/PUBLIC_REQUESTS.jsonl').splitlines()]
        resources = {}
        tasks = {}
        for pos, ((target, reference), entry, timing) in enumerate(zip(identities,journal,meter,strict=True),1):
            mcp = f"{SLOT}/mcp/rpc_{entry['receipt']['index']:02d}"
            tx, rx = [run.load(mcp+'/'+which+'.bin') for which in ('TX','RX')]
            raw = tx['params']['arguments']
            query = raw['query']
            require(entry['request']==tx and entry['response']==rx and tx['id']==entry['id']==rx['id']
                    and tx['method']=='tools/call' and tx['params']['name']=='human_eye_scene_observe'
                    and raw['include_image'] is True and rx['result']['isError'] is False
                    and query['mode']=='source_region' and query['region']['object']=={'name':target}
                    and query['reference']=={'name':reference} and query['requested_facts']==['surface_proximity'],
                    'historical_registered_task_request_or_wire_changed')
            host = historical_capture(run,pos,timing,native_index,resources)
            times = timing['stages']['host_request']
            require(host['capture_state']==timing['decoder']['capture_state']
                    and entry['started_ns']<=times['started_ns']<=times['closed_ns']<=entry['client_returned_ns'],
                    'historical_native_capture_crossed_query_window')
            roster = world_geometry(host,end,resources)
            obj_idx, = [i for i,row in enumerate(roster) if row['name']==target]
            ref_idx, = [i for i,row in enumerate(roster) if row['name']==reference]
            obj = roster[obj_idx]
            geometry = obj['evaluated']
            box = query['region']['world_box_m']
            indices, explicit = selected_indices(geometry['vertices_world_m'], geometry['triangles'], box)
            p = f'{SLOT}/product_full/call_{pos:03d}/SERVICE_RESULT.json'
            producer = run.load(p)
            fact, region_ref = producer['facts']['region'], producer['region_ref']
            require(entry['producer_archive']['sha256']==run.used[p]['sha256']
                    and producer['binding']['capture_state']==host['capture_state']
                    and fact['host_id']==region_ref['host_id']==obj['object_id']
                    and fact['instance_id']==region_ref['instance_id']==obj['instance_id']
                    and fact['object_name']==target and fact['index_domain']==DOMAIN
                    and fact['source_triangle_indices']==region_ref['source_triangle_indices']==indices
                    and fact['triangles_source_vertices']==[geometry['triangles'][i] for i in indices]
                    and producer['task_result']['reference']['object_id']==roster[ref_idx]['object_id'],
                    'historical_published_source_label_disagrees_with_independent_box')
            tasks[target] = {
                'asset':key, 'target':target, 'reference':reference, 'host_id':obj['object_id'],
                'object_index':obj_idx, 'total_source_triangles':len(geometry['triangles']),
                'source_triangle_indices':indices, 'explicit_source_triangle_index':explicit,
                'world_box_m':box, 'source_index_domain':DOMAIN, 'prior_request_id':entry['id'],
                'prior_mcp_tx_sha256':run.used[mcp+'/TX.bin']['sha256'],
                'prior_mcp_rx_sha256':run.used[mcp+'/RX.bin']['sha256'],
                'prior_producer_sha256':run.used[p]['sha256'],
                'prior_native_response_sha256':run.used[f'{SLOT}/native/WIRE/{pos+1:03d}/RESPONSE.bin']['sha256'],
                'target_source_geometry_sha256':digest(canonical(geometry))['sha256'],
            }
        result = {
            'historical_commit':commit, 'asset':run.pin(asset), 'terminal':run.pin(terminal),
            'initial':run.pin(initial), 'historical_result':digest(run.record), 'archive':run.zip_pin,
            'archive_index':run.index_pin, 'zip_member_count':run.member_count, 'used_archive_members':run.used,
        }
        return result, tasks


def freeze(archive, repo, plan, out):
    require(digest(plan.read_bytes())['sha256']==PLAN_SHA256, 'administrative_plan_hash_mismatch')
    require(out.parent.resolve(strict=True)==plan.parent.resolve(strict=True), 'label_output_outside_preflight')
    asset_pins, tasks = {}, {}
    for key in ASSETS:
        asset_pins[key], cases = asset_labels(key,archive,repo)
        tasks.update(cases)
    labels = {
        'schema':'human-eye-directed-focus-assembly-holdout-labels-v1',
        'frozen_before_formal_automatic_calls':True,
        'plan_sha256':PLAN_SHA256,
        'independent_rule':'all_world_vertices_in_closed_historical_box_and_exact_binary64_nondegenerate_minimum',
        'task_order':list(tasks), 'assets':asset_pins, 'tasks':tasks,
    }
    require(not (plan.parent.parent/'slots').exists(), 'formal_slots_already_exist')
    raw=(json.dumps(labels,sort_keys=True,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode('utf8')
    with out.open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'labels':digest(raw),'cases':len(tasks),'used_archive_members':sum(
        len(item['used_archive_members']) for item in asset_pins.values())},sort_keys=True))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('archive','repo','plan','out'):
        parser.add_argument('--'+arg,required=True,type=Path)
    args=parser.parse_args()
    freeze(args.archive,args.repo,args.plan,args.out)
