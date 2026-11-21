"""Check the fixed consumer, fresh prompt delivery and checked early shutdown."""

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import driver


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def run(root):
    turn,proof,metadata = driver.consumer_adapter()
    cli = proof['CLI_path']
    check = subprocess.run([cli,'--version'],timeout=20,capture_output=True,check=True)
    login = subprocess.run([cli,'login','status'],timeout=20,capture_output=True,check=True)
    require(check.stdout.decode().strip()=='codex-cli 0.152.1'
            and (login.stdout+login.stderr).decode().strip()=='Logged in using ChatGPT',
            'fixed_existing_CLI_or_ChatGPT_login_unavailable')
    require(turn.__globals__['safe_environment']({
        'OPENAI_API_KEY':'sentinel','GOOGLE_API_KEY':'sentinel','CODEX_THREAD_ID':'sentinel','Keep':'value'})=={'Keep':'value'},
        'alternative_credentials_or_thread_context_not_filtered')
    root.mkdir(parents=True,exist_ok=False)
    records = {}
    for label in ('A1','B1'):
        slot = root/label
        slot.mkdir()
        endpoint = slot/'ENDPOINT.json'
        owner = slot/'owner'
        owner.mkdir()
        deadline = time.perf_counter_ns()+50_000_000_000
        endpoint.write_text(json.dumps({'chain_deadline_ns':deadline,'host':'127.0.0.1'}),encoding='utf8')
        marker = slot/'STDIN.bin'
        probe = slot/'stdin_echo.py'
        probe.write_text(f'from pathlib import Path\nimport sys\nPath({str(marker)!r}).write_bytes(sys.stdin.buffer.read())\nraise SystemExit(7)\n',encoding='utf8')
        offline = {'command':[proof['Python_path'],'-I','-B',str(probe)],'script_sha256':sha256(probe.read_bytes()).hexdigest()}

        def local_turn(**entry):
            require(entry['expected_thread_id'] is None and entry['turn_index']==1
                    and not entry['work'].exists() and not entry['folder'].exists()
                    and entry['prompt']==driver.PROMPT.read_bytes(),'actual_consumer_not_fresh_and_identical')
            return turn(**entry,local_cli=offline)

        with patch.object(driver,'consumer_adapter',return_value=(local_turn,proof,metadata)):
            result = driver.consume_slot(label,slot,endpoint,owner,deadline,deadline+150_000_000_000)
        record = driver.read(Path(result['consumer_record']))
        require(marker.read_bytes()==driver.PROMPT.read_bytes()
                and record['execution_kind']=='synthetic_local_process' and record['status']=='failed'
                and record['exit_code']==7 and record['process_reaped'] and record['readers_stopped']
                and not record['valid_completion'] and not record['tool_calls'] and record['thread_id'] is None,
                'real_consumer_early_exit_did_not_keep_failure_and_close')
        literal = str(slot)
        escaped = literal.replace('\u005c','\u005c\u005c')
        argv = [item.replace(escaped,'<slot>').replace(literal,'<slot>') for item in record['frozen_cli_argv']]
        records[label] = {'argv':argv,'stdin_bytes':marker.stat().st_size,'stdin_sha256':sha256(marker.read_bytes()).hexdigest(),
                          'early_exit_code':7,'readers_stopped':True,'provider_model_launched':False}
    require(records['A1']==records['B1'] and records['A1']['stdin_sha256']==driver.PROMPT_SHA,
            'paired_real_CLI_configuration_or_prompt_differed')
    summary = {'passed':True,'provider_model_launches':0,'Blender_launches':0,'CLI':'0.152.1',
               'login_status':'Logged in using ChatGPT','proof':proof,'arms':records}
    driver.save(root/'PREFLIGHT.json',summary)
    print(json.dumps({'passed':True,'model':proof['model'],'same_requested_args':True}))


if __name__=='__main__':
    run(Path(sys.argv[1]))
