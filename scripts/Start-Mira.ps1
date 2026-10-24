# A local launcher. The key is prompted without echo and is never written to disk.
[CmdletBinding()]
param([switch]$Pilot, [switch]$Mock)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($Mock -and $Pilot) {
    throw '-Mock cannot be combined with -Pilot; the pilot evaluates a real model.'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv312\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Install the locked Python environment first; see docs/live_demo.md.'
}

if ($Mock) {
    Write-Host 'Mira offline mock: scripted replies; no API key or network required.'
    Write-Host 'Try: Hi, /workout start squats 12, /workout reps 10, How many left?, /quit'
    & $pythonPath -m hope_brain.cli --provider mock --chat 1>$null
    exit $LASTEXITCODE
}

# These are explicit pilot rates, checked against the official documentation.
# Recheck prices before running. The application itself has no default model/rates.
$settings = @{
    HOPE_ANTHROPIC_MODEL = 'claude-haiku-4-5-20251001'
    HOPE_INPUT_USD_PER_MILLION = '1'
    HOPE_OUTPUT_USD_PER_MILLION = '5'
    HOPE_TURN_BUDGET_USD = '0.01'
    HOPE_SESSION_BUDGET_USD = '0.05'
    HOPE_MAX_TOKENS = '256'
    HOPE_TIMEOUT_SECONDS = '30'
}
$saved = @{}
$settingNames = @('ANTHROPIC_API_KEY') + @($settings.Keys)
foreach ($name in $settingNames) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$secretPointer = [IntPtr]::Zero
$secureKey = $null
$resultCode = 1
try {
    if ([string]::IsNullOrWhiteSpace($env:ANTHROPIC_API_KEY)) {
        $secureKey = Read-Host 'Anthropic API key (hidden; this run only)' -AsSecureString
        $secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        $env:ANTHROPIC_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer)
    }
    foreach ($name in $settings.Keys) {
        [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
    }
    $cliArguments = @('-m', 'hope_brain.cli', '--provider', 'anthropic', '--chat')
    if ($Pilot) { $cliArguments += '--live-pilot' }
    Write-Host 'Mira demo: $0.01 per turn, $0.05 cumulative for this process.'
    Write-Host 'NDJSON events are discarded here; Mira and pilot results appear below.'
    & $pythonPath @cliArguments 1>$null
    $resultCode = $LASTEXITCODE
}
finally {
    if ($secretPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer)
    }
    if ($null -ne $secureKey) { $secureKey.Dispose() }
    foreach ($name in $settingNames) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
    }
}
exit $resultCode
