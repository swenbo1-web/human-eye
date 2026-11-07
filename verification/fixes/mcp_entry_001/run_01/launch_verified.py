"""Isolated QA bootstrap into the unchanged installed production stdio entry."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import sysconfig
import types
from types import MappingProxyType

parser=argparse.ArgumentParser()
parser.add_argument('--identity',type=Path,required=True)
parser.add_argument('--config',type=Path,required=True)
parser.add_argument('--evidence',type=Path,required=True)
args=parser.parse_args()
identity=json.loads(args.identity.read_text('utf8'))['identity']
root=Path(sysconfig.get_path('purelib')).resolve()
manifest=identity['source_files']
assert len(manifest)==131 and identity['source_sha256']=='fb5a4485c935512c1521b160c55e6034a30ae8177e2662b6a132fec5d85a4509'
blobs={row['path']:(root/row['path']).read_bytes() for row in manifest}
assert len(blobs)==131
for row in manifest:
    assert hashlib.sha256(blobs[row['path']]).hexdigest()==row['sha256']
payload=dict(base_version=identity['base_version'],implementation_revision=identity['implementation_revision'],files=manifest)
assert hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()==identity['source_sha256']
helper_path=root/'human_eye_plugin/verified_source_loader.py'
helper_blob=blobs['human_eye_plugin/verified_source_loader.py']
helper=types.ModuleType('_human_eye_verified_source_bootstrap')
helper.__file__=str(helper_path)
sys.modules[helper.__name__]=helper
exec(compile(helper_blob,str(helper_path),'exec',dont_inherit=True),helper.__dict__)
guard=helper.install(root,manifest,sources=MappingProxyType(blobs),bootstrap_module=helper)
# Existing loader-supported namespace: avoid executing the unrelated SDK
# facade while selecting the production entry. Its source is still pinned.
package=types.ModuleType('human_eye_plugin')
package.__path__=[str(root/'human_eye_plugin')]
guard.allow_namespace(package)
sys.modules[package.__name__]=package
from human_eye_plugin import production_server, runtime_identity
assert guard.verify_loaded()
assert runtime_identity.runtime_identity()['source_sha256']==identity['source_sha256']
assert runtime_identity.runtime_identity()['source_kind']=='installed_distribution'

def record(name,value):
    (args.evidence/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')

record('BOOTSTRAP.json',dict(entry='unchanged production_server.main -> original run_stdio_mcp_server',
    root=str(root),source_sha256=identity['source_sha256'],source_count=131,
    loader_sha256=hashlib.sha256(helper_blob).hexdigest(),guard_protocol=guard.protocol,
    initial_guard_verify_loaded=True,all_manifest_bytes_frozen=True,
    bootstrap_scope='thin controlled QA entry, no desktop activation or product patch'))
code=None
try:
    code=production_server.main(['--config',str(args.config)])
finally:
    owned={name:module for name,module in sys.modules.items() if guard._owned_name(name)}
    witnessed=all(guard._executed.get(id(module),(None,None))[0] is module
                  or guard._namespaces.get(id(module)) is module for module in owned.values())
    source_check=runtime_identity.check_task_source()
    record('BOOTSTRAP_EXIT.json',dict(production_exit_code=code,loaded_engine_module_count=len(owned),
        every_loaded_engine_module_has_existing_guard_execution_witness=witnessed,
        task_source_check=source_check,source_sha256=identity['source_sha256']))
raise SystemExit(code)
