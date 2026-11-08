$ErrorActionPreference='Stop'
$schemaFile=Join-Path $PSScriptRoot 'public_schema.json'
$cases=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'public_cases.json') -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
$rows=@()
foreach ($case in $cases) {
    $text=ConvertTo-Json -InputObject $case.arguments -Depth 40 -Compress
    $actual=Test-Json -Json $text -SchemaFile $schemaFile -ErrorAction SilentlyContinue
    $rows += @{name=$case.name;expected=$case.expected;actual=[bool]$actual;passed=([bool]$actual -eq $case.expected)}
}
$passed=@($rows | Where-Object {-not $_.passed}).Count -eq 0
@{passed=$passed;checks=$rows.Count;rows=$rows;validator='Installed PowerShell Test-Json';schema_sha256=(Get-FileHash -LiteralPath $schemaFile).Hash.ToLowerInvariant()} |
    ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'schema_results.json') -Encoding utf8
@{passed=$passed;checks=$rows.Count} | ConvertTo-Json -Compress
if (-not $passed) {exit 1}
