"""Exercise the independent scorer on actual baseline stdio and derived certificates."""

from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
D = run_path(str(NS/'checks/evidence.py'))
M = run_path(str(NS/'checks/matrix.py'))
G,sets = D['G'],D['F']
require = D['require']
BASE = sets['EXTERNAL']/'preflight_01_baseline_evidence'


def rejects(callback,reason):
    try:
        callback()
    except ValueError as error:
        require(str(error)==reason,'certificate_checker_rejected_for_another_reason/'+str(error))
        return reason
    raise ValueError('invalid_certificate_was_accepted/'+reason)


def feature_attainer(left,right,shown):
    """Find a rational vertex-face/edge pair reproducing the two displayed points."""
    dot,sub,cross,at = (G[key] for key in ('dot','sub','cross','at'))
    pairs = []
    for vertices,triangle,flip in ((left,right,False),(right,left,True)):
        a,b,c = triangle
        normal = cross(sub(b,a),sub(c,a))
        nn = dot(normal,normal)
        if nn:
            for p in vertices:
                q = at(p,normal,-dot(sub(p,a),normal)/nn)
                if G['exactly_on'](q,triangle):
                    pairs.append((q,p) if flip else (p,q))
    for a,b in G['edges'](left):
        for c,d in G['edges'](right):
            u,v,w = sub(b,a),sub(d,c),sub(a,c)
            uu,uv,vv,uw,vw = (dot(x,y) for x,y in ((u,u),(u,v),(v,v),(u,w),(v,w)))
            det = uu*vv-uv*uv
            if det:
                t,s = (uv*vw-vv*uw)/det,(uu*vw-uv*uw)/det
                if 0<=t<=1 and 0<=s<=1:
                    pairs.append((at(a,u,t),at(c,v,s)))
            for p,c0,d0,swap in ((a,c,d,False),(b,c,d,False),(c,a,b,True),(d,a,b,True)):
                line = sub(d0,c0)
                denom = dot(line,line)
                t = min(F(1),max(F(0),dot(sub(p,c0),line)/denom)) if denom else F(0)
                q = at(c0,line,t)
                pairs.append((q,p) if swap else (p,q))
    candidates = {tuple(pair) for pair in pairs}
    allowed = [pair for pair in candidates if [[float(x) for x in row] for row in pair]==shown]
    require(len(allowed)==1,'independent_current_face_features_did_not_uniquely_match_both_rounded_points')
    return list(map(lambda row:list(map(str,row)),allowed[0]))


def derived_extension(label,capture,body):
    names = sets['CASES'][label][1]
    lookup = {row['name']:row for row in capture['meshes']}
    surfaces = [G['surface'](lookup[n]) for n in names]
    witness = D['OLD']['witnesses'](body)
    reverse = {'linear_m03_m01':'linear_m01_m03','linear_m20_m16':'linear_m16_m20'}.get(label)
    fixed = G['REGISTERED_EXACT'][reverse or label]
    indices = list(reversed(fixed['indices'])) if reverse else fixed['indices']
    if 'points_m' in fixed:
        points = list(reversed(fixed['points_m'])) if reverse else fixed['points_m']
    else:
        triangles = [G['selected'](mesh,index) for mesh,index in zip(surfaces,indices,strict=True)]
        points = feature_attainer(*triangles,[witness[k] for k in D['SIDES']])
    host = capture['host_identity']
    scope = {'scope':D['OLD']['PROOF_SCOPE'],'index_domain':D['OLD']['DOMAIN'],
             'document_epoch':host['document_epoch'],'capture_state':deepcopy(capture['capture_state'])}
    for key,row,index,exact in zip(D['SIDES'],body['binding']['objects'],indices,points,strict=True):
        scope[key] = {'instance_id':host['object_instances'][row['object_id']],
                      'source_triangle_index':index,'point_m':exact}
    return scope


def preflight():
    verified,example = {},None
    for label in sets['CASES']:
        identity,actual = M['read_case'](BASE,label,opted_in=True)
        raw = actual['cold']
        capture = raw['capture']
        prior = raw['reply']
        _,_,body = D['OLD']['E']['public'](prior)
        present = sets['CASES'][label][0]!='success'
        issued = deepcopy(prior)
        if present:
            ext = derived_extension(label,capture,body)
            D['OLD']['witnesses'](body)[D['EXACT']] = ext
            if example is None:
                example = capture,deepcopy(body)
        issued['result']['content'][0]['text'] = G['encode'](body)
        verified[label] = D['verify_delivery'](label,prior,issued,capture=capture,identity=identity)
    capture,good = example
    stale = deepcopy(capture)
    stale['capture_state']['revision'] += 1
    stale_error = rejects(lambda:D['verify_certificate'](stale,good,expect_exact=True),
                          'exact_public_proof_does_not_bind_current_capture_generation')
    lost = deepcopy(good)
    lost['binding']['objects'].reverse()
    swapped = rejects(lambda:D['verify_certificate'](capture,lost,expect_exact=True,
                       expected_order=('M01','M03')),'exact_public_proof_order_scope_or_actual_capture_detached')
    invalid = deepcopy(good)
    D['OLD']['witnesses'](invalid)[D['EXACT']]['a']['source_triangle_index'] = 10**6
    wrong_face = rejects(lambda:D['verify_certificate'](capture,invalid,expect_exact=True),
                         'certificate_triangle_index_outside_current_object')
    unnormalized = deepcopy(good)
    point = D['OLD']['witnesses'](unnormalized)[D['EXACT']]['a']['point_m']
    point[0]='-82/20'
    not_reduced = rejects(lambda:D['verify_certificate'](capture,unnormalized,expect_exact=True),
                          'reduced_rational_coordinate_string_required')
    insane = deepcopy(good)
    D['OLD']['witnesses'](insane)[D['EXACT']]['a']['point_m'][0]='1'+'0'*2000
    over = rejects(lambda:D['verify_certificate'](capture,insane,expect_exact=True),
                   'exact_public_source_certificate_schema_or_1024_byte_bound_changed')
    return {'passed':True,'actual_base_stdio':sets['pin'](BASE/'INDEX.json'),
            'verified_fixture_pairs':verified,'negative_controls':[stale_error,swapped,wrong_face,not_reduced,over],
            'scope':'Derived checker projections on actual replay, checked independently; no installed candidate gains claimed.',
            'actual_new_models':0,'actual_new_Blender':0}


if __name__=='__main__':
    print(json.dumps(preflight(),ensure_ascii=False,allow_nan=False,indent=2))
