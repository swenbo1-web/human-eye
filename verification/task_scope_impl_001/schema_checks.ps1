$ErrorActionPreference = 'Stop'
$schemaFile = Join-Path $PSScriptRoot 'public_schema.json'
$query = @{ mode='task'; target=@{id='a'}; candidates=@(@{id='b'},@{id='c'},@{id='d'}); requested_facts=@('closed_solid_relation','surface_proximity','aabb') }
$cases = @()
function Add-SchemaCase($label,$value,$expected) {
    $script:cases += @{ name=$label; arguments=@{include_image=$false;query=$value}; expected=$expected }
}
function Copy-Query { return ($query | ConvertTo-Json -Depth 20 | ConvertFrom-Json -AsHashtable) }
Add-SchemaCase 'three_candidates' (Copy-Query) $true
$value=Copy-Query; $value.candidates=@(@{id='b'}); Add-SchemaCase 'one_candidate' $value $true
$value=Copy-Query; $value.requested_facts=@('closed_solid_relation','surface_proximity'); Add-SchemaCase 'without_aabb' $value $true
Add-SchemaCase 'old_pair' @{mode='task';objects=@(@{id='a'},@{id='b'});requested_facts=@('pair_relation')} $true
Add-SchemaCase 'old_aabb_four' @{mode='task';objects=@(@{id='a'},@{id='b'},@{id='c'},@{id='d'});requested_facts=@('aabb')} $true
$value=Copy-Query; $value.candidates=@(); Add-SchemaCase 'empty_candidates' $value $false
$value=Copy-Query; $value.candidates=@(@{id='b'},@{id='c'},@{id='d'},@{id='e'}); Add-SchemaCase 'four_candidates' $value $false
$value=Copy-Query; $value.objects=@(@{id='a'},@{id='b'}); Add-SchemaCase 'mixed_public_shapes' $value $false
$value=Copy-Query; $value.target.name='a'; Add-SchemaCase 'dual_selector' $value $false
$value=Copy-Query; $value.requested_facts=@('surface_proximity'); Add-SchemaCase 'missing_required_fact' $value $false
$value=Copy-Query; $value.requested_facts=@('closed_solid_relation','surface_proximity','axis_gap'); Add-SchemaCase 'unsupported_set_fact' $value $false
$value=Copy-Query; $value.object_ids=@('b'); Add-SchemaCase 'set_extra_legacy_field' $value $false
$rows=@()
foreach ($case in $cases) {
    $text=ConvertTo-Json -InputObject $case.arguments -Compress -Depth 30
    $actual=Test-Json -Json $text -SchemaFile $schemaFile -ErrorAction SilentlyContinue
    $rows += @{name=$case.name;expected=$case.expected;actual=[bool]$actual;passed=([bool]$actual -eq $case.expected);request=$text}
}
$passed=@($rows | Where-Object { -not $_.passed }).Count -eq 0
@{passed=$passed;checks=$rows.Count;rows=$rows;validator='Installed PowerShell Test-Json';schema_sha256=(Get-FileHash -LiteralPath $schemaFile).Hash.ToLowerInvariant()} |
    ConvertTo-Json -Depth 40 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'schema_results.json') -Encoding utf8
@{passed=$passed;checks=$rows.Count} | ConvertTo-Json -Compress
if (-not $passed) {exit 1}
