# dump_dbs.ps1 — POLARIS 3DB 덤프 (MariaDB / Qdrant / Neo4j)
#
# 사용: .\scripts\dump_dbs.ps1
# 출력: dumps/{mariadb.sql, qdrant_snapshot.tar, neo4j.dump}

param(
    [string]$OutDir = "dumps"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "=== 1/3 MariaDB mysqldump ===" -ForegroundColor Cyan
$mariaSql = Join-Path $OutDir "mariadb.sql"
docker exec polaris-mariadb mariadb-dump `
    -upolaris -ppolaris_dev_only `
    --single-transaction --routines --triggers `
    polaris > $mariaSql
$size = (Get-Item $mariaSql).Length / 1MB
Write-Host ("  saved {0,8:N1} MB → {1}" -f $size, $mariaSql)

Write-Host "`n=== 2/3 Qdrant snapshot ===" -ForegroundColor Cyan
# Qdrant snapshot API (active + standby 둘 다)
foreach ($col in @("polaris-1024-cos-blue", "polaris-1024-cos-green")) {
    $resp = Invoke-RestMethod -Method Post -Uri "http://localhost:6333/collections/$col/snapshots"
    $snapName = $resp.result.name
    Write-Host "  $col → snapshot $snapName"
    # 컨테이너에서 호스트로 복사
    $local = Join-Path $OutDir "qdrant_$col.snapshot"
    docker cp "polaris-qdrant:/qdrant/snapshots/$col/$snapName" $local
    $size = (Get-Item $local).Length / 1MB
    Write-Host ("    saved {0,8:N1} MB → {1}" -f $size, $local)
}

Write-Host "`n=== 3/3 Neo4j dump (offline, stop/dump/start) ===" -ForegroundColor Cyan
# Neo4j 5.x community: dump 는 DB stop 필요. 컨테이너 일시 정지 후 별도 컨테이너로 dump.
$mounts = docker inspect polaris-neo4j --format '{{json .Mounts}}' | ConvertFrom-Json
$neoVol = ($mounts | Where-Object { $_.Destination -eq "/data" }).Name
Write-Host "  volume = $neoVol"
docker stop polaris-neo4j | Out-Null
$absDump = (Resolve-Path $OutDir).Path
docker run --rm -v "${neoVol}:/data" -v "${absDump}:/backup" neo4j:5.24-community `
    neo4j-admin database dump neo4j --to-path=/backup --overwrite-destination=true
docker start polaris-neo4j | Out-Null
$neoFile = Join-Path $OutDir "neo4j.dump"
if (Test-Path $neoFile) {
    $size = (Get-Item $neoFile).Length / 1MB
    Write-Host ("  saved {0,8:N1} MB → {1}" -f $size, $neoFile)
} else {
    Write-Host "  neo4j.dump 생성 실패" -ForegroundColor Red
}

Write-Host "`n=== 완료 ===" -ForegroundColor Green
Get-ChildItem $OutDir | Select-Object Name, @{N='MB';E={[math]::Round($_.Length/1MB,1)}} | Format-Table -AutoSize
