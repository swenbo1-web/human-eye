param([Parameter(Mandatory=$true)][string]$Pin)
$ErrorActionPreference='Stop'
$EngineeringRoot = Split-Path $PSScriptRoot -Parent
$repoRoot = (Resolve-Path (Join-Path $EngineeringRoot '../../../..')).Path
$basePython = 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe'
. (Join-Path $PSScriptRoot 'timed_step.ps1')
$unit = Get-Content -Raw -LiteralPath (Join-Path $EngineeringRoot 'UNIT_ACCEPTANCE.json') | ConvertFrom-Json
if (-not $unit.successful -or $unit.identity.source_sha256 -ne $Pin) { throw 'Frozen targeted candidate must pass before build' }
Invoke-EngineeringStep -Label build -Executable $basePython -Arguments @('-I','-B',(Join-Path $repoRoot 'verification/build_candidate_release.py'),'--output',(Join-Path $EngineeringRoot 'build'),'--version','9.7.2+surface.facts.b.1')
$build = Get-Content -Raw -LiteralPath (Join-Path $EngineeringRoot 'build/BUILD.json') | ConvertFrom-Json
if ($build.runtime_identity.source_sha256 -ne $Pin -or $build.runtime_identity.source_files.Count -ne 131) { throw 'Build identity differs from frozen suite' }
Invoke-EngineeringStep -Label venv_create -Executable $basePython -Arguments @('-I','-B','-m','venv',(Join-Path $EngineeringRoot 'venv'))
$candidatePython = Join-Path $EngineeringRoot 'venv/Scripts/python.exe'
Invoke-EngineeringStep -Label install -Executable $candidatePython -Arguments @('-I','-B','-m','pip','install','--no-index','--no-compile','--disable-pip-version-check','--find-links','D:/hefe/artifacts/local_release_dependency_cache',(Join-Path $EngineeringRoot 'build/human_eye_spatial_plugin-9.7.2+surface.facts.b.1-py3-none-any.whl'),'numpy==2.3.5','Pillow==12.3.0')
$aHelpers = Join-Path (Split-Path $EngineeringRoot -Parent) 'engineering_a/venv/Lib/site-packages/verification'
$bHelpers = Join-Path $EngineeringRoot 'venv/Lib/site-packages/verification'
$null=New-Item -ItemType Directory -Path $bHelpers
$copies=foreach($name in @('perf000_scene_tool','perf010_qualification','visual004_native','visual004_session','visual004_product')) {
    $source=Join-Path $aHelpers ($name+'.py')
    $target=Join-Path $bHelpers ($name+'.py')
    Copy-Item -LiteralPath $source -Destination $target
    $sourceHash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    $targetHash=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if($sourceHash -ne $targetHash){throw 'QA helper copy changed'}
    [ordered]@{module=$name;source=$source;target=$target;sha256=$targetHash;adaptation='same accepted A installed helper bytes for both comparison versions'}
}
[IO.File]::WriteAllText((Join-Path $EngineeringRoot 'QA_COPIES.json'),($copies|ConvertTo-Json -Depth 4)+"`n",[Text.UTF8Encoding]::new($false))
Invoke-EngineeringStep -Label installed_identity -Executable $candidatePython -Arguments @('-I','-B',(Join-Path $PSScriptRoot 'installed_identity.py'),'--pin',$Pin,'--source-count','131')
