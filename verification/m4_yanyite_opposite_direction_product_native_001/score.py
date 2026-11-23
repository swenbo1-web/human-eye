"""Score original answers and independently verify both opposing Cube witnesses."""

import argparse
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from inspect import getsource
import json
from pathlib import Path
import re
from runpy import run_path
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
FOOT_PATH = HERE.parent/'m1_yanyite_foot_region_image_evidence_consumption_001/score.py'
FOOT = SimpleNamespace(**run_path(str(FOOT_PATH)))
LOW, OLD, ORACLE = FOOT.LOW, FOOT.OLD, FOOT.ORACLE
load, write, pin, require = LOW.load, LOW.write, LOW.pin, LOW.require
BOXES = {
    'negative_y': ((-.08,-.112,0),(.08,-.09,.05)),
    'positive_y': ((-.08,.085,0),(.08,.105,.05)),
}
EXPECTED = {
    'negative_y': (301,225,.8884277344390303,'c5094b937cdc4e22d516efe7cfca999b6ed36fa22956038b693e2d848b60310d'),
    'positive_y': (136,107,.8952636703382715,'c35941e6477bef1347e6e034b0526f792bba981cdc364da2a1b3d969a934eab5'),
}
THRESHOLD = Fraction(223,250)
REQUIRED = tuple(f'{region}.{item}' for region in BOXES for item in OLD.REGIONAL_ITEMS) + ('nearer',)
ROOT = Path('D:/he_m4_yanyite_opposite_direction_product_native_001')
TERMINAL_RUN = Path('D:/he_m1_yanyite_foot_region_image_evidence_consumption_001')
TERMINAL_MEMBER = 'slots/B1/TERMINAL_SOURCE.json'
TERMINAL_SHA = 'f52fc746cea933725ffe5a0c7602b2893914c331b427b83366259b283de1f5fb'
PRODUCT_SOURCE = 'eb6590279920f3c9c4ca07330c0636d6d9bd99860bbed02abaa6e0976321381e'
PRODUCT_SOURCES = {'N1':None,'P1':PRODUCT_SOURCE}


def region_truth(world, triangles, cube, cube_triangles, bounds, expected_plane):
    """Extrema of each affine distance on the selected triangles occur at vertices."""
    faces,vertices = ORACLE.selected_indices(world,triangles,bounds)
    low,high,plane_triangles = ORACLE.boxed_reference(cube,cube_triangles)
    extrema = ([min(world[v][d] for v in vertices) for d in range(3)],
               [max(world[v][d] for v in vertices) for d in range(3)])
    gaps = ([Fraction(extrema[0][d])-Fraction(low[d]) for d in range(3)],
            [Fraction(high[d])-Fraction(extrema[1][d]) for d in range(3)])
    minimum = min(g for row in gaps for g in row)
    require(minimum>0, 'selected_surface_not_strictly_inside_cube')
    nearest = [(plane,axis) for plane in range(2) for axis in range(3) if gaps[plane][axis]==minimum]
    require(nearest==[expected_plane], 'expected_unique_oriented_cube_face_not_found')
    plane,axis = nearest[0]
    witnesses = [v for v in vertices if world[v][axis]==extrema[plane][axis]]
    vertex = witnesses[0]
    point = world[vertex]
    neighbor = list(point)
    neighbor[axis] = (low,high)[plane][axis]
    supporting_source = [i for i in faces if vertex in triangles[i]]
    supporting_cube = [i for i in plane_triangles[plane,axis]
                       if ORACLE.triangle_contains(neighbor,[cube[v] for v in cube_triangles[i]])]
    require(supporting_source and supporting_cube
            and abs(Fraction(neighbor[axis])-Fraction(point[axis]))==minimum, 'closest_pair_does_not_attain_bound')
    witness_set = set(witnesses)
    features = []
    for i in faces:
        ids = [v for v in triangles[i] if v in witness_set]
        if ids:
            features.append({'source_triangle_id':i,'vertex_ids':ids,'vertices_world_m':[world[v] for v in ids]})
    direction = [0,0,0]
    direction[axis] = 2*plane-1
    return {'box_m':bounds,'triangle_ids':faces,'vertex_ids':vertices,'triangle_count':len(faces),
            'vertex_count':len(vertices),'source_point_world_m':point,'reference_point_world_m':neighbor,
            'attaining_vertex':vertex,'all_attaining_selected_vertices':witnesses,'attaining_features':features,
            'source_witness_triangle_ids':supporting_source,'cube_witness_triangle_ids':supporting_cube,
            'distance_m':float(minimum),'distance_exact':[minimum.numerator,minimum.denominator],
            'gaps_by_plane_m':[[float(g) for g in row] for row in gaps], 'direction_world':direction,
            'at_least_0_892_m':minimum>=THRESHOLD}


def truth_regions(world, triangles, cube, cube_triangles):
    regions = {}
    for plane,(name,bounds) in enumerate(BOXES.items()):
        row = region_truth(world,triangles,cube,cube_triangles,bounds,(plane,1))
        faces,vertices,distance,checksum = EXPECTED[name]
        digest = sha256(json.dumps(row['triangle_ids'],separators=(',',':')).encode()).hexdigest()
        require((row['triangle_count'],row['vertex_count'],digest)==(faces,vertices,checksum)
                and abs(row['distance_m']-distance)<=ORACLE.WORLD_ALLOWANCE_M,'frozen_opposite_box_changed/'+name)
        row['ordered_triangle_ids_sha256'] = digest
        regions[name] = row
    negative,positive = regions.values()
    require(not negative['at_least_0_892_m'] and positive['at_least_0_892_m']
            and negative['distance_m']<positive['distance_m']
            and not set(negative['triangle_ids']).intersection(positive['triangle_ids']),
            'opposite_box_threshold_rank_or_disjointness_changed')
    return regions


_verify_terminal = OLD.with_replacements(ORACLE.verify_terminal,truths=truth_regions)


def verify_terminal(terminal, historical, expected=None):
    result = _verify_terminal(terminal,historical,expected)
    require(terminal['display_object_mask']==[True,False], 'hidden_Cube_display_changed')
    result['nearer'] = min(result['regions'],key=lambda name:result['regions'][name]['distance_m'])
    return result


verify_closed_source = OLD.with_replacements(ORACLE.verify_closed_source,verify_terminal=verify_terminal)


def historical_truth():
    snapshot,history = ORACLE.history()
    terminal,native_pins = LOW.archived(TERMINAL_RUN,TERMINAL_MEMBER,TERMINAL_SHA)
    captured,product_pins = LOW.archived(LOW.CURVED_RUN,LOW.CURVED_MEMBER,LOW.CURVED_SHA)
    require(native_pins[0]['bytes']==9_614_533 and
            (captured['source'],captured['coordinate_frame'],captured['unit'])==('blender','world','m'),
            'frozen_opposite_source_or_coordinate_domain_changed')
    for old,mesh,shown in zip(terminal['objects'],captured['meshes'],captured['display_snapshot']['objects'],strict=True):
        require((old['name'],old['object_id'],old['evaluated']['triangles'],old['evaluated']['vertices_world_m'])
                == (mesh['name'],mesh['object_id'],mesh['faces'],mesh['vertices'])
                and shown['host_id']==old['object_id'] and shown['visible_get'] is old['visible_get']
                and all(shown[key]==old['display'][key] for key in ORACLE.DISPLAY),
                'archived_product_and_terminal_geometry_disagree')
    current = verify_terminal(terminal,snapshot)
    prior = [history['matrix64_world'],*(scorer.verify_terminal(terminal,snapshot)['matrix64_regions']
                                       for scorer in (OLD,LOW,FOOT))]
    require(all(not set(region['triangle_ids']).intersection(old['triangle_ids'])
                for region in current['regions'].values() for domain in prior for old in domain.values()),
            'opposite_selection_overlaps_earlier_tasks')
    sources = [*native_pins,*product_pins,*history['histories'],
               *(pin(Path(p)) for p in (__file__,FOOT_PATH,FOOT.LOW_PATH,OLD.__file__,ORACLE.__file__,FOOT.QUALIFY.__file__))]
    for row in sources:
        require(pin(row['path'])=={k:row[k] for k in ('path','bytes','sha256')},'frozen_opposite_source_pin_changed')
    return snapshot,{'passed':True,'source':native_pins[0],'second_capture':product_pins[0],
                     'regions':current['regions'],'matrix64_world':current['matrix64_regions'],
                     'threshold_m':float(THRESHOLD),'nearer':current['nearer'],'asset_sha256':ORACLE.ASSET,
                     'disjoint_prior_regions':sum(len(domain) for domain in prior),'no_overlap_with_old_tasks':True,
                     'actual_Blender_starts':0,'actual_models':0,'source_pins':sources}


def preflight(output):
    _,proof = historical_truth()
    for name,row in proof['regions'].items():
        numeric_pair(row['distance_m'],row['direction_world'],row['source_point_world_m'],row['reference_point_world_m'],row)
        try:
            numeric_pair(row['distance_m'],[0,0,1],row['source_point_world_m'],row['reference_point_world_m'],row)
        except ValueError:
            continue
        raise ValueError('unchanged_legacy_direction_guard_not_rejected/'+name)
    write(output,proof)
    return proof


def numeric_pair(dist, direction, a, b, truth, tolerance=1e-7):
    expected = truth['direction_world']
    require(type(dist) in (int,float) and abs(dist-truth['distance_m'])<=tolerance
            and FOOT.QUALIFY.near_point(direction,expected,tolerance)
            and isinstance(a,(list,tuple)) and isinstance(b,(list,tuple))
            and len(a)==len(b)==3 and all(type(v) in (int,float) for v in (*a,*b)),
            'pair_direction_or_distance_not_current_oriented_Cube_witness')
    boundary = truth['reference_point_world_m']
    projected = [boundary[i] if expected[i] else a[i] for i in range(3)]
    require(FOOT.QUALIFY.near_point(b,projected,tolerance)
            and any(FOOT.QUALIFY.project_to_feature(a,item['vertices_world_m'],tolerance)
                    for item in truth['attaining_features']),
            'pair_not_current_attaining_selected_surface_to_oriented_Cube')


QUALIFY = SimpleNamespace(**{**vars(FOOT.QUALIFY),'numeric_pair':numeric_pair})
_claim = OLD.with_replacements(OLD.check_claim,QUALIFY=QUALIFY)


def distance_in_metres(row):
    raw = row['distance_literal']
    unit = row.get('distance_unit','m')
    require(isinstance(raw,str) and re.fullmatch(r'[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',raw)
            and unit in ('m','mm'),'distance_not_a_literal_metric_value')
    recorded = Decimal(raw)
    factor = 1000 if unit=='mm' else 1
    value = float(recorded)/factor
    require(0<=value<=2,'distance_outside_current_cube')
    resolution = float(Decimal((0,(5,),recorded.as_tuple().exponent-1)))/factor
    return value,max(ORACLE.WORLD_ALLOWANCE_M,1.000002*resolution)


def rounded_distance_matches(row, expected):
    value,allowance = distance_in_metres(row)
    return any(abs(value-sample)<=allowance for sample in expected)


def check_claim(item,row,answer,geometry,frames,claims):
    region,_,criterion = item.partition('.')
    if criterion in ('threshold','distance'):
        quote = row['quote']
        shape = geometry['regions'][region]
        require(isinstance(quote,str) and quote.strip() and quote in answer,'claim_quote_absent_from_actual_final')
        if criterion=='threshold':
            require(row['at_least_0_892_m'] is shape['at_least_0_892_m'],'wrong_literal_threshold_classification')
        else:
            value,_ = distance_in_metres(row)
            require(re.search(r'(?<![\d.])'+re.escape(row['distance_literal'])+r'(?![\d.])',quote)
                    and (value>=float(THRESHOLD)) is shape['at_least_0_892_m']
                    and rounded_distance_matches(row,(shape['distance_m'],geometry['matrix64_regions'][region]['distance_m'])),
                    'distance_rounding_incorrect_or_does_not_resolve_threshold')
        return None
    return _claim(item,row,answer,geometry,frames,claims)


_inner = SimpleNamespace(**{**vars(OLD),'qualify_frames':OLD.with_replacements(OLD.qualify_frames,BOXES=BOXES)})
qualify_frames = OLD.with_replacements(LOW.qualify_frames,OLD=_inner)
_product_measurements = OLD.with_replacements(LOW.product_inputs,BOXES=BOXES,EXPECTED=EXPECTED,
                                              QUALIFY=QUALIFY,PRODUCT_SOURCE=PRODUCT_SOURCE)


def verify_product_measurements(slot,calls,geometry,terminal):
    return {r['attempt']:r for r in _product_measurements(slot,calls,geometry,terminal)} if slot.name=='P1' else {}


def exposure_verifier():
    # Retain the same per-attempt exposure ledger while adapting its one arm label.
    source = getsource(FOOT.score_exposure)
    guard = "slot.name=='B1'"
    distance = "abs(float(claims[region+'.distance']['distance_literal'])-first_fact['distance_m'])<=OLD.POSITION_TOL"
    require(source.count(guard)==source.count(distance)==1,'retained_exposure_anchor_changed')
    scope = dict(FOOT.score_exposure.__globals__,BOXES=BOXES,
                 rounded_distance_matches=rounded_distance_matches,
                 requested_region=OLD.with_replacements(FOOT.requested_region,BOXES=BOXES))
    source = source.replace(guard,"slot.name=='P1'").replace(
        distance,"rounded_distance_matches(claims[region+'.distance'],(first_fact['distance_m'],))")
    exec(compile(source,str(FOOT_PATH),'exec'),scope)
    return scope['score_exposure']


score_slot = OLD.with_replacements(FOOT.score_slot,PRODUCT_SOURCES=PRODUCT_SOURCES,
                                   BOXES=BOXES,REQUIRED=REQUIRED,historical_truth=historical_truth,
                                   verify_closed_source=verify_closed_source,qualify_frames=qualify_frames,
                                   verify_product_measurements=verify_product_measurements,check_claim=check_claim,
                                   score_exposure=exposure_verifier())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight',type=Path)
    mode.add_argument('--slot',type=Path)
    parser.add_argument('--claims',type=Path)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    if args.preflight:
        preflight(args.preflight)
    else:
        require(args.output is not None,'score_output_required')
        try:
            verdict = score_slot(args.slot,args.claims)
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            verdict = {'slot':args.slot.name,'quality_complete':False,'passed_items':0,'total_items':len(REQUIRED),
                       'unverified_items':list(REQUIRED),'error':str(error),'adoption':None}
        write(args.output,verdict)
        print({key:verdict[key] for key in ('slot','quality_complete','passed_items','total_items','error') if key in verdict})
        raise SystemExit(0 if verdict['quality_complete'] or args.claims is None and
                         verdict.get('awaits_literal_claim_transcription') is True else 1)
