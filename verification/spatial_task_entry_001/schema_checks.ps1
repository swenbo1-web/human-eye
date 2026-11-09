$ErrorActionPreference='Stop'
$cases=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'schema_cases.json') -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
$rows=@()
foreach ($case in $cases) {
    $schemaFile=Join-Path $PSScriptRoot ($case.schema + '_schema.json')
    $text=ConvertTo-Json -InputObject $case.arguments -Depth 40 -Compress
    $actual=Test-Json -Json $text -SchemaFile $schemaFile -ErrorAction SilentlyContinue
    $rows += @{name=$case.name;schema=$case.schema;expected=$case.expected;actual=[bool]$actual;passed=([bool]$actual -eq $case.expected)}
}
$passed=@($rows | Where-Object {-not $_.passed}).Count -eq 0
@{passed=$passed;checks=$rows.Count;rows=$rows;validator='Installed PowerShell Test-Json';
  dedicated_schema_sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'dedicated_schema.json')).Hash.ToLowerInvariant();
  legacy_schema_sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'legacy_schema.json')).Hash.ToLowerInvariant()} |
    ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'schema_results.json') -Encoding utf8
@{passed=$passed;checks=$rows.Count} | ConvertTo-Json -Compress
if (-not $passed) {exit 1}
