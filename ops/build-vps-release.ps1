[CmdletBinding()]
param(
    [string]$OutputDirectory = "dist"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$outputRoot = Join-Path $projectRoot $OutputDirectory
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archive = Join-Path $outputRoot "partner-reports-synthetic-runtime-$timestamp.tar.gz"

$required = @(
    "Dockerfile",
    "pyproject.toml",
    "README.md",
    "alembic.ini",
    "compose.production.yml",
    "compose.staging.yml",
    "src",
    "migrations",
    "deploy/Caddyfile",
    "deploy/Caddyfile.staging",
    "deploy/production.env.example",
    "deploy/restic.env.example",
    "deploy/systemd",
    "ops"
)

foreach ($item in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $item))) {
        throw "Arquivo obrigatório ausente: $item"
    }
}

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
Push-Location $projectRoot
try {
    & tar --exclude "__pycache__" --exclude "*.pyc" -czf $archive @required
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao criar o pacote de implantação"
    }
}
finally {
    Pop-Location
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
Write-Output "release_archive=$archive"
Write-Output "release_sha256=$hash"
Write-Output "release_scope=synthetic_only"
