"""Fresh coverage-task CLI using the fixed image/event/archive loop.

The frozen CLI event/process loop is reused with explicit output, workspace,
thread and absolute deadline parameters. Local fake CLI runs use this same loop.
Provider execution remains disabled unless a later frozen plan enables it.
"""

import base64
import hashlib
import struct
import importlib.util
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'verification/m4_surface_scan_compact_consumption_001/runtime'
CONTINUITY = ROOT / 'verification/m4_surface_scan_continuity_001'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


previous = load('_fix1_original_consumer', OLD / 'consumer_transport.py')
cli = load('_fix1_continuity_cli', CONTINUITY / 'cli/continuity_cli.py')
compatibility = load('_image_compatibility', ROOT / 'verification/m4_surface_scan_continuous_interface_fix_001/compatibility.py')
launch = load('_coverage_handle_launch', ROOT / 'verification/m4_active_coverage_003/launch.py')
runtime_handle = load('_coverage_thin_runtime_handle', HERE / 'runtime_handle.py')
packer = load('_fix1_original_pack_quality', OLD / 'pack_quality.py')
TOOLS_BY_GROUP = {'N': frozenset({'execute_python', 'scene_data', 'render_views', 'read_images'}),
                  'P': frozenset({'execute_python', 'scene_data', 'render_views', 'read_images', 'active_coverage'})}
USAGE = previous.USAGE
KNOWN_TOOL_TYPES = previous.KNOWN_TOOL_TYPES
safe_environment = previous.safe_environment
wait_bridge_closed = previous.wait_bridge_closed
read = previous.read
save = previous.save
sha = previous.sha


def initial_image_metadata(plan):
    """Initial stdin is text only; subsequent MCP tool images are independent."""
    return {'count': 0, 'bytes': 0, 'attachment': 'none',
            'scope': 'Initial CLI attachments only; actual tool images counted separately.'}


def initial_argv(python, cell_path, work, final, group):
    cell = read(cell_path)
    config = previous.settings()
    config['mcp_servers.arm_engine'] = {
        'command': str(python),
        'args': ['-I', '-B', str(previous.ATTACH_PATH), '--endpoint', cell['endpoint'],
                 '--kind', 'native', '--audit', str(Path(cell_path).parent / 'attachments')],
        'cwd': str(work), 'required': True, 'startup_timeout_sec': 60, 'tool_timeout_sec': 40,
        'tools': {name: {'approval_mode': 'approve'} for name in sorted(TOOLS_BY_GROUP[group])}}
    interface = read(CONTINUITY / 'cli/CLI_INTERFACE.json')
    if sha(interface['executable']) != interface['executable_sha256']:
        raise ValueError('frozen_CLI_executable_changed')
    argv = [interface['executable'], 'exec', '--ignore-user-config', '--ignore-rules',
            '--strict-config', '--json', '--skip-git-repo-check', '-C', str(work), '--color', 'never']
    for key, value in config.items():
        argv.extend(['-c', key + '=' + previous.toml(value)])
    return argv + ['-m', 'gpt-6.1-sol', '-o', str(final), '-']


def completed_images(item, received_ns, raw_event_bytes):
    """Measure actual completed CLI content without interpreting image pixels."""
    rows = []
    result = item.get('result')
    content = result.get('content', []) if type(result) is dict else []
    for block_index, block in enumerate(content):
        if type(block) is not dict or block.get('type') != 'image':
            continue
        row = {'tool_item_id': item.get('id'), 'tool': item.get('tool'),
               'block_index': block_index, 'received_ns': received_ns,
               'CLI_completed_event_JSON_line_bytes': raw_event_bytes,
               'mimeType': block.get('mimeType'), 'PNG_bytes': None,
               'base64_bytes': None, 'PNG_sha256': None, 'width': None, 'height': None,
               'payload_valid': False, 'error': None}
        try:
            data = block['data']
            if type(data) is not str or block.get('mimeType') != 'image/png':
                raise ValueError('standard_image_content_fields')
            row['base64_bytes'] = len(data.encode('ascii'))
            png = base64.b64decode(data, validate=True)
            if len(png) < 24 or png[:8] != b'\x89PNG\r\n\x1a\n' or png[12:16] != b'IHDR':
                raise ValueError('PNG_header')
            width, height = struct.unpack('>II', png[16:24])
            row.update(PNG_bytes=len(png), PNG_sha256=hashlib.sha256(png).hexdigest(),
                       width=width, height=height, payload_valid=True)
        except (KeyError, TypeError, ValueError, UnicodeError) as error:
            row['error'] = {'type': type(error).__name__, 'message': str(error)}
        rows.append(row)
    return rows


def image_telemetry(record, folder):
    rows = record['image_deliveries']
    unknown = sum(not row['payload_valid'] for row in rows)
    record['public_image_count'] = len(rows)
    record['known_PNG_bytes'] = sum(row['PNG_bytes'] or 0 for row in rows)
    record['public_image_bytes'] = record['known_PNG_bytes'] if not unknown else None
    record['base64_bytes'] = sum(row['base64_bytes'] or 0 for row in rows)
    record['unknown_image_payloads'] = unknown
    record['image_delivery']['status'] = 'CLI_completed_tool_image_content_observed' if rows else 'no_completed_tool_image_content_observed'
    wire = []
    for path in sorted((folder / 'attachments').rglob('*.bin')):
        raw = path.read_bytes()
        wire.append({'path': path.relative_to(folder).as_posix(), 'bytes': len(raw),
                     'sha256': hashlib.sha256(raw).hexdigest()})
    record['MCP_wire_files'] = wire
    record['MCP_stdio_TX_bytes'] = sum(row['bytes'] for row in wire if row['path'].endswith('/TX.bin'))
    record['MCP_stdio_RX_bytes'] = sum(row['bytes'] for row in wire if row['path'].endswith('/RX.bin'))
    record['image_observation_scope'] = 'Completed CLI MCP image blocks; provider-internal request and model visual consumption unobserved.'


def launch_argv(frozen_argv, local_cli, plan, python):
    if local_cli is None:
        if plan.get('model_consumer_enabled') is not True:
            raise ValueError('model_consumer_disabled_in_preparation')
        return frozen_argv, 'provider'
    command = local_cli.get('command')
    if not isinstance(command, list) or len(command) < 2 or any(type(value) is not str for value in command):
        raise ValueError('local_CLI_command_required')
    if sha(command[0]) != sha(python) or command[1:-1] not in (['-I', '-B'], ['-I', '-B', '-X', 'utf8']):
        raise ValueError('local_CLI_isolated_Python_required')
    script = Path(command[-1]).resolve()
    if script.suffix != '.py' or sha(script) != local_cli.get('script_sha256'):
        raise ValueError('local_CLI_script_binding')
    return command + frozen_argv[1:], 'synthetic_local_process'


def archive_turn(folder, cell, first_attempt, tool_calls):
    """Bind actual per-turn original requests/responses and thin wire archives."""
    audit = Path(cell['audit_dir'])
    tools = read(audit / 'TOOLS.json') if (audit / 'TOOLS.json').exists() else {'tools': []}
    selected = [row for row in tools.get('tools', []) if row['attempt'] >= first_attempt]
    source_records = []
    binding_errors = []
    if len(selected) != len(tool_calls):
        binding_errors.append({'reason': 'owner_and_CLI_attempt_count', 'owner': len(selected), 'CLI': len(tool_calls)})
    for owner, public in zip(selected, tool_calls):
        original = audit / ('tool_' + str(owner['attempt']).zfill(2))
        try:
            request = read(original / 'REQUEST.json')
            response_path = original / ('RESPONSE.json' if (original / 'RESPONSE.json').exists() else 'ERROR_RESPONSE.json')
            response = read(response_path)
            item = public['item']
            if request['params']['name'] != item['tool'] or packer.encoded(request['params']['arguments']) != packer.encoded(item['arguments']):
                binding_errors.append({'attempt': owner['attempt'], 'reason': 'CLI_request_differs_from_owner'})
            if (packer.encoded(response.get('result')) != packer.encoded(item.get('result'))
                    and not compatibility.successful_result_matches(response, item)):
                binding_errors.append({'attempt': owner['attempt'], 'reason': 'CLI_result_differs_from_owner'})
        except (OSError, ValueError, KeyError, TypeError) as error:
            binding_errors.append({'attempt': owner['attempt'], 'reason': 'owner_original_unreadable', 'error': repr(error)})
    for row in selected:
        original = audit / ('tool_' + str(row['attempt']).zfill(2))
        for source in sorted(original.rglob('*')):
            if not source.is_file():
                continue
            target = folder / 'owner_turn' / original.name / source.relative_to(original)
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = source.read_bytes()
            target.write_bytes(raw)
            source_records.append({'original': str(source), 'copy': target.relative_to(folder).as_posix(),
                                   'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    save(folder / 'BUSINESS_SOURCE_BINDING.json', {
        'first_owner_attempt': first_attempt, 'recorded_owner_attempts': [row['attempt'] for row in selected],
        'sources': source_records, 'binding_errors': binding_errors,
        'scope': 'Actual owner originals copied unchanged and matched to the CLI completed tool events for this turn.'})
    archive = folder.parent / (folder.name + '.raw.zip')
    sources = packer.capture_cell(folder, archive)
    value = {'archive': str(archive), 'archive_sha256': sha(archive), 'archive_bytes': archive.stat().st_size,
             'source_files_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()},
             'original_file_count': len(sources), 'owner_attempts': [row['attempt'] for row in selected],
             'business_binding_errors': binding_errors,
             'scope': 'Raw events, outputs, attachments and owner business originals; derived CONSUMER and timing receipts are published after this archive.'}
    save(folder / 'ARCHIVE.json', value)
    return value


def consume_turn(*, episode_id, turn_index, folder, work, cell, install, plan, prompt,
                 episode_deadline_ns, turn_deadline_ns, expected_thread_id=None, local_cli=None):
    """Consume one fresh turn under the owner's original absolute deadline.

    Keep the CLI and actual thin-runtime terminal evidence independent of the
    answer and image-content records. The actor belongs to the outer driver.
    """
    began = time.perf_counter_ns()
    if type(turn_index) is not int or turn_index != 1:
        raise ValueError('single_fresh_turn_required')
    if not episode_id or (turn_index == 1) != (expected_thread_id is None):
        raise ValueError('episode_and_resume_binding_required')
    endpoint = read(cell['endpoint'])
    if not (type(turn_deadline_ns) is int and type(episode_deadline_ns) is int
            and began < turn_deadline_ns <= episode_deadline_ns <= endpoint['chain_deadline_ns']):
        raise ValueError('original_absolute_turn_and_episode_deadlines')
    group = cell['group']
    expected_tools = TOOLS_BY_GROUP[group]
    folder, work = Path(folder), Path(work)
    image = initial_image_metadata(plan)
    if local_cli is None and plan.get('model_consumer_enabled') is not True:
        raise ValueError('model_consumer_disabled_in_preparation')
    folder.mkdir(parents=True, exist_ok=False)
    if turn_index == 1:
        work.mkdir(parents=True, exist_ok=True)
        if list(work.iterdir()):
            raise ValueError('first_turn_fresh_workspace_required')
    elif not work.is_dir():
        raise ValueError('resume_workspace_missing')
    cell = dict(cell, attachments_dir=str(folder / 'attachments'))
    cell_path = folder / 'cell.json'
    save(cell_path, cell)
    final = folder / 'final.txt'
    frozen_argv = cli.argv_for_turn(initial_argv(install['python'], cell_path, work, final, group), expected_thread_id)
    argv, execution_kind = launch_argv(frozen_argv, local_cli, plan, install['python'])
    deadline = turn_deadline_ns
    slot = {'episode_id': episode_id, 'turn_index': turn_index, 'turn_label': cli.TURN_LABELS[turn_index - 1],
            'expected_thread_id': expected_thread_id, 'execution_kind': execution_kind,
            'frozen_cli_argv': frozen_argv, 'shared_work': str(work), 'endpoint': cell['endpoint'],
            'episode_deadline_ns': episode_deadline_ns}
    tools_before = read(Path(cell['audit_dir']) / 'TOOLS.json') if (Path(cell['audit_dir']) / 'TOOLS.json').exists() else {}
    first_attempt = tools_before.get('attempts', tools_before.get('calls', 0)) + 1
    logged_events = []
    raw_usage_events = []
    record={**slot,'status':'running','started_ns':began,'deadline_ns':deadline,
        'argv':argv,'expected_tool_names':sorted(expected_tools),'consumer_pid':None,'popen_ns':None,'prompt_submitted_ns':None,'prompt_write_started_ns':None,
        'final_received_ns':None,'turn_completed_ns':None,'process_exit_ns':None,'cleanup_end_ns':None,
        'usage':None,'usage_rows':[],'thread_id':None,'tool_calls':[],'public_events':[],
        'all_public_messages':[],'final':None,'errors':[],'unexpected_tool_deviations':[],
        'provider_retry_observations':[],'provider_requests':None,'fees':None,'model':'gpt-6.1-sol',
        'requested_effort':'medium','resolved_effort':None,'process_reaped':False,
        'input_text_bytes':len(prompt),'input_sha256':hashlib.sha256(prompt).hexdigest(),
        'public_image_bytes':0,'public_image_count':0,'image_deliveries':[],
        'tool_image_scope':'actual completed MCP image content, independent of initial attachments',
        'initial_image':image,'input_image_count':0,'input_image_bytes':0,'image_tokens':None,
        'input_image_count_scope':'Initial stdin text only; no initial attachment. Tool content counted separately.',
        'image_delivery':{'prepared_file_verified':None,'initial_attachment_in_argv':False,
            'CLI_process_launched':False,'CLI_thread_started':False,'status':'awaiting_actual_tool_content',
            'provider_delivery_confirmed':None,'model_view_confirmed':None},
        'valid_completion':False,'safe_to_continue':False}
    save(folder/'CONSUMER_STARTED.json',record)
    process=None;readers=[];timer=None;fired=threading.Event();events=queue.Queue();closed=0
    held_runtime = None
    runtime_binding_attempted = False
    record['runtime_binding'] = None
    record['runtime_exit'] = None
    record['stdout_raw_scope'] = 'Original stdout bytes retained privately; parsed public reasoning items remain hash/count redacted.'
    def bind_started_runtime():
        nonlocal held_runtime, runtime_binding_attempted
        starts = sorted((folder / 'attachments').glob('bridge_*/STARTED.json'))
        if len(starts) > 1:
            if not record.get('multiple_thin_runtime_starts'):
                record['multiple_thin_runtime_starts'] = [str(path) for path in starts]
                record['errors'].append({'type': 'RuntimeError', 'message': 'unexpected_multiple_thin_runtimes'})
            return
        if starts and not runtime_binding_attempted:
            try:
                started = read(starts[0])
            except (OSError, ValueError):
                return
            runtime_binding_attempted = True
            proof, held_runtime = runtime_handle.bind_runtime(process, started,
                install['python'], launch.BASE_SHA256, deadline)
            proof['STARTED_path'] = str(starts[0])
            record['runtime_binding'] = proof
            save(folder / 'RUNTIME_BINDING.json', proof)
    def expire():
        fired.set()
        if process is not None and process.poll() is None:
            process.kill()
    def reader(stream,label):
        raw_file = None
        try:
            if label == 'stdout':
                raw_file = (folder / 'stdout.raw.bin').open('wb')
            for raw in iter(stream.readline,b''):
                received_ns = time.perf_counter_ns()
                if raw_file is not None:
                    raw_file.write(raw)
                    raw_file.flush()
                events.put((label,raw,received_ns))
        except BaseException as error:
            events.put(('reader_error',repr(error).encode(),time.perf_counter_ns()))
        finally:
            if raw_file is not None:
                raw_file.close()
            events.put((label,None,time.perf_counter_ns()))
    try:
        timer=threading.Timer(max(0.,(deadline-time.perf_counter_ns())/1e9),expire);timer.daemon=True;timer.start()
        if time.perf_counter_ns() >= deadline:raise TimeoutError('original_absolute_turn_deadline_before_launch')
        record['popen_ns']=time.perf_counter_ns()
        process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            cwd=work,env=safe_environment(os.environ),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        record['consumer_pid']=process.pid;record['image_delivery']['CLI_process_launched']=True
        record['image_delivery']['status']='CLI_process_launched; no_initial_attachment'
        for label,stream in (('stdout',process.stdout),('stderr',process.stderr)):
            thread=threading.Thread(target=reader,args=(stream,label),daemon=True);readers.append(thread);thread.start()
        record['prompt_write_started_ns']=time.perf_counter_ns();process.stdin.write(prompt);process.stdin.close()
        record['prompt_submitted_ns']=time.perf_counter_ns()
        with (folder/'events.jsonl').open('w',encoding='utf8',newline='\n') as public_log, \
                (folder/'stderr.raw.bin').open('wb') as stderr_raw, \
                (folder/'stderr_lines.jsonl').open('w',encoding='utf8',newline='\n') as stderr_log:
            while closed<2:
                bind_started_runtime()
                left=(deadline-time.perf_counter_ns())/1e9
                if left<=0 or fired.is_set():raise TimeoutError('original_absolute_session_deadline')
                try:label,raw,received=events.get(timeout=min(.1,left))
                except queue.Empty:continue
                if raw is None:closed+=1;continue
                if label=='stderr':
                    stderr_raw.write(raw);stderr_raw.flush()
                    text=raw.decode('utf8',errors='replace')
                    stderr_log.write(json.dumps({'perf_ns':received,'text':text},ensure_ascii=False)+'\n');stderr_log.flush()
                    if any(word in text.lower() for word in ('retry','reconnect','429','503','rate limit','quota','usage limit')):
                        record['provider_retry_observations'].append({'perf_ns':received,'source':'stderr','text':text})
                    continue
                if label=='reader_error':raise RuntimeError(raw.decode())
                record['stdout_bytes']=record.get('stdout_bytes',0)+len(raw)
                try:event=json.loads(raw)
                except (ValueError,UnicodeError) as error:
                    with (folder/'stdout_unparsed.bin').open('ab') as malformed:malformed.write(raw)
                    record.setdefault('stdout_unparsed_lines',[]).append({'perf_ns':received,
                        'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
                    raise ValueError('non_JSON_CLI_stdout_line_retained') from error
                kind=event.get('type');item=event.get('item',{})
                # Hide agent reasoning is set. Retain only a hash/count if the
                # CLI nevertheless emits a reasoning body; never export it.
                if item.get('type') in ('reasoning','analysis'):
                    logged={'type':kind,'item':{'type':item['type'],'redacted':True},
                        'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw)}
                else:logged=event
                logged_events.append({'perf_ns':received,'event':logged})
                public_log.write(json.dumps(logged_events[-1],ensure_ascii=False)+'\n');public_log.flush()
                if kind=='thread.started':
                    record['thread_id']=event.get('thread_id');record['image_delivery']['CLI_thread_started']=True
                    record['image_delivery']['status']='CLI_thread_started; no_initial_attachment'
                if kind in ('error','turn.failed'):
                    record['errors'].append({'perf_ns':received,'event':event})
                if kind=='turn.completed':
                    usage=event.get('usage');record['turn_completed_ns']=received
                    raw_usage_events.append(usage)
                    if type(usage) is dict:
                        numeric={k:usage[k] for k in USAGE if k in usage}
                        if any(type(v) is not int or v<0 for v in numeric.values()):raise ValueError('invalid_actual_usage')
                        record['usage']=numeric;record['usage_rows'].append(numeric)
                if kind in ('item.started','item.completed'):
                    if item.get('type') in KNOWN_TOOL_TYPES:
                        projected={'perf_ns':received,'type':kind,'item':item};record['public_events'].append(projected)
                        if item.get('type')!='mcp_tool_call' or item.get('server')!='arm_engine' or item.get('tool') not in expected_tools:
                            record['unexpected_tool_deviations'].append(projected)
                        if kind=='item.completed' and item.get('type')=='mcp_tool_call':
                            record['tool_calls'].append(projected)
                            record['image_deliveries'].extend(completed_images(item, received, len(raw)))
                            if len(record['tool_calls']) > 12:
                                raise ValueError('route_twelve_tool_call_limit')
                    if item.get('type')=='agent_message' and kind=='item.completed':
                        text=item.get('text','');record['all_public_messages'].append({'perf_ns':received,'id':item.get('id'),'text':text})
                        record['final']=text;record['final_received_ns']=received
            process.wait(timeout=max(.01,(deadline-time.perf_counter_ns())/1e9))
            record['process_exit_ns']=time.perf_counter_ns()
        if record['final'] is not None:
            # Preserve the public item bytes as the answer even if -o is absent.
            record['cli_output_file_present']=final.exists()
            record['cli_output_matches_public_final']=None if not final.exists() else final.read_text(encoding='utf8')==record['final']
            (folder/'PUBLIC_FINAL.txt').write_bytes(record['final'].encode('utf8'))
        record['valid_completion']=bool(process.returncode==0 and record['thread_id']
            and record['turn_completed_ns'] and record['final_received_ns'] and not fired.is_set()
            and record['turn_completed_ns']<deadline and not record['errors'] and not record['unexpected_tool_deviations'])
    except BaseException as error:record['errors'].append({'type':type(error).__name__,'message':str(error)})
    finally:
        if timer is not None:timer.cancel();timer.join(timeout=15)
        if process is not None and process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=max(.01, min(5., (deadline - time.perf_counter_ns()) / 1e9)))
            except BaseException as error:
                record['errors'].append({'stage': 'CLI_before_thin_exit_wait', 'type': type(error).__name__, 'message': str(error)})
        record['runtime_exit'] = runtime_handle.wait_exit(held_runtime, deadline)
        record['process_cleanup']=launch.stop_process(process, timeout=5) if process is not None else None
        record['process_reaped']=bool(record['process_cleanup'] and record['process_cleanup']['confirmed'])
        record['exit_code']=None if record['process_cleanup'] is None else record['process_cleanup']['exit_code']
        if record['process_exit_ns'] is None and record['process_reaped']:record['process_exit_ns']=time.perf_counter_ns()
        for thread in readers:
            if thread.ident is not None:thread.join(timeout=1)
        record['readers_stopped']=all(not thread.is_alive() for thread in readers)
        record['deadline_timer_fired']=fired.is_set()
        record['bridge_cleanup']=wait_bridge_closed(dict(cell,attachments_dir=str(folder/'attachments')))
        bridge_path=Path(cell['audit_dir'])/'BRIDGE_RESULT.json'
        bridge=read(bridge_path) if bridge_path.exists() else {}
        unknown=any(call.get('result',{}).get('status')=='execution_uncertain' for call in bridge.get('calls',[]))
        record['mutation_unknown']=unknown
        record['bridge_protocol_errors']=bridge.get('protocol_errors',[])
        record['safe_to_continue']=bool(record['process_reaped'] and record['readers_stopped']
            and record['runtime_binding'] and record['runtime_binding']['confirmed'] is True
            and record['runtime_exit']['confirmed'] is True
            and record['bridge_cleanup'].get('confirmed') is not False
            and not record.get('multiple_thin_runtime_starts') and not unknown and not record['bridge_protocol_errors'])
        record['safe_to_continue_scope']='CLI original handle and readers, plus read-only STARTED-bound actual thin image/creation/ancestry and retained-handle exit. Missing EXIT remains unknown; proven actual exit permits continuation. Actor closure remains external.'
        try:
            record['initial_image_unchanged']=initial_image_metadata(plan)==image
        except (OSError,ValueError,KeyError) as exc:
            record['initial_image_unchanged']=False;record['errors'].append({'type':type(exc).__name__,'message':str(exc)})
        if not record['initial_image_unchanged']:
            record['valid_completion']=False;record['safe_to_continue']=False
        image_telemetry(record, folder)
        stdout_raw = folder / 'stdout.raw.bin'
        record['stdout_raw_bytes'] = stdout_raw.stat().st_size if stdout_raw.exists() else None
        record['stdout_raw_sha256'] = sha(stdout_raw) if stdout_raw.exists() else None
        record['raw_usage_events'] = raw_usage_events
        record['summary'] = cli.summarize_turn(logged_events, episode_id=episode_id, turn_index=turn_index,
            expected_thread_id=expected_thread_id, exit_code=record['exit_code'])
        record['usage_semantics'] = 'unconfirmed_turn_or_session_scope'
        record['usage_aggregation'] = None
        record['valid_completion'] = record['valid_completion'] and record['summary']['valid_completion'] and record['safe_to_continue']
        try:
            record['archive'] = archive_turn(folder, cell, first_attempt, record['tool_calls'])
            if record['archive']['business_binding_errors']:
                record['errors'].append({'stage': 'business_original_binding', 'errors': record['archive']['business_binding_errors']})
                record['valid_completion'] = False
        except BaseException as error:
            record['errors'].append({'stage': 'raw_archive', 'type': type(error).__name__, 'message': str(error)})
            record['valid_completion'] = False
        record['cleanup_end_ns']=time.perf_counter_ns();record['wall_ns']=record['cleanup_end_ns']-began
        if record['cleanup_end_ns'] >= deadline:
            record['errors'].append({'type': 'TimeoutError', 'message': 'original_turn_deadline_through_cleanup_and_archive'})
            record['valid_completion'] = False
        if record['errors'] or record['unexpected_tool_deviations']:
            record['valid_completion'] = False
        record['summary']['valid_completion'] = record['valid_completion']
        record['summary']['execution_state'] = 'completed' if record['valid_completion'] else 'failed'
        record['summary']['consumer_errors'] = record['errors']
        record['summary']['archive'] = record.get('archive')
        record['summary']['execution_kind'] = execution_kind
        record['prompt_to_final_ns']=None if record['final_received_ns'] is None or record['prompt_submitted_ns'] is None else record['final_received_ns']-record['prompt_submitted_ns']
        record['public_text_bytes']=sum(len(row['text'].encode('utf8')) for row in record['all_public_messages'])
        record['output_text_bytes']=None if record['final'] is None else len(record['final'].encode('utf8'))
        record['status']='completed' if record['valid_completion'] else 'failed'
        record['bridge_public_text_bytes']=bridge.get('public_text_bytes')
        record['validity_scope'] = 'Includes cleanup and archive. FINAL_TIMING is authoritative through CONSUMER write/close.'
        save(folder/'CONSUMER.json',record)
        closed_ns = time.perf_counter_ns()
        if record['valid_completion'] and closed_ns >= deadline:
            record['valid_completion'] = False
            record['status'] = 'failed'
            record['errors'].append({'type': 'TimeoutError', 'message': 'original_turn_deadline_during_consumer_publication'})
            record['summary']['valid_completion'] = False
            record['summary']['execution_state'] = 'failed'
            save(folder/'CONSUMER.json', record)
            closed_ns = time.perf_counter_ns()
        timing = {'started_ns': began, 'consumer_record_closed_ns': closed_ns,
                  'full_turn_wall_ns': closed_ns - began, 'original_turn_deadline_ns': deadline,
                  'episode_deadline_ns': episode_deadline_ns, 'accepted_success': record['valid_completion'] and closed_ns < deadline,
                  'scope': 'Before input/workspace checks through process, events, CLI/thin cleanup, raw archive and CONSUMER write/close.'}
        if not timing['accepted_success']:
            record['valid_completion'] = False
            record['status'] = 'failed'
            record['summary']['valid_completion'] = False
            record['summary']['execution_state'] = 'failed'
        record['final_timing'] = timing
        save(folder/'FINAL_TIMING.json',timing)
        for stream in (() if process is None else (process.stdin, process.stdout, process.stderr)):
            if stream is not None:stream.close()
    return record
