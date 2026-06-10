param(
  [string]$RepoName = "kondate-streamlit-app",
  [switch]$Public
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

gh auth status

$visibility = if ($Public) { "--public" } else { "--private" }
if (-not (Test-Path ".git")) {
  git init
  git add .
  git -c user.name="Codex" -c user.email="codex@example.local" commit -m "Initial Streamlit Cloud app"
}

gh repo create $RepoName $visibility --source . --remote origin --push
Write-Host "GitHub repo created and pushed."
