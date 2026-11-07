$ErrorActionPreference = 'Stop'
$evidenceRoot = Split-Path $PSScriptRoot -Parent
$records = [Collections.Generic.List[object]]::new()
foreach ($file in Get-ChildItem -LiteralPath $evidenceRoot -Filter '*.process.json') {
    $record = Get-Content -Raw -LiteralPath $file.FullName | ConvertFrom-Json
    $records.Add([ordered]@{source=$file.Name;pid=$record.launcher_pid;ended_utc=$record.ended_utc;creation_utc=$null})
    foreach ($observed in $record.observed) {
        $records.Add([ordered]@{source=$file.Name;pid=$observed.ProcessId;ended_utc=$record.ended_utc;creation_utc=([DateTimeOffset]$observed.CreationDate).ToUniversalTime().ToString('o')})
    }
}
$asset = Get-Content -Raw -LiteralPath (Join-Path $evidenceRoot 'ASSET_BUILD_PROCESS.json') | ConvertFrom-Json
$records.Add([ordered]@{source='ASSET_BUILD_PROCESS.json';pid=$asset.pid;ended_utc=$asset.ended_utc;creation_utc=$null})
$acceptance = Get-Content -Raw -LiteralPath (Join-Path $evidenceRoot 'acceptance/RESULT.json') | ConvertFrom-Json
foreach ($case in $acceptance.cases) {
    foreach ($ownedId in @($case.launcher_pid,$case.ready.pid,$case.ready.worker_pid)) {
        $records.Add([ordered]@{source=('acceptance/'+$case.case);pid=$ownedId;ended_utc=$case.ended_utc;creation_utc=$null})
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
$result = [ordered]@{checked_utc=[DateTimeOffset]::UtcNow.ToString('o');scope='original recorded process identity plus active python/blender command lines containing this engineering root';original_records=$checks;matching_live_processes=$matching;possibly_owned_count=@($checks | Where-Object {$_.classification -eq 'possibly_still_owned'}).Count;forced_cleanup_count=0;unrelated_reused_pids_terminated=0;session_close_receipts=@($acceptance.cases | ForEach-Object { [ordered]@{case=$_.case;launcher_exit_code=$_.launcher_exit_code;worker_exit_code=$_.close_reply.result.exit_code;worker_reaped=$_.close_reply.result.process_reaped;forced_cleanup=$_.forced_cleanup;source_file_unchanged=$_.close_reply.result.source_file_unchanged;protected_files_unchanged=$_.close_reply.result.protected_files_unchanged} })}
[IO.File]::WriteAllText((Join-Path $evidenceRoot 'CLEANUP.json'),($result | ConvertTo-Json -Depth 7)+"`n",[Text.UTF8Encoding]::new($false))
if ($result.possibly_owned_count -ne 0 -or $matching.Count -ne 0) { throw 'Owned process remains or identity requires review' }
Write-Output ('Cleanup verified: '+$checks.Count+' original records; no owned process remains')
