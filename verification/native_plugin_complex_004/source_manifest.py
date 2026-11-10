"""COMPLEX-004 PREP_ONLY source/controlled-entry qualification.

Reads existing releases, Git bytes, wheels and certificates.  The only product
execution is fresh isolated identity and static ordinary tools/list imports;
no service/configuration/host is constructed and no serve process is started.
"""
import ast
from collections import Counter
import difflib
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
RELEASES=Path('D:/hefe/.human-eye/releases')
DEPENDENCY_PYTHON=RELEASES/'9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe'
SCALE_INSTALLS=ROOT/'verification/scale_opt_001/INSTALLS.json'
ROOT_MODULES=('human_eye_hook.py','human_eye_foveated_renderer.py','native_3d_spatial_scratchpad.py',
    'module_2_low_token_mcp_scene_bridge.py','module_3_1_mcp_protocol_ipc_engine.py',
    'module_3_2_vlm_grounding_closed_loop_agent.py','module_3_3_closed_loop_control_engine.py')
VERSIONS={
    'O':{'commit':'d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d',
        'release':'9.7.2+20261110.scale.baseline.lab',
        'canonical':'a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b',
        'entry_sha256':'32bc059c53766d43bcb34cfd13bbf7470fffb423656880cbc12516f69c0c1bc0',
        'receipt':Path('D:/hefe/verification/fixes/20261110_native_plugin_compare_004/BASELINE_INSTALL/ISOLATED_INSTALL.json')},
    'C':{'commit':'df016079b0265ee327f884c90dd4815c392016b6',
        'release':'9.7.2+20261110.scale.opt.r1',
        'canonical':'3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd',
        'entry_sha256':'e8f710dd283be03acf01a29f3b811a41ef767fd12b2fb6372fa8b628269617d2',
        'receipt':Path('D:/hefe/verification/fixes/20261110_local_upgrade/INSTALL/ISOLATED_INSTALL.json')},
}
SCHEMA_PROBE=r'''
import importlib.util,json,pathlib,sys
forbidden=[]
def audit(event,args):
    if event in ('socket.connect','socket.connect_ex','socket.bind','subprocess.Popen','os.system'):
        forbidden.append(event);raise RuntimeError('source_preflight_forbids_'+event)
sys.addaudithook(audit)
entry=pathlib.Path(sys.argv[1]).resolve()
spec=importlib.util.spec_from_file_location('_complex004_fixed_target',entry)
boot=importlib.util.module_from_spec(spec);sys.modules[spec.name]=boot;spec.loader.exec_module(boot)
proof=boot.validate_binding(expected_python=sys.executable)
sys.path.insert(0,proof['module_root']);identity,origins=boot.verify_imported_runtime(proof)
import numpy,PIL
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
server=LiveSpatialMCPServer(object(),default_session_id='complex004-source-only',spatial_task_only=False)
response=server.handle_jsonrpc_message({'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}})
identity,origins=boot.verify_imported_runtime(proof)
print(json.dumps({'isolated':bool(sys.flags.isolated),'dont_write_bytecode':sys.dont_write_bytecode,
    'python':sys.executable,'prefix':sys.prefix,'python_version':sys.version,
    'numpy_version':numpy.__version__,'numpy_file':numpy.__file__,
    'pillow_version':PIL.__version__,'pillow_file':PIL.__file__,
    'identity':identity,'module_origins':origins,'launcher':proof,'tools_list':response,
    'spatial_task_only':server.spatial_task_only,'service_constructed':False,
    'configuration_read':False,'host_calls':0,'forbidden_audit_events':forbidden}))
'''


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf8')
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
def load(path):return json.loads(Path(path).read_bytes())


def manifest(root):
    names=set(ROOT_MODULES)
    for package in ('human_eye_plugin','human_eye_module1_operators'):
        names.update(package+'/'+p.name for p in (root/package).glob('*.py'))
    if len(names)!=137:raise ValueError('actual_runtime_source_count:'+str(len(names)))
    return [{'path':name,'sha256':sha(root/name)} for name in sorted(names)]


def git_manifest(commit,names):
    # Archive stays in memory; no old source/evidence tree is copied.
    raw=subprocess.check_output(['git','archive','--format=tar',commit,*names],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        rows=[{'path':member.name,'sha256':hashlib.sha256(archive.extractfile(member).read()).hexdigest()}
              for member in archive.getmembers() if member.isfile()]
    if {r['path'] for r in rows}!=set(names) or len(rows)!=137:raise ValueError('fixed_git_source_members_mismatch')
    return sorted(rows,key=lambda row:row['path'])


def wheel_manifest(path):
    with zipfile.ZipFile(path) as archive:
        names=[name for name in archive.namelist() if name.endswith('.py')]
        if len(names)!=137 or len(set(names))!=137:raise ValueError('actual_wheel_runtime_count_or_duplicates')
        return [{'path':name,'sha256':hashlib.sha256(archive.read(name)).hexdigest()} for name in sorted(names)]


def normalized_template(a,b,allowed):
    old=ast.parse(a.read_text(encoding='utf8'));new=ast.parse(b.read_text(encoding='utf8'))
    if len(old.body)!=len(new.body):raise ValueError('controlled_template_statement_count_changed')
    changes=[]
    for left,right in zip(old.body,new.body):
        if ast.dump(left,include_attributes=False)==ast.dump(right,include_attributes=False):continue
        if not (isinstance(left,ast.Assign) and isinstance(right,ast.Assign) and len(left.targets)==len(right.targets)==1
            and isinstance(left.targets[0],ast.Name) and isinstance(right.targets[0],ast.Name)
            and left.targets[0].id==right.targets[0].id and left.targets[0].id in allowed):
            raise ValueError('controlled_entry_guard_or_flow_differs:'+type(left).__name__)
        changes.append(left.targets[0].id)
        left.value=ast.Constant(value='<bound-release-identity>');right.value=ast.Constant(value='<bound-release-identity>')
    if ast.dump(old,include_attributes=False)!=ast.dump(new,include_attributes=False):raise ValueError('controlled_template_does_not_match_after_identity_only_normalization')
    return {'same_guard_and_control_flow':True,'identity_or_pin_assignment_differences':changes,
        'normalized_ast_sha256':hashlib.sha256(ast.dump(old,include_attributes=False).encode()).hexdigest()}


def run(label,argv):
    env=dict(os.environ)
    for key in ('PYTHONPATH','PYTHONHOME'):env.pop(key,None)
    env['PYTHONDONTWRITEBYTECODE']='1'
    proc=subprocess.run([str(a) for a in argv],cwd=HERE,env=env,capture_output=True,timeout=45)
    stdout=HERE/(label+'.stdout.json');stderr=HERE/(label+'.stderr.txt')
    stdout.write_bytes(proc.stdout);stderr.write_bytes(proc.stderr)
    if proc.returncode:raise ValueError(label+'_failed:'+str(proc.returncode)+':'+str(stderr))
    return json.loads(proc.stdout),{'argv':[str(a) for a in argv],'exit_code':proc.returncode,
        'stdout':str(stdout),'stdout_sha256':sha(stdout),'stderr':str(stderr),'stderr_sha256':sha(stderr)}


def qualify_version(group,reference):
    fixed=VERSIONS[group];release=RELEASES/fixed['release'];entry=release/'admin/target_runtime_entry.py';site=release/'site-packages'
    receipt=load(fixed['receipt']);binding=load(entry.with_name('RUNTIME_BINDING.json'))
    if receipt['status']!='passed' or receipt['fixed_commit']!=fixed['commit'] or receipt['source_sha256']!=fixed['canonical']:raise ValueError('deployment_receipt_mismatch:'+group)
    if sha(entry)!=fixed['entry_sha256'] or sha(entry)!=receipt['launcher_sha256'] or sha(entry)!=binding['launcher_sha256']:raise ValueError('controlled_entry_hash_mismatch:'+group)
    if sha(entry.with_name('installed_release.py'))!=binding['admin_sha256'] or sha(entry.with_name('RUNTIME_BINDING.json'))!=receipt['binding_sha256']:raise ValueError('controlled_admin_or_binding_mismatch:'+group)
    if Path(binding['dependency_python']).resolve()!=DEPENDENCY_PYTHON.resolve():raise ValueError('different_dependency_interpreter:'+group)
    actual=manifest(site);fixed_git=git_manifest(fixed['commit'],[r['path'] for r in actual])
    source=Path(receipt['source_root']);source_rows=manifest(source)
    wheels=list(Path(receipt['bundle']).glob('*.whl'))
    if len(wheels)!=1:raise ValueError('one_deployed_actual_wheel_required:'+group)
    wheel=wheels[0]
    if sha(wheel)!=receipt['wheel_sha256']:raise ValueError('deployment_actual_wheel_hash_mismatch:'+group)
    whl=wheel_manifest(wheel);ref=manifest(Path(reference['installed_root']))
    if not actual==fixed_git==source_rows==whl==ref==binding['source_files']:raise ValueError('source_git_wheel_install_reference_manifest_mismatch:'+group)
    identity_raw,identity_command=run(group+'_identity',[DEPENDENCY_PYTHON,'-I','-B',entry,'identity'])
    identity=identity_raw['runtime_identity'];canonical=hashlib.sha256(encoded({'base_version':identity['base_version'],
        'implementation_revision':identity['implementation_revision'],'files':actual})).hexdigest()
    if canonical!=fixed['canonical'] or identity['source_files']!=actual or identity['source_kind']!='installed_distribution' or identity['distribution_version']!=fixed['release']:
        raise ValueError('actual_controlled_identity_mismatch:'+group)
    schema,schemas_command=run(group+'_schemas',[DEPENDENCY_PYTHON,'-I','-B','-X','utf8','-c',SCHEMA_PROBE,entry])
    if schema['identity']!=identity or not schema['isolated'] or not schema['dont_write_bytecode'] or schema['forbidden_audit_events']:
        raise ValueError('isolated_static_schema_source_mismatch:'+group)
    if schema['numpy_version']!='2.3.5' or schema['pillow_version']!='12.3.0' or schema['spatial_task_only'] is not False:raise ValueError('dependency_or_ordinary_scope_mismatch:'+group)
    tools=schema['tools_list']['result']['tools'];names=[tool['name'] for tool in tools]
    if len(names)!=len(set(names)) or 'human_eye_scene_observe' not in names or 'human_eye_spatial_relations' in names:raise ValueError('ordinary_tool_schema_scope_mismatch:'+group)
    observe=next(tool for tool in tools if tool['name']=='human_eye_scene_observe')
    query=encoded(observe['inputSchema']['properties']['query']).decode()
    if '"task"' not in query or '"surface_nearest"' not in query:raise ValueError('ordinary_task_and_surface_nearest_modes_required')
    return {'commit':fixed['commit'],'entry':str(entry),'entry_sha256':sha(entry),'source_sha256':canonical,
        'installed_root':str(site),'identity':identity,'dependency_python':str(DEPENDENCY_PYTHON),
        'distribution_version':identity['distribution_version'],'wheel':str(wheel),'wheel_sha256':sha(wheel),
        'source_root':str(source),'runtime_sources':actual,'source_git_wheel_install_reference_equal':True,
        'reference_venv':reference['venv'],'reference_installed_root':reference['installed_root'],
        'binding':str(entry.with_name('RUNTIME_BINDING.json')),'binding_sha256':sha(entry.with_name('RUNTIME_BINDING.json')),
        'admin_sha256':binding['admin_sha256'],'deployment_receipt':str(fixed['receipt']),'deployment_receipt_sha256':sha(fixed['receipt']),
        'ordinary_tools_sha256':hashlib.sha256(encoded(tools)).hexdigest(),'ordinary_tool_names':names,
        'ordinary_query_modes':['task','surface_nearest'],'identity_command':identity_command,'schema_command':schemas_command,
        'schema_probe':{'numpy_version':schema['numpy_version'],'pillow_version':schema['pillow_version'],
            'numpy_file':schema['numpy_file'],'pillow_file':schema['pillow_file'],'python_version':schema['python_version'],
            'host_calls':0,'service_constructed':False,'configuration_read':False},
        'ordinary_serve_argv_prefix':[str(DEPENDENCY_PYTHON),'-I','-B',str(entry),'serve'],
        'ordinary_serve_required_suffix':['--config','<owned-isolated-config>'],'spatial_task_only':False}


def fixture_bindings():
    assembly=ROOT/'verification/native_plugin_complex_003';frozen=load(assembly/'FREEZE.json')
    for name in ('scene.blend','private/TRUTH.json','private/author_mesh_snapshots.json'):
        if sha(assembly/name)!=frozen[name]:raise ValueError('frozen_assembly_reference_changed:'+name)
    truth=load(assembly/'private/TRUTH.json')
    if truth['input_snapshot_sha256']!=frozen['private/author_mesh_snapshots.json']:raise ValueError('assembly_oracle_snapshot_binding_mismatch')
    diag=ROOT/'verification/scale_diag_001';freeze=load(diag/'FREEZE.json')
    for name in ('fixtures/D48.blend','fixtures/D48.json','ORACLE.json'):
        if sha(diag/name)!=freeze['files'][name]:raise ValueError('frozen_D48_reference_changed:'+name)
    snapshot=load(diag/'fixtures/D48.json');oracle=load(diag/'ORACLE.json');certificate=next(row for row in oracle['snapshots'] if row['id']=='D48')
    if certificate['snapshot_geometry_sha256']!=hashlib.sha256(encoded(snapshot)).hexdigest() or not certificate['global_nearest_unsigned']['complete']:
        raise ValueError('D48_oracle_worldmesh_binding_mismatch')
    return {'assembly':{'blend':str(assembly/'scene.blend'),'blend_sha256':frozen['scene.blend'],
        'oracle':str(assembly/'private/TRUTH.json'),'oracle_sha256':frozen['private/TRUTH.json'],'state':'assembly.initial',
        'snapshot':str(assembly/'private/author_mesh_snapshots.json'),'snapshot_sha256':frozen['private/author_mesh_snapshots.json'],
        'oracle_admin_only':True,'live_owned_initial_mesh_binding':'pending root Blender preflight'},
        'D48':{'blend':str(diag/'fixtures/D48.blend'),'blend_sha256':freeze['files']['fixtures/D48.blend'],
        'oracle':str(diag/'ORACLE.json'),'oracle_sha256':freeze['files']['ORACLE.json'],'oracle_snapshot_id':'D48',
        'snapshot':str(diag/'fixtures/D48.json'),'snapshot_sha256':freeze['files']['fixtures/D48.json'],
        'oracle_admin_only':True,'live_owned_initial_mesh_binding':'pending root Blender preflight'}}


def main():
    HERE.mkdir(exist_ok=True)
    result={'schema':'complex-004-source-preflight-v1','task':'COMPLEX-004','scope':'PREP_ONLY','passed':False,
        'dependency_python':str(DEPENDENCY_PYTHON),'versions':{},'model_calls':0,'Blender_started':0,
        'performance_runs':0,'serve_processes_started':0,'default_or_formal_configuration_writes':0,
        'new_builds':0,'new_installs':0,'old_data_copies':0,'learning_task_sync':'pending; no legal bound context; no borrowed handle'}
    try:
        references=load(SCALE_INSTALLS)
        for group in ('O','C'):result['versions'][group]=qualify_version(group,references['versions'][group])
        old,new=(result['versions'][g] for g in ('O','C'))
        if old['ordinary_tools_sha256']!=new['ordinary_tools_sha256']:raise ValueError('ordinary_tool_schemas_differ')
        if old['schema_probe']!=new['schema_probe']:raise ValueError('dependency_interpreter_or_schema_import_scope_differs')
        result['ordinary_schema_equal']=True
        old_site,new_site=Path(old['installed_root']),Path(new['installed_root'])
        changed=[a['path'] for a,b in zip(old['runtime_sources'],new['runtime_sources']) if a!=b]
        if changed!=['human_eye_plugin/surface_proximity.py']:raise ValueError('unexpected_runtime_source_differences')
        old_lines=(old_site/changed[0]).read_text(encoding='utf8').splitlines();new_lines=(new_site/changed[0]).read_text(encoding='utf8').splitlines()
        edits=list(difflib.ndiff(old_lines,new_lines));added=sum(line.startswith('+ ') for line in edits);removed=sum(line.startswith('- ') for line in edits)
        if (added,removed)!=(4,0):raise ValueError('source_delta_is_not_exactly_four_added_lines')
        result['product_source_diff']={'changed_files':changed,'added_lines':added,'removed_lines':removed,
            'diff':[line for line in difflib.unified_diff(old_lines,new_lines,fromfile='O/surface_proximity.py',tofile='C/surface_proximity.py',lineterm='')]}
        old_admin=Path(old['entry']).parent;new_admin=Path(new['entry']).parent
        result['entry_template_comparison']=normalized_template(old_admin/'target_runtime_entry.py',new_admin/'target_runtime_entry.py',{'RELEASE_NAME','SOURCE_SHA256','IDENTITY'})
        result['admin_template_comparison']=normalized_template(old_admin/'installed_release.py',new_admin/'installed_release.py',{'_TARGET_ENTRY_SHA256'})
        result['fixtures']=fixture_bindings();result['passed']=True
    except BaseException as exc:
        result['failure']={'type':type(exc).__name__,'message':str(exc)}
        raise
    finally:
        result['script_sha256']=sha(__file__);save(HERE/'SOURCE_PREFLIGHT.json',result)
        print(json.dumps({'passed':result['passed'],'output':str(HERE/'SOURCE_PREFLIGHT.json'),
            'versions':{g:v['source_sha256'] for g,v in result['versions'].items()}}))


if __name__=='__main__':main()
