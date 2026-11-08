$ErrorActionPreference = 'Stop'
$proofRoot = $PSScriptRoot
$offlineRoot = Join-Path $proofRoot 'offline_04'
$resultPath = Join-Path $proofRoot 'JSONSCHEMA_RESULTS.json'
if (Test-Path -LiteralPath $resultPath) { throw 'Fresh JSONSchema verification only' }
$jsonExample = Get-Content -LiteralPath (Join-Path $offlineRoot 'generic_example.json') -Raw -Encoding utf8
$pairCase = $jsonExample | ConvertFrom-Json -AsHashtable
$nearestCase = @{ session_id='read-1'; include_image=$false; query=@{ mode='surface_nearest'; objects=@(@{ name='A' }) } }
$dualSelector = $jsonExample | ConvertFrom-Json -AsHashtable
$dualSelector.query.objects[0].id = 'A-id'
$twoNearest = @{ session_id='read-1'; include_image=$false; query=@{ mode='surface_nearest'; objects=@(@{ name='A' },@{ name='B' }) } }
$unsupportedFact = $jsonExample | ConvertFrom-Json -AsHashtable
$unsupportedFact.query.requested_facts = @('not_a_fact')
$selectorAndFocal = @{ session_id='read-1'; include_image=$false; focal_id='A-id'; query=@{ mode='surface_nearest'; objects=@(@{ name='A' }) } }
$schemaCases = @(
    @{ name='generic_pair_example'; value=$pairCase; expected=$true },
    @{ name='one_object_global_surface_nearest'; value=$nearestCase; expected=$true },
    @{ name='selector_name_and_id_rejected'; value=$dualSelector; expected=$false },
    @{ name='surface_nearest_two_objects_rejected'; value=$twoNearest; expected=$false },
    @{ name='unsupported_fact_rejected'; value=$unsupportedFact; expected=$false },
    @{ name='surface_nearest_selector_and_focal_rejected'; value=$selectorAndFocal; expected=$false }
)
$schemaRows = @()
foreach ($armName in @('baseline','candidate')) {
    $schemaPath = Join-Path $offlineRoot ($armName + '_observe.inputSchema.json')
    foreach ($schemaCase in $schemaCases) {
        $caseText = ConvertTo-Json -InputObject $schemaCase.value -Depth 30 -Compress
        $validationErrors = @()
        $actual = Test-Json -Json $caseText -SchemaFile $schemaPath -ErrorAction SilentlyContinue -ErrorVariable validationErrors
        $schemaRows += @{
            arm=$armName; case=$schemaCase.name; expected=$schemaCase.expected; actual=[bool]$actual
            passed=([bool]$actual -eq $schemaCase.expected); request_json=$caseText
            schema_sha256=(Get-FileHash -LiteralPath $schemaPath -Algorithm SHA256).Hash.ToLowerInvariant()
            validation_messages=@($validationErrors | ForEach-Object { $_.ToString() })
        }
    }
}
$schemaCommand = Get-Command Test-Json
$validatorAssembly = $schemaCommand.ImplementingType.Assembly
$loadedSchemaAssemblies = @([AppDomain]::CurrentDomain.GetAssemblies() | Where-Object { $_.GetName().Name -match 'JsonSchema|JsonPointer|Json.More' } | ForEach-Object {
    @{ name=$_.FullName; path=$_.Location; sha256=(Get-FileHash -LiteralPath $_.Location -Algorithm SHA256).Hash.ToLowerInvariant() }
})
$allPassed = @($schemaRows | Where-Object { -not $_.passed }).Count -eq 0
$schemaResult = @{
    passed=$allPassed; cases=$schemaRows; checks=$schemaRows.Count
    validator=@{ command=$schemaCommand.Name; source=$schemaCommand.Source; version=$schemaCommand.Version.ToString()
        powershell=$PSVersionTable.PSVersion.ToString(); assembly=$validatorAssembly.FullName; path=$validatorAssembly.Location
        sha256=(Get-FileHash -LiteralPath $validatorAssembly.Location -Algorithm SHA256).Hash.ToLowerInvariant()
        schema_assemblies=$loadedSchemaAssemblies }
    source='Installed PowerShell Test-Json against archived actual product-generated schemas; no replacement validator'
    Blender_sessions=0; field_RPC=0; models=0; performance_samples=0
}
ConvertTo-Json -InputObject $schemaResult -Depth 40 | Set-Content -LiteralPath $resultPath -Encoding utf8
ConvertTo-Json -InputObject @{ passed=$allPassed; checks=$schemaRows.Count; result=$resultPath } -Compress
if (-not $allPassed) { exit 1 }
