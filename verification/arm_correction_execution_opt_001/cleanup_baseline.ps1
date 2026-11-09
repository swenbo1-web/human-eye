$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$taskExpected = [System.IO.Path]::GetFullPath((Join-Path $taskRoot '.arm_correction_opt_baseline'))
$taskTarget = (Resolve-Path -LiteralPath $taskExpected).ProviderPath
if ($taskTarget -ne $taskExpected -or -not $taskTarget.StartsWith($taskRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Baseline cleanup path escaped the fixed workspace target'
}
$taskNodes = @(Get-Item -LiteralPath $taskTarget -Force) + @(Get-ChildItem -LiteralPath $taskTarget -Force -Recurse)
if (@($taskNodes | Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint }).Count -ne 0) {
    throw 'Refuse recursive cleanup through a reparse point'
}
$taskManifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'BASELINE_MATERIALIZATION.json') -Raw | ConvertFrom-Json
$taskFiles = @($taskNodes | Where-Object { -not $_.PSIsContainer })
if ($taskFiles.Count -ne 138 -or @($taskManifest.files.PSObject.Properties).Count -ne 138) {
    throw 'Unexpected materialized baseline file count'
}
foreach ($taskFile in $taskFiles) {
    $taskRelative = [System.IO.Path]::GetRelativePath($taskTarget, $taskFile.FullName).Replace('\', '/')
    $taskMember = $taskManifest.files.PSObject.Properties[$taskRelative]
    if ($null -eq $taskMember -or (Get-FileHash -LiteralPath $taskFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskMember.Value) {
        throw "Unexpected baseline file bytes: $taskRelative"
    }
}
Remove-Item -LiteralPath $taskTarget -Recurse -Force
if (Test-Path -LiteralPath $taskTarget) { throw 'Baseline directory still exists after cleanup' }
Write-Output ('Removed verified temporary baseline: ' + $taskTarget)
