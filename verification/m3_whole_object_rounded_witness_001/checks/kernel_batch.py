"""Run the frozen 210-pair installed kernel batch and compare exact provenance."""

import argparse
from fractions import Fraction as F
from hashlib import sha256
from itertools import combinations
import json
from math import isclose
from pathlib import Path
from subprocess import check_output
import sys
from time import perf_counter_ns
from unittest.mock import patch
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
FREEZE_ROOT = Path('D:/he_m4_cross_scale_live_task_001/fixture')
ASSET = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
READBACK = '836219a6cd00f81dc658b0277c4dfa82cfafba8d094570ec797dbc5eb8e12dee'
REFERENCE = V/'m3_whole_object_witness_triangle_001/install/PRODUCT_RUN_BINDING.json'
EXPECTED_LOSS = [('M01','M03'),*((f'M{x:02d}','M20') for x in (10,11,13,14,16,17,18))]
KNOWN = {
    ('M01','M03'): {'exact_m2':'11449/1024','points':[['-41/10','-503/160','5/4'],['-67/32','-15/32','5/4']],
                    'indices':[8,12]},
    ('M16','M20'): {'exact_m2':'3481/50','points':[['109/4','-13/4','15/4'],['3197/100','-679/100','193/20']],
                    'indices':[2,1]},
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data):
    return sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        stream.write('\n')


def pin(path, expected=None):
    raw = Path(path).read_bytes()
    actual = digest(raw)
    require(expected in (None, actual), 'sealed_file_digest_changed/'+str(path))
    return {'path':Path(path).resolve().as_posix(),'bytes':len(raw),'sha256':actual}


def fixed_source():
    model = FREEZE_ROOT/'main.blend'
    source = FREEZE_ROOT/'READBACK_AFTER_RELOAD.json'
    pins = [pin(model, ASSET),pin(source, READBACK)]
    packet = read(source)
    items = {row['name']:row['evaluated'] for row in packet['objects']}
    require(len(items)==21 and set(items)=={f'M{i:02d}' for i in range(1,22)}
            and sum(len(row['vertices_world']) for row in items.values())==148
            and sum(len(row['triangles']) for row in items.values())==184
            and packet['scale_length']==1.0,'sealed_evaluated_source_roster_or_units_changed')
    return items,pins


def installed(binding_path):
    binding = read(binding_path)
    wheel,root = (Path(binding[key]).resolve(strict=True) for key in ('wheel_path','install_root'))
    require(len(binding['source_manifest'])==len({row['path'] for row in binding['source_manifest']})==143,
            'runtime_source_denominator_changed')
    identity = {'binding':pin(binding_path),'wheel':pin(wheel,binding['wheel_sha256']),
                'source_sha256':binding['source_sha256'],'git':binding['preparation_git'],
                'source_count':len(binding['source_manifest'])}
    with ZipFile(wheel) as archive:
        for row in binding['source_manifest']:
            relative = row['path']
            package = archive.read(relative)
            raw = (root/relative).read_bytes()
            require(raw==package and digest(raw)==row['sha256'],'install_source_differs_from_pinned_wheel/'+relative)
    source_file='human_eye_plugin/surface_proximity.py'
    git=check_output(['git','show',binding['preparation_git']+':'+source_file],cwd=V.parent)
    require(git==(root/source_file).read_bytes(),'installed_kernel_differs_from_fixed_Git')
    sys.path[:0] = [str(root),binding['dependency_root']]
    from human_eye_plugin import surface_proximity as surface
    from human_eye_plugin.runtime_identity import runtime_identity
    require(Path(surface.__file__).resolve().is_relative_to(root)
            and runtime_identity()['source_sha256']==binding['source_sha256'],
            'loaded_kernel_is_not_verified_installed_candidate')
    return surface,identity


def meshes(source):
    import numpy as np
    from human_eye_module1_operators import MeshEntity3D

    return {name:MeshEntity3D(name,'#'+name,name,np.array(row['vertices_world'],dtype=float),
                np.array(row['triangles'],dtype=np.int64),None,(100,140,180),False)
            for name,row in source.items()}


def inner(a,b):
    return sum(x*y for x,y in zip(a,b,strict=True))


def minus(a,b):
    return tuple(x-y for x,y in zip(a,b,strict=True))


def exact_point(point):
    return tuple(F(v) if isinstance(v,(str,int,F)) else F(float(v)) for v in point)


def contains(point, triangle):
    """Independent rational Gram solve, including finite segment and point hulls."""
    p,a,b,c = (exact_point(row) for row in (point,*triangle))
    ab,ac,ap = minus(b,a),minus(c,a),minus(p,a)
    uu,uv,vv = inner(ab,ab),inner(ab,ac),inner(ac,ac)
    determinant = uu*vv-uv*uv
    if determinant==0:
        for low,high in ((a,b),(b,c),(c,a)):
            direction,delta=minus(high,low),minus(p,low)
            scale,projection=inner(direction,direction),inner(delta,direction)
            if p==low or scale and 0<=projection<=scale and all(
                    d*scale==v*projection for d,v in zip(delta,direction,strict=True)):
                return True
        return False
    left,right=inner(ab,ap),inner(ac,ap)
    u,v=(left*vv-right*uv)/determinant,(right*uu-left*uv)/determinant
    return 0<=u and 0<=v and u+v<=1 and all(
        d==u*x+v*y for d,x,y in zip(ap,ab,ac,strict=True))


def original_winner_measure(surface, pair):
    observed = []
    entry = surface._nearest

    def nearest(*args, **kwargs):
        result = entry(*args,**kwargs)
        observed.append(list(kwargs['witness_pair']))
        return result

    start = perf_counter_ns()
    with patch.object(surface,'_nearest',side_effect=nearest) as meter:
        result = surface.measure_surface_proximity(*pair,lambda _:None,retain_witness_triangles=True)
        require(meter.call_count==1 and len(observed)==1 and len(observed[0])==2,'one_original_solver_call_required')
    return result,observed[0],perf_counter_ns()-start


def packet_checks(pair,result,chosen,rounded_exact):
    displayed = [result['point_a_world'],result['point_b_world']]
    require(result['measurement_valid'] is True and result['witness_status']=='measured'
            and all(point is not None for point in displayed),'frozen_210_corpus_lost_original_point_witness')
    faces = []
    for mesh,index in zip(pair,chosen,strict=True):
        require(type(index) is int and 0<=index<len(mesh.faces),'wrong_original_object_local_face')
        face=mesh.vertices[mesh.faces[index]]
        faces.append(face)
    strict = result.get('witness_triangle_indices')
    displayed_members = [contains(point,face) for point,face in zip(displayed,faces,strict=True)]
    require((strict==chosen) if all(displayed_members) else strict is None,'legacy_strict_winner_or_membership_changed')
    if rounded_exact is not None:
        require(rounded_exact['indices']==chosen and strict is None
                and len(rounded_exact['points'])==2 and all(type(point) is list and len(point)==3 for point in rounded_exact['points']),
                'rational_provenance_changed_winner_or_strict_scope')
        for point,output,face in zip(rounded_exact['points'],displayed,faces,strict=True):
            require(all(type(value) is str and str(F(value))==value for value in point)
                and list(map(float,map(F,point)))==output and contains(point,face),
                'exact_world_point_not_canonical_not_same_display_or_not_in_original_face')
        a,b = tuple(exact_point(point) for point in rounded_exact['points'])
        square=inner(minus(b,a),minus(b,a))
        require(isclose(float(square),result['distance_m']**2,rel_tol=1e-14,abs_tol=1e-14),
                'rational_point_pair_is_not_the_original_distance')
        return str(square)
    return None


def candidate_extension(result):
    # This adapter is the only location that depends on the candidate ABI.
    value = result.get('exact_witness_triangles')
    return None if value is None else {'indices':value['indices'],'points':value['points_m']}


def compare(existing,new):
    require(existing['winner']==new['winner'],'rounded_certification_changed_original_search_winner')
    a,b=(row['result'] for row in (existing,new))
    base={key:value for key,value in b.items() if key not in ('work','exact_witness_triangles')}
    require(base=={key:value for key,value in a.items() if key!='work'},'rounded_certification_changed_original_public_metric')
    old,new_work=a['work'],b['work']
    require(all(old[key]==new_work[key] for key in old if key != 'work_units'),
            'rounded_certification_changed_original_search_counts')
    extra=new_work.get('exact_witness_triangle_checks',0)
    require(type(extra) is int and 0<=extra<=2 and new_work['work_units']-old['work_units']==extra,
            'rounded_certification_added_unbounded_or_unaccounted_search_work')


def run(binding_path, output, baseline=None):
    source,pins=fixed_source()
    surface,identity=installed(binding_path)
    raw_meshes=meshes(source)
    before=read(baseline) if baseline is not None else None
    old = {tuple(row['names']):row for row in before['cases']} if before is not None else {}
    cases,loss,exact = [],[],[]
    for names in combinations(sorted(raw_meshes),2):
        pair=tuple(raw_meshes[n] for n in names)
        result,winner,clock=original_winner_measure(surface,pair)
        extension=candidate_extension(result)
        squared=packet_checks(pair,result,winner,extension)
        if 'witness_triangle_indices' not in result:
            loss.append(names)
        if extension:
            exact.append(names)
        if names in KNOWN:
            verify=KNOWN[names]
            require(winner==verify['indices'], 'independent_original_winner_changed/'+str(names))
            if before is not None:
                require(squared==verify['exact_m2'] and extension['points']==verify['points'],
                        'independent_support_plane_neighbors_differ/'+str(names))
        row={'names':names,'winner':winner,'result':result,'exact_world_distance_squared_m2':squared,
             'installed_kernel_with_winner_receipt_ns':clock}
        if before is not None:
            compare(old[names],row)
        cases.append(row)
    require(len(cases)==210 and loss==EXPECTED_LOSS and (exact==EXPECTED_LOSS if before is not None else not exact),
            'registered_202_strict_and_8_rounded_scope_changed')
    receipt={'passed':True,'identity':identity,'source_pins':pins,'pair_count':len(cases),
             'old_style_strict':len(cases)-len(loss),'strict_missing':loss,'exact_rational':exact,'cases':cases,
             'baseline_receipt':pin(baseline) if baseline else None}
    write(output,receipt)
    print(json.dumps({'passed':True,'strict':receipt['old_style_strict'],'exact_rational':len(exact),'denominator':len(cases)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding',type=Path,default=REFERENCE)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline',type=Path)
    args=parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode,'use_frozen_interpreter_I_B')
    run(args.binding,args.output,args.baseline)
