"""Independent saved-RNA replay and exact-source fake-host cases; no Blender."""
from pathlib import Path
from fractions import Fraction
import copy, hashlib, itertools, json, math, random, struct, sys, time, types

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT = Path(__file__).resolve().parent
E = ROOT / 'verification/m2_tight_directory_001/correctness/entry_02'
seen = {}
def read(path):
    blob = path.read_bytes()
    seen[str(path)] = hashlib.sha256(blob).hexdigest()
    return blob
def load_json(path): return json.loads(read(path))
def source_module(name, path):
    mod = types.ModuleType(name); mod.__file__ = str(path)
    sys.modules[name] = mod
    exec(compile(read(path), str(path), 'exec', dont_inherit=True), mod.__dict__)
    return mod
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def oid(source): return 'blender:' + digest([source['library_path'], source['name_full']])

hostmod = source_module('_root_directory_actual_host', ROOT/'human_eye_plugin/blender_host.py')
hostsha = seen[str(ROOT/'human_eye_plugin/blender_host.py')]
hostmod._READONLY_LOADED_HOST_SHA256 = hostsha
corekeys = ('schema','result_kind','status','unit','coordinate_frame','objects','coverage','binding','execution_authority')
bindingkeys = ('host_source_sha256','host_identity','frame','subframe','scale_length')
checks = 0
def check(ok, detail):
    global checks
    checks += 1
    if not ok: raise AssertionError(detail)

saved = []
packets = {}
max_error = 0.
coordinates = 0
for path in sorted(E.glob('*.ORACLE.json')):
    label = path.name.removesuffix('.ORACLE.json')
    response = load_json(E/(label+'.RESPONSE.json'))
    packet = json.loads(response['result']['content'][0]['text'])
    if packet.get('result_kind') != 'scene_directory': continue
    oracle = load_json(path)
    check(response['result']['isError'] is False, label+' error')
    expected = {oid(row):row for row in oracle['objects']}
    check(set(expected) == {row['object_id'] for row in packet['objects']}, label+' coverage')
    check(packet['coverage'] == dict(status='complete',mesh_objects=len(expected),measured_objects=len(expected)), label+' count')
    check(packet['execution_authority'] is False, label+' authority')
    check(packet['binding']['host_source_sha256'] == hostsha, label+' host sha')
    check(packet['binding']['frame']==oracle['frame'] and packet['binding']['subframe']==oracle['subframe'], label+' frame')
    b = copy.deepcopy(packet['binding']); b = {k:b[k] for k in bindingkeys}
    core = {k:packet[k] for k in corekeys}; core['binding'] = b
    check(digest(core)==packet['directory_sha256'], label+' digest')
    check(not set(packet).intersection(('scene_revision','scene_fingerprint','scene_memory','meshes','resources')), label+' separate')
    gap = 0.
    for row in packet['objects']:
        raw = expected[row['object_id']]
        check(row['name']==raw['name'], label+' name')
        check(packet['binding']['host_identity']['object_instances'][row['object_id']]==raw['instance_id'],label+' instance')
        vertices, matrix, scale = raw['vertices_local'], raw['matrix_world'], raw['unit_scale_m']
        world = [[(sum(Fraction(matrix[r][c])*Fraction(v[c]) for c in range(3))+Fraction(matrix[r][3]))*Fraction(scale) for r in range(3)] for v in vertices]
        lo = [min(v[k] for v in world) for k in range(3)]
        hi = [max(v[k] for v in world) for k in range(3)]
        # Independent arithmetic bound for three products, addition, translation and scale.
        magnitude = max(float((sum(abs(Fraction(matrix[r][c])*Fraction(v[c])) for c in range(3))+abs(Fraction(matrix[r][3])))*abs(Fraction(scale))) for r in range(3) for v in vertices)
        bound = 16 * sys.float_info.epsilon * max(magnitude,sys.float_info.min)
        for field, truth in (('bbox_min',lo),('bbox_max',hi)):
            for actual, wanted in zip(row[field], truth):
                error = abs(Fraction(actual)-wanted)
                check(error <= Fraction(bound), (label,row['name'],field,float(error),bound))
                max_error = max(max_error,float(error)); coordinates += 1
        center = [float((Fraction(a)+Fraction(b))/2) for a,b in zip(row['bbox_min'],row['bbox_max'])]
        check(row['center']==center, label+' exact published midpoint'); coordinates += 3
        local_bounds = [ (min(v[k] for v in vertices),max(v[k] for v in vertices)) for k in range(3)]
        corners = [[(sum(Fraction(matrix[r][c])*Fraction(v[c]) for c in range(3))+Fraction(matrix[r][3]))*Fraction(scale) for r in range(3)] for v in itertools.product(*local_bounds)]
        wrongcenter = [(min(v[k] for v in corners)+max(v[k] for v in corners))/2 for k in range(3)]
        gap = max(gap,max(abs(float(w)-float((l+h)/2)) for w,l,h in zip(wrongcenter,lo,hi)))
    saved.append(dict(label=label,objects=len(expected),wrong_corner_center_max_delta_m=gap,capture_state=packet['capture_state'],cache_hit=packet['cache_hit']))
    packets[label] = packet
check(len(saved)==17,'17 directory records')
check(packets['directory_cold']['capture_state']==packets['directory_warm']['capture_state'],'cold warm same')
check(packets['directory_warm']['cache_hit'] is True,'warm hit')
check(max(r['wrong_corner_center_max_delta_m'] for r in saved)>0.001,'actual rotated nonbox refutes corners')
ordered = load_json(E/'RESULTS.json')['records']
previous = None
state_changes = []
for record in ordered:
    label = record.get('label')
    if label not in packets: continue
    current=packets[label]
    if label.startswith('changed_'):
        check(previous is not None and previous['capture_state']!=current['capture_state'], label+' state change')
        state_changes.append(label)
    previous=current
check(packets['changed_reload']['objects']==packets['connector_reconnect']['objects'],'reconnect same live document facts')
check(packets['changed_reload']['binding']['host_identity']==packets['connector_reconnect']['binding']['host_identity'],'reconnect same host identity')

# Saved delta publication is full resync: directory did not create a full capture baseline.
delta = load_json(E/'delta_after_directory.RESPONSE.json')
delta_text = delta['result']['content'][0]['text']
delta_packet = json.loads(delta_text)['scene_transport']
delta_request = load_json(E/'delta_after_directory.REQUEST.json')['params']['arguments']['scene_delta']
check(delta_request['base_fingerprint']==packets['directory_cold']['directory_sha256'],'directory digest proposed as full base')
check(delta_packet['status']=='full' and delta_packet['base'] is None,'directory base gives complete resync')
check(delta_packet['capture_scope']=='complete_scene_meshes','delta full scope')
check(all(set(('vertices','faces','edges'))<=set(mesh) for mesh in delta_packet['payload']['meshes']),'delta payload real full records')

# Midpoints: actual product function against exact rational rounding, fixed corpus.
rng=random.Random(20261112)
vals=[0.,-0.,sys.float_info.max,-sys.float_info.max,sys.float_info.min,-sys.float_info.min,
      float.fromhex('0x0.0000000000001p-1022'),-float.fromhex('0x0.0000000000001p-1022')]
while len(vals)<256:
    x=struct.unpack('>d',rng.getrandbits(64).to_bytes(8,'big'))[0]
    if math.isfinite(x): vals.append(x)
midpoints=0
for a,b in itertools.product(vals,repeat=2):
    a,b=sorted((a,b)); actual=hostmod._bounds_midpoint(a,b)
    check(actual==float((Fraction(a)+Fraction(b))/2),('midpoint',a,b,actual))
    midpoints+=1

# Actual source host and existing bpy doubles; only scenarios below are new root execution.
resident=source_module('_root_directory_bpy_doubles',ROOT/'verification/arch_resident_001/test_residency_contract.py')
resident.Host=hostmod.BlenderSceneHost
resident.fixture.BlenderSceneHost=hostmod.BlenderSceneHost
resident.fixture.BlenderHostError=hostmod.BlenderHostError
resident.fixture._module=hostmod
for rel in ('verification/test_blender_host_contracts.py','human_eye_plugin/scene_residency.py'):
    read(ROOT/rel)
fake=[]
def capture(host): return host.capture_directory(time.perf_counter_ns()+10_000_000_000,2_000_000)
host,focal,ref,graph=resident.make_host()
try:
    p=capture(host)
    replacement=resident.prepare_object(resident.fixture.FakeObject(focal.name,(2,3,4)),777)
    replacement._matrix_world=copy.deepcopy(focal._matrix_world)
    replacement.data.vertices=copy.deepcopy(focal.data.vertices)
    host.scene.objects[host.scene.objects.index(focal)]=replacement
    q=capture(host)
    check(p['objects']==q['objects'],'sameworld replacement preserved directory facts')
    check(p['binding']['host_identity']!=q['binding']['host_identity'],'sameworld replacement changed identity')
    check(p['directory_sha256']!=q['directory_sha256'],'sameworld replacement changed binding digest')
    check(p['capture_state']!=q['capture_state'] and q['cache_hit'] is False,'sameworld replacement fresh')
    fake.append(dict(case='same_world_same_name_replacement',passed=True,before=p,after=q))
    # Inward point edit leaves bounds unchanged; its event must still invalidate generation.
    z=copy.deepcopy(q)
    replacement.data.vertices.append(types.SimpleNamespace(co=(.25,.25,.25)))
    resident.notify_geometry(host,graph,replacement,via_data=True)
    changed=capture(host)
    check(changed['capture_state']!=z['capture_state'] and changed['cache_hit'] is False,'interior event state change')
    fake.append(dict(case='geometry_event_cache_invalidation',passed=True,after=changed))
    # Full capture then directory reuse never places directory into wire resources.
    full=host.capture_scene()
    beforewire=set(host._residency.wire)
    d=capture(host)
    check(set(host._residency.wire)==beforewire,'directory did not mutate full wire')
    check(all('vertices' in m for m in full['meshes']),'full remains mesh packet')
    fake.append(dict(case='full_directory_cache_separation',passed=True))
finally: host.close_residency()
host,_,_,_=resident.make_host()
try:
    host.capture_scene()
    before=host.residency_work()
    d=capture(host)
    after=host.residency_work()
    opportunity=dict(case='full_first_then_directory_miss',before=before,after=after,
        incremental_to_mesh=after['to_mesh']-before['to_mesh'],
        incremental_directory_vertices=after['directory_vertices']-before['directory_vertices'],
        interpretation='Actual current code does not reuse already resident world vertices on a directory miss; no incorrect facts, possible bounded future optimization.')
finally: host.close_residency()

result=dict(passed=True,independent_checks=checks, saved_directory_records=len(saved),saved_object_rows=sum(r['objects'] for r in saved),
    saved_coordinate_comparisons=coordinates,max_rational_coordinate_error_m=max_error,changed_states=state_changes,
    midpoint_cases=midpoints,source_host_sha256=hostsha,source_reads=seen,records=saved,fake_host_cases=fake,optimization_observation=opportunity,
    source_scope='actual candidate host source compiled from read bytes, resident bpy test doubles; no Blender execution',
    not_run=['Blender','model consumers','installation','full JSON Schema engine','source fixture real same-world replacement'],
    notes=['Saved real Blender inputs/results recomputed independently; original scene acquisition was author execution.',
           'No product/source edits. No full old unit-suite rerun. Assertions are not independent scenes.'])
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
print(json.dumps({k:result[k] for k in ('passed','independent_checks','saved_directory_records','saved_object_rows','saved_coordinate_comparisons','midpoint_cases','max_rational_coordinate_error_m')},ensure_ascii=False))
