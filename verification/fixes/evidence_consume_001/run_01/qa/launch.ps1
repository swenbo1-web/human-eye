param(
 [Parameter(Mandatory=$true)][ValidateSet('S','G')][string]$Case,
 [Parameter(Mandatory=$true)][ValidateSet('P','N')][string]$Condition,
 [Parameter(Mandatory=$true)][ValidateSet('W1','W2')][string]$Wording
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$window=Get-Content -Raw -LiteralPath (Join-Path $root 'WINDOW.json') | ConvertFrom-Json
$deadlineUnix=1794042043
if($window.deadline_unix -and [double]$window.deadline_unix -ne $deadlineUnix){throw 'Implementation deadline must remain the assigned fixed epoch'}
$deadline=[DateTimeOffset]::FromUnixTimeSeconds($deadlineUnix)
$now=[DateTimeOffset]::UtcNow
$remaining=($deadline-$now).TotalSeconds
$required=600+300
if($remaining -lt $required){throw 'Full 600-second chain budget plus 300-second report/reap reserve unavailable'}
$python=(Resolve-Path -LiteralPath (Join-Path $root '../../surface_facts_001/engineering_b/venv/Scripts/python.exe')).Path
$started=$now.ToUnixTimeMilliseconds()/1000
$arguments=@('-I','-B',(Join-Path $root 'qa/chain_owner.py'),'--root',$root,'--reuse-root',$root,'--case',$Case,'--condition',$Condition,'--wording',$Wording,'--deadline-unix',$deadlineUnix.ToString([Globalization.CultureInfo]::InvariantCulture),'--started-unix',$started.ToString([Globalization.CultureInfo]::InvariantCulture))
$chainId=$Case+'_'+$Condition+'_'+$Wording
$stem=Join-Path $root ('owner_'+$chainId)
if(Test-Path -LiteralPath ($stem+'.LAUNCH.json')){throw 'Owner launch replay refused'}
$process=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput ($stem+'.stdout.log') -RedirectStandardError ($stem+'.stderr.log') -PassThru
$record=[ordered]@{started_utc=$now.ToString('o');started_unix=$started;implementation_deadline_unix=$deadlineUnix;remaining_before_chain_seconds=$remaining;minimum_required_seconds=$required;chain_seconds=600;pid=$process.Id;executable=$python;argv=$arguments;chain_id=$chainId}
[IO.File]::WriteAllText(($stem+'.LAUNCH.json'),($record|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
$ready=Join-Path $root ('chains/'+$chainId+'/READY.json')
$waitUntil=[DateTimeOffset]::UtcNow.AddSeconds(25)
while(-not(Test-Path -LiteralPath $ready)){
 if($process.HasExited -or [DateTimeOffset]::UtcNow -ge $waitUntil){throw 'Owner readiness failed; inspect actual state before any further action'}
 Start-Sleep -Milliseconds 100
}
$process.Dispose()
$record|ConvertTo-Json -Depth 5
