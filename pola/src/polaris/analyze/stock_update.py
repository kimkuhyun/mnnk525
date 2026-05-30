"""주가 증분 업데이트 — FinanceDataReader → stock_daily UPSERT.

시드 3사(삼성전자·SK하이닉스·한미반도체) 각각:
  1. stock_daily.date 워터마크(MAX) 조회 — 없으면 2022-01-01
  2. fdr.DataReader(stock_code, 워터마크+1일, 오늘)
  3. stock_daily ON DUPLICATE KEY UPDATE (멱등)

change_pct = (close - prev_close) / prev_close * 100 (직전 거래일 종가 기준).
fdr.DataReader 의 Change 컬럼이 있으면 그것도 후보지만, 워터마크 증분 구간에서
직전 종가가 잘려나갈 수 있으므로 DB에서 직전 close 를 조회하여 계산한다.

실행:  uv run python -m polaris.analyze.stock_update
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from polaris.analyze.stock_load import ensure_tables
from polaris.config import mariadb_conn

# ── 시드 3사: corp_code → KRX 종목코드 ──────────────────────────
# organizations.yml ticker[0] 기준 (config.get_corp_meta 의 fallback 과 동일)
SEED_CORPS: dict[str, str] = {
    "00126380": "005930",  # 삼성전자
    "00164779": "000660",  # SK하이닉스
    "00161383": "042700",  # 한미반도체
}

_WATERMARK_FLOOR = date(2022, 1, 1)


def _get_watermark(cur, corp_code: str) -> date:
    """stock_daily 의 MAX(date) 반환. 행 없으면 _WATERMARK_FLOOR."""
    cur.execute(
        "SELECT MAX(date) FROM stock_daily WHERE corp_code = %s",
        (corp_code,),
    )
    row = cur.fetchone()
    if row and row[0] is not None:
        return row[0]  # pymysql returns datetime.date
    return _WATERMARK_FLOOR


def _get_prev_close(cur, corp_code: str, before_date: date) -> float | None:
    """before_date 직전 거래일의 close 반환. 없으면 None."""
    cur.execute(
        "SELECT close FROM stock_daily WHERE corp_code = %s AND date < %s ORDER BY date DESC LIMIT 1",
        (corp_code, before_date),
    )
    row = cur.fetchone()
    return float(row[0]) if row else None


def _safe_float(v) -> float:
    if v is None:
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def _safe_int(v) -> int:
    if v is None:
        return 0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return 0 if math.isnan(f) else int(f)


def track_stock_corp(cur, corp_code: str, stock_code: str, today: date) -> int:
    """단일 회사 증분 fetch → UPSERT. 삽입/갱신 행 수 반환."""
    try:
        import FinanceDataReader as fdr
    except ImportError:
        raise ImportError(
            "finance-datareader 미설치. 'uv add finance-datareader' 후 재실행."
        )

    watermark = _get_watermark(cur, corp_code)
    start = watermark + timedelta(days=1)

    if start > today:
        print(f"  [{corp_code}/{stock_code}] 이미 최신 (워터마크={watermark}). skip.")
        return 0

    print(f"  [{corp_code}/{stock_code}] {start} ~ {today} fetch 중...")

    try:
        df = fdr.DataReader(stock_code, start.isoformat(), today.isoformat())
    except Exception as e:
        print(f"  [{corp_code}/{stock_code}] fdr.DataReader 오류: {e}")
        return 0

    if df is None or df.empty:
        print(f"  [{corp_code}/{stock_code}] 결과 없음 (휴장 구간일 수 있음).")
        return 0

    df = df.reset_index()
    date_col = df.columns[0]  # 'Date' or 'Datetime'

    # 직전 close (change_pct 계산용) — DB 에서 조회
    rows_sorted = df.sort_values(date_col)
    first_date_in_df: date | None = None
    for _, r in rows_sorted.iterrows():
        d_raw = r[date_col]
        d = d_raw.date() if hasattr(d_raw, "date") else date.fromisoformat(str(d_raw)[:10])
        first_date_in_df = d
        break

    prev_close: float | None = (
        _get_prev_close(cur, corp_code, first_date_in_df)
        if first_date_in_df is not None
        else None
    )

    upserted = 0
    for _, r in rows_sorted.iterrows():
        d_raw = r[date_col]
        d: date = d_raw.date() if hasattr(d_raw, "date") else date.fromisoformat(str(d_raw)[:10])

        close = _safe_float(r.get("Close"))
        if close == 0.0:
            # 거래정지/데이터 없음 — skip
            continue

        volume = _safe_int(r.get("Volume"))

        # change_pct: 직전 종가 대비 계산 우선. fdr Change 컬럼은 소수(0.03 = 3%)
        if prev_close is not None and prev_close != 0:
            change_pct: float | None = (close - prev_close) / prev_close * 100.0
        else:
            fdr_change = r.get("Change")
            if fdr_change is not None:
                fc = _safe_float(fdr_change)
                change_pct = fc * 100.0 if abs(fc) < 1.0 else fc
            else:
                change_pct = None

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


def track_stock() -> None:
    """시드 3사 주가 증분 업데이트 진입점."""
    today = date.today()
    conn = mariadb_conn()
    cur = conn.cursor()

    ensure_tables(cur)
    conn.commit()

    total = 0
    for corp_code, stock_code in SEED_CORPS.items():
        try:
            n = track_stock_corp(cur, corp_code, stock_code, today)
            conn.commit()
            print(f"  [{corp_code}/{stock_code}] {n} 행 upsert 완료")
            total += n
        except Exception as e:
            conn.rollback()
            print(f"  [{corp_code}/{stock_code}] 오류: {e}")

    cur.close()
    conn.close()
    print(f"[stock_update] 총 {total} 행 stock_daily 증분 적재 완료")


def main() -> None:
    track_stock()


if __name__ == "__main__":
    main()
