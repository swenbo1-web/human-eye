"""Read-only CLI/config inspection. Never starts an agent, server, or model."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import tomllib

OUT=Path(__file__).resolve().parent
CODEX=Path('C:/Users/Administrator/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe')
USER=Path('C:/Users/Administrator/.codex')
sha=lambda b:hashlib.sha256(b).hexdigest()
commands=[]

def run(label,args,*,project=None):
    begun=time.perf_counter_ns()
    done=subprocess.run([str(CODEX),*args],cwd=project,stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    row=dict(label=label,argv=[str(CODEX),*args],exit_code=done.returncode,
        elapsed_ns=time.perf_counter_ns()-begun,stdout_bytes=len(done.stdout),stderr_bytes=len(done.stderr),
        stdout_sha256=sha(done.stdout),stderr_sha256=sha(done.stderr))
    commands.append(row)
    return done.stdout,done.stderr

for label,args in [('version',['--version']),('exec_help',['exec','--help']),
        ('login_status',['login','status']),('debug_help',['debug','--help']),
        ('prompt_input_help',['debug','prompt-input','--help']),
        ('schema_help',['app-server','generate-json-schema','--help']),
        ('features',['features','list'])]:
    stdout,stderr=run(label,args)
    # These exact readonly commands contain help/version/status and feature flags only.
    (OUT/(label+'.stdout.txt')).write_bytes(stdout)
    (OUT/(label+'.stderr.txt')).write_bytes(stderr)

config_path=USER/'config.toml'
config=tomllib.loads(config_path.read_text('utf-8-sig'))
allowed=('model','model_provider','model_reasoning_effort','service_tier','model_reasoning_summary',
    'model_verbosity','approval_policy','sandbox_mode','profile','project_doc_max_bytes',
    'project_doc_fallback_filenames','features','windows','skills')
safe={key:config[key] for key in allowed if key in config}
safe['mcp_servers']={name:{key:value for key,value in row.items() if key in
    ('enabled','required','command','cwd','enabled_tools','disabled_tools','startup_timeout_sec','tool_timeout_sec')}
    for name,row in config.get('mcp_servers',{}).items()}
safe['plugins']={name:dict(enabled=row.get('enabled')) for name,row in config.get('plugins',{}).items()}
safe['hooks']=dict(present=bool(config.get('hooks')),events=list(config.get('hooks',{})),
    state=config.get('hooks',{}).get('state'))
safe['provider_metadata']={name:{key:value for key,value in row.items() if key in
    ('name','wire_api','requires_openai_auth','supports_websockets')}
    for name,row in config.get('model_providers',{}).items()}
safe['profile_names']=list(config.get('profiles',{}))
safe['instructions_metadata']={key:dict(present=bool(config.get(key)),bytes=len(str(config.get(key,'')).encode()))
    for key in ('developer_instructions','user_instructions','instructions')}
safe['config_sha256']=sha(config_path.read_bytes())
safe['environment_presence_only']={name:bool(os.environ.get(name)) for name in
    ('CODEX_HOME','CODEX_THREAD_ID','OPENAI_API_KEY','CODEX_API_KEY','CODEX_ACCESS_TOKEN')}
safe['auth_policy']='Only codex login status; no auth/key/token file read, hash, export, copy or value print.'
(OUT/'USER_CONFIG_WHITELIST.json').write_text(json.dumps(safe,indent=2)+'\n',encoding='utf8')

# No refresh: bundled catalog and local cache do not establish backend availability.
catalog_raw,catalog_err=run('bundled_catalog',['debug','models','--bundled'])
catalog=json.loads(catalog_raw)
model_rows=catalog if isinstance(catalog,list) else catalog.get('models',[])
model_metadata=[]
for row in model_rows:
    slug=row.get('slug',row.get('id'))
    if slug!=safe.get('model'):continue
    keys=('slug','id','display_name','supported_reasoning_levels','default_reasoning_level',
        'supported_reasoning_efforts','context_window','supports_parallel_tool_calls','supports_reasoning_summaries',
        'supported_in_api','visibility','priority','supports_image_detail_original')
    model_metadata.append({key:row[key] for key in keys if key in row})
(OUT/'MODEL_CATALOG_WHITELIST.json').write_text(json.dumps(dict(source='installed bundled catalog --bundled; no refresh',
    configured_model=safe.get('model'),configured_effort=safe.get('model_reasoning_effort'),
    configured_provider=safe.get('model_provider'),configured_service_tier=safe.get('service_tier'),
    matching_model_rows=model_metadata,actual_runtime_backend='unexposed_before_authorized_consumer',
    actual_availability='unverified_without_model_request',instructions_or_templates_exported=False),indent=2)+'\n',encoding='utf8')

metadata=[]
for path in [USER/'AGENTS.md',USER/'hooks.json',USER/'requirements.toml',
    Path('C:/ProgramData/OpenAI/Codex/requirements.toml'),Path('C:/ProgramData/Codex/requirements.toml')]:
    row=dict(path=str(path),exists=path.is_file())
    if path.is_file():row.update(bytes=path.stat().st_size,sha256=sha(path.read_bytes()))
    metadata.append(row)
# Skill names/paths only, not skill bodies or reference evidence.
skill_roots=[Path('C:/Users/Administrator/.agents/skills'),USER/'skills/.system']
skill_files=[path for base in skill_roots for path in base.glob('*/SKILL.md')]
metadata.append(dict(skill_catalog_paths=[str(path) for path in sorted(skill_files)]))
(OUT/'CONTEXT_SOURCES_METADATA.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf8')

schema=OUT/'app_schema'
schema_manifest=[dict(path=str(path.relative_to(schema)).replace('\\','/'),bytes=path.stat().st_size,
    sha256=sha(path.read_bytes())) for path in sorted(schema.rglob('*.json'))]
source=schema/'v2/ConfigReadResponse.json'
parsed=json.loads(source.read_bytes());definitions=parsed.get('definitions',{})
selected={name:value for name,value in definitions.items() if name in
    ('Config','ForcedLoginMethod','ReasoningEffort','ServiceTier')}
req=schema/'v2/ConfigRequirementsReadResponse.json'
required=json.loads(req.read_bytes()).get('definitions',{})
for name in ('ConfiguredHookMatcherGroup','ConfiguredHookHandler','ManagedHooksRequirements'):
    if name in required:selected[name]=required[name]
serialized='\n'.join(path.read_text('utf8') for path in schema.rglob('*.json'))
(OUT/'LOCAL_SCHEMA_EXTRACT.json').write_text(json.dumps(dict(generator='codex app-server generate-json-schema --experimental',
    generator_starts_app_server=False,manifest=schema_manifest,definitions=selected,
    exact_text_search=dict(max_tool_calls='max_tool_calls' in serialized,max_output_tokens='max_output_tokens' in serialized,
        PreToolUse='PreToolUse' in serialized)),indent=2)+'\n',encoding='utf8')
(OUT/'READONLY_COMMANDS.json').write_text(json.dumps(dict(at_utc=datetime.now(timezone.utc).isoformat(),
    commands=commands,no_model_prompt=True,no_model_request=True,no_Blender=True,no_MCP_server_or_RPC=True,
    no_auth_content_read=True,cli_launcher_sha256=sha(CODEX.read_bytes())),indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(readonly_commands=len(commands),model=safe.get('model'),effort=safe.get('model_reasoning_effort'),
    provider=safe.get('model_provider'),tier=safe.get('service_tier'),matching_bundled_models=len(model_metadata),
    source_schema_files=len(schema_manifest),consumer_starts=0,Blender=0,RPC=0)))
