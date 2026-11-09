# Phoenix — one-command repo push + SHA pin.
#
#   .\setup.ps1 -Handle YOUR-GITHUB-HANDLE
#
# Requires git. If the GitHub CLI (`gh`) is installed and authenticated it will
# also create the repo; otherwise it prints the two manual commands.

param(
    [Parameter(Mandatory = $true)]
    [string]$Handle
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "== init + first commit =="
git init -b main
git add -A
git commit -m "Phoenix v0.2.0: crash-proof ledger, idempotency guard & deterministic wind tunnel"

Write-Host "== fill handle in catalog entry =="
$catalog = Join-Path $root "submit\phoenix.yaml"
(Get-Content $catalog -Raw) -replace "YOUR-HANDLE", $Handle | Set-Content $catalog -NoNewline -Encoding utf8

if (Get-Command gh -ErrorAction SilentlyContinue) {
    Write-Host "== creating repo via gh =="
    gh repo create "$Handle/phoenix" --public --source . --push
} else {
    Write-Host "== creating remote (manual if gh missing) =="
    git remote add origin "https://github.com/$Handle/phoenix.git"
    git push -u origin main
}

Write-Host "== pin catalog SHA =="
$sha = (git rev-parse HEAD).Trim()
(Get-Content $catalog -Raw) -replace "0000000000000000000000000000000000000000", $sha | Set-Content $catalog -NoNewline -Encoding utf8
git add -A
git commit -m "pin catalog SHA ($sha.Substring(0,7))"
git push

Write-Host ""
Write-Host "DONE. Repo: https://github.com/$Handle/phoenix"
Write-Host "Pinned SHA: $sha"
Write-Host "Next: open the catalog PR (see submit\HANDOFF.md), then shoot the video."
