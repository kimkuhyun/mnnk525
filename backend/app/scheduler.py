"""POLARIS 백그라운드 스케줄러.

주가 잡: 매일 18:30 KST  → polaris.analyze.stock_update
공시 잡: 매일 19:00 KST  → polaris.ingest.disclosure_poll

run_job(name) 은 routers/track.py 에서 수동 트리거에도 재사용.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Literal

from apscheduler.schedulers.background import BackgroundScheduler

# pola 패키지 루트: backend/app/scheduler.py → parents[2] = mnnk525/ → pola/
_POLA = Path(__file__).resolve().parents[2] / "pola"

_JOB_MODULE: dict[str, str] = {
    "stock": "polaris.analyze.stock_update",
    "disclosures": "polaris.ingest.disclosure_poll",
}

_scheduler: BackgroundScheduler | None = None


def _job_cmd(module: str) -> list[str]:
    """pola venv 의 python 으로 직접 실행(백엔드가 이미 uv run 하위라 중첩 uv 회피).
    venv 없으면 uv run 폴백."""
    sub = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    venv_py = _POLA / ".venv" / sub / exe
    if venv_py.exists():
        return [str(venv_py), "-m", module]
    return ["uv", "run", "--directory", str(_POLA), "python", "-m", module]


def _tail(text, n: int = 50) -> str:
    lines = (text or "").strip().splitlines()
    return "\n".join(lines[-n:]) if lines else ""


def run_job(name: Literal["stock", "disclosures"]) -> dict:
    """subprocess 로 잡을 실행하고 결과 dict 반환."""
    module = _JOB_MODULE.get(name)
    if module is None:
        return {"job": name, "returncode": -1, "error": f"unknown job: {name}"}
    try:
        result = subprocess.run(
            _job_cmd(module),
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(_POLA),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        return {
            "job": name,
            "returncode": result.returncode,
            "stdout_tail": _tail(result.stdout),
            "stderr_tail": _tail(result.stderr),
        }
    except subprocess.TimeoutExpired:
        return {"job": name, "returncode": -1, "error": "timeout (600s)"}
    except Exception as exc:
        return {"job": name, "returncode": -1, "error": str(exc)}


def _run_stock() -> None:
    run_job("stock")


def _run_disclosures() -> None:
    run_job("disclosures")


def start_scheduler() -> None:
    """BackgroundScheduler 시작 (중복 시작 방지).

    POLARIS_SCHEDULER=0 이거나 pola 패키지가 없는 환경(예: backend 단독 컨테이너)에서는
    스케줄러를 띄우지 않는다 — 야간 잡이 매번 실패하는 것을 방지(잡은 pola 측에서 실행).
    """
    global _scheduler
    if os.environ.get("POLARIS_SCHEDULER", "1") == "0":
        return
    if not _POLA.exists():
        return
    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    _scheduler.add_job(_run_stock, "cron", hour=18, minute=30, id="stock_daily")
    _scheduler.add_job(_run_disclosures, "cron", hour=19, minute=0, id="disclosures_daily")
    _scheduler.start()


def stop_scheduler() -> None:
    """BackgroundScheduler 정지."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
