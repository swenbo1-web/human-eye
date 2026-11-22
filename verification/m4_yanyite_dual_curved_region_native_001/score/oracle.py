"""Independently certify the two selection boxes and the complete Cube surface."""

import argparse
from collections import Counter
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from subprocess import check_output


REPO = Path(__file__).resolve().parents[3]
OLD = REPO/'verification/m4_source_region_display_001'
COMMIT = 'aa45f033'
ARCHIVE = {
    'inputs/evaluated_selected.json':'493ba8fe76d9e3034a1c7393056170e44c84ed1a13209b8d1625f65567d40066',
    'runtime_archive/f000240_ORACLE_initial.json':'470c83108128eae1572f0ad96a902d407c9f8a94bdcd03a63948978086430ff7',
    'runtime_archive/f000271_SOURCE_initial.json':'ab40c007b4ac44c9b9d7392040a08de0bb82583d3c8e31d0de25cc3b9b2b387b',
}
ASSET = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
TARGET = '0135bbc4-c6c7-4003-a402-6f2e0283497d'
REFERENCE = 'Cube'
INDEX_DOMAIN = 'zero_based_object_local_current_evaluated_capture_triangle_rows'
BOXES = {'lower': ((-0.09,0.13,0.505),(0.09,0.18,0.565)),
         'upper': ((-0.09,0.13,0.565),(0.09,0.18,0.63))}
SELECTION_EXPECTED = {'lower': (331,192,24195), 'upper': (311,184,24331)}
DISPLAY = ('hide_get','hide_viewport','hide_render')
MESH_FIELDS = ('vertices','polygons','triangles','triangle_polygons')
WORLD_ALLOWANCE_M = 1e-7


def require(ok, error):
    if not ok:
        raise ValueError(error)


def digest(data):
    return {'bytes':len(data),'sha256':sha256(data).hexdigest()}


def load(path):
    return json.loads(path.read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path':str(path),**digest(path.read_bytes())}


def write(path, document):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(document,stream,ensure_ascii=False,allow_nan=False,indent=2,sort_keys=True)
        stream.write('\n')


def archived():
    values = {}
    pins = []
    for relative, checksum in ARCHIVE.items():
        path = OLD/relative
        blob = path.relative_to(REPO).as_posix()
        raw = path.read_bytes()
        require(sha256(raw).hexdigest() == checksum and raw == check_output(
            ['git','show',f'{COMMIT}:{blob}'],cwd=REPO),'historical_fixed_source_changed/'+relative)
        values[relative] = json.loads(raw)
        pins.append({'path':str(path),**digest(raw),'git':COMMIT})
    selected, prior, snapshot = values.values()
    require(prior['inputs']['snapshot']['sha256'] == pins[-1]['sha256'] and
            prior['source_sha256'] == snapshot['source_sha256'] == ASSET and
            snapshot['source_writes'] == 0 and not snapshot['saved_blend'],'original_assets_not_linked')
    return selected, prior, snapshot, pins


def transform(vertices, matrix, scale):
    require(len(matrix) == 4 and len(matrix[0]) == 4 and matrix[-1] == [0,0,0,1],
            'unsupported_affine_transform')
    return [[(sum(axis[col]*point[col] for col in range(3)) + axis[3])*scale for axis in matrix[:3]]
            for point in vertices]


def near_world(left, right):
    return len(left) == len(right) and all(
        len(a) == len(b) == 3 and all(abs(x-y) <= WORLD_ALLOWANCE_M for x,y in zip(a,b,strict=True))
        for a,b in zip(left,right,strict=True))


def selected_indices(world, triangles, box):
    low, high = box
    valid = [all(low[d] <= p[d] <= high[d] for d in range(3)) for p in world]
    face_ids = [i for i, row in enumerate(triangles) if all(valid[v] for v in row)]
    vertex_ids = sorted({v for i in face_ids for v in triangles[i]})
    require(bool(face_ids) and bool(vertex_ids),'empty_control_selection')
    return face_ids, vertex_ids


def boxed_reference(world, triangles):
    low = [min(p[d] for p in world) for d in range(3)]
    high = [max(p[d] for p in world) for d in range(3)]
    require(low==[-1,-1,-1] and high==[1,1,1] and len(world)==8 and len(triangles)==12,
            'Cube_bounds_or_cardinality_changed')
    corners = {tuple(p) for p in world}
    expect = {(x,y,z) for x in (-1,1) for y in (-1,1) for z in (-1,1)}
    require(corners==expect,'Cube_corner_set_changed')
    covered = {}
    for plane in (0,1):
        for axis in range(3):
            boundary = (low,high)[plane][axis]
            pair = [i for i, face in enumerate(triangles) if all(world[v][axis] == boundary for v in face)]
            require(len(pair)==2,'Cube_face_needs_two_triangles')
            edges = Counter(tuple(sorted((a,b))) for i in pair for a,b in zip(
                triangles[i],triangles[i][1:]+triangles[i][:1],strict=True))
            signature = Counter((count,sum(world[a][d]!=world[b][d] for d in range(3)))
                                for (a,b),count in edges.items())
            require(signature=={(1,1):4,(2,2):1},'Cube_plane_not_completely_tiled')
            covered[plane,axis] = pair
    require(sorted(i for pair in covered.values() for i in pair)==list(range(12)),'Cube_planes_not_disjoint')
    return low, high, covered


def triangle_contains(point, vertices):
    # Exact barycentric signs via the normal's largest projection component.
    p, a, b, c = [tuple(map(Fraction,row)) for row in (point,*vertices)]

    def sub(x,y):
        return tuple(i-j for i,j in zip(x,y,strict=True))

    def cross(x,y):
        return (x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0])

    normal = cross(sub(b,a),sub(c,a))
    axis = max(range(3),key=lambda i: abs(normal[i]))
    if normal[axis]==0 or sum(x*y for x,y in zip(normal,sub(p,a),strict=True))!=0:
        return False
    turns = [cross(sub(y,x),sub(p,x))[axis] for x,y in ((a,b),(b,c),(c,a))]
    return all(turn*normal[axis]>=0 for turn in turns)


def region_truth(world, triangles, cube, cube_triangles, bounds):
    face_ids, vertices = selected_indices(world,triangles,bounds)
    low, high, plane_faces = boxed_reference(cube,cube_triangles)
    range_low = [min(world[v][d] for v in vertices) for d in range(3)]
    range_high = [max(world[v][d] for v in vertices) for d in range(3)]
    gaps = [[Fraction(range_low[d])-Fraction(low[d]) for d in range(3)],
            [Fraction(high[d])-Fraction(range_high[d]) for d in range(3)]]
    require(all(g>0 for row in gaps for g in row),'surface_not_strictly_inside_reference')
    smallest = min(g for row in gaps for g in row)
    planes = [(s,d) for s in range(2) for d in range(3) if gaps[s][d]==smallest]
    require(planes==[(1,2)],'expected_unique_closest_positive_Z_face')
    witnesses = [v for v in vertices if world[v][2]==range_high[2]]
    vertex = witnesses[0]
    apex = world[vertex]
    neighbor = [*apex[:2],high[2]]
    supporting_source = [i for i in face_ids if vertex in triangles[i]]
    supporting_cube = [i for i in plane_faces[1,2] if
                       triangle_contains(neighbor,[cube[v] for v in cube_triangles[i]])]
    require(bool(supporting_source) and bool(supporting_cube)
            and Fraction(neighbor[2])-Fraction(apex[2])==smallest,'attaining_surface_pair_not_proved')
    attaining = {i: [v for v in triangles[i] if v in witnesses] for i in face_ids}
    witness_features = [{'source_triangle_id':i,'vertex_ids':row,'vertices_world_m':[world[v] for v in row]}
                        for i,row in attaining.items() if row]
    return {'box_m':bounds,'triangle_ids':face_ids,'vertex_ids':vertices,
            'triangle_count':len(face_ids),'vertex_count':len(vertices),
            'source_point_world_m':apex,'reference_point_world_m':neighbor,
            'attaining_vertex':vertex,'all_attaining_selected_vertices':witnesses,
            'attaining_features':witness_features,'source_witness_triangle_ids':supporting_source,
            'cube_witness_triangle_ids':supporting_cube,'distance_m':float(smallest),
            'distance_exact':[smallest.numerator,smallest.denominator],
            'gaps_by_plane_m':[[float(value) for value in row] for row in gaps],
            'direction_world':[0,0,1],'at_least_0_40_m':smallest>=Fraction(2,5)}


def truths(world, triangles, cube, cube_triangles):
    regions = {name: region_truth(world,triangles,cube,cube_triangles,bounds)
               for name,bounds in BOXES.items()}
    for name, row in regions.items():
        require((row['triangle_count'],row['vertex_count'],row['attaining_vertex'])==SELECTION_EXPECTED[name],
                'frozen_box_counts_or_attaining_source_changed/'+name)
    require(regions['lower']['at_least_0_40_m'] and not regions['upper']['at_least_0_40_m']
            and regions['upper']['distance_m']<regions['lower']['distance_m'],'threshold_or_order_changed')
    return regions


def history():
    selected, prior, snapshot, pins = archived()
    require(snapshot['frame']==1 and snapshot['subframe']==0 and snapshot['unit_scale']==1
            and snapshot['display_snapshot']['view_layer']['name']=='ViewLayer','historical_current_context_changed')
    objects = {o['name']:o for o in snapshot['objects']}
    require(set(objects)=={TARGET,REFERENCE},'historical_object_roster_changed')
    target, ref = (objects[name] for name in (TARGET,REFERENCE))
    target_mesh, ref_mesh = target['evaluated'],ref['evaluated']
    require(target['display']['visible_get'] is True and ref['display']['visible_get'] is False
            and ref['display']['hide_get'] is True,'original_display_premise_changed')
    require(selected['object_name']==target['name'] and selected['matrix_world']==target['matrix_world']
            and selected['vertices_object']==target_mesh['vertices']
            and selected['triangles']==target_mesh['triangles']
            and selected['polygon_ids_by_triangle']==target_mesh['triangle_polygons']
            and selected['vertices_world']==target_mesh['vertices_world_m'],'exact_historical_mesh_binding_changed')
    world64=transform(target_mesh['vertices'],target['matrix_world'],snapshot['unit_scale'])
    cube64=transform(ref_mesh['vertices'],ref['matrix_world'],snapshot['unit_scale'])
    native=target_mesh['vertices_world_m']
    require(near_world(native,world64) and cube64==ref_mesh['vertices_world_m'],'Blender_and_binary64_world_inconsistent')
    verified = truths(native,target_mesh['triangles'],cube64,ref_mesh['triangles'])
    other = truths(world64,target_mesh['triangles'],cube64,ref_mesh['triangles'])
    require(all((r['triangle_ids'],r['vertex_ids']) == (other[k]['triangle_ids'],other[k]['vertex_ids'])
                for k,r in verified.items()),'two_domains_select_different_source_rows')
    require(all(ref_mesh['triangles'][rec['evaluated_triangle_row']]==rec['evaluated_vertex_ids']
                and [cube64[v] for v in rec['evaluated_vertex_ids']]==rec['evaluated_vertices_world_m']
                for rec in prior['reference']['triangle_mapping']), 'original_Cube_reference_rows_differ')
    return snapshot, {'asset_sha256':ASSET,'histories':pins,'threshold_m':0.40,'nearer':'upper',
                      'blender_world':verified,'matrix64_world':other,
                      'both_world_domains_same_ordered_source_ids':True}


def verify_terminal(terminal, historical, expected=None):
    context = terminal['source']
    require(context['kind']=='actual_owned_Blender_evaluated_mesh' and context['asset_sha256']==ASSET
            and context['frame']==historical['frame'] and context['subframe']==historical['subframe']
            and context['scale_length']==historical['unit_scale'] and context['view_layer']=='ViewLayer'
            and context['unit_settings']==historical['unit_settings']
            and context['source_index_domain']==INDEX_DOMAIN,'terminal_asset_or_context_differs')
    original = {o['name']:o for o in historical['objects']}
    objects = terminal['objects']
    require(len(objects)==2 and {o['name'] for o in objects}==set(original),'terminal_mesh_roster_changed')
    offsets = [0]
    transforms = {}
    for o in objects:
        old = original[o['name']]
        require(o['object_id']==old['host_id'] and o['mesh_name']==old['mesh_name']
                and o['parent']==old['parent'] and o['matrix_world']==o['native_matrix_world']==old['matrix_world']
                and o['visible_get'] is old['display']['visible_get']
                and all(o['display'][key]==old['display'][key] for key in DISPLAY),
                'terminal_mesh_identity_transform_or_display_changed/'+o['name'])
        for kind in ('native','evaluated'):
            now, before = o[kind],old[kind]
            require(all(now[f]==before[f] for f in MESH_FIELDS),'terminal_ordered_mesh_data_changed/'+o['name']+'/'+kind)
            calculated = transform(now['vertices'],o['matrix_world'],context['scale_length'])
            require(near_world(now['vertices_world_m'],calculated) and near_world(now['vertices_world_m'],before['vertices_world_m']),
                    'terminal_mesh_world_metric_changed/'+o['name']+'/'+kind)
            if kind=='evaluated':
                transforms[o['name']] = calculated
        offsets.append(offsets[-1]+len(o['evaluated']['triangles']))
    require(offsets==terminal['source_face_offsets']
            and terminal['display_object_mask']==[item['visible_get'] for item in objects],
            'terminal_offset_or_display_mask_changed')
    target, cube = ({o['name']:o['evaluated'] for o in objects}[name] for name in (TARGET,REFERENCE))
    truth = truths(target['vertices_world_m'],target['triangles'],cube['vertices_world_m'],cube['triangles'])
    matrix = truths(transforms[TARGET],target['triangles'],transforms[REFERENCE],cube['triangles'])
    for choice, regions in (('terminal_world',truth),('matrix64_world',matrix)):
        for name,v in regions.items():
            require((v['triangle_ids'],v['vertex_ids']) == (matrix[name]['triangle_ids'],matrix[name]['vertex_ids']),
                    'terminal_coordinate_domains_select_different_rows/'+choice+'/'+name)
            if expected is not None:
                known = expected['matrix64_world'][name]
                require(v['triangle_ids']==known['triangle_ids'] and v['vertex_ids']==known['vertex_ids']
                        and abs(v['distance_m']-known['distance_m'])<=WORLD_ALLOWANCE_M,
                        'terminal_selection_not_registered_source/'+name)
    return {'source':context,'meshes':[{'name':o['name'],'object_id':o['object_id'],'instance_id':o['instance_id'],
                                       'visible_get':o['visible_get']} for o in objects],
            'source_face_offsets':offsets,'regions':truth,'matrix64_regions':matrix,'nearer':'upper'}


def verify_closed_source(slot,historical,expected):
    terminal_path=slot/'TERMINAL_SOURCE.json'
    device_path=slot/'DEVICE_EVIDENCE.json'
    result_pin=pin(slot/'SLOT_RESULT.json')
    result, publication, device = (load(slot/name) for name in ('SLOT_RESULT.json','SLOT_PUBLICATION.json','DEVICE_EVIDENCE.json'))
    terminal=load(terminal_path)
    source=verify_terminal(terminal,historical,expected)
    receipt=device['terminal_source']
    before=load(slot/'initial_capture/TERMINAL_SOURCE.json')
    verify_terminal(before,historical,expected)
    require(before['source']==terminal['source'] and before['objects']==terminal['objects'],
            'initial_and_terminal_current_meshes_not_equal')
    require(result['label']==slot.name==publication['label']==device['label'] and
            publication['result_sha256']==result_pin['sha256'] and
            result['status']==publication['status']=='completed' and
            result['closure_verification']['passed'] and result['independent_before_after']['passed'] and
            result['asset_sha256']==device['asset_sha256']==source['source']['asset_sha256'] and
            result['terminal_source']==receipt and receipt['status']=='complete' and
            receipt['worker']['pid']==source['source']['pid'] and pin(terminal_path)==
            {key:receipt[key] for key in ('path','bytes','sha256')},'terminal_receipt_or_actual_close_mismatch')
    copied=Path(source['source']['asset_copy']).resolve(strict=True)
    require(copied.is_relative_to(slot) and pin(copied)['sha256']==ASSET,'slot_asset_copy_is_not_original_bytes')
    return source,terminal,device


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    args=cli.add_mutually_exclusive_group(required=True)
    args.add_argument('--historical-only',action='store_true')
    args.add_argument('--slot',type=Path)
    cli.add_argument('--output',type=Path,required=True)
    opt=cli.parse_args()
    snapshot, verdict=history()
    if opt.slot:
        source,_,_=verify_closed_source(opt.slot.resolve(strict=True),snapshot,verdict)
        verdict={'same_historical_source':True,'current':source}
    write(opt.output,verdict)
