function Invoke-EngineeringStep {
    param([string]$Label, [string]$Executable, [string[]]$Arguments, [int]$LimitSeconds = 180)
    $window = Get-Content -Raw (Join-Path $EngineeringRoot 'WINDOW.json') | ConvertFrom-Json
    $now = [DateTimeOffset]::UtcNow
    if ($now -ge [DateTimeOffset]$window.stop_new_experiments_utc) { throw 'New experiment cutoff reached' }
    $remaining = ([DateTimeOffset]$window.turn_deadline_utc - $now).TotalSeconds
    $limit = [Math]::Min($LimitSeconds, [Math]::Floor($remaining))
    $stem = Join-Path $EngineeringRoot $Label
    if (Test-Path -LiteralPath ($stem + '.process.json')) { throw 'Step replay refused' }
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $EngineeringRoot -WindowStyle Hidden -RedirectStandardOutput ($stem + '.stdout.log') -RedirectStandardError ($stem + '.stderr.log') -PassThru
    $null = $process.Handle
    $pidValue = $process.Id
    $observed = @(Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue OR ParentProcessId=$pidValue" | Select-Object Name,ProcessId,ParentProcessId,CreationDate,CommandLine)
    $completed = $process.WaitForExit([int]($limit * 1000))
    if (-not $completed) { $process.Kill($true); $null = $process.WaitForExit(10000) }
    $timer.Stop()
    $exitCode = $process.ExitCode
    $record = [ordered]@{started_utc=$now.ToString('o');ended_utc=[DateTimeOffset]::UtcNow.ToString('o');wall_seconds=$timer.Elapsed.TotalSeconds;executable=$Executable;argv=$Arguments;launcher_pid=$pidValue;exit_code=$exitCode;forced_tree_cleanup=(-not $completed);observed=$observed}
    [IO.File]::WriteAllText(($stem + '.process.json'), ($record | ConvertTo-Json -Depth 5) + "`n", [Text.UTF8Encoding]::new($false))
    $process.Dispose()
    if (-not $completed -or $exitCode -ne 0) { throw ($Label + ' failed exit ' + $exitCode) }
    Write-Output ($Label + ' completed in ' + [Math]::Round($timer.Elapsed.TotalSeconds, 4) + 's')
}
