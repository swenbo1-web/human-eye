"""047 source-bound arithmetic certificate. This module never imports a tested kernel.

The formulas certify count/work inequalities, not a product route or a timeout,
bit-domain, source-validity, publication or closed-solid success decision.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
RAW=Path('D:/HumanEye/runs/M6-047-R3-COVERAGE-DOMAIN/proof')
SITES={
    'A':Path('D:/HumanEye/runs/M6-041-KERNEL-HOOK/install/032/.human-eye/releases/9.7.2+k041hook032/site-packages/human_eye_plugin'),
    'C':Path('D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/candidate/.human-eye/releases/9.7.2+k043region/site-packages/human_eye_plugin'),
}

def pin(path):
    p=Path(path).resolve(strict=True);b=p.read_bytes()
    return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}

def bvh_build_upper(n):
    """All nonempty binary source partitions, leaves of size at least two except n=1."""
    assert type(n) is int and n>0
    return n*n+n

def bounds(n,m,*,remaining_work=1179648,remaining_narrow=16384):
    assert type(n) is int and type(m) is int and n>0 and m>0
    p=n*m;f=n+m
    linear=p<=256
    leaf=75*p
    preparation=5*f
    if linear:
        traversal=optional=tree=0
        total=preparation+leaf+4
    else:
        traversal=10*p
        optional=39*p
        tree=f+2+bvh_build_upper(n)+bvh_build_upper(m)
        total=preparation+tree+leaf+traversal+optional+4
    return {'n':n,'m':m,'P':p,'F':f,'linear':linear,'source_pair_narrow_upper':p,
        'source_pair_leaf_visits_upper':p,'conceptual_tree_node_upper':2*p-1,
        'fresh_or_normal_recharged_preparation_upper':preparation,'tree_preparation_upper':tree,
        'charged_leaf_work_upper':leaf,'ordinary_tree_work_upper':traversal,
        'optional_settled_projection_work_upper':optional,'native_publication_checks_upper':4,
        'abstract_work_upper':total,'remaining_work':remaining_work,'remaining_narrow':remaining_narrow,
        'face_cap_sufficient':f<=4096,'narrow_cap_sufficient':p<=remaining_narrow,
        'abstract_work_cap_sufficient':total<=remaining_work,
        'known_answer_guaranteed':False,
        'not_covered':['invalid/mutating source','integer/Fraction bit refusal','unrepresentable or unpublished witness',
            'closed-solid/support/composite work beyond this distance suffix','deadline/cancel/host transport']}

def source_functions(path,names):
    source=path.read_text(encoding='utf8');tree=ast.parse(source)
    result={}
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names:
            code=ast.get_source_segment(source,node)
            result[node.name]={'first_line':node.lineno,'last_line':node.end_lineno,
                'text_sha256':hashlib.sha256(code.encode()).hexdigest()}
    return result

def main():
    started=time.perf_counter_ns();cpu=time.process_time_ns();RAW.mkdir(parents=True,exist_ok=False)
    sources={}
    for arm,folder in SITES.items():
        sources[arm]={}
        for name,names in [
            ('surface_proximity.py',{'_nearest_linear','_nearest_tree','_nearest','_distance_roots','_compile_bvh_node',
                '_node_queue_bounds','_nearest_pair','_clip_coplanar','_ProjectionCredit','_wp_narrow_work_floor',
                '_pair_from_mesh_cache','_boundary_witness','_witness_triangle_provenance',
                'measure_surface_proximity','measure_spatial_relation'}),
            ('surface_geometry.py',{'_bvh','_build_sah_bvh','_bvh_median'}),
            ('task_query.py',{'_surface_pair_measurement','_closed_surface_facts'})]:
            p=folder/name;sources[arm][name]={'file':pin(p),'functions':source_functions(p,names)}
    # Check the numerical build bound over every possible source size without
    # building a BVH. Worst split is the combinatorial 1+(n-1) recurrence.
    worst=[0,2,3]
    for n in range(3,4097):
        worst.append(n+1+worst[1]+worst[n-1])
        assert worst[n]<=bvh_build_upper(n)
    cases=[bounds(125,125),bounds(129,129),bounds(262,12),bounds(174,12),
        bounds(96,12),bounds(128,28),bounds(12,12),bounds(60,60),bounds(174,12,remaining_work=8356)]
    proof={'schema':'m6-047-source-only-obligation-work-certificate-v1','status':'count_and_abstract_work_bounds_proved',
        'source':pin(__file__),'written_proof':pin(HERE/'DOMAIN_PROOF.md'),'source_bindings':sources,
        'cap_constants':{'faces':4096,'narrow':16384,'work':1179648,'bits':4096,'linear_product':256},
        'no_kernel_imports_or_calls':True,'Blender':0,'MCP':0,
        'pair_uniqueness_scope':'one _nearest invocation on two valid original-row-preserving prepared sides; early contact bypass has zero narrow calls',
        'C_tree_formula':'124*n*m+n*n+m*m+7*(n+m)+6',
        'linear_formula':'75*n*m+5*(n+m)+4',
        'example_count_evaluations':cases,
        'build_bound_checks':{'n_range':[1,4096],'checked_by_integer_recurrence_only':True},
        'whole_contract_known_answer_proof':False,
        'first_missing_general_conditions':['bit-domain success','publication and canonical evidence on every path',
            'remaining composite/closed work','actual valuable G60 load inclusion'],
        'zero_contact_canonical_limit':'validated _boundary_contact can bypass distance traversal without proving lexicographic global zero-distance source pair',
        'cost_wall_ns':time.perf_counter_ns()-started,'cost_cpu_ns':time.process_time_ns()-cpu}
    p=RAW/'CERTIFICATE.json'
    with p.open('x',encoding='utf8',newline='\n') as out:json.dump(proof,out,indent=2);out.write('\n')
    print(json.dumps({'certificate':pin(p),'status':proof['status']}))

if __name__=='__main__':main()
