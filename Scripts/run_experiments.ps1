param(
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.7',
    [string]$PythonExe = 'python',
    [string]$OutputDirectory = '',
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$Project = Join-Path $ProjectRoot 'PlayableSketch.uproject'
$RunId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$WorkDirectory = Join-Path $ProjectRoot "Saved\Experiments\runs\$RunId"
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $ProjectRoot "Experiments\runs\$RunId" }
if (Test-Path -LiteralPath $OutputDirectory) { throw "Output already exists: $OutputDirectory. Choose an unused directory." }
New-Item -ItemType Directory -Force -Path $WorkDirectory | Out-Null
$Metadata = Join-Path $WorkDirectory 'provenance.json'
$Analyzer = Join-Path $PSScriptRoot 'analyze_experiments.py'
& $PythonExe $Analyzer --prepare $Metadata
if ($LASTEXITCODE -ne 0) { throw 'Manifest/source preflight failed.' }
if (-not $SkipBuild) {
    & (Join-Path $EngineRoot 'Engine\Build\BatchFiles\Build.bat') PlayableSketchEditor Win64 Development "-Project=$Project" -WaitMutex -NoHotReloadFromIDE -NoUBA "-Log=$WorkDirectory\build.log"
    if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
}
$PreviousLocalCache = [Environment]::GetEnvironmentVariable('UE-LocalDataCachePath', 'Process')
$PreviousSharedCache = [Environment]::GetEnvironmentVariable('UE-SharedDataCachePath', 'Process')
$Raw = Join-Path $ProjectRoot 'Saved\Experiments\raw_results.json'
$PreviousHash = if (Test-Path -LiteralPath $Raw) { (Get-FileHash -LiteralPath $Raw).Hash } else { '' }
try {
    [Environment]::SetEnvironmentVariable('UE-LocalDataCachePath', (Join-Path $WorkDirectory 'ddc'), 'Process')
    [Environment]::SetEnvironmentVariable('UE-SharedDataCachePath', 'None', 'Process')
    & (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe') $Project /Engine/Maps/Entry -Unattended -NullRHI -NoSplash -NoSound -NoLiveCoding -ddc=InstalledNoZenLocalFallback -stdout -FullStdOutLogOutput '-ExecCmds=Automation RunTests PlayableSketch.' '-TestExit=Automation Test Queue Empty' "-ReportExportPath=$WorkDirectory\test-report" "-abslog=$WorkDirectory\tests.log"
    $EditorExit = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('UE-LocalDataCachePath', $PreviousLocalCache, 'Process')
    [Environment]::SetEnvironmentVariable('UE-SharedDataCachePath', $PreviousSharedCache, 'Process')
}
if (-not (Test-Path -LiteralPath $Raw)) { throw "Runner did not produce raw results. Logs: $WorkDirectory" }
if ($PreviousHash -and (Get-FileHash -LiteralPath $Raw).Hash -eq $PreviousHash) { throw "Raw results were not refreshed. Logs: $WorkDirectory" }
$Report = Join-Path $WorkDirectory 'test-report\index.json'
& $PythonExe $Analyzer --raw $Raw --metadata $Metadata --report $Report --output $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'Result validation/export failed.' }
$TestReport = Get-Content -Raw -LiteralPath $Report | ConvertFrom-Json
if ($EditorExit -ne 0 -or $TestReport.failed -ne 0 -or @($TestReport.tests | Where-Object { $_.state -ne 'Success' }).Count -ne 0) {
    throw "Automation failed; raw results retained in $OutputDirectory; logs: $WorkDirectory"
}
Write-Host "Results: $OutputDirectory"
Write-Host "Logs and automation report: $WorkDirectory"
