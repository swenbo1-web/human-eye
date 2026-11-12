"""Count a proposed exact rejection/contact certificate, not a solver candidate.

Uses unchanged integer preparation/BVH. Exhaustive candidate enumeration is
diagnostic-only, without the original pair/work ceilings; result acceptance
is not evaluated. Full intersection is counted only to classify the remaining
work, and no public tool, Blender or model is run.
"""
import hashlib
import json
from pathlib import Path
import sys
import types

OUT = Path(__file__).resolve().parent
ROOT = Path(r'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
binding = json.loads((OUT / 'SOURCE_BINDING.json').read_bytes())
expected = {r['path']: r['sha256'] for r in binding['manifest']}
pkg = types.ModuleType('review_certificate_potential'); pkg.__path__ = []
sys.modules[pkg.__name__] = pkg
for name in ('surface_proximity', 'surface_geometry'):
    raw = (OUT / (name + '.py.snapshot')).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected['human_eye_plugin/' + name + '.py']
    m = types.ModuleType(pkg.__name__ + '.' + name); m.__package__ = pkg.__name__
    sys.modules[m.__name__] = m; setattr(pkg, name, m)
    exec(compile(raw, str(OUT / (name + '.py.snapshot')), 'exec'), m.__dict__)
e, c = pkg.surface_proximity, pkg.surface_geometry
e.MAX_TRIANGLE_PAIRS = 10**9
c.CLOSED_SOLID_MAX_WORK = 10**9
c.CLOSED_SOLID_MAX_PAIR_TESTS = 10**9
raw = (ROOT / 'verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json').read_bytes()
assert hashlib.sha256(raw).hexdigest() == binding['snapshot_sha256']
meshes = {x['name']: types.SimpleNamespace(vertices=x['vertices_world'], faces=x['triangles'])
          for x in json.loads(raw)['objects']}


def certificate(a, b, fa, fb, shared, count):
    # If B is wholly on one closed side of A's plane, its intersection with
    # that plane is exactly the convex hull of B's zero-distance vertices.
    # When these are precisely shared mesh vertices, any intersection is the
    # permitted shared simplex. No assumption about winding/dihedral angle.
    for t, other, indices in ((a,b,fb), (b,a,fa)):
        count['plane_tests'] += 1
        distances = [e._dot(t[1], e._sub(p,t[0][0])) for p in other[0]]
        if all(v>0 for v in distances) or all(v<0 for v in distances):
            return 'strict_plane_separation'
        if shared and (all(v>=0 for v in distances) or all(v<=0 for v in distances)):
            zeros = {indices[k] for k,v in enumerate(distances) if v == 0}
            if zeros and zeros <= shared:
                return 'shared_simplex_halfspace'
    if len(shared) == 2:
        # Non-coplanar shared-edge cases were already certified above.
        # In the coplanar case opposite open sides of the shared edge imply
        # intersection exactly that edge; equal sides remain undecided.
        count['coplanar_edge_tests'] += 1
        vertices = dict(zip(fa, a[0])) | dict(zip(fb, b[0]))
        i,j = sorted(shared); delta=e._sub(vertices[j],vertices[i])
        left=next(v for v in fa if v not in shared)
        right=next(v for v in fb if v not in shared)
        sa=e._dot(e._cross(delta,e._sub(vertices[left],vertices[i])),a[1])
        sb=e._dot(e._cross(delta,e._sub(vertices[right],vertices[i])),a[1])
        if (sa<0<sb) or (sb<0<sa):return 'shared_edge_opposite_sides'
    return None


rows=[]
for name in ('Peer_000','Competing_001','Near_003'):
    diag={}; budget=c._ClosedWork(lambda stage:None,diag,e)
    records,topology=e._admit((meshes['Target'],meshes[name]),budget)
    origin,factor,prepared=e._integer_frame(records,budget)
    shells=[c._closed_topology(record[0],record[1],triangles,budget)
            for record,triangles in zip(records,prepared)]
    prep_work=diag['work_units']; phases=[]
    for label,left,right,self_pass in (('self_target',shells[0],shells[0],True),
          ('self_candidate',shells[1],shells[1],True),('cross',shells[0],shells[1],False)):
        before=dict(diag); counts=dict(plane_tests=0,coplanar_edge_tests=0,passed_aabb=0,
                                    full_intersection_calls=0,full_intersection_contacts=0)
        iterator=c.candidate_pairs(left['bounds'],0,budget,diag,
                 roots=(left['root'],right['root']),**({} if self_pass else {'other_bounds':right['bounds']}))
        for i,j in iterator:
            counts['passed_aabb']+=1
            fa,fb=left['faces'][i],right['faces'][j]
            shared=set(fa)&set(fb) if self_pass else set()
            a,b=left['triangles'][i],right['triangles'][j]
            result=certificate(a,b,fa,fb,shared,counts)
            if result:
                counts[result]=counts.get(result,0)+1
            else:
                counts['full_intersection_calls']+=1
                points=e._intersection(a[0],b[0],a[1],b[1],budget)
                counts['full_intersection_contacts']+=bool(points)
                if points and self_pass:
                    assert c._closed_legal_contact(points,sorted(shared),left['vertices'],budget)
        phases.append({'phase':label,'counts':counts,
                       'original_bvh_work_delta':{k:diag[k]-before.get(k,0) for k in diag if isinstance(diag[k],int)}})
    rows.append({'candidate':name,'preparation_work_units':prep_work,'phases':phases,
                 'original_bvh_and_remaining_predicate_work_units':diag['work_units'],
                 'extra_cheap_tests':sum(x['counts']['plane_tests']+x['counts']['coplanar_edge_tests'] for x in phases),
                 'remaining_narrow_pairs':sum(x['counts']['full_intersection_calls'] for x in phases),
                 'scope':'potential counts, not candidate result or budget pass; excludes ray/location'})
    (OUT/'CHEAP_CERTIFICATE_POTENTIAL.json').write_text(json.dumps({'rows':rows},indent=2),encoding='utf8')
    print(json.dumps(rows[-1]),flush=True)
