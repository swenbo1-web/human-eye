"""Exactly two zero-consumer complete-config parses; no exec or MCP startup.

The features command lacks exec's ignore-user-config/strict-config flags. It
therefore checks the complete override values with inherited config, and is
explicitly not an exec, injection, authentication, or model-availability proof.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
import types

HERE=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-sha256',required=True)
    parser.add_argument('--runner-sha256',required=True)
    args=parser.parse_args()
    plan_raw=(HERE/'PLAN.json').read_bytes();runner_raw=(HERE/'runner.py').read_bytes()
    assert sha(plan_raw)==args.plan_sha256 and sha(runner_raw)==args.runner_sha256,'fixed_candidate_changed'
    plan=json.loads(plan_raw)
    assert plan['execution_ready'] is False,'offline_preparation_only'
    assert not any(key.startswith('mcp_servers.') for key in plan['codex']['settings']), 'candidate_has_unexpected_MCP_overrides'
    runner=types.ModuleType('_startup_config_parse_runner');runner.__file__=str(HERE/'runner.py')
    sys.modules[runner.__name__]=runner
    exec(compile(runner_raw,str(HERE/'runner.py'),'exec',dont_inherit=True),runner.__dict__)
    assert callable(runner.retain_startup_diagnostic)
    env=runner.safe_environment(os.environ)
    assert 'CODEX_PERMISSION_PROFILE' not in env,'parent_permission_selector_not_removed'
    exe=Path(plan['codex']['executable'])
    assert sha(exe.read_bytes())==plan['codex']['sha256'],'CLI_binary_changed'
    out=HERE/'config_parse_001';out.mkdir(exist_ok=False)
    started=datetime.now(timezone.utc).isoformat();cases=[];attempts=0
    limits=dict(max_cli_parse_calls=2,exec_consumers=0,Blender=0,MCP_services=0,RPC=0,model_API=0)
    save(out/'STARTED.json',dict(started_utc=started,plan_sha256=args.plan_sha256,
        runner_sha256=args.runner_sha256,CLI_sha256=plan['codex']['sha256'],limits=limits,
        inherited_permission_selector_excluded=True,authentication_values_read=False,
        config_scope='features list inherits user/project configuration; all candidate -c values supplied; exec-only flags omitted'))
    feature_row=re.compile(r'^[A-Za-z0-9_]+\s+(?:stable|experimental|under development|deprecated|removed)\s+(?:true|false)\s*$')
    for arm in ('N','P'):
        folder=out/arm;folder.mkdir();work=folder/'work';work.mkdir()
        cell=folder/'CELL.json';save(cell,dict(arm=arm))
        candidate_argv=runner.argv_for(plan,cell,work,folder/'unused_final.txt')
        assert candidate_argv[1]=='exec' and '--strict-config' in candidate_argv and '--ignore-user-config' in candidate_argv
        pairs=[];transport={}
        for index,part in enumerate(candidate_argv[:-1]):
            if part!='-c':continue
            override=candidate_argv[index+1];key,value=override.split('=',1)
            if key.startswith('mcp_servers.'):
                assert key in ('mcp_servers.native','mcp_servers.human_eye')
                table=tomllib.loads('server='+value)['server']
                assert table.get('command') and isinstance(table.get('args'),list) and table.get('cwd')
                assert table.get('required') is True
                table['enabled']=False
                transport[key]=table
                override=key+'='+runner.toml_value(table)
            pairs.append(override)
        assert set(transport)==({'mcp_servers.native'} if arm=='N' else {'mcp_servers.native','mcp_servers.human_eye'})
        command=[str(exe),'features','list']
        for value in pairs:command.extend(['-c',value])
        assert 'exec' not in command and 'debug' not in command and '--ignore-user-config' not in command and '--strict-config' not in command
        attempts+=1;assert attempts<=2
        save(out/'ATTEMPTS.json',dict(attempted=attempts,maximum=2,latest_arm=arm,no_retries=True))
        record=dict(arm=arm,argv=command,source_runtime_exec_argv=candidate_argv,cwd=str(work),
            candidate_override_count=len(pairs),full_disabled_transports=transport,
            started_utc=datetime.now(timezone.utc).isoformat(),started_ns=time.perf_counter_ns(),
            stderr_bytes=0,timeout=False,raw_stdout_bytes=0,raw_stderr_bytes=0)
        save(folder/'COMMAND.json',record)
        process=None
        try:
            process=subprocess.Popen(command,cwd=work,env=env,stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            record['pid']=process.pid;save(folder/'OWNED_PROCESS.json',record)
            try:stdout,stderr=process.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill();stdout,stderr=process.communicate(timeout=5)
                record.update(timeout=True,error='features_list_timeout; owned process killed/waited')
            record['exit_code']=process.returncode
        except OSError as error:
            stdout=b'';stderr=b''
            record.update(exit_code=None,error_type=type(error).__name__,error='CLI configuration process startup failed; no retry')
        record['process_reaped']=process is not None and process.poll() is not None
        record['elapsed_ns']=time.perf_counter_ns()-record['started_ns']
        record['raw_stdout_bytes']=len(stdout);record['raw_stderr_bytes']=len(stderr)
        record['raw_stdout_sha256']=sha(stdout)
        accepted=[];redacted=0
        for line in stdout.splitlines(keepends=True):
            try:text=line.decode('utf8').rstrip('\r\n')
            except UnicodeError: redacted+=1;continue
            if not text.strip() or feature_row.fullmatch(text):accepted.append(line)
            else:redacted+=1
        safe_stdout=b''.join(accepted)
        (folder/'FEATURES.safe.txt').write_bytes(safe_stdout)
        record.update(feature_rows_retained=sum(bool(line.strip()) for line in accepted),
            stdout_lines_redacted=redacted,stdout_all_lines_validated=redacted==0,
            safe_stdout_bytes=len(safe_stdout))
        for line in stderr.splitlines(keepends=True):runner.retain_startup_diagnostic(record,line)
        save(folder/'RESULT.json',record);cases.append(record)
    unchanged=sha((HERE/'PLAN.json').read_bytes())==args.plan_sha256 and sha((HERE/'runner.py').read_bytes())==args.runner_sha256
    result=dict(started_utc=started,ended_utc=datetime.now(timezone.utc).isoformat(),cases=cases,
        CLI_parse_calls=attempts,maximum=2,all_exit_zero=all(c['exit_code']==0 for c in cases),candidate_unchanged=unchanged,
        passed=unchanged and len(cases)==2 and all(c['exit_code']==0 for c in cases),
        plan_sha256=args.plan_sha256,runner_sha256=args.runner_sha256,CLI_sha256=plan['codex']['sha256'],
        activity=limits,scope='two complete candidate override configurations with full transports enabled=false; no exec, prompt, server or RPC',
        limitations='features list loads inherited user/project config and does not support exec-only ignore-user-config/strict-config; no actual exec/injection/model/runtime proof',
        original_71byte_error_recovered=False,extra_calls_or_retries=0)
    save(out/'RESULTS.json',result)
    print(json.dumps(dict(CLI_parse_calls=attempts,all_exit_zero=result['all_exit_zero'],candidate_unchanged=unchanged,
        cases=[dict(arm=c['arm'],exit_code=c['exit_code'],candidate_override_count=c['candidate_override_count'],raw_stderr_bytes=c['raw_stderr_bytes']) for c in cases])))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
