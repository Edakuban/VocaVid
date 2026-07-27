$ErrorActionPreference = "Stop"

$desktopRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $desktopRoot "..")).Path
$buildRoot = Join-Path $desktopRoot ".build"
$staging = Join-Path $buildRoot "payload"
$resources = Join-Path $desktopRoot "resources"
$payload = Join-Path $resources "vocavid-app.zip"

if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}
New-Item -ItemType Directory -Path $staging -Force | Out-Null
New-Item -ItemType Directory -Path $resources -Force | Out-Null

$directories = @("VocaVid", "workflows", "prompts", "templates", "icon")
foreach ($directory in $directories) {
    Copy-Item -LiteralPath (Join-Path $repoRoot $directory) -Destination $staging -Recurse
}
Copy-Item -LiteralPath (Join-Path $repoRoot "requirements.txt") -Destination $staging
Copy-Item -LiteralPath (Join-Path $desktopRoot "stack.lock.json") -Destination (Join-Path $resources "stack.lock.json")

if (Test-Path -LiteralPath $payload) {
    Remove-Item -LiteralPath $payload -Force
}
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $payload -CompressionLevel Optimal
Write-Output "Prepared $payload"
