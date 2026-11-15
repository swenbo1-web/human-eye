"""Write a read-only source/evidence review without importing product modules."""

import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAN = Path('D:/hefe/docs/M2_DIRECTORY_RESOURCE_REUSE_001_PLAN.md')
BASELINE = '8f2a739e789b777358d84a168154bc7c50b929e5'
PLAN_SHA = '19c991d42ac17d0b8e38cfe7286c2c4c28fc4dd554c2e25c29fd52cc41d2cf21'
BRIDGE = ROOT / 'verification/m4_active_observation_host_bridge_001'
ACCEPTANCE = BRIDGE / 'external_archive/run/acceptance_02'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def source_anchor(relative, symbol):
    lines = (ROOT / relative).read_text(encoding='utf-8').splitlines()
    matches = [index for index, line in enumerate(lines, 1) if symbol in line]
    if len(matches) != 1:
        raise ValueError('Source anchor must be unique: ' + relative + ' ' + symbol)
    return {'path': relative, 'line': matches[0], 'symbol': symbol}


def host_result(path):
    outer = read_json(path)
    if outer['status'] != 'success':
        raise ValueError('Saved host response was unsuccessful')
    text = outer['result']['result']
    prefix = 'HUMAN_EYE_BLENDER_MCP:'
    if not text.startswith(prefix):
        raise ValueError('Saved response lacks the fixed host envelope')
    return json.loads(text[len(prefix):])['result']


def main():
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()
    if head != BASELINE or sha(PLAN) != PLAN_SHA:
        raise ValueError('Baseline or administrator plan changed')

    sources = {
        'human_eye_plugin/blender_host.py': [
            '    def _sync_residency(', '    def _resource_stamp(',
            '    def _resident_capture(', '    def capture_directory(',
            '    def capture_task_scene(', '    def _guard_description(',
            '    def _identity_metadata('],
        'human_eye_plugin/scene_residency.py': [
            'class SceneResidency:', '    def sync(self,context,signature,live):',
            'def encode_capture('],
        'human_eye_plugin/live_service.py': [
            '    def observe(self, session_id,', '    def _observe_directory(',
            '    def _validate_directory(', '    def _observe_active_observation(',
            '    def _observe_task('],
        'human_eye_plugin/blender_mcp_host.py': [
            '    def _resident_setup(', '    def _resident_code('],
        'human_eye_plugin/blender_worker.py': ['def run_worker('],
        'human_eye_plugin/query_policy.py': ['def validate_query('],
    }
    source_inventory = [
        {'path': relative, 'sha256': sha(ROOT / relative),
         'anchors': [source_anchor(relative, symbol) for symbol in symbols]}
        for relative, symbols in sources.items()
    ]

    capture_delta = host_result(ACCEPTANCE / 'qa/rpc_005/RX.bin')
    capture = capture_delta['capture']
    directory = host_result(ACCEPTANCE / 'qa/rpc_006/RX.bin')
    task_request = read_json(ACCEPTANCE / 'stdio/rpc_08/TX.bin')
    fixture_binding = read_json(BRIDGE / 'HARNESS_PROTOCOL.json')
    frozen_case = next(row for row in fixture_binding['fixed_requests']
                       if row['id'] == 'old_readonly_regression')
    resource = capture_delta['resources'][0]
    mesh = capture['meshes'][0]
    generation_fields = ('instance_id', 'epoch', 'revision')
    same_generation = all(capture['capture_state'][key] == directory['capture_state'][key]
                          for key in generation_fields)
    if (capture_delta['schema'] != 'human-eye-scene-delta-v1'
            or directory['schema'] != 'human-eye-directory-v1'
            or directory['cache_hit'] is not False or not same_generation
            or task_request['params']['arguments']['query'] != {'mode': 'directory'}
            or directory['binding']['host_source_sha256'] != sha(ROOT / 'human_eye_plugin/blender_host.py')):
        raise ValueError('Saved technical duplicate evidence changed')

    typed_root = ROOT / 'verification/m2_tight_directory_001/correctness/typed_01'
    typed_result = read_json(typed_root / 'RESULTS.json')
    typed_packets = {label: read_json(typed_root / (label + '.json'))
                     for label in ('directory_cold', 'directory_hot', 'directory_after_selected')}
    context = read_json(HERE / 'CONTEXT_TRACE_INVENTORY.json')
    context_summary = {
        'namespace_count': context['namespace_count'],
        'file_count': context['file_count'],
        'parse_errors': context['parse_errors'],
        'tool_catalogue_occurrences': sum(len(row['tool_catalogue_occurrences']) for row in context['namespaces']),
        'explicit_directory_request_occurrences': sum(len(row['scene_directory_request_occurrences']) for row in context['namespaces']),
        'explicit_directory_result_occurrences': sum(len(row['scene_directory_result_occurrences']) for row in context['namespaces']),
        'denominator_unit': 'files and JSON occurrences, not independent tasks',
        'limitation': 'Only JSON/JSONL and JSON-looking embedded strings were inspected. SCRIPT.py, binary transports and arbitrary execute_code strings are outside this inventory.'}

    evidence_paths = [
        BRIDGE / 'HARNESS_PROTOCOL.json', BRIDGE / 'run_acceptance_r2.py',
        ACCEPTANCE / 'stdio/rpc_08/TX.bin', ACCEPTANCE / 'stdio/rpc_08/RESPONSE.json',
        ACCEPTANCE / 'qa/rpc_005/SCRIPT.py', ACCEPTANCE / 'qa/rpc_005/RX.bin',
        ACCEPTANCE / 'qa/rpc_006/SCRIPT.py', ACCEPTANCE / 'qa/rpc_006/RX.bin',
        ACCEPTANCE / 'qa/EVENTS.jsonl', ACCEPTANCE / 'qa/CLOSE.json',
        ROOT / 'verification/m2_tight_directory_001/correctness/test_directory.py',
        typed_root / 'run_typed.py', typed_root / 'RESULTS.json',
        typed_root / 'directory_cold.json', typed_root / 'directory_hot.json',
        typed_root / 'directory_after_selected.json',
        ROOT / 'verification/m2_tight_directory_001/measurement/sample.py',
        ROOT / 'verification/m2_tight_directory_001/measurement/probe.py',
        ROOT / 'verification/m2_tight_directory_001/measurement/wire_meter.py',
        HERE / 'CONTEXT_TRACE_INVENTORY.json', HERE / 'context_trace_inventory.py',
    ]
    report = {
        'schema': 'm2-directory-resource-reuse-source-eligibility-review-v1',
        'reviewer': '/root/m1_scoring', 'source_baseline_git': head,
        'plan': {'path': str(PLAN), 'sha256': PLAN_SHA},
        'source_inventory': source_inventory,
        'read_only_scope': {'product_imports': 0, 'Blender_startups': 0,
                            'model_calls': 0, 'raster_calls': 0,
                            'product_edits': 0, 'old_evidence_edits': 0},
        'source_findings': [
            {'id': 'DIRECTORY_MISS', 'finding': 'capture_directory obtains current graph, objects and residency, checks the directory selection cache, then unconditionally to_mesh and world-forwards every evaluated vertex on miss. The complete packet is cached only after successful construction.'},
            {'id': 'RESOURCE_OWNER', 'finding': 'Resident resources are created by _resident_capture through full/task/acquisition captures. They retain vertices_local, faces, edges, stamp, world mesh and pose=(evaluated matrix, scale). Directory capture does not create mesh resources or decoder baselines.'},
            {'id': 'CURRENT_RESOURCE', 'finding': 'The reusable predicate needs enabled residency, current runtime-object key, a retained resource, exact current _resource_stamp, exact evaluated matrix/scale pose and materialized finite world vertices. Aggregate resident_resources>0 cannot prove this per object.'},
            {'id': 'INVALIDATION', 'finding': 'Context reset and undo/redo/load clear resources. Signature or depsgraph serial changes clear captures/nearest while retaining still-live resources. Resource-budget eviction clears captures and may evict relevant objects. The eight-entry capture cap can clear directory entries while retaining resource arrays.'},
            {'id': 'HOST_WIRING', 'finding': 'BlenderMCPHost uses a project-root-derived sys.modules slot and source/helper/expert-derived resident tag. Matching module/tag reuses _mcp_resident_host even through a newly constructed connector. Different source/root or missing module changes this relation. The owned typed worker constructs one host before its dispatch loop.'},
            {'id': 'COUNTERS', 'finding': 'to_mesh counts resident/directory expansions. directory_vertices counts directory world-forwarded vertices. world_transforms and world_vertices_transformed count resource world rebuilds. Legacy counters do not count the still-required tight-min/max visits separately.'},
            {'id': 'OLD_OVERVIEW', 'finding': 'measurement/sample.py old lane calls query.mode=overview and extracts routing.context_text objects as directory_facts. This old full-capture overview is not a capture_directory invocation. The new lane calls mode=directory. Both are identified from actual arguments and response schema, not directory_facts labels.'},
        ],
        'eligibility_rules': {
            'confirmed_natural_hit': [
                'An archived business sequence needs the earlier capture and later explicit tight-directory request for the task, independently of this optimization plan or a compatibility-only regression.',
                'Original input, request order, actual successful route, installed/loaded source and uninterrupted host lifetime are bound.',
                'Runtime object incarnation and retained per-object resource continuity are established. Current stamp and evaluated matrix/scale compatibility are directly observed or conservatively reconstructed from the bound source and complete unchanged static-host trace.',
                'The actual directory packet has cache_hit=false. Existing directory-cache hits remove the proposed work already.',
                'Removable work is attributable to the current directory miss. A complete business window exists before selecting a performance candidate.'
            ],
            'confirmed_non_hit': [
                'A successful actual tight-directory packet reports cache_hit=true.',
                'A complete trace proves no later tight-directory request, or proves current selected-object resources absent/incompatible.',
                'The only directory request is a predeclared compatibility control with no task requirement. This excludes natural eligibility while preserving technical mechanism evidence.'
            ],
            'unknown': [
                'Missing original arguments, incomplete route, missing host/generation continuity, missing object/resource binding, or unobserved stamp/pose change.',
                'Only same PID, same public scene revision/fingerprint, unchanged directory digest, positive aggregate resource count or receiver decoder baseline is available.',
                'A partial archive search finds no explicit directory text but excludes binary RPCs and arbitrary code-string requests.',
                'A source-derived operation count has no elapsed whole-task measurement. Cost benefit stays unknown.'
            ],
            'not_actionable': 'The bounded audit establishes zero qualified natural hits. Remaining unknowns do not authorize enlarging search or constructing a natural consumer. This is a decision within this batch, not proof that real workloads can never hit.'
        },
        'real_host_technical_example': {
            'source': str(ACCEPTANCE.relative_to(ROOT)).replace('\\', '/'),
            'actual_request_id': task_request['id'],
            'actual_query': task_request['params']['arguments']['query'],
            'predeclared_case': frozen_case,
            'classification': 'technical duplicate mechanism evidenced, compatibility-only sequence, natural task eligibility not met',
            'direct_observations': {
                'capture_schema': capture_delta['schema'],
                'capture_generation': {key: capture['capture_state'][key] for key in generation_fields},
                'directory_generation': {key: directory['capture_state'][key] for key in generation_fields},
                'same_generation': same_generation, 'directory_cache_hit': directory['cache_hit'],
                'resource_id': resource['id'], 'resource_revision': resource['revision'],
                'resource_vertices': len(resource['vertices_local']), 'resource_faces': len(resource['faces']),
                'resource_matrix': mesh['_scene_resource']['matrix'],
                'resource_scale': mesh['_scene_resource']['scale'],
                'object_instances': capture['host_identity']['object_instances'],
                'directory_binding': directory['binding'],
                'directory_objects': directory['objects'],
            },
            'source_derived_inference': {
                'host': 'Both adjacent successful SCRIPT.py requests reuse the same sys.modules resident slot/tag and _mcp_resident_host.',
                'resource': 'The prior delta serializes actual host-owned resource29. No intervening control is present. Static rigid unchanged generation and source invalidation logic support retained stamp/pose compatibility.',
                'directory_work': {'inferred_to_mesh': 1, 'inferred_vertex_forwards': 4,
                                   'provenance': 'deterministic complete directory-miss branch in source, not runtime instrumentation'}
            },
            'not_directly_observed': ['private resource stamp at directory entry', 'private current resource pose at directory entry', 'per-resource before/after residency_work snapshot', 'marginal elapsed time removed by reuse', 'whole-task benefit'],
            'technical_duplicate_examples': 1, 'qualified_natural_hits': 0,
        },
        'known_controls': {
            'fake_host': 'test_directory.py validates tight/fresh facts, invalidation, no-hooks behavior, directory-first followed by selected capture, and full→directory decoder independence. Fake host counts demonstrate reachable code behavior, not real task demand or time.',
            'typed_saved_result': {'passed': typed_result['passed'],
                'actual_commands': typed_result['post_capabilities_requests'],
                'cache_hits': {label: packet['cache_hit'] for label, packet in typed_packets.items()},
                'classification': 'directory→directory→task→directory→full, already-covered later directory hit'},
            'wire_meter': 'host_work records module, generation, aggregate counters and per-runtime-key resource revision/array lengths. It omits stamp, evaluated matrix, pose and mesh existence, and omits id(host) from serialized output. Pair with original source-bound RPC and continuous generation rather than equating module or aggregate count to current compatibility.'
        },
        'supporting_context_inventory': context_summary,
        'plan_review': {
            'judgment': 'The bounded natural-demand gate and not_actionable exit are appropriate. The technical duplicate remains a valid source opportunity.',
            'false_positive_guards': [
                'Do not count old overview/task_overview labels as a tight-directory call.',
                'Do not promote HARNESS_PROTOCOL old_readonly_regression to natural demand.',
                'Do not treat CAPTURE_REPLAY, fake hosts or programmed warm-up as real demand.',
                'Do not claim measured counts or timing from source-derived branch counts.',
                'Do not use 2221 files, catalogue occurrences or repeated copies as independent task denominators.'
            ],
            'false_negative_guards': [
                'Directory miss is the operational condition. First-ever directory is narrower, because capture-cap eviction or non-geometric invalidation can remove the directory packet while retaining compatible resources. Preserve the current frozen first-directory domain and label these later-miss opportunities separately.',
                'Same resource may remain compatible across a scene-residency revision change. Exact revision equality is sufficient continuity evidence in supported static traces, not a mandatory reuse predicate.',
                'A new connector may retain the same Blender resident host. Resolve actual module/tag/token continuity.',
                'Insufficient source/resource/pose data stays unknown rather than confirmed miss.',
                'JSON-only no-occurrence inventories cannot exclude all low-level binary/code-string traffic.'
            ],
            'candidate_constraints_if_later_authorized': [
                'Retain the original directory triangle upper bound max(0,len(loops)-2*len(polygons)) as source-derived metadata. Actual triangulated face count is not an equivalent admission budget.',
                'Prepared-local resources lacking this original count take the existing directory read path.',
                'Reuse world vertices for tight min/max with original finite, budget and deadline checks. Count min/max visits separately and do not build full mesh resources on cold directory.',
                'Keep directory packet, sender resources and receiver decoder baselines as distinct ownership contracts.'
            ]
        },
        'preparation_events': [
            {'event': 'windows_python_alias_empty_output',
             'attempts': 2, 'exit_code': 0, 'stdout': '',
             'scope': 'A static JSON metadata script piped to python and a print-only python check resolved to WindowsApps aliases. No product was imported and no metadata output was produced. Reports use the explicit runtime below.'}
        ],
        'generation_runtime': 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -I -B -X utf8',
        'evidence_pins': [{'path': str(path.relative_to(ROOT)).replace('\\', '/'),
                           'bytes': path.stat().st_size, 'sha256': sha(path)} for path in evidence_paths],
        'review_generator_sha256': sha(Path(__file__)),
        'conclusion': {'source_opportunity_confirmed': True,
                       'real_host_technical_example_count': 1,
                       'qualified_natural_task_hit_count': 0,
                       'qualification_disposition': 'not_actionable within audited scope',
                       'whole_task_benefit': 'unknown', 'product_change_authorized_by_review': False,
                       'implementation_or_formal_matrix': 'not_run'}
    }
    markdown = '''# M2 目录资源复用源码及资格复核

基线为 `8f2a739e789b777358d84a168154bc7c50b929e5`。本复核仅读取源码和已归档记录，没有执行产品、Blender、模型或 raster。

## 当前判定

源码存在明确的重复工作机会。真实宿主归档中也找到 1 个技术例子。符合本批自然任务准入的例子为 0，建议按本批计划收口 `not_actionable`。完整任务收益仍为 `unknown`。

真实技术例子来自 `m4_active_observation_host_bridge_001/external_archive/run/acceptance_02`。实际 `nonplanar_source` 完整捕获已传出实例 277 的 resource29，含 4 个顶点和 2 个三角形。之后 `old_readonly_regression` 明确发送 `query.mode=directory`，实际目录 `cache_hit=false`，同驻留模块、instance、epoch、revision。HARNESS_PROTOCOL 已将该请求登记为兼容回归，运行器只断言成功与纯文本。归档没有证明业务任务需要该目录，因此技术例子不能转为自然需求。

目录入口的私有 stamp 和当前 pose 没有直接序列化。资源连续性由原始 delta、相邻请求、固定静态刚性来源、相同代际及源码失效逻辑支持。额外 1 次 to_mesh、4 个顶点 world forward 是确定分支的源码推断，归档没有这些操作的独立运行计数和可删除耗时。

## 源码流程

`blender_host.capture_directory` 取得当前依赖图、对象和 residency 后，先查目录 selection cache。命中则返回已缓存目录。未命中对每个对象重新 `to_mesh`、读取局部点、计算世界点并求紧界。目录只缓存自身 packet，不创建 mesh resource 或 delta baseline。

`_resident_capture` 已保留局部点、面、边、stamp、世界 mesh 和 `pose=(evaluated matrix, scale)`。兼容复用需要当前运行对象身份对应的资源仍在、stamp 匹配、当前 evaluated matrix/scale 匹配且世界点已物化。`resident_resources>0` 无法证明指定对象符合这些条件。

场景上下文变化及 undo/redo/load 会清空资源。普通 signature/serial 变化主要清除 capture 与 nearest，仍可保留兼容资源。资源预算驱逐和八项 capture 上限也可能清除目录缓存。目录 cache miss 是可删除工作的实际条件，首次目录只是本批冻结的更窄需求域。

MCP 接线按 project root 的 sys.modules slot 和源码 tag 复用 `_mcp_resident_host`。新建 connector 仍可能接回同宿主。owned typed worker 则在分发循环前创建单一 host。PID、名称或 public scene revision 单独不能代替这些关系。

## 旧记录的判别

旧 M2 `measurement/sample.py` 的 old lane 发送 `overview`，其 `directory_facts` 来自 `routing.context_text`。只有实际 `mode=directory`、对应 host command 和 `human-eye-directory-v1/scene_directory` 回包才能证明紧目录调用。

旧 typed_01 原始结果顺序为 directory、directory、task、directory、full。后续目录实际 `cache_hit=true`，已有缓存已消除这项工作。fake-host 控制证明紧界、失效和接口接线，也能证明源码路径可达，但不代表自然任务需求或实机收益。

根补充盘点覆盖 11 个 namespace 的 2221 个 JSON/JSONL 文件，显式目录请求与结果均未发现，tools/list catalogue 出现 66 次。文件数及 occurrence 不是独立任务数。该盘点没有搜索二进制、SCRIPT.py 和任意 execute_code 字符串，因此结论限定在显式 JSON 证据范围。

## 资格与误判边界

- 自然命中需要原任务确实需要先前捕获和后续紧目录，完整请求与输入可绑定，同宿主资源连续且兼容，实际目录 miss，完整业务窗口可恢复。
- 实际 `cache_hit=true` 可判已有缓存覆盖。明确的兼容性回归可判本批自然任务条件不满足，同时保留技术重复事实。
- 缺原始 arguments、宿主连续性、对象资源绑定、stamp/pose 支持或完整成本时保留 unknown。正数资源计数、decoder baseline、相同目录摘要均不够。
- scene residency revision 改变时资源仍可能兼容。不能把 revision 相等变成产品的额外复用限制。
- 首次之外的目录 miss 可能仍有机会，本批按原计划单列范围，避免扩大实验。
- 后续若授权实现，必须保留原 loops/polygons 三角上界、有限期限与预算。prepared_local 缺原计数时走原路径。world 顶点复用仍需一次紧界 min/max，不能宣称零遍历。

精确源码锚点、证据 SHA、直接观察、源码推断和缺失证据均列于同名 JSON。当前只建议关闭本批资格，下一模块由根另行派发。
'''
    with (HERE / 'SOURCE_ELIGIBILITY_REVIEW.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    with (HERE / 'SOURCE_ELIGIBILITY_REVIEW.md').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(markdown)
    print(json.dumps({name: sha(HERE / name) for name in
                      ('source_eligibility_review.py', 'SOURCE_ELIGIBILITY_REVIEW.json', 'SOURCE_ELIGIBILITY_REVIEW.md')}))


if __name__ == '__main__':
    main()
