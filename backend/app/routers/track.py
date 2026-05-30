"""POST /api/track/{job} — 잡 수동 트리거.

job: stock | disclosures | all
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..scheduler import run_job

router = APIRouter(tags=["track"])

_VALID_JOBS = {"stock", "disclosures"}


@router.post("/track/{job}")
def trigger_job(job: str) -> dict:
    """잡을 즉시 실행하고 결과를 반환한다."""
    if job == "all":
        results = [run_job(j) for j in ("stock", "disclosures")]  # type: ignore[arg-type]
        return {"results": results}

    if job not in _VALID_JOBS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown job '{job}'. Valid values: stock | disclosures | all",
        )

    return run_job(job)  # type: ignore[return-value]
