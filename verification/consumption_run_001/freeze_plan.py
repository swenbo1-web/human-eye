"""Create review artifacts without importing product or starting consumers."""
from datetime import datetime,timezone
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
def save(name,value):(HERE/name).write_text(json.dumps(value,indent=2,ensure_ascii=True)+'\n',encoding='utf8')
material=load(HERE/'materials/MATERIAL_MANIFEST.json')
entry=load(HERE/'entry_check/DESKTOP_CANDIDATE.json')
identity=load(ROOT/'verification/surface_nearest_entry_001/offline_run_02/EXECUTION_IDENTITY.json')
assert identity['runtime_source_sha256']=='01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de'
sources={}
for row in identity['manifest']:
    raw=subprocess.check_output(['git','show','17db41c481397965a9bae3f4571c59a5a80939c9:'+row['path']],cwd=ROOT)
    assert sha(raw)==row['sha256'] and raw==(ROOT/row['path']).read_bytes()
    sources[row['path']]=raw
assert len(sources)==131
tree=ast.parse(sources['human_eye_plugin/runtime_identity.py'])
constants={n.targets[0].id:ast.literal_eval(n.value) for n in tree.body
    if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)
    and n.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION')}
canonical=dict(base_version=constants['BASE_VERSION'],implementation_revision=constants['IMPLEMENTATION_REVISION'],files=identity['manifest'])
assert sha(json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())==identity['runtime_source_sha256']
with zipfile.ZipFile(HERE/'PRODUCT_BYTES.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
    for name,raw in sources.items():archive.writestr(name,raw)
assignment=Path('D:/hefe/verification/fixes/20261107_nearest_contract/CONSUMPTION_RUN_PREP_ASSIGNMENT.md')
assert sha(assignment.read_bytes())=='216648129320b30444347bd025e5a6cd958b4180fc709215132ea79723bef299'
reviews=[assignment]+[assignment.parent/name for name in ('SURFACE_ENTRY_REVIEW.md','CONSUMPTION_PREP_REVIEW.md','review_consumption_prep/entry/ROUTE.md','CONSUMPTION_BUDGET_CLARIFICATION_001.md')]
plan=dict(cycle_id='CONSUMPTION-RUN-PREP-001',future_cycle_id='CONSUMPTION-RUN-001',
    prepared_utc=datetime.now(timezone.utc).isoformat(),execution_ready=False,
    execution_blockers=[
        'Actual exec model-visible injection/tool registry not inspected: ignore-user-config only omits config.toml. Global skills/plugins/managed hooks must be ruled out before clean N can be claimed.',
        '1MiB prepublication bound across builtin shell/image/tool outputs not verified; bridge cap alone covers MCP, prompt and final, builtin monitoring occurs after delivery.',
    ],
    source_commit='17db41c481397965a9bae3f4571c59a5a80939c9',source_sha256=identity['runtime_source_sha256'],
    source_count=131,product_manifest=identity['manifest'],product_zip_sha256=sha((HERE/'PRODUCT_BYTES.zip').read_bytes()),
    material_manifest_sha256=sha((HERE/'materials/MATERIAL_MANIFEST.json').read_bytes()),
    materials_source_commit=material['source_commit'],cells=material['cell_order'],
    limits=dict(answer_seconds=180,chain_seconds=600,cleanup_reserve_seconds=60,model_answers=8,native_sessions=8,
        action_observation_threshold=8,public_text_bytes_per_answer=1048576,execute_rpc_per_answer=128,close_rpc_per_answer=1,
        total_physical_rpc=1032,output_tokens_hard_limit=None),
    limits_scope=dict(answer_clock='dispatch before asset/host startup; includes queueing/MCP schema/ID discovery/errors/fallback/final',
        execute_rpc='shared native+HE actual owned endpoint connection admission; original NativeSession max_calls128 capability frozen separately from logical actions',
        actions='root clarification supersedes hard8: diagnostic threshold only; more actions never cause threshold termination or invalidation',
        public_text='exact question+MCP full tool directory+tool text/errors+observed shell output+final; conservative server-side counts distinct from model effective input; not double sum layers',
        hard_output_tokens='unavailable; same both arms, no invented4096 cap',
        image='common optional PNG relay, at most1 image <=768x768; actual construction/host delivery capability unverified',
        parent_window='proposed8 distinct chains, each original600s with60s reserved cleanup;8*(128execution+1close)=1032 physical RPC maximum plan, not granted; failed starts still occupy scheduled cells'),
    image_limits=dict(max_images=1,max_single_pixels=589824,max_total_pixels=589824),max_image_dimension=768,
    codex=dict(executable=entry['cli_path'],sha256=entry['cli_sha256'],model='gpt-6.1-sol',effort='ultra',
        provider='openai_http',service_tier='default',settings=entry['candidate_common_overrides'],
        auth='existing ChatGPT login status only; no auth/key file content read/copied',actual_backend='unexposed',
        availability='local catalogue advertises alias/effort/image; no provider request or answer attempted'),
    blender='D:/Tools/blender5.2/blender.exe',blender_sha256='284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb',
    python=dict(path=sys.executable,sha256=sha(Path(sys.executable).read_bytes()),version=sys.version),
    neutral_run_root=str(Path(os.environ.get('LOCALAPPDATA','C:/Users/Administrator/AppData/Local'))/'Temp/he-consumption-run-001'),
    privacy=dict(automatic_injection='only unchanged per-task911-byte question, common native schema, P-only actual HE observation descriptor via normalMCP; no manual inventory or knownID free handoff',
        consumer_workdir='fresh neutral outside repository ancestor chain; no truth/admin/oldraw or case source names copied',
        hard_file_isolation=False,diagnostic_class='nonblind engineering diagnostic; full Python/shell can read account-visible files',
        public_record='whitelist public tool args/results, final and numeric usage only; reasoning/system/encrypted dispatched text not exported',
        invalidation='answer/admin/history/author-code access, source/config contamination, unsupported event/schema delivery, budget overrun, unrecovered host state => invalid comparison but retained denominator'),
    measurement=dict(model_answers='8 scheduled unique contexts, no replacement; failures remain8 denominator',
        provider_requests=None,fees=None,token_usage='each fresh exec terminal usage once;cached subset ofinput,reasoning subset ofoutput; never sum snapshots',
        schema='retain actual initialize/list wire and complete registered descriptor bytes; host-filtered/effectively delivered schema bytes remain unexposed absent public evidence',
        native_cache='per-answer persistent Python namespace allowed; new NativeSession each cell',
        HE_cache='fresh service/state perP cell; ordinary audit/cache records, no QA profilecounter',
        clocks='cell dispatch, owner startup, Codex Popen, first publictool/final, processwait, nativeclose; nested stages not summed',
        costs='production inside HE/native, experimental metering/launch/cleanup separately; inseparable model-host orchestration labelled; no bytes→token or subscription dollar inference'),
    scoring=dict(protocol='frozen materials plus root amendments, no new truth solving in preparation',
        unsigned_distance='reject bool/negative/nonfinite before display tolerance',
        reviewer='if isolated Pro agent, label Pro agent; never human',
        credit='independent answer fields and evidence sufficiency; selfreported complete is not global certification; T04 unknown alone task incomplete',
        attribution='P may choose zeroHE; then no engine credit; compare speed only correct pairs and report all4task coverage',
        images='common prepared optional native image relay; actual availability not validated. If absent, only jointly frozen numeric/text diagnostic, never visual/full baseline victory'),
    actual_activity=dict(model_answers=0,Blender_sessions=0,native_RPC=0,product_RPC=0,API_calls=0,product_imports=0),
    unverified_in_unique_batch=['exact model/backend availability without fallback','normal MCP registration and actual filtered schema delivery',
        'actual context injection including managed layers','public JSON event coverage on this CLI/model code_mode',
        'native PNG relay/Pillow/host image delivery and construction limits','no answer-file access (not hard guaranteed)',
        'actual token usage and product/native cache work accounting'],
    unverified_rule='not a preliminary consumer probe; first cell attempt counts once, failures retained; no replacement or change of question/model/source',
    source_documents=[dict(path=str(p),sha256=sha(p.read_bytes())) for p in reviews])
components=['runner.py','bridge.py','he_bootstrap.py','freeze_plan.py','preparation_checks.py','tests_bridge.py','tests_runner.py','PRODUCT_BYTES.zip',
    'materials/MATERIAL_MANIFEST.json','materials/'+material['neutral_helper']['local_path']]
components += ['materials/'+t['prompt_path'] for t in material['tasks']]
plan['runtime_components']=[dict(path=p,sha256=sha((HERE/p).read_bytes())) for p in components]
save('PLAN.json',plan)
save('COST_RECORD_TEMPLATE.json',dict(cell=None,source_sha256=plan['source_sha256'],dispatch_ns=None,
    scheduled_answer=1,provider_requests=None,tool_actions=None,physical_RPC=None,
    initialization_and_full_tool_catalogue=dict(TX=None,RX=None,registered_bytes=None,model_delivered_bytes=None),
    production=dict(native_TX=None,native_RX=None,HE_TX=None,HE_RX=None,capture_count=None,pair_cache=None,wire_evidence=[]),
    public_payload=dict(prompt_bytes=None,tool_text_bytes=None,final_bytes=None,image_generated=None,image_delivered=None),
    usage=None,fees=None,currency=None,queue_wall_ns=None,answer_wall_ns=None,whole_cell_wall_ns=None,cleanup_wall_ns=None,
    experimental_management_wall_ns=None,inseparable_wall_ns=None,errors=[],fallbacks=[],retries=0,valid_comparison=None,
    failures_count_in_denominator=True,actual_model_backend='unexposed',hidden_reasoning_exported=False))
print(json.dumps(dict(execution_ready=False,cells=8,source_count=131,plan_sha256=sha((HERE/'PLAN.json').read_bytes()),product_zip_sha256=plan['product_zip_sha256'])))
