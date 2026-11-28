"""Use the formal transport against actual Codex app-server without starting a turn."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from transport import encode, pin, read, require, rows, start_transport, write
from close_probe import App, wait_file
import natural
from natural_bridge import Bridge

ROOT = Path(os.environ['HE_NATURAL_HOLDOUT_ROOT']).resolve(strict=True)
PRIOR = ROOT.parent/'M4-NEAREST-SURFACE-FIRST-FOCUS-001'
OLD = ROOT.parent/'M4-REFERENCE-ONLY-INTENT-HOLDOUT-001'
CUSTODY = PRIOR/'preflight/CANDIDATE_INSTALL_CUSTODY.json'
SOURCE = PRIOR/'slots/B/post_capture.json'
OUT = ROOT/'preflight/transport'
PLAN = ROOT/'preflight/TRANSPORT_PLAN.json'
RESULT = ROOT/'preflight/TRANSPORT_RESULT.json'
KINDS = ('normal', 'missing_last', 'reset')


class NoTurnApp(App):
    def __init__(self, folder, endpoint):
        self.folder, self.work = folder, folder/'workspace'
        self.work.mkdir()
        isolated = folder/'codex-home'
        isolated.mkdir()

        def q(value):
            return json.dumps(str(value), ensure_ascii=True)

        args = ','.join(map(q, ('-IB', '-X', 'utf8', HERE/'transport.py', 'thin', endpoint)))
        mcp = (f'mcp_servers.arm_engine={{command={q(sys.executable)},args=[{args}],cwd={q(self.work)},'
               'required=true,startup_timeout_sec=15,tool_timeout_sec=15}')
        config = [mcp, 'features.apps=false', 'features.hooks=false', 'features.plugins=false',
                  'features.memories=false', 'web_search="disabled"', 'model_provider="close_probe_local"',
                  'model_providers.close_probe_local={name="offline",base_url="http://127.0.0.1:1/v1",'
                  'wire_api="responses",requires_openai_auth=false}']
        argv = [str(natural.CLI), 'app-server', '--stdio', '--strict-config']
        for item in config:
            argv.extend(('-c', item))
        env = dict(os.environ, CODEX_HOME=str(isolated))
        for key in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'AZURE_OPENAI_API_KEY'):
            env.pop(key, None)
        self.stderr = (folder/'APP_STDERR.bin').open('xb')
        self.proc = subprocess.Popen(argv, cwd=self.work, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.stderr, creationflags=subprocess.CREATE_NO_WINDOW)
        write(folder/'APP_STARTED.json', {'pid': self.proc.pid, 'argv': argv, 'started_ns': time.perf_counter_ns()})
        self.queue = queue.Queue()
        self.reader = threading.Thread(target=self.pump, daemon=True)
        self.reader.start()


def prepare():
    product = read(CUSTODY)
    require(product['candidate_commit'] == '4225256485a82a9ddbdeeca61e1bbd3275574a6e'
            and product['source_sha256'] == '60eabe4f875aabbd6c7b1c24c7498ed06b53d10b40a0e70a0ab920b4a64631e0'
            and product['wheel']['sha256'] == '5b1f10708bc61cf21453ca0c72fb54cc8b7af19fc3925747bcef96499fd8e4fb'
            and product['runtime_sources'] == 146 and pin(natural.CLI)['sha256'] == natural.CLI_SHA,
            'wrong_frozen_candidate_or_CLI')
    old = []
    for key in 'KT':
        folder = OLD/'slots'/f'NATURAL_{key}'
        close, verdict = folder/'closed.json', folder/'consumer/RESULT.json'
        require('10054' in read(close)['transport']['error']['message'] and
                read(verdict)['passed_transport'] is False, 'original_10054_or_failed_verdict_missing')
        old += [close, verdict]
    paths = [Path(__file__), HERE/'transport.py', ROOT/'preflight/ADMIN_PLAN.md', SOURCE, CUSTODY,
             natural.CLI, Path(sys.executable), Path(natural.__file__),
             HERE.parent/'m4_reference_only_intent_holdout_001/natural_bridge.py',
             HERE.parent/'m4_nearest_surface_first_focus_001/close_probe.py', *old]
    write(PLAN, {'inputs': list(map(pin, paths)), 'cases': list(KINDS), 'source': pin(SOURCE),
          'formal_transport': pin(HERE/'transport.py'), 'candidate_install': pin(CUSTODY),
          'old_unmodified': list(map(pin,old)),
          'no_model_entry': 'Codex 0.152.1 app-server, ephemeral thread and actual manual mcpServer/tool/call',
          'entry_difference': 'formal uses codex exec model and real CLI item/completed; this qualification checks same transport via direct no-turn app-server response',
          'limits': {'app_servers': 3, 'business_per_case': 2, 'offline_raster_max_per_case': 2,
                     'Blender': 0, 'models': 0}})


def verify_raw(folder, source, case, transport, answers):
    wire = rows(folder/'wire/INDEX.jsonl')
    owner, thin = [rows(folder/f'TRANSPORT_{side}.jsonl') for side in ('OWNER','THIN')]
    require(len(answers) == 2 and sum(r['method']=='tools/call' for r in wire) == 2
            and len(owner) == len(thin) == len(wire)-int(case != 'normal'), 'paired_real_exchange_inventory')
    for item, left, right in zip(wire,owner,thin):
        pair = left['request']
        require(pair == right['request'] and left['offer'] == right['offer'] and left['ack'] == right['ack']
                and left['peer_eof'] and right['peer_eof'] and item['ordinal'] == pair['ordinal']
                and pin(item['tx']['path']) == item['tx'] and pin(item['rx']['path']) == item['rx']
                and pair['request_sha256'] == item['tx']['sha256'] and pair['response_sha256'] == item['rx']['sha256'],
                'same_wire_not_bilaterally_settled')
    real = [r for r in wire if r['method']=='tools/call']
    content = [read(item['rx']['path'])['result']['content'] for item in real]
    accepted = [a.get('result',{}).get('content') == c for a,c in zip(answers,content,strict=True)]
    require(accepted == [True,case == 'normal'], 'actual_Codex_caller_receive_contract')
    require(any(row['type']=='image' for row in content[1]), 'original_last_MCP_image_missing')
    frame = next(f for f in rows(folder/'frames.jsonl') if f['source']=='product' and f['delivered'])
    require(pin(frame['image_path'])['sha256'] == frame['image_sha256']
            and pin(frame['arrays_path'])['sha256'] == frame['arrays_sha256'], 'original_frame_not_bound')
    if case == 'normal':
        require(transport['closed'] and transport['zero_in_flight'] and transport['transport_eof']
                and transport['Thin_process']['exit_code'] == 0 and
                transport['Thin_termination'] == 'observed_own_graceful_termination'
                and transport['Thin_exit']['normal_close_request'] == transport['last_paired']['request'],
                'normal_owned_end_missing')
    else:
        require(not transport['closed'] and not transport['zero_in_flight']
                and transport['outstanding']['fault'] == case and transport['Thin_process']['exit_code'] != 0,
                'failed_transport_must_not_be_accepted')
        thin_error = transport['Thin_exit']['error']
        if case == 'reset':
            require(thin_error['winerror'] == 10054 and transport['outstanding']['prepared_reply_read_by_Thin'],
                    'genuine_Windows_reset_not_observed')
        else:
            require(thin_error['message'] == 'owner_EOF_before_private_response',
                    'missing_last_must_never_reach_Thin')
    return {'accepted_by_real_caller': accepted, 'original_frame': pin(frame['image_path']), 'wire':wire}


def run_case(folder, case, plan):
    folder.mkdir()
    custody = read(CUSTODY)
    source = read(plan['source']['path'])
    settings = {'site':custody['installation']['path'], 'product_source_sha256':custody['source_sha256'],
                'product_source_files':custody['runtime_sources']}
    host = natural.ReplayHost(source)
    service, server = natural.product(settings,folder,host)
    deadline = time.perf_counter_ns() + 60_000_000_000
    owner = start_transport(folder, Bridge(folder,host,service,server,deadline), deadline)
    app = NoTurnApp(folder,owner.endpoint)
    owner.bind_cli(app.proc.pid)
    answers = []
    try:
        hello = app.call('initialize', {'clientInfo': {'name':'natural-paired-transport','version':'1'},
                                      'capabilities':None},1)
        require(hello and 'result' in hello, 'actual_no_turn_initialize_failed')
        app.call('initialized',{})
        thread = app.call('thread/start', {'cwd':str(app.work),'ephemeral':True,
                                           'sandbox':'read-only','approvalPolicy':'never'},2)
        require(thread and 'result' in thread, 'actual_no_turn_thread_failed')
        thread_id = thread['result']['thread']['id']

        def call(tool, arguments, ident):
            return app.call('mcpServer/tool/call', {'threadId':thread_id,'server':'arm_engine',
                            'tool':tool,'arguments':arguments},ident)

        answers.append(call('read_scene',{'objects':['Part M','Fixture K']},3))
        require(answers[0] and 'result' in answers[0], 'dynamic_first_call_not_received')
        if case != 'normal':
            owner.arm_offline_fault(case)
        answers.append(call('human_eye_scene_observe', {
            'query':{'mode':'active_observation','objects':[{'name':'Part M'}],
                'focus':{'task_region':{'reference':{'name':'Fixture K'},'relation':'nearest_surface'}}},
            'include_image':True,'response_detail':'full'},4))
        if case == 'normal':
            owner.request_thin_end()
        wait_file(folder/'THIN_EXIT.json')
    finally:
        transport = owner.finish()
        app_close = app.close()
    evidence = verify_raw(folder,source,case,transport,answers)
    require(app_close['exit_code'] == 0 and app_close['stdout_eof'] and not app_close['forced'],
            'actual_app_server_closure_missing')
    report = {'case':case,'passed':True,'business':transport['business'],'rasters':transport['rasters'],
              'transport':transport,'app_close':app_close,'real_caller_evidence':evidence,
              'raw_files':[pin(folder/n) for n in ('APP_TX.bin','APP_RX.bin','APP_STDERR.bin','TRANSPORT_OWNER.json',
                  'TRANSPORT_OWNER.jsonl','TRANSPORT_THIN.jsonl','TRANSPORT_FLUSH.jsonl','THIN_EXIT.json','wire/INDEX.jsonl')]}
    write(folder/'RESULT.json',report)
    return pin(folder/'RESULT.json')


def run():
    plan = read(PLAN)
    require(all(pin(p['path'])==p for p in plan['inputs']), 'transport_preflight_frozen_source_changed')
    OUT.mkdir()
    cases = {case:run_case(OUT/case,case,plan) for case in KINDS}
    write(RESULT,{'passed':True,'plan':pin(PLAN),'cases':cases,'formal_transport':plan['formal_transport'],
                  'Blender':0,'models':0,'actual_app_server_processes':3,
                  'ordinary_product_calls':6,'entry_difference':plan['entry_difference']})


if __name__ == '__main__':
    require(os.name=='nt' and sys.flags.isolated and sys.dont_write_bytecode, 'isolated_Windows_required')
    {'prepare':prepare,'run':run}[sys.argv[1]]()
