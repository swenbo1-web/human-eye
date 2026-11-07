$ErrorActionPreference = 'Stop'
$evidenceRoot = Split-Path $PSScriptRoot -Parent
$records = [Collections.Generic.List[object]]::new()
foreach ($file in Get-ChildItem -LiteralPath $evidenceRoot -Filter '*.process.json') {
    $record = Get-Content -Raw -LiteralPath $file.FullName | ConvertFrom-Json
    if ($record.launcher_pid) {
        $records.Add([ordered]@{source=$file.Name;pid=$record.launcher_pid;ended_utc=$record.ended_utc;creation_utc=$null})
    }
    foreach ($observed in $record.observed) {
        if ($observed.ProcessId) {
            $created = if ($observed.CreationDate) { ([DateTimeOffset]$observed.CreationDate).ToUniversalTime().ToString('o') } else { $null }
            $records.Add([ordered]@{source=$file.Name;pid=$observed.ProcessId;ended_utc=$record.ended_utc;creation_utc=$created})
        }
    }
}
$comparison = Get-Content -Raw -LiteralPath (Join-Path $evidenceRoot 'comparison/RESULT.json') | ConvertFrom-Json
foreach ($session in $comparison.sessions) {
    foreach ($ownedId in @($session.launcher_pid,$session.ready.pid,$session.ready.worker_pid)) {
        if ($ownedId) {
            $records.Add([ordered]@{source=('comparison/'+$session.sequence+'_'+$session.version);pid=$ownedId;ended_utc=$session.ended_utc;creation_utc=$null})
        }
    }
}
$current = @(Get-CimInstance Win32_Process)
$checks = foreach ($record in $records) {
    $live = @($current | Where-Object { $_.ProcessId -eq $record.pid })
    $classification = 'absent'
    $currentCreated = $null
    if ($live.Count -gt 0) {
        $currentCreated = ([DateTimeOffset]$live[0].CreationDate).ToUniversalTime()
        if ($currentCreated -gt [DateTimeOffset]$record.ended_utc) { $classification='pid_reused_after_original_end' }
        elseif ($record.creation_utc -and $currentCreated -ne [DateTimeOffset]$record.creation_utc) { $classification='different_creation_time' }
        else { $classification='possibly_still_owned' }
    }
    [ordered]@{source=$record.source;pid=$record.pid;original_creation_utc=$record.creation_utc;original_end_utc=$record.ended_utc;classification=$classification;current_creation_utc=$(if($currentCreated){$currentCreated.ToString('o')}else{$null})}
}
$rootPattern = [regex]::Escape($evidenceRoot.Replace('/','\'))
$matching = @($current | Where-Object { $_.Name -match '^(python|blender)(\.exe)?$' -and $_.CommandLine -match $rootPattern } | Select-Object Name,ProcessId,ParentProcessId,CreationDate,CommandLine)
$closeReceipts = @($comparison.sessions | ForEach-Object {
    [ordered]@{sequence=$_.sequence;version=$_.version;launcher_exit_code=$_.launcher_exit_code;worker_exit_code=$_.worker_exit_code;worker_exited=$_.worker_exited;worker_reaped=$_.close_reply.result.process_reaped;forced_cleanup=$_.forced_cleanup;watchdog_joined=$_.watchdog_joined;source_file_unchanged=$_.close_reply.result.source_file_unchanged;protected_files_unchanged=$_.close_reply.result.protected_files_unchanged}
})
$forcedSessionCount = @($comparison.sessions | Where-Object { $_.forced_cleanup.Count -gt 0 }).Count
$forcedStepCount = @(Get-ChildItem -LiteralPath $evidenceRoot -Filter '*.process.json' | ForEach-Object { Get-Content -Raw -LiteralPath $_.FullName | ConvertFrom-Json } | Where-Object { $_.forced_tree_cleanup }).Count
$result = [ordered]@{checked_utc=[DateTimeOffset]::UtcNow.ToString('o');scope='recorded launcher/observed identities and eight session broker/worker identities; active Python/Blender command lines containing this B engineering root; read-only snapshot, no process termination';original_records=$checks;unique_recorded_pid_count=@($records.pid | Sort-Object -Unique).Count;matching_live_processes=$matching;possibly_owned_count=@($checks | Where-Object {$_.classification -eq 'possibly_still_owned'}).Count;forced_session_cleanup_count=$forcedSessionCount;forced_step_cleanup_count=$forcedStepCount;unrelated_reused_pids_terminated=0;session_close_receipts=$closeReceipts;cli_scope='successful subprocess.run observes were individually returned/reaped; their PIDs are not retained by the existing wrapper'}
[IO.File]::WriteAllText((Join-Path $evidenceRoot 'CLEANUP.json'),($result | ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
if ($result.possibly_owned_count -ne 0 -or $matching.Count -ne 0) { throw 'Owned process remains or PID identity requires review; no process was killed' }
Write-Output ('Cleanup verified: '+$checks.Count+' historical identity records; no B owned process remains')
