"""Desktop CLI metadata/config whitelist; no prompt, server or model request."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import tomllib
import urllib.parse
import zipfile

OUT=Path(__file__).resolve().parent
EXE=Path('C:/Users/Administrator/AppData/Local/OpenAI/Codex/bin/f71a721e0e6193a9/codex.exe')
HOME=Path('C:/Users/Administrator/.codex')
sha=lambda b:hashlib.sha256(b).hexdigest()
commands=[]
for label,args in [('desktop_version',['--version']),('desktop_exec_help',['exec','--help']),
    ('desktop_login_status',['login','status'])]:
    started=time.perf_counter_ns()
    done=subprocess.run([str(EXE),*args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (OUT/(label+'.stdout.txt')).write_bytes(done.stdout)
    (OUT/(label+'.stderr.txt')).write_bytes(done.stderr)
    commands.append(dict(argv=[str(EXE),*args],exit_code=done.returncode,elapsed_ns=time.perf_counter_ns()-started,
        stdout_bytes=len(done.stdout),stderr_bytes=len(done.stderr)))

config_raw=(HOME/'config.toml').read_bytes()
config=tomllib.loads(config_raw.decode('utf-8-sig'))
provider=config['model_providers']['openai_http']
assert set(provider)=={'name','wire_api','requires_openai_auth','supports_websockets','supports_standalone_web_search','base_url'}
url=urllib.parse.urlsplit(provider['base_url'])
assert not (url.username or url.password or url.query or url.fragment)
assert url.scheme=='https' and url.hostname=='chatgpt.com'
assert url.path=='/backend-api/codex'
provider_safe={k:provider[k] for k in ('name','wire_api','requires_openai_auth','supports_websockets','supports_standalone_web_search','base_url')}
selected=dict(model=config['model'],model_reasoning_effort=config['model_reasoning_effort'],
    model_provider=config['model_provider'],service_tier=config.get('service_tier'))
assert selected==dict(model='gpt-6.1-sol',model_reasoning_effort='ultra',model_provider='openai_http',service_tier='default')

cache_raw=(HOME/'models_cache.json').read_bytes()
cache=json.loads(cache_raw)
model=next(r for r in cache['models'] if r['slug']==selected['model'])
keys=('slug','display_name','default_reasoning_level','supported_reasoning_levels','service_tiers','input_modalities',
    'context_window','max_context_window','supported_in_api','visibility','experimental_supported_tools',
    'supports_image_detail_original','tool_mode')
cache_metadata={k:model[k] for k in keys if k in model}
assert 'ultra' in {r['effort'] for r in model['supported_reasoning_levels']}

settings=dict(selected)
settings.update({'model_providers.openai_http':provider_safe,'forced_login_method':'chatgpt',
    'hide_agent_reasoning':True,'show_raw_agent_reasoning':False,'web_search':'disabled',
    'features.hooks':False,'features.apps':False,'features.memories':False,'memories.use_memories':False,
    'features.multi_agent':False,'features.multi_agent_v2':False,'features.goals':False,
    'features.remote_plugin':False,'features.plugins':False,'features.skip_host_skill_discovery':True,
    'skills.bundled.enabled':False,'skills.include_instructions':False,'project_doc_max_bytes':0,
    'features.shell_tool':True,'features.view_image':True})
settings['skills.config']=[dict(path=str(p),enabled=False) for base in
    (Path('C:/Users/Administrator/.agents/skills'),HOME/'skills/.system') for p in sorted(base.glob('*/SKILL.md'))]
for name in config.get('plugins',{}):settings['plugins.'+json.dumps(name)+'.enabled']=False
for name in config.get('mcp_servers',{}):settings['mcp_servers.'+name+'.enabled']=False

def toml_value(value):
    if isinstance(value,dict):return '{'+', '.join(json.dumps(k)+'='+toml_value(v) for k,v in value.items())+'}'
    if isinstance(value,list):return '['+', '.join(toml_value(v) for v in value)+']'
    return json.dumps(value,ensure_ascii=False)
overrides=[k+'='+toml_value(v) for k,v in settings.items()]
argv=[str(EXE),'exec','--ignore-user-config','--ephemeral','--json','--strict-config',
    '--skip-git-repo-check','-C','<new-neutral-cell-cwd>','-o','<cell-final-path>']
for item in overrides:argv+=['-c',item]
argv+=['<root-appended-native-and-P-only-HE-registration>','-']
proposal=dict(cli_path=str(EXE),cli_sha256=sha(EXE.read_bytes()),cli_bytes=EXE.stat().st_size,
    config_source_sha256=sha(config_raw),selected_settings=selected,provider_definition=provider_safe,
    candidate_common_overrides=settings,candidate_common_argv=argv,
    capability_cache=dict(path=str(HOME/'models_cache.json'),sha256=sha(cache_raw),fetched_at=cache.get('fetched_at'),
        client_version=cache.get('client_version'),model_metadata=cache_metadata),
    current_parent_process_environment_names_only=sorted(k for k in os.environ if
        k.startswith('CODEX') or 'AGENT_LEARNING' in k or k.startswith('HUMAN_EYE')),
    future_environment_rule='Do not inherit API keys/access tokens or parent task/context bindings; preserve original CODEX_HOME/default login store without copying auth contents.',
    normal_MCP_registration='Root adds actual native command/args/required and P-only production HE enabled_tools allowlist; no hand CLI forwarding.',
    runtime_model_backend='unexposed',runtime_model_availability='unverified_without_consumer',
    actual_registered_tools_and_actual_injection='unverified_until_authorized_unique_batch; config/feature checks alone do not prove it',
    max_output_tokens_hard_limit='not exposed by exec help/local config schema; do not claim4096hardlimit',
    all_tools_hard_action_limit='not verified; MCP broker budget is not a general shell/view_image/write_stdin gate',
    hook_limit_dependency='A new owned PreToolUse hook requires exact-hash trust; task forbids trust changes or bypass. No installed max_tool_calls exposed; hosted/specialized paths and write_stdin have documented hook gaps.',
    candidate_not_execution_authorization=True,consumer_starts=0,Blender=0,RPC=0,API_calls=0)
(OUT/'DESKTOP_CANDIDATE.json').write_text(json.dumps(proposal,indent=2,ensure_ascii=False)+'\n',encoding='utf8')

desktop_schema=OUT/'desktop_schema'
files=[p for p in sorted(desktop_schema.rglob('*.json'))]
manifest=[dict(path=p.relative_to(desktop_schema).as_posix(),bytes=p.stat().st_size,sha256=sha(p.read_bytes())) for p in files]
config_schema=json.loads((desktop_schema/'v2/ConfigReadResponse.json').read_bytes())
requirements=json.loads((desktop_schema/'v2/ConfigRequirementsReadResponse.json').read_bytes())
defs=config_schema.get('definitions',{})
extract={k:defs[k] for k in ('Config','ForcedLoginMethod','ReasoningEffort','ServiceTier') if k in defs}
rdefs=requirements.get('definitions',{})
extract.update({k:rdefs[k] for k in ('ConfiguredHookMatcherGroup','ConfiguredHookHandler','ManagedHooksRequirements') if k in rdefs})
text='\n'.join(p.read_text('utf8') for p in files)
(OUT/'DESKTOP_SCHEMA_EXTRACT.json').write_text(json.dumps(dict(generator_argv=[str(EXE),'app-server','generate-json-schema','--experimental'],
    static_generation_only=True,manifest=manifest,definitions=extract,
    exact_text_search=dict(max_tool_calls='max_tool_calls' in text,max_output_tokens='max_output_tokens' in text,PreToolUse='PreToolUse' in text)),indent=2)+'\n',encoding='utf8')
with zipfile.ZipFile(OUT/'GENERATED_SCHEMAS.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
    for base in (OUT/'app_schema',desktop_schema):
        for path in sorted(base.rglob('*.json')):archive.write(path,path.relative_to(OUT).as_posix())
(OUT/'DESKTOP_READONLY_COMMANDS.json').write_text(json.dumps(dict(at_utc=datetime.now(timezone.utc).isoformat(),commands=commands,
    no_model_prompt=True,no_model_request=True,no_Blender=True,no_MCP_server_or_RPC=True,no_auth_content_read=True),indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(cli_sha256=proposal['cli_sha256'],selected=selected,schema_files=len(files),cache_model=model['slug'],
    consumer_starts=0,Blender=0,RPC=0,API_calls=0)))
