param(
  [string]$StartFrom = "LG디스플레이",
  [string]$Model = "qwen3.5:9b",
  [string]$ExtractedBy = "q3.5:9b",
  [int]$Wave = 10,
  [int]$BatchSize = 20,
  [string[]]$CorpCodes = @(
    "00105873", # LG디스플레이
    "00138020", # SK실트론
    "00139889", # SKC
    "00105961", # LG이노텍
    "00447609", # 비에이치
    "00152686", # 코리아써키트
    "00301246", # SFA반도체
    "00158219", # 시그네틱스
    "00227333", # 네패스
    "00445054"  # 하나마이크론
  ),
  [switch]$SkipFetch,
  [switch]$SkipChunk,
  [switch]$SkipMariaLoad,
  [switch]$SkipVectorLoad
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"

$LogDir = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$TranscriptPath = Join-Path $LogDir "dart_to_local_extract_$Stamp.log"

function Run-Step {
  param(
    [string]$Name,
    [scriptblock]$Command
  )
  Write-Host ""
  Write-Host ">>> $Name" -ForegroundColor Cyan
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "FAILED: $Name (exit=$LASTEXITCODE)"
  }
}

function Summarize-Review {
  param([string]$CorpCode)
  $Pattern = "review_${CorpCode}_*.jsonl"
  $Files = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot "graph\_auto") -Filter $Pattern -ErrorAction SilentlyContinue
  if (-not $Files) {
    Write-Host "  review 없음: $Pattern" -ForegroundColor Yellow
    return
  }

  $Chunks = 0
  $Edges = 0
  $Rejected = 0
  foreach ($File in $Files) {
    Get-Content -LiteralPath $File.FullName -Encoding UTF8 | ForEach-Object {
      if (-not $_.Trim()) { return }
      $Obj = $_ | ConvertFrom-Json
      $Chunks += 1
      $Edges += @($Obj.clean_edges).Count
      $Rejected += @($Obj.rejected).Count
    }
  }
  Write-Host ("  summary corp={0}: chunks={1}, clean_edges={2}, rejected={3}" -f $CorpCode, $Chunks, $Edges, $Rejected)
}

Start-Transcript -Path $TranscriptPath | Out-Null
try {
  Write-Host "POLARIS DART -> local graph extraction"
  Write-Host "db dir       : $PSScriptRoot"
  Write-Host "model        : $Model"
  Write-Host "extracted_by : $ExtractedBy"
  Write-Host "start-from   : $StartFrom"
  Write-Host "wave/batch   : $Wave / $BatchSize"
  Write-Host "corp count   : $($CorpCodes.Count)"
  Write-Host "log          : $TranscriptPath"
  Write-Host ""
  Write-Host "NOTE: This script DOES NOT run graph/auto_runner.py load."
  Write-Host "NOTE: This script DOES NOT run graph/load_structured_extra28.py."
  Write-Host "NOTE: MariaDB/Qdrant load is used to prepare retrieval/extraction batches."

  if (-not $SkipFetch) {
    Run-Step "DART fetch selected corps" {
      $FetchArgs = @("extra28/fetch_extra28.py")
      if ($CorpCodes.Count -gt 0) {
        foreach ($CorpCode in $CorpCodes) {
          $FetchArgs += "--corp-code"
          $FetchArgs += $CorpCode
        }
      }
      elseif ($StartFrom) {
        $FetchArgs += "--start-from"
        $FetchArgs += $StartFrom
      }
      uv run python @FetchArgs
    }
  }

  if (-not $SkipChunk) {
    Run-Step "Chunk fetched periodic reports" {
      uv run python extra28/chunk_extra28.py
    }
  }

  if (-not $SkipMariaLoad) {
    Run-Step "Load raw/document/chunk indexes into MariaDB" {
      uv run python load/load_extra28_maria.py
    }
  }

  if (-not $SkipVectorLoad) {
    Run-Step "Embed pending chunks into Qdrant" {
      uv run python load/embed_qdrant.py
    }
  }

  foreach ($CorpCode in $CorpCodes) {
    Run-Step "Prepare positive-filter batches for $CorpCode" {
      uv run python graph/auto_runner.py prep-positive $CorpCode $Wave $BatchSize
    }

    $BatchPattern = "batch_${CorpCode}_*.json"
    $BatchFiles = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot "graph\_auto") -Filter $BatchPattern -ErrorAction SilentlyContinue
    if (-not $BatchFiles) {
      Write-Host "  batch 없음, 추출 스킵: $CorpCode" -ForegroundColor Yellow
      continue
    }

    Run-Step "Ollama extract $CorpCode" {
      uv run python graph/ollama_extract.py $CorpCode --model $Model
    }

    Summarize-Review -CorpCode $CorpCode
  }

  Write-Host ""
  Write-Host "DONE. Graph load was not executed." -ForegroundColor Green
  Write-Host "Review files: db\graph\_auto\review_<corp>_*.jsonl"
  Write-Host "Result files: db\graph\_auto\result_<corp>_*.json"
  foreach ($CorpCode in $CorpCodes) {
    Write-Host "  review: db\graph\_auto\review_${CorpCode}_*.jsonl"
    Write-Host "  result: db\graph\_auto\result_${CorpCode}_*.json"
  }
  Write-Host ""
  Write-Host "After manual review, load one corp like this:"
  Write-Host "  uv run python graph/auto_runner.py load 00105873 $ExtractedBy --keep-files"
}
finally {
  Stop-Transcript | Out-Null
}

