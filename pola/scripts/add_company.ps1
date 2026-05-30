# add_company.ps1 — POLARIS 신규 회사 추가 자동화
#
# 사용:
#   .\scripts\add_company.ps1 -CorpCode 00160843
#   .\scripts\add_company.ps1 -CorpCode 00160843,00369657 -FromYear 2024
#   .\scripts\add_company.ps1 -CorpCode 00164742 -PatchEnv     # .env 자동 추가
#
# 단계:
#   0. corp_code 사전 검증 (DART corps.json 에 존재하는지)
#   1. (옵션) .env POLARIS_CORPS 자동 추가
#   2. raw 수집 (DART + KRX + documents)
#   3. build (Organization MERGE + 청크/임베딩/적재)
#   4. graph-extract (Person/Affiliated/Invests/Events 자동 채움)
#   5. promote-run
#   6. verify + graph-diag

param(
    [Parameter(Mandatory=$true)]
    [string]$CorpCode,                    # 콤마로 여러 개
    [int]$FromYear = 2024,
    [string]$Profile = "slow",            # slow / normal / fast
    [switch]$PatchEnv,                    # .env POLARIS_CORPS 자동 추가
    [switch]$SkipIngest                   # raw 이미 있을 때
)

$ErrorActionPreference = "Stop"
Write-Host "=== POLARIS 신규 회사 추가 ===" -ForegroundColor Cyan
Write-Host "대상: $CorpCode (from $FromYear, profile $Profile)"
$envFile = Join-Path $PSScriptRoot "..\.env"
if (-not (Test-Path $envFile)) {
    Write-Host "[ERROR] .env 없음: $envFile" -ForegroundColor Red
    exit 1
}

# 0) corp_code 사전 검증 (corps.json lookup)
Write-Host "`n[0/6] corp_code 사전 검증"
$ccList = @($CorpCode.Split(",") | ForEach-Object { $_.Trim() })
$lookupScript = @"
import json, sys
from polaris.config import _load_corp_db
db = _load_corp_db()
ccs = sys.argv[1:]
for cc in ccs:
    cc8 = cc.zfill(8)
    m = db.get(cc8)
    if m:
        print(f'  OK  {cc8} = {m.get("corp_name","?")} ({m.get("stock_code","-")})')
    else:
        print(f'  ERR {cc8} = (corps.json에 없음 — polaris ingest corp-code-refresh 권장)')
        sys.exit(2)
"@
python -c $lookupScript @ccList
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[ERROR] 일부 corp_code 가 DART 마스터에 없습니다. 진행 중단." -ForegroundColor Red
    exit 2
}

# 1) .env patch (옵션)
$envContent = Get-Content $envFile -Raw
$missing = @($ccList | Where-Object { $envContent -notmatch [regex]::Escape($_) })
if ($missing.Count -gt 0) {
    if ($PatchEnv) {
        Write-Host "`n[1/6] .env POLARIS_CORPS 에 자동 추가: $($missing -join ', ')"
        $newCsv = (($ccList) -join ",")
        if ($envContent -match "(?m)^POLARIS_CORPS=(.+)$") {
            $current = $matches[1].Trim()
            $merged = (@($current.Split(",")) + $missing | Where-Object { $_ } | Select-Object -Unique) -join ","
            $newContent = $envContent -replace "(?m)^POLARIS_CORPS=.+$", "POLARIS_CORPS=$merged"
            Set-Content -Path $envFile -Value $newContent -Encoding utf8 -NoNewline
            Write-Host "  OK  POLARIS_CORPS = $merged"
        } else {
            Add-Content -Path $envFile -Value "POLARIS_CORPS=$newCsv"
        }
    } else {
        Write-Host "`n[ERROR] .env POLARIS_CORPS 에 없음: $($missing -join ', ')" -ForegroundColor Red
        Write-Host "        -PatchEnv 옵션으로 자동 추가 가능, 또는 수동 .env 편집 후 재실행" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "`n[1/6] .env POLARIS_CORPS 이미 포함됨 (skip)"
}

# 2) raw 수집
if ($SkipIngest) {
    Write-Host "`n[2/6] -SkipIngest — raw 수집 skip"
} else {
    Write-Host "`n[2/6] polaris ingest --only dart,krx,documents --corp-codes $CorpCode --from-year $FromYear --profile $Profile"
    polaris ingest --only dart,krx,documents --corp-codes $CorpCode --from-year $FromYear --profile $Profile
    if ($LASTEXITCODE -ne 0) { Write-Host "ingest 실패" -ForegroundColor Red; exit 1 }
}

# 3) build (청크·임베딩·3DB 적재 + Organization 자동 MERGE)
Write-Host "`n[3/6] polaris build --skip-init"
polaris build --skip-init
if ($LASTEXITCODE -ne 0) { Write-Host "build 실패" -ForegroundColor Red; exit 1 }

# 4) graph-extract (Person/Affiliated/Invests/Events 채움)
Write-Host "`n[4/6] polaris graph-extract"
polaris graph-extract
if ($LASTEXITCODE -ne 0) { Write-Host "graph-extract 실패" -ForegroundColor Red; exit 1 }

# 5) promote-run
Write-Host "`n[5/6] polaris promote-run"
polaris promote-run
if ($LASTEXITCODE -ne 0) { Write-Host "promote-run 실패" -ForegroundColor Red; exit 1 }

# 6) verify + graph-diag
Write-Host "`n[6/6] polaris verify + graph-diag"
polaris verify
$verifyRc = $LASTEXITCODE
polaris graph-diag
$diagRc = $LASTEXITCODE

if ($verifyRc -ne 0 -or $diagRc -ne 0) {
    Write-Host "`n[WARN] verify=$verifyRc, graph-diag=$diagRc — 위 결과 확인 후 수동 fix 필요" -ForegroundColor Yellow
    exit 1
}
Write-Host "`n=== 완료. 회사 추가 + 검증 PASS ===" -ForegroundColor Green
