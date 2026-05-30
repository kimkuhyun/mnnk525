# restore_dbs.ps1 — 덤프에서 3DB 복원
#
# 전제: docker compose up -d 로 3DB 컨테이너 실행 중
# 사용: .\scripts\restore_dbs.ps1
# 입력: dumps/{mariadb.sql, qdrant_polaris-1024-cos-{blue,green}.snapshot, neo4j.dump}

param(
    [string]$InDir = "dumps"
)

$ErrorActionPreference = "Stop"

Write-Host "=== 1/3 MariaDB import ===" -ForegroundColor Cyan
$mariaSql = Join-Path $InDir "mariadb.sql"
if (-not (Test-Path $mariaSql)) { throw "$mariaSql 없음" }
Get-Content $mariaSql -Raw | docker exec -i polaris-mariadb mariadb -upolaris -ppolaris_dev_only polaris
Write-Host "  MariaDB OK"

Write-Host "`n=== 2/3 Qdrant snapshot upload ===" -ForegroundColor Cyan
foreach ($col in @("polaris-1024-cos-blue", "polaris-1024-cos-green")) {
    $local = Join-Path $InDir "qdrant_$col.snapshot"
    if (-not (Test-Path $local)) {
        Write-Host "  $local 없음 - skip" -ForegroundColor Yellow
        continue
    }
    # 컨테이너 안으로 복사 후 recover API 호출
    $remoteName = (Split-Path $local -Leaf)
    docker cp $local "polaris-qdrant:/qdrant/snapshots_in/$remoteName" 2>$null
    docker exec polaris-qdrant mkdir -p /qdrant/snapshots_in 2>$null
    docker cp $local "polaris-qdrant:/qdrant/snapshots_in/$remoteName"
    Invoke-RestMethod -Method Put -Uri "http://localhost:6333/collections/$col/snapshots/recover" `
        -ContentType "application/json" `
        -Body (@{ location = "file:///qdrant/snapshots_in/$remoteName" } | ConvertTo-Json)
    Write-Host "  $col recovered"
}

Write-Host "`n=== 3/3 Neo4j load ===" -ForegroundColor Cyan
$neoDump = Join-Path $InDir "neo4j.dump"
if (-not (Test-Path $neoDump)) { throw "$neoDump 없음" }
docker cp $neoDump polaris-neo4j:/tmp/neo4j.dump
# Neo4j 5.x: load 는 DB stop 상태 필요. 기존 DB drop 후 load.
docker exec polaris-neo4j sh -c "neo4j-admin database stop neo4j 2>/dev/null; neo4j-admin database load neo4j --from-path=/tmp --overwrite-destination=true; neo4j-admin database start neo4j"
Write-Host "  Neo4j OK"

Write-Host "`n=== 완료. verify 실행 권장 ===" -ForegroundColor Green
Write-Host "  polaris verify"
