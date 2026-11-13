$ErrorActionPreference = 'Stop'
$taskOut = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskAuthor = 'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_002'
$taskPrior = 'D:/hefe/verification/fixes/20261104_visual_benefit004a_r2/qualification'
$taskInputs = @(
    "$taskAuthor/runner.py", "$taskAuthor/runtime.py", "$taskAuthor/validate.py",
    "$taskAuthor/RESULTS.json", "$taskAuthor/runs/main_p01_A/RESULT.json", "$taskAuthor/runs/main_p01_A/TRACE.jsonl",
    "$taskAuthor/PID_BINDING_DIAGNOSIS.json",
    "$taskPrior/run_minimal_calibration_r2.py", "$taskPrior/minimal_calibration_r1/RESULT.json", "$taskPrior/minimal_calibration_r2/RESULT.json",
    'D:/hefe/verification/fixes/20261028_audit_rotation/retired_runtime_v20/verification/test_audit_log_independent.py',
    'D:/hefe/verification/fixes/20261106_perf020_o4/harness/qa_resources.py',
    'D:/hefe/verification/fixes/20261106_perf020_o4/harness/lifecycle.py',
    'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/pyvenv.cfg',
    'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/venv/__init__.py',
    'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/subprocess.py',
    'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe',
    'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
)
$taskSources = @($taskInputs | ForEach-Object {
    $file = Get-Item -LiteralPath $_
    [ordered]@{path=$file.FullName;bytes=$file.Length;sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()}
})
$taskResult = Get-Content -LiteralPath "$taskAuthor/RESULTS.json" -Raw | ConvertFrom-Json
$taskChild = Get-Content -LiteralPath "$taskAuthor/runs/main_p01_A/RESULT.json" -Raw | ConvertFrom-Json
$taskTrace = @(Get-Content -LiteralPath "$taskAuthor/runs/main_p01_A/TRACE.jsonl" | ForEach-Object { $_ | ConvertFrom-Json })
$taskHistorical = @()
foreach ($version in @('r1','r2')) {
    $item = Get-Content -LiteralPath "$taskPrior/minimal_calibration_$version/RESULT.json" -Raw | ConvertFrom-Json
    $conditions = @($item.conditions | ForEach-Object {
        [ordered]@{condition=$_.condition;passed=$_.passed;owner_pid=$_.owner_pid;broker_pid=$_.broker_state.owner_pid;owner_exit_code=$_.owner_exit_code;owner_wait_completed=$_.owner_wait_completed;lifecycle_ok=$_.lifecycle_ok;exe=$_.owner_command[0];errors=$_.errors}
    })
    $taskHistorical += [ordered]@{version=$version;passed=$item.passed;scope=$item.scope;conditions=$conditions}
}
$taskExe = @($taskInputs[-2..-1] | ForEach-Object { $file=Get-Item -LiteralPath $_; [ordered]@{path=$file.FullName;bytes=$file.Length;original_filename=$file.VersionInfo.OriginalFilename;product_version=$file.VersionInfo.ProductVersion} })
$taskFacts = [ordered]@{
    scope='Read-only static/source/resource/original JSON review; no Python probe/candidate execution or new renderer/benchmark/Blender/model/API.'
    source_commit='35e9321121e5ca8e9a8414dab859cd6361da4d9c'
    sources=$taskSources
    current=[ordered]@{
        parent_pid=$taskResult.rows[0].process_id;runtime_pid=$taskChild.process_id;trace_pids=@($taskTrace.process_id|Sort-Object -Unique)
        parent_slot_status=$taskResult.rows[0].status;parent_returncode=$taskResult.rows[0].returncode;error=$taskResult.rows[0].error
        child_status=$taskChild.status;child_exceptions=$taskChild.exceptions;child_metrics=$taskChild.metrics
        output_directory_equal=($taskResult.rows[0].output_directory -eq $taskChild.output_directory)
        child_window_inside_parent=($taskResult.rows[0].started_ns -le $taskChild.started_ns -and $taskChild.started_ns -le $taskChild.work_closed_ns -and $taskChild.work_closed_ns -le $taskResult.rows[0].process_exited_ns)
        frozen_summary=$taskResult.summary;live_lineage='not recorded; unknown';exceptional_tree_cleanup='not exercised; unknown'
    }
    executables=$taskExe
    existing_same_issue_and_base_route=$taskHistorical
    recommended_route='Fixed direct base interpreter, explicit existing venv dependency path and fixed product path; strict PID equality retained; four no-raster launch/cleanup qualifications before new formal denominator.'
    unrun=@('new base launch normal qualification','new nonzero exception qualification','new timeout cleanup qualification','new receipt failure qualification','new main B/control/render/benchmark')
}
$taskJson = $taskFacts | ConvertTo-Json -Depth 35
[System.IO.File]::WriteAllText((Join-Path $taskOut 'EVIDENCE.json'), $taskJson + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
[ordered]@{sources=$taskSources.Count;current_parent_pid=$taskFacts.current.parent_pid;current_runtime_pid=$taskFacts.current.runtime_pid;trace_pids=$taskFacts.current.trace_pids;output_directory_equal=$taskFacts.current.output_directory_equal;child_window_inside_parent=$taskFacts.current.child_window_inside_parent;historical_r1_passed=$taskHistorical[0].passed;historical_r2_passed=$taskHistorical[1].passed} | ConvertTo-Json -Depth 8
