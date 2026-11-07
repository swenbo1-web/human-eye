$ErrorActionPreference='Stop'
$evidenceRoot=Split-Path $PSScriptRoot -Parent
$records=[Collections.Generic.List[object]]::new()
foreach($file in Get-ChildItem -LiteralPath $evidenceRoot -Filter '*.process.json'){
 $r=Get-Content -Raw -LiteralPath $file.FullName|ConvertFrom-Json
 $records.Add([ordered]@{source=$file.Name;pid=$r.launcher_pid;ended_utc=$r.ended_utc;creation_utc=$null})
 foreach($p in $r.observed){$records.Add([ordered]@{source=$file.Name;pid=$p.ProcessId;ended_utc=$r.ended_utc;creation_utc=([DateTimeOffset]$p.CreationDate).ToUniversalTime().ToString('o')})}
}
$qualification=Get-Content -Raw -LiteralPath (Join-Path $evidenceRoot 'QUALIFICATION.json')|ConvertFrom-Json
$receipts=[Collections.Generic.List[object]]::new()
foreach($q in $qualification.cases){
 foreach($ownedId in @($q.launcher_pid,$q.ready.pid,$q.ready.worker_pid)){$records.Add([ordered]@{source=('qualification/'+$q.case);pid=$ownedId;ended_utc=$q.ended_utc;creation_utc=$null})}
 $receipts.Add([ordered]@{source=('qualification/'+$q.case);launcher_exit_code=$q.launcher_exit_code;worker_exit_code=$q.worker_exit_code;watchdog_joined=$q.watchdog_joined;forced_cleanup=$q.forced_cleanup;worker_reaped=$q.close_reply.result.process_reaped;source_file_unchanged=$q.close_reply.result.source_file_unchanged;protected_files_unchanged=$q.close_reply.result.protected_files_unchanged})
}
foreach($file in Get-ChildItem -LiteralPath (Join-Path $evidenceRoot 'chains') -Filter FINAL.json -Recurse){
 $f=Get-Content -Raw -LiteralPath $file.FullName|ConvertFrom-Json
 $chainId=$file.Directory.Name
 $launch=Get-Content -Raw -LiteralPath (Join-Path $evidenceRoot ('owner_'+$chainId+'.LAUNCH.json'))|ConvertFrom-Json
 foreach($ownedId in @($launch.pid,$f.launcher_pid,$f.ready.pid,$f.ready.worker_pid)){$records.Add([ordered]@{source=('chains/'+$chainId);pid=$ownedId;ended_utc=$f.ended_utc;creation_utc=$null})}
 $receipts.Add([ordered]@{source=('chains/'+$chainId);launcher_exit_code=$f.launcher_exit_code;worker_exit_code=$f.worker_exit_code;watchdog_joined=$f.watchdog_joined;forced_cleanup=$f.forced_cleanup;worker_reaped=$f.close_reply.result.process_reaped;source_file_unchanged=$f.close_reply.result.source_file_unchanged;protected_files_unchanged=$f.close_reply.result.protected_files_unchanged})
}
$current=@(Get-CimInstance Win32_Process)
$checks=foreach($record in $records){
 $live=@($current|Where-Object{$_.ProcessId -eq $record.pid})
 $classification='absent';$created=$null
 if($live.Count -gt 0){$created=([DateTimeOffset]$live[0].CreationDate).ToUniversalTime();if($created -gt [DateTimeOffset]$record.ended_utc){$classification='pid_reused_after_original_end'}elseif($record.creation_utc -and $created -ne [DateTimeOffset]$record.creation_utc){$classification='different_creation_time'}else{$classification='possibly_still_owned'}}
 [ordered]@{source=$record.source;pid=$record.pid;original_end_utc=$record.ended_utc;original_creation_utc=$record.creation_utc;classification=$classification;current_creation_utc=$(if($created){$created.ToString('o')}else{$null})}
}
$pattern=[regex]::Escape($evidenceRoot.Replace('/','\'))
$matching=@($current|Where-Object{$_.Name -match '^(python|blender)(\.exe)?$' -and $_.CommandLine -match $pattern}|Select-Object Name,ProcessId,CreationDate,CommandLine)
$bad=@($receipts|Where-Object{$_.launcher_exit_code -ne 0 -or $_.worker_exit_code -ne 0 -or -not $_.watchdog_joined -or $_.forced_cleanup.Count -gt 0 -or -not $_.worker_reaped -or -not $_.source_file_unchanged -or -not $_.protected_files_unchanged})
$result=[ordered]@{checked_utc=[DateTimeOffset]::UtcNow.ToString('o');scope='original recorded process identities and active Python/Blender command lines containing this run root';historical_records=$checks;unique_recorded_pids=@($records.pid|Sort-Object -Unique).Count;matching_live_processes=$matching;possibly_owned_count=@($checks|Where-Object{$_.classification -eq 'possibly_still_owned'}).Count;session_close_receipts=$receipts;session_count=$receipts.Count;bad_close_receipt_count=$bad.Count;processes_terminated_by_this_check=0;cli_process_scope='all actual subprocess.run attempts returned/reaped; existing CLI wrapper does not retain PID';codex_consumers='eight completed collaboration tasks; no followup/resample'}
[IO.File]::WriteAllText((Join-Path $evidenceRoot 'CLEANUP.json'),($result|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
if($result.possibly_owned_count -ne 0 -or $matching.Count -ne 0 -or $bad.Count -ne 0 -or $receipts.Count -ne 10){throw 'Cleanup identity/receipt mismatch; no process was terminated'}
'Cleanup verified: '+$checks.Count+' historical identities; 10 sessions closed; no owned process remains'
