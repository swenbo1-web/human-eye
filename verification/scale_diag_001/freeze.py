"""Pre-sampling contract and implementation freeze; no performance selection."""
from pathlib import Path
import hashlib, importlib.util, json, time
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8',newline='\n')
spec=importlib.util.spec_from_file_location('native_smoke',HERE/'native_impl.py');n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
def counts():return {k:0 for k in ('triangle_pairs','segment_face_tests','point_face_tests','edge_edge_tests')}
cases=[]
for name,a,b,expected in [
 ('edge_pierces_face',[(-2.,-2.,0.),(2.,-2.,0.),(0.,2.,0.)],[(0.,0.,-1.),(0.,0.,1.),(0.,1.,1.)],0.),
 ('edge_edge_interior',[(-2.,0.,0.),(2.,0.,0.),(0.,-2.,0.)],[(0.,-1.,1.),(0.,1.,1.),(0.,1.,3.)],1.),
 ('coplanar_overlap',[(-2.,-2.,0.),(2.,-2.,0.),(0.,2.,0.)],[(-1.,0.,0.),(1.,0.,0.),(0.,3.,0.)],0.)]:
 got=n.triangle_pair(a,b,counts())[0];assert abs(got-expected)<1e-12,(name,got,expected);cases.append({'id':name,'squared_distance':got,'expected':expected,'pass':True})
mesh=json.loads((HERE/'fixtures/G60_D12.json').read_bytes())['objects']
g0=next(o for o in mesh if o['logical_id']=='target');g=n.Geometry(n.np.array(g0['vertices_local']),n.np.array(g0['triangles']),n.np.array(g0['matrix_world']),time.perf_counter_ns()+30*10**9,{'vertices_copied':0,'triangles_copied':0,'index_builds':0})
assert n.qualify_prism(g,time.perf_counter_ns()+30*10**9)
local=g.local.tolist()+[g.local[0].tolist(),g.local[len(g.local)//2].tolist(),g.local[1].tolist()];s=len(g.local)
faces=g.faces.tolist()+[[s,s+1,s+2],[s+2,s+1,s]]
bad=n.Geometry(n.np.array(local),n.np.array(faces),g.matrix,time.perf_counter_ns()+30*10**9,{'vertices_copied':0,'triangles_copied':0,'index_builds':0})
assert not n.qualify_prism(bad,time.perf_counter_ns()+30*10**9)
cases.append({'id':'duplicate_coincident_shell_component','pass':True,'expected':'reject','actual':'reject'})
save(HERE/'NATIVE_SMOKE.json',{'source_sha256':sha(HERE/'native_impl.py'),'cases':cases})
paths=[p for p in HERE.glob('*.py')]+[HERE/'ORACLE.json',HERE/'ORACLE_REPLAY.json']+list((HERE/'fixtures').glob('*'))
for p in HERE.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
freeze={'task':'SCALE-DIAG-001','client_date':'2026-11-10','product_commit':'d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d',
 'source_canonical':'a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b','entry_deadline_s':30,'worker_lifetime_s':570,
 'physical_chains':18,'logical_cells':78,'static_cells':36,'continuous_cells':42,'static_cold':12,'static_warm':24,
 'static_order':['G_low','G_mid','G_high','D_low','D_mid','D_high'],'route_order':['N','P'],'T_rounds':3,
 'accuracy_m':1e-6,'unknown_correct_completion':False,'timeout_retained':True,'retry_or_replacement':False,
 'cache_policy':'cold per separate child/Blender chain; retain own cache within chain; each T round reinitializes; identical management/state scripts',
 'native_tie_tolerance_m':1e-9,'unique_expected_winners':True,'G_solid_qualification_scope':'two-layer simple embedded prism fixture, independently checked actual world coordinates; numerical native classifier limited to this domain',
 'native_dirty_information':'fixed coordinator mutation events only; no general automatic invalidation claim; geometry generation and shared data invalidated; reload clears all',
 'cost_scope':'entry includes actual JSON/code/IPC/decode/solve/response encoding; cold adds setup; outer child wall includes full chain, readbacks, raw publication, cleanup',
 'preflights':'explicitly excluded from 78; raw retained; harness/Native correctness changes before freeze only; no product algorithm/budget/contract change',
 'model_consumers':False,'tokens':'N/A','fees':'N/A','coordinator_model_cost':'unmeasured','learning_task_sync':'pending: current session_context context_bound=false,rebind_required=true; no foreign handle borrowed',
 'files':{str(p.relative_to(HERE)).replace('\\','/'):sha(p) for p in sorted(paths)}}
assert not (HERE/'FREEZE.json').exists()
save(HERE/'FREEZE.json',freeze)
