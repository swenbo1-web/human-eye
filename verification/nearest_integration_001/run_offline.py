"""Execute frozen131 product bytes and exact test bytes; no Blender/session."""
import ast
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import types
from types import MappingProxyType
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DEST = OUT / sys.argv[1]
DEST.mkdir(exist_ok=False)
ENGINE = DEST / 'engine'
records, test_blobs, outcomes = [], {}, {}
started = datetime.now(timezone.utc).isoformat()
sha = lambda b: hashlib.sha256(b).hexdigest()


def save(name, value):
    (DEST/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf8')


identity_ast = ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes())
constants = {n.targets[0].id: ast.literal_eval(n.value) for n in identity_ast.body
    if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
    and n.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES')}
names = set(constants['_ROOT_MODULES']) | {p.relative_to(ROOT).as_posix()
    for package in ('human_eye_plugin', 'human_eye_module1_operators') for p in (ROOT/package).glob('*.py')}
blobs = {p: (ROOT/p).read_bytes() for p in sorted(names)}
assert len(blobs) == 131
manifest = [dict(path=p, sha256=sha(b)) for p,b in blobs.items()]
digest = sha(json.dumps(dict(base_version=constants['BASE_VERSION'],
    implementation_revision=constants['IMPLEMENTATION_REVISION'], files=manifest),
    sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
for p,b in blobs.items():
    path = ENGINE/p; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b)
loader_path = ENGINE/'human_eye_plugin/verified_source_loader.py'
helper = types.ModuleType('_human_eye_verified_source_bootstrap'); helper.__file__ = str(loader_path)
sys.modules[helper.__name__] = helper
exec(compile(blobs['human_eye_plugin/verified_source_loader.py'], str(loader_path), 'exec', dont_inherit=True), helper.__dict__)
guard = helper.install(ENGINE.resolve(), manifest, sources=MappingProxyType(blobs), bootstrap_module=helper)
package = types.ModuleType('human_eye_plugin'); package.__path__ = [str(ENGINE/'human_eye_plugin')]
guard.allow_namespace(package); sys.modules[package.__name__] = package
sys.path.insert(0, str(ROOT))
from human_eye_plugin import runtime_identity, blender_host
assert runtime_identity.runtime_identity()['source_sha256'] == digest
blender_host._READONLY_LOADED_HOST_SHA256 = sha(blobs['human_eye_plugin/blender_host.py'])
blender_host._FIRST_FACE_FIXED_GIT = True


def execute_test(name, path, content=None):
    raw = (ROOT/path).read_bytes() if content is None else content
    test_blobs[path] = raw
    module = types.ModuleType(name); module.__file__ = str(ROOT/path)
    module.__package__ = name.rpartition('.')[0]
    sys.modules[name] = module
    filename = 'verified-test:' + sha(raw) + ':' + path
    exec(compile(raw, filename, 'exec', dont_inherit=True), module.__dict__)
    records.append(dict(module=name, path=path, bytes=len(raw), sha256=sha(raw), co_filename=filename))
    return module


def run_group(label, modules):
    stream = io.StringIO(); suite = unittest.TestSuite()
    for module in modules:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (DEST/(label+'.txt')).write_text(stream.getvalue(), encoding='utf8')
    outcomes[label] = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        skipped=len(result.skipped), successful=result.wasSuccessful())
    return result


try:
    import verification.test_blender_host_contracts as fixtures
    fixtures._module = blender_host; fixtures.BlenderSceneHost = blender_host.BlenderSceneHost
    fixtures.BlenderHostError = blender_host.BlenderHostError
    integration = execute_test('nearest_integration_tests',
        'verification/nearest_integration_001/tests/test_integration.py')
    run_group('INTEGRATION', [integration])
    save('INTEGRATION_EVIDENCE.json', integration.EVIDENCE)
    base_names = ['test_host_runtime', 'test_selected_task_query', 'test_task_query', 'test_surface_proximity_001']
    normal = [execute_test('verification.'+n, 'verification/'+n+'.py') for n in base_names]
    exact = execute_test('verification.exact_rank_001.test_exact_rank', 'verification/exact_rank_001/test_exact_rank.py')
    run_group('NORMAL_TASK_EXACT', normal+[exact])
    save('EXACT_EVIDENCE.json', exact.EVIDENCE)
    import verification.test_m4_capture_001 as m4
    assert m4.m is blender_host
    # Compile the old witness baseline only for the accepted first-face sentinel.
    old_path = 'human_eye_plugin/blender_host.py'
    prior = subprocess.check_output(['git','show','3b0f67abd6ed5bdab023b2b243e395aa1e8ff109:'+old_path], cwd=ROOT)
    execute_test('_first_face_prior', old_path, prior)
    directed = execute_test('verification.bound_source_fix_001.test_source_validation',
        'verification/bound_source_fix_001/test_source_validation.py')
    first = execute_test('verification.bound_first_face_fix_001.test_first_face',
        'verification/bound_first_face_fix_001/test_first_face.py')
    run_group('SOURCE_FIRST_FACE', [directed, first])
    original = m4.TriangleObject.__init__
    def adapt(data):
        offset = 0
        for face in data.polygons:
            indices = tuple(face.vertices)
            if not hasattr(face,'loop_start') and not hasattr(face,'loop_total'):
                face.loop_start=offset; face.loop_total=len(indices); face._nearest_auto_layout=True
            elif getattr(face,'_nearest_auto_layout',False):
                face.loop_start=offset; face.loop_total=len(indices)
            for corner,index in enumerate(indices):
                slot=offset+corner
                if slot >= len(data.loops): continue
                loop=data.loops[slot]
                if loop is None:
                    data.loops[slot]=types.SimpleNamespace(vertex_index=index,_nearest_auto_index=True)
                elif getattr(loop,'_nearest_auto_index',False): loop.vertex_index=index
            offset += len(indices)
        return data
    def initialize(obj,*args,**kwargs): original(obj,*args,**kwargs); adapt(obj.data)
    witness, validator = blender_host._acquisition_witness, blender_host._acquisition_validate_triangles
    def adapted_witness(data,*args): return witness(adapt(data),*args)
    def adapted_validator(data,**kwargs): return validator(adapt(data),**kwargs)
    nine = execute_test('verification.m4_capture_opt_001.test_nine_pairs', 'verification/m4_capture_opt_001/test_nine_pairs.py')
    with patch.object(m4.TriangleObject,'__init__',initialize), \
         patch.object(blender_host,'_acquisition_witness',side_effect=adapted_witness), \
         patch.object(blender_host,'_acquisition_validate_triangles',side_effect=adapted_validator):
        run_group('LEGACY_M4_RNA_ADAPTED', [m4,nine])
    assert blender_host._acquisition_witness is witness and blender_host._acquisition_validate_triangles is validator
    assert guard.verify_loaded()
finally:
    checked = guard.verify_loaded()
    witnessed = {name: guard._executed[id(module)][1] for name,module in list(sys.modules.items())
        if guard._owned_name(name) and id(module) in guard._executed}
    save('EXECUTION_IDENTITY.json', dict(runtime_source_sha256=digest, source_count=131,
        manifest=manifest, loader_sha256=sha(blobs['human_eye_plugin/verified_source_loader.py']),
        guard_verify_loaded=checked, loaded_product_witnesses=witnessed, executed_tests=records,
        product_execution='original verified_source_loader from frozen exact bytes',
        test_execution='compile exact read bytes with SHA in co_filename; loadTestsFromModule',
        dependency_scope='stdlib/third party/test dependencies outside product guard',
        RNA_adapter_scope='only legacy M4 group; no explicit bad fields overridden'))
    result=dict(started_utc=started, ended_utc=datetime.now(timezone.utc).isoformat(), groups=outcomes,
        tests_run=sum(r['tests'] for r in outcomes.values()), passed=bool(outcomes) and all(r['successful'] for r in outcomes.values()),
        runtime_source_sha256=digest, source_count=131, Blender_sessions=0, real_RPC=0)
    save('RESULTS.json', result)
    with zipfile.ZipFile(DEST/'EXECUTED_BYTES.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for p,b in blobs.items(): archive.writestr('product/'+p,b)
        for p,b in test_blobs.items(): archive.writestr('tests/'+p,b)
        archive.writestr('runner/run_offline.py', Path(__file__).read_bytes())
    print(json.dumps(result))
raise SystemExit(0 if result['passed'] else 1)
