"""Synthetic/static checks for argv/config evidence; no Codex/model/Blender/RPC."""
import ast
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile

HERE=Path(__file__).resolve().parent
candidate=json.loads((HERE/'DESKTOP_CANDIDATE.json').read_bytes())
argv=candidate['candidate_common_argv']
assert argv[0]==candidate['cli_path']
assert all(flag in argv for flag in ('exec','--ignore-user-config','--ephemeral','--json','--strict-config'))
assert '--dangerously-bypass-hook-trust' not in argv
assert '--dangerously-bypass-approvals-and-sandbox' not in argv
assert '--ignore-rules' not in argv
overrides=[argv[i+1] for i,value in enumerate(argv) if value=='-c']
for item in overrides:tomllib.loads(item)
merged=tomllib.loads('\n'.join(overrides))
assert merged['model']=='gpt-6.1-sol' and merged['model_reasoning_effort']=='ultra'
assert merged['model_provider']=='openai_http' and merged['service_tier']=='default'
assert merged['forced_login_method']=='chatgpt'
provider=merged['model_providers']['openai_http']
assert provider==candidate['provider_definition']
assert provider['requires_openai_auth'] and provider['wire_api']=='responses'
assert provider['base_url']=='https://chatgpt.com/backend-api/codex'
assert merged['features']['shell_tool'] and merged['features']['view_image']
assert all(not merged['features'][key] for key in ('hooks','apps','memories','multi_agent','multi_agent_v2','goals','plugins','remote_plugin'))
assert all(not row['enabled'] for row in merged['skills']['config'])
assert all(not row['enabled'] for row in merged['plugins'].values())
assert all(not row['enabled'] for row in merged['mcp_servers'].values())
assert all(candidate[key]==0 for key in ('consumer_starts','Blender','RPC','API_calls'))
for name in ('inspect_local.py','inspect_desktop.py','check_static.py'):
    ast.parse((HERE/name).read_bytes(),filename=name)
with zipfile.ZipFile(HERE/'GENERATED_SCHEMAS.zip') as archive:
    for filename,prefix in (('LOCAL_SCHEMA_EXTRACT.json','app_schema/'),('DESKTOP_SCHEMA_EXTRACT.json','desktop_schema/')):
        manifest=json.loads((HERE/filename).read_bytes())['manifest']
        for row in manifest:
            raw=archive.read(prefix+row['path'])
            assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
result=dict(passed=True,common_override_entries=len(overrides),synthetic_TOML_parse_only=True,
    schema_archive_members=len(archive.namelist()),syntax_files=3,consumer_starts=0,Blender=0,RPC=0,API_calls=0,
    actual_runtime_config_validation=False,actual_injection_verification=False,all_tools_hard_limit_verified=False)
(HERE/'STATIC_CHECK.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps(result))
