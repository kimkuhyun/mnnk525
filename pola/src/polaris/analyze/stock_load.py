"""주가 적재 — pola/data/rawData/{corp}/krx/daily_ohlcv_*.json → stock_daily.

시드 3사: 00126380 삼성전자 · 00164779 SK하이닉스 · 00161383 한미반도체.
JSON 구조: {"rows": [{"basDd":"YYYYMMDD","close":float,"volume":int,"change_pct":float,...}]}
멱등(ON DUPLICATE KEY UPDATE). change_pct 는 JSON 에 이미 있으면 그대로, 없으면 직전 종가 대비 계산.

실행:  uv run python -m polaris.analyze.stock_load
"""
from __future__ import annotations

import json
from datetime import date

from polaris.config import CORPS, DATA_ROOT, mariadb_conn

RAW_ROOT = DATA_ROOT / "rawData"


def ensure_tables(cur) -> None:
    cur.execute("""CREATE TABLE IF NOT EXISTS stock_daily (
        corp_code  VARCHAR(8)  NOT NULL,
        date       DATE        NOT NULL,
        close      DOUBLE      NOT NULL,
        change_pct DOUBLE,
        volume     BIGINT,
        PRIMARY KEY (corp_code, date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")


def load_corp(cur, corp_code: str) -> int:
    krx_dir = RAW_ROOT / corp_code / "krx"
    if not krx_dir.exists():
        print(f"  [{corp_code}] KRX 디렉터리 없음: {krx_dir}")
        return 0

    files = sorted(krx_dir.glob("daily_ohlcv_*.json"))
    if not files:
        print(f"  [{corp_code}] JSON 파일 없음")
        return 0

    # 전체 행 수집 후 date 오름차순 정렬
    all_rows: list[dict] = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        rows = data.get("rows", [])
        all_rows.extend(rows)

    # date 오름차순 정렬 (basDd: "YYYYMMDD")
    all_rows.sort(key=lambda r: r.get("basDd", ""))

    upserted = 0
    prev_close: float | None = None

    for row in all_rows:
        bas_dd = row.get("basDd", "")
        if len(bas_dd) != 8:
            continue
        try:
            d = date(int(bas_dd[:4]), int(bas_dd[4:6]), int(bas_dd[6:8]))
        except ValueError:
            continue

        close = row.get("close")
        if close is None:
            continue
        close = float(close)

        volume = row.get("volume")
        volume = int(volume) if volume is not None else None

        # change_pct: JSON 에 있으면 사용, 없으면 직전 종가 대비 계산
        change_pct = row.get("change_pct")
        if change_pct is None and prev_close is not None and prev_close != 0:
            change_pct = (close - prev_close) / prev_close * 100.0
        elif change_pct is not None:
            change_pct = float(change_pct)

        cur.execute(
            """INSERT INTO stock_daily (corp_code, date, close, change_pct, volume)
               VALUES (%s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE close=VALUES(close),
                                        change_pct=VALUES(change_pct),
                                        volume=VALUES(volume)""",
            (corp_code, d, close, change_pct, volume),
        )
        upserted += 1
        prev_close = close

    return upserted


def main() -> None:
    conn = mariadb_conn()
    cur = conn.cursor()
    ensure_tables(cur)
    conn.commit()

    total = 0
    for corp in CORPS:
        n = load_corp(cur, corp)
        conn.commit()
        print(f"  [{corp}] {n} 행 upsert 완료")
        total += n

    cur.close()
    conn.close()
    print(f"[stock_load] 총 {total} 행 stock_daily 적재 완료")


if __name__ == "__main__":
    main()
