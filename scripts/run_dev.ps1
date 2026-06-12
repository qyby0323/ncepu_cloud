$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
Push-Location $projectDir
try {
    $env:PYTHONPATH = "$projectDir\src;$env:PYTHONPATH"
    python -m ncepu_cloud_client.main
}
finally {
    Pop-Location
}
