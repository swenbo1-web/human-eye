function Invoke-TrialStep {
    param([string]$Label, [string]$Executable, [string[]]$Arguments, [int]$LimitSeconds = 180)
    $windowPath = Join-Path $TrialRunRoot 'WINDOW.json'
    if (-not (Test-Path -LiteralPath $windowPath)) { throw 'Recovery start record required' }
    $window = Get-Content -Raw -LiteralPath $windowPath | ConvertFrom-Json
    $nowUnix = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
    $remaining = [Math]::Floor($window.deadline_unix - $nowUnix)
    if ($remaining -le 0) { throw 'Global execution deadline reached' }
    $limit = [Math]::Min($LimitSeconds, $remaining)
    $stdout = Join-Path $TrialRunRoot ($Label + '.stdout.log')
    $stderr = Join-Path $TrialRunRoot ($Label + '.stderr.log')
    $meta = Join-Path $TrialRunRoot ($Label + '.process.json')
    if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $meta)) { throw 'Step replay refused' }
    $started = [DateTime]::UtcNow
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $TrialRunRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $null = $process.Handle
    $pidValue = $process.Id
    $observed = @(Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue OR ParentProcessId=$pidValue" | Select-Object Name,ProcessId,ParentProcessId,CommandLine,CreationDate)
    $completed = $process.WaitForExit([int]($limit * 1000))
    $forced = $false
    if (-not $completed) {
        $forced = $true
        $process.Kill($true)
        $null = $process.WaitForExit(10000)
    }
    $timer.Stop()
    $record = [ordered]@{
        executable = $Executable
        argv = $Arguments
        started_utc = $started.ToString('o')
        ended_utc = [DateTime]::UtcNow.ToString('o')
        wall_seconds = $timer.Elapsed.TotalSeconds
        launcher_pid = $pidValue
        launcher_exit_code = $process.ExitCode
        forced_tree_cleanup = $forced
        observed_processes = $observed
        stdout = $stdout
        stderr = $stderr
        scope = 'launcher start through exit including initial CIM snapshot; per-step outer bound'
    }
    [IO.File]::WriteAllText($meta, ($record | ConvertTo-Json -Depth 6) + "`n", [Text.UTF8Encoding]::new($false))
    $exitCode = $process.ExitCode
    $process.Dispose()
    if ($forced -or $exitCode -ne 0) { throw ('Authorized step failed ' + $Label + ' exit=' + $exitCode) }
    Write-Output ($Label + ' completed in ' + [Math]::Round($timer.Elapsed.TotalSeconds, 4) + 's')
}
