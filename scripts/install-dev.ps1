# Install Python packages in editable mode, then run API / tests.
# Usage (from repo root, venv activated):
#   .\scripts\install-dev.ps1
#   uvicorn powerforge_api.main:app --reload --app-dir services/api/src --port 8000

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e packages/shared `
  -e packages/project `
  -e packages/engineering-model `
  -e packages/document-model `
  -e packages/extraction `
  -e packages/topology `
  -e packages/validation `
  -e packages/provenance `
  -e packages/ai `
  -e services/api `
  -e services/document-worker `
  -e services/extraction-worker `
  -e services/validation-worker
