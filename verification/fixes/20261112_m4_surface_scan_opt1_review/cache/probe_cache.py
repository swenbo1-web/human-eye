"""Independent private-binding probes, without Blender or author fixtures."""
from pathlib import Path
from copy import deepcopy
import hashlib
import importlib.util
import json
import subprocess
import sys
import types

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT = Path(__file__).resolve().parent
PRODUCT = 'c1cb2da32034e056a270384e691a2cde8dddbc0d'
SOURCES = []
CHECKS = []

def load(name):
    path = ROOT / ('human_eye_plugin/' + name + '.py')
    data = path.read_bytes()
    original = subprocess.check_output(['git','show',PRODUCT+':'+path.relative_to(ROOT).as_posix()], cwd=ROOT)
    assert data == original
    SOURCES.append({'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    mod = types.ModuleType('probe_package.' + name)
    mod.__file__ = str(path)
    mod.__package__ = 'probe_package'
    sys.modules[mod.__name__] = mod
    exec(compile(data, str(path), 'exec'), mod.__dict__)
    return mod

pkg = types.ModuleType('probe_package');pkg.__path__=[]
sys.modules[pkg.__name__] = pkg
res = load('scene_residency')
memo = load('scene_cache')
SHA = 'f'*64

def check(name, test, detail=None):
    CHECKS.append({'name':name,'passed':bool(test),'detail':detail})
    assert test, name

def fixture(*, generation=1, positions=None, revisions=None, changes=None,
            epoch=1, document='doc', incarnations=None, scale=1., signed_zero=0., protocol=None):
    positions={'a':0.,'b':2.,'c':4.} if positions is None else positions
    revisions=revisions or {};changes=changes or {};incarnations=incarnations or {}
    ids=sorted(positions)
    hi={'schema_version':'1.0','capture_scope':'surface_scan_candidates','document_epoch':document,
        'object_instances':{oid:incarnations.get(oid, 'inc-'+oid) for oid in ids}}
    scene={'revision':str(generation),'capture_scope':'surface_scan_candidates','source':'blender',
           'unit':'m','coordinate_frame':'world','host_identity':hi,
           'capture_state':{'instance_id':'host','epoch':epoch,'revision':generation,'selection_key':'scan'},
           'meshes':[{'object_id':oid,'name':oid,'vertices':[],'faces':[],'edges':[]} for oid in ids]}
    payload={'protocol':protocol or 'single-read-surface-scan-v1','capture':scene,
             'binding':{'host_source_sha256':'a'*64,'host_identity':dict(hi,capture_scope='complete_scene_meshes')}}
    bindings={}
    for oid in ids:
        resource={'resource_id':'r-'+oid,'revision':revisions.get(oid,1),
            'vertices_local':[[changes.get(oid,0.),0.,0.],[0.,1.,0.],[0.,0.,1.]],
            'faces':[[0,1,2]],'edges':[[0,1],[1,2],[2,0]]}
        matrix=[[1.,signed_zero,0.,positions[oid]],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
        bindings[oid]=(resource,matrix,scale)
    return payload,bindings

class Mesh:
    def __init__(self,row):self.row=deepcopy(row);self.object_id=row['object_id']
    def to_dict(self):return deepcopy(self.row)

def decoded(decoder, *, resend=False, **kw):
    packet,binding=fixture(**kw)
    wire=res.encode_capture(packet,None if resend else decoder.baseline(),binding)
    result=decoder.apply(wire)
    return result,decoder.surface_scan_dependencies(result)

def bind(cache,payload,token, *, runtime=SHA):
    meshes={m['object_id']:Mesh(m) for m in payload['capture']['meshes']}
    # Exactly the owning ReadContext reset/bind boundary; the generic token changes.
    cache._bind_read_meshes(('capture',payload['capture']['capture_state']['revision']),meshes.values())
    accepted=cache._bind_surface_scan_meshes(list(meshes.values()),token,runtime,capture=payload)
    return meshes,accepted

def request(cache,meshes,a,b, *, scan=True, valid=True, reserve=None):
    work={};called=[]
    def compute():
        called.append(True)
        return {'measurement_valid':valid,'endpoints':[meshes[a].row['vertices'][0],meshes[b].row['vertices'][0]]}
    result,hit=cache.pair_measurement(meshes[a],meshes[b],compute,
        algorithm_version='independent-binding-probe',parameters={'unit':'m'},
        _surface_scan=scan,_diagnostics=work,before_compute=reserve)
    return result,hit,called,work

def main():
    d=res.SceneDeltaDecoder();c=memo.SpatialSceneCache(max_bytes=2*1024*1024)
    p,t=decoded(d);m,ok=bind(c,p,t)
    check('typed_initial',ok and type(t) is res.SurfaceScanDependencies)
    check('getter_consumes_reference',d._surface_scan_binding is None and d.surface_scan_dependencies(p) is None)
    base={pair:request(c,m,*pair) for pair in [('a','b'),('a','c'),('b','c')]}
    check('cold_misses',all(not item[1] for item in base.values()))
    p2,t2=decoded(d,generation=2,positions={'a':.25,'b':2.,'c':4.});m2,_=bind(c,p2,t2)
    moved={pair:request(c,m2,*pair) for pair in base}
    check('only_unaffected_hit',[item[1] for item in moved.values()]==[False,False,True])
    check('moving_witness_fresh',moved[('a','b')][0]['endpoints'][0]==[.25,0.,0.])
    reverse=request(c,m2,'c','b')
    check('reverse_is_distinct',not reverse[1] and reverse[0]['endpoints']==list(reversed(moved[('b','c')][0]['endpoints'])))
    check('generic_key_does_not_use_surface_namespace',not request(c,m2,'b','c',scan=False)[1])
    check('generic_repeat_hits_own_namespace',request(c,m2,'b','c',scan=False)[1])
    p3,t3=decoded(d,generation=3,positions={'a':.25,'b':2.,'c':4.},revisions={'a':2},changes={'a':.125});m3,_=bind(c,p3,t3)
    check('same_face_count_geometry_misses',not request(c,m3,'a','b')[1])
    check('same_face_count_other_hit',request(c,m3,'b','c')[1])
    before=d.baseline();serial=d._resource_serial
    try:decoded(d,resend=True,generation=4,positions={'a':.25,'b':2.,'c':4.},revisions={'a':2},changes={'a':.5})
    except ValueError as exc: conflict=str(exc)
    else:conflict=None
    check('conflict_rejected_atomically',conflict=='scene_delta_immutable_resource_rebound' and d.baseline()==before and d._resource_serial==serial and d._surface_scan_binding is None)
    prior_b=t3.objects['b'];prior_c=t3.objects['c']
    decoded(d,generation=5,positions={'a':.25,'b':2.},revisions={'a':2},changes={'a':.125})
    p4,t4=decoded(d,generation=6,positions={'a':.25,'b':2.,'c':4.},revisions={'a':2},changes={'a':.125});m4,_=bind(c,p4,t4)
    check('deleted_reintroduced_admission_changes',prior_c!=t4.objects['c'] and prior_b==t4.objects['b'])
    check('reintroduced_pair_misses',not request(c,m4,'b','c')[1])
    # A legacy decoder packet may rebind a resource version under its old contract.
    # It must change admission before a subsequent scan uses that same revision.
    before_a=t4.objects['a'];before_b=t4.objects['b']
    legacy,_=decoded(d,resend=True,generation=7,positions={'a':.25,'b':2.,'c':4.},
        revisions={'a':2},changes={'a':.5},protocol='legacy-capture')
    p5,t5=decoded(d,generation=8,positions={'a':.25,'b':2.,'c':4.},revisions={'a':2},changes={'a':.5});m5,_=bind(c,p5,t5)
    check('legacy_rebind_cannot_reuse_scan_key',before_a!=t5.objects['a'] and not request(c,m5,'a','b')[1])
    check('legacy_rebound_geometry_current',m5['a'].row['vertices'][0]==[.75,0.,0.])
    # Metadata-only fields do not prove a token for a distinct payload object.
    copied=deepcopy(p5);_,accepted=bind(c,copied,t5)
    check('copy_payload_not_authorized',not accepted)
    changed=deepcopy(p5['capture']['capture_state']);p5['capture']['capture_state']['epoch']+=1
    _,accepted=bind(c,p5,t5);check('changed_signature_not_authorized',not accepted)
    p5['capture']['capture_state']=changed
    _,accepted=bind(c,p5,dict(objects=dict(t5.objects)))
    check('plain_dict_not_authorized',not accepted)
    for label,kw in [('incarnation',{'incarnations':{'a':'new-a'}}),('unit',{'scale':.01}),
                     ('document',{'document':'newdoc'}),('host_epoch',{'epoch':2}),('signed_zero',{'signed_zero':-0.})]:
        dx=res.SceneDeltaDecoder();cx=memo.SpatialSceneCache()
        first,token=decoded(dx);mm,_=bind(cx,first,token);request(cx,mm,'a','b')
        nextp,nexttoken=decoded(dx,generation=2,**kw);mm,_=bind(cx,nextp,nexttoken)
        check(label+'_invalidates',not request(cx,mm,'a','b')[1])
    dx=res.SceneDeltaDecoder();cx=memo.SpatialSceneCache()
    pp,tt=decoded(dx);mm,_=bind(cx,pp,tt);request(cx,mm,'a','b')
    mm,_=bind(cx,pp,tt,runtime='e'*64);check('runtime_invalidates',not request(cx,mm,'a','b')[1])
    py,ty=decoded(res.SceneDeltaDecoder());mm,_=bind(cx,py,ty)
    check('decoder_owner_invalidates',not request(cx,mm,'a','b')[1])
    dz=res.SceneDeltaDecoder();cz=memo.SpatialSceneCache();pz,tz=decoded(dz);mz,_=bind(cz,pz,tz)
    check('unknown_first_not_cached',not request(cz,mz,'a','b',valid=False)[1])
    check('unknown_second_not_cached',not request(cz,mz,'a','b',valid=False)[1])
    requests=[]
    def stop():requests.append(1);raise TimeoutError('probe_stop')
    try:request(cz,mz,'a','b',reserve=stop)
    except TimeoutError:pass
    check('budget_miss_stops_before_computation',requests==[1] and cz.stats()['measurement_entries']==0)
    request(cz,mz,'a','b')
    check('cache_hit_does_not_charge_new_kernel',request(cz,mz,'a','b',reserve=stop)[1] and requests==[1])
    for max_count in (1,2):
        ce=memo.SpatialSceneCache(max_measurements=max_count);me,_=bind(ce,pz,tz)
        for pair in [('a','b'),('a','c'),('b','c')]:request(ce,me,*pair)
        check('bounded_eviction_'+str(max_count),ce.stats()['measurement_entries']==max_count and not request(ce,me,'a','b')[1])
    return {'passed':all(x['passed'] for x in CHECKS),'checks':CHECKS,'source_files':SOURCES,
            'scope':'Pure decoder/cache methods and synthetic geometry; no product process, Blender, network, consumer or API',
            'product_commit':PRODUCT}

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    result=main()
    (OUT/'PROBES.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'passed':result['passed'],'checks':len(CHECKS)}))
