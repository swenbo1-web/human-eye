param([ValidateSet('S','G')][string]$Case,[ValidateSet('P','N')][string]$Condition,[int]$FutureChains)
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$window=Get-Content -Raw -LiteralPath (Join-Path $root 'WINDOW.json') | ConvertFrom-Json
$now=[DateTimeOffset]::UtcNow
$remaining=([DateTimeOffset]$window.deadline_utc-$now).TotalSeconds
$required=600*(1+$FutureChains)+300
if($remaining -lt $required -or $now -ge [DateTimeOffset]$window.stop_new_experiments_utc){throw 'Full current/future chain budgets plus seal reserve unavailable'}
$python=(Resolve-Path -LiteralPath (Join-Path $root '../../../task_contract_001/engineering_r1/venv/Scripts/python.exe')).Path
$started=$now.ToUnixTimeMilliseconds()/1000
$arguments=@('-I','-B',(Join-Path $root 'qa/chain_owner.py'),'--root',$root,'--reuse-root',$root,'--case',$Case,'--condition',$Condition,'--deadline-unix',$window.deadline_unix.ToString([Globalization.CultureInfo]::InvariantCulture),'--started-unix',$started.ToString([Globalization.CultureInfo]::InvariantCulture))
$stem=Join-Path $root ('owner_'+$Case+'_'+$Condition)
if(Test-Path -LiteralPath ($stem+'.LAUNCH.json')){throw 'Owner launch replay refused'}
$process=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput ($stem+'.stdout.log') -RedirectStandardError ($stem+'.stderr.log') -PassThru
$record=[ordered]@{started_utc=$now.ToString('o');started_unix=$started;remaining_before_chain_seconds=$remaining;minimum_required_seconds=$required;reserved_future_chains=$FutureChains;chain_seconds=600;pid=$process.Id;executable=$python;argv=$arguments}
$record|ConvertTo-Json -Depth 5|Set-Content -LiteralPath ($stem+'.LAUNCH.json') -Encoding utf8
$ready=Join-Path $root ('chains/'+$Case+'_'+$Condition+'/READY.json')
$waitUntil=[DateTimeOffset]::UtcNow.AddSeconds(25)
while(-not(Test-Path -LiteralPath $ready)){
 if($process.HasExited -or [DateTimeOffset]::UtcNow -ge $waitUntil){throw 'Owner readiness failed; inspect actual state before any further action'}
 Start-Sleep -Milliseconds 100
}
$process.Dispose()
$record|ConvertTo-Json -Depth 5
