"""Freeze the one eight-answer diagnostic; no Blender or observe invocation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys
import sysconfig

from human_eye_plugin.runtime_identity import runtime_identity, check_source_drift
from human_eye_plugin.live_spatial_mcp import LIVE_MCP_TOOLS_SCHEMA

ROOT = Path(__file__).resolve().parents[1]
PIN = 'fb5a4485c935512c1521b160c55e6034a30ae8177e2662b6a132fec5d85a4509'
ORDER = [('S','P','W1'), ('S','N','W1'), ('S','N','W2'), ('S','P','W2'),
         ('G','P','W2'), ('G','N','W2'), ('G','N','W1'), ('G','P','W1')]
CORE = dict(S='当前 Object_01 与 Object_02 的三角表面最小距离是多少米？给出从前者到后者的单位方向，以及两者各自的边界边数和非流形边数。',
            G='报告当前两对象的最小表面距离、最近点方向，以及实体穿插状态。区分有数值答案、不适用和当前无法判定的项目，并说明原因。')
WORDING = dict(W1='给出简短可核查依据，说明依据来自什么当前几何。', W2='说明实际采用的证据及其来源。')


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


identity = runtime_identity()
assert identity['source_kind'] == 'installed_distribution'
assert identity['source_sha256'] == PIN and len(identity['source_files']) == 131
assert check_source_drift()['compatible']
purelib = Path(sysconfig.get_path('purelib')).resolve()
assert Path(sys.modules['human_eye_plugin.runtime_identity'].__file__).resolve().is_relative_to(purelib)
tool = next(row for row in LIVE_MCP_TOOLS_SCHEMA if row['name'] == 'human_eye_scene_observe')
description = tool['description']
assert len(description.encode('utf8')) == 1214
save(ROOT/'SOURCE_CHECK.json', dict(identity=identity, source_drift=check_source_drift(),
    executable=sys.executable, purelib=str(purelib), checked_utc=datetime.now(timezone.utc).isoformat()))
save(ROOT/'prompts/OBSERVE_TOOL.json', tool)
(ROOT/'prompts/OBSERVE_DESCRIPTION.txt').write_text(description, encoding='utf8')

window = dict(task='EVIDENCE-CONSUME-001', route_started_epoch=1794036043,
    route_deadline_epoch=1794043243, deadline_unix=1794042043,
    route_started_utc='2026-11-07T07:20:43Z', deadline_utc='2026-11-07T09:00:43Z',
    route_deadline_utc='2026-11-07T09:20:43Z', stop_new_experiments_utc='2026-11-07T08:45:43Z',
    host_turn_id='01a1b4e2-2a3b-7f61-9607-1b6d9e6e80ee', host_started_utc='2026-11-07T07:21:23Z',
    host_start_precision='read_thread whole-second precision, conservatively earlier',
    chain_seconds=600, answer_seconds=150, minimum_remaining_to_start_chain_seconds=900,
    maximum_answers=8, maximum_qualification_sessions=2, maximum_qualification_observe=2,
    maximum_qualification_raw_reads=2, maximum_qa_recovery=1, vertex_updates=0,
    source_sha256=PIN, source_count=131, baseline_head='c3b93d34d1cbdc370b3630d540490b79093b3d82',
    assignment_sha256='f3c6742c062f5d9748ff66a9020447f88bee864b344323c4f977f6150a339842')
save(ROOT/'WINDOW.json', window)

python = Path(sys.executable).resolve().as_posix()
cli = (ROOT/'qa/cli.py').as_posix()
labels = list(range(1, 9))
random.Random(1794036043).shuffle(labels)
bindings, prompt_index = [], []
for sequence, ((case, condition, wording), label) in enumerate(zip(ORDER, labels), 1):
    chain_id = '_'.join((case, condition, wording))
    workspace = (ROOT/'runs'/chain_id).as_posix()
    prompt = f'''你正在完成一个只读当前几何诊断。每条链拥有包括启动的600秒总额度，本问最多150秒，只给一份自然语言最终回答。可以自由使用普通bpy/Python、数学、自己的脚本、算法、索引、持久变量和缓存。当前native进程中已有bpy，变量在同一链保留。可使用自己的工作区编写脚本。不要修改场景，不打开共享GUI，不读取作者资产、truth、产品源码、其他组工作区或其他会话资料。只访问自己的工作区和给定工具入口。遇到错误如实保留，在剩余预算内使用可用能力。场景原始数据可以按需要通过native读取。

工作区为 {workspace}
Python为 {python}
工具入口为 {cli}

原生调用形式为
& '{python}' -I -B '{cli}' native --workspace '{workspace}' --script '{workspace}/your_script.py'

同一链累计限额为48次公开调用，262144数据字节、98304控制字节、128worker RPC、262144 native代码字节。native单次30秒，图片0。入口保存实际CLI stdout/stderr并原样交付。工具选择自由。
'''
    if condition == 'P':
        prompt += f'''
另有可用observe入口，单次20秒。工具原文说明如下，保留原始英文。

{description}

调用形式示例为
& '{python}' -I -B '{cli}' observe --workspace '{workspace}' --query-literal "{{'mode':'task','objects':[{{'name':'Object_01'}},{{'name':'Object_02'}}],'requested_facts':['pair_relation']}}" --detail brief
同一既有task入口也接受aabb、center_delta、axis_gap、surface_clearance、solid_relation、nearest_witness、surface_proximity。
'''
    question = CORE[case] + WORDING[wording]
    prompt += '\n任务单位米。距离精度约1e-6m，单位方向精度约1e-6。\n' + question + '\n'
    path = ROOT/'prompts'/(chain_id+'.txt')
    path.write_text(prompt, encoding='utf8')
    prompt_index.append(dict(sequence=sequence, chain_id=chain_id, path=str(path),
        sha256=sha(path), utf8_bytes=len(prompt.encode('utf8')),
        description_utf8_bytes=1214 if condition=='P' else 0,
        description_delivery_count=1 if condition=='P' else 0))
    bindings.append(dict(sequence=sequence, chain_id=chain_id, answer_id='A%02d'%label,
        case=case, condition=condition, wording=wording, question=question,
        workspace=workspace, prompt_path=str(path), prompt_sha256=sha(path),
        status='planned', agent_path=None, thread_id=None, dispatch_utc=None, final_saved_utc=None,
        answer_timeout_sec=150, chain_started_unix=None))
save(ROOT/'dispatch/BINDINGS.json', dict(schema='evidence-consume-dispatch-v1', bindings=bindings))
save(ROOT/'PROMPT_INDEX.json', prompt_index)
save(ROOT/'FROZEN_PLAN.json', dict(task='EVIDENCE-CONSUME-001', frozen_utc=datetime.now(timezone.utc).isoformat(),
    source_sha256=PIN, source_count=131, order=['_'.join(row) for row in ORDER], maximum_answers=8,
    chain_seconds=600, answer_seconds=150, minimum_remaining_to_start_chain_seconds=900,
    public_calls_per_chain=48, data_bytes_per_chain=262144, control_bytes_per_chain=98304,
    worker_rpcs_per_chain=128, native_code_bytes_per_chain=262144, images=0, consumer_retries=0,
    qualification=dict(sessions=2, observe=2, raw_readback=2, updates=0, necessary_compatibility_recovery_max=1),
    core_questions=CORE, wording=WORDING, prompts=prompt_index,
    observe_description_utf8_bytes=1214, observe_schema_sha256=sha(ROOT/'prompts/OBSERVE_TOOL.json'),
    actual_exposure='CLI consumer diagnostic: description delivered in P prompts; archived schema is not native function registration',
    model_settings='fork_turns=none, no model/effort override; actual outer settings verified per child rollout',
    provider_requests=None, fees=None, pro_identity_verified=False,
    public_package='unlabeled final answers plus exact questions/independent truth; body may disclose tool source so not completely blind',
    scoring='distance/direction1e-6; numeric vs not_applicable vs unknown separately; no independent recomputation requirement',
    causal_scope='one answer per cell; W1/W2 evidence requirements differ; no population preference/net benefit claim',
    baseline_script_hashes={name:sha(ROOT/'qa'/name) for name in ('cli.py','chain_owner.py','launch.ps1','qualify_assets.py','build_assets.py','fixture_truth.py')}))
print(json.dumps(dict(status='protocol_and_eight_prompts_frozen', source_sha256=PIN,
                     description_bytes=1214, public_answer_slots=8)))
