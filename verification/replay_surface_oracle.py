"""Independent edge-plane all-pairs oracle on frozen native B1 sources.

Offline validation is separately timed and never charged as a fast runtime
path. It uses no production spatial tree, clipping, or legal-simplex function.
"""
import argparse,hashlib,importlib.util,json,sys,time
from pathlib import Path
from fractions import Fraction as Q
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main(args):
    spec=importlib.util.spec_from_file_location('_oracle_entry',args.entry);entry=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=entry;spec.loader.exec_module(entry);proof=entry.validate_binding(expected_python=sys.executable)
    sys.path.insert(0,proof['module_root']);identity,_=entry.verify_imported_runtime(proof)
    from human_eye_plugin import surface_geometry as g,mesh_structure as raw
    from verification.test_surface_geometry import oracle
    def sub(a,b):return tuple(a[k]-b[k] for k in range(3))
    def dot(a,b):return sum(a[k]*b[k] for k in range(3))
    def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    rows=[]
    for case in ('intersecting_icospheres','external_Avocado','suzanne'):
        path=args.assets/case/'SOURCE_0.json';blob=path.read_bytes();value=json.loads(blob);r=value['raw'];triangles=value['triangles']
        assert len(triangles)<=2048
        meta=dict(object_id='offline:'+case,object_instance='frozen_offline_source',document_epoch='not_a_current_host',capture_id='oracle_capture')
        prepared=raw.prepare_raw(r,meta);production=g.analyze(prepared,triangles,value['triangle_polygons'],budget=raw.WorkBudget(),near_m=0)
        assert production['scan_complete'] and production['pair_accounting_complete'] and not production['degenerate_triangles_total']
        started=time.perf_counter_ns();matrix=r['matrix_world'];unit=Q(r['unit_scale'])
        vertices=[tuple((sum(Q(matrix[k][j])*Q(p[j]) for j in range(3))+Q(matrix[k][3]))*unit for k in range(3)) for p in r['vertices']]
        points=[tuple(vertices[i] for i in t) for t in triangles]
        boxes=[(tuple(min(p[k] for p in t) for k in range(3)),tuple(max(p[k] for p in t) for k in range(3))) for t in points]
        contacts={};candidate_count=0;all_pairs=0
        for i,a in enumerate(points):
            for j in range(i+1,len(points)):
                all_pairs+=1
                if any(boxes[i][0][k]>boxes[j][1][k] or boxes[j][0][k]>boxes[i][1][k] for k in range(3)):continue
                candidate_count+=1;b=points[j];witness=oracle(a,b)
                if not witness:continue
                shared=sorted(set(triangles[i])&set(triangles[j]));legal=False
                if len(shared)==1:legal=all(p==vertices[shared[0]] for p in witness)
                if len(shared)==2:
                    s,t=(vertices[k] for k in shared);d=sub(t,s)
                    legal=all(not any(cross(sub(p,s),d)) and 0<=dot(sub(p,s),d)<=dot(d,d) for p in witness)
                if legal:continue
                p=list(witness);rank=0 if len(p)==1 else 2 if any(any(cross(sub(p[1],p[0]),sub(v,p[0]))) for v in p[2:]) else 1
                kind=('contact_point','contact_line','contact_area')[rank]
                contacts[(i,j)]=kind
        assert all_pairs==len(points)*(len(points)-1)//2
        assert len(contacts)==production['total'],(case,len(contacts),production['total'])
        for region in production['regions']:assert contacts[tuple(region['triangles'])]==region['kind']
        rows.append(dict(case=case,source_file_sha256=hashlib.sha256(blob).hexdigest(),all_pairs=all_pairs,
            oracle_candidate_tests=candidate_count,expected_contacts=len(contacts),production_total=production['total'],
            delivered_source_pairs_verified=len(production['regions']),oracle_elapsed_ns=time.perf_counter_ns()-started,
            production_counts_by_relation=production['counts_by_relation'],all_pairs_complete=True))
        print(json.dumps(rows[-1]),flush=True)
    with args.output.open('x',encoding='utf8') as f:json.dump(dict(runtime_source=identity['source_sha256'],rows=rows,all_passed=True,
        independent_algorithm='six_segment_plane_tests_with_coplanar_segment_halfplane_clipping',formal_model_calls=0),f,indent=2)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--entry',type=Path,required=True);p.add_argument('--assets',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);main(p.parse_args())
